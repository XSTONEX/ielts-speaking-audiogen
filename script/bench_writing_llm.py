"""写作批改 / 追问：两个模型同题对比（速度 + 抓错 + 盲评素材）。

用法（在项目根目录）：
    uv run python script/bench_writing_llm.py --limit 1        # 先冒烟，确认两边 key 都能用
    uv run python script/bench_writing_llm.py                  # 全量，默认 gemini-3.8-flash vs deepseek-flash

题目来源：
- script/bench_writing_cases.json：题库原句 + 故意写错的作答（planted 标了埋的错）、
  一字不差 / 换个正确说法的作答（查误报）、带标准答案要点的追问；
- writing_correction/data/*_practice.json 里所有用户的真实作答（运行时读取）。

每题两个模型背靠背各跑一次（先后顺序随机），提示词、温度、超时和线上路由完全一样。
key 只从 .env / 环境变量读，脚本不打印也不落盘任何 key。

输出到 --out 目录：
- results.jsonl：每次调用的原始输出、耗时、重试次数、解析结果
- summary.md：速度、JSON 合法率、分数、埋错命中率、误报
- blind_pairs.json + blind_key.json：A/B 打乱的盲评素材和揭晓表（判卷时只看前者）
"""

import argparse
import glob
import json
import os
import random
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

import requests  # noqa: E402

import core  # noqa: E402  (导入时 load_dotenv)
from routers.writing_logic import _normalize_feedback, _parse_ai_json  # noqa: E402

CASES_FILE = os.path.join(ROOT, 'script', 'bench_writing_cases.json')
T2_BANK = os.path.join(ROOT, core.WRITING_MD_FILE)
T1_BANK = os.path.join(ROOT, core.WRITING_SMALL_MD_FILE)
ERROR_TYPES = {'拼写', '时态', '主谓一致', '单复数', '冠词', '介词', '词性', '用词', '搭配',
               '缺成分', '多余', '非谓语', '句子结构', '漏译', '标点'}
KEY_ENVS = {'gemini': 'WILDAPI_API_KEY', 'deepseek': 'DEEPSEEK_API_KEY'}


# ---------- 题目 ----------

def _bank_refs():
    """中文句 → 英文参考答案（大作文论证块 + 小作文仿写），给真实作答补参考答案用。"""
    refs = {}
    lines = open(T2_BANK, encoding='utf-8').read().split('\n')
    for i, line in enumerate(lines[:-1]):
        if re.match(r'^[A-Z][^一-鿿]+$', line.strip()) and re.search(r'[一-鿿]', lines[i + 1]):
            refs.setdefault(lines[i + 1].strip(), line.strip())
    lines = open(T1_BANK, encoding='utf-8').read().split('\n')
    for i, line in enumerate(lines[:-1]):
        m = re.match(r'\s*- \*\*原句\*\*：(.*)', line)
        z = re.match(r'\s*- \*\*翻译\*\*：(.*)', lines[i + 1])
        if m and z:
            refs.setdefault(z.group(1).strip(), m.group(1).strip())
    return refs


def real_cases():
    refs = _bank_refs()
    cases = []
    for path in sorted(glob.glob(os.path.join(core.WRITING_DATA_DIR, '*_practice.json'))):
        name = os.path.basename(path)
        try:
            records = json.load(open(path, encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        for r in records if isinstance(records, list) else []:
            answer = (r.get('user_translation') or '').strip()
            target = (r.get('target_chinese') or '').strip()
            if not answer or not target:
                continue
            question = (r.get('question') or '').strip() or '（未提供题目）'
            if name.endswith('_template_practice.json'):
                task = r.get('task') or 'task2'
                if r.get('section_name') or r.get('template_text'):
                    question += f"\n\n本句在模板中的位置：{r.get('section_name') or '未标注'}"
                    if r.get('template_text'):
                        question += f"\n对应的模板骨架：{r['template_text']}"
                reference = (r.get('reference') or '').strip()
            else:
                task = 'task1' if name.endswith('_small_practice.json') else 'task2'
                reference = refs.get(target, '')
            cases.append({'id': f"real_{str(r.get('id') or len(cases))[:8]}", 'kind': 'correct', 'task': task,
                          'source': 'real', 'question': question, 'target': target,
                          'reference': reference, 'answer': answer, 'planted': None})
    return cases


def build_messages(case):
    """和线上路由拼提示词的方式一模一样。"""
    if case['kind'] == 'correct':
        cfg = core.load_prompt('writing_small_correct' if case['task'] == 'task1' else 'writing_correct')
        user = cfg['user_prompt'].format(question=case['question'], target=case['target'],
                                         reference=case['reference'] or '（无参考答案）',
                                         translation=case['answer'])
        return cfg, [{'role': 'system', 'content': cfg['system_prompt']}, {'role': 'user', 'content': user}]
    cfg = core.load_prompt('writing_ai_chat_practice')
    system = cfg['system_prompt'].format(
        target_chinese=case['target'], user_translation=case['answer'],
        ai_feedback_summary=case['feedback_summary'], grammar_corrections=case['grammar_corrections'],
        user_query=case['query'])
    return cfg, [{'role': 'system', 'content': system}, {'role': 'user', 'content': case['query']}]


# ---------- 调用 ----------

_local = threading.local()
_real_post = requests.post


def _counting_post(*args, **kwargs):
    """包一层 requests.post，记下每次 HTTP 尝试的耗时（含重试）。"""
    t0 = time.perf_counter()
    try:
        return _real_post(*args, **kwargs)
    finally:
        getattr(_local, 'attempts', []).append(round(time.perf_counter() - t0, 2))


requests.post = _counting_post


def run_one(case, model):
    cfg, messages = build_messages(case)
    _local.attempts = []
    rec = {'case_id': case['id'], 'kind': case['kind'], 'source': case['source'], 'model': model}
    t0 = time.perf_counter()
    try:
        text = core.call_llm({**cfg, 'model': model}, messages)
        rec.update(ok=True, output=text)
    except Exception as exc:  # 只记异常类型和简短信息，不记响应体
        rec.update(ok=False, output='', error=f'{type(exc).__name__}: {str(exc)[:200]}')
    rec['latency'] = round(time.perf_counter() - t0, 2)
    rec['attempts'] = _local.attempts
    if rec['ok'] and case['kind'] == 'correct':
        try:
            fb = _normalize_feedback(_parse_ai_json(rec['output']), case['reference'])
            rec['parsed'] = fb if isinstance(fb, dict) else None
        except (json.JSONDecodeError, ValueError):
            rec['parsed'] = None
    return rec


# ---------- 统计 ----------

def _pct(values, p):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p * (len(s) - 1))))]


def _score(rec):
    try:
        return float(str((rec.get('parsed') or {}).get('score', '')).strip())
    except ValueError:
        return None


def _planted_hits(case, parsed):
    """埋的错被抓到几处：有一条改动的 original 含这个错误片段就算抓到。"""
    origs = [c.get('original', '').lower() for c in (parsed or {}).get('grammar_corrections') or []
             if isinstance(c, dict)]
    hits = 0
    for wrong, _ in case['planted']:
        w = re.compile(r'(?<![A-Za-z])' + re.escape(wrong.lower()) + r'(?![A-Za-z])')
        hits += any(w.search(o) for o in origs)
    return hits


def summarize(cases, results, models):
    by_case = {c['id']: c for c in cases}
    out = [f"# 写作模型对比：{' vs '.join(models)}", '',
           f"时间 {datetime.now():%Y-%m-%d %H:%M}，批改 {sum(c['kind'] == 'correct' for c in cases)} 题"
           f"（真实作答 {sum(c['source'] == 'real' for c in cases)}），追问 {sum(c['kind'] == 'chat' for c in cases)} 题。", '']

    out += ['## 速度（秒，含重试的端到端耗时）', '',
            '| 模型 | 类型 | 次数 | 失败 | 重试 | 中位 | P90 | 最慢 | 平均 | 输出字数中位 |',
            '|---|---|---|---|---|---|---|---|---|---|']
    for m in models:
        for kind in ('correct', 'chat'):
            rs = [r for r in results if r['model'] == m and r['kind'] == kind]
            if not rs:
                continue
            lat = [r['latency'] for r in rs if r['ok']]
            lens = [len(r['output']) for r in rs if r['ok']]
            out.append(f"| {m} | {'批改' if kind == 'correct' else '追问'} | {len(rs)} | "
                       f"{sum(not r['ok'] for r in rs)} | {sum(max(0, len(r['attempts']) - 1) for r in rs)} | "
                       f"{_pct(lat, .5)} | {_pct(lat, .9)} | {max(lat) if lat else '-'} | "
                       f"{round(statistics.mean(lat), 2) if lat else '-'} | {_pct(lens, .5)} |")
    errors = [f"- {r['model']} / {r['case_id']}：{r['error']}" for r in results if not r['ok']]
    if errors:
        out += ['', '失败明细：', *errors]

    out += ['', '## 批改格式与打分', '',
            '| 模型 | JSON 合法 | 分数超出 4.0–7.0 | original 不在原句里 | type 不在规定列表 | 平均分 |',
            '|---|---|---|---|---|---|']
    for m in models:
        rs = [r for r in results if r['model'] == m and r['kind'] == 'correct' and r['ok']]
        parsed = [r for r in rs if r.get('parsed')]
        scores = [s for s in map(_score, parsed) if s is not None]
        bad_orig = bad_type = n_corr = 0
        for r in parsed:
            answer = by_case[r['case_id']]['answer']
            for c in r['parsed'].get('grammar_corrections') or []:
                if not isinstance(c, dict):
                    continue
                n_corr += 1
                bad_orig += c.get('original', '') not in answer
                bad_type += c.get('type', '') not in ERROR_TYPES
        out.append(f"| {m} | {len(parsed)}/{len(rs)} | {sum(not 4.0 <= s <= 7.0 for s in scores)} | "
                   f"{bad_orig}/{n_corr} | {bad_type}/{n_corr} | "
                   f"{round(statistics.mean(scores), 2) if scores else '-'} |")

    if len(models) == 2:
        a, b = models
        pairs = {}
        for r in results:
            if r['kind'] == 'correct' and r.get('parsed'):
                pairs.setdefault(r['case_id'], {})[r['model']] = _score(r)
        diffs = [v[b] - v[a] for v in pairs.values() if v.get(a) is not None and v.get(b) is not None]
        if diffs:
            out += ['', f"同题分差（{b} − {a}）：相同 {sum(d == 0 for d in diffs)}，"
                        f"差 0.5 分 {sum(abs(d) == 0.5 for d in diffs)}，差 1 分及以上 {sum(abs(d) >= 1 for d in diffs)}；"
                        f"平均 {round(statistics.mean(diffs), 2):+}（正数 = {b} 给分更高）。"]

    out += ['', '## 埋错命中与误报（题库 + 故意写错的作答）', '',
            '| 模型 | 埋错命中 | 无错作答被挑错（条） | 无错作答的分数 |', '|---|---|---|---|']
    for m in models:
        hit = total = fp = 0
        clean_scores = []
        for r in results:
            case = by_case[r['case_id']]
            if r['model'] != m or case['kind'] != 'correct' or case['planted'] is None or not r.get('parsed'):
                continue
            if case['planted']:
                total += len(case['planted'])
                hit += _planted_hits(case, r['parsed'])
            else:
                fp += len(r['parsed'].get('grammar_corrections') or [])
                clean_scores.append(f"{case['id']}={r['parsed'].get('score')}")
        out.append(f"| {m} | {hit}/{total} | {fp} | {', '.join(clean_scores)} |")
    out += ['', '埋错命中是按改动的 original 自动匹配的粗略数字；解释对不对要看盲评。']
    return '\n'.join(out) + '\n'


def blind_pairs(cases, results, models, seed):
    rng = random.Random(seed)
    by_case = {c['id']: c for c in cases}
    grouped = {}
    for r in results:
        grouped.setdefault(r['case_id'], {})[r['model']] = r
    pairs, key = [], {}
    for cid, per_model in grouped.items():
        if len(models) != 2 or not all(per_model.get(m, {}).get('ok') for m in models):
            continue
        order = models[:]
        rng.shuffle(order)
        case = by_case[cid]
        item = {'id': cid, 'kind': case['kind'], 'target_chinese': case['target'], 'student_answer': case['answer']}
        if case['kind'] == 'correct':
            item.update(task=case['task'], reference=case['reference'])
            if case['planted'] is not None:
                item['planted_errors'] = case['planted']
        else:
            item.update(prior_feedback=case['grammar_corrections'], question=case['query'],
                        expected_points=case['expect'])
        item['A'], item['B'] = per_model[order[0]]['output'], per_model[order[1]]['output']
        pairs.append(item)
        key[cid] = {'A': order[0], 'B': order[1]}
    rng.shuffle(pairs)
    return pairs, key


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--models', nargs='+', default=['gemini-3.8-flash', 'deepseek-flash'])
    ap.add_argument('--out', default=os.path.join('output', 'bench_writing_llm', datetime.now().strftime('%Y%m%d-%H%M%S')))
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--limit', type=int, default=0, help='批改、追问各只跑前 N 题（冒烟用）')
    ap.add_argument('--no-real', action='store_true', help='不读用户真实作答')
    ap.add_argument('--seed', type=int, default=7)
    args = ap.parse_args()

    for m in args.models:
        env = KEY_ENVS['deepseek' if m.startswith('deepseek') else 'gemini']
        print(f"{m}: {env} {'已设置' if os.getenv(env) else '未设置！'}")

    cases = json.load(open(CASES_FILE, encoding='utf-8'))
    if not args.no_real:
        cases += real_cases()
    if args.limit:
        cases = ([c for c in cases if c['kind'] == 'correct'][:args.limit]
                 + [c for c in cases if c['kind'] == 'chat'][:args.limit])
    os.makedirs(args.out, exist_ok=True)
    json.dump(cases, open(os.path.join(args.out, 'cases.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    rng = random.Random(args.seed)
    jobs = []
    for c in cases:
        order = args.models[:]
        rng.shuffle(order)
        jobs.append((c, order))
    rng.shuffle(jobs)
    print(f'{len(cases)} 题 × {len(args.models)} 个模型，并发 {args.workers}，输出到 {args.out}')

    results, lock = [], threading.Lock()
    out_jsonl = open(os.path.join(args.out, 'results.jsonl'), 'w', encoding='utf-8')

    def work(job):
        case, order = job
        for m in order:
            rec = run_one(case, m)
            with lock:
                results.append(rec)
                out_jsonl.write(json.dumps(rec, ensure_ascii=False) + '\n')
                out_jsonl.flush()
                status = f"{rec['latency']:.1f}s" if rec['ok'] else f"失败 {rec['error'][:80]}"
                print(f"[{len(results)}/{len(jobs) * len(args.models)}] {m:<18} {case['id']:<16} {status}", flush=True)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        list(pool.map(work, jobs))
    out_jsonl.close()

    summary = summarize(cases, results, args.models)
    open(os.path.join(args.out, 'summary.md'), 'w', encoding='utf-8').write(summary)
    pairs, key = blind_pairs(cases, results, args.models, args.seed)
    json.dump(pairs, open(os.path.join(args.out, 'blind_pairs.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    json.dump(key, open(os.path.join(args.out, 'blind_key.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('\n' + summary)
    print(f'结果目录：{os.path.abspath(args.out)}')


if __name__ == '__main__':
    main()

"""精读「AI 讲解」：几个模型同题对比，产出一页能点着看的效果预览。

用法（在项目根目录）：
    uv run python script/bench_reading_explain.py --limit 1 --models wild/claude-opus-5-5   # 先冒烟：一篇、一个模型
    uv run python script/bench_reading_explain.py --only Thomas Organisational              # 只跑有人工对照的两篇
    uv run python script/bench_reading_explain.py                                           # 全量：默认 4 个模型 × 目录里所有文章
    uv run python script/bench_reading_explain.py --models wild/gpt-6.2-astra gemini-3.8-flash@think
    uv run python script/bench_reading_explain.py --models none                         # 不调模型，只把人工对照画出来
    uv run python script/bench_reading_explain.py --merge <结果目录> <结果目录> --out <目录>   # 不调模型，把几次结果合成一份报告

模型名写法和线上一样（见 docs/writing-llm.md）：wild/<名字> 走 WildAPI 的 OpenAI 兼容接口，名字照 gptsapi.net 价目页
（2026-11-26 看到的：claude-fable-5-2 / claude-opus-5-5 / claude-sonnet-5-5 / gpt-6.2-astra / gpt-6.2-sol …）。
另外 gemini-* 后面可以加 @think（开思考，预算 8192）或 @think=4096；aihubmix/ 的 @low / @medium 照旧是它自己的思考档位。
默认比的是 WildAPI 上最强的三档 Claude，加一个便宜的 gemini-3.8-flash 当参照。
WildAPI 自己的 gemini-4-hydrogen 不要比：docs/writing-llm.md 里测过，基本就是 3.8-flash。
key 只从 .env / 环境变量读，脚本不打印也不落盘任何 key；没配 key 的模型自动跳过。

输入：
- --articles 目录里的文章 JSON（线上 intensive_articles/ 里 source=jiufen 的那种），默认 output/reading_explain_bench/articles
- --gold 目录里同名的人工对照（和模型输出同一个格式），有就一起画出来，并拿它给模型打分

每篇文章、每个模型：题组并发各调一次（提示词在 prompts/intensive_explain.yaml），再调一次全篇 overview。
输出到 --out 目录：
- results.json   每次调用的原始回复、耗时、校验后的讲解
- summary.md     每个模型：失败数、耗时、硬伤数（引用对不上 / 填空答案不在证据句 / 判断结论不符）、
                 和九分定位的一致率、和人工对照的一致率
- report.html    效果预览：左边原文、右边题目，点一道题看划词、证据句、对应关系；顶上切文章和模型
"""

import argparse
import glob
import json
import os
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

import yaml  # noqa: E402

from utils import reading_explain as rx  # noqa: E402

core = None   # 要调模型时才导入（导入会 load_dotenv）；--models none 只画人工对照，不碰任何 key

BENCH_DIR = os.path.join(ROOT, 'output', 'reading_explain_bench')
TEMPLATE = os.path.join(ROOT, 'script', 'bench_reading_explain_report.html')
DEFAULT_MODELS = ['wild/claude-fable-5-2', 'wild/claude-opus-5-5', 'wild/claude-sonnet-5-5', 'gemini-3.8-flash']
KEY_ENVS = {'gemini': 'WILDAPI_API_KEY', 'wild': 'WILDAPI_API_KEY', 'deepseek': 'DEEPSEEK_API_KEY',
            'aihubmix': 'AIHUBMIX_API_KEY'}
GOLD = '人工对照'
# gptsapi.net 价目页 2026-11-26 的价格，美元 / 百万 token（输入, 输出）。只用来估花费，没列的模型不估
PRICES = {'wild/claude-fable-5-2': (6.4, 32), 'wild/claude-opus-5-5': (3.2, 16), 'wild/claude-sonnet-5-5': (1.6, 8),
          'wild/gpt-6.2-sol': (1.6, 8), 'wild/gpt-6.2-astra': (6.4, 32), 'gemini-3.8-flash': (0.6, 3)}
USD_CNY = 7.2


def est_tokens(text):
    """粗估 token 数：中转的流式接口不回 usage，只能按字数估。中文和全角标点按 1.3 个 / 字，其余按 3.5 个字符一个。
    实际账单以 WildAPI 后台为准。"""
    cjk = len(re.findall(r'[\u2e80-\u9fff\uff00-\uffef\u3000-\u303f]', text))
    return round(cjk * 1.3 + (len(text) - cjk) / 3.5)
AIHUBMIX_PREFIX = 'aihubmix/'


def load_core():
    global core
    if core is None:
        import core as _core
        # 思考模型出第一个字之前会闷头想一阵，线上写作那个 15 秒的「卡住」阈值在这里太短
        _core.STREAM_STALL_SECONDS = 90
        core = _core
    return core


def model_cfg(base, spec):
    """bench 里的模型写法 → 调用配置。"""
    cfg = {k: v for k, v in base.items() if k in ('temperature', 'max_output_tokens', 'timeout')}
    cfg['model'] = spec
    if not spec.startswith(AIHUBMIX_PREFIX) and '@think' in spec:
        name, _, tail = spec.partition('@think')
        cfg['model'] = name
        cfg['thinking_budget'] = int(tail.lstrip('=') or 8192)
        cfg['max_output_tokens'] = (cfg.get('max_output_tokens') or 16384) + cfg['thinking_budget']
    return cfg


# 同时在飞的请求数。2026-11-26 实测：10 个请求同时发，WildAPI 在 TLS 握手阶段全部断开（SSLEOFError）；3 个没事
SLOTS = threading.BoundedSemaphore(3)


def call(cfg, messages):
    """返回 (解析后的 dict 或 None, 原始回复, 耗时秒, 错误)。解析失败 / 调用失败重试一次。耗时不含排队。"""
    raw, error, secs = '', None, 0
    for attempt in range(2):
        with SLOTS:
            started = time.monotonic()
            try:
                raw = ''.join(core.stream_llm(cfg, messages))
                return rx.parse_reply(raw), raw, round(secs + time.monotonic() - started, 1), None
            except Exception as exc:   # noqa: BLE001  评测脚本：任何失败都记下来继续
                error = f'{type(exc).__name__}: {str(exc)[:200]}'
                secs += time.monotonic() - started
        time.sleep(3)
    return None, raw, round(secs, 1), error


def run_article(base, spec, part, overview=True):
    cfg = model_cfg(base, spec)
    n = len(part['groups'])
    with ThreadPoolExecutor(max_workers=max(1, n)) as pool:
        prompts = [rx.group_messages(base, part, gi) for gi in range(n)]
        replies = list(pool.map(lambda msgs: call(cfg, msgs), prompts))
    groups, calls = {}, []
    for gi, (data, raw, secs, error) in enumerate(replies):
        calls.append({'what': f'g{gi}', 'secs': secs, 'chars': len(raw), 'error': error, 'raw': raw,
                      'tok_in': est_tokens(''.join(m['content'] for m in prompts[gi])), 'tok_out': est_tokens(raw)})
        if data is not None:
            groups[gi] = rx.validate_group(part, gi, data)
    result = {'groups': groups, 'calls': calls, 'overview': None}
    if overview and groups:
        msgs = rx.overview_messages(base, part, groups)
        data, raw, secs, error = call(cfg, msgs)
        calls.append({'what': 'overview', 'secs': secs, 'chars': len(raw), 'error': error, 'raw': raw,
                      'tok_in': est_tokens(''.join(m['content'] for m in msgs)), 'tok_out': est_tokens(raw)})
        if data is not None:
            result['overview'] = rx.validate_overview(part, data)
    return result


def load_gold(path, part):
    if not os.path.exists(path):
        return None
    raw = json.load(open(path, encoding='utf-8'))
    groups = {}
    for gi, data in (raw.get('groups') or {}).items():
        groups[int(gi)] = rx.validate_group(part, int(gi), data)
    overview = rx.validate_overview(part, raw['overview']) if raw.get('overview') else None
    return {'groups': groups, 'calls': [], 'overview': overview}


# ---------- 打分 ----------

def _key_tokens(expl):
    words = set()
    for m in expl.get('marks') or []:
        if m['role'] in ('题眼', '特别的字'):
            words |= {w for w in re.findall(r"[a-z']+", m['text'].lower()) if len(w) > 2}
    return words


def score(run, gold, part):
    """一篇文章上一个模型的各项计数。"""
    c = {'questions': 0, 'missing': 0, 'hard': 0, 'hard_q': 0, 'soft': 0, 'jf_total': 0, 'jf_agree': 0,
         'gold_total': 0, 'gold_ev': 0, 'gold_eye': 0, 'marks': 0, 'pairs': 0}
    for gi, g in enumerate(part['groups']):
        for q in g.get('questions') or []:
            c['questions'] += 1
            e = ((run['groups'].get(gi) or {}).get('questions') or {}).get(str(q.get('num')))
            if not e or e.get('missing'):
                c['missing'] += 1
                continue
            hard = rx.hard_issues(e['issues'])
            c['hard'] += len(hard)
            c['hard_q'] += 1 if hard else 0
            c['soft'] += len(e['issues']) - len(hard)
            c['marks'] += len(e['marks'])
            c['pairs'] += e['pairs']
            if e.get('jiufen'):
                c['jf_total'] += 1
                c['jf_agree'] += 1 if e['jiufen']['agree'] else 0
            ge = ((gold['groups'].get(gi) or {}).get('questions') or {}).get(str(q.get('num'))) if gold else None
            if ge and not ge.get('missing'):
                c['gold_total'] += 1
                c['gold_ev'] += 1 if set(e['evidence']) & set(ge['evidence']) else 0
                c['gold_eye'] += 1 if _key_tokens(e) & _key_tokens(ge) else 0
    return c


def pct(a, b):
    return f'{a}/{b}（{round(100 * a / b)}%）' if b else '—'


def summarize(models, articles, runs):
    lines = ['# 精读 AI 讲解：模型对比', '',
             f'文章 {len(articles)} 篇：' + '、'.join(a['title'] for a in articles), '',
             '| 模型 | 调用失败 | 题组耗时 中位 / 最长 | 缺题 | 有硬伤的题 | 硬伤条数 | 小问题 | 和九分定位一致 | 证据句同人工 | 题眼同人工 |',
             '|---|---|---|---|---|---|---|---|---|---|']
    for m in models:
        total = {}
        secs, failed, ncalls = [], 0, 0
        for a in articles:
            run = runs[a['id']].get(m)
            if not run:
                continue
            for k, v in score(run, runs[a['id']].get(GOLD) if m != GOLD else None, a['part']).items():
                total[k] = total.get(k, 0) + v
            for c in run['calls']:
                ncalls += 1
                failed += 1 if c['error'] else 0
                if not c['error'] and c['what'] != 'overview':
                    secs.append(c['secs'])
        if not total:
            continue
        speed = f'{statistics.median(secs):.0f}s / {max(secs):.0f}s' if secs else '—'
        lines.append(f"| {m} | {failed}/{ncalls} | {speed} | {total['missing']} | "
                     f"{pct(total['hard_q'], total['questions'] - total['missing'])} | {total['hard']} | {total['soft']} | "
                     f"{pct(total['jf_agree'], total['jf_total'])} | {pct(total['gold_ev'], total['gold_total'])} | "
                     f"{pct(total['gold_eye'], total['gold_total'])} |")
    lines += ['', '- 硬伤：引用的词在题目 / 原文里找不到、填空答案不在它给的证据句里、判断结论和标准答案不符、没给证据句。',
              '- 小问题：句号报错（词在别的句子）、对应组数不够、题眼不是恰好一个。',
              '- 和九分定位一致：模型的证据句落在九分给的范围里。不一致不等于模型错，要逐题看（report.html 里标了「≠九分」）。',
              '- 后两列只统计有人工对照的文章。', '']
    for a in articles:
        lines.append(f"## {a['title']}")
        for m in models:
            run = runs[a['id']].get(m)
            if not run:
                continue
            name = m.split('@')[0]
            if name in PRICES and run['calls'] and all('tok_in' in c for c in run['calls']):
                tin, tout = sum(c['tok_in'] for c in run['calls']), sum(c['tok_out'] for c in run['calls'])
                usd = (tin * PRICES[name][0] + tout * PRICES[name][1]) / 1e6
                lines.append(f"- {m} · 估算花费：输入约 {tin} token、输出约 {tout} token，约 ${usd:.2f}（¥{usd * USD_CNY:.1f}）；"
                             f"全部调用耗时合计 {sum(c['secs'] for c in run['calls']):.0f} 秒")
            for gi, g in sorted(run['groups'].items()):
                for num, e in g['questions'].items():
                    notes = list(e['issues'])
                    if e.get('jiufen') and not e['jiufen']['agree']:
                        notes.append(f"≠九分：模型 {e['evidence']}，九分 {e['jiufen']['range']}")
                    if notes:
                        lines.append(f"- {m} · Q{num}：" + '；'.join(notes))
            for c in run['calls']:
                if c['error']:
                    lines.append(f"- {m} · {c['what']} 调用失败：{c['error']}")
        lines.append('')
    return '\n'.join(lines)


def report_data(models, articles, runs):
    out = []
    for a in articles:
        part = a['part']
        sents = [{'i': i, 'label': label, 'en': text, 'para': k} for i, label, text, k in rx.sentences(part)]
        zh = {s.get('i'): s.get('zh') or '' for p in part.get('paragraphs') or [] for s in p.get('sentences') or []}
        for s in sents:
            s['zh'] = zh.get(s['i'], '')
        groups = []
        for gi, g in enumerate(part['groups']):
            qs = []
            for q in g.get('questions') or []:
                stem, opts = rx.question_view(g, q)
                qs.append({'num': str(q.get('num')), 'stem': stem, 'opts': opts, 'answer': q.get('answer') or '',
                           'user': q.get('user_answer') or '', 'state': q.get('state') or '', 'zh': q.get('zh') or ''})
            gtype = rx.group_type(g)
            groups.append({'range': g.get('range') or '', 'type': gtype, 'type_name': rx.TYPE_NAMES.get(gtype, gtype),
                           'instruction': rx._plain(g.get('instruction_html')), 'questions': qs})
        shown = {}
        for m in models:
            run = runs[a['id']].get(m)
            if run:
                shown[m] = {'groups': {str(gi): g for gi, g in run['groups'].items()}, 'overview': run['overview'],
                            'calls': [{k: c[k] for k in ('what', 'secs', 'chars', 'error')} for c in run['calls']]}
        out.append({'id': a['id'], 'title': part.get('title') or a['id'], 'sentences': sents, 'groups': groups, 'runs': shown})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--articles', default=os.path.join(BENCH_DIR, 'articles'))
    ap.add_argument('--gold', default=os.path.join(BENCH_DIR, 'gold'))
    ap.add_argument('--models', nargs='*', default=DEFAULT_MODELS)
    ap.add_argument('--limit', type=int, default=0, help='只跑前 N 篇')
    ap.add_argument('--only', nargs='*', default=[], help='只跑文件名里含这些文字之一的文章')
    ap.add_argument('--no-overview', action='store_true')
    ap.add_argument('--concurrency', type=int, default=3, help='同时在飞的请求数')
    ap.add_argument('--merge', nargs='*', default=[], help='不调模型：把这几个结果目录的 results.json 合成一份报告')
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    global SLOTS
    SLOTS = threading.BoundedSemaphore(max(1, args.concurrency))
    base = yaml.safe_load(open(os.path.join(ROOT, 'prompts', 'intensive_explain.yaml'), encoding='utf-8'))
    models = []
    for spec in args.models:
        if spec == 'none':
            continue
        load_core()
        env = KEY_ENVS[core._provider(model_cfg(base, spec)['model'])]
        if not os.getenv(env):
            print(f'跳过 {spec}：没配 {env}')
            continue
        models.append(spec)

    articles = []
    for path in sorted(glob.glob(os.path.join(args.articles, '*.json'))):
        if args.only and not any(o in os.path.basename(path) for o in args.only):
            continue
        obj = json.load(open(path, encoding='utf-8'))
        if obj.get('exam'):
            articles.append({'id': os.path.basename(path)[:-5], 'title': obj['exam'].get('title') or obj.get('title'),
                             'part': obj['exam']})
    if args.limit:
        articles = articles[:args.limit]
    if not articles:
        sys.exit(f'{args.articles} 里没有文章 JSON')

    merged = {}
    for folder in args.merge:
        for aid, by_model in json.load(open(os.path.join(folder, 'results.json'), encoding='utf-8')).items():
            for m, run in by_model.items():
                run['groups'] = {int(gi): g for gi, g in run['groups'].items()}
                merged.setdefault(aid, {})[m] = run
    if args.merge:
        articles = [a for a in articles if a['id'] in merged]
        models = [m for m in dict.fromkeys(m for r in merged.values() for m in r) if m != GOLD]

    runs = {}
    for a in articles:
        runs[a['id']] = dict(merged.get(a['id']) or {})
        gold = load_gold(os.path.join(args.gold, a['id'] + '.json'), a['part'])
        if gold:
            runs[a['id']][GOLD] = gold
        if models and not args.merge:
            print(f"{a['title']}：{len(a['part']['groups'])} 个题组 × {len(models)} 个模型 …", flush=True)
            with ThreadPoolExecutor(max_workers=len(models)) as pool:
                done = list(pool.map(lambda m: run_article(base, m, a['part'], not args.no_overview), models))
            for m, run in zip(models, done):
                runs[a['id']][m] = run
                failed = [c['what'] for c in run['calls'] if c['error']]
                print(f"  {m}: {sum(c['secs'] for c in run['calls']):.0f}s" + (f"，失败 {failed}" if failed else ''), flush=True)

    shown = ([GOLD] if any(GOLD in r for r in runs.values()) else []) + models
    out = args.out or os.path.join(BENCH_DIR, datetime.now().strftime('%Y%m%d-%H%M%S'))
    os.makedirs(out, exist_ok=True)
    json.dump(runs, open(os.path.join(out, 'results.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    summary = summarize(shown, articles, runs)
    open(os.path.join(out, 'summary.md'), 'w', encoding='utf-8').write(summary)
    data = json.dumps(report_data(shown, articles, runs), ensure_ascii=False).replace('</', '<\\/')
    page = open(TEMPLATE, encoding='utf-8').read().replace('/*DATA*/null', data)
    open(os.path.join(out, 'report.html'), 'w', encoding='utf-8').write(page)
    print(summary.split('\n## ')[0])
    print(f'结果在 {os.path.relpath(out, ROOT)}/ ：report.html（效果预览）、summary.md、results.json')


if __name__ == '__main__':
    main()

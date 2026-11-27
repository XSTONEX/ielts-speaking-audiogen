"""精读「AI 讲解」：把九分学长导入的一篇阅读（exam part）拼成提示词，并校验模型的输出。

这里只有纯函数，不调模型：
- group_type()            题组 → 题型（决定用 prompts/intensive_explain.yaml 里哪一段方法）
- group_messages()        一个题组的提示词
- parse_reply()           模型回复 → dict
- validate_group()        逐题校验 + 把引用的词换算成页面能直接画的下标
- overview_messages() / validate_overview()   全篇那一次调用

校验的原则：模型引用的每个词都必须能在题目 / 原文里原样找到，找不到的引用直接丢掉并记一条问题；
填空题的答案必须出现在它给的证据句里；判断题的 T/F/NG 必须和标准答案一致。
这些都是不看内容就能判的硬伤，评测脚本拿它们比较模型，线上拿它们决定要不要重试。
"""

import html
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

ROLES = ('定位词', '题眼', '特别的字', '辅助')
RELS = ('原词', '同替', '上下义', '词形', '反向', '无对应')
TYPE_NAMES = {
    'judge': '判断题', 'blank': '填空题', 'choose_two': '双选题', 'single_choice': '单选题',
    'para_match': '段落信息配对', 'name_match': '人名配对', 'heading': '小标题', 'match': '配对题',
}
# 每种题型「证据算确认」至少要几组对应
MIN_PAIRS = {'heading': 3}
# 硬伤：不看内容就能判定模型错了
HARD_ISSUES = ('题目里找不到引用', '原文里找不到引用', '答案不在证据句里', '判断结论和答案不符', '没有证据句', '缺这道题')

_NORM = str.maketrans({
    '‘': "'", '’': "'", '‚': "'", '′': "'", '“': '"', '”': '"', '″': '"',
    '–': '-', '—': '-', '‑': '-', ' ': ' ', ' ': ' ', ' ': ' ',
})


def _u16(text):
    return len(text.encode('utf-16-le')) // 2


def _plain(raw):
    return ' '.join(html.unescape(re.sub(r'<[^>]*>', ' ', raw or '')).split())


def _norm(text):
    """比对用：弯引号、破折号、不换行空格统一掉，转小写。逐字符替换，长度不变，下标可以直接回到原文。"""
    out = (text or '').translate(_NORM).lower()
    return out if len(out) == len(text or '') else (text or '').translate(_NORM)


def find_span(hay, needle):
    """needle 在 hay 里的位置 (起, 止)，按 UTF-16 下标（和页面高亮一致）；找不到返回 None。
    大小写、弯引号、空白宽度不计较；模型多抄了首尾标点也能对上。"""
    if not hay or not needle or not needle.strip():
        return None
    h = _norm(hay)
    for cand in (needle.strip(), needle.strip().strip('.,;:!?"\'()[]…')):
        n = _norm(cand)
        if not n:
            continue
        # 先按整词找（on 不该对上 presented 里的 on），再退到子串，最后放宽空白
        m = re.search(r'(?<![a-z0-9])' + re.escape(n) + r'(?![a-z0-9])', h) \
            or re.search(re.escape(n), h) \
            or re.search(r'\s+'.join(re.escape(w) for w in n.split()), h)
        if not m:
            continue
        i, end = m.start(), m.end()
        return _u16(hay[:i]), _u16(hay[:end])
    return None


# ---------- 文章和题目的统一视图 ----------

def sentences(part):
    """[(句号, 段落标签, 英文, 第几段)]。没有标签的段落（九分把小标题单独切成一段时）沿用上一段的。"""
    rows, label = [], None
    for k, para in enumerate(part.get('paragraphs') or []):
        sents = para.get('sentences') or []
        lead = re.match(r'\s*\(([A-Z])\)\s', (sents[0].get('en') or '') if sents else '')
        label = para.get('label') or (lead.group(1) if lead else label)
        for s in sents:
            rows.append((s.get('i'), label, s.get('en') or '', k))
    return rows


def passage_text(part):
    lines, last = [], object()
    for i, label, text, k in sentences(part):
        mark = label or k
        if mark != last:
            lines.append(f"\n¶ {label or ('第 %d 段' % (k + 1))}")
            last = mark
        lines.append(f'[{i}] {text}')
    return '\n'.join(lines).strip()


def group_type(group):
    kind = group.get('kind')
    gtype = (group.get('type') or '').lower()
    sub = (group.get('subtype') or '').lower()
    instr = _plain(group.get('instruction_html'))
    if kind == 'judge':
        return 'judge'
    if kind == 'blank':
        return 'blank'
    if 'heading' in sub or re.search(r'\bheadings?\b', instr, re.I):
        return 'heading'
    if 'person' in sub or re.search(r'list of (people|persons|researchers|scientists|experts|writers)|correct (person|researcher|scientist)', instr, re.I):
        return 'name_match'
    if gtype == 'map' or re.search(r'which (paragraph|section)', instr, re.I):
        return 'para_match'
    if 'ir-blank' in (group.get('content_html') or '') and group.get('options') and re.search(r'summary|notes|table|flow', instr, re.I):
        return 'blank'      # 从词库里选词填空
    if gtype in ('multiple-choice', 'single-choice'):
        return 'choose_two' if re.search(r'\b(TWO|THREE)\b', instr) else 'single_choice'
    return 'match'


def _layout_stems(group):
    """原题版式里每个空所在的那一格文字：{题号: 文字}。小标题题的题干只有 Paragraph，靠它补出是哪一段。"""
    out = {}
    for cell in re.findall(r'<td[^>]*>(.*?)</td>', group.get('content_html') or '', re.S):
        nums = re.findall(r'data-q="([^"]+)"', cell)
        if len(nums) != 1:
            continue
        text = re.sub(r'<span class="ir-blank"[^>]*>.*?</span>', ' ', cell, flags=re.S)
        text = _plain(re.sub(r'<(strong|b)>\s*%s\s*</\1>' % re.escape(nums[0]), ' ', text))
        if text:
            out[nums[0]] = text
    return out


def question_view(group, q):
    """一道题讲解时用的文字：题干（小标题 / 名字配对补全）和它能用的选项 {编号: 文字}。"""
    stem = (q.get('text') or '').strip()
    cell = _layout_stems(group).get(str(q.get('num')))
    if cell and (len(stem) < 12 or stem in cell) and '____' not in stem:
        stem = cell
    stem = re.sub(r'^\s*%s\s+' % re.escape(str(q.get('num'))), '', stem)
    opts = {}
    for o in group.get('options') or []:
        if isinstance(o, dict) and o.get('text'):
            opts[str(o.get('key'))] = o['text']
    own = [o for o in q.get('options') or [] if isinstance(o, dict)]
    if not own and group.get('kind') == 'choice':
        for other in group.get('questions') or []:
            if other.get('options'):
                own = [o for o in other['options'] if isinstance(o, dict)]
                break
    for o in own:
        if o.get('text'):
            opts[str(o.get('key'))] = o['text']
    return stem, opts


def _answer_label(q, opts):
    ans = q.get('answer') or ''
    return f"{ans}（{opts[ans]}）" if ans in opts else ans


def _user_label(q, opts):
    user = q.get('user_answer') or ''
    state = q.get('state')
    if state == 'right':
        return '答对'
    if not user:
        return '没作答'
    shown = f"{user}（{opts[user]}）" if user in opts else user
    return f'{shown} ✗'


def group_messages(cfg, part, gi):
    group = part['groups'][gi]
    gtype = group_type(group)
    views = [(q, *question_view(group, q)) for q in group.get('questions') or []]
    shared = None
    all_opts = [opts for _, _, opts in views]
    if all_opts and all(o == all_opts[0] for o in all_opts) and all_opts[0] and gtype != 'judge':
        shared = all_opts[0]
    layout = ''
    if group.get('content_html') and gtype == 'blank':
        text = re.sub(r'<span class="ir-blank"[^>]*data-q="([^"]+)"[^>]*>.*?</span>', r' __(\1)__ ', group['content_html'], flags=re.S)
        layout = '原题版式（__(n)__ 是第 n 题的空）：\n' + _plain(text) + '\n\n'
    options = ''
    if shared:
        options = '选项：\n' + '\n'.join(f'  {k}  {v}' for k, v in shared.items()) + '\n\n'
    lines = []
    for q, stem, opts in views:
        row = [f"Q{q.get('num')}  {stem}"]
        if not shared and opts and gtype != 'judge':
            row += [f'    {k}  {v}' for k, v in opts.items()]
        row.append(f'    标准答案：{_answer_label(q, opts)}    学生：{_user_label(q, opts)}')
        lines.append('\n'.join(row))
    user = cfg['user_prompt'].format(
        title=part.get('title') or '', passage=passage_text(part), range=group.get('range') or '',
        method=(cfg.get('methods') or {}).get(gtype) or (cfg.get('methods') or {}).get('match') or '',
        instruction=_plain(group.get('instruction_html')), layout=layout, options=options,
        questions='\n\n'.join(lines))
    return [{'role': 'system', 'content': cfg['system_prompt']}, {'role': 'user', 'content': user}]


def parse_reply(text):
    text = (text or '').strip()
    m = re.match(r'^```(?:json)?\s*(.*?)\s*```$', text, re.S)
    text = m.group(1) if m else text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        i, j = text.find('{'), text.rfind('}')
        if i < 0 or j <= i:
            raise
        return json.loads(text[i:j + 1])


# ---------- 校验 ----------

def _text(value, limit=200):
    return ' '.join(str(value).split())[:limit] if value not in (None, '', 'null') else ''


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _verdict_of(q, opts):
    label = (opts.get(q.get('answer') or '') or q.get('answer') or '').upper()
    if 'NOT' in label:
        return 'NG'
    if label in ('TRUE', 'YES'):
        return 'T'
    if label in ('FALSE', 'NO'):
        return 'F'
    return ''


def validate_group(part, gi, data):
    """模型一个题组的输出 → {'type', 'questions': {题号: 讲解}}。每题带 issues（问题清单）和 jiufen（和九分定位比）。"""
    group = part['groups'][gi]
    gtype = group_type(group)
    sent = {i: text for i, _, text, _ in sentences(part)}
    order = sorted(sent)
    rows = data.get('questions') if isinstance(data, dict) else data
    by_num = {str(r.get('num')).strip().lstrip('Qq'): r for r in rows or [] if isinstance(r, dict)}
    out = {}
    for q in group.get('questions') or []:
        num = str(q.get('num'))
        stem, opts = question_view(group, q)
        raw = by_num.get(num)
        if not raw:
            out[num] = {'num': num, 'missing': True, 'issues': ['缺这道题'], 'marks': [], 'evidence': []}
            continue
        issues = []
        evidence = []
        for s in raw.get('evidence') if isinstance(raw.get('evidence'), list) else [raw.get('evidence')]:
            s = _int(s)
            if s in sent and s not in evidence:
                evidence.append(s)

        def locate_p(p, s):
            """p 在第 s 句；模型报错句号时先找证据句，再找前后两句。返回 (句号, 起, 止) 或 None。"""
            tried = [s] if s in sent else []
            tried += [e for e in evidence if e not in tried]
            for base in list(tried):
                k = order.index(base)
                tried += [order[j] for j in (k - 1, k + 1, k - 2, k + 2) if 0 <= j < len(order) and order[j] not in tried]
            for cand in tried:
                span = find_span(sent[cand], p)
                if span:
                    return cand, span
            hits = [(i, find_span(sent[i], p)) for i in order]
            hits = [(i, sp) for i, sp in hits if sp]
            return hits[0] if len(hits) == 1 else None

        marks = []
        for m in raw.get('marks') or []:
            if not isinstance(m, dict) or not _text(m.get('text')):
                continue
            text = _text(m.get('text'))
            where = str(m.get('in') or 'stem').strip()
            key = where.split(':', 1)[1].strip() if where.startswith('opt') and ':' in where else None
            places = [('stem', None, stem)] if key is None else [('opt', key, opts.get(key, ''))]
            places += [('stem', None, stem)] + [('opt', k, v) for k, v in opts.items() if k == q.get('answer')]
            if gtype == 'blank':   # 表格 / 流程图里同一行别的格子（行标题、人名）也能当定位词，它们只在原题版式里
                places.append(('layout', None, _plain(group.get('content_html'))))
            hit = next(((w, k, find_span(body, text)) for w, k, body in places if find_span(body, text)), None)
            if not hit:
                issues.append(f'题目里找不到引用：{text}')
                continue
            role = m.get('role') if m.get('role') in ROLES else '辅助'
            mark = {'in': hit[0], 'key': hit[1], 'text': text, 'qs': hit[2][0], 'qe': hit[2][1], 'role': role,
                    'rel': m.get('rel') if m.get('rel') in RELS else '', 'zh': _text(m.get('zh'), 60)}
            p = _text(m.get('p'))
            if p:
                found = locate_p(p, _int(m.get('s')))
                if found:
                    mark.update(p=p, s=found[0], ps=found[1][0], pe=found[1][1])
                    if found[0] != _int(m.get('s')):
                        issues.append(f"句号报错了：{p}（说在 {m.get('s')}，实际在 {found[0]}）")
                else:
                    issues.append(f'原文里找不到引用：{p}')
            marks.append(mark)

        for s in [m['s'] for m in marks if m.get('p')]:
            if not evidence:
                evidence.append(s)
        if not evidence:
            issues.append('没有证据句')

        matched = [m for m in marks if m.get('p')]
        groups_n = len({(m['s'], m['ps']) for m in matched})
        verdict = _text(raw.get('verdict'), 4).upper() or None
        answer_text = _text(raw.get('answer_text')) or None
        want = _verdict_of(q, opts) if gtype == 'judge' else ''
        if gtype == 'judge':
            if want and (verdict or '')[:1] != want[:1]:
                issues.append(f'判断结论和答案不符：给了 {verdict}，答案是 {want}')
            if want == 'NG' and any(m['role'] == '题眼' and m.get('p') for m in marks):
                issues.append('NG 题的题眼不该有原文对应')
        if gtype == 'blank' and (q.get('answer') or '') not in opts:   # 词库选词的答案是选项编号，不查
            variants = [a.strip() for a in (q.get('answer') or '').split('|') if a.strip()]
            pool = ' '.join(sent[s] for s in evidence)
            if variants and not any(find_span(pool, a) for a in variants):
                where = [i for i in order if any(find_span(sent[i], a) for a in variants)]
                issues.append(f"答案不在证据句里：{variants[0]}（证据 {evidence}，答案实际出现在 {where[:4]}）")
            if not answer_text or not find_span(pool, answer_text):
                answer_text = next((a for a in variants if find_span(pool, a)), None)
        need = MIN_PAIRS.get(gtype, 2)
        if want != 'NG' and groups_n < need:
            issues.append(f'对应不够：只有 {groups_n} 组，这种题型要 {need} 组')
        if gtype in ('judge', 'blank', 'single_choice') and sum(1 for m in marks if m['role'] == '题眼') != 1:
            issues.append('题眼应该有且只有一个')

        steps = [_text(s, 120) for s in raw.get('steps') or [] if _text(s)][:4]
        wrong = [{'key': str(w.get('key')), 'type': _text(w.get('type'), 20), 'why': _text(w.get('why'), 80)}
                 for w in raw.get('wrong_options') or [] if isinstance(w, dict) and str(w.get('key')) in opts]
        jf = q.get('evidence')
        jiufen = None
        if jf:
            jiufen = {'range': jf, 'agree': any(jf[0] <= s <= jf[1] for s in evidence), 'width': jf[1] - jf[0] + 1}
        out[num] = {
            'num': num, 'marks': marks, 'eye_type': _text(raw.get('eye_type'), 10) or None,
            'predict': _text(raw.get('predict'), 60) or None, 'evidence': evidence, 'answer_text': answer_text,
            'verdict': verdict, 'steps': steps, 'rule': _text(raw.get('rule'), 80) or None,
            'trap': _text(raw.get('trap'), 100) or None, 'wrong_options': wrong,
            'slip': (_text(raw.get('slip'), 120) or None) if q.get('state') != 'right' else None,
            'vocab_gate': _text(raw.get('vocab_gate'), 40) or None, 'doubt': _text(raw.get('doubt'), 160) or None,
            'pairs': groups_n, 'issues': issues, 'jiufen': jiufen,
        }
    return {'type': gtype, 'questions': out}


def hard_issues(issues):
    return [i for i in issues or [] if i.startswith(HARD_ISSUES)]


# ---------- 全篇 ----------

def overview_messages(cfg, part, groups):
    """groups：{题组下标: validate_group 的结果}。"""
    evidence, pairs = [], []
    for gi in sorted(groups):
        for num, e in groups[gi]['questions'].items():
            if e.get('evidence'):
                evidence.append(f"Q{num}：{e['evidence']}")
            for m in e.get('marks') or []:
                if m.get('p') and m.get('rel') != '原词' and _norm(m['p']) != _norm(m['text']):
                    pairs.append(f"Q{num}  {m['text']}  ↔  {m['p']}（{m.get('rel') or '对应'}）")
    user = cfg['overview_user_prompt'].format(
        title=part.get('title') or '', passage=passage_text(part),
        evidence='\n'.join(evidence) or '（无）', pairs='\n'.join(pairs) or '（无）')
    return [{'role': 'system', 'content': cfg['overview_system_prompt']}, {'role': 'user', 'content': user}]


def validate_overview(part, data):
    sent = {i: text for i, _, text, _ in sentences(part)}
    issues = []
    data = data if isinstance(data, dict) else {}
    paragraphs = [{'label': _text(p.get('label'), 12), 'gist': _text(p.get('gist'), 80), 'repeat': _text(p.get('repeat'), 160) or None}
                  for p in data.get('paragraphs') or [] if isinstance(p, dict)]
    pairs = [{k: _text(p.get(k), 80) or None for k in ('q', 'p', 'q_zh', 'p_zh', 'note')}
             for p in data.get('pairs') or [] if isinstance(p, dict) and _text(p.get('q')) and _text(p.get('p'))]
    vocab = []
    for v in data.get('vocab') or []:
        if not isinstance(v, dict) or not _text(v.get('word')):
            continue
        word, s = _text(v.get('word'), 60), _int(v.get('s'))
        span = find_span(sent.get(s, ''), word)
        if not span:
            hits = [(i, find_span(t, word)) for i, t in sent.items()]
            hits = [(i, sp) for i, sp in hits if sp]
            if not hits:
                issues.append(f'词汇不在原文里：{word}')
                continue
            s, span = hits[0]
        vocab.append({'word': word, 'lemma': _text(v.get('lemma'), 40) or word, 'meaning': _text(v.get('meaning'), 60),
                      'tier': '必背' if '必' in str(v.get('tier')) else '眼熟', 'why': _text(v.get('why'), 20),
                      's': s, 'ps': span[0], 'pe': span[1], 'family': _text(v.get('family'), 100) or None})
    vocab.sort(key=lambda v: v['tier'] != '必背')
    hard = [{'s': _int(h.get('s')), 'core': _text(h.get('core'), 300), 'note': _text(h.get('note'), 160)}
            for h in data.get('hard') or [] if isinstance(h, dict) and _int(h.get('s')) in sent]
    return {'paragraphs': paragraphs, 'pairs': pairs, 'vocab': vocab, 'hard': hard, 'issues': issues}


# ---------- 一篇文章从头到尾生成一遍 ----------

def _hard_count(group):
    return sum(len(hard_issues(e['issues'])) for e in group['questions'].values())


def generate(part, cfg, llm, on_update=None, workers=3):
    """讲完一篇：每个题组调一次模型（并发），再调一次全篇。返回存盘用的 dict。

    llm(cfg, messages) -> 回复文本，出错就抛异常；on_update(state) 每讲完一块调一次（页面边生成边看）。
    一个题组回来的东西解析不了、缺题或有硬伤（引用对不上之类）就再要一次，两次里留硬伤少的那份。
    status：done 全部讲完；partial 有题组没讲出来；error 一个都没讲出来。"""
    n = len(part.get('groups') or [])
    state = {'status': 'running', 'model': cfg.get('model'), 'started_at': datetime.now().isoformat(),
             'total': n + 1, 'done': 0, 'groups': {}, 'overview': None, 'errors': []}
    lock = threading.Lock()

    def tell():
        if on_update:
            on_update(state)

    def one(gi):
        best, error = None, None
        for _ in range(2):
            try:
                out = validate_group(part, gi, parse_reply(llm(cfg, group_messages(cfg, part, gi))))
            except Exception as exc:   # 模型、网络、JSON 任何一环出错都算这次没讲出来
                error = f'{type(exc).__name__}: {str(exc)[:160]}'
                continue
            if best is None or _hard_count(out) < _hard_count(best):
                best = out
            if not _hard_count(best):
                break
        return gi, best, error

    tell()
    if n:
        with ThreadPoolExecutor(max_workers=max(1, min(workers, n))) as pool:
            for fut in as_completed([pool.submit(one, gi) for gi in range(n)]):
                gi, best, error = fut.result()
                with lock:
                    state['done'] += 1
                    if best is not None:
                        state['groups'][gi] = best
                    else:
                        state['errors'].append(f"第 {gi + 1} 组（{(part['groups'][gi].get('range') or '').strip()}）没讲出来：{error}")
                    tell()
    if state['groups']:
        try:
            state['overview'] = validate_overview(part, parse_reply(llm(cfg, overview_messages(cfg, part, state['groups']))))
        except Exception as exc:
            state['errors'].append(f'全篇分析没出来：{type(exc).__name__}: {str(exc)[:160]}')
    state['done'] = state['total']
    state['status'] = 'done' if len(state['groups']) == n and state['overview'] else ('partial' if state['groups'] else 'error')
    state['finished_at'] = datetime.now().isoformat()
    tell()
    return state

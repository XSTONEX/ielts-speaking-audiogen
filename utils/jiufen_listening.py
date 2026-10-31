"""九分学长听力作答 JSON → 听力精听项目（逐句字幕 + 题目 + 这一次的作答和划线）。

两种形状都认：
- 单篇练习：data.attempt.parts[0] 是题目和原文，作答在 attempt 里，划线在 data.annotationSnapshot，
  题目名在 data.unit.title，用时在 attempt.elapsedSeconds；
- 组卷：data.parts[i] 是每个 Part 的题目和原文，data.children[i] 是这个 Part 自己的作答和划线
  （按 partId 对上）；没有题目名（有的题组带 title），也没有每个 Part 的用时。
题目、答案、解析复用 utils/jiufen_import（精读导入那套），这里只补听力要的：音频链接、带时间的逐句字幕、
题组 id、配对题、按题组存的划线。

原文直接用 articleJson 的逐句字幕，sentence_index 就是精听页的句子 id，所以题目里的
sentenceIndex（如 "17-19"）能直接对到字幕上的出处。
下标一律按 UTF-16 计，和页面上的 JS 下标一致。
"""

import json
import re
from html.parser import HTMLParser

from utils import jiufen_import as base
from utils.jiufen_import import JiufenFormatError

# 看题的静音有时被并进下一句的第一个词（"Now" 从 30 秒拖到 68 秒）；这么长的词按它结束前半秒算句子开头
LONG_WORD_SECONDS = 2.5


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def text_content(raw):
    """和浏览器的 textContent 一样：只取文字，实体解码，空白原样保留（<input> 不占位置）。"""
    if not raw:
        return ''
    p = _Text()
    p.feed(str(raw))
    p.close()
    return ''.join(p.parts)


def _iso(value):
    """'2026-09-24 08:05:08' → '2026-09-24T08:05:08'（Safari 解析不了中间是空格的写法）。"""
    text = base._clean(value)
    return text.replace(' ', 'T', 1) if re.match(r'^\d{4}-\d\d-\d\d \d', text) else text


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _http(url):
    url = base._clean(url)
    return url if re.match(r'^https?://', url) else ''


def _audio_url(part):
    for key in ('audioUrl', 'exAudioUrl'):
        if _http(part.get(key)):
            return _http(part.get(key))
    for asset in part.get('assets') or []:
        if isinstance(asset, dict) and asset.get('assetType') == 'audio' and _http(asset.get('url')):
            return _http(asset.get('url'))
    return ''


def _channel(*objs):
    for o in objs:
        if isinstance(o, dict) and isinstance(o.get('channel'), str) and o['channel'].strip():
            return o['channel'].strip().lower()
    return ''


# ---------- 拆成一个个 Part ----------

def _units(obj):
    """返回 (kind, meta, [(part, attempt, details, annotations, unit_title)])。"""
    data = obj.get('data') if isinstance(obj.get('data'), dict) else obj
    children = data.get('children')
    if isinstance(children, list) and children and isinstance(data.get('parts'), list):
        by_part = {}
        for child in children:
            if not isinstance(child, dict):
                continue
            attempt = base._as_dict(child.get('attempt'))
            pid = child.get('partId') or next(
                (p.get('id') for p in attempt.get('parts') or [] if isinstance(p, dict)), None)
            if pid is not None:
                by_part[str(pid)] = child
        units = []
        for part in data['parts']:
            if not isinstance(part, dict):
                continue
            child = by_part.get(str(part.get('id')), {})
            attempt = dict(base._as_dict(child.get('attempt')))
            if not attempt.get('id') and child.get('resultId'):
                attempt['id'] = child['resultId']
            details = [d for d in attempt.get('details') or [] if isinstance(d, dict)]
            annotations = base._as_dict(child.get('annotationSnapshot')).get('annotations') or []
            units.append((part, attempt, details, [a for a in annotations if isinstance(a, dict)], ''))
        meta = {'submitted_at': _iso(data.get('submittedAt')), 'elapsed_seconds': None}
        return 'composition', meta, units, data

    parts, attempt, details, annotations = base._locate(obj)
    unit = base._as_dict(data.get('unit'))
    unit_title = base._clean(unit.get('title')) if len(parts) == 1 else ''
    attempt = attempt or {}
    meta = {
        'submitted_at': _iso(attempt.get('submittedAt') or attempt.get('createdAt')),
        'elapsed_seconds': _int(attempt.get('elapsedSeconds')),
    }
    return 'single', meta, [(p, attempt, details, annotations, unit_title) for p in parts], data


# ---------- 字幕 ----------

def _segments(part):
    """articleJson 里带时间的句子 → [{id, start, end, text}]；没有时间的返回 []（只能重新转录）。"""
    art = base._article_json(part)
    if not art:
        return []
    words = {}
    for seg in art.get('segments') or []:
        for w in (seg or {}).get('words') or []:
            if isinstance(w, dict) and base._clean(w.get('text')) and w.get('sentence_index') is not None:
                words.setdefault(w['sentence_index'], w)   # 每句第一个词
    out = []
    for seg in art.get('segments') or []:
        for s in (seg or {}).get('sentences') or []:
            if not isinstance(s, dict):
                continue
            text = base._clean(s.get('text'))
            idx = _int(s.get('sentence_index'))
            try:
                start, end = float(s.get('start_time')), float(s.get('end_time'))
            except (TypeError, ValueError):
                return []
            if not text or idx is None:
                continue
            first = words.get(idx)
            try:
                w_start, w_end = float(first['start_time']), float(first['end_time'])
                if w_end - w_start > LONG_WORD_SECONDS and abs(w_start - start) < 0.05:
                    start = max(start, w_end - 0.5)
            except (TypeError, ValueError, KeyError):
                pass
            out.append({'id': idx, 'start': round(start, 2), 'end': round(max(end, start), 2), 'text': text})
    out.sort(key=lambda s: (s['start'], s['id']))
    return out


# ---------- 题目 ----------

def _strip_zh(items):
    return [{k: v for k, v in o.items() if k != 'zh'} for o in items]


def _groups(part, details):
    """题目按原卷顺序；作答（你的答案、对错）拆出来另存，题目本身每次导入都一样。"""
    raw = sorted([g for g in part.get('groups') or [] if isinstance(g, dict)],
                 key=lambda g: g.get('displayOrder') or 0)
    parsed = base._groups(part, details)
    groups, answers = [], {}
    for rg, g in zip(raw, parsed):
        kind = g['kind']
        if 'match' in (rg.get('type') or '').lower():
            kind = 'match'
        questions = []
        for q in g['questions']:
            answers[q['num']] = {'user': q['user_answer'], 'state': q['state']}
            questions.append({
                'num': q['num'],
                'text': q['text'],
                'options': _strip_zh(q['options']),
                'answer': q['answer'],
                'evidence': q['evidence'],
                'analysis': q['analysis'],
            })
        groups.append({
            'id': str(rg.get('id') or ''),
            'range': g['range'],
            'kind': kind,
            'instruction_html': g['instruction_html'],
            'content_html': g['content_html'],
            'image': g['image'],
            'title': g['title'],
            'options': _strip_zh(g['options']),
            'questions': questions,
        })
    return raw, groups, answers


def _title(part, raw_groups, unit_title):
    for value in (unit_title, part.get('title'), part.get('subtitle')):
        if base._clean(value):
            return base._clean(value)
    for g in raw_groups:   # 组卷的 Part 没有题目名，填空题组常带一个
        for key in ('title', 'title1'):
            if base._plain(g.get(key)):
                return base._plain(g.get(key))
    return ''


# ---------- 做题时划的线 ----------

def _nearest(haystack, needle, around):
    """needle 在 haystack 里离 around 最近的位置（Python 下标），没有返回 -1。"""
    best = -1
    for m in re.finditer(re.escape(needle), haystack):
        if best < 0 or abs(m.start() - around) < abs(best - around):
            best = m.start()
    return best


def _locate_in(basis, start, text):
    """九分学长给的 UTF-16 起点在 basis 里对不上（复制时空白被收过）就找附近同一个词。返回 Python 下标或 -1。"""
    i = base._u16_to_index(basis, start)
    if basis[i:i + len(text)] == text:
        return i
    return _nearest(basis, text, i)


def _pieces(raw_group, group):
    """没有 contentHtml 的题组（选择题）：九分学长把每题题干、各选项的文字首尾相接当成一整段算下标。"""
    out = []
    by_num = {q['num']: q for q in group['questions']}
    for q in sorted([q for q in raw_group.get('questions') or [] if isinstance(q, dict)],
                    key=lambda q: q.get('displayOrder') or 0):
        num = base._clean(q.get('qNumber') or '')
        mine = by_num.get(num)
        if not mine:
            continue
        out.append((num, None, text_content(q.get('question')), mine['text']))
        opts = {o['key']: o['text'] for o in mine['options']}
        for o in sorted([o for o in q.get('options') or [] if isinstance(o, dict)],
                        key=lambda o: o.get('displayOrder') or 0):
            key = base._clean(o.get('optionNum') or o.get('key') or '')
            raw = text_content(o.get('option') or o.get('optionContent') or o.get('content') or '')
            out.append((num, key, raw, opts.get(key, base._clean(raw))))
    return out


def _piece_mark(pieces, gi, start, text):
    """把整段下标换成某一题题干 / 某个选项里的下标（按页面上显示的、收过空白的文字算）。"""
    basis = ''.join(p[2] for p in pieces)
    at = _locate_in(basis, start, text)
    order = []
    pos = 0
    for k, (_, _, raw, _) in enumerate(pieces):
        if at >= 0 and pos <= at < pos + len(raw):
            order.insert(0, (k, at - pos))
        else:
            order.append((k, 0))
        pos += len(raw)
    for k, local in order:
        num, key, raw, shown = pieces[k]
        found = _nearest(shown, text, local)
        if found >= 0:
            s = base._u16(shown[:found])
            return {'g': gi, 'q': num, 'o': key, 'start': s, 'end': s + base._u16(text), 'text': text}
    return None


def _marks(part, raw_groups, groups, annotations):
    part_id = str(part.get('id') or '')
    index = {str(rg.get('id')): k for k, rg in enumerate(raw_groups)}
    marks = []
    for a in annotations:
        if a.get('area') != 'question' or (part_id and a.get('partId') and str(a.get('partId')) != part_id):
            continue
        r = base._as_dict(a.get('range'))
        text = r.get('text') or ''
        start = _int(r.get('start'))
        gid = str(r.get('rootScope') or '').rsplit(':', 1)[-1]
        gi = index.get(gid)
        if gi is None or start is None or not text.strip():
            continue
        rg, g = raw_groups[gi], groups[gi]
        mark = None
        if rg.get('contentHtml'):
            basis = text_content(rg['contentHtml'])
            at = _locate_in(basis, start, text)
            if at >= 0:
                s = base._u16(basis[:at])
                mark = {'g': gi, 'start': s, 'end': s + base._u16(text), 'text': text}
        if mark is None:
            mark = _piece_mark(_pieces(rg, g), gi, start, text)
        if mark:
            marks.append(mark)
    marks.sort(key=lambda m: (m['g'], m.get('q') or '', m.get('o') or '', m['start']))
    return marks


# ---------- 入口 ----------

def _load(raw):
    """和 jiufen_import.load_payload 一样宽容（前后多了说明文字也行），只是读不出来时把原因说得更具体。"""
    if isinstance(raw, dict):
        return raw
    text = str(raw or '').strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise JiufenFormatError('没找到 JSON：要粘贴九分学长交卷后接口返回的整段内容（以 { 开头）')
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        where = f'第 {e.lineno} 行第 {e.colno} 列附近格式不对'
        # 里层的 articleJson 本身也是一段 JSON 字符串，引号前要有反斜杠；从网页上复制有时会把反斜杠弄丢
        if re.search(r'"articleJson"\s*:\s*"\{(?:\s|\\[rnt])*"', text):
            raise JiufenFormatError(f'{where}，像是复制时把引号前面的反斜杠弄丢了。请从九分学长重新复制一遍，或者存成 .json 文件再选')
        raise JiufenFormatError(f'{where}（{e.msg}），可能没复制完整。请重新复制一遍，或者存成 .json 文件再选')
    if not isinstance(obj, dict):
        raise JiufenFormatError('JSON 最外层应该是一个对象 {...}')
    return obj


def parse(raw):
    """解析整份 JSON，返回 {kind, submitted_at, elapsed_seconds, parts: [...]}，一个 Part 一份。"""
    obj = _load(raw)
    kind, meta, units, data = _units(obj)
    if _channel(data, base._as_dict(data.get('attempt'))) == 'reading':
        raise JiufenFormatError('这是阅读题的 JSON：请到「文章精读 → 添加文章」里导入')
    if not units:
        raise JiufenFormatError('JSON 里没找到听力题（parts / articleJson）。请确认复制的是听力交卷后的接口返回')
    parts = []
    for k, (part, attempt, details, annotations, unit_title) in enumerate(
            sorted(units, key=lambda u: u[0].get('sortNo') or 0)):
        raw_groups, groups, answers = _groups(part, details)
        segments = _segments(part)
        qs = [q for g in groups for q in g['questions']]
        states = [answers[q['num']]['state'] for q in qs]
        correct = sum(1 for s in states if s == 'right')
        if not any(states) and isinstance(attempt.get('correctCount'), int):
            correct = attempt['correctCount']
        parts.append({
            'part_id': str(part.get('id') or ''),
            'label': base._clean(part.get('partNum') or part.get('label') or '') or f'Part {k + 1}',
            'title': _title(part, raw_groups, unit_title),
            'audio_url': _audio_url(part),
            'segments': segments,
            'duration': segments[-1]['end'] if segments else None,
            'groups': groups,
            'attempt': {
                'id': str(attempt.get('id') or ''),
                'submitted_at': _iso(attempt.get('submittedAt') or attempt.get('createdAt')) or meta['submitted_at'],
                'elapsed_seconds': _int(attempt.get('elapsedSeconds')) if kind == 'single' else None,
                'correct': correct,
                'total': len(qs) or (attempt.get('totalCount') if isinstance(attempt.get('totalCount'), int) else 0),
                'answers': answers,
                'marks': _marks(part, raw_groups, groups, annotations),
            },
        })
    if not any(p['segments'] or p['audio_url'] for p in parts):
        raise JiufenFormatError('JSON 里既没有音频链接，也没有逐句字幕，导入不了')
    return {'kind': kind, **meta, 'parts': parts}


def summarize(part):
    """预解析时给用户看的一行。"""
    qs = [(q['num'], part['attempt']['answers'].get(q['num'], {}).get('state')) for g in part['groups'] for q in g['questions']]
    return {
        'part_id': part['part_id'],
        'label': part['label'],
        'title': part['title'],
        'has_audio': bool(part['audio_url']),
        'has_timing': bool(part['segments']),
        'sentences': len(part['segments']),
        'duration': part['duration'],
        'questions': len(qs),
        'correct': part['attempt']['correct'],
        'total': part['attempt']['total'],
        'wrong': [n for n, s in qs if s == 'wrong'],
        'blank': [n for n, s in qs if s == 'blank'],
        'marks': len(part['attempt']['marks']),
        'attempt_id': part['attempt']['id'],
        'submitted_at': part['attempt']['submitted_at'],
    }

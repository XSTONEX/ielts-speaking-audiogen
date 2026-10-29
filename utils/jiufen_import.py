"""九分学长阅读作答 JSON → 精读文章（原文 + 题目 + 作答）。

接口返回的形状会变，所以这里尽量宽容：
- 外层可以是整份 {code, data}、只有 data、只有 attempt，或者单个 part；
- articleJson 可以是字符串，也可以已经是对象；
- 题目和作答新结构合在 groups[].questions[] 里，老结构作答在 details[]，两边都认；
- 粘贴时前后多了引号、说明文字也没关系，取第一个 { 到最后一个 } 之间的内容。
字段缺了就给空值，只有连原文都拿不到时才报错。

文章正文仍然存成 content_text（一行一句：英文一行、译文一行），高亮、朗读这些按原文下标
工作的功能不用改；题目、段落、每句在 content_text 里的位置另存在 exam 里给页面用。
页面上的下标是 JS 的 UTF-16 下标，所以这里算位置一律按 UTF-16 计。
"""

import html
import json
import re
from html.parser import HTMLParser


class JiufenFormatError(ValueError):
    """粘贴的内容不是能用的九分学长 JSON；消息直接给用户看。"""


JUDGE_WORDS = {'TRUE', 'FALSE', 'NOT GIVEN', 'YES', 'NO'}


def _u16(text):
    return len(text.encode('utf-16-le')) // 2


def _clean(text):
    """一句话里不能有换行（content_text 按行切句），多余空白收成一个空格。"""
    return re.sub(r'\s+', ' ', str(text or '')).strip()


def load_payload(raw):
    if isinstance(raw, dict):
        return raw
    text = str(raw or '').strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise JiufenFormatError('没找到 JSON：请把九分学长接口返回的整段内容（以 { 开头）粘贴进来')
    try:
        obj = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        raise JiufenFormatError(f'JSON 格式不对（第 {e.lineno} 行第 {e.colno} 列附近）：{e.msg}。可能没复制完整')
    if not isinstance(obj, dict):
        raise JiufenFormatError('JSON 最外层应该是一个对象 {...}')
    return obj


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _locate(obj):
    """返回 (parts, attempt, details, annotations)。"""
    data = obj.get('data') if isinstance(obj.get('data'), dict) else obj
    attempt = data.get('attempt') if isinstance(data.get('attempt'), dict) else None
    if attempt is None and isinstance(data.get('parts'), list) and ('details' in data or 'accuracy' in data):
        attempt = data
    parts = (attempt or {}).get('parts') or data.get('parts') or []
    if not parts and ('articleJson' in data or 'groups' in data):
        parts = [data]
    parts = [p for p in parts if isinstance(p, dict)]
    details = (attempt or {}).get('details') or data.get('details') or []
    annotations = _as_dict(data.get('annotationSnapshot')).get('annotations') or []
    return parts, attempt, [d for d in details if isinstance(d, dict)], [a for a in annotations if isinstance(a, dict)]


def _article_json(part):
    art = part.get('articleJson')
    if isinstance(art, str) and art.strip():
        try:
            art = json.loads(art)
        except json.JSONDecodeError:
            art = None
    if isinstance(art, dict) and art.get('segments'):
        return art
    # 没有 articleJson 时退回纯文本 article：空行分段，句末标点切句
    text = part.get('article')
    if isinstance(text, str) and text.strip():
        text = re.sub(r'<[^>]+>', '\n', text)
        segments, idx = [], 0
        for block in re.split(r'\n\s*\n|\n', html.unescape(text)):
            sents = [s for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"“‘(])', _clean(block)) if s]
            if sents:
                segments.append({'sentences': [{'sentence_index': idx + k, 'text': s} for k, s in enumerate(sents)]})
                idx += len(sents)
        return {'title': part.get('title'), 'segments': segments}
    return None


LABEL_RE = re.compile(r'^([A-Z])(?:[.:)]\s*|\s+)(?=\S)')


def _paragraph_labels(first_sentences):
    """每段第一句开头是 A、B、C… 连续的字母，才认作段落编号（单看一句的 "A study…" 不算）。"""
    if len(first_sentences) < 2:
        return None
    labels = []
    for k, text in enumerate(first_sentences):
        m = LABEL_RE.match(text)
        if not m or m.group(1) != chr(ord('A') + k):
            return None
        labels.append((m.group(1), m.end()))
    return labels


# ---------- 题目 HTML：白名单清洗，<input placeholder="8"> 换成编号空格 ----------

_KEEP = {'p', 'br', 'strong', 'b', 'em', 'i', 'u', 'ul', 'ol', 'li', 'table', 'thead', 'tbody',
         'tr', 'td', 'th', 'span', 'div', 'sup', 'sub', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
_VOID = {'br'}
_BLOCK = {'p', 'li', 'tr', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'ul', 'ol'}


class _Html(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []          # 清洗后的 HTML
        self.blocks = [[]]     # 纯文本，按块切开；空格写成 \x00N\x00
        self.stack = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'input':
            num = _clean(a.get('placeholder') or a.get('data-q') or '')
            self.out.append(f'<span class="ir-blank" data-q="{html.escape(num)}">{html.escape(num)}</span>')
            self.blocks[-1].append(f'\x00{num}\x00')
            return
        if tag in ('td', 'th') and self.blocks[-1]:
            self.blocks[-1].append(' | ')
        if tag in _BLOCK or tag == 'br':
            self.blocks.append([])
        if tag not in _KEEP:
            return
        keep = ''.join(f' {k}="{html.escape(v)}"' for k, v in attrs if k in ('colspan', 'rowspan') and v and v.isdigit())
        self.out.append(f'<{tag}{keep}>')
        if tag not in _VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in _BLOCK:
            self.blocks.append([])
        if tag in _KEEP and tag not in _VOID and tag in self.stack:
            while self.stack:
                t = self.stack.pop()
                self.out.append(f'</{t}>')
                if t == tag:
                    break

    def handle_data(self, data):
        self.out.append(html.escape(data))
        self.blocks[-1].append(data)

    def result(self):
        while self.stack:
            self.out.append(f'</{self.stack.pop()}>')
        blocks = [_clean(''.join(b)) for b in self.blocks]
        return ''.join(self.out).strip(), [b for b in blocks if b]


def sanitize_html(raw):
    """返回 (安全 HTML, 纯文本块列表)。"""
    if not raw:
        return '', []
    p = _Html()
    p.feed(str(raw))
    p.close()
    return p.result()


def _plain(raw):
    return _clean(' '.join(sanitize_html(raw)[1]).replace('\x00', ''))


def _stem_from_blocks(blocks, num):
    """填空题没有单独题干时，从题目版式里取出这个空所在的那一行，空格画成 ____，别的空写成 (N)。"""
    mark = f'\x00{num}\x00'
    for block in blocks:
        if mark not in block:
            continue
        text = block.replace(mark, '____')
        text = re.sub(r'\x00([^\x00]*)\x00', r'(\1)', text)
        text = _clean(text.strip(' |'))
        if len(text) > 220:   # 一整段摘要里有好几个空：只留这个空所在的那句
            for piece in re.split(r'(?<=[.!?;])\s+', text):
                if '____' in piece:
                    text = piece
                    break
        return text
    return ''


def _evidence(value):
    """sentenceIndex: "4-7" / "4" / "4,6" → [起, 止]。"""
    nums = [int(n) for n in re.findall(r'\d+', str(value or ''))]
    if not nums:
        return None
    return [min(nums), max(nums)]


def _analysis(items):
    explain, trap, extra = [], [], []
    for a in sorted([a for a in items or [] if isinstance(a, dict)], key=lambda a: a.get('displayOrder') or 0):
        text = _clean(a.get('content'))
        if not text:
            continue
        one, two = (a.get('labelsOne') or '').strip(), (a.get('labelsTwo') or '').strip()
        if one == '句子':
            continue   # 证据句本身，页面上直接在原文里定位
        if one == '解析':
            explain.append(text)
        elif two == '干扰' or one == '干扰':
            trap.append(text)
        else:
            extra.append({'label': one or two, 'text': text})
    return {'explain': '\n'.join(explain), 'trap': '\n'.join(trap), 'extra': extra}


def _kind(group, options, has_blank):
    gtype = (group.get('type') or '').lower()
    subtype = (group.get('questionSubtype') or '').lower()
    texts = {o['text'].upper() for o in options}
    if subtype.startswith('judg') or (options and texts <= JUDGE_WORDS):
        return 'judge'
    if options:
        return 'choice'
    if 'fill' in gtype or 'blank' in gtype or has_blank:
        return 'blank'
    if group.get('options'):
        return 'match'
    return 'other'


def _options(items):
    out = []
    for o in sorted([o for o in items or [] if isinstance(o, dict)], key=lambda o: o.get('displayOrder') or 0):
        key = _clean(o.get('optionNum') or o.get('key') or '')
        text = _plain(o.get('option') or o.get('optionContent') or o.get('content') or '')
        if key or text:
            out.append({'key': key, 'text': text, 'zh': ''})
    return out


def _state(raw):
    """1 对、2 错、0 没作答；没有作答记录时为空。"""
    return {'1': 'right', '2': 'wrong', '0': 'blank'}.get(str(raw).strip() if raw is not None else '', '')


def _groups(part, details):
    by_id = {str(d.get('questionId')): d for d in details if d.get('questionId') is not None}
    by_num = {str(d.get('qNumber')): d for d in details if d.get('qNumber') is not None}
    groups = []
    raw_groups = [g for g in part.get('groups') or [] if isinstance(g, dict)]
    for g in sorted(raw_groups, key=lambda g: g.get('displayOrder') or 0):
        instruction, _ = sanitize_html(g.get('description') or g.get('typeDescription') or '')
        content_html, blocks = sanitize_html(g.get('contentHtml') or '')
        image = g.get('imageUrl') or g.get('image')
        image = image if isinstance(image, str) and re.match(r'^https?://', image) else ''
        questions = []
        raw_qs = [q for q in g.get('questions') or [] if isinstance(q, dict)]
        for q in sorted(raw_qs, key=lambda q: (q.get('displayOrder') or 0)):
            num = _clean(q.get('qNumber') or '')
            d = by_id.get(str(q.get('id'))) or by_num.get(num) or {}
            user = q.get('userAnswer') if q.get('userAnswer') is not None else d.get('userAnswer')
            right = q.get('rightAnswer') if q.get('rightAnswer') not in (None, '') else d.get('rightAnswer')
            options = _options(q.get('options'))
            text = _plain(q.get('question') or '') or _stem_from_blocks(blocks, num)
            questions.append({
                'num': num,
                'text': text,
                'zh': '',
                'options': options,
                'answer': _clean(right or ''),
                'user_answer': _clean(user or ''),
                'state': _state(q.get('state') if q.get('state') is not None else d.get('state')),
                'evidence': _evidence(q.get('sentenceIndex')),
                'analysis': _analysis(q.get('analyses')),
            })
        has_blank = 'ir-blank' in content_html
        kind = _kind(g, questions[0]['options'] if questions else [], has_blank)
        groups.append({
            'range': _clean(g.get('qRange') or ''),
            'kind': kind,
            'type': _clean(g.get('type') or ''),
            'subtype': _clean(g.get('questionSubtype') or ''),
            'instruction_html': instruction,
            'content_html': content_html,
            'image': image,
            'options': _options(g.get('options')),
            'title': _plain(g.get('title') or ''),
            'questions': questions,
        })
    return groups


def _marks(part, title, raw_sentences, prefix, annotations):
    """九分学长做题时在原文上划的线。下标按 "标题 + 每句之间一个分隔符" 计（实测 28/28 对得上）；
    对不上的再在那句里按原词找一次，还找不到就丢掉。"""
    part_id = str(part.get('id') or '')
    starts, pos = [], _u16(title)
    for _, text in raw_sentences:
        starts.append(pos)
        pos += _u16(text) + 1
    marks = []
    for a in annotations:
        if a.get('area') != 'text' or (part_id and a.get('partId') and str(a.get('partId')) != part_id):
            continue
        r = _as_dict(a.get('range'))
        word = r.get('text') or ''
        try:
            start = int(r.get('start'))
        except (TypeError, ValueError):
            continue
        if not word.strip():
            continue
        k = next((k for k in range(len(starts) - 1, -1, -1) if starts[k] <= start), None)
        if k is None:
            continue
        idx, text = raw_sentences[k]
        local = _u16_to_index(text, start - starts[k])
        if text[local:local + len(word)] != word:
            local = text.find(word)
            if local < 0:
                continue
        local -= prefix.get(idx, 0)
        if local < 0:
            continue
        clean_text = _clean(text[prefix.get(idx, 0):])
        # _clean 只会收空白；词本身不含换行时，去掉前缀后的位置不变
        if clean_text[local:local + len(word)] != word:
            found = clean_text.find(word)
            if found < 0:
                continue
            local = found
        prefix_u16 = _u16(clean_text[:local])
        marks.append({'s': idx, 'start': prefix_u16, 'end': prefix_u16 + _u16(word), 'text': word})
    marks.sort(key=lambda m: (m['s'], m['start']))
    return marks


def _u16_to_index(text, units):
    """UTF-16 下标 → Python 下标（没有生僻字时两者相同）。"""
    if units <= 0:
        return 0
    count = 0
    for i, ch in enumerate(text):
        if count >= units:
            return i
        count += 2 if ord(ch) > 0xFFFF else 1
    return len(text)


def _attempt_summary(attempt, groups):
    qs = [q for g in groups for q in g['questions']]
    if not attempt and not any(q['user_answer'] or q['state'] for q in qs):
        return None
    attempt = attempt or {}
    right = sum(1 for q in qs if q['state'] == 'right')
    try:
        elapsed = int(attempt.get('elapsedSeconds') or 0)
    except (TypeError, ValueError):
        elapsed = 0
    return {
        'correct': attempt.get('correctCount') if isinstance(attempt.get('correctCount'), int) else right,
        'total': attempt.get('totalCount') if isinstance(attempt.get('totalCount'), int) else len(qs),
        'elapsed_seconds': elapsed,
        'submitted_at': _clean(attempt.get('submittedAt') or attempt.get('createdAt') or ''),
    }


def parse(raw):
    """解析整份 JSON，返回 part 列表（一篇文章一个）。"""
    obj = load_payload(raw)
    parts, attempt, details, annotations = _locate(obj)
    if not parts:
        raise JiufenFormatError('JSON 里没找到文章（parts / articleJson）。请确认复制的是阅读题的接口返回')
    result = []
    for part in sorted(parts, key=lambda p: p.get('sortNo') or 0):
        art = _article_json(part)
        if not art:
            continue
        title = _clean(part.get('title') or art.get('title') or '')
        raw_paragraphs = []
        for seg in art.get('segments') or []:
            sents = []
            for s in (seg or {}).get('sentences') or []:
                if isinstance(s, dict) and _clean(s.get('text')):
                    sents.append((int(s.get('sentence_index') if s.get('sentence_index') is not None else -1), str(s.get('text'))))
            if sents:
                raw_paragraphs.append(sents)
        if not raw_paragraphs:
            continue
        # 句号缺失时按出现顺序补
        n = 0
        for para in raw_paragraphs:
            for k, (idx, text) in enumerate(para):
                para[k] = (idx if idx >= 0 else n, text)
                n += 1
        labels = _paragraph_labels([_clean(p[0][1]) for p in raw_paragraphs])
        prefix = {}
        paragraphs = []
        for k, para in enumerate(raw_paragraphs):
            label = None
            if labels:
                label = labels[k][0]
                lead = LABEL_RE.match(para[0][1].lstrip())
                prefix[para[0][0]] = (len(para[0][1]) - len(para[0][1].lstrip())) + (lead.end() if lead else 0)
            paragraphs.append({
                'label': label,
                'sentences': [{'i': idx, 'en': _clean(text[prefix.get(idx, 0):]), 'zh': ''} for idx, text in para],
            })
        groups = _groups(part, details)
        raw_sentences = [s for para in raw_paragraphs for s in para]
        result.append({
            'title': title,
            'part': _clean(part.get('partNum') or part.get('label') or ''),
            'description': _plain(part.get('partDescription') or part.get('description') or ''),
            'paragraphs': paragraphs,
            'groups': groups,
            'attempt': _attempt_summary(attempt if len(parts) == 1 else None, groups),
            'marks': _marks(part, title, raw_sentences, prefix, annotations),
        })
    if not result:
        raise JiufenFormatError('找到了 parts，但里面没有原文句子（articleJson.segments 为空）')
    return result


def summarize(part):
    """导入前给用户看的一行概要。"""
    sentences = sum(len(p['sentences']) for p in part['paragraphs'])
    groups = [{'range': g['range'], 'kind': g['kind'], 'count': len(g['questions'])} for g in part['groups']]
    return {
        'title': part['title'],
        'part': part['part'],
        'paragraphs': len(part['paragraphs']),
        'labelled': any(p['label'] for p in part['paragraphs']),
        'sentences': sentences,
        'questions': sum(g['count'] for g in groups),
        'groups': groups,
        'attempt': part['attempt'],
        'marks': len(part['marks']),
    }


def build_article_text(part):
    """把原文（和已有的译文）排成 content_text，同时把每行的位置记回 part。

    排法：段落编号单独一行（"A"），然后每句英文一行、它的译文紧跟一行，段与段之间空一行。
    位置按 UTF-16 计，和页面上的下标一致。"""
    lines, pos = [], 0

    def add(line):
        nonlocal pos
        lines.append(line)
        at = pos
        pos += _u16(line) + 1
        return at

    for k, para in enumerate(part['paragraphs']):
        if k:
            add('')
        para['o'] = add(para['label']) if para['label'] else None
        for s in para['sentences']:
            s['o'] = add(s['en'])
            s['zo'] = add(s['zh']) if s.get('zh') else None
    return '\n'.join(lines)


def translation_items(part):
    """要翻译的条目：每句原文、每道题的题干、选择题里有实际内容的选项。"""
    items = [{'id': f"s{s['i']}", 'en': s['en']} for p in part['paragraphs'] for s in p['sentences']]
    for gi, g in enumerate(part['groups']):
        for q in g['questions']:
            if q['text']:
                items.append({'id': f"q{gi}.{q['num']}", 'en': q['text']})
            if g['kind'] == 'choice':
                for o in q['options']:
                    if o['text'] and o['text'].upper() not in JUDGE_WORDS:
                        items.append({'id': f"o{gi}.{q['num']}.{o['key']}", 'en': o['text']})
        for o in g['options']:
            if o['text']:
                items.append({'id': f"g{gi}.{o['key']}", 'en': o['text']})
    return items


def apply_translations(part, zh):
    """zh: {条目 id: 译文}。缺的条目留空，不影响原文。"""
    for p in part['paragraphs']:
        for s in p['sentences']:
            s['zh'] = _clean(zh.get(f"s{s['i']}", ''))
    for gi, g in enumerate(part['groups']):
        for q in g['questions']:
            q['zh'] = _clean(zh.get(f"q{gi}.{q['num']}", ''))
            for o in q['options']:
                o['zh'] = _clean(zh.get(f"o{gi}.{q['num']}.{o['key']}", ''))
        for o in g['options']:
            o['zh'] = _clean(zh.get(f"g{gi}.{o['key']}", ''))

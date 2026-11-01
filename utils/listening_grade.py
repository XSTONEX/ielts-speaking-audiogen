"""精听「重做」交卷判分，以及题组类型的统一整理（地图题、多选题）。

判分照雅思官方的说法（IDP / British Council 的备考说明，剑桥真题答案的写法）：
- 大小写不管，首尾和多打的空格不管
- 拼写要完全对，单复数要和答案一样；超字数的答案和答案对不上，自然算错
- 数字写阿拉伯数字或英文单词都算对（320 = three hundred and twenty）
- 英式、美式拼写都算对（colour / color，centre / center）
- 答案里 | 隔开的几种写法任一都对；括号里的词可写可不写：(the) museum
- 多选题（Choose TWO letters）不分先后：每个题号一分，选中几个对的就对几题
官方没说连字符和空格能不能混用（mobile-phone / mobile phone），按拼写不同算错。
"""

import html
import itertools
import re
import unicodedata

NUMBER_WORDS = {
    'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
    'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19, 'twenty': 20, 'thirty': 30,
    'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90,
}
SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000}
COUNT_WORDS = {'two': 2, 'three': 3, 'four': 4, 'five': 5}

# 美式 → 英式；两边都换成英式再比，所以写哪种都对
US_UK_WORDS = {
    'center': 'centre', 'centers': 'centres', 'theater': 'theatre', 'theaters': 'theatres',
    'meter': 'metre', 'meters': 'metres', 'kilometer': 'kilometre', 'kilometers': 'kilometres',
    'centimeter': 'centimetre', 'centimeters': 'centimetres', 'millimeter': 'millimetre',
    'millimeters': 'millimetres', 'liter': 'litre', 'liters': 'litres', 'fiber': 'fibre', 'fibers': 'fibres',
    'caliber': 'calibre', 'somber': 'sombre', 'specter': 'spectre', 'luster': 'lustre', 'saber': 'sabre',
    'meager': 'meagre', 'catalog': 'catalogue', 'catalogs': 'catalogues', 'dialog': 'dialogue',
    'dialogs': 'dialogues', 'analog': 'analogue', 'program': 'programme', 'programs': 'programmes',
    'gray': 'grey', 'tire': 'tyre', 'tires': 'tyres', 'jewelry': 'jewellery', 'aluminum': 'aluminium',
    'mold': 'mould', 'moldy': 'mouldy', 'plow': 'plough', 'pajamas': 'pyjamas', 'cozy': 'cosy',
    'mustache': 'moustache', 'aging': 'ageing', 'judgment': 'judgement', 'artifact': 'artefact',
    'artifacts': 'artefacts', 'maneuver': 'manoeuvre', 'pediatric': 'paediatric',
    'archeology': 'archaeology', 'encyclopedia': 'encyclopaedia', 'airplane': 'aeroplane',
    'airplanes': 'aeroplanes', 'defense': 'defence', 'offense': 'offence', 'license': 'licence',
    'licenses': 'licences', 'pretense': 'pretence', 'practise': 'practice', 'practised': 'practiced',
    'practising': 'practicing', 'traveled': 'travelled', 'traveling': 'travelling', 'traveler': 'traveller',
    'travelers': 'travellers', 'canceled': 'cancelled', 'canceling': 'cancelling', 'labeled': 'labelled',
    'labeling': 'labelling', 'modeled': 'modelled', 'modeling': 'modelling', 'fueled': 'fuelled',
    'counselor': 'counsellor', 'counselors': 'counsellors', 'enrollment': 'enrolment', 'enroll': 'enrol',
    'fulfill': 'fulfil', 'skillful': 'skilful', 'installment': 'instalment', 'woolen': 'woollen',
    'marvelous': 'marvellous',
}
# 这些词开头的美式写法：color → colour，colorful → colourful，neighborhood → neighbourhood
US_UK_STEMS = (
    ('color', 'colour'), ('favor', 'favour'), ('flavor', 'flavour'), ('honor', 'honour'),
    ('humor', 'humour'), ('labor', 'labour'), ('neighbor', 'neighbour'), ('behavior', 'behaviour'),
    ('harbor', 'harbour'), ('rumor', 'rumour'), ('vapor', 'vapour'), ('odor', 'odour'),
    ('savor', 'savour'), ('endeavor', 'endeavour'), ('armor', 'armour'), ('parlor', 'parlour'),
    ('vigor', 'vigour'), ('tumor', 'tumour'), ('valor', 'valour'), ('savior', 'saviour'),
)
IZE_KEEP = {'size', 'sizes', 'sized', 'prize', 'prizes', 'seize', 'seized', 'seizes', 'seizing', 'capsize'}
IZE = re.compile(r'(?<=[a-z]{2})iz(e|es|ed|ing|ation|ations|er|ers)$')
YZE = re.compile(r'(?<=[a-z])yz(e|es|ed|ing)$')


# ---------- 填空题 ----------

def _uk(word):
    if word in US_UK_WORDS:
        return US_UK_WORDS[word]
    for us, uk in US_UK_STEMS:
        if word.startswith(us) and not word.startswith(uk):
            return uk + word[len(us):]
    if word not in IZE_KEEP:
        word = IZE.sub(r'is\1', word)
        word = YZE.sub(r'ys\1', word)
    return word


def _number_run(words):
    total, current = 0, 0
    for w in words:
        if w in NUMBER_WORDS:
            current += NUMBER_WORDS[w]
        elif w == 'hundred':
            current = (current or 1) * 100
        else:
            total += (current or 1) * SCALES[w]
            current = 0
    return str(total + current)


def _cat(w):
    if w == 'and':
        return 'and'
    if w in SCALES:
        return 'hundred' if w == 'hundred' else 'big'
    n = NUMBER_WORDS.get(w)
    if n is None:
        return None
    return 'zero' if n == 0 else 'unit' if n < 10 else 'teen' if n < 20 else 'tens'


# 哪种数字词后面能接哪种：twenty one、three hundred and twenty、five thousand；one two 不算一个数
FOLLOW = {
    None: {'zero', 'unit', 'teen', 'tens', 'hundred', 'big'},
    'unit': {'hundred', 'big'},
    'teen': {'hundred', 'big'},
    'tens': {'unit', 'big'},
    'hundred': {'and', 'unit', 'teen', 'tens', 'big'},
    'big': {'and', 'unit', 'teen', 'tens'},
    'and': {'unit', 'teen', 'tens'},
    'zero': set(),
}


def _numbers(tokens):
    """英文数字换成阿拉伯数字：three hundred and twenty → 320，twenty-one → 21。"""
    out, run = [], []

    def flush():
        tail = []
        while run and run[-1] == 'and':
            tail.append(run.pop())
        if run:
            out.append(_number_run([w for w in run if w != 'and']))
        out.extend(tail)
        run.clear()

    for tok in tokens:
        parts = tok.split('-')
        if not all(_cat(p) not in (None, 'and') for p in parts):
            if tok == 'and' and run and 'and' in FOLLOW[_cat(run[-1])]:
                run.append(tok)
                continue
            flush()
            out.append(tok)
            continue
        for p in parts:
            if run and _cat(p) not in FOLLOW[_cat(run[-1])]:
                flush()
            run.append(p)
    flush()
    return out


def canon(text):
    """比较用的写法：小写、空格收好、末尾标点去掉、数字统一成阿拉伯数字、拼写统一成英式。"""
    s = unicodedata.normalize('NFKC', str(text or '')).lower()
    s = s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'[.,;:!?]+$', '', s).strip()
    s = re.sub(r'(?<=\d),(?=\d{3}\b)', '', s)   # 30,000 = 30000
    return ' '.join(_uk(t) for t in _numbers(s.split(' ') if s else []))


def _variants(alt):
    """(the) museum → the museum / museum；括号最多认 4 处，再多的照原样留着。"""
    parts = re.split(r'(\([^()]*\))', alt)
    opts = [i for i, p in enumerate(parts) if p.startswith('(') and p.endswith(')')][:4]
    out = set()
    for keep in itertools.product((True, False), repeat=len(opts)):
        chosen = dict(zip(opts, keep))
        text = ''.join((p[1:-1] if chosen[i] else '') if i in chosen else p for i, p in enumerate(parts))
        out.add(re.sub(r'\s+', ' ', text).strip())
    return out


def text_matches(user, answer):
    u = canon(user)
    if not u:
        return False
    for alt in str(answer or '').split('|'):
        if alt.strip() and any(canon(v) == u for v in _variants(alt.strip())):
            return True
    return False


# ---------- 选字母的题 ----------

def keys_of(value, options):
    """'B' / 'b, d' / 'BD' / 选项原文 → {'B', 'D'}（和页面上的 keysOf 一样）。"""
    s = str(value or '').strip().upper()
    if not s:
        return set()
    keys = [str(o.get('key') or '').upper() for o in options or []]
    tokens = [t for t in re.split(r'[\s,，、/&|]+', s) if t]
    if keys and all(t in keys for t in tokens):
        return set(tokens)
    if keys and re.fullmatch(r'[A-Z]+', s) and all(c in keys for c in s):
        return set(s)
    hit = next((o for o in options or [] if str(o.get('text') or '').strip().upper() == s), None)
    if hit:
        return {str(hit.get('key') or '').upper()}
    return set()


def letter_matches(user, answer, options):
    u = str(user or '').strip().upper()
    if not u:
        return False
    for alt in str(answer or '').split('|'):
        a = alt.strip().upper()
        if a and (a == u or (options and keys_of(a, options) == keys_of(u, options) != set())):
            return True
    return False


# ---------- 题组整理 ----------

def _plain(raw):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', str(raw or '')))).strip()


def _pick_count(group):
    text = _plain(group.get('instruction_html'))
    m = re.search(r'\bchoose\s+(two|three|four|five)\s+(letters|answers|options|correct)', text, re.I)
    if not m:
        m = re.search(r'\bwhich\s+(two|three|four|five)\b', text, re.I)
    if m and 'from the box' not in text.lower():
        return COUNT_WORDS[m.group(1).lower()]
    return 0


def normalize_groups(groups):
    """导入时存下的题组再整理一遍（旧数据也适用）：
    - 选项只有字母、没有文字的（地图 / 平面图标注）→ kind 'map'，一题一行
    - 「Choose TWO letters」这种几个题号共用一份选项的 → kind 'multi'，units 是一组组题号
    - 填空题其实是从选项框里选字母的 → kind 'match'
    原数据不动，返回新的列表。"""
    out = []
    for raw in groups or []:
        if not isinstance(raw, dict):
            continue
        g = dict(raw)
        qs = [q for q in g.get('questions') or [] if isinstance(q, dict)]
        kind = g.get('kind') or 'other'
        gtype = str(g.get('type') or '').lower()
        with_opts = bool(qs) and all(q.get('options') for q in qs)
        if kind in ('choice', 'map') and with_opts and all(
                not str(o.get('text') or '').strip() for q in qs for o in q['options']):
            kind = 'map'
        elif 'map' in gtype and kind in ('choice', 'other'):
            kind = 'map'
        pick = _pick_count(g)
        if kind in ('choice', 'multi') and with_opts and (pick > 1 or 'multi' in gtype):
            if pick < 2:
                pick = max(2, max(len(keys_of(q.get('answer'), q['options'])) for q in qs)) if len(qs) == 1 else len(qs)
            kind = 'multi'
            if len(qs) == 1:
                g['units'] = [[qs[0]['num']]]
            else:
                g['units'] = [[q['num'] for q in qs[i:i + pick]] for i in range(0, len(qs), pick)]
            g['pick'] = pick
        if kind == 'blank' and g.get('options') and qs:
            keys = {str(o.get('key') or '').upper() for o in g['options']}
            if all(a.strip().upper() in keys for q in qs for a in str(q.get('answer') or '').split('|') if a.strip()):
                kind = 'match'
        g['kind'] = kind
        out.append(g)
    return out


# ---------- 交卷 ----------

def _bank(group):
    if group.get('options'):
        return group['options']
    qs = group.get('questions') or []
    return qs[0].get('options') or [] if qs else []


def grade(groups, submitted):
    """submitted: {题号: 填的内容}；多选题一组题号的选择写在其中任一个题号上（'B,D'）。
    返回 {'answers': {题号: {'user', 'state'}}, 'correct', 'total'}。"""
    submitted = {str(k): str(v or '')[:200] for k, v in (submitted or {}).items()}
    answers = {}
    for g in normalize_groups(groups):
        qs = [q for q in g.get('questions') or [] if isinstance(q, dict)]
        by_num = {q['num']: q for q in qs}
        kind = g['kind']
        if kind == 'multi':
            for nums in g['units']:
                unit = [by_num[n] for n in nums if n in by_num]
                if len(unit) == 1 and len(keys_of(unit[0].get('answer'), unit[0]['options'])) > 1:
                    q = unit[0]
                    mine = keys_of(submitted.get(q['num']), q['options'])
                    right = keys_of(q.get('answer'), q['options'])
                    state = 'blank' if not mine else 'right' if mine == right else 'wrong'
                    answers[q['num']] = {'user': ','.join(sorted(mine)), 'state': state}
                    continue
                raw = next((submitted[n] for n in nums if submitted.get(n, '').strip()), '')
                picked = []
                for k in re.split(r'[\s,，、/&|]+', raw.upper()):
                    if k and k not in picked and any(str(o.get('key') or '').upper() == k for o in unit[0]['options']):
                        picked.append(k)
                picked = picked[:len(unit)]   # 一组几个题号就选几个字母
                left = list(picked)
                got = {}
                for q in unit:   # 不分先后：先把选对的字母分给它所在的那题
                    right = keys_of(q.get('answer'), q['options'])
                    hit = next((k for k in left if k in right), None)
                    if hit:
                        got[q['num']] = (hit, 'right')
                        left.remove(hit)
                for q in unit:
                    if q['num'] not in got:
                        got[q['num']] = (left.pop(0), 'wrong') if left else ('', 'blank')
                for n, (user, state) in got.items():
                    answers[n] = {'user': user, 'state': state}
            continue
        for q in qs:
            user = submitted.get(q['num'], '').strip()
            if not user:
                answers[q['num']] = {'user': '', 'state': 'blank'}
                continue
            if kind in ('choice', 'judge'):
                mine, right = keys_of(user, q.get('options')), keys_of(q.get('answer'), q.get('options'))
                ok = bool(mine) and mine == right
                user = ','.join(sorted(mine)) or user
            elif kind in ('match', 'map'):
                ok = letter_matches(user, q.get('answer'), q.get('options') or _bank(g))
                user = user.upper()
            else:
                ok = text_matches(user, q.get('answer'))
            answers[q['num']] = {'user': user, 'state': 'right' if ok else 'wrong'}
    total = len(answers)
    return {'answers': answers, 'correct': sum(1 for a in answers.values() if a['state'] == 'right'), 'total': total}

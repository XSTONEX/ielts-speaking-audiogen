#!/usr/bin/env python3
"""从飞书知识库导入「九分学长 写作大+小模板」，生成 writing_correction/resource/写作模板.json。

数据源是飞书 wiki 索引页，脚本按索引页的表格自动发现全部子文档，因此飞书那边新增
条目后重跑本脚本即可，不需要改代码。

用法:
    python script/import_writing_templates.py              # 用本地缓存（缺失才联网）
    python script/import_writing_templates.py --refresh    # 强制重新拉取飞书
    python script/import_writing_templates.py --report     # 只打印解析报告，不写文件
"""

import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib import request as urlrequest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX_URL = 'https://my.feishu.cn/wiki/DZuQwwvEsiAP6dkxeDsc9gjZn9d'
CACHE_DIR = os.path.join(ROOT, 'writing_correction', 'resource', '模板原文')
OUT_FILE = os.path.join(ROOT, 'writing_correction', 'resource', '写作模板.json')
TRANS_CACHE = os.path.join(CACHE_DIR, '_译文缓存.json')
TRANS_API = 'https://api.deerapi.com/v1/chat/completions'
TRANS_MODEL = 'gpt-4o-mini'

WIKI_RE = re.compile(r'https://[\w.-]+/wiki/([A-Za-z0-9]+)')
SLOT_RE = re.compile(r'\[([^\[\]]{1,200})\]')
# 范文里填入槽位的内容被加粗：[**xxx**]
SAMPLE_SLOT_RE = re.compile(r'\[\s*(?:\*\*)?(.+?)(?:\*\*)?\s*\]', re.S)

# 大作文题型 → 稳定 id（供前端路由与存档使用，名称变动不影响历史记录）
BIG_TYPE_IDS = {
    '观点型': 'opinion', '好坏型': 'positive_negative', '比较型': 'compare',
    '讨论型': 'discuss', '报告型': 'report', '混搭型': 'mixed', '特殊型': 'special',
}
SMALL_CHART_IDS = {'数据图': 'data', '流程图': 'process', '地图': 'map'}
SMALL_SECTION_IDS = {'改写段': 'rewrite', '概述段': 'overview', '概括段': 'overview', '细节段': 'detail'}

warnings = []
# 飞书接口频控：串行化实际请求，配合退避重试
_FETCH_GATE = threading.Semaphore(2)


def warn(msg):
    warnings.append(msg)


# ---------------------------------------------------------------- 抓取

def fetch_doc(token, force=False):
    """拉取飞书文档 markdown，带磁盘缓存。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f'{token}.md')
    if not force and os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, encoding='utf-8') as f:
            return f.read()
    env = dict(os.environ, LARKSUITE_CLI_NO_UPDATE_NOTIFIER='1', LARKSUITE_CLI_NO_SKILLS_NOTIFIER='1')
    last_err = ''
    content = None
    # 飞书开放接口有频控，失败按指数退避重试
    for attempt in range(5):
        with _FETCH_GATE:
            proc = subprocess.run(
                ['lark-cli', 'docs', '+fetch', '--doc', f'https://my.feishu.cn/wiki/{token}',
                 '--doc-format', 'markdown'],
                capture_output=True, text=True, env=env, timeout=120,
            )
        if proc.returncode == 0:
            content = json.loads(proc.stdout)['data']['document']['content']
            break
        last_err = proc.stderr[:400]
        if 'rate_limit' not in last_err and '99991400' not in last_err:
            break
        time.sleep(2 * (attempt + 1))
    if content is None:
        raise RuntimeError(f'fetch {token} failed: {last_err}')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    return content


# ---------------------------------------------------------------- 文本归一化

def clean_line(s):
    """去掉飞书导出残留的反引号 / 加粗标记，统一全角方括号。"""
    s = s.replace('`', '').replace('［', '[').replace('］', ']')
    s = re.sub(r'\*\*(.*?)\*\*', r'\1', s)
    s = s.replace('**', '')
    s = s.strip()
    # 飞书原文里有槽位漏了右括号（如 "..., except [数据/类别"），补齐后才能正常解析
    if s.count('[') == s.count(']') + 1 and not s.endswith(']'):
        s += ']'
    # 也有多打一个右括号的（报告型第二种 "effect(s)] behind"），去掉孤立的那个
    if s.count(']') == s.count('[') + 1:
        s = s.replace(']', '', 1) if '[' not in s else re.sub(r'\](?![^\[]*\[)', '', s, count=1)
    return s


def strip_title(md):
    return re.sub(r'^<title>.*?</title>\s*', '', md, flags=re.S)


def source_url(md):
    m = re.search(r'^>\s*来源[：:]\s*(\S+)', md, flags=re.M)
    return m.group(1) if m else ''


def is_meta_line(s):
    # 飞书导出的分割线有 -- / --- 两种写法，都不是正文
    return ((not s) or s.startswith('>') or s.startswith('<') or s.startswith('|')
            or re.fullmatch(r'[-—–*_\s]{2,}', s) is not None)


def is_prose_line(text):
    """判断是不是中文说明行：只看 [槽位] 外面的内容有没有中文。

    `[数据A1] [趋势模块], [数值模块].` 括号外只剩标点，是句型；
    `以下所有句型均可配合[数值模块]来给出具体的数值。` 括号外是中文，是说明。
    """
    outside = SLOT_RE.sub('', text)
    cjk = len(re.findall(r'[\u4e00-\u9fff]', outside))
    if not cjk:
        return False
    # 中文释义里可能夹着英文专名（River Stoke位于…），按中文字数与英文词数的比例判定
    words = len(re.findall(r'[A-Za-z]{2,}', outside))
    return cjk >= max(2, words)


def is_note_line(s):
    return bool(re.match(r'^(注意|注|说明|备注)[：:]', s))


def has_cjk(s):
    return bool(re.search(r'[一-鿿]', s))


# ---------------------------------------------------------------- 槽位

def build_slot(key, index):
    """把 [xxx] 解析成槽位描述：选择型 / 带示例的填空 / 普通填空。"""
    key = key.strip()
    slot = {'index': index, 'key': key, 'label': key, 'type': 'text', 'hint': ''}
    m = re.match(r'^e\.g\.\s*(.+)$', key, flags=re.I)
    if m:
        slot['label'] = '内容'
        slot['hint'] = m.group(1).strip()
        return slot
    if '/' in key and not has_cjk(key):
        parts = [p.strip() for p in key.split('/') if p.strip()]
        if len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts):
            slot['type'] = 'choice'
            slot['options'] = parts
    return slot


LEADIN_RE = re.compile(r'^([A-Za-z][A-Za-z .]*[,:])\s*(.+)$')


def hoist_leadin(text):
    """把 [For example, 主体 + 场景…] 拆成 For example, [主体 + 场景…]。

    模板里这类整句槽位自带英文引导词，拆出来后既能和范文逐句对齐，
    练习时也不会让学生对着一个大空格发呆。
    """
    def repl(m):
        inner = m.group(1)
        lm = LEADIN_RE.match(inner)
        if lm and has_cjk(lm.group(2)) and not has_cjk(lm.group(1)):
            return f'{lm.group(1)} [{lm.group(2).strip()}]'
        return m.group(0)
    return SLOT_RE.sub(repl, text)


PAREN_ALT_RE = re.compile(r'\(([^()\[\]]*?/[^()\[\]]*?)\)')


def hoist_paren_alt(text):
    """把「(is reasonable/convincing)」这类括号二选一转成槽位。

    模板作者用括号表示「挑一个写」，不转成槽位的话会原样拼进作文变成病句。
    括号里含中文或含其它槽位的不动。
    """
    def repl(m):
        inner = m.group(1).strip()
        if not inner or has_cjk(inner) or not re.search(r'[A-Za-z]', inner):
            return m.group(0)
        return f'[{inner}]'
    return PAREN_ALT_RE.sub(repl, text)


def split_slots(text):
    """返回 (原文, 槽位列表)。原文保留 [xxx] 写法，前端按槽位下标渲染输入框。"""
    text = hoist_paren_alt(hoist_leadin(text))
    slots = [build_slot(m.group(1), i) for i, m in enumerate(SLOT_RE.finditer(text))]
    return text, slots


def strip_brackets(text):
    """去掉范文里标注填空用的方括号，留下可直接阅读的英文。"""
    return re.sub(r'\s+', ' ', re.sub(r'\[([^\[\]]*)\]', r'\1', text or '')).strip()


def alpha_only(text, sample=False):
    """抹掉槽位后的纯字母骨架，用于范文与模板对齐。

    范文里填入槽位的内容可以很长，必须用不限长度的正则剥离，
    否则整段正文会留在骨架里，相似度算不准。
    """
    rx = SAMPLE_SLOT_RE if sample else SLOT_RE
    stripped = rx.sub(' ', text).lower()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z ]', '', stripped)).strip()


def split_sentences(paragraph):
    """按句号切分，但保护 [...] 内部的标点不被切开。"""
    holder, spans = [], []

    def stash(m):
        spans.append(m.group(0))
        return f'\x01{len(spans) - 1}\x01'

    masked = SAMPLE_SLOT_RE.sub(stash, paragraph)
    parts = re.split(r'(?<=[.!?])\s+', masked)
    for part in parts:
        text = re.sub(r'\x01(\d+)\x01', lambda m: spans[int(m.group(1))], part).strip()
        if text:
            holder.append(text)
    return holder


# ---------------------------------------------------------------- 索引页

def parse_index(md):
    """解析索引页，得到 {'big': [...], 'small': {...}, 'samples': [...]} 的文档清单。"""
    reg = {'big': [], 'small': {}, 'samples': [], 'small_videos': {}}
    h1 = h2 = h3 = ''
    for raw in md.split('\n'):
        s = raw.strip()
        if s.startswith('# ') and not s.startswith('## '):
            h1, h2, h3 = s[2:].strip(), '', ''
            continue
        if s.startswith('## ') and not s.startswith('### '):
            h2, h3 = s[3:].strip(), ''
            continue
        if s.startswith('### ') and not s.startswith('#### '):
            h3 = s[4:].strip()
            continue
        if not s.startswith('|'):
            continue
        cells = [c.strip() for c in s.strip('|').split('|')]
        if len(cells) < 3 or cells[0] in ('标题', '-', ':-'):
            continue
        m = WIKI_RE.search(cells[2])
        if not m:
            continue
        item = {'title': clean_line(cells[0]), 'kind': clean_line(cells[1]), 'token': m.group(1)}
        if h1 == '模板' and h2 == '大作文模板':
            reg['big'].append(item)
        elif h1 == '模板' and h2 == '小作文模板':
            chart = h3.replace('小作文', '').strip()
            reg['small'].setdefault(chart, []).append(item)
        elif h1.startswith('范文') and '大作文' in h1:
            reg['samples'].append(item)
        else:
            warn(f'索引页出现未归类条目：{h1}/{h2}/{h3} → {item["title"]}')
    return reg


# ---------------------------------------------------------------- 通用标题树解析

def parse_heading_tree(md, min_level=2):
    """把 markdown 解析成 [(标题路径, [正文行])]，供小作文句型库与参考资料使用。"""
    body = strip_title(md)
    groups = []
    path = []
    cur = None
    for raw in body.split('\n'):
        s = raw.rstrip()
        hm = re.match(r'^(#{1,6})\s+(.*)$', s.strip())
        if hm:
            level, title = len(hm.group(1)), clean_line(hm.group(2))
            if level < min_level:
                path = []
                cur = None
                continue
            m_sent = re.match(r'^(?:句子\d+|第[一二三四五六七八九十]+句)[：:]\s*(.*)$', title)
            if m_sent and cur is not None:
                # 「句子1：中文释义」只是父句型下的一条例句，不单独成组
                if m_sent.group(1).strip():
                    cur['lines'].append(m_sent.group(1).strip())
                continue
            path = path[:level - min_level]
            path.append(title)
            cur = {'path': list(path), 'lines': []}
            groups.append(cur)
            continue
        t = clean_line(s)
        if is_meta_line(t) or cur is None:
            continue
        cur['lines'].append(t)
    return groups


def lines_to_patterns(lines):
    """把一组正文行转成句型列表；中文行作为其后英文行的释义。

    返回 (句型, 说明, 原文顺序的条目)。第三个返回值保留说明与句型在文档里的
    先后顺序，前端按它渲染，避免所有说明被挤到句型前面。
    """
    patterns, notes, items = [], [], []
    pending_cn = ''
    for line in lines:
        if not line:
            continue
        if is_note_line(line) or re.match(r'^(以下|如果|上述|这个|说明)', line):
            if pending_cn:
                notes.append(pending_cn)
                items.append({'type': 'note', 'text': pending_cn})
                pending_cn = ''
            notes.append(line)
            items.append({'type': 'note', 'text': line})
            continue
        m = re.match(r'^(第[一二三四五六七八九十]+句|英文翻译|中文)[：:]\s*(.*)$', line)
        label = ''
        if m:
            label, line = m.group(1), m.group(2).strip()
            if label in ('英文翻译', '中文'):
                label = ''
            if not line:
                continue
        if is_prose_line(line):
            if pending_cn:
                notes.append(pending_cn)
                items.append({'type': 'note', 'text': pending_cn})
            pending_cn = line
            continue
        text, slots = split_slots(line)
        pat = {'text': text, 'chinese': pending_cn, 'label': label, 'slots': slots}
        patterns.append(pat)
        items.append({'type': 'pattern', 'index': len(patterns) - 1})
        pending_cn = ''
    if pending_cn:
        notes.append(pending_cn)
        items.append({'type': 'note', 'text': pending_cn})
    return patterns, notes, items


# ---------------------------------------------------------------- 大作文模板

def parse_big_template(md, title):
    """解析单个大作文题型模板文档 → {feature, variants:[{name, sections:[...]}]}。"""
    body = strip_title(md)
    feature = ''
    variants = []
    cur_variant = None
    cur_section = None

    def ensure_variant(name=''):
        nonlocal cur_variant
        if cur_variant is None or (name and cur_variant['name'] != name):
            cur_variant = {'name': name, 'sections': []}
            variants.append(cur_variant)
        return cur_variant

    for raw in body.split('\n'):
        s = clean_line(raw)
        hm = re.match(r'^(#{1,6})\s+(.*)$', s)
        if hm:
            level, htitle = len(hm.group(1)), clean_line(hm.group(2))
            if level == 1:
                if htitle == title or htitle.endswith('模板') and not htitle.startswith('第'):
                    continue
                ensure_variant(htitle)
                cur_section = None
                continue
            if level == 2:
                m = re.search(r'第.类[：:]\s*(.+)', htitle)
                if m:
                    continue
                ensure_variant(htitle)
                cur_section = None
                continue
            if level >= 3:
                ensure_variant()
                cur_section = {'name': htitle, 'note': '', 'sentences': []}
                cur_variant['sections'].append(cur_section)
                continue
        if cur_section is None and cur_variant is not None and SLOT_RE.search(clean_line(raw)):
            # 变体标题之后、第一个小节标题之前直接写的句子，归入隐式「开头」段
            cur_section = {'name': '开头', 'note': '', 'sentences': []}
            cur_variant['sections'].insert(0, cur_section)
        if is_meta_line(s):
            continue
        m = re.match(r'^题目特征[：:]\s*(.+)$', s)
        if m:
            feature = m.group(1).strip()
            continue
        if cur_section is None:
            continue
        if is_note_line(s) or is_prose_line(s):
            cur_section['note'] = (cur_section['note'] + ' ' + s).strip()
            continue
        for piece in split_sentences(hoist_leadin(s)):
            text, slots = split_slots(piece)
            cur_section['sentences'].append({'text': text, 'slots': slots})

    variants = [v for v in variants if v['sections']]
    for vi, v in enumerate(variants):
        v['index'] = vi
        v['sections'] = [sec for sec in v['sections'] if sec['sentences']]
        for i, sec in enumerate(v['sections']):
            # 报告型有两套结构，段落 id 带上变体序号才不会重号
            sec['id'] = f'v{vi + 1}s{i + 1}'
            sec['variant_index'] = vi
            sec['slot_count'] = sum(len(x['slots']) for x in sec['sentences'])
    return {'feature': feature, 'variants': [v for v in variants if v['sections']]}


FEATURE_RE = re.compile(r'^\d+\s*[.、]\s*(观点|好坏|比较|讨论|报告|混搭)\s*[：:]\s*(.+)$')


def parse_feature_map(md):
    """从「总结构」里抽出六种题型的题目问法，补齐各题型模板缺失的题目特征。"""
    out = {}
    for raw in strip_title(md).split('\n'):
        m = FEATURE_RE.match(clean_line(raw))
        if m:
            out[f'{m.group(1)}型'] = m.group(2).strip()
    return out


# ---------------------------------------------------------------- 大作文范文

def parse_samples(md):
    """解析范文文档 → [{question, versions:[{name, paragraphs:[str]}]}]。"""
    body = strip_title(md)
    samples, cur_q, cur_v, buf = [], None, None, []

    def flush():
        nonlocal buf
        text = ' '.join(x for x in buf if x).strip()
        buf = []
        if text and cur_v is not None:
            cur_v['paragraphs'].append(text)

    for raw in body.split('\n'):
        s = clean_line(raw)
        hm = re.match(r'^(#{1,6})\s+(.*)$', s)
        if hm:
            flush()
            level, htitle = len(hm.group(1)), clean_line(hm.group(2))
            if level <= 2:
                continue
            if re.match(r'^版本', htitle):
                cur_v = {'name': htitle, 'paragraphs': []}
                if cur_q:
                    cur_q['versions'].append(cur_v)
                continue
            cur_q = {'question': htitle, 'versions': []}
            cur_v = None
            samples.append(cur_q)
            continue
        if is_meta_line(s):
            flush()
            continue
        buf.append(s)
    flush()
    return [q for q in samples if q['versions']]


def extract_values(paragraph):
    """从范文段落中抽出所有填入槽位的内容。"""
    return [m.group(1).strip() for m in SAMPLE_SLOT_RE.finditer(paragraph)]


def _section_skeleton(sec):
    return alpha_only(' '.join(x['text'] for x in sec['sentences']))


def _best_section(paragraph, sections):
    ptext = alpha_only(paragraph, sample=True)
    best, best_score = None, 0.0
    for sec in sections:
        stext = _section_skeleton(sec)
        if not stext:
            continue
        score = difflib.SequenceMatcher(None, ptext, stext).ratio()
        if score > best_score:
            best, best_score = sec, score
    return best, best_score


def pick_variant(paragraphs, candidates):
    """范文可能用的不是本题型的模板（飞书里存在放错分区的题），
    因此在全部题型的全部变体里挑最贴近的一套。"""
    best, best_score = None, -1.0
    for cand in candidates:
        score = sum(_best_section(p, cand['variant']['sections'])[1] for p in paragraphs)
        if score > best_score:
            best, best_score = cand, score
    return best


SENT_MATCH_MIN = 0.34


def align_sentences(tpl_sentences, sample_sentences):
    """逐句对齐模板与范文：范文换了别的回扣句时，槽位不会顺位错配。"""
    n, m = len(tpl_sentences), len(sample_sentences)
    sim = [[difflib.SequenceMatcher(
        None, alpha_only(t['text']), alpha_only(sent, sample=True)).ratio()
        for sent in sample_sentences] for t in tpl_sentences]
    NEG = float('-inf')
    dp = [[NEG] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == NEG:
                continue
            base = dp[i][j]
            if i < n and j < m:
                gain = sim[i][j] if sim[i][j] >= SENT_MATCH_MIN else -0.5
                if base + gain > dp[i + 1][j + 1]:
                    dp[i + 1][j + 1], bt[i + 1][j + 1] = base + gain, ('M', i, j)
            if i < n and base - 0.25 > dp[i + 1][j]:
                dp[i + 1][j], bt[i + 1][j] = base - 0.25, ('T', i, j)
            if j < m and base - 0.25 > dp[i][j + 1]:
                dp[i][j + 1], bt[i][j + 1] = base - 0.25, ('S', i, j)
    steps, i, j = [], n, m
    while (i, j) != (0, 0):
        move = bt[i][j]
        if move is None:
            break
        kind, pi, pj = move
        steps.append((kind, pi, pj))
        i, j = pi, pj
    return list(reversed(steps))


WORD_RE = re.compile(r"[a-z']+")


def _tokenize(text, rx):
    """把文本拆成 (固定词序列, 每个槽位/填入内容之前的词数, 内容列表)。"""
    words, marks, contents = [], [], []
    pos = 0
    for m in rx.finditer(text):
        words.extend(WORD_RE.findall(text[pos:m.start()].lower()))
        marks.append(len(words))
        contents.append(m.group(1).strip())
        pos = m.end()
    words.extend(WORD_RE.findall(text[pos:].lower()))
    return words, marks, contents


def _position_mapper(tpl_words, sample_words):
    """基于固定词的最长公共块，建立「模板词位 → 范文词位」的映射。"""
    blocks = [b for b in difflib.SequenceMatcher(None, tpl_words, sample_words)
              .get_matching_blocks() if b.size]

    def to_sample(p):
        if not blocks:
            return p
        best, best_dist = None, None
        for b in blocks:
            if b.a <= p <= b.a + b.size:
                return b.b + (p - b.a)
            dist = b.a - p if p < b.a else p - (b.a + b.size)
            if best_dist is None or dist < best_dist:
                best, best_dist = b, dist
        return best.b - (best.a - p) if p < best.a else best.b + best.size + (p - best.a - best.size)

    return to_sample


SKIP_COST = 7.0
MAX_MATCH_COST = 14.0


CHOICE_PENALTY = 2.0


def pair_by_anchor(tpl_text, sample_text, tpl_slots=None):
    """返回 [(槽位下标, 填入内容下标)]：按固定词锚点单调配对，允许两边各有空缺。

    相邻两个槽位之间没有固定词时（如 "...that [话题中的观点] [is reasonable/convincing]."），
    锚点位置完全相同、代价打平。范文一般会把选择型槽位直接写成定稿措辞，
    所以给选择型槽位加一点偏置，让填入内容优先落到实义槽位上。
    """
    tw, tmarks, _ = _tokenize(tpl_text, SLOT_RE)
    sw, smarks, svals = _tokenize(sample_text, SAMPLE_SLOT_RE)
    if not tmarks or not smarks:
        return [], svals
    to_sample = _position_mapper(tw, sw)
    want = [to_sample(p) for p in tmarks]
    n, m = len(want), len(smarks)
    INF = float('inf')
    dp = [[INF] * (m + 1) for _ in range(n + 1)]
    bt = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0
    for i in range(n + 1):
        for j in range(m + 1):
            if dp[i][j] == INF:
                continue
            base = dp[i][j]
            if i < n and j < m:
                bias = CHOICE_PENALTY if (tpl_slots and i < len(tpl_slots)
                                          and tpl_slots[i].get('type') == 'choice') else 0.0
                cost = base + min(abs(want[i] - smarks[j]), MAX_MATCH_COST) + bias
                if cost < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1], bt[i + 1][j + 1] = cost, ('M', i, j)
            if i < n and base + SKIP_COST < dp[i + 1][j]:
                dp[i + 1][j], bt[i + 1][j] = base + SKIP_COST, ('T', i, j)
            if j < m and base + SKIP_COST < dp[i][j + 1]:
                dp[i][j + 1], bt[i][j + 1] = base + SKIP_COST, ('S', i, j)
    out, i, j = [], n, m
    while (i, j) != (0, 0):
        move = bt[i][j]
        if move is None:
            break
        kind, pi, pj = move
        if kind == 'M':
            out.append((pi, pj))
        i, j = pi, pj
    return list(reversed(out)), svals


def align_sample(paragraph, sections):
    """把范文段落匹配到模板段落，并逐句配对槽位与填入内容。"""
    values = extract_values(paragraph)
    best, best_score = _best_section(paragraph, sections)
    if best is None or best_score < 0.4:
        return {'section_id': '', 'section_name': '', 'score': round(best_score, 3),
                'values': values, 'pairs': [], 'sentences': [], 'match': 'none',
                'slot_count': 0, 'filled_count': 0}

    tpl_sentences = best['sentences']
    tpl_text = ' '.join(x['text'] for x in tpl_sentences)
    slot_keys, slot_owner = [], []
    for si_, sent in enumerate(tpl_sentences):
        for slot in sent['slots']:
            slot_keys.append(slot['key'])
            slot_owner.append(si_)
    tpl_slots = [s for sent in tpl_sentences for s in sent['slots']]
    mapping, sample_values = pair_by_anchor(tpl_text, paragraph, tpl_slots)
    slot_value = {si_: sample_values[vi] for si_, vi in mapping}
    used = {vi for _, vi in mapping}

    pairs = [{'key': slot_keys[si_], 'value': slot_value[si_]}
             for si_ in range(len(slot_keys)) if si_ in slot_value]
    sample_sentences = split_sentences(paragraph)
    steps = align_sentences(tpl_sentences, sample_sentences)
    rows = []
    for kind, ti, sj in steps:
        if kind == 'S':
            rows.append({'tpl_index': None, 'tpl_text': '', 'sample_text': sample_sentences[sj],
                         'pairs': []})
            continue
        tpl = tpl_sentences[ti]
        row_pairs = [{'key': slot_keys[k], 'value': slot_value[k]}
                     for k in range(len(slot_keys))
                     if slot_owner[k] == ti and k in slot_value]
        rows.append({'tpl_index': ti, 'tpl_text': tpl['text'],
                     'sample_text': sample_sentences[sj] if kind == 'M' else '',
                     'pairs': row_pairs})
    filled = len(pairs)
    extra = [v for i, v in enumerate(sample_values) if i not in used]
    if filled == len(slot_keys) and not extra:
        match = 'exact'
    elif filled == len(slot_keys):
        match = 'extra'
    else:
        match = 'partial'
    return {'section_id': best['id'], 'section_name': best['name'], 'score': round(best_score, 3),
            'values': values, 'pairs': pairs, 'sentences': rows, 'match': match,
            'extra_values': extra, 'slot_count': len(slot_keys), 'filled_count': filled}


# ---------------------------------------------------------------- 特殊型：由范文反推骨架

def infer_slot_key(sentence, slot_text, para_idx, sent_idx, slot_idx, total_paras):
    rest = sentence.replace(f'[{slot_text}]', '').strip(' .,:;')
    if len(rest) <= 3:
        return '前推+后推'
    low = sentence.lower()
    if low.startswith('for example') or low.startswith('a case in point'):
        return '举例'
    if para_idx == 0:
        return '改写话题' if slot_idx == 0 else '本文探讨的内容'
    if para_idx == total_paras - 1:
        return '总结要点'
    if re.search(r'\b(this is|this directly|this further|this highlights)\b', low):
        return '回扣内容'
    if sent_idx == 0:
        return '破题关键词'
    return '关键内容'


def derive_template_from_sample(sample):
    """特殊型在飞书里没有模板，用范文版本1反推一份骨架，并标记 derived。"""
    version = sample['versions'][0]
    paras = version['paragraphs']
    names = ['开头', 'Body 1', 'Body 2', 'Body 3 让步', '结尾']
    sections = []
    for pi, para in enumerate(paras):
        sentences = []
        para_slot_idx = 0
        for si, sent in enumerate(split_sentences(para)):
            sent = sent.strip()
            if not sent:
                continue

            def repl(m, _sent=sent, _si=si):
                nonlocal para_slot_idx
                key = infer_slot_key(_sent, m.group(1), pi, _si, para_slot_idx, len(paras))
                para_slot_idx += 1
                return f'[{key}]'

            out = SAMPLE_SLOT_RE.sub(repl, sent)
            text, slots = split_slots(out)
            sentences.append({'text': text, 'slots': slots})
        sections.append({
            'id': f'v1s{pi + 1}',
            'variant_index': 0,
            'name': names[pi] if pi < len(names) else f'段落 {pi + 1}',
            'note': '', 'sentences': sentences,
            'slot_count': sum(len(x['slots']) for x in sentences),
        })
    return {'feature': '题目问法不落入六大常规题型时使用', 'derived': True,
            'variants': [{'name': '', 'index': 0, 'sections': sections}]}


def _build_groups(md):
    """把一篇参考资料按标题拆成分组，保留说明与句型的原文顺序。"""
    out = []
    for g in parse_heading_tree(md, 1):
        if not g['lines']:
            continue
        pats, notes, items = lines_to_patterns(g['lines'])
        if not pats and not notes:
            continue
        out.append({'label': ' · '.join(g['path']), 'patterns': pats,
                    'notes': notes, 'items': items})
    return out


# ---------------------------------------------------------------- 范文中译

TRANS_SYSTEM = """你是雅思写作教学助理。用户会给你一篇 7.5 分范文的逐句英文。
请把每一句翻译成自然、准确的中文，供学生"看中文写英文"的回译练习使用。

要求：
1. 忠实表达原句的全部信息，不要漏译、不要扩写。
2. 用书面中文，句式贴合原句结构，让学生能据此还原出接近原句的英文。
3. 专有名词、数字照译。
4. 只返回一个 JSON 数组，元素按输入顺序一一对应，形如 ["译文1","译文2"]。
   不要带 markdown 代码块标记，不要有任何其他文字。"""


def _read_env(key):
    """从项目根目录的 .env 里读取一个键，避免脚本依赖 python-dotenv。"""
    if os.getenv(key):
        return os.getenv(key)
    path = os.path.join(ROOT, '.env')
    if not os.path.exists(path):
        return ''
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith(f'{key}='):
                return line.split('=', 1)[1].strip().strip('"\'')
    return ''


_OPENER = None


def _opener():
    """本机直连 DeerAPI 即可；仅当 .env 配了 PROXY_URL 时才走代理。"""
    global _OPENER
    if _OPENER is None:
        proxy = _read_env('TEMPLATE_IMPORT_PROXY')
        handlers = [urlrequest.ProxyHandler({'http': proxy, 'https': proxy})] if proxy else []
        _OPENER = urlrequest.build_opener(*handlers)
    return _OPENER


def _load_trans_cache():
    if os.path.exists(TRANS_CACHE):
        with open(TRANS_CACHE, encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_trans_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(TRANS_CACHE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def _sent_key(text):
    return hashlib.sha1(text.strip().encode('utf-8')).hexdigest()[:16]


def _translate_batch(sentences, api_key):
    """一次翻译一批句子，返回等长的中文列表；失败返回空列表。"""
    numbered = '\n'.join(f'{i + 1}. {t}' for i, t in enumerate(sentences))
    body = json.dumps({
        'model': TRANS_MODEL, 'temperature': 0.2,
        'messages': [{'role': 'system', 'content': TRANS_SYSTEM},
                     {'role': 'user', 'content': numbered}],
    }).encode('utf-8')
    # DeerAPI 会拒绝 urllib 的默认 User-Agent，必须显式带一个
    req = urlrequest.Request(TRANS_API, data=body, headers={
        'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (ielts-audiogen template importer)'})
    try:
        with _opener().open(req, timeout=120) as resp:
            content = json.loads(resp.read())['choices'][0]['message']['content'].strip()
    except Exception as exc:
        warn(f'翻译请求失败：{exc}')
        return []
    content = re.sub(r'^```(?:json)?\s*|\s*```$', '', content).strip()
    start, end = content.find('['), content.rfind(']')
    if start != -1 and end > start:
        content = content[start:end + 1]
    try:
        out = json.loads(content)
    except json.JSONDecodeError:
        warn('翻译返回的不是合法 JSON 数组')
        return []
    if not isinstance(out, list) or len(out) != len(sentences):
        warn(f'翻译条数对不上：要 {len(sentences)} 条，返回 {len(out) if isinstance(out, list) else "?"} 条')
        return []
    return [str(x).strip() for x in out]


def translate_samples(big_types, enabled=True):
    """给范文的每一句补中文，供实战的回译练习使用；按句缓存，重跑不重复付费。"""
    cache = _load_trans_cache()
    rows = []          # (段落行对象, 英文原句)
    for t in big_types:
        for q in t.get('samples', []):
            for v in q.get('versions', []):
                for para in v.get('paragraphs', []):
                    for row in para.get('sentences', []):
                        text = strip_brackets(row.get('sample_text', ''))
                        if text:
                            rows.append((row, text))

    todo = sorted({text for _, text in rows if _sent_key(text) not in cache})
    if todo and enabled:
        api_key = _read_env('DEER_API_KEY')
        if not api_key:
            warn('未配置 DEER_API_KEY，范文中译跳过（实战页会缺少中文提示）')
        else:
            print(f'范文中译：{len(todo)} 句待翻译，分 {(len(todo) + 11) // 12} 批…')
            batches = [todo[i:i + 12] for i in range(0, len(todo), 12)]

            def run(batch):
                return batch, _translate_batch(batch, api_key)

            with ThreadPoolExecutor(max_workers=4) as pool:
                for batch, res in pool.map(run, batches):
                    got = False
                    for src, zh in zip(batch, res):
                        if zh:
                            cache[_sent_key(src)] = zh
                            got = True
                    # 每批落一次盘，中途中断也不会白翻
                    if got:
                        _save_trans_cache(cache)
    elif todo:
        warn(f'范文中译已跳过（--no-translate），{len(todo)} 句仍无中文')

    missing = 0
    for row, text in rows:
        zh = cache.get(_sent_key(text), '')
        row['chinese'] = zh
        row['sample_plain'] = text
        if not zh:
            missing += 1
    if missing:
        warn(f'{missing} 句范文没有中文译文，实战页会退回显示模板槽位提示')
    return len(rows) - missing, len(rows)


# ---------------------------------------------------------------- 主流程

def build(refresh=False, translate=True):
    index_token = WIKI_RE.search(INDEX_URL).group(1)
    index_md = fetch_doc(index_token, refresh)
    reg = parse_index(index_md)

    tokens = ([i['token'] for i in reg['big']]
              + [i['token'] for lst in reg['small'].values() for i in lst]
              + [i['token'] for i in reg['samples']])
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda t: fetch_doc(t, refresh), tokens))

    # ---- 大作文模板
    big_types, big_refs = [], []
    for item in reg['big']:
        md = fetch_doc(item['token'])
        title = item['title']
        name = re.sub(r'模板$', '', title).strip()
        if '视频讲解' in title or name not in BIG_TYPE_IDS:
            big_refs.append({'id': item['token'], 'name': title, 'kind': item['kind'],
                             'url': f'https://my.feishu.cn/wiki/{item["token"]}',
                             'source_url': source_url(md),
                             'groups': _build_groups(md)})
            continue
        parsed = parse_big_template(md, title)
        big_types.append({
            'id': BIG_TYPE_IDS[name], 'name': name, 'title': title,
            'feature': parsed['feature'], 'kind': item['kind'],
            'url': f'https://my.feishu.cn/wiki/{item["token"]}', 'source_url': source_url(md),
            'variants': parsed['variants'], 'samples': [],
        })

    # 题目特征：只有观点型模板自带，其余从「总结构」的六种题型清单补齐
    feature_map = {}
    for r in reg['big']:
        if '总结构' in r['title']:
            feature_map = parse_feature_map(fetch_doc(r['token']))
            break
    for t in big_types:
        if not t.get('feature'):
            t['feature'] = feature_map.get(t['name'], '')

    # ---- 大作文范文
    by_id = {t['id']: t for t in big_types}
    pending = []
    for item in reg['samples']:
        md = fetch_doc(item['token'])
        name = re.sub(r'范文.*$', '', item['title']).strip()
        tid = BIG_TYPE_IDS.get(name)
        if not tid:
            warn(f'范文「{item["title"]}」无法对应题型，已跳过')
            continue
        samples = parse_samples(md)
        target = by_id.get(tid)
        if target is None:
            if not samples:
                warn(f'{name}：既无模板也无可解析范文')
                continue
            derived = derive_template_from_sample(samples[0])
            target = {'id': tid, 'name': name, 'title': f'{name}模板（由范文反推）',
                      'feature': derived['feature'], 'kind': name, 'url': '',
                      'source_url': source_url(md), 'derived': True,
                      'variants': derived['variants'], 'samples': []}
            big_types.append(target)
            by_id[tid] = target
        pending.append((name, tid, target, samples, item['token']))

    # 范文与模板的对齐放在所有题型都解析完之后做：
    # 飞书里存在放错分区的范文（报告型分区里混了混搭型题），跨题型匹配才不会错配
    candidates = [{'type_id': t['id'], 'type_name': t['name'],
                   'variant': v, 'variant_index': vi}
                  for t in big_types for vi, v in enumerate(t['variants']) if v['sections']]
    for name, tid, target, samples, token in pending:
        for q in samples:
            for v in q['versions']:
                cand = pick_variant(v['paragraphs'], candidates)
                sections = cand['variant']['sections'] if cand else []
                v['variant'] = cand['variant']['name'] if cand else ''
                v['template_type_id'] = cand['type_id'] if cand else tid
                v['template_type_name'] = cand['type_name'] if cand else name
                v['template_variant_index'] = cand['variant_index'] if cand else 0
                v['paragraphs'] = [align_sample(p, sections) | {'text': p} for p in v['paragraphs']]
                if v['template_type_id'] != tid:
                    warn(f'{name}｜{q["question"][:32]}…｜{v["name"]}｜'
                         f'实际使用的是「{v["template_type_name"]}」模板，已按该模板对照')
                for p in v['paragraphs']:
                    if p['match'] not in ('exact', 'extra') and not _only_choice_missing(p, sections):
                        warn(f'{name}｜{q["question"][:32]}…｜{v["name"]}｜{p["section_name"] or "未匹配"}｜'
                             f'{p["match"]}（相似度 {p["score"]}，'
                             f'已配 {p["filled_count"]}/{p["slot_count"]} 槽位，范文填了 {len(p["values"])} 处）')
        target['samples'] = samples
        target['sample_url'] = f'https://my.feishu.cn/wiki/{token}'

    order = list(BIG_TYPE_IDS.values())
    big_types.sort(key=lambda t: order.index(t['id']) if t['id'] in order else 99)

    done, total = translate_samples(big_types, enabled=translate)
    print(f'范文中译：{done}/{total} 句已就绪')

    # ---- 小作文模板
    charts = []
    for chart_name, items in reg['small'].items():
        cid = SMALL_CHART_IDS.get(chart_name, chart_name)
        sections, refs = [], []
        for item in items:
            md = fetch_doc(item['token'])
            title = item['title']
            base = re.sub(r'模板$', '', re.sub(r'（视频讲解）$', '', title)).strip()
            groups = []
            for g in parse_heading_tree(md, 1):
                pats, notes, items = lines_to_patterns(g['lines'])
                if not pats and not notes:
                    continue
                path = [p for p in g['path'] if not re.match(r'^第[一二三四五六七八九十]段', p)
                        and p != title]
                groups.append({'label': ' · '.join(path) if path else base,
                               'patterns': pats, 'notes': notes, 'items': items})
            entry = {'id': item['token'], 'name': base, 'title': title, 'kind': item['kind'],
                     'url': f'https://my.feishu.cn/wiki/{item["token"]}',
                     'source_url': source_url(md), 'groups': groups}
            if '视频讲解' in title or base not in SMALL_SECTION_IDS:
                refs.append(entry)
            else:
                entry['id'] = SMALL_SECTION_IDS[base]
                entry['pattern_count'] = sum(len(g['patterns']) for g in groups)
                sections.append(entry)
        sections.sort(key=lambda s: ['rewrite', 'overview', 'detail'].index(s['id'])
                      if s['id'] in ('rewrite', 'overview', 'detail') else 99)
        charts.append({'id': cid, 'name': chart_name, 'sections': sections, 'references': refs})
    charts.sort(key=lambda c: ['data', 'process', 'map'].index(c['id'])
                if c['id'] in ('data', 'process', 'map') else 99)

    return {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'source': INDEX_URL,
        'big': {'types': big_types, 'references': big_refs},
        'small': {'charts': charts},
        'warnings': warnings,
    }


def _only_choice_missing(para, sections):
    """范文把 [agree/disagree] 这类选择项直接写成了定稿措辞，不算漏配。"""
    sec = next((x for x in sections if x['id'] == para['section_id']), None)
    if sec is None or para['filled_count'] == 0:
        return False
    slots = [s for sent in sec['sentences'] for s in sent['slots']]
    filled_keys = {p['key'] for p in para['pairs']}
    missing = [s for s in slots if s['key'] not in filled_keys]
    return bool(missing) and all(s['type'] == 'choice' for s in missing)


def validate(data):
    """检查每句的 [槽位] 个数与 slots 列表是否一一对应；前端按下标配对，必须严格一致。"""
    problems = []

    def check(where, text, slots):
        keys = [m.group(1) for m in SLOT_RE.finditer(text)]
        if keys != [s['key'] for s in slots]:
            problems.append(f'{where}｜槽位错位：文本 {keys} vs 槽位 {[s["key"] for s in slots]}')

    for t in data['big']['types']:
        for v in t['variants']:
            for sec in v['sections']:
                for st in sec['sentences']:
                    check(f'{t["name"]}/{sec["name"]}', st['text'], st['slots'])
    for c in data['small']['charts']:
        for r in c['sections'] + c['references']:
            for g in r['groups']:
                for pat in g['patterns']:
                    check(f'{c["name"]}/{r["name"]}/{g["label"]}', pat['text'], pat['slots'])
    ids = [(t['id'], sec['id']) for t in data['big']['types']
           for v in t['variants'] for sec in v['sections']]
    if len(ids) != len(set(ids)):
        problems.append('段落 id 在同一题型内重复')
    return problems


def report(data):
    print('=' * 60)
    print(f'生成时间 {data["generated_at"]}')
    print('-- 大作文 --')
    for t in data['big']['types']:
        secs = [s for v in t['variants'] for s in v['sections']]
        nver = sum(len(q['versions']) for q in t['samples'])
        flag = ' (骨架由范文反推)' if t.get('derived') else ''
        print(f'  {t["name"]:<6} id={t["id"]:<18} 变体{len(t["variants"])} '
              f'段落{len(secs)} 槽位{sum(s["slot_count"] for s in secs)} '
              f'范文{len(t["samples"])}题/{nver}版{flag}')
        for v in t['variants']:
            head = f'    · 变体「{v["name"] or "默认"}」: '
            print(head + ', '.join(f'{s["name"]}({s["slot_count"]})' for s in v['sections']))
    print(f'  参考资料 {len(data["big"]["references"])} 篇')
    print('-- 小作文 --')
    for c in data['small']['charts']:
        print(f'  {c["name"]:<4} id={c["id"]}')
        for s in c['sections']:
            print(f'    · {s["name"]:<6} 分组{len(s["groups"])} 句型{s["pattern_count"]}')
        print(f'    · 参考资料 {len(c["references"])} 篇: '
              + ', '.join(r['name'] for r in c['references']))
    issues = validate(data)
    if issues:
        print(f'-- 结构校验失败 {len(issues)} 条 --')
        for i in issues:
            print('  X', i)
    else:
        print('-- 结构校验通过 --')
    if data['warnings']:
        print(f'-- 待确认 {len(data["warnings"])} 条 --')
        for w in data['warnings']:
            print('  !', w)
    print('=' * 60)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--refresh', action='store_true', help='忽略缓存，重新拉取飞书')
    ap.add_argument('--report', action='store_true', help='只打印解析报告，不写文件')
    ap.add_argument('--no-translate', action='store_true', help='跳过范文中译（不调用 LLM）')
    args = ap.parse_args()
    data = build(refresh=args.refresh, translate=not args.no_translate)
    report(data)
    if args.report:
        return 0
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'已写入 {os.path.relpath(OUT_FILE, ROOT)}（{os.path.getsize(OUT_FILE) / 1024:.0f} KB）')
    return 0


if __name__ == '__main__':
    sys.exit(main())

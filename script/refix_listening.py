"""重跑听力项目的转录，并把原有标注迁移到新字幕上。

用在 ASR 出过重复循环的项目上：新字幕的断句和 id 与旧的完全不同，而
starred_segments / error_tags / vocab_annotations / notes 全是以 segment id
为键的，直接重跑会把标注全丢掉。

迁移按两层做：
  1. 句子级——按时间轴重叠找对应的新句（时间戳都回填到原始音频时间轴，可比）
  2. 字符级——vocab / notes 还带 start_offset/end_offset，断句一变就失效，
     所以要在新句文本里重新定位那个词，重算偏移

分两步跑，中间可以人工审：
    python script/refix_listening.py transcribe <关键词> ...   # 重跑并缓存
    python script/refix_listening.py apply <关键词> ...        # 迁移并落盘
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

from core import LISTENING_REVIEW_DIR  # noqa: E402
import routers.listening_review as R  # noqa: E402
from utils.audio_segment import detect_loop  # noqa: E402

CACHE_DIR = '/tmp/refix_listening'
USERNAME = 'KaidaOcea'


def _projects(keywords):
    path = os.path.join(LISTENING_REVIEW_DIR, f'{USERNAME}_projects.json')
    out = []
    for p in json.load(open(path, encoding='utf-8')):
        if any(k.lower() in (p.get('title') or '').lower() for k in keywords):
            out.append(p)
    return out


def _overlap(a, b):
    return max(0.0, min(a['end'], b['end']) - max(a['start'], b['start']))


def _best_match(old_seg, new_segs):
    """按时间重叠找对应新句；完全无重叠时退到中点最近的一句。"""
    best, best_ov = None, 0.0
    for n in new_segs:
        ov = _overlap(old_seg, n)
        if ov > best_ov:
            best, best_ov = n, ov
    if best is not None:
        return best, best_ov
    mid = (old_seg['start'] + old_seg['end']) / 2
    nearest = min(new_segs, key=lambda n: min(abs(n['start'] - mid), abs(n['end'] - mid)))
    return nearest, 0.0


def _match_all(old_seg, new_segs, cover=0.6):
    """一句旧句可能被新转录拆成好几句，星标和错误分类要跟着拆。

    只取重叠最大的那一句会丢掉另一半——旧稿里「These holidays are becoming
    increasingly popular. Would you like to...」是两句并成一句的，新稿拆开后
    只标后半句就丢了前半句。

    所以除了重叠最大的那句（保底，绝不丢），再带上任何被这句旧句覆盖掉
    cover 以上的新句。旧稿时间戳可能是退化的均匀值，用「覆盖新句的比例」
    判断比用旧句时长可靠。
    """
    best, best_ov = _best_match(old_seg, new_segs)
    out = [best]
    for n in new_segs:
        if n is best:
            continue
        span = n['end'] - n['start']
        if span > 0 and _overlap(old_seg, n) / span >= cover:
            out.append(n)
    return sorted(out, key=lambda n: n['start']), best_ov


def _common_suffix(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[-1 - n] == b[-1 - n]:
        n += 1
    return n


def _common_prefix(a, b):
    n = 0
    while n < len(a) and n < len(b) and a[n] == b[n]:
        n += 1
    return n


def _whole_word(text, pos, length):
    before = pos == 0 or not text[pos - 1].isalnum()
    after = pos + length >= len(text) or not text[pos + length].isalnum()
    return before and after


def _locate(needle, old_text, old_so, old_eo, new_seg, new_segs, window=2):
    """在新句里重新定位标注锚点，返回 (句, 起偏移, 止偏移) 或 None。

    不能简单 find() 取第一个匹配：有条真实笔记的 quote 就是「end」，三个字母，
    新句里只要出现 recommend / friend / attend 就会锚到错误的位置。所以拿旧句
    里该锚点左右的文本当上下文打分，再叠一个「整词性要和旧的一致」的加分。
    """
    needle_low = needle.lower()
    if not needle_low:
        return None
    left = old_text[max(0, old_so - 24):old_so].lower()
    right = old_text[old_eo:old_eo + 24].lower()
    old_whole = _whole_word(old_text.lower(), old_so, old_eo - old_so)

    idx = new_segs.index(new_seg)
    cands = [new_seg] + [new_segs[i]
                         for i in range(max(0, idx - window), min(len(new_segs), idx + window + 1))
                         if new_segs[i] is not new_seg]

    best = None
    for rank, cand in enumerate(cands):
        low = cand['text'].lower()
        pos = low.find(needle_low)
        while pos >= 0:
            score = (_common_suffix(low[:pos], left)
                     + _common_prefix(low[pos + len(needle_low):], right)
                     + (4 if _whole_word(low, pos, len(needle_low)) == old_whole else 0)
                     - rank * 0.5)
            if best is None or score > best[0]:
                best = (score, cand, pos, pos + len(needle_low))
            pos = low.find(needle_low, pos + 1)
    if best is None:
        return None
    return best[1], best[2], best[3]


def cmd_transcribe(keywords):
    os.makedirs(CACHE_DIR, exist_ok=True)
    for p in _projects(keywords):
        pid, title = p['id'], p['title']
        audio = os.path.join(LISTENING_REVIEW_DIR, pid, p.get('audio_filename') or 'original.mp3')
        print(f'\n=== {title} ===')
        if not os.path.exists(audio):
            print('  音频不存在，跳过')
            continue

        result, error = R._transcribe(audio)
        if error:
            print(f'  转录失败: {error}')
            continue
        segs = result['segments']
        print(f'  转录 {len(segs)} 句，循环检测 {detect_loop(segs)}')

        polished, perr = R._polish_and_translate(segs)
        if perr:
            print(f'  润色失败: {perr}')
            continue
        pm = {s['id']: s for s in polished}
        for s in segs:
            hit = pm.get(s['id'])
            if hit:
                s['text'] = hit.get('text', s['text'])
                s['translation'] = hit.get('translation', '')
        missing = [s['id'] for s in segs if 'translation' not in s or not s['translation']]
        print(f'  润色完成，无译文 {len(missing)} 句')

        json.dump({'segments': segs, 'duration': result['duration']},
                  open(os.path.join(CACHE_DIR, f'{pid}.json'), 'w', encoding='utf-8'),
                  ensure_ascii=False, indent=2)
        print(f'  已缓存 -> {CACHE_DIR}/{pid}.json')


def cmd_apply(keywords, write=True):
    stamp = datetime.now().strftime('%Y%m%d')
    for p in _projects(keywords):
        pid, title = p['id'], p['title']
        cache = os.path.join(CACHE_DIR, f'{pid}.json')
        data_path = os.path.join(LISTENING_REVIEW_DIR, pid, 'data.json')
        print(f'\n=== {title} ===')
        if not os.path.exists(cache):
            print('  没有缓存，先跑 transcribe')
            continue

        new = json.load(open(cache, encoding='utf-8'))
        new_segs = new['segments']
        old = json.load(open(data_path, encoding='utf-8'))
        old_segs = old.get('segments') or []
        old_by_id = {s['id']: s for s in old_segs}
        print(f'  {len(old_segs)} 句 -> {len(new_segs)} 句')

        def remap_id(old_id):
            o = old_by_id.get(int(old_id))
            if not o:
                return None, None, None
            n, ov = _best_match(o, new_segs)
            return n['id'], ov, o

        def remap_all(old_id):
            o = old_by_id.get(int(old_id))
            if not o:
                return None, None, None
            hits, ov = _match_all(o, new_segs)
            return hits, ov, o

        lost = []

        # 星标（旧句被拆成多句时全都标上）
        stars = []
        for oid in old.get('starred_segments') or []:
            hits, ov, o = remap_all(oid)
            if hits is None:
                lost.append(f'★ id={oid} 旧句不存在')
                continue
            stars.extend(n['id'] for n in hits)
            mark = '' if ov > 0 else '  (无时间重叠, 取最近句)'
            split = '  (旧句被拆成 %d 句)' % len(hits) if len(hits) > 1 else ''
            print(f'    ★ {oid} -> {[n["id"] for n in hits]}{split}{mark}')
            for n in hits:
                print(f'         @{n["start"]:.1f}s  {n["text"][:58]}')
        stars = sorted(set(stars))

        # 错误分类（同样跟着拆）
        tags = {}
        for oid, vals in (old.get('error_tags') or {}).items():
            hits, ov, o = remap_all(oid)
            if hits is None:
                lost.append(f'🏷 id={oid} 旧句不存在')
                continue
            for n in hits:
                key = str(n['id'])
                tags.setdefault(key, [])
                for v in vals:
                    if v not in tags[key]:
                        tags[key].append(v)
            print(f'    🏷 {oid} -> {[n["id"] for n in hits]} {vals}')

        # 生词（需要重算字符偏移）
        vocab = []
        for a in old.get('vocab_annotations') or []:
            nid, ov, o = remap_id(a['segment_id'])
            if nid is None:
                lost.append(f'📖 {a["word"]} 旧句不存在')
                continue
            n = next(s for s in new_segs if s['id'] == nid)
            hit = _locate(a['word'], o['text'], a['start_offset'], a['end_offset'], n, new_segs)
            if not hit:
                lost.append(f'📖 «{a["word"]}» 在新字幕 @{n["start"]:.1f}s 附近找不到')
                continue
            seg, so, eo = hit
            vocab.append({**a, 'segment_id': seg['id'], 'start_offset': so, 'end_offset': eo})
            print(f'    📖 {a["segment_id"]} -> {seg["id"]}  {a["word"]} [{so}:{eo}] '
                  f'= «{seg["text"][so:eo]}»')

        # 笔记（同样重算偏移，锚在 quote 上）
        notes = []
        for nt in old.get('notes') or []:
            nid, ov, o = remap_id(nt['segment_id'])
            if nid is None:
                lost.append(f'📝 «{nt["quote"]}» 旧句不存在')
                continue
            n = next(s for s in new_segs if s['id'] == nid)
            hit = _locate(nt['quote'], o['text'], nt['start_offset'], nt['end_offset'], n, new_segs)
            if not hit:
                lost.append(f'📝 «{nt["quote"]}» 在新字幕 @{n["start"]:.1f}s 附近找不到')
                continue
            seg, so, eo = hit
            notes.append({**nt, 'segment_id': seg['id'], 'start_offset': so, 'end_offset': eo})
            print(f'    📝 {nt["segment_id"]} -> {seg["id"]}  «{nt["quote"][:30]}» [{so}:{eo}]')

        n_old = (len(old.get('starred_segments') or []) + len(old.get('error_tags') or {})
                 + len(old.get('vocab_annotations') or []) + len(old.get('notes') or []))
        n_new = len(stars) + len(tags) + len(vocab) + len(notes)
        print(f'  标注 {n_old} 项 -> 复原 {n_new} 项' + (f'，丢失 {len(lost)} 项' if lost else '，无丢失'))
        for item in lost:
            print(f'    ✗ {item}')

        if not write:
            continue

        backup = f'{data_path}.bak.{stamp}'
        if not os.path.exists(backup):
            shutil.copy2(data_path, backup)
        payload = {
            'segments': new_segs,
            'starred_segments': stars,
            'vocab_annotations': vocab,
            'notes': notes,
            'error_tags': tags,
        }
        json.dump(payload, open(data_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
        print(f'  已写入，备份 {os.path.basename(backup)}')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mode, kws = sys.argv[1], sys.argv[2:]
    if mode == 'transcribe':
        cmd_transcribe(kws)
    elif mode == 'apply':
        cmd_apply(kws, write=True)
    elif mode == 'dry-run':
        cmd_apply(kws, write=False)
    else:
        print(__doc__)
        sys.exit(1)

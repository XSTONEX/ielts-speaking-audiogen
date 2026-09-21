"""听力项目字幕体检：找出 ASR 留下的三类坏味道。

  1. 重复循环——Whisper 解码崩坏后把自己的输出反复喂回去
  2. 静音区幻觉——纯静音上凭空生成的句子（"Thank you for watching." 之类
     的训练残留），混在精听材料里是假句子
  3. 退化时间戳——句子时长高度集中在同一个整数值，说明 Whisper 放弃了
     真实时间戳改用均匀切分，点句跳转会对不准

用法:
    python script/check_listening_health.py            # 体检全部
    python script/check_listening_health.py --ids      # 只输出需重跑的 id
"""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import LISTENING_REVIEW_DIR  # noqa: E402
from utils.audio_segment import detect_loop, detect_silences, probe_duration, LONG_SILENCE  # noqa: E402

USERNAME = 'KaidaOcea'
DEGEN_RATIO = 0.25


def inspect(project):
    pid = project['id']
    data_path = os.path.join(LISTENING_REVIEW_DIR, pid, 'data.json')
    audio = os.path.join(LISTENING_REVIEW_DIR, pid, project.get('audio_filename') or 'original.mp3')
    if not os.path.exists(data_path):
        return None
    segs = (json.load(open(data_path, encoding='utf-8')) or {}).get('segments') or []
    if not segs:
        return None

    loop = detect_loop(segs)[0]

    halluc = []
    if os.path.exists(audio):
        total = probe_duration(audio)
        for a, b in detect_silences(audio):
            if b - a < LONG_SILENCE:
                continue
            for s in segs:
                if s['start'] >= a + 0.3 and s['end'] <= b - 0.3 and (s.get('text') or '').strip():
                    halluc.append((round(s['start']), s['text'][:46]))

    # 时长取值集中在同一个整数 = 均匀切分，不是真实时间戳
    durs = Counter(round(s['end'] - s['start'], 2) for s in segs)
    dval, dn = durs.most_common(1)[0]
    degen = dn / len(segs) if float(dval).is_integer() else 0.0

    return {'id': pid, 'title': project['title'], 'n': len(segs),
            'loop': loop, 'halluc': halluc, 'degen': degen, 'degen_val': dval}


def main():
    only_ids = '--ids' in sys.argv
    path = os.path.join(LISTENING_REVIEW_DIR, f'{USERNAME}_projects.json')
    rows = [r for r in (inspect(p) for p in json.load(open(path, encoding='utf-8'))) if r]
    bad = [r for r in rows if r['loop'] or r['halluc'] or r['degen'] >= DEGEN_RATIO]

    if only_ids:
        print('\n'.join(r['id'] for r in bad))
        return

    print(f'{len(rows)} 个项目，{len(bad)} 个需要重跑\n')
    print(f"{'循环':>4}{'幻觉':>5}{'退化':>7}{'句数':>6}  标题")
    print('-' * 62)
    for r in sorted(bad, key=lambda r: -(r['loop'] * 100 + len(r['halluc']))):
        print(f"{r['loop']:>4}{len(r['halluc']):>5}{r['degen'] * 100:>6.0f}%{r['n']:>6}  {r['title']}")
        for at, text in r['halluc']:
            print(f"        @{at}s  «{text}»")
    if not bad:
        print('全部健康')


if __name__ == '__main__':
    main()

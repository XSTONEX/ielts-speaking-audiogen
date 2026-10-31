"""给听力 E2E 的沙盒灌一套编造的数据：两个假用户、5 个听力项目（已完成 / 已掌握 / 转录中 / 翻译中 / 失败）。

所有英文句子和中文译文都是编的；音频用 macOS 的 `say` 现场合成，再用 ffmpeg 拼起来。
每次跑都会清空沙盒里的 listening_review/ 重新灌，并把两个登录 token 写进 <沙盒>/e2e_tokens.json 给 e2e.js 用。
用法: python3 seed.py <沙盒目录>
"""
import json, os, secrets, subprocess, sys, tempfile, shutil
from datetime import datetime

if len(sys.argv) != 2:
    sys.exit('用法: python3 seed.py <沙盒目录>')
SB = os.path.abspath(sys.argv[1])
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
# 会清空 listening_review/、覆盖 users.json，绝不能对着真实仓库跑
if os.path.exists(os.path.join(SB, '.git')) or SB == REPO or not os.path.exists(os.path.join(SB, 'app.py')):
    sys.exit(f'{SB} 不像沙盒副本（要有 app.py、不能是 git 仓库本身），不灌数据')
LR = os.path.join(SB, 'listening_review')
shutil.rmtree(LR, ignore_errors=True)
os.makedirs(LR, exist_ok=True)

USER = 'demo'

HALL = [
    ("Samantha", "Good morning, Riverside Community Centre. How can I help you?", "早上好，这里是河畔社区中心。有什么可以帮您？"),
    ("Daniel", "Hi, I'd like to book the main hall for a birthday party next month.", "你好，我想预订下个月的主厅办生日派对。"),
    ("Samantha", "Of course. Which date did you have in mind?", "没问题。您想定哪一天？"),
    ("Daniel", "Saturday the fourteenth, if it's still available.", "十四号星期六，如果还空着的话。"),
    ("Samantha", "Let me check. Yes, the hall is free from two until eleven.", "我查一下。是的，大厅两点到十一点都空着。"),
    ("Daniel", "Great. How many guests can it hold?", "太好了。能容纳多少位客人？"),
    ("Samantha", "Up to one hundred and twenty standing, or eighty if they're seated.", "站着最多一百二十人，坐着的话八十人。"),
    ("Daniel", "We'll probably have around sixty, so that's plenty of room.", "我们大概六十人左右，那空间很充足。"),
    ("Samantha", "The hire fee is forty-five pounds an hour, and there's a refundable deposit of a hundred pounds.", "租金每小时四十五英镑，另有一百英镑可退押金。"),
    ("Daniel", "Does that include the kitchen?", "这包括厨房吗？"),
    ("Samantha", "The kitchen is extra, but the tables and chairs come free of charge.", "厨房另外收费，不过桌椅免费提供。"),
    ("Daniel", "And is there anywhere to park nearby?", "附近有地方停车吗？"),
    ("Samantha", "There's a car park behind the building, but it fills up quickly on weekends.", "楼后面有个停车场，不过周末很快就满。"),
    ("Daniel", "Okay. Could I take the booking under the name Whitfield?", "好的。可以用 Whitfield 这个名字登记吗？"),
    ("Samantha", "Could you spell that for me, please?", "麻烦您拼一下好吗？"),
    ("Daniel", "W, H, I, T, F, I, E, L, D.", "W、H、I、T、F、I、E、L、D。"),
]

GLASS = [
    ("Daniel", "Today I want to look at how glass bridges became a tourist attraction.", "今天我想讲讲玻璃桥是怎么变成旅游景点的。"),
    ("Daniel", "The first designs were tested in the late nineteen nineties, mostly in mountain parks.", "最早的设计在九十年代末开始测试，大多在山地公园。"),
    ("Daniel", "Engineers had to solve two problems: strength and public confidence.", "工程师得解决两个问题：强度和公众信心。"),
    ("Daniel", "Laminated panels meant that a single crack would not cause the floor to fail.", "夹层玻璃板意味着一道裂缝不会让桥面整体失效。"),
    ("Daniel", "Surprisingly, visitor surveys showed that fear was part of the appeal.", "出人意料的是，游客调查显示恐惧本身就是吸引力的一部分。"),
    ("Daniel", "However, maintenance costs turned out to be far higher than predicted.", "然而，维护成本远高于预期。"),
]

LIB = [("Samantha", "Welcome to the city library tour.", "")]


def tts(lines, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    tmp = tempfile.mkdtemp()
    parts, segs, t = [], [], 0.0
    gap = 0.6
    silence = os.path.join(tmp, 'gap.wav')
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono',
                    '-t', str(gap), silence], check=True)
    for i, (voice, text, zh) in enumerate(lines):
        aiff = os.path.join(tmp, f'{i}.aiff')
        wav = os.path.join(tmp, f'{i}.wav')
        subprocess.run(['say', '-v', voice, '-r', '175', '-o', aiff, text], check=True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', aiff, '-ar', '22050', '-ac', '1', wav], check=True)
        dur = float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                                             '-of', 'csv=p=0', wav]).decode().strip())
        segs.append({'id': i, 'start': round(t, 2), 'end': round(t + dur, 2), 'text': text, 'translation': zh})
        parts += [wav, silence]
        t += dur + gap
    lst = os.path.join(tmp, 'list.txt')
    with open(lst, 'w') as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', lst,
                    '-c:a', 'libmp3lame', '-b:a', '64k', out_path, '-y'], check=True)
    shutil.rmtree(tmp)
    return segs, round(t, 2)


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


projects = []

# 1. a well-used project
pid = 'lr_20261028_201500_demo0001'
segs, dur = tts(HALL, os.path.join(LR, pid, 'original.mp3'))
write(os.path.join(LR, pid, 'data.json'), {
    'segments': segs,
    'starred_segments': [6, 8, 15],
    'vocab_annotations': [
        {'id': 'v_a1b2c3', 'segment_id': 8, 'word': 'refundable deposit', 'meaning': '可退还的押金',
         'start_offset': HALL[8][1].index('refundable deposit'), 'end_offset': HALL[8][1].index('refundable deposit') + len('refundable deposit')},
        {'id': 'v_d4e5f6', 'segment_id': 10, 'word': 'free of charge', 'meaning': '免费',
         'start_offset': HALL[10][1].index('free of charge'), 'end_offset': HALL[10][1].index('free of charge') + len('free of charge')},
        {'id': 'v_g7h8i9', 'segment_id': 12, 'word': 'fills up', 'meaning': '（场地）被占满',
         'start_offset': HALL[12][1].index('fills up'), 'end_offset': HALL[12][1].index('fills up') + len('fills up')},
    ],
    'notes': [
        {'id': 'n_j1k2l3', 'segment_id': 6, 'quote': 'one hundred and twenty standing, or eighty if they\'re seated',
         'note': '数字题陷阱：先说站立容量，后说坐着的容量。题目问 seated 要填 80，不是 120。',
         'start_offset': HALL[6][1].index('one hundred'), 'end_offset': HALL[6][1].index('one hundred') + len("one hundred and twenty standing, or eighty if they're seated"),
         'created_at': '2026-10-28T20:40:00'},
        {'id': 'n_m4n5o6', 'segment_id': 15, 'quote': 'W, H, I, T, F, I, E, L, D',
         'note': '拼写题：F 和 S 容易听混，注意 Whitfield 中间是 F。',
         'start_offset': 0, 'end_offset': len('W, H, I, T, F, I, E, L, D'),
         'created_at': '2026-10-28T20:42:00'},
    ],
    'error_tags': {'6': ['phonetic'], '8': ['vocab', 'spelling'], '15': ['spelling']},
})
projects.append({'id': pid, 'title': 'Part 1 · Booking a Community Hall', 'username': USER, 'status': 'completed',
                 'created_at': '2026-10-28T20:15:00', 'updated_at': '2026-10-29T21:00:00', 'duration': dur,
                 'audio_filename': 'original.mp3', 'source_type': 'upload', 'source_url': None, 'error': None,
                 'checkin_count': 3, 'mastered': False})

# 2. mastered lecture
pid2 = 'lr_20261020_190000_demo0002'
segs2, dur2 = tts(GLASS, os.path.join(LR, pid2, 'original.mp3'))
write(os.path.join(LR, pid2, 'data.json'), {
    'segments': segs2, 'starred_segments': [5],
    'vocab_annotations': [
        {'id': 'v_p7q8r9', 'segment_id': 3, 'word': 'Laminated', 'meaning': '层压的；夹层的',
         'start_offset': 0, 'end_offset': len('Laminated')},
    ],
    'notes': [
        {'id': 'n_s1t2u3', 'segment_id': 5, 'quote': 'far higher than predicted',
         'note': 'However 后面是转折答案；predicted = expected 同义替换。',
         'start_offset': GLASS[5][1].index('far higher'), 'end_offset': GLASS[5][1].index('far higher') + len('far higher than predicted'),
         'created_at': '2026-10-21T08:10:00'},
    ],
    'error_tags': {'5': ['distractor']},
})
projects.append({'id': pid2, 'title': 'Part 4 · The Rise of Glass Bridges', 'username': USER, 'status': 'completed',
                 'created_at': '2026-10-20T19:00:00', 'updated_at': '2026-10-26T10:00:00', 'duration': dur2,
                 'audio_filename': 'original.mp3', 'source_type': 'url', 'source_url': 'https://example.com/glass.mp3',
                 'error': None, 'checkin_count': 7, 'mastered': True})

# 3. processing / translating / error states (no data.json)
for i, (status, title, extra) in enumerate([
    ('processing', 'Part 2 · City Library Tour', {}),
    ('translating', 'Part 3 · Planning a Field Trip', {'duration': 312.4}),
    ('error', 'Part 1 · Gym Membership Enquiry', {'error': 'WildAPI API error: HTTP 504', 'error_phase': 'polish', 'duration': 288.0}),
]):
    p = f'lr_2026103{i}_120000_demo000{i + 3}'
    os.makedirs(os.path.join(LR, p), exist_ok=True)
    tts(LIB, os.path.join(LR, p, 'original.mp3'))
    rec = {'id': p, 'title': title, 'username': USER, 'status': status,
           'created_at': ['2026-10-30T10:00:00', '2026-10-30T09:00:00', '2026-10-29T22:00:00'][i], 'updated_at': '2026-10-30T10:01:00', 'duration': None,
           'audio_filename': 'original.mp3', 'source_type': 'upload', 'source_url': None, 'error': None}
    rec.update(extra)
    projects.append(rec)

# 「翻译中」那篇假装重启前已经转完字幕：重试应该直接从润色翻译开始
write(os.path.join(LR, 'lr_20261031_120000_demo0004', 'transcript.json'), {
    'segments': [{'id': 0, 'start': 0.0, 'end': 2.1, 'text': 'welcome to the city library tour'}],
    'duration': 2.1,
})

write(os.path.join(LR, f'{USER}_projects.json'), projects)
# demo2 没有任何项目，用来验证别人拿不到 demo 的音频
write(os.path.join(SB, 'users.json'), {
    USER: {'password': 'sandbox-only', 'username': USER},
    'demo2': {'password': 'sandbox-only-2', 'username': 'demo2'},
})
tokens_path = os.path.join(SB, 'tokens.json')
try:
    with open(tokens_path, encoding='utf-8') as f:
        tokens = json.load(f)
except (OSError, json.JSONDecodeError):
    tokens = {}
e2e_tokens = {}
for name in (USER, 'demo2'):
    token = secrets.token_urlsafe(32)
    tokens[token] = {'created_time': datetime.now().isoformat(), 'username': name}
    e2e_tokens[name] = token
write(tokens_path, tokens)
write(os.path.join(SB, 'e2e_tokens.json'), e2e_tokens)
print('seeded', len(projects), 'projects;', 'hall', dur, 's; glass', dur2, 's')

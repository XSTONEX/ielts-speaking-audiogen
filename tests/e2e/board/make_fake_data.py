"""给学习交流小天地的浏览器测试搭一份编造的数据（用户、录音、文章、帖子、评论、token、上传用的测试文件）。

用法：python make_fake_data.py <沙盒目录>
沙盒目录是仓库代码的一份拷贝（见同目录 README.md），绝不能是仓库本身：这里会整个覆盖
users.json / tokens.json / message_board / challenges 等数据。每次跑都会恢复成同样的初始状态。
所有人名、内容都是编造的；仓库是公开的，不要换成真实数据。
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta

if len(sys.argv) != 2:
    sys.exit('用法：python make_fake_data.py <沙盒目录>')
sb = os.path.realpath(sys.argv[1])
repo = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
if sb == repo or sb.startswith(repo + os.sep) or os.path.exists(os.path.join(sb, '.git')):
    sys.exit(f'拒绝：{sb} 是仓库或在仓库里面，会覆盖真实数据。请用仓库外的拷贝目录。')
if not os.path.exists(os.path.join(sb, 'app.py')):
    sys.exit(f'拒绝：{sb} 里没有 app.py，不像是仓库代码的拷贝。')
os.chdir(sb)

def dump(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

# ---- 清掉上一轮测试留下的东西 ----
for d in ('message_board', 'challenges', '_e2e'):
    shutil.rmtree(d, ignore_errors=True)
for d in glob.glob('vocab_audio/challenge_*'):
    shutil.rmtree(d, ignore_errors=True)

users = {
    'linxia': {'username': 'linxia', 'password': 'test-only', 'display_name': '林夏', 'avatar': 'avatar_admin.svg', 'role': 'admin', 'created_at': '2026-01-01T09:00:00'},
    'zhouyu': {'username': 'zhouyu', 'password': 'test-only', 'display_name': '周屿', 'avatar': 'avatar_teacher.svg', 'role': 'admin', 'created_at': '2026-01-01T09:00:00'},
    'chenmo': {'username': 'chenmo', 'password': 'test-only', 'display_name': '陈默', 'avatar': 'avatar_admin.svg', 'role': 'user', 'created_at': '2026-01-01T09:00:00'},
}
dump('users.json', users)
dump('tokens.json', {})

# ---- 口语录音（2 秒静音 mp3，要有 ffmpeg） ----
silence = '_silence.mp3'
if not os.path.exists(silence):
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', '-t', '2', '-q:a', '9', silence], check=True)
silent = open(silence, 'rb').read()

folders = {
    'P1 - Hometown': [
        ("What's the most interesting part of your hometown?", "My hometown is a small coastal city, and the old harbour is the part I like best."),
        ("Do you think you'll live there in the future?", "Probably not, because most of the jobs I'm interested in are in bigger cities."),
    ],
    'P1 - Reading': [
        ("Do you like reading?", "Yes, I read a little almost every night before bed."),
        ("What kind of books did you read as a child?", "Mostly adventure stories and comics."),
    ],
    'P2 - A Memorable Trip': [
        (None, "I'd like to talk about a trip to a mountain village I took with my cousins two summers ago."),
        (None, "The trip I remember best was a weekend in a small lake town."),
    ],
    'P3 - Technology': [
        ("How has technology changed the way people communicate?", "It has made communication instant but perhaps a little shallower."),
    ],
}
for folder, items in folders.items():
    d = os.path.join('audio_files', folder)
    os.makedirs(d, exist_ok=True)
    for i, (q, a) in enumerate(items):
        name = f'{folder}_20261020_10{i:02d}00'
        open(os.path.join(d, name + '.mp3'), 'wb').write(silent)
        text = (q + '\n' + a) if q else a
        open(os.path.join(d, name + '.txt'), 'w', encoding='utf-8').write(text)
open('audio_files/P2 - A Memorable Trip/question.txt', 'w', encoding='utf-8').write(
    'Describe a trip you took that you still remember.\nYou should say:\nwhere you went\nwho you went with\nwhat you did\nand explain why it was memorable.')
os.makedirs('combined_audio', exist_ok=True)
for folder in ('P2 - A Memorable Trip', 'P1 - Hometown'):
    open(os.path.join('combined_audio', folder + '.mp3'), 'wb').write(silent)

# ---- 精读文章（挑战从这些生词里出题） ----
def article(aid, title, category, words):
    text = ' '.join(w for w, _ in words) + '.'
    hl = []
    pos = 0
    for i, (w, m) in enumerate(words):
        hl.append({'id': f'h{i}', 'start': pos, 'end': pos + len(w), 'meaning': m, 'created_at': '2026-10-01T10:00:00', 'text': w})
        pos += len(w) + 1
    dump(f'intensive_articles/{aid}.json', {
        'id': aid, 'title': title, 'category': category, 'created_at': '2026-10-01T10:00:00',
        'content_text': text, 'content_html': f'<p>{text}</p>', 'highlights': hl})

article('20261001100000-glass-bridge', 'The Glass Bridge', 'Reading', [
    ('span', 'n. 跨度；一段时间'), ('load-bearing', 'adj. 承重的'), ('tempered', 'adj. 钢化的'),
    ('withstand', 'v. 经受住'), ('panoramic', 'adj. 全景的'), ('vertigo', 'n. 眩晕'),
    ('inspection', 'n. 检查'), ('durable', 'adj. 耐用的')])
article('20261002100000-urban-bees', 'Urban Bees and City Gardens', 'Reading', [
    ('pollinate', 'v. 授粉'), ('colony', 'n. 蜂群；群体'), ('foraging', 'n. 觅食'),
    ('rooftop', 'n. 屋顶'), ('biodiversity', 'n. 生物多样性'), ('decline', 'n. 下降'),
    ('habitat', 'n. 栖息地')])
article('20261003100000-campus-radio', 'Campus Radio Interview', 'Listening', [
    ('broadcast', 'v. 广播'), ('volunteer', 'n. 志愿者'), ('schedule', 'n. 日程表'),
    ('interview', 'n. 采访'), ('feedback', 'n. 反馈'), ('audience', 'n. 听众')])
article('20261004100000-public-transport', "Why Cities Can't Ignore Public Transport", 'Writing', [
    ('congestion', 'n. 拥堵'), ('subsidise', 'v. 补贴'), ('commuter', 'n. 通勤者'),
    ('emission', 'n. 排放'), ('infrastructure', 'n. 基础设施')])

# ---- 帖子里的图片（画出来的，不是照片） ----
from PIL import Image, ImageDraw
os.makedirs('message_board/images/zhouyu', exist_ok=True)
os.makedirs('message_board/images/linxia', exist_ok=True)
img = Image.new('RGB', (1200, 800), (244, 241, 232))
d = ImageDraw.Draw(img)
for y in range(90, 800, 52):
    d.line([(60, y), (1140, y)], fill=(200, 205, 220), width=2)
d.rectangle([60, 40, 1140, 760], outline=(160, 160, 160), width=3)
for i, y in enumerate(range(120, 700, 104)):
    d.rectangle([90, y, 90 + 300 + (i * 97) % 500, y + 22], fill=(120, 130, 150))
img.save('message_board/images/zhouyu/20261028_201500_a1b2c3d4.jpg', quality=85)
img2 = Image.new('RGB', (900, 1200), (228, 236, 244))
d2 = ImageDraw.Draw(img2)
d2.ellipse([200, 300, 700, 800], fill=(150, 175, 205))
d2.rectangle([100, 950, 800, 1000], fill=(110, 120, 140))
img2.save('message_board/images/linxia/20261029_093000_e5f6a7b8.jpg', quality=85)

# ---- 帖子和评论 ----
now = datetime.now()
def ts(minutes):
    return (now - timedelta(minutes=minutes)).isoformat()
def u(name):
    x = users[name]
    return {k: x[k] for k in ('username', 'display_name', 'role', 'avatar')}

messages = [
    {'id': 'msg_fake_0001', 'user': u('zhouyu'), 'type': 'mixed_content', 'timestamp': ts(60 * 26),
     'content': {'text': '今天把 Part 2「难忘的旅行」重新录了一遍，第二版比第一版流畅多了。大家帮我听听开头那段是不是还有点赶？',
                 'audios': [{'folder': 'P2 - A Memorable Trip', 'filename': 'P2 - A Memorable Trip_20261020_100100.mp3',
                             'question': '', 'type': 'single'},
                            {'folder': 'P2 - A Memorable Trip', 'file_count': 2, 'has_combined': True,
                             'question': 'Describe a trip you took that you still remember.\nYou should say:\nwhere you went\nwho you went with\nwhat you did\nand explain why it was memorable.',
                             'type': 'combined'}],
                 'articles': [], 'images': [], 'challenge': None}},
    {'id': 'msg_fake_0002', 'user': u('linxia'), 'type': 'mixed_content', 'timestamp': ts(60 * 5),
     'content': {'text': '推荐一篇读完很有收获的文章，桥梁结构那段的词汇特别适合背。',
                 'audios': [], 'images': [], 'challenge': None,
                 'articles': [{'id': '20261001100000-glass-bridge', 'title': 'The Glass Bridge', 'category': 'Reading', 'highlight_count': 8}]}},
    {'id': 'msg_fake_0003', 'user': u('zhouyu'), 'type': 'mixed_content', 'timestamp': ts(60 * 2),
     'content': {'text': '昨晚整理的同义替换笔记，拍了一张。',
                 'audios': [], 'articles': [], 'challenge': None,
                 'images': [{'filename': 'zhouyu/20261028_201500_a1b2c3d4.jpg', 'caption': ''}]}},
    {'id': 'msg_fake_0004', 'user': u('chenmo'), 'type': 'text', 'timestamp': ts(60 * 24 * 9),
     'content': {'text': '（旧格式的纯文字帖）大家早上好，今天一起打卡吧。'}},
    # 挑战文件已经不在了的帖子（页面要显示「题目已经不在了」）
    {'id': 'msg_fake_0005', 'user': u('zhouyu'), 'type': 'mixed_content', 'timestamp': '2026-03-02T10:00:00',
     'content': {'text': '', 'audios': [], 'articles': [], 'images': [],
                 'challenge': {'id': 'gone-challenge-0001', 'title': '三月词汇赛', 'description': '',
                               'vocabulary_count': 5, 'mentioned_users': ['linxia']}}},
]
dump('message_board/messages.json', messages)
comments = [
    {'id': 'comment_fake_0001', 'post_id': 'msg_fake_0001', 'user': u('linxia'), 'type': 'mixed_content', 'timestamp': ts(60 * 25),
     'content': {'text': '开头确实快了一点，第二句后面停顿半拍会更自然。', 'audios': [], 'articles': [], 'images': [], 'challenge': None}},
    {'id': 'comment_fake_0002', 'post_id': 'msg_fake_0001', 'user': u('chenmo'), 'type': 'mixed_content', 'timestamp': ts(60 * 20),
     'content': {'text': '我也录了同一题，可以对比一下：', 'articles': [], 'images': [], 'challenge': None,
                 'audios': [{'folder': 'P1 - Hometown', 'filename': 'P1 - Hometown_20261020_100000.mp3',
                             'question': "What's the most interesting part of your hometown?", 'type': 'single'}]}},
    {'id': 'comment_fake_0003', 'post_id': 'msg_fake_0003', 'user': u('linxia'), 'type': 'mixed_content', 'timestamp': ts(60),
     'content': {'text': '字好工整！我也传一张我的。', 'audios': [], 'articles': [], 'challenge': None,
                 'images': [{'filename': 'linxia/20261029_093000_e5f6a7b8.jpg', 'caption': ''}]}},
]
dump('message_board/comments.json', comments)
os.makedirs('challenges', exist_ok=True)

# ---- 上传测试用的文件：两张小图、一个超过 10MB 的、一个不是图片的 ----
fx = os.path.join('_e2e', 'fixtures')
os.makedirs(fx, exist_ok=True)
Image.new('RGB', (320, 240), (196, 214, 232)).save(os.path.join(fx, 'a.png'))
Image.new('RGB', (240, 320), (232, 220, 196)).save(os.path.join(fx, 'b.png'))
with open(os.path.join(fx, 'big.jpg'), 'wb') as f:
    f.write(b'\xff\xd8\xff\xe0' + b'\0' * (11 * 1024 * 1024))
with open(os.path.join(fx, 'note.txt'), 'w', encoding='utf-8') as f:
    f.write('not an image')

# ---- 给三个假用户发 token，浏览器脚本直接拿来用 ----
sys.path.insert(0, sb)
import core  # noqa: E402  沙盒里的那份代码，tokens.json 写在沙盒目录
out = {}
for name, x in users.items():
    out[name] = {'token': core.create_token(name), 'user': u(name)}
dump(os.path.join('_e2e', 'tokens.json'), out)
print(f'假数据已写入 {sb}')

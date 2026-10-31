"""往沙盒里写一份编造的单词本数据（没有任何真实用户数据），给 e2e_vocab.js 用。

用法：python3 make_fake_data.py <沙盒目录>
写出 vocabulary_book/、一份一样的 vocabulary_book.pristine/（测试每轮从它重置）、
users.json（假账号 demo / not-a-real-password）和空的 tokens.json。
只用标准库；同一个种子每次生成的单词、收藏、id 都一样。
"""
import json, math, os, shutil, sys, uuid, random, struct, wave, io
from datetime import datetime, timedelta

if len(sys.argv) != 2:
    sys.exit('用法：python3 make_fake_data.py <沙盒目录>')
root = sys.argv[1]
random.seed(7)
_ids = random.Random(20261031)  # id 单独一个随机源，不影响上面选词的顺序


def new_id():
    return str(uuid.UUID(int=_ids.getrandbits(128), version=4))

WORDS = """
abundant|adj. 丰富的，充裕的
accommodation|n. 住处，膳宿
acquire|v. 获得，习得
adjacent|adj. 邻近的
allocate|v. 分配，拨出
ambiguous|adj. 模棱两可的
anticipate|v. 预期，预料
apparatus|n. 器械，装置
approximately|adv. 大约
aquatic|adj. 水生的
arid|adj. 干旱的
artificial|adj. 人造的，人工的
assess|v. 评估，评定
attain|v. 达到，获得
autonomous|adj. 自主的，自治的
barren|adj. 贫瘠的
beneficial|adj. 有益的
biodiversity|n. 生物多样性
boost|v. 促进，提高
breakthrough|n. 突破
budget|n. 预算
bulletin|n. 公告，简报
canteen|n. 食堂
catastrophe|n. 灾难
cease|v. 停止
circulate|v. 循环，传播
coincide|v. 同时发生，相符
collaborate|v. 合作
commute|v. 通勤
compensate|v. 补偿，弥补
comprehensive|adj. 全面的，综合的
compulsory|adj. 强制的，义务的
concession|n. 让步；优惠
consecutive|adj. 连续的
conserve|v. 保护，节约
constrain|v. 限制，约束
contaminate|v. 污染
controversial|adj. 有争议的
convention|n. 惯例；大会
crucial|adj. 至关重要的
cultivate|v. 培养；耕种
curriculum|n. 课程
decline|v./n. 下降，衰退
deduct|v. 扣除
deficiency|n. 缺乏，不足
deforestation|n. 森林砍伐
deposit|n. 押金；沉积物
deteriorate|v. 恶化
diminish|v. 减少，缩小
disposal|n. 处理，处置
distinguish|v. 区分，辨别
domestic|adj. 国内的；家庭的
dominant|adj. 占优势的
drought|n. 干旱
durable|adj. 耐用的
ecosystem|n. 生态系统
eliminate|v. 消除，淘汰
emission|n. 排放
enrol|v. 注册，入学
erode|v. 侵蚀
exceed|v. 超过
excursion|n. 远足，短途旅行
exhibit|v./n. 展出；展品
expand|v. 扩大，扩张
extinct|adj. 灭绝的
facilitate|v. 促进，使便利
feasible|adj. 可行的
fertile|adj. 肥沃的
fluctuate|v. 波动
forecast|n./v. 预报，预测
fragile|adj. 易碎的，脆弱的
fundamental|adj. 基本的，根本的
habitat|n. 栖息地
hazard|n. 危险
hemisphere|n. 半球
humid|adj. 潮湿的
hypothesis|n. 假设
identical|adj. 完全相同的
immerse|v. 沉浸
implement|v. 实施，执行
incentive|n. 激励，奖励
indigenous|adj. 本土的，土著的
inevitable|adj. 不可避免的
infrastructure|n. 基础设施
inhabitant|n. 居民
innovative|adj. 创新的
insulation|n. 隔热，绝缘
intensive|adj. 密集的，集中的
irrigation|n. 灌溉
landfill|n. 垃圾填埋场
legislation|n. 立法，法律
leisure|n. 闲暇，休闲
lecture|n. 讲座
likewise|adv. 同样地
literacy|n. 读写能力
maintenance|n. 维护，保养
mandatory|adj. 强制的
migrate|v. 迁徙，移居
minimise|v. 使减到最少
modify|v. 修改，调整
monitor|v. 监测
negligible|adj. 可以忽略的
nutrition|n. 营养
obsolete|adj. 过时的，淘汰的
occupation|n. 职业
optimal|adj. 最佳的
orientation|n. 方向；新生培训
outweigh|v. 比……重要
overwhelm|v. 压倒，使不知所措
parallel|adj. 平行的；类似的
participant|n. 参与者
pedestrian|n. 行人
perceive|v. 察觉，认为
permanent|adj. 永久的
pesticide|n. 杀虫剂
phenomenon|n. 现象
portable|adj. 便携的
precipitation|n. 降水
predator|n. 捕食者
preliminary|adj. 初步的
prevalent|adj. 普遍的，流行的
prior|adj. 先前的
productivity|n. 生产率
prohibit|v. 禁止
prominent|adj. 显著的，著名的
prospect|n. 前景
questionnaire|n. 调查问卷
radical|adj. 根本的；激进的
receptionist|n. 前台接待员
recruit|v. 招募
refund|n./v. 退款
regulate|v. 管理，调节
reinforce|v. 加强，巩固
relevant|adj. 相关的
reliable|adj. 可靠的
renewable|adj. 可再生的
reservoir|n. 水库
resilient|adj. 有弹性的，适应力强的
restore|v. 恢复，修复
retain|v. 保留
revenue|n. 收入，税收
rigorous|adj. 严格的
scarce|adj. 稀缺的
schedule|n. 时间表
sediment|n. 沉积物
seminar|n. 研讨会
sophisticated|adj. 复杂的，精密的
specimen|n. 样本，标本
stimulate|v. 刺激，激发
substantial|adj. 大量的，可观的
subsidy|n. 补贴
sufficient|adj. 足够的
surplus|n. 过剩，盈余
sustainable|adj. 可持续的
symptom|n. 症状
terrain|n. 地形
thermal|adj. 热的
transition|n. 过渡，转变
transmit|v. 传输，传播
tuition|n. 学费；教学
undergo|v. 经历，经受
utilise|v. 利用
vacancy|n. 空缺；空房
vegetation|n. 植被
ventilation|n. 通风
versatile|adj. 多才多艺的，多用途的
vulnerable|adj. 脆弱的，易受伤害的
warehouse|n. 仓库
wildlife|n. 野生动物
withdraw|v. 撤回，提取
""".strip().splitlines()
WORDS = [w.split('|') for w in WORDS]

SPEAKING = """
cosy|adj. 舒适温馨的
hectic|adj. 忙乱的
laid-back|adj. 悠闲的，放松的
bustling|adj. 熙熙攘攘的
unwind|v. 放松
catch up with|赶上；叙旧
off the beaten track|人迹罕至的
a breath of fresh air|令人耳目一新的人或事
once in a blue moon|难得一次
hit the road|出发，上路
breathtaking|adj. 令人惊叹的
nostalgic|adj. 怀旧的
""".strip().splitlines()
SPEAKING = [w.split('|') for w in SPEAKING]

WRITING = """
plummet|v. 骤降
soar|v. 猛增
fluctuate|v. 波动
remain stable|保持稳定
peak at|在……达到峰值
marginally|adv. 略微地
dramatically|adv. 急剧地
steadily|adv. 稳步地
""".strip().splitlines()
WRITING = [w.split('|') for w in WRITING]

base = datetime(2026, 9, 1, 9, 0, 0)

def mk_words(pairs, fav_every=0, noaudio=(), start_day=0):
    out = []
    for i, (w, m) in enumerate(pairs):
        out.append({
            'id': new_id(),
            'word': w,
            'meaning': m,
            'created_at': (base + timedelta(days=start_day + i // 6, minutes=i * 7)).isoformat(),
            'audio_generated': i not in noaudio,
            'is_favorited': bool(fav_every) and i % fav_every == 0,
        })
    return out

def sub(name, words, day):
    return {'name': name, 'created_at': (base + timedelta(days=day)).isoformat(), 'words': words}

pool = WORDS[:]
random.shuffle(pool)
cats = {
    'listening': {
        'default': sub('默认分类', mk_words(pool[:6]), 0),
        new_id(): sub('Part 1 拼写易错词', mk_words(pool[6:30], fav_every=4), 1),
        new_id(): sub('Part 3 学术场景', mk_words(pool[30:44], fav_every=5, noaudio={0, 3}), 3),
        new_id(): sub('地图题方位词', [], 5),
        new_id(): sub('不熟悉词汇', mk_words(pool[44:160], fav_every=3, noaudio={1}), 2),
    },
    'speaking': {
        'default': sub('默认分类', mk_words(SPEAKING[:4]), 0),
        new_id(): sub('Part 2 地点描述', mk_words(SPEAKING[4:], fav_every=3), 2),
        new_id(): sub('Part 1 爱好', [], 4),
    },
    'reading': {
        'default': sub('默认分类', [], 0),
        **{new_id(): sub(f'Chapter{n} {t}', mk_words(random.sample(WORDS, k), fav_every=f), n)
           for n, t, k, f in [(1, '自然地理', 40, 4), (2, '植物研究', 22, 0), (10, '物品材料', 18, 0),
                              (3, '动物保护', 26, 6), (11, '时尚潮流', 12, 0)]},
        new_id(): sub('[同义替换] 动词', mk_words(random.sample(WORDS, 15), fav_every=2), 12),
    },
    'writing': {
        'default': sub('默认分类', mk_words([('notwithstanding', '')]), 0),
        new_id(): sub('[小作文] 趋势动词', mk_words(WRITING, fav_every=4), 1),
    },
}

vb = os.path.join(root, 'vocabulary_book')
shutil.rmtree(vb, ignore_errors=True)
for d in ['categories', 'tasks', 'challenges'] + [f'audio/{c}' for c in cats]:
    os.makedirs(os.path.join(vb, d), exist_ok=True)

icons = {"listening": "🎧", "speaking": "🗣️", "reading": "📖", "writing": "✍️"}
now = datetime(2026, 10, 30).isoformat()

# 0.35s 440Hz tone, saved with an .mp3 name (browsers sniff the WAV header)
buf = io.BytesIO()
with wave.open(buf, 'wb') as wf:
    wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(16000)
    wf.writeframes(b''.join(struct.pack('<h', int(6000 * math.sin(2 * math.pi * 440 * t / 16000))) for t in range(5600)))
tone = buf.getvalue()

coverage = {}
for c, subs in cats.items():
    with open(os.path.join(vb, 'categories', f'{c}.json'), 'w', encoding='utf-8') as f:
        json.dump({'name': c.capitalize(), 'icon': icons[c], 'subcategories': subs,
                   'metadata': {'created_at': base.isoformat(), 'last_updated': now}}, f, ensure_ascii=False, indent=2)
    for s in subs.values():
        for i, w in enumerate(s['words']):
            if w['audio_generated']:
                open(os.path.join(vb, 'audio', c, f"{w['id']}.mp3"), 'wb').write(tone)
            if i % 2 == 0:
                coverage[w['id']] = {'appear_count': 1 + i % 3, 'last_appeared': '2026-10-20T10:00:00'}

with open(os.path.join(vb, 'challenges', 'demo.json'), 'w', encoding='utf-8') as f:
    json.dump({'word_coverage': coverage,
               'challenge_stats': {'total_challenges': 6, 'total_correct': 41, 'total_questions': 60, 'last_challenge': '2026-10-20T10:00:00'},
               'metadata': {'created_at': base.isoformat(), 'last_updated': now}}, f, ensure_ascii=False, indent=2)

with open(os.path.join(root, 'users.json'), 'w', encoding='utf-8') as f:
    json.dump({'demo': {'username': 'demo', 'password': 'not-a-real-password', 'display_name': '演示用户',
                        'avatar': '/static/avatar_teacher.svg', 'role': 'user', 'created_at': base.isoformat()}},
              f, ensure_ascii=False, indent=2)
with open(os.path.join(root, 'tokens.json'), 'w', encoding='utf-8') as f:
    json.dump({}, f)
pristine = os.path.join(root, 'vocabulary_book.pristine')
shutil.rmtree(pristine, ignore_errors=True)
shutil.copytree(vb, pristine)
print('ok', {c: sum(len(s['words']) for s in subs.values()) for c, subs in cats.items()})

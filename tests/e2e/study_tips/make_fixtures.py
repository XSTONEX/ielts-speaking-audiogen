"""给学习技巧浏览器测试的沙盒写一份编造的数据（没有任何真实用户内容）。

用法：python3 make_fixtures.py <沙盒目录> [--mint-token]
  写 <沙盒>/study_techniques/data/*.json 和 <沙盒>/users.json（测试账号 demo）。
  --mint-token 再用沙盒里的 core.create_token 给 demo 发一个 token，存到 <沙盒>/e2e_token.txt；
  这一步要导入应用代码，得用装好依赖的 Python（项目的 .venv）。只生成数据用系统 python3 就行。
沙盒怎么建见同目录 README.md。会覆盖沙盒里这些文件，所以拒绝对真实仓库运行。
"""
import argparse, json, os, sys, uuid
from datetime import datetime, timedelta

MARKER = '.study_tips_e2e_sandbox'

parser = argparse.ArgumentParser(description='生成学习技巧的编造数据')
parser.add_argument('root', help='沙盒目录（代码的副本，不是仓库本身）')
parser.add_argument('--mint-token', action='store_true', help='顺便给 demo 发一个登录 token，写到 <沙盒>/e2e_token.txt')
args = parser.parse_args()
root = os.path.abspath(args.root)

# 会整份覆盖用户和学习技巧数据：有 .git 的是真实仓库，有数据却没有沙盒标记的也不碰
if os.path.exists(os.path.join(root, '.git')):
    sys.exit(f'{root} 里有 .git，像是真实仓库而不是沙盒，不写')
has_data = os.path.exists(os.path.join(root, 'users.json')) or os.path.isdir(os.path.join(root, 'study_techniques', 'data'))
if has_data and not os.path.exists(os.path.join(root, MARKER)):
    sys.exit(f'{root} 里已经有 users.json 或学习技巧数据，又没有沙盒标记 {MARKER}，不写')
open(os.path.join(root, MARKER), 'w').close()

d = os.path.join(root, 'study_techniques', 'data')
os.makedirs(d, exist_ok=True)
os.makedirs(os.path.join(root, 'study_techniques', 'audio'), exist_ok=True)

base = datetime(2026, 9, 1, 9, 0, 0)
counter = [0]


def stamp():
    counter[0] += 1
    t = base + timedelta(days=counter[0], minutes=counter[0] * 7)
    return t.isoformat()


def W(pairs):
    return [{'word': w, 'definition': dfn} for w, dfn in pairs]


def syn(title, pairs):
    t = stamp()
    e = {'id': str(uuid.uuid4()), 'synonyms': W(pairs), 'created_at': t, 'updated_at': t}
    if title:
        e['title'] = title
    return e


def hyp(title, upper, lower):
    t = stamp()
    e = {'id': str(uuid.uuid4()), 'upper_words': W(upper), 'lower_words': W(lower), 'created_at': t, 'updated_at': t}
    if title:
        e['title'] = title
    return e


def tech(title, content):
    t = stamp()
    return {'id': str(uuid.uuid4()), 'title': title, 'content': content, 'created_at': t, 'updated_at': t}


reading_syn = [
    syn('增长 / 上升', [('increase', '增加'), ('rise', '上升'), ('grow', '增长'), ('climb', '攀升'), ('surge', '激增'), ('soar', '飙升')]),
    syn('重要的', [('important', '重要的'), ('crucial', '关键的'), ('vital', '至关重要的'), ('essential', '必不可少的'), ('significant', '显著的')]),
    syn('导致', [('cause', '导致'), ('lead to', '引起'), ('result in', '造成'), ('give rise to', '引发'), ('trigger', '触发')]),
    syn('古老的', [('ancient', '古代的'), ('antique', '古董的'), ('prehistoric', '史前的'), ('archaic', '古老的')]),
    syn('证明', [('prove', '证明'), ('demonstrate', '论证'), ('confirm', '证实'), ('verify', '核实'), ('validate', '验证'), ('establish', '确立'), ('show', '表明')]),
    syn('困难', [('difficulty', '困难'), ('obstacle', '障碍'), ('challenge', '挑战'), ('hurdle', '难关'), ('setback', '挫折')]),
    syn('', [('reduce', '减少'), ('decline', '下降'), ('diminish', '减小'), ('shrink', '缩小')]),
    syn('研究者', [('researcher', '研究者'), ('scientist', '科学家'), ('scholar', '学者'), ('investigator', '调查者'), ('academic', '学术人员'), ('expert', '专家'), ('specialist', '专业人员'), ('analyst', '分析员'), ('team', '团队')]),
    syn('迅速地', [('quickly', '快速地'), ('rapidly', '迅速地'), ('swiftly', '敏捷地'), ('promptly', '立即')]),
    syn('传统', [('tradition', '传统'), ('custom', '习俗'), ('convention', '惯例'), ('heritage', '遗产')]),
    syn('方法', [('method', '方法'), ('approach', '途径'), ('technique', '技巧'), ('strategy', '策略'), ('means', '手段')]),
    syn('相似的', [('similar', '相似的'), ('comparable', '可比的'), ('alike', '相像的'), ('analogous', '类似的')]),
]
listening_syn = [
    syn('预订', [('book', '预订'), ('reserve', '保留'), ('make a reservation', '订位')]),
    syn('便宜', [('cheap', '便宜的'), ('affordable', '负担得起的'), ('inexpensive', '不贵的'), ('reasonable', '合理的')]),
    syn('不可以', [('not allowed', '不允许'), ('prohibited', '禁止的'), ('forbidden', '被禁止的')]),
    syn('附近', [('nearby', '附近的'), ('close to', '靠近'), ('within walking distance', '步行可达')]),
    syn('报名', [('sign up', '报名'), ('register', '注册'), ('enrol', '登记入学'), ('join', '加入')]),
]
writing_syn = [
    syn('认为', [('think', '认为'), ('believe', '相信'), ('argue', '主张'), ('contend', '声称'), ('maintain', '坚持认为')]),
    syn('问题', [('problem', '问题'), ('issue', '议题'), ('concern', '关注的问题'), ('challenge', '挑战')]),
    syn('有益', [('beneficial', '有益的'), ('advantageous', '有利的'), ('rewarding', '有回报的')]),
]
speaking_syn = [
    syn('喜欢', [('like', '喜欢'), ('be into', '热衷于'), ('be keen on', '着迷于'), ('be fond of', '喜爱')]),
]

reading_hyp = [
    hyp('交通工具', [('transport', '交通')], [('car', '汽车'), ('bus', '公交'), ('train', '火车'), ('tram', '有轨电车'), ('ferry', '渡轮'), ('bicycle', '自行车')]),
    hyp('动物', [('animal', '动物'), ('creature', '生物')], [('mammal', '哺乳动物'), ('reptile', '爬行动物'), ('bird', '鸟类'), ('insect', '昆虫')]),
    hyp('能源', [('energy', '能源')], [('solar power', '太阳能'), ('wind power', '风能'), ('coal', '煤'), ('natural gas', '天然气'), ('nuclear power', '核能')]),
    hyp('乐器', [('musical instrument', '乐器')], [('violin', '小提琴'), ('piano', '钢琴'), ('flute', '长笛')]),
    hyp('灾害', [('natural disaster', '自然灾害')], [('flood', '洪水'), ('drought', '干旱'), ('earthquake', '地震'), ('hurricane', '飓风'), ('wildfire', '野火')]),
    hyp('', [('vegetation', '植被')], [('tree', '树'), ('shrub', '灌木'), ('grass', '草')]),
    hyp('建筑材料', [('building material', '建材')], [('brick', '砖'), ('timber', '木材'), ('concrete', '混凝土'), ('steel', '钢'), ('glass', '玻璃')]),
    hyp('只有下义词', [], [('salmon', '三文鱼'), ('tuna', '金枪鱼'), ('cod', '鳕鱼')]),
]
listening_hyp = [
    hyp('住宿', [('accommodation', '住宿')], [('hostel', '青旅'), ('hotel', '酒店'), ('flat', '公寓'), ('homestay', '寄宿家庭')]),
]

LONG_WRITING = """# 大作文：论证块写法

先想清楚一句话的立场，再用「原因 → 机制 → 结果」三步把它撑起来。下面每一节都是一种常用论证块。

## 一、因果链

因果链是最稳的论证方式：每一步都要能被追问「为什么」。

### 1. 三步展开

1. **原因**：点出驱动因素，例如 rising living costs。
2. **机制**：解释它如何起作用，例如 people delay buying homes。
3. **结果**：落到题目关心的影响上，例如 lower birth rates in cities。

> 提示：机制这一步最容易被省略，但考官最看重的就是它。

### 2. 常用连接

| 作用 | 表达 | 例句片段 |
| --- | --- | --- |
| 引出原因 | owing to / stem from | stem from a lack of funding |
| 推出结果 | thereby / consequently | thereby reducing traffic |
| 加强 | not only… but also… | not only cheaper but also cleaner |

#### 易错点

- 不要连用三个 *because*。
- ==结果句要回扣题目关键词==，否则容易跑题。
- 一段只写一条链，别贪多。

## 二、对比论证

对比的核心是「同一维度」：比较两种做法在成本、效率、公平这类同一标准上的差异。

### 1. 结构

先写对方观点的合理之处，再用 ++however++ 转到自己的立场，最后给出取舍理由。

<div STYLE="page-break-after:always;"></div>

### 2. 示例段落

```
While public transport is often slower than driving, it carries far more
people per lane, which makes it the only realistic option for dense cities.
```

#### 自查清单

- [ ] 两边是否用了同一个比较标准
- [ ] 让步句是否只有一句
- [ ] 结论是否明确选边

## 三、举例论证

例子要具体到可以想象：时间、地点、人群三选二即可。

### 1. 例子来源

- 个人经历（小作文慎用）
- 公共政策：congestion charges in large cities
- 科技产品：ride-sharing apps

### 2. 写法

把例子放在机制之后，用 *for instance* 引出，一两句即可，最后一句回到论点。

---

## 四、结尾段

结尾只做两件事：重申立场、点出最重要的理由。不要引入新论据。

### 1. 模板

In conclusion, although X has some merits, I firmly believe that Y, mainly because Z.

### 2. 字数

结尾控制在 40–60 词。
"""

READING_TECH = """# 判断题（T / F / NG）

## 先读题，圈定位词

人名、地名、数字、大写词最好找。把题干里**最具体**的词圈出来。

## 同义替换

原文几乎不会照抄题干，常见替换见「词汇替换」页。

## NG 的三种情况

1. 原文没提到这个对象
2. 原文提到对象但没提这个比较
3. 原文只说可能，题干说一定

## 时间分配

13 题控制在 18 分钟内，卡住就先跳过。
"""

SPEAKING_TECH = """### Part 2 一分钟准备

#### 先定时间线

过去 → 现在 → 将来，三段各说 40 秒。

#### 关键词卡

只写 5 个英文关键词，不写句子。

##### 示例

- old bookshop
- rainy afternoon
- recommended by a friend
- still visit
- quiet place

#### 收尾

用一句感受收尾：It's one of those places I'll always come back to.
"""

listening_tech = [tech('填空题先看词性', '#### 看空格前后\n\n判断要填名词、动词还是数字。\n\n#### 注意单复数\n\n听到 -s 要写上。\n\n#### 拼写\n\n常考月份和星期，平时就要写对。')]
reading_tech = [tech('判断题三步法', READING_TECH), tech('段落信息匹配', '## 先看段落首句\n\n首句往往概括全段。\n\n## 抓细节\n\n题干里的例子、数据、原因，在原文里通常只出现一次。')]
writing_tech = [tech('大作文论证块', LONG_WRITING), tech('小作文：线图描述', '# 线图\n\n## 开头段\n\n改写题目，一句话。\n\n## 概述段\n\n写**两个**最明显的趋势。\n\n## 细节段\n\n按时间或按对象分组。'),
    # 这两篇的时间带 6 位微秒，和后端 datetime.now().isoformat() 存下来的格式一样
    {'id': str(uuid.uuid4()), 'title': '小作文：饼图', 'created_at': '2026-10-08T20:15:42.381920', 'updated_at': '2026-10-08T20:15:42.381920',
     'content': '# 饼图\n\n先比大小，再说占比：概述段只写最大和最小的两块，细节段按「大 → 中 → 小」分组，数字写成百分比或分数二选一。\n\n## 概述段\n\n- 最大的一块\n- 最小的一块\n\n## 细节段\n\n### 大块\n\naccounts for / makes up\n\n### 小块\n\nonly a fraction of'},
    {'id': str(uuid.uuid4()), 'title': '开头段改写', 'created_at': '2026-10-09T08:02:11.004512', 'updated_at': '2026-10-09T08:02:11.004512',
     'content': '同义替换加语序调整，两句话写完开头段：第一句改写题目背景，第二句亮明立场，不要照抄题目里的任何一个短语。\n\n## 第一句：改写背景\n\n换词 + 换句型。\n\n## 第二句：立场\n\nThis essay argues that…\n\n## 常见错误\n\n照抄题目原句。\n\n## 字数\n\n40 词左右。'},
]
speaking_tech = [tech('Part 2 一分钟准备', SPEAKING_TECH)]

files = {
    'reading_synonyms': reading_syn, 'listening_synonyms': listening_syn,
    'writing_synonyms': writing_syn, 'speaking_synonyms': speaking_syn,
    'reading_hypernyms': reading_hyp, 'listening_hypernyms': listening_hyp,
    'writing_hypernyms': [], 'speaking_hypernyms': [],
    'listening_techniques': listening_tech, 'reading_techniques': reading_tech,
    'writing_techniques': writing_tech, 'speaking_techniques': speaking_tech,
}
for name, data in files.items():
    with open(os.path.join(d, name + '.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

users = {
    'demo': {'username': 'demo', 'password': 'demo-pass-not-real', 'display_name': '测试同学',
             'avatar': 'avatar_teacher.svg', 'role': 'user', 'created_at': '2026-09-01T00:00:00'}
}
with open(os.path.join(root, 'users.json'), 'w', encoding='utf-8') as f:
    json.dump(users, f, ensure_ascii=False, indent=2)

if args.mint_token:
    # core 用相对路径读写 tokens.json，要在沙盒目录里导入
    os.chdir(root)
    sys.path.insert(0, root)
    import core  # noqa: E402
    with open(os.path.join(root, 'e2e_token.txt'), 'w', encoding='utf-8') as f:
        f.write(core.create_token('demo') + '\n')
print('ok')

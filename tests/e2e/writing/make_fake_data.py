"""给写作逻辑训练页（/writing_practice）的浏览器测试搭一份编造的数据。

用法：python make_fake_data.py <沙盒目录>
沙盒目录是仓库代码的一份拷贝（git ls-files -co --exclude-standard 复制过去的），绝不能是仓库本身：
这里会整个删掉重写 writing_correction/，并覆盖 users.json / tokens.json。每次跑都会恢复成同样的初始状态
（记录 id 固定，时间戳按「现在往前推几天」算）。
要用仓库的 .venv 跑：写 token 时会 import 沙盒里的 core.py（要有 flask），画题图要有 Pillow。

造出来的东西：
- 大作文思维链语料（九分学长雅思写作论证块.md）：人群 / 科技两个话题，5 个子类，11 道例题
- 小作文仿写语料（小作文仿写.md）：折线图 2 道（都配了题图）、柱状图 1 道、流程图 1 道（没有题图）
- 模板写作语料（写作模板.json）：观点型 / 讨论型两个大作文题型 + 总结构等参考资料；
  数据图 / 流程图 / 地图题三种小作文图表的句型库（地图题没有例题）
- 用户 linxia「林夏」的练习记录（全都收进复习中心）、速记本、一段 AI 助手聊天记录
- 登录凭证写到 <沙盒目录>/_e2e/tokens.json：{"linxia": {"token": ..., "user": {...}}}

所有题目、句子、人名、数字都是编的；仓库是公开的，不要换成真实语料或真实练习记录。
"""
import json
import os
import re
import shutil
import sys
import uuid
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

NOW = datetime.now()
RES = 'writing_correction/resource'
DATA = 'writing_correction/data'
IMAGES = 'writing_correction/images'


def ago(days=0, hours=0, minutes=0):
    return (NOW - timedelta(days=days, hours=hours, minutes=minutes)).isoformat()


def ms(iso):
    """页面里的 _gradedAt 是毫秒时间戳。"""
    return int(datetime.fromisoformat(iso).timestamp() * 1000)


def fixed_id(name):
    """记录 id 和线上一样是 uuid 的样子，但每次跑都一样，测试可以直接按 id 找。"""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, 'e2e-writing/' + name))


def dump(path, obj):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def write_text(path, text):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)


# ---- 清掉上一轮测试留下的东西（高亮、追问、上传的题图都在 writing_correction 里） ----
shutil.rmtree('writing_correction', ignore_errors=True)

users = {
    'linxia': {'username': 'linxia', 'password': 'test-only', 'display_name': '林夏',
               'avatar': 'avatar_admin.svg', 'role': 'user', 'created_at': '2026-01-01T09:00:00'},
}
dump('users.json', users)
dump('tokens.json', {})


# =====================================================================
# 大作文思维链：话题 → 子类 → 关键词 / 逻辑链 / 例题（每题 4 句中英对照）
# 题目可以拆成几行写，解析时用空格拼起来（练习记录里的 question 也按拼好的存）
# =====================================================================
BIG = [
    {'name': '人群', 'subs': [
        {'name': '老年人',
         'keywords': ['the elderly / senior citizens', 'retirement', 'social isolation'],
         'chains': [
             ('退休后社交变少 → 容易孤独 → 影响身心健康',
              'After retirement, older people have fewer social contacts, which can lead to loneliness and poorer health.'),
             ('和子女同住 → 有人照顾和陪伴 → 生活质量更高',
              'Living with their children means older people receive care and company, so their quality of life improves.'),
             ('学习新技能 → 保持大脑活跃 → 延缓衰老',
              'Learning new skills keeps the brain active and may slow down the effects of ageing.'),
         ],
         'examples': [
             {'q': ('Some people think that elderly people should live with their adult children rather than in care homes.',
                    'To what extent do you agree or disagree?'),
              'use': '和子女同住 → 有人照顾和陪伴 → 生活质量更高',
              'write': '先写陪伴，再写照顾，最后补一句对子女的好处',
              'sents': [
                  ('When older people live with their children, they are rarely left alone for long periods.',
                   '老年人和子女同住时，很少会长时间独处。'),
                  ('Family members can notice small health problems early and take them to see a doctor.',
                   '家人能及早发现小的健康问题，并带他们去看医生。'),
                  # 故意写长（约 40 词），看换行
                  ('In addition, grandparents who share a home with their grandchildren often help with cooking, homework and school pick-ups, which gives them a sense of purpose and allows busy working parents to spend less money on childcare every single month.',
                   '此外，和孙辈同住的祖父母常常帮忙做饭、辅导作业、接送孩子，这让他们觉得自己有用，也让忙碌的双职工父母每个月少花一些托育费。'),
                  ('As a result, the whole family benefits from this arrangement.',
                   '因此，整个家庭都能从这种安排中受益。'),
              ]},
             {'q': ('In many countries, the number of people over 65 is growing. What problems does this cause, and what can be done to solve them?',),
              # 「使用」只写了链的前半截，页面要能靠箭头左边对上链 1
              'use': '退休后社交变少 → 容易孤独',
              'write': '问题写孤独，对策写社区活动',
              'sents': [
                  ('Many retired people spend most of the day at home with nobody to talk to.',
                   '很多退休老人一天中的大部分时间都待在家里，没有人说话。'),
                  ('Over time, this loneliness can lead to depression and other health problems.',
                   '久而久之，这种孤独可能导致抑郁和其他健康问题。'),
                  ('Local governments could open community centres where older residents can meet and take part in activities.',
                   '地方政府可以开设社区中心，让老年居民聚在一起参加活动。'),
                  ('Such places would help them stay connected with society.',
                   '这样的地方能帮助他们和社会保持联系。'),
              ]},
             {'q': ('Some people believe that older people should be encouraged to learn new technology.',
                    'Do the advantages of this outweigh the disadvantages?'),
              'use': '学习新技能 → 保持大脑活跃 → 延缓衰老',
              'write': '优点写大脑和联系家人，缺点一句带过',
              'sents': [
                  ('Learning to use a smartphone can be a real challenge for people in their seventies.',
                   '对七十多岁的人来说，学用智能手机可能是一个真正的挑战。'),
                  ('However, this kind of learning keeps their minds active.',
                   '不过，这类学习能让他们的大脑保持活跃。'),
                  ('They can also make video calls to relatives who live far away.',
                   '他们还可以和住在远方的亲戚视频通话。'),
                  ('Therefore, I believe the benefits clearly outweigh the drawbacks.',
                   '因此，我认为好处明显大于坏处。'),
              ]},
         ]},
        {'name': '儿童',
         'keywords': ['screen time', 'outdoor activities', 'parental guidance'],
         'chains': [
             ('孩子自控力弱 → 容易沉迷屏幕 → 需要家长引导',
              'Children have weak self-control, so they can easily become addicted to screens and need guidance from parents.'),
             ('户外活动多 → 身体更健康 → 也更会交朋友',
              'Spending more time outdoors makes children healthier and helps them make friends.'),
             ('从小做家务 → 培养责任感',
              'Doing housework from an early age helps children develop a sense of responsibility.'),
         ],
         'examples': [
             {'q': ('Children today spend too much time on electronic devices.',
                    'What are the causes of this, and what can parents do about it?'),
              'use': '孩子自控力弱 → 容易沉迷屏幕 → 需要家长引导',
              'write': '原因一句，对策两句',
              'sents': [
                  ('Young children find it hard to stop watching videos once they start.',
                   '年幼的孩子一旦开始看视频，就很难停下来。'),
                  ('Many parents also hand a tablet to their child to keep them quiet.',
                   '很多家长也会把平板电脑递给孩子，好让他们安静下来。'),
                  ('Parents should set clear rules about when and where devices can be used.',
                   '家长应该明确规定什么时候、在哪里可以使用电子设备。'),
                  ('They could also plan screen-free activities at weekends.',
                   '他们也可以在周末安排不碰屏幕的活动。'),
              ]},
             {'q': ('Some people think children should spend more time playing outside than studying at home. To what extent do you agree or disagree?',),
              'use': '户外活动多 → 身体更健康 → 也更会交朋友',
              'write': '先让步承认学习重要',
              'sents': [
                  # 带撇号，看转义
                  ("Studying at home is important, but it should not take up a child's whole afternoon.",
                   '在家学习很重要，但不应该占据孩子的整个下午。'),
                  ('Children who play outside every day are usually fitter and sleep better.',
                   '每天在户外玩耍的孩子通常更健康，睡得也更好。'),
                  ('Team games such as football also teach them how to share and take turns.',
                   '足球这样的团队游戏还能教会他们分享和轮流。'),
                  ('For these reasons, outdoor play deserves a bigger place in the daily lives of children.',
                   '因此，户外玩耍应该在孩子的日常生活中占更大的比重。'),
              ]},
         ]},
        {'name': '大学生',
         'keywords': ['tuition fees', 'part-time jobs', 'practical skills'],
         'chains': [
             ('兼职 → 积累工作经验 → 更容易找工作',
              'Part-time work gives students experience, which makes it easier for them to find a job after graduation.'),
             ('学费太高 → 学生负债 → 不敢选喜欢的专业',
              'High tuition fees leave students in debt, so some of them avoid subjects they really enjoy.'),
             ('大学只教理论 → 缺少实践 → 毕业后不适应工作',
              'If universities only teach theory, graduates may struggle to adapt to real work.'),
         ],
         'examples': [
             {'q': ('Many university students work part-time while studying. Is this a positive or negative development?',),
              'use': '兼职 → 积累工作经验 → 更容易找工作',
              'write': '正面为主，最后提醒别影响学业',
              'sents': [
                  ('A part-time job in a shop or café teaches students how to deal with customers.',
                   '在商店或咖啡馆兼职能教会学生如何和顾客打交道。'),
                  ('These skills look good on a CV when they apply for full-time jobs.',
                   '他们申请全职工作时，这些技能会让简历更好看。'),
                  ('Students who earn their own money also learn to manage a budget.',
                   '自己挣钱的学生还能学会管理开支。'),
                  ('However, they should not work so many hours that their grades suffer.',
                   '不过，他们打工的时间不应该长到影响成绩。'),
              ]},
             {'q': ('Some people think university education should be free for all students. To what extent do you agree or disagree?',),
              'use': '学费太高 → 学生负债 → 不敢选喜欢的专业',
              'write': '用一个具体专业举例',
              'sents': [
                  ('In some countries, students leave university with very large debts.',
                   '在一些国家，学生毕业时背着很重的债务。'),
                  ('As a result, they may choose a well-paid subject instead of one they love.',
                   '结果，他们可能会选择一个收入高的专业，而不是自己喜欢的专业。'),
                  ('For example, a student who enjoys history might study accounting simply to repay a loan.',
                   '比如，一个喜欢历史的学生可能仅仅为了还贷而去学会计。'),
                  ('Free education would allow young people to follow their real interests.',
                   '免费教育能让年轻人追随自己真正的兴趣。'),
              ]},
         ]},
    ]},
    {'name': '科技', 'subs': [
        {'name': '网络学习',
         'keywords': ['online courses', 'flexibility', 'self-discipline'],
         'chains': [
             ('网课时间灵活 → 上班族也能学习',
              'Online courses are flexible, so people with full-time jobs can still study.'),
             ('缺少面对面交流 → 学习动力下降',
              'Without face-to-face contact, learners may lose motivation.'),
             ('网上资源丰富 → 偏远地区学生也能学到好课',
              'There are plenty of resources online, so students in remote areas can also access good courses.'),
         ],
         'examples': [
             {'q': ('More and more people are choosing to study online rather than at a traditional school.',
                    'Do the advantages outweigh the disadvantages?'),
              'use': '网课时间灵活 → 上班族也能学习',
              'write': '优点两句，缺点一句，结论一句',
              'sents': [
                  ('Online learners can watch lessons at any time of day.',
                   '网上学习的人可以在一天中的任何时间看课程。'),
                  ('This makes it possible for nurses and drivers who work night shifts to earn a degree.',
                   '这让上夜班的护士和司机也有可能拿到学位。'),
                  ('On the other hand, studying alone at home requires a lot of self-discipline.',
                   '另一方面，一个人在家学习需要很强的自律。'),
                  ('Overall, I think the flexibility of online study is a major advantage.',
                   '总的来说，我认为网上学习的灵活性是一个很大的优势。'),
              ]},
             {'q': ('Some people think online learning will replace classroom teaching in the future. To what extent do you agree or disagree?',),
              'use': '缺少面对面交流 → 学习动力下降',
              'write': '反对为主',
              'sents': [
                  ('Many students find it hard to stay focused in front of a screen for hours.',
                   '很多学生觉得在屏幕前连续几个小时很难集中注意力。'),
                  ('In a classroom, teachers can see at once when someone is confused.',
                   '在教室里，老师能立刻看出谁没听懂。'),
                  ('Classmates also motivate each other to keep up with their work.',
                   '同学之间也会互相督促，跟上进度。'),
                  ('For this reason, I do not believe screens will ever fully replace teachers.',
                   '因此，我不认为屏幕会完全取代老师。'),
              ]},
         ]},
        {'name': '人工智能',
         'keywords': ['artificial intelligence', 'automation', 'job market'],
         'chains': [
             ('机器取代重复劳动 → 部分岗位消失 → 需要再培训',
              'Machines are replacing repetitive work, so some jobs will disappear and workers will need retraining.'),
             ('AI 处理数据快 → 医生更早发现疾病',
              'AI can process data quickly, which helps doctors detect diseases earlier.'),
             ('过度依赖 AI → 独立思考能力下降',
              'Relying too much on AI may weaken our ability to think for ourselves.'),
         ],
         'examples': [
             {'q': ('Artificial intelligence is expected to take over many jobs in the future.',
                    'What problems might this cause, and how can they be solved?'),
              'use': '机器取代重复劳动 → 部分岗位消失 → 需要再培训',
              'write': '问题和对策各两句',
              'sents': [
                  ('Jobs such as checking forms or sorting parcels can already be done by machines.',
                   '核对表格、分拣包裹这类工作已经可以由机器完成。'),
                  ('Workers in these jobs may find themselves unemployed with few useful skills.',
                   '从事这些工作的人可能会发现自己失业了，而且没什么有用的技能。'),
                  ('Governments should provide free training courses for people who lose their jobs.',
                   '政府应该为失业的人提供免费的培训课程。'),
                  ('Companies could also help their staff move into new roles.',
                   '公司也可以帮助员工转到新的岗位。'),
              ]},
             {'q': ('Some people say that students should not be allowed to use AI tools for their homework. To what extent do you agree or disagree?',),
              'use': '过度依赖 AI → 独立思考能力下降',
              'write': '部分同意，给出合理使用的例子',
              'sents': [
                  ('If students ask an AI tool to write every essay, they will not learn to organise their own ideas.',
                   '如果学生让 AI 工具写每一篇作文，他们就学不会组织自己的想法。'),
                  ('This could become a serious problem when they sit exams without any help.',
                   '当他们在没有任何帮助的情况下参加考试时，这可能会成为一个严重的问题。'),
                  ('However, AI can be useful for checking grammar after a draft is finished.',
                   '不过，在写完初稿之后，AI 可以用来检查语法。'),
                  ('Teachers should therefore explain clearly when these tools may be used.',
                   '因此，老师应该讲清楚什么时候可以使用这些工具。'),
              ]},
         ]},
    ]},
]


def big_question(ex):
    return ' '.join(ex['q'])


def big_md():
    out = ['# 雅思写作论证块（e2e 测试用，全部内容为编造）', '']
    for cat in BIG:
        out += [f'## {cat["name"]}', '']
        for sub in cat['subs']:
            out += [f'### {sub["name"]}', '', '#### 关键词']
            out += [f'- {k}' for k in sub['keywords']]
            out += ['', '#### 逻辑链']
            for i, (zh, en) in enumerate(sub['chains'], 1):
                out += [f'链{i}', f'- {zh}', f'- {en}']
            out += ['', '#### 细节举例', '']
            for i, ex in enumerate(sub['examples'], 1):
                out += [f'##### 例题 {i}', *ex['q'], '使用 / 写作提示',
                        f'- 使用：{ex["use"]}', f'- 写作：{ex["write"]}']
                for en, zh in ex['sents']:
                    out += [en, zh]
                out.append('')
    return '\n'.join(out)


write_text(f'{RES}/九分学长雅思写作论证块.md', big_md())


# =====================================================================
# 小作文仿写：图表类型 → 例题 → 段落 → 句子（原句 / 翻译 / 标签）
# 句子标题为 None 的是改写段那种不带标题、直接写原句和翻译的格式
# =====================================================================
SMALL = [
    ('折线图', [
        {'name': '1. 三座城市的共享单车出行量', 'subtype': '动态图',
         'q': ('The line graph below shows the average number of shared bike trips made per day in three cities, Northport, Lakeside and Hillview, from 2016 to 2026.',
               'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'),
         'sections': [
             ('改写段', [
                 (None, 'The line graph illustrates how many shared bike trips were taken on an average day in Northport, Lakeside and Hillview over the ten years from 2016.',
                  '这张折线图展示了从 2016 年起的十年里，北港、湖畔和山景三座城市平均每天的共享单车出行次数。'),
             ]),
             ('概括段', [
                 ('句子一【统一的】', 'Overall, shared bike use rose in all three cities over the period.',
                  '总体来看，三座城市的共享单车使用量在这段时间里都上升了。'),
                 ('句子二【另类】', 'Northport stood out, with its figure climbing far faster than those of the other two cities.',
                  '北港最为突出，它的数字比另外两座城市攀升得快得多。'),
             ]),
             ('细节段一 [先写起点最高的城市]', [
                 ('句子一【极端数值】', 'Northport began with about 12,000 trips a day in 2016, the highest of the three.',
                  '2016 年北港起步时每天约有 12,000 次出行，是三座城市中最高的。'),
                 ('句子二【极端趋势】', 'Its figure then surged to roughly 45,000 by 2026, almost four times the starting level.',
                  '随后它的数字激增到 2026 年的约 45,000 次，几乎是起点的四倍。'),
                 ('句子三【极端趋势】 / 【趋势非常相反】', 'By contrast, Hillview saw only a slight increase, from 5,000 to just over 7,000 trips.',
                  '相比之下，山景只略有增长，从 5,000 次增加到 7,000 多次。'),
             ]),
             ('细节段二', [
                 ('句子一【趋势非常相似】', 'Lakeside followed a similar path to Northport in the first five years, rising steadily to around 20,000 trips.',
                  '湖畔在前五年的走势和北港相似，稳步上升到约 20,000 次。'),
                 # 标签不在句型库分组里，页面要退回「可用的句型」
                 ('句子二【平稳】', 'After 2021, however, its figure levelled off and stayed close to that level until the end of the period.',
                  '然而 2021 年之后，它的数字趋于平稳，一直到最后都保持在这个水平附近。'),
             ]),
         ],
         'vocab': [('上升', 'surge to', '激增到'), ('上升', 'climb steadily', '稳步攀升'),
                   ('平稳', 'level off', '趋于平稳'), ('对比', 'by contrast', '相比之下')],
         'image': ('line_trips.png', [[12, 15, 19, 24, 28, 33, 36, 39, 41, 43, 45],
                                      [6, 9, 12, 16, 19, 20, 20, 21, 20, 20, 21],
                                      [5, 5, 5, 6, 6, 6, 6, 7, 7, 7, 7]])},
        {'name': '2. 一家咖啡馆两种饮品的月销量', 'subtype': '动态图',
         'q': ('The graph shows the number of cups of hot tea and iced coffee sold each month at a small café in 2025.',
               'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'),
         'sections': [
             ('改写段', [
                 (None, 'The graph compares monthly sales of hot tea and iced coffee at a small café over the course of 2025.',
                  '这张图比较了一家小咖啡馆 2025 年全年热茶和冰咖啡的月销量。'),
             ]),
             ('概括段', [
                 ('句子一【统一的】', 'Overall, the two drinks moved in opposite directions as the seasons changed.',
                  '总体来看，两种饮品的销量随季节变化朝相反的方向走。'),
                 ('句子二【另类】', 'Iced coffee was the only drink whose sales peaked in summer.',
                  '冰咖啡是唯一在夏天达到销量高峰的饮品。'),
             ]),
             ('细节段一', [
                 ('句子一【极端数值】', 'Hot tea was most popular in January, when around 900 cups were sold.',
                  '热茶在一月最受欢迎，当月卖出了约 900 杯。'),
                 ('句子二【极端趋势】', 'Its sales then dropped sharply to just 200 cups in July.',
                  '随后它的销量急剧下降，七月只卖出了 200 杯。'),
                 ('句子三【趋势非常相反】', 'Iced coffee showed the opposite pattern, rising from 150 cups to a peak of 1,000.',
                  '冰咖啡的走势正好相反，从 150 杯上升到 1,000 杯的峰值。'),
             ]),
             ('细节段二', [
                 ('句子一【数值非常相似】', 'In April and October, the two drinks sold almost the same number of cups.',
                  '在四月和十月，两种饮品卖出的杯数几乎相同。'),
                 ('句子二【极端趋势】', 'By December, hot tea had recovered to about 850 cups.',
                  '到了十二月，热茶回升到约 850 杯。'),
             ]),
         ],
         'vocab': None,
         'image': ('line_drinks.png', [[90, 82, 70, 55, 40, 28, 20, 24, 38, 55, 72, 85],
                                       [15, 20, 32, 55, 75, 92, 100, 96, 78, 56, 35, 22]])},
    ]),
    ('柱状图', [
        {'name': '1. 四个年龄段每周的阅读时长', 'subtype': '静态图',
         'q': ('The bar chart shows how many hours per week people in four age groups spent reading books, newspapers and online articles in 2025.',
               'Summarise the information by selecting and reporting the main features, and make comparisons where relevant.'),
         'sections': [
             ('改写段', [
                 (None, 'The bar chart compares the weekly reading time of four age groups across three types of material in 2025.',
                  '这张柱状图比较了 2025 年四个年龄段在三类读物上每周花的阅读时间。'),
             ]),
             ('概括段', [
                 ('句子一【【乱乱】】', 'Overall, there was no single pattern shared by all four age groups.',
                  '总体来看，四个年龄段之间没有一个共同的规律。'),
                 ('句子二【另类】', 'People over 60 were the only group who read newspapers more than anything else.',
                  '60 岁以上的人是唯一一个读报纸多于其他读物的群体。'),
             ]),
             ('细节段一', [
                 ('句子一【极端数值】', 'Young adults aged 18 to 29 spent the most time on online articles, at about 7 hours a week.',
                  '18 到 29 岁的年轻人花在网络文章上的时间最多，每周约 7 小时。'),
                 ('句子二【数值非常相反】', 'In contrast, they read newspapers for less than half an hour.',
                  '相比之下，他们读报纸的时间不到半小时。'),
                 ('句子三【极端数值】', 'Book reading was highest among people over 60, at roughly 5 hours.',
                  '读书时间在 60 岁以上人群中最高，约为 5 小时。'),
             ]),
             ('细节段二', [
                 ('句子一【数值非常相似】', 'The two middle groups spent a similar amount of time on books, at around 3 hours each.',
                  '中间两个年龄段花在书上的时间差不多，各约 3 小时。'),
                 ('句子二【数值非常相反】', 'Their online reading, however, differed by almost 2 hours.',
                  '不过，他们在网上阅读的时间相差将近 2 小时。'),
             ]),
         ],
         'vocab': None, 'image': None},
    ]),
    ('流程图', [
        {'name': '1. 屋顶雨水收集系统', 'subtype': '人工流程',
         'q': ('The diagram shows how rainwater is collected from the roof of a house and made ready for use in the garden and toilets.',
               'Summarise the information by selecting and reporting the main features.'),
         'sections': [
             ('改写段', [
                 (None, 'The diagram illustrates the way in which rain falling on a house roof is gathered and treated so that it can be reused.',
                  '这张图展示了落在房顶上的雨水如何被收集和处理，以便再次利用。'),
             ]),
             ('概括段', [
                 ('句子一【步骤总数】', 'Overall, the process consists of six main steps.',
                  '总体来看，这个过程包括六个主要步骤。'),
                 ('句子二【起点和终点】', 'It begins with rain landing on the roof and ends with clean water being pumped into the house.',
                  '它从雨水落到房顶开始，到干净的水被泵入屋内结束。'),
             ]),
             ('细节段一', [
                 ('句子一【第一阶段】', 'First, rainwater runs off the roof into a gutter.',
                  '首先，雨水从房顶流进檐沟。'),
                 ('句子二【第一阶段】', 'It then passes through a mesh filter, which removes leaves and other large objects.',
                  '然后它流过一层网状过滤器，把树叶和其他大的杂物滤掉。'),
                 ('句子三【第一阶段】', 'After that, the water is stored in an underground tank.',
                  '之后，水被储存在地下水箱里。'),
             ]),
             ('细节段二', [
                 ('句子一【第二阶段】', 'When it is needed, a small pump sends the water through a second, finer filter.',
                  '需要用水时，一个小水泵把水送过第二层更细的过滤器。'),
                 ('句子二【第二阶段】', 'Finally, the clean water is piped to the garden taps and the toilets.',
                  '最后，干净的水通过管道送到花园水龙头和厕所。'),
             ]),
         ],
         'vocab': None, 'image': None},
    ]),
]


def small_md():
    out = ['# 小作文仿写（e2e 测试用，全部内容为编造）', '']
    for type_name, examples in SMALL:
        out += [f'## {type_name}', '']
        for ex in examples:
            q = ex['q']
            out += [f'### {ex["name"]}', '', f'**图表类型**：{ex["subtype"]}', '', f'**题目**：{q[0]}', *q[1:], '']
            for heading, sents in ex['sections']:
                out.append(f'#### {heading}')
                for title, en, zh in sents:
                    if title is None:
                        out += [f'- **原句**：{en}', f'- **翻译**：{zh}']
                    else:
                        out += [f'- **{title}**', f'  - **原句**：{en}', f'  - **翻译**：{zh}']
                out.append('')
            if ex['vocab']:
                out += ['#### 表达积累', '| 类别 | 英文表达 | 中文含义 |', '| :--- | :--- | :--- |']
                out += [f'| **{c}** | {en} | {zh} |' for c, en, zh in ex['vocab']]
                out.append('')
    return '\n'.join(out)


write_text(f'{RES}/小作文仿写.md', small_md())


# ---- 题图：两张画出来的折线图，绑给折线图的两道例题；柱状图、流程图的例题留空 ----
from PIL import Image, ImageDraw  # noqa: E402

COLORS = [(44, 110, 180), (214, 120, 40), (90, 160, 90)]


def draw_line_chart(path, series):
    w, h, left, bottom, top, right = 480, 300, 50, 260, 24, 460
    img = Image.new('RGB', (w, h), (250, 250, 246))
    d = ImageDraw.Draw(img)
    for y in range(top + 36, bottom, 47):
        d.line([(left, y), (right, y)], fill=(226, 226, 220))
    d.line([(left, top), (left, bottom), (right, bottom)], fill=(80, 80, 80), width=2)
    peak = max(max(s) for s in series)
    for ys, color in zip(series, COLORS):
        step = (right - left) / (len(ys) - 1)
        pts = [(left + i * step, bottom - v / peak * (bottom - top - 10)) for i, v in enumerate(ys)]
        d.line(pts, fill=color, width=3)
        for x, y in pts:
            d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=color)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


bindings = {}
for type_name, examples in SMALL:
    for ex_idx, ex in enumerate(examples, 1):  # 解析器按 ^### 切分，第 0 块是图表类型标题下的空白，第一道例题是 1
        if not ex['image']:
            continue
        ex_id = f'{type_name}_{ex_idx}'
        fname, series = ex['image']
        draw_line_chart(f'{IMAGES}/{ex_id}/{fname}', series)
        bindings[ex_id] = f'/api/writing/small/image/{ex_id}/{fname}'
dump(f'{IMAGES}/image_bindings.json', bindings)


# =====================================================================
# 模板写作语料（结构和 script/import_writing_templates.py 导出的一样）
# =====================================================================
SLOT_RE = re.compile(r'\[([^\[\]]+)\]')
CJK_RE = re.compile(r'[一-鿿]')


def slots_of(text):
    out = []
    for i, m in enumerate(SLOT_RE.finditer(text)):
        key = m.group(1).strip()
        slot = {'index': i, 'key': key, 'label': key, 'type': 'text', 'hint': ''}
        parts = [p.strip() for p in key.split('/') if p.strip()]
        if '/' in key and not CJK_RE.search(key) and len(parts) >= 2 and all(len(p.split()) <= 4 for p in parts):
            slot['type'] = 'choice'
        out.append(slot)
    return out


def pattern(text, chinese='', label=''):
    return {'text': text, 'chinese': chinese, 'label': label, 'slots': slots_of(text)}


def group(label, *entries):
    """entries：字符串是说明，(英文, 中文[, 句序标签]) 是句型，按原文顺序排。"""
    patterns, notes, items = [], [], []
    for e in entries:
        if isinstance(e, str):
            notes.append(e)
            items.append({'type': 'note', 'text': e})
        else:
            patterns.append(pattern(*e))
            items.append({'type': 'pattern', 'index': len(patterns) - 1})
    return {'label': label, 'patterns': patterns, 'notes': notes, 'items': items}


def fake_url(slug):
    return f'https://example.com/fake-wiki/{slug}'


def big_variant(vi, name, sections):
    secs = []
    for si, (sec_name, note, texts) in enumerate(sections, 1):
        sentences = [{'text': t, 'slots': slots_of(t)} for t in texts]
        secs.append({'name': sec_name, 'note': note, 'sentences': sentences, 'id': f'v{vi + 1}s{si}',
                     'variant_index': vi, 'slot_count': sum(len(s['slots']) for s in sentences)})
    return {'name': name, 'sections': secs, 'index': vi}


def fill(tpl, values):
    it = iter(values)
    return SLOT_RE.sub(lambda m: '[' + next(it) + ']', tpl)


def paragraph(sec, rows_spec):
    """rows_spec：(槽位值列表, 中文) 按骨架顺序；值为 None 表示范文省略了这句；
    ('+', 英文, 中文) 是范文比骨架多写的一句。"""
    rows, all_pairs, values, ti = [], [], [], 0
    for spec in rows_spec:
        if spec[0] == '+':
            rows.append({'tpl_index': None, 'tpl_text': '', 'sample_text': spec[1], 'pairs': [],
                         'chinese': spec[2], 'sample_plain': spec[1]})
            continue
        vals, zh = spec
        tpl = sec['sentences'][ti]
        if vals is None:
            rows.append({'tpl_index': ti, 'tpl_text': tpl['text'], 'sample_text': '', 'pairs': []})
        else:
            assert len(vals) == len(tpl['slots']), (tpl['text'], vals)
            text = fill(tpl['text'], vals)
            pairs = [{'key': s['key'], 'value': v} for s, v in zip(tpl['slots'], vals)]
            all_pairs += pairs
            values += vals
            rows.append({'tpl_index': ti, 'tpl_text': tpl['text'], 'sample_text': text, 'pairs': pairs,
                         'chinese': zh, 'sample_plain': text.replace('[', '').replace(']', '')})
        ti += 1
    exact = all(r['sample_text'] for r in rows) and len(rows) == len(sec['sentences'])
    return {'section_id': sec['id'], 'section_name': sec['name'], 'score': 0.93 if exact else 0.71,
            'values': values, 'pairs': all_pairs, 'sentences': rows,
            'match': 'exact' if exact else 'partial', 'extra_values': [],
            'slot_count': sec['slot_count'], 'filled_count': len(all_pairs),
            'text': ' '.join(r['sample_plain'] for r in rows if r.get('sample_plain'))}


def unmatched_paragraph(text):
    """范文里有、骨架里对不上的一段（实战里会被跳过）。"""
    return {'section_id': '', 'section_name': '', 'score': 0.22, 'values': [], 'pairs': [], 'sentences': [],
            'match': 'none', 'slot_count': 0, 'filled_count': 0, 'text': text}


def version(name, type_obj, vi, paras):
    """paras：[(段落 id, rows_spec)]，按骨架段落顺序；段落 id 是 None 时第二项是对不上骨架的一段原文。"""
    secs = {s['id']: s for s in type_obj['variants'][vi]['sections']}
    out = []
    for sid, spec in paras:
        out.append(unmatched_paragraph(spec) if sid is None else paragraph(secs[sid], spec))
    return {'name': name, 'paragraphs': out, 'variant': type_obj['variants'][vi]['name'],
            'template_type_id': type_obj['id'], 'template_type_name': type_obj['name'],
            'template_variant_index': vi}


opinion = {
    'id': 'opinion', 'name': '观点型', 'title': '观点型模板',
    'feature': '题目问 To what extent do you agree or disagree，全文只站一个立场。',
    'kind': '模板', 'url': fake_url('opinion-template'), 'source_url': '',
    'variants': [big_variant(0, '', [
        ('开头（2组句子）', '第一句改写题目，第二句亮明立场并预告两个理由。', [
            'It is often argued that [改写观点].',
            'Personally, I [totally/partly] agree with this view, because [理由一] and [理由二].',
        ]),
        ('第一个理由', '理由一 + 前推 + 后推，三句写满。', [
            'The main reason is that [理由一].',
            'To be more specific, [前推].',
            'As a result, [后推].',
        ]),
        ('第二个理由', '', [
            'Another reason is that [理由二].',
            'For example, [例子].',
            'This shows that [小结].',
        ]),
        ('让步段', '先承认对方有道理，再用一句话拉回来。', [
            'Admittedly, [对方观点].',
            'However, [反驳].',
        ]),
        ('结尾', '', [
            'In conclusion, I believe that [重申立场].',
            'Therefore, [建议].',
        ]),
    ])],
    'samples': [],
    'sample_url': fake_url('opinion-samples'),
    # 和线上语料一样，题型上不挂 references：总结构只在 big 顶层，由题型详情接口补上
}

discuss = {
    'id': 'discuss', 'name': '讨论型', 'title': '讨论型模板',
    'feature': '题目要求 Discuss both views and give your own opinion，两边都要写到。',
    'kind': '模板', 'url': fake_url('discuss-template'), 'source_url': '',
    'variants': [
        big_variant(0, '第一种：两边观点 + 我的看法', [
            ('开头', '', [
                'People hold different views on whether [话题].',
                'While some argue that [观点A], others believe that [观点B].',
                'In my opinion, [我的立场].',
            ]),
            ('观点A段', '', [
                'On the one hand, those who support [观点A] point out that [理由A].',
                'For instance, [例子A].',
            ]),
            ('观点B段', '', [
                'On the other hand, there are good reasons to believe that [观点B].',
                'This is because [理由B].',
            ]),
            ('结尾', '', [
                'To sum up, although [观点A], I am convinced that [我的立场].',
            ]),
        ]),
        big_variant(1, '第二种：先让步再立论', [
            ('开头', '', [
                'It is a common belief that [观点A].',
                'However, I would argue that [我的立场].',
            ]),
            ('让步段', '', ['Admittedly, [观点A的道理].']),
            ('立论段', '', [
                'Nevertheless, [理由B].',
                'A good example is [例子B].',
            ]),
            ('结尾', '', ['Overall, [重申立场].']),
        ]),
    ],
    'samples': [],
    'sample_url': fake_url('discuss-samples'),
}

opinion['samples'] = [
    {'question': 'Some people think that every secondary school should teach students how to cook. To what extent do you agree or disagree?',
     'versions': [
         version('版本1', opinion, 0, [
             ('v1s1', [(['every secondary school should make cooking a compulsory subject'], '有人认为，每所中学都应该把烹饪设为必修课。'),
                       (['totally', 'cooking is a basic life skill', 'it encourages healthier eating habits'],
                        '我完全同意这个观点，因为烹饪是一项基本生活技能，而且它能培养更健康的饮食习惯。')]),
             ('v1s2', [(['cooking is a basic life skill that every adult needs'], '最主要的原因是，烹饪是每个成年人都需要的基本生活技能。'),
                       (['students who leave home for university often rely on takeaway food because they have never learned to prepare a simple meal'],
                        '具体来说，离家上大学的学生常常依赖外卖，因为他们从来没学过做一顿简单的饭。'),
                       (['they spend more money and eat less balanced meals'], '结果，他们花钱更多，饮食也更不均衡。')]),
             ('v1s3', [(['cooking lessons encourage healthier eating habits'], '另一个原因是，烹饪课能培养更健康的饮食习惯。'),
                       (['a pupil who learns to make a vegetable soup is more likely to choose fresh ingredients at home'],
                        '比如，学会做蔬菜汤的学生在家里更可能选择新鲜食材。'),
                       (['practical lessons can change daily behaviour'], '这说明，实践课程能改变日常行为。')]),
             ('v1s4', [(['the school timetable is already crowded with academic subjects'], '诚然，学校课表里的学术科目已经排得很满了。'),
                       (['one hour of cooking a week would not take much time away from other lessons'],
                        '然而，每周一小时的烹饪课并不会占用其他课程太多时间。')]),
             ('v1s5', [(['cooking should be taught in every secondary school'], '总之，我认为每所中学都应该教烹饪。'),
                       (['schools should work with local parents and chefs to make these lessons practical'],
                        '因此，学校应该与当地家长和厨师合作，让这些课程更实用。')]),
         ]),
         # 版本2：第一个理由省略了骨架第 2 句，又多写了一句骨架里没有的
         version('版本2', opinion, 0, [
             ('v1s1', [(['cooking ought to be part of the school curriculum'], '有人认为，烹饪应该纳入学校课程。'),
                       (['partly', 'it teaches independence', 'it can be fun'], '我部分同意这个观点，因为它能培养独立性，也可以很有趣。')]),
             ('v1s2', [(['learning to cook teaches young people to be independent'], '最主要的原因是，学做饭能教会年轻人独立。'),
                       (None, ''),
                       (['they feel more confident when they move out of their family home'], '结果，他们搬出家门时会更有自信。'),
                       ('+', 'Many of my classmates say the same thing.', '我的很多同学也这么说。')]),
             ('v1s3', [(['cooking can be an enjoyable break from exams'], '另一个原因是，烹饪可以让学生从考试中愉快地放松一下。'),
                       (['baking bread together gives classmates a chance to relax and talk'], '比如，一起烤面包让同学们有机会放松和聊天。'),
                       (['not every useful lesson has to be tested'], '这说明，并不是每门有用的课都需要考试。')]),
             ('v1s4', [(['some families can teach these skills at home'], '诚然，有些家庭可以在家里教这些技能。'),
                       (['many parents work long hours and have little time to cook with their children'],
                        '然而，很多父母工作时间很长，几乎没有时间和孩子一起做饭。')]),
             ('v1s5', [(['cooking deserves a place in the timetable, even if it is not a core subject'],
                        '总之，我认为烹饪应该在课表里占一席之地，即使它不是核心科目。'),
                       (['schools could offer it as a short weekly course'], '因此，学校可以把它作为每周一次的短课程。')]),
         ]),
     ]},
    {'question': 'Some people believe that city parks should be closed at night for safety reasons. To what extent do you agree or disagree?',
     'versions': [
         version('版本1', opinion, 0, [
             ('v1s1', [(['public parks in cities should be locked after dark to keep people safe'], '有人认为，为了保证安全，城市公园天黑后应该关闭。'),
                       (['partly', 'some parks are poorly lit', 'night-time visitors may be at risk'],
                        '我部分同意这个观点，因为有些公园照明很差，而且夜间游客可能有危险。')]),
             ('v1s2', [(['many parks are poorly lit'], '最主要的原因是，很多公园照明很差。'),
                       (['visitors cannot see uneven paths or steps'], '具体来说，游客看不清不平的小路和台阶。'),
                       (['accidents become more likely after sunset'], '结果，日落之后更容易发生意外。')]),
             ('v1s3', [(['night-time visitors may be at risk of crime'], '另一个原因是，夜间游客可能会遭遇犯罪。'),
                       (['a quiet park with no staff can attract people who want to damage property'],
                        '比如，一个没有工作人员的安静公园可能会吸引想破坏公物的人。'),
                       (['some form of control is needed'], '这说明，需要某种形式的管理。')]),
             ('v1s4', [(['closing parks would stop residents from exercising in the evening'], '诚然，关闭公园会让居民无法在晚上锻炼。'),
                       (['better lighting and night guards could solve this problem'], '然而，更好的照明和夜间保安可以解决这个问题。')]),
             ('v1s5', [(['parks should only be closed at night if they cannot be made safe'], '总之，我认为只有在无法保证安全时，公园才应该在夜间关闭。'),
                       (['local councils should invest in lighting first'], '因此，地方政府应该先投资照明。')]),
         ]),
     ]},
]

discuss['samples'] = [
    {'question': 'Some people think young people should take a gap year to travel before university, while others think they should start their studies straight away. Discuss both views and give your own opinion.',
     'versions': [
         version('版本1', discuss, 0, [
             ('v1s1', [(['school leavers should travel for a year or go straight to university'], '对于高中毕业生应该先旅行一年还是直接上大学，人们看法不一。'),
                       (['a gap year broadens the mind', 'it delays important studies'], '有人认为间隔年能开阔眼界，也有人认为它会耽误重要的学业。'),
                       (['a well-planned gap year is worth it'], '我认为，规划得好的间隔年是值得的。')]),
             ('v1s2', [(['taking a year off', 'travel helps young people understand other cultures'],
                        '一方面，支持休学一年的人指出，旅行能帮助年轻人了解其他文化。'),
                       (['a student who volunteers on a farm abroad learns to work with people from different backgrounds'],
                        '例如，在国外农场做志愿者的学生能学会和不同背景的人合作。')]),
             ('v1s3', [(['students should begin university immediately'], '另一方面，也有充分理由认为学生应该马上开始大学学习。'),
                       (['study habits may be lost after a long break'], '这是因为，长时间休息后学习习惯可能会丢掉。')]),
             ('v1s4', [(['a gap year delays university by twelve months', 'a year with clear goals benefits most young people'],
                        '总而言之，尽管间隔年会让上大学推迟一年，我仍然相信有明确目标的一年对大多数年轻人有好处。')]),
         ]),
         # 版本2 套的是第二种结构，学习页的结构切换要跟着变
         version('版本2', discuss, 1, [
             ('v2s1', [(['a gap year is a waste of time'], '人们普遍认为间隔年是浪费时间。'),
                       (['a year of travel can teach lessons that no classroom can'], '然而，我认为一年的旅行能教会课堂教不了的东西。')]),
             ('v2s2', [(['starting university at eighteen keeps students in the habit of studying'], '诚然，十八岁直接上大学能让学生保持学习习惯。')]),
             ('v2s3', [(['young people who have worked or travelled usually know more clearly what they want to study'],
                        '尽管如此，工作过或旅行过的年轻人通常更清楚自己想学什么。'),
                       (['a friend of mine who taught English abroad for a year and then chose to study education'],
                        '一个很好的例子是我的一位朋友，她在国外教了一年英语，之后选择了教育专业。')]),
             ('v2s4', [(['a gap year is worth taking if it is planned carefully'], '总的来说，只要计划周全，间隔年是值得的。')]),
         ]),
     ]},
    # 放错分区的题：在讨论型下面，实际套的是观点型模板（页面会标「套「观点型」」并按观点型对照）
    {'question': 'Some people think that museums should charge every visitor an entrance fee. To what extent do you agree or disagree?',
     'versions': [
         version('版本1', opinion, 0, [
             ('v1s1', [(['museums should ask every visitor to pay for a ticket'], '有人认为，博物馆应该向每位参观者收取门票。'),
                       (['partly', 'ticket money helps to protect collections', 'free entry keeps culture open to all'],
                        '我部分同意这个观点，因为门票收入有助于保护藏品，而免费入场能让文化向所有人开放。')]),
             ('v1s2', [(['ticket money helps to protect valuable collections'], '最主要的原因是，门票收入有助于保护珍贵的藏品。'),
                       (['old paintings and fragile objects need constant care and expert staff'], '具体来说，古老的画作和易碎的物品需要持续的维护和专业人员。'),
                       (['museums without enough income may have to close some rooms'], '结果，收入不足的博物馆可能不得不关闭部分展厅。')]),
             (None, 'Free days once a month would be a fair compromise for families on low incomes.'),
             ('v1s5', [(['a small fee is reasonable if there are free days for families on low incomes'],
                        '总之，我认为只要为低收入家庭设置免费日，收少量费用是合理的。'),
                       (['governments and museums should share the cost'], '因此，政府和博物馆应该共同承担费用。')]),
         ]),
     ]},
]

big_refs = [
    {'id': 'ref_big_structure', 'name': '大作文总结构', 'title': '大作文总结构', 'kind': '总结构',
     'url': fake_url('big-structure'), 'source_url': '',
     'groups': [
         group('四段式结构',
               '开头段两句话：改写题目 + 亮明立场，不要超过 60 词。',
               ('It is often argued that [改写观点].', '有人认为……（改写题目）', '第一句'),
               ('Personally, I [totally/partly] agree with this view.', '我（完全 / 部分）同意这个观点。', '第二句'),
               '主体段每段只讲一个理由，理由后面跟前推和后推。'),
         group('六种题型怎么认',
               '1. 观点：To what extent do you agree or disagree',
               '2. 讨论：Discuss both views and give your own opinion',
               '3. 好坏：Is this a positive or negative development'),
     ]},
    {'id': 'ref_big_linkers', 'name': '大作文常用衔接句', 'title': '大作文常用衔接句（视频讲解）', 'kind': '句型库',
     'url': fake_url('big-linkers'), 'source_url': '',
     'groups': [
         group('引出理由',
               ('The main reason is that [理由].', '最主要的原因是……'),
               ('Another reason is that [理由].', '另一个原因是……')),
         group('举例 · 让步',
               ('For example, [例子].', '比如……'),
               '让步句后面一定要接 However，把话题拉回自己的立场。',
               ('Admittedly, [对方观点]. However, [反驳].', '诚然……然而……')),
     ]},
]


def small_section(sid, name, groups):
    return {'id': sid, 'name': name, 'title': f'{name}模板', 'kind': '模板', 'url': fake_url(f'small-{sid}'),
            'source_url': '', 'groups': groups, 'pattern_count': sum(len(g['patterns']) for g in groups)}


REWRITE_GROUP = group('题目改写',
                      '改写段只要一句话：图表类型 + 主题 + 时间，动词换一个，别照抄题目。',
                      ('The [line graph/bar chart] [illustrates/compares] [主题] in [地点] from [年份] to [年份].',
                       '这张（折线图 / 柱状图）展示了……从……到……的……'),
                      ('The [line graph/bar chart] gives information about [主题] over a period of [年数] years.',
                       '这张图给出了……在……年间的情况。'))

charts = [
    {'id': 'data', 'name': '数据图', 'sections': [
        small_section('rewrite', '改写段', [REWRITE_GROUP]),
        small_section('overview', '概括段', [
            group('大众 · 动态图',
                  ('Overall, [数据] [rose/fell] over the period.', '总体来看，……在这段时间里（上升 / 下降）了。'),
                  ('It is clear that all [类别] followed an [upward/downward] trend.', '很明显，所有……都呈（上升 / 下降）趋势。')),
            group('另类 · 动态图',
                  ('[类别] stood out, with its figure [climbing/falling] far faster than the others.', '……最为突出，它的数字比其他的（涨 / 跌）得快得多。')),
            group('乱乱 · 静态图',
                  '数据之间没有统一规律时，用这一组概括。',
                  ('Overall, there was no single pattern shared by all [类别].', '总体来看，各……之间没有一个共同的规律。')),
        ]),
        small_section('detail', '细节段', [
            group('极端数值 · 动态图',
                  ('[类别] began with [数值] in [年份], the highest of all.', '……在……年起步时为……，是所有类别中最高的。'),
                  ('[类别] reached a peak of [数值] in [年份].', '……在……年达到……的峰值。')),
            group('极端数值 · 静态图',
                  ('[类别] had the largest share, at [数值].', '……占比最大，为……。')),
            group('极端趋势 · 动态图',
                  ('[类别] then [surged/plunged] to [数值] by [年份].', '随后……到……年（激增 / 骤降）到……。'),
                  ('There was a dramatic [rise/fall] in [类别], from [数值] to [数值].', '……出现了大幅（上升 / 下降），从……到……。')),
            group('趋势的相似 · 动态图',
                  ('[类别A] followed a similar path to [类别B], [rising/falling] steadily to [数值].', '……的走势和……相似，稳步（上升 / 下降）到……。')),
            group('趋势的相反 · 动态图',
                  ('By contrast, [类别] saw only a slight [increase/decrease].', '相比之下，……只略有（增长 / 下降）。')),
            group('数值的相似 · 静态图',
                  ('[类别A] and [类别B] were almost the same, at around [数值].', '……和……几乎一样，都在……左右。')),
            group('数值的相反 · 静态图',
                  ('In contrast, [类别] accounted for less than [数值].', '相比之下，……还不到……。')),
        ]),
    ], 'references': [
        {'id': 'ref_data_video', 'name': '数据图', 'title': '数据图（视频讲解）', 'kind': '视频讲解',
         'url': fake_url('data-video'), 'source_url': '',
         'groups': [group('看图顺序',
                          '先看横轴和单位，再找最高、最低和变化最大的线。',
                          '动态图写趋势，静态图比数值。')]},
    ]},
    {'id': 'process', 'name': '流程图', 'sections': [
        small_section('rewrite', '改写段', [group('题目改写',
            ('The diagram illustrates [how/the way in which] [过程].', '这张图展示了……的过程。'))]),
        small_section('overview', '概括段', [
            group('步骤总数', ('Overall, the process consists of [数字] main steps.', '总体来看，这个过程包括……个主要步骤。')),
            group('起点和终点', ('It begins with [第一步] and ends with [最后一步].', '它从……开始，到……结束。')),
        ]),
        small_section('detail', '细节段', [
            group('第一阶段',
                  ('First, [动作].', '首先，……'),
                  ('It then passes through [设备], which [作用].', '然后它经过……，……')),
            group('第二阶段',
                  ('When it is needed, [动作].', '需要的时候，……'),
                  ('Finally, [结果].', '最后，……')),
        ]),
    ], 'references': []},
    # 地图题只有句型库，没有仿写例题：段落卡片和例题列表都是空的
    {'id': 'map', 'name': '地图题', 'sections': [
        small_section('rewrite', '改写段', [group('题目改写',
            ('The two maps show how [地点] changed between [年份] and [年份].', '这两张地图展示了……在……年到……年之间的变化。'))]),
        small_section('overview', '概括段', [
            group('整体变化 · 静态图', ('Overall, [地点] became more [modern/residential] over the period.', '总体来看，……在这段时间里变得更加（现代化 / 住宅化）。')),
        ]),
        small_section('detail', '细节段', [
            group('方位描述', ('To the [north/south] of [地标], a new [建筑] was built.', '在……的（北 / 南）边，新建了一座……。')),
            group('新增与拆除', '先写拆掉的，再写新建的。',
                  ('The [建筑] was demolished to make way for [新建筑].', '……被拆除，为……让路。')),
        ]),
    ], 'references': []},
]

dump(f'{RES}/写作模板.json', {
    'generated_at': '2026-10-28T09:00:00',   # 写死，语料文件每次跑都一模一样
    'source': fake_url('writing-templates-index'),
    'big': {'types': [opinion, discuss], 'references': big_refs},
    'small': {'charts': charts},
    'warnings': [],
})


# =====================================================================
# 练习记录：字段和三个 save_practice 接口写进去的一模一样，全都 in_review: true
# feedback 是页面存进去的整个批改结果（服务端归一化后的字段 + 页面挂上的 _ 开头字段）
# =====================================================================
def feedback(score, summary, corrections, vocab, std, opt, ts, extra):
    native = f'1. 标准答案：{std}' + (f'\n\n2. 你的结构优化版：{opt}' if opt else '')
    fb = {'score': score, 'feedback_summary': summary, 'grammar_corrections': corrections,
          'vocabulary_upgrade': vocab, 'native_version': native,
          '_gradedAt': ms(ts), '_savedToReview': True}
    fb.update(extra)
    return fb


def gc(type_, original, corrected, reason):
    return {'original': original, 'corrected': corrected, 'type': type_, 'reason': reason}


def vu(original, replacement, reason):
    return {'original': original, 'replacement': replacement, 'reason': reason}


cat0, cat1 = BIG
elder, online = cat0['subs'][0], cat1['subs'][0]
elder_ex, online_ex = elder['examples'][0], online['examples'][0]

big_records = []
for rid, ts, sub_cat, sub, ex, si, answer, score, summary, corrections, vocab, opt in [
    ('big/3', ago(hours=20), cat1, online, online_ex, 2,
     'On the other hand, studying alone at home needs a lot of self-discipline.', '7.0',
     '句子准确，用词可以更正式。', [],
     [vu('needs', 'requires', '正式写作里 require 更合适')], ''),
    ('big/2', ago(days=1, hours=3), cat0, elder, elder_ex, 0,
     'When older people live with their children, they are rarely alone for a long time.', '6.0',
     '意思完整，个别搭配还能更地道。',
     [gc('搭配', 'rarely alone', 'rarely left alone', '被留下独处要用 left alone')],
     # 老格式的词汇提升（upgrade / explanation），页面也要认
     [{'original': 'for a long time', 'upgrade': 'for long periods', 'explanation': '强调反复多次的长时间'}],
     'When older people live with their children, they are rarely left alone for long periods.'),
    ('big/1', ago(days=3, hours=2), cat0, elder, elder_ex, 0,
     'When old people lives with their children, they are seldom alone for long time.', '5.0',
     '意思到位，但主谓一致和冠词出错。',
     [gc('主谓一致', 'old people lives', 'older people live', 'people 是复数，动词用原形'),
      gc('冠词', 'for long time', 'for a long time', 'long time 前要加 a')],
     [vu('seldom alone', 'rarely left alone', '被动的 left alone 更贴近原意')],
     'When older people live with their children, they are seldom alone for a long time.'),
]:
    target = ex['sents'][si][1]
    big_records.append({
        'id': fixed_id(rid), 'timestamp': ts, 'category': sub_cat['name'], 'subcategory': sub['name'],
        'question': big_question(ex), 'target_chinese': target, 'user_translation': answer, 'score': score,
        'feedback': feedback(score, summary, corrections, vocab, ex['sents'][si][0], opt, ts, {'_userInput': answer}),
        'native_version': '', 'in_review': True,
    })
# 页面存的 native_version 就是批改结果里的那段
for r in big_records:
    r['native_version'] = r['feedback']['native_version']
dump(f'{DATA}/linxia_practice.json', big_records)  # 新的在前，和接口 insert(0) 一致


def small_sentence(type_name, ex_pos, section_prefix, sent_pos):
    ex = dict(SMALL)[type_name][ex_pos]
    sec = next(s for s in ex['sections'] if s[0].startswith(section_prefix))
    title, en, zh = sec[1][sent_pos]
    tags = re.findall(r'【【?([^】]+?)】】?', title or '')
    return ex, sec[0].split(' [')[0], tags, en, zh


small_records = []
for rid, ts, type_name, ex_pos, sec_prefix, sent_pos, answer, score, summary, corrections, vocab, opt in [
    ('small/2', ago(days=1, hours=6), '流程图', 0, '概括段', 0,
     'Overall, the process include six main step.', '5.0', '结构对了，单复数和主谓一致要改。',
     [gc('主谓一致', 'the process include', 'the process includes', '主语单数，动词加 s'),
      gc('单复数', 'six main step', 'six main steps', 'six 后面用复数')],
     [vu('includes', 'consists of', '描述流程更常用 consist of')],
     'Overall, the process includes six main steps.'),
    ('small/1', ago(days=2, hours=1), '折线图', 0, '改写段', 0,
     'The line graph shows how many shared bike trips were taken each day in three cities over ten years from 2016.',
     '6.0', '改写到位，可以换个动词避免照抄题目。', [],
     [vu('shows', 'illustrates', '改写段换掉题目里的动词')], ''),
]:
    ex, sec_name, tags, en, zh = small_sentence(type_name, ex_pos, sec_prefix, sent_pos)
    fb = feedback(score, summary, corrections, vocab, en, opt, ts, {'_userInput': answer})
    small_records.append({
        'id': fixed_id(rid), 'timestamp': ts, 'chart_type': type_name, 'chart_subtype': ex['subtype'],
        'example_name': ex['name'], 'question': ' '.join(ex['q']), 'section_name': sec_name,
        'sentence_tags': tags, 'target_chinese': zh, 'user_translation': answer, 'score': score,
        'feedback': fb, 'native_version': fb['native_version'], 'in_review': True,
    })
dump(f'{DATA}/linxia_small_practice.json', small_records)


def big_tpl_row(type_obj, qi, vi, sid, idx):
    """实战页的句序只数范文写了的句子（sample_text 非空），这里按同样的规则取。"""
    v = type_obj['samples'][qi]['versions'][vi]
    para = next(p for p in v['paragraphs'] if p['section_id'] == sid)
    return para, [r for r in para['sentences'] if r['sample_text']][idx]


tpl_records = []
for rid, ts, qi, vi, sid, idx, answer, score, summary, corrections, vocab, opt, peeked in [
    ('tpl/2', ago(hours=5), 0, 0, 'v1s2', 1,
     'To be more specific, students who go to university often rely on takeaway because they never learned cooking simple meal.',
     '5.0', '骨架套对了，后半句缺冠词、时态不对。',
     [gc('时态', 'they never learned', 'they have never learned', '到现在为止的经历用现在完成时'),
      gc('冠词', 'cooking simple meal', 'to prepare a simple meal', 'meal 可数，前面要加 a')],
     [vu('rely on takeaway', 'rely on takeaway food', 'takeaway food 更完整')],
     'To be more specific, students who go to university often rely on takeaway food because they have never learned to prepare a simple meal.',
     True),
    ('tpl/1', ago(days=2, hours=4), 0, 0, 'v1s1', 0,
     'It is often argued that all secondary schools should make cooking a required subject.',
     '6.0', '改写准确，用词还能再贴近原文。', [],
     [vu('required subject', 'compulsory subject', '必修课的固定说法')], '', False),
]:
    para, row = big_tpl_row(opinion, qi, vi, sid, idx)
    q = opinion['samples'][qi]
    ver = q['versions'][vi]
    payload = {
        'task': 'task2', 'type_id': opinion['id'], 'type_name': ver['template_type_name'], 'variant': ver['variant'],
        'section_id': sid, 'section_name': para['section_name'],
        'question_id': f'sample{qi}v{vi}', 'question': q['question'],
        'example_name': f'{opinion["name"]}范文 {qi + 1} · {ver["name"]}', 'sentence_index': idx,
        'template_text': row['tpl_text'], 'target_chinese': row['chinese'], 'reference': row['sample_plain'],
        'user_translation': answer, 'peeked': peeked,
    }
    fb = feedback(score, summary, corrections, vocab, row['sample_plain'], opt, ts, {'_payload': payload})
    tpl_records.append({'id': fixed_id(rid), 'timestamp': ts, **{k: payload[k] for k in (
        'task', 'type_id', 'type_name', 'variant', 'section_id', 'section_name', 'question_id', 'question',
        'example_name', 'sentence_index', 'template_text', 'reference', 'target_chinese', 'user_translation')},
        'score': score, 'feedback': fb, 'native_version': fb['native_version'], 'peeked': peeked, 'in_review': True})

# 小作文模板实战一条：数据图 · 细节段，套的是「极端数值 · 动态图」第 1 个句型（句型库里显示「已练 1/2」）
ex, sec_name, tags, en, zh = small_sentence('折线图', 0, '细节段一', 0)
ts = ago(days=1, hours=1)
answer = 'Northport began with about 12,000 trips per day in 2016, which was the highest among three cities.'
payload = {
    'task': 'task1', 'type_id': 'data', 'type_name': '数据图 · 细节段', 'variant': '',
    'section_id': 'detail', 'section_name': sec_name, 'question_id': '折线图_1', 'question': ' '.join(ex['q']),
    'example_name': ex['name'], 'sentence_index': 0,
    'template_text': charts[0]['sections'][2]['groups'][0]['patterns'][0]['text'],
    'target_chinese': zh, 'reference': en, 'user_translation': answer, 'peeked': False,
}
fb = feedback('7.0', '表达清楚，介词搭配再注意一下。',
              [gc('冠词', 'among three cities', 'among the three cities', '特指图里的三座城市要加 the')],
              [vu('which was the highest', 'the highest of the three', '同位语更简洁')], en, '', ts, {'_payload': payload})
tpl_records.insert(1, {'id': fixed_id('tpl/3'), 'timestamp': ts, **{k: v for k, v in payload.items() if k != 'peeked'},
                       'score': '7.0', 'feedback': fb, 'native_version': fb['native_version'],
                       'peeked': False, 'in_review': True})
dump(f'{DATA}/linxia_template_practice.json', tpl_records)


# ---- 速记本（两个标签页）和一段 AI 助手聊天记录 ----
tab1, tab2 = fixed_id('notebook/1'), fixed_id('notebook/2')
dump(f'{DATA}/linxia_notebook.json', {
    'tabs': [
        {'id': tab1, 'title': '速记 1', 'created_at': ago(days=5), 'updated_at': ago(days=1),
         'content': '<p>开头段别照抄题目，动词换成 <b>illustrates</b> / <b>compares</b>。</p><p>让步段：Admittedly … However …</p>'},
        {'id': tab2, 'title': '连接词', 'created_at': ago(days=4), 'updated_at': ago(days=4),
         'content': '<ul><li>by contrast 相比之下</li><li>as a result 结果</li><li>to be more specific 具体来说</li></ul>'},
    ],
    'active_tab_id': tab1, 'updated_at': ago(days=1),
})

chat_id = fixed_id('chat/1')
s0_en, s0_zh = elder_ex['sents'][0]
dump(f'{DATA}/chat_history/linxia/{chat_id}.json', {
    'id': chat_id, 'sentence_key': f'big|{cat0["name"]}|例题 1|0',
    'context_zh': s0_zh, 'context_en': s0_en, 'context_tags': [], 'module': 'big',
    'detail_info': f'{cat0["name"]} > 例题 1', 'created_at': ago(days=2), 'updated_at': ago(days=2),
    'messages': [
        {'role': 'user', 'content': '这个句子的主干是什么？'},
        {'role': 'assistant', 'content': '主干是 they are rarely left alone，前面的 When … 是时间状语从句。'},
    ],
})


# ---- 给假用户发 token，浏览器脚本直接拿来用 ----
sys.path.insert(0, sb)
import core  # noqa: E402  沙盒里的那份代码，tokens.json 写在沙盒目录

u = users['linxia']
dump(os.path.join('_e2e', 'tokens.json'), {
    'linxia': {'token': core.create_token('linxia'),
               'user': {k: u[k] for k in ('username', 'display_name', 'role', 'avatar')}},
})
print(f'假数据已写入 {sb}')

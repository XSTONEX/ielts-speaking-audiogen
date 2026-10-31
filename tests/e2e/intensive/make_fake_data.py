"""给「文章精读」浏览器测试造一份沙盒数据。文章、释义、图片、音频全是编的——仓库是公开的，不放任何真实记录。

用法：python make_fake_data.py <沙盒目录>
- 沙盒目录里应该已经有一份代码（git ls-files -co --exclude-standard 复制过去的，sandbox.sh start 会做）。
  服务器按相对路径读写数据，所以数据就建在沙盒目录下面，和线上的目录结构一样。
- 每次运行都会先清空沙盒里的 intensive_articles/ 和 vocab_audio/，再重新写一遍，可以随时用来「重置」。
- 登录凭证写到 <沙盒目录>/e2e_token.txt（用户 reader01「测试读者」）。浏览器测试把它放进 localStorage，不输密码。
- 为了不误伤真数据：目录里有 .git、.env，或者 users.json 里有别的用户，就直接退出。

文章 ID 是固定的，run.js 里 lib.js 的 IDS 要和这里保持一致。
"""
import json
import os
import secrets
import shutil
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent.parent / "fixtures" / "jiufen_reading_attempt.json"   # 编出来的九分学长作答（The Glass Bridge）
USERNAME = "reader01"

# ---------- 小工具 ----------


def u16(text):
    """页面上的下标是 JS 的 UTF-16 下标，高亮的 start/end 也按这个存。"""
    return len(text.encode("utf-16-le")) // 2


def content_html(text):
    """和 routers/intensive_reading.py 的 _content_html 一样：每个非空行一个 <p>。"""
    paragraphs = [f"<p>{p.replace('<', '&lt;')}</p>" for p in text.split("\n") if p.strip()]
    return "\n".join(paragraphs) or f"<p>{text.replace('<', '&lt;')}</p>"


def highlight(text, word, meaning, hid, nth=0, created="2026-10-20T10:00:00"):
    """在正文里找第 nth 次出现的 word，按 UTF-16 算下标。"""
    i = -1
    for _ in range(nth + 1):
        i = text.index(word, i + 1)
    start = u16(text[:i])
    return {"id": hid, "start": start, "end": start + u16(word), "meaning": meaning,
            "created_at": created, "text": word}


def article(aid, title, category, created, lines, highlights=(), images=(), exam=None):
    text = "\n".join(lines)
    obj = {
        "id": aid,
        "title": title,
        "category": category,
        "created_at": created,
        "content_text": text,
        "content_html": content_html(text),
        "highlights": [highlight(text, *h) for h in highlights],
        "images": list(images),
    }
    if exam is not None:
        obj["source"] = "jiufen"
        obj["exam"] = exam
    return obj


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def png(width, height, bars):
    """一张很小的 PNG：白底 + 几根彩色竖条，看着像柱状图就行。bars: [(x0, x1, 高度比例, (r, g, b))]"""
    rows = []
    for y in range(height):
        row = bytearray(b"\x00")
        for x in range(width):
            color = (255, 255, 255)
            for x0, x1, frac, c in bars:
                if x0 <= x < x1 and y >= height * (1 - frac):
                    color = c
            row += bytes(color)
        rows.append(bytes(row))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")


def silent_mp3(seconds):
    """一串 MPEG-1 Layer III 帧（128kbps / 44.1kHz / 单声道），帧体全是 0，播出来是静音，浏览器能解出时长。"""
    frame = bytes([0xFF, 0xFB, 0x90, 0xC4]) + bytes(417 - 4)
    return frame * (int(seconds * 44100 / 1152) + 1)


# ---------- 文章 ----------
# 每篇各管一种容易出错的正文格式，选词测试（suite_select.js）会在每篇上逐行试。

LIGHTHOUSE = "20261020090000-The-Lighthouse-Keeper-s-Log"      # 普通的一句英文一句译文；有一条重复的高亮
FERRY = "20261019090000-Night-Ferry-Timetable"                  # 含不间断空格（U+00A0），还有只有 NBSP 的空行
COLD_CHAIN = "20261018090000-The-Cold-Chain"                    # 「第1段」「Paragraph C」小标题；行首就是高亮
EMOJI = "20261017090000-助记小文章-天气与心情"                   # emoji（代理对）+ 一行好几句；中文标题
ROPE_BRIDGE = "20261001090000-The-Rope-Bridge-Builders"         # 手机测试用；Reading 里最旧，排在列表最下面
CHART = "20261016090000-Task1-饼图-城市用电来源"                 # Writing，带一张图片
SALT_MARSH = "20261015090000-The-Salt-Marsh-Survey"             # Listening，带一段已生成的朗读音频，正文够长能滚动
GLASS_BRIDGE = "20261021090000-The-Glass-Bridge"                # 九分学长导入（带译文），由 tests/fixtures 的编造作答生成

FILLERS = [  # 只是为了让列表够长、手机上要往下翻
    ("Tidal Mills", "Tide mills used the sea to grind grain twice a day.", "潮汐磨坊一天两次借海水磨谷物。"),
    ("Beekeeping on Rooftops", "City bees often produce more honey than rural ones.", "城里的蜜蜂产的蜜常常比乡下的多。"),
    ("The Last Tram Driver", "He drove the same route for thirty-one years.", "他在同一条线路上开了三十一年。"),
    ("Ice Roads", "Some northern roads exist only in the coldest months.", "有些北方的路只在最冷的几个月里存在。"),
    ("Paper Lanterns", "Each lantern takes about two hours to fold and glue.", "每只灯笼折叠、粘合大约要两个小时。"),
    ("A Village of Clockmakers", "Almost every house once had a workbench by the window.", "以前几乎每户人家窗边都有一张工作台。"),
    ("Desert Gardens", "Stone walls trap the morning dew for the plants.", "石墙为植物留住了清晨的露水。"),
    ("Floating Schools", "During floods, classes continue on converted boats.", "洪水期间，课堂搬到改装过的船上继续上。"),
    ("The Seed Library", "Members borrow seeds in spring and return new ones in autumn.", "会员春天借种子，秋天还回新收的种子。"),
]


def lighthouse():
    lines = [
        "The Lighthouse Keeper's Log",
        "灯塔看守人的日志",
        "For forty years, the lamp on Gull Point was tended by a single family.",
        "四十年来，海鸥角上的那盏灯一直由同一个家庭照看。",
        "Every evening the keeper climbed one hundred and twelve steps to light the wick.",
        "每天傍晚，看守人都要爬一百一十二级台阶去点燃灯芯。",
        "Storms were recorded in a leather notebook, along with the names of passing ships.",
        "风暴被记在一本皮面笔记本里，一同记下的还有过往船只的名字。",
        "Visitors often assumed the work was lonely, but the log tells a different story.",
        "游客常常以为这份工作很孤独，但日志讲述的是另一番景象。",
        "Neighbours rowed across with bread, letters and, occasionally, a stray cat.",
        "邻居们划船过来，带着面包、信件，偶尔还有一只流浪猫。",
        "Engineers automated the lamp in 1987, and the family moved to the mainland.",
        "1987 年，工程师把灯改成了自动运行，这家人搬到了大陆上。",
        "Today the notebook is kept in the harbour museum, open to anyone who asks.",
        "如今这本笔记本存放在港口博物馆里，谁想看都可以。",
        "Researchers use it to compare historic storms with modern weather data.",
        "研究人员用它来对比历史上的风暴和现代的气象数据。",
    ]
    hls = [
        ("tended", "照料", "fake-lh-01"),
        ("Storms", "风暴", "fake-lh-02"),
        ("leather notebook", "皮面笔记本", "fake-lh-03"),
        ("assumed", "以为；假定", "fake-lh-04"),
        ("assumed", "以为；假定", "fake-lh-04b"),   # 同一范围存了两次：页面要去重，只画一个
        ("occasionally", "偶尔", "fake-lh-05"),
        ("automated", "使自动化", "fake-lh-06"),
        ("harbour", "港口", "fake-lh-07"),
        ("compare", "比较", "fake-lh-08"),
    ]
    return article(LIGHTHOUSE, "The Lighthouse Keeper's Log", "Reading", "2026-10-20T09:00:00", lines, hls)


def ferry():
    nb = " "
    lines = [
        "Night Ferry Timetable",
        "夜班渡轮时刻表",
        nb,
        f"The last ferry leaves the north pier at 11{nb}p.m. on weekdays.",
        "工作日最后一班渡轮晚上 11 点从北码头开出。",
        nb + nb,
        f"Tickets{nb}cost three coins, or one coin for children under{nb}ten.",
        "船票三枚硬币，十岁以下儿童一枚。",
        "Passengers may bring bicycles but not cars.",
        "乘客可以带自行车，但不能带汽车。",
        nb,
        "During winter the crossing takes twice as long because of ice.",
        "冬天因为结冰，渡河时间要翻倍。",
        "Captains sound the horn three times before leaving.",
        "船长开船前会鸣笛三次。",
        "Latecomers sometimes wave from the pier, hoping the boat will turn back.",
        "迟到的人有时会在码头挥手，希望船能掉头回来。",
        "Nobody can remember the last time it did.",
        "没人记得它上一次掉头是什么时候。",
    ]
    hls = [
        ("pier", "码头", "fake-fe-01"),
        (f"11{nb}p.m.", "晚上 11 点", "fake-fe-02"),
        ("crossing", "横渡", "fake-fe-03"),
        ("horn", "汽笛", "fake-fe-04"),
        ("Latecomers", "迟到的人", "fake-fe-05"),
        ("turn back", "掉头", "fake-fe-06"),
    ]
    return article(FERRY, "Night Ferry Timetable", "Reading", "2026-10-19T09:00:00", lines, hls)


def cold_chain():
    lines = [
        "The Cold Chain",
        "冷链",
        "第1段",
        "Orders for frozen vegetables rise sharply every December.",
        "每年十二月，冷冻蔬菜的订单都会大幅上涨。",
        "Warehouses must keep the produce below minus eighteen degrees.",
        "仓库必须把农产品保持在零下十八度以下。",
        "",
        "第2段",
        "Sales staff track each pallet with a small temperature sticker.",
        "销售人员用一张小小的温度贴纸追踪每一托货。",
        "If the sticker turns red, the whole pallet is rejected.",
        "如果贴纸变红，整托货都会被拒收。",
        "",
        "Paragraph C",
        "Drivers are paid a bonus for deliveries that arrive intact.",
        "送达时完好无损的货物，司机能拿到奖金。",
        "Customers rarely notice any of this effort.",
        "顾客很少注意到这些努力。",
    ]
    hls = [
        ("sharply", "急剧地", "fake-cc-01"),
        ("Sales", "销售", "fake-cc-02"),
        ("pallet", "托盘（一托货）", "fake-cc-03"),
        ("rejected", "被拒收", "fake-cc-04"),
        ("intact", "完好无损的", "fake-cc-05"),
        ("rarely", "很少", "fake-cc-06"),
    ]
    return article(COLD_CHAIN, "The Cold Chain", "Reading", "2026-10-18T09:00:00", lines, hls)


def emoji():
    lines = [
        "助记小文章：天气与心情 🌦️",
        "Rain 🌧️ kept the harbour quiet. Nobody hurried, and the gulls sulked on the rooftops.",
        "雨🌧️让港口安静下来。没人赶路，海鸥在屋顶上闷闷不乐。",
        "☀️ When the sun returned, the market woke up. Vendors shouted; children chased pigeons.",
        "☀️ 太阳回来时，集市醒了。小贩吆喝，孩子们追着鸽子跑。",
        "Fog 🌫️ made everyone whisper. Even the dogs seemed reluctant to bark.",
        "雾🌫️让每个人都压低了声音。连狗都似乎懒得叫。",
        "😴 Gloomy afternoons are perfect for naps. Grumpy cats agree.",
        "😴 阴沉的下午最适合午睡。脾气差的猫也同意。",
        "Thunder ⚡ rattled the windows twice. Afterwards the air smelled of metal.",
        "雷声⚡把窗户震响了两次。之后空气里有股金属味。",
        "Snow ❄️ softened every sound. People smiled at strangers for no reason.",
        "雪❄️让所有声音都变轻了。人们无缘无故地对陌生人微笑。",
    ]
    hls = [
        ("sulked", "闷闷不乐", "fake-em-01"),
        ("chased", "追赶", "fake-em-02"),
        ("reluctant", "不情愿的", "fake-em-03"),
        ("Gloomy", "阴沉的", "fake-em-04"),
        ("rattled", "使发出咯咯声", "fake-em-05"),
        ("softened", "使变柔和", "fake-em-06"),
    ]
    return article(EMOJI, "助记小文章-天气与心情", "Reading", "2026-10-17T09:00:00", lines, hls)


def rope_bridge():
    lines = [
        "The Rope Bridge Builders",
        "绳桥建造者",
        "High in the valley, villagers rebuild their rope bridge every spring.",
        "在山谷高处，村民们每年春天都会重建他们的绳桥。",
        "Grass is gathered from the hillsides and twisted into thin cords.",
        "人们从山坡上采集草，把它们拧成细绳。",
        "Families compete to braid the longest and strongest section.",
        "各家比赛，看谁编出的那一段最长最结实。",
        "Elders inspect every knot before the cords are joined together.",
        "长者在把绳子接起来之前要检查每一个结。",
        "Crossing the finished bridge is the highlight of the festival.",
        "走过建好的桥是节日的高潮。",
        "Tourists watch nervously while children run across without fear.",
        "游客们紧张地看着，孩子们却毫无畏惧地跑过去。",
        "Within a year the grass weakens, so the cycle begins again.",
        "一年之内草绳就会变弱，于是这个循环又重新开始。",
    ]
    hls = [
        ("rebuild", "重建", "fake-rb-01"),
        ("twisted", "拧；搓", "fake-rb-02"),
        ("braid", "编（辫子、绳）", "fake-rb-03"),
        ("inspect", "检查", "fake-rb-04"),
        ("nervously", "紧张地", "fake-rb-05"),
    ]
    return article(ROPE_BRIDGE, "The Rope Bridge Builders", "Reading", "2026-10-01T09:00:00", lines, hls)


def chart(root):
    filename = "20261016_090000_c0ffee01.png"
    path = root / "intensive_articles" / "images" / CHART / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png(160, 100, [(20, 50, 0.8, (90, 120, 200)), (65, 95, 0.45, (230, 150, 60)), (110, 140, 0.25, (80, 170, 110))]))
    lines = [
        "Task 1 · 饼图",
        "The pie charts compare the sources of electricity in a coastal city in 2000 and 2020.",
        "两张饼图比较了一座沿海城市 2000 年和 2020 年的电力来源。",
        "Coal fell from roughly half of the total to under a fifth.",
        "煤炭从总量的大约一半降到了不足五分之一。",
        "Wind and solar together grew from almost nothing to over a third.",
        "风能和太阳能合计从几乎为零增长到三分之一以上。",
    ]
    images = [{"id": "fake-img-01", "filename": filename, "original_name": "chart.png", "created_at": "2026-10-16T09:01:00"}]
    return article(CHART, "Task1-饼图-城市用电来源", "Writing", "2026-10-16T09:00:00", lines, [("roughly", "大约", "fake-ch-01")], images)


def salt_marsh(root):
    pairs = [
        ("The Salt Marsh Survey", "盐沼调查"),
        ("Every autumn, volunteers walk the marsh at low tide with clipboards.", "每年秋天，志愿者们拿着记录板在退潮时走进盐沼。"),
        ("They count wading birds, measure the mud and photograph the channels.", "他们清点涉禽、测量淤泥，并给水道拍照。"),
        ("The survey began with six people and a borrowed rowing boat.", "调查开始时只有六个人和一条借来的划艇。"),
        ("Now more than two hundred people take part each year.", "如今每年有两百多人参加。"),
        ("The data show that the marsh is slowly moving inland.", "数据显示，盐沼正在慢慢向内陆移动。"),
        ("Rising sea levels push the salt water further up the valley.", "海平面上升把咸水推向山谷更深处。"),
        ("Some farmers have agreed to let their fields flood naturally.", "一些农民同意让自己的田地自然被淹。"),
        ("In return, they receive a small payment from the regional council.", "作为回报，他们从地区议会领取一小笔补偿。"),
        ("Within a decade, the new marsh attracted rare plants and insects.", "十年之内，新形成的盐沼吸引来了罕见的植物和昆虫。"),
        ("Scientists now use the volunteers' records to plan coastal defences.", "科学家现在用志愿者的记录来规划海岸防护。"),
        ("The organisers say the best part is still the muddy walk itself.", "组织者说，最棒的部分仍然是那段满是泥的步行本身。"),
        ("Hot soup is served at the end, whatever the weather.", "不管天气如何，结束时都会供应热汤。"),
        ("Children are given their own small notebooks to record what they see.", "孩子们会拿到自己的小本子，记下看到的东西。"),
        ("Next year the survey will add an evening walk to count bats.", "明年调查会增加一次傍晚的步行，去数蝙蝠。"),
    ]
    lines = [x for pair in pairs for x in pair]
    audio_dir = root / "vocab_audio" / "articles" / SALT_MARSH
    audio_dir.mkdir(parents=True, exist_ok=True)
    (audio_dir / "article_audio_20261015_090500.mp3").write_bytes(silent_mp3(3))
    (audio_dir / "article_audio_20261015_090500.txt").write_text(" ".join(p[0] for p in pairs), encoding="utf-8")
    return article(SALT_MARSH, "The Salt Marsh Survey", "Listening", "2026-10-15T09:00:00", lines,
                   [("wading birds", "涉禽", "fake-sm-01"), ("inland", "向内陆", "fake-sm-02")])


GLASS_BRIDGE_ZH = {   # 编的译文，配 tests/fixtures/jiufen_reading_attempt.json
    "s0": "马洛镇在 1998 年建了第一座玻璃桥。",
    "s1": "工程师选用玻璃，是因为它能让光照到下面的河上。",
    "s2": "当地渔民起初很担心。",
    "s3": "他们认为桥的影子会把鱼吓跑。",
    "s4": "然而不到一年，渔获量反而增加了。",
    "s5": "如今这座桥是很受欢迎的景点。",
    "s6": "游客大多在傍晚来，那时玻璃从下方被照亮。",
    "s7": "北岸的一座小博物馆讲述了它的建造过程。",
    "q0.1": "马洛的这座桥是全国同类桥中的第一座。",
    "q0.2": "渔民从一开始就支持建桥。",
    "q0.3": "这座桥晚上吸引的游客比白天多。",
    "q1.4": "工程师为什么选择玻璃？为了让光照到____",
    "q1.5": "博物馆在哪里？在____",
}


def glass_bridge(root):
    """和 /intensive_import 走同一套代码（utils/jiufen_import），只是译文是这里给的，不调翻译接口。"""
    sys.path.insert(0, str(root))
    try:
        from utils import jiufen_import as J
    finally:
        sys.path.pop(0)
    with open(FIXTURE, encoding="utf-8") as f:
        part = J.parse(json.load(f))[0]
    J.apply_translations(part, GLASS_BRIDGE_ZH)
    text = J.build_article_text(part)
    obj = article(GLASS_BRIDGE, part["title"], "Reading", "2026-10-21T09:00:00", [text], exam={**part, "translated": True})
    return obj


def fillers():
    out = []
    for k, (title, en, zh) in enumerate(FILLERS):
        day = 2 + k   # 2026-10-02 … 2026-10-10：比 ROPE_BRIDGE 新、比上面几篇旧
        aid = f"202610{day:02d}090000-" + title.replace(" ", "-")
        out.append(article(aid, title, "Reading", f"2026-10-{day:02d}T09:00:00", [title, en, zh]))
    return out


# ---------- 入口 ----------


def check_target(root):
    if not root.is_dir():
        sys.exit(f"沙盒目录不存在：{root}")
    if (root / ".git").exists() or (root / ".env").exists():
        sys.exit(f"{root} 里有 .git 或 .env，看起来是真项目目录，不往这里写。请先用 sandbox.sh start 建一个沙盒。")
    if not (root / "utils" / "jiufen_import.py").exists():
        sys.exit(f"{root} 里没有代码（utils/jiufen_import.py）。先把代码复制进去：sandbox.sh start 会做。")
    users = root / "users.json"
    if users.exists():
        try:
            names = set(json.loads(users.read_text(encoding="utf-8")))
        except ValueError:
            names = {"?"}
        if names - {USERNAME}:
            sys.exit(f"{users} 里有别的用户，可能是真数据，不覆盖。")


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1]).resolve()
    check_target(root)

    write_json(root / "users.json", {USERNAME: {
        "username": USERNAME, "password": "not-used-in-e2e", "display_name": "测试读者",
        "role": "admin", "avatar": "avatar_admin.svg", "created_at": "2026-09-01T09:00:00"}})
    token = secrets.token_urlsafe(32)   # 和 core.create_token 存的格式一样
    write_json(root / "tokens.json", {token: {"created_time": "2026-10-31T09:00:00", "username": USERNAME}})
    (root / "e2e_token.txt").write_text(token, encoding="utf-8")

    for name in ("intensive_articles", "vocab_audio"):
        shutil.rmtree(root / name, ignore_errors=True)
    (root / "intensive_articles" / "images").mkdir(parents=True)

    articles = [lighthouse(), ferry(), cold_chain(), emoji(), rope_bridge(), chart(root), salt_marsh(root),
                glass_bridge(root)] + fillers()
    for a in articles:
        write_json(root / "intensive_articles" / f"{a['id']}.json", a)

    print(f"写好了 {len(articles)} 篇编造的文章 → {root / 'intensive_articles'}")
    print(f"登录 token → {root / 'e2e_token.txt'}（用户 {USERNAME}）")


if __name__ == "__main__":
    main()

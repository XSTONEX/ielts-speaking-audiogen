"""给「词汇汇总 + 登录」浏览器测试造一份沙盒数据。文章、单词、挑战记录全是编的——仓库是公开的，不放任何真实记录。

用法：python make_fake_data.py <沙盒目录>
- 沙盒目录里应该已经有一份代码（sandbox.sh start 会用 git ls-files 复制过去）。
  服务器按相对路径读写数据，所以数据就建在沙盒目录下面，和线上的目录结构一样。
- 每次运行都会先清空沙盒里的 intensive_articles/、vocab_audio/、challenges/，再重新写一遍，可以随时用来「重置」。
- 用户 reader02「词汇测试员」，密码见 PASSWORD（故意以空格结尾：登录页以前会把首尾空格删掉，这样的密码登不上）。
  登录凭证写到 <沙盒目录>/e2e_token.txt，浏览器测试把它放进 localStorage。
- 为了不误伤真数据：目录里有 .git、.env，或者 users.json 里有别的用户，就直接退出。

文章 ID、单词在 vocab_summary_e2e.js 的 DATA 里也写了一份，两边要保持一致。
"""
import hashlib
import json
import secrets
import shutil
import sys
from pathlib import Path

USERNAME = "reader02"
PASSWORD = "tide pool 7 "   # 末尾有空格

LIGHTHOUSE = "20261020090000-The-Lighthouse-Keepers-Log"
FERRY = "20261019090000-Night-Ferry-Timetable"
COLD_CHAIN = "20261018090000-The-Cold-Chain"
RADIO = "20261015090000-Campus-Radio-Interview"


def u16(text):
    """页面上的下标是 JS 的 UTF-16 下标，高亮的 start/end 也按这个存。"""
    return len(text.encode("utf-16-le")) // 2


def content_html(text):
    paragraphs = [f"<p>{p.replace('<', '&lt;')}</p>" for p in text.split("\n") if p.strip()]
    return "\n".join(paragraphs)


def article(aid, title, category, created, lines, words=()):
    text = "\n".join(lines)
    highlights = []
    for n, (word, meaning) in enumerate(words, 1):
        i = text.index(word)
        start = u16(text[:i])
        highlights.append({"id": f"{aid[-6:]}-h{n}", "start": start, "end": start + u16(word), "text": word,
                           "meaning": meaning, "created_at": created})
    return {"id": aid, "title": title, "category": category, "created_at": created, "content_text": text,
            "content_html": content_html(text), "highlights": highlights, "images": []}


def articles():
    return [
        article(LIGHTHOUSE, "The Lighthouse Keeper’s Log", "Reading", "2026-10-20T09:00:00", [
            "The coast here is treacherous, and the beacon must burn all night.",
            "A solitary keeper stays at one's post through every gale.",
            "When supplies dwindle, he must keep watch and ration the provisions.",
            "Write <i>tide</i> in the margin when the foghorn sounds; the lamp is now automated.",
        ], [
            ("treacherous", "adj. 危险的；变化莫测的"), ("beacon", "n. 灯塔；信标"), ("solitary", "adj. 独自的"),
            ("one's post", "自己的岗位（带撇号）"), ("gale", "n. 大风"), ("dwindle", "v. 逐渐减少"),
            ("keep watch", "值守；守夜"), ("<i>tide</i>", "写成 <b>粗体</b> 的 \"潮水\""), ("automated", "adj. 自动化的"),
        ]),
        article(FERRY, "Night Ferry Timetable", "Reading", "2026-10-19T09:00:00", [
            "The night ferry left the berth late, so the crossing was rough.",
            "Passengers waited on the quay with a refund voucher.",
        ], [
            ("ferry", "n. 渡船"), ("berth", "n. 泊位；铺位"), ("crossing", "n. 横渡"), ("quay", "n. 码头"),
            ("refund", "n. 退款"), ("voucher", ""),
        ]),
        article(COLD_CHAIN, "The Cold Chain", "Reading", "2026-10-18T09:00:00", [
            "Perishable goods travel in refrigerated trucks; any delay means spoilage and a costly shipment loss.",
        ], [
            ("Perishable", "adj. 易腐烂的"), ("refrigerated", "adj. 冷藏的"), ("spoilage", "n. 变质"),
            ("shipment", "n. 货物；装运"), ("costly", "adj. 昂贵的"),
        ]),
        article(RADIO, "Campus Radio Interview", "Listening", "2026-10-15T09:00:00", [
            "The presenter asked about the seminar timetable and the lecture venue for the orientation week.",
        ], [
            ("seminar", "n. 研讨会"), ("venue", "n. 场地"), ("orientation", "n. 新生介绍"), ("presenter", "n. 主持人"),
        ]),
        article("20261010090000-The-Seed-Library", "The Seed Library", "Reading", "2026-10-10T09:00:00",
                ["Seeds are lent out like books."]),
        article("20261009090000-Floating-Schools", "Floating Schools", "Reading", "2026-10-09T09:00:00",
                ["Boats become classrooms in the wet season."]),
        article("20261008090000-Desert-Gardens", "Desert Gardens", "Reading", "2026-10-08T09:00:00",
                ["Gardens survive on very little water."]),
        article("20261007090000-Essay-Plan", "Essay Plan", "Writing", "2026-10-07T09:00:00",
                ["Some people think cities should ban cars."]),
    ]


def old_records():
    """以前的挑战记录：文章名是空的（旧页面一开始挑战就把选中的文章清掉了）"""
    return [{
        "id": "1761800000000", "timestamp": "2026-10-28T20:12:00", "article_ids": [LIGHTHOUSE], "article_titles": [],
        "total_questions": 2, "correct_count": 1, "accuracy": 50, "score": 45, "time_bonus": 9,
        "answers": [
            {"question_index": 0, "vocab": {"word": "gale", "meaning": "n. 大风", "article_id": LIGHTHOUSE},
             "selected_option": "n. 大风", "correct_answer": "n. 大风", "time_taken": 6, "is_correct": True,
             "question_type": "word_to_meaning"},
            {"question_index": 1, "vocab": {"word": "beacon", "meaning": "n. 灯塔；信标", "article_id": LIGHTHOUSE},
             "selected_option": "dwindle", "correct_answer": "beacon", "time_taken": 9, "is_correct": False,
             "question_type": "meaning_to_word"},
        ],
        "username": USERNAME, "saved_at": "2026-10-28T20:12:05",
    }]


def wrong_words():
    def item(word, meaning, count, when, aid=LIGHTHOUSE, title="The Lighthouse Keeper’s Log"):
        return {"word": word, "meaning": meaning, "article_title": title, "article_id": aid, "wrong_count": count,
                "last_wrong_at": when, "wrong_answers": []}
    rows = [
        item("beacon", "n. 灯塔；信标", 2, "2026-10-28T20:12:00"),
        item("one's post", "it's \"one's\" own post", 3, "2026-10-27T19:00:00"),
        item('<img src=x onerror="window.__xss=1">', "<script>window.__xss=2</script>", 1, "2026-10-26T19:00:00"),
    ]
    return {f"{w['word']}::{w['meaning']}": w for w in rows}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def check_target(root):
    if not root.is_dir():
        sys.exit(f"{root} 不是目录")
    if (root / ".git").exists() or (root / ".env").exists():
        sys.exit(f"{root} 里有 .git 或 .env，不像沙盒，不动它。")
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
        "username": USERNAME, "password": PASSWORD, "display_name": "词汇测试员",
        "role": "admin", "avatar": "avatar_admin.svg", "created_at": "2026-09-01T09:00:00"}})
    token = secrets.token_urlsafe(32)   # 和 core.create_token 存的格式一样
    write_json(root / "tokens.json", {token: {"created_time": "2026-10-31T09:00:00", "username": USERNAME}})
    (root / "e2e_token.txt").write_text(token, encoding="utf-8")

    for name in ("intensive_articles", "vocab_audio", "challenges"):
        shutil.rmtree(root / name, ignore_errors=True)
    (root / "intensive_articles" / "images").mkdir(parents=True)
    for a in articles():
        write_json(root / "intensive_articles" / f"{a['id']}.json", a)

    # 精读划词时生成的发音：只放一个（内容是假的，浏览器解不出来，页面应该接着去取有道的）
    audio = root / "vocab_audio" / LIGHTHOUSE / (hashlib.md5("treacherous".encode("utf-8")).hexdigest() + ".mp3")
    audio.parent.mkdir(parents=True)
    audio.write_bytes(b"ID3fake-treacherous")

    write_json(root / "challenges" / f"vocab_summary_{USERNAME}.json", old_records())
    write_json(root / "challenges" / f"wrong_words_{USERNAME}.json", wrong_words())
    print(f"写好了 {len(articles())} 篇编造的文章、1 条旧挑战记录、3 个错词 → {root}")


if __name__ == "__main__":
    main()

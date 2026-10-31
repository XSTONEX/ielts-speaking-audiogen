"""给首页浏览器测试造一份沙盒数据。数据全是编的，仓库是公开的，不放任何真实记录。

用法：python make_fake_data.py <沙盒目录> [--empty]
- 沙盒目录里应该已经有一份代码（git ls-files -co --exclude-standard 复制过去的），
  数据目录按相对路径建在它下面，和线上一样。
- 不带 --empty：各模块都有数据，首页每张卡片都有数字、有待复习、有「继续上次」。
- 带 --empty：只有一个新账号，用来看「还没有数据」时的样子。
- 登录凭证写到 <沙盒目录>/e2e_token.txt（用户 linxia「林夏」）。
"""
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta

NOW = datetime.now()


def ago(days=0, hours=0, minutes=0):
    return (NOW - timedelta(days=days, hours=hours, minutes=minutes)).isoformat()


def write(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def fake_mp3(path, seconds):
    """一个 128kbps MPEG1 Layer III 帧头 + 留空：服务器按文件大小估出时长；稀疏文件，几乎不占磁盘。"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(bytes([0xFF, 0xFB, 0x90, 0x00]))
        f.seek(16000 * seconds - 1)
        f.write(b"\0")


def users_and_token(root):
    write(root, "users.json", {
        "linxia": {"username": "linxia", "password": "not-used-in-e2e", "display_name": "林夏",
                   "role": "admin", "avatar": "avatar_admin.svg", "created_at": ago(days=60)},
        "zhouyu": {"username": "zhouyu", "password": "not-used-in-e2e", "display_name": "周屿",
                   "role": "user", "avatar": "avatar_admin.svg", "created_at": ago(days=60)},
    })
    token = secrets.token_urlsafe(24)
    write(root, "tokens.json", {token: {"created_time": NOW.isoformat(), "username": "linxia"}})
    with open(os.path.join(root, "e2e_token.txt"), "w") as f:
        f.write(token)


def speaking(root):
    topics = {
        "P1 Hometown": ["Where is your hometown?", "Do you like living there?"],
        "P1 Weather": ["What's the weather like today?", "Do you prefer hot or cold days?", "Does weather change your mood?"],
        "P2 A helpful neighbour": ["Describe a neighbour who helped you."],
        "P3 Technology": ["Has technology made people lonelier?", "Should children own phones?"],
    }
    for folder, questions in topics.items():
        for i, question in enumerate(questions):
            base = os.path.join(root, "audio_files", folder, f"answer_{i + 1}")
            fake_mp3(base + ".mp3", 40 + 10 * i)
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(question + "\nA made-up sample answer for testing the page layout.")


def intensive(root):
    articles = [
        ("Desert Ants Count Their Steps", ago(days=20), [ago(days=2)]),
        ("The Quiet Return of River Otters", ago(days=10), []),
        ("Why Glass Bends Light", ago(days=5), [ago(days=4)]),
    ]
    for title, created, marks in articles:
        article_id = created[:10].replace("-", "") + "-" + title.replace(" ", "-")
        text = f"{title}. This paragraph is made up for browser tests. It talks about patterns, evidence and change."
        write(root, f"intensive_articles/{article_id}.json", {
            "id": article_id, "title": title, "category": "Reading", "created_at": created,
            "content_text": text, "content_html": f"<p>{text}</p>",
            "highlights": [{"id": uuid.uuid4().hex[:12], "start": 0, "end": 6, "meaning": "示例释义",
                            "text": text[:6], "created_at": m} for m in marks],
            "images": [],
        })


def vocabulary(root):
    words = {
        "listening": ["itinerary", "refund", "deposit"],
        "speaking": ["hospitable", "nostalgic"],
        "reading": ["erode", "arid", "scarce", "vivid", "gauge"],
        "writing": ["cohesive", "mitigate"],
    }
    for category, items in words.items():
        write(root, f"vocabulary_book/categories/{category}.json", {
            "name": category.capitalize(),
            "subcategories": {"default": {"name": "默认分类", "created_at": ago(days=40), "words": [
                {"id": uuid.uuid4().hex, "word": w, "meaning": "示例释义", "created_at": ago(days=i * 3),
                 "is_favorited": i % 2 == 0, "audio_generated": False}
                for i, w in enumerate(items)
            ]}},
            "metadata": {"created_at": ago(days=40), "last_updated": ago(days=1)},
        })


def tips(root):
    counts = {("reading", "synonyms"): 6, ("writing", "synonyms"): 3, ("reading", "hypernyms"): 4,
              ("speaking", "techniques"): 2, ("listening", "techniques"): 1}
    for category in ("listening", "speaking", "reading", "writing"):
        for kind in ("synonyms", "hypernyms", "techniques"):
            n = counts.get((category, kind), 0)
            write(root, f"study_techniques/data/{category}_{kind}.json", [
                {"id": uuid.uuid4().hex, "title": f"示例 {i + 1}", "created_at": ago(days=i), "updated_at": ago(days=i)}
                for i in range(n)
            ])


def board(root):
    challenge_id = str(uuid.uuid4())
    linxia = {"username": "linxia", "display_name": "林夏", "avatar": "avatar_admin.svg", "role": "admin"}
    zhouyu = {"username": "zhouyu", "display_name": "周屿", "avatar": "avatar_admin.svg", "role": "user"}
    empty = {"audios": [], "articles": [], "images": []}
    write(root, "message_board/messages.json", [
        {"id": str(uuid.uuid4()), "type": "mixed_content", "timestamp": ago(days=6), "user": linxia,
         "content": {**empty, "text": "今天把沙漠蚂蚁那篇精读完了。", "challenge": None}},
        {"id": str(uuid.uuid4()), "type": "mixed_content", "timestamp": ago(days=3), "user": linxia,
         "content": {**empty, "text": "", "challenge": None,
                     "articles": [{"id": "x", "title": "Why Glass Bends Light", "category": "Reading", "highlight_count": 1}]}},
        {"id": str(uuid.uuid4()), "type": "mixed_content", "timestamp": ago(days=1), "user": zhouyu,
         "content": {**empty, "text": "", "challenge": {"id": challenge_id, "title": "第三周 PK", "description": "",
                                                        "vocabulary_count": 5, "mentioned_users": ["linxia"]}}},
    ])
    write(root, "message_board/comments.json", [])
    write(root, f"challenges/{challenge_id}.json", {
        "id": challenge_id, "title": "第三周 PK", "description": "", "creator": "zhouyu", "created_at": ago(days=1),
        "article_ids": [], "vocabulary": [{"word": w, "meaning": "示例释义"} for w in ("erode", "arid", "vivid", "gauge", "scarce")],
        "mentioned_users": ["linxia"], "participants": {}, "status": "active",
    })
    write(root, "challenges/wrong_words_linxia.json", {
        w: {"word": w, "meaning": "示例释义", "wrong_count": n, "last_wrong_at": ago(days=n),
            "article_id": "", "article_title": "", "wrong_answers": []}
        for w, n in (("scarce", 4), ("vivid", 3), ("gauge", 2), ("arid", 1), ("erode", 1))
    })


def writing(root):
    template = []
    for i, (zh, score) in enumerate([("城市化让住房更贵", "5.5"), ("政府应多投钱给公交", "5.0"),
                                     ("网络学习比课堂更灵活", "6.5"), ("运动能缓解学习压力", "7.0")]):
        template.append({"id": str(uuid.uuid4()), "timestamp": ago(hours=2 + i * 20), "task": "task2",
                         "type_name": "观点类", "section_name": "第二段", "sentence_index": i,
                         "target_chinese": zh + "。", "score": score, "in_review": float(score) < 6})
    write(root, "writing_correction/data/linxia_template_practice.json", template)
    write(root, "writing_correction/data/linxia_small_practice.json", [
        {"id": str(uuid.uuid4()), "timestamp": ago(days=9), "example_name": "Bus use", "section_name": "Overview",
         "target_chinese": "公交使用量明显上升。", "score": "6.5", "in_review": False}])
    write(root, "writing_correction/data/linxia_practice.json", [
        {"id": str(uuid.uuid4()), "timestamp": ago(days=12), "category": "Education", "subcategory": "Homework",
         "target_chinese": "作业太多会压垮学生。", "score": "5.0", "in_review": True}])


def listening(root):
    write(root, "listening_review/linxia_projects.json", [
        {"id": "lr_fake_campus", "title": "Campus Tour", "username": "linxia", "status": "completed", "mastered": False,
         "checkin_count": 3, "checkins": [ago(days=8), ago(days=1), ago(hours=5)],
         "created_at": ago(days=14), "updated_at": ago(days=1), "duration": 210},
        {"id": "lr_fake_museum", "title": "Museum Talk", "username": "linxia", "status": "completed", "mastered": True,
         "checkin_count": 2, "created_at": ago(days=20), "updated_at": ago(days=15), "duration": 180},
    ])


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    users_and_token(root)
    if "--empty" not in sys.argv[2:]:
        speaking(root)
        intensive(root)
        vocabulary(root)
        tips(root)
        board(root)
        writing(root)
        listening(root)
    print("沙盒数据已写到", root)


if __name__ == "__main__":
    main()

"""给口语音频库（/speaking、/combined）浏览器测试造一份沙盒数据。数据全是编的，仓库是公开的，不放任何真实录音和文本。

用法：python make_fake_data.py <沙盒目录> [--empty]
- 沙盒目录里应该已经有一份代码（git ls-files -co --exclude-standard 复制过去的），
  数据目录（audio_files/、combined_audio/）按相对路径建在它下面，和线上一样。会先清空这两个目录。
- 不带 --empty：四个 Part 都有话题，Part 2 带题卡问题（有一个故意没填），「其他」里有一篇 3000 多字的长文；
  另有三个话题提前做好了合集（含一个名字带英文单引号的，测 /combined 的按钮）。
- 带 --empty：只有账号，音频库是空的。
- 登录凭证写到 <沙盒目录>/e2e_token.txt（用户 linxia「林夏」）。

音频是真能播放的静音 MP3（128kbps / 44.1kHz 的空帧拼起来），浏览器能读出时长、触发 timeupdate / ended，
所以播放条、连播、拖动进度都能实测；服务器按文件大小估时长，和浏览器读到的一致。
"""
import json
import os
import secrets
import shutil
import sys
import time
from datetime import datetime

NOW = datetime.now()

# 一个 MPEG-1 Layer III 帧：128kbps、44.1kHz、联合立体声、无填充，帧长 417 字节，里面全是 0 = 一帧静音（1152 个采样）
FRAME = bytes([0xFF, 0xFB, 0x90, 0x64]) + bytes(413)
FRAMES_PER_SECOND = 44100 / 1152


def silent_mp3(seconds):
    return FRAME * max(1, round(seconds * FRAMES_PER_SECOND))


def write_json(root, rel, value):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def users_and_token(root):
    write_json(root, "users.json", {
        "linxia": {"username": "linxia", "password": "not-used-in-e2e", "display_name": "林夏",
                   "role": "admin", "avatar": "avatar_admin.svg", "created_at": NOW.isoformat()},
    })
    token = secrets.token_urlsafe(24)
    write_json(root, "tokens.json", {token: {"created_time": NOW.isoformat(), "username": "linxia"}})
    with open(os.path.join(root, "e2e_token.txt"), "w") as f:
        f.write(token)


LONG_TEXT = (
    "朗读材料：下面是一篇编出来的长文，用来测试手机上的全文阅读。\n\n"
    + "\n\n".join(
        f"Paragraph {i + 1}. The lighthouse keeper wrote in his notebook every evening, listing the ships he had seen, "
        "the colour of the sea and the direction of the wind. Nobody asked him to do it, but the habit gave shape to "
        "long and quiet days. Years later, a student found the notebooks in a box and used them to describe how "
        "the coast had slowly changed."
        for i in range(10)
    )
)

# (文件夹, 题卡问题或 None, [(问题, 答案, 秒数)])
# Part 1 / Part 3 的 txt 首行是问题；Part 2 和「其他」整篇都是答案。
TOPICS = [
    # 一批只有一两条的老话题，让列表长到手机上要滚好几屏
    *[(f"P1 - {name}", None, [(q, f"A made-up sample answer about {name.lower()} for testing the layout.", 5)
                               for q in qs])
      for name, qs in [
          ("Music", ["Do you listen to music while studying?"]),
          ("Sleep", ["How many hours do you usually sleep?", "Do you take naps?"]),
          ("Photography", ["Do you like taking photos?"]),
          ("Cooking", ["Can you cook?", "Who taught you to cook?"]),
          ("Public transport", ["How do you usually get around?"]),
          ("Plants", ["Do you keep any plants at home?"]),
          ("Shoes", ["Do you buy shoes online?"]),
          ("Names", ["Does your name have a special meaning?"]),
      ]],
    ("P1 - Weather", None, [
        ("What's the weather like where you live?", "It's mild most of the year, with a rainy season in early summer.", 6),
        ("Do you prefer hot or cold days?", "Cold days, because I can wear a coat and walk for hours without getting tired.", 7),
        ("Does the weather change your mood?", "A little. Grey mornings make me slow, but a sunny afternoon fixes that.", 6),
    ]),
    ("P1 - Children's games", None, [
        ("What games did you play as a child?", "Mostly hide and seek in the courtyard, and a paper boat race after rain.", 6),
        ("Do children today play the same games?", "Some do, but many of them would rather play on a tablet indoors.", 5),
    ]),
    ("P3 - 城市交通与环境保护的长期规划", None, [
        ("Should cities ban private cars from the centre?", "I think a gradual approach works better than a sudden ban, starting with weekends.", 9),
        ("Who should pay for public transport?", "It should be shared: riders pay a fair fare, and the city covers the rest from taxes.", 8),
        ("Will people really change their habits?", "Only if the alternative is faster and cheaper; good intentions alone rarely last.", 8),
    ]),
    ("朗读材料", None, [
        (None, LONG_TEXT, 12),
        (None, "A short note: practise linking sounds such as 'turn it off' and 'pick it up'.", 5),
    ]),
    ("P2 - 一座你想再去的海边城市", "Describe a coastal city you would like to visit again.\nYou should say:\nwhere it is\nwhen you went there\nwhat you did there\nand explain why you would like to go back.", [
        (None, "The city I'd love to revisit is a small harbour town in the south. I went there two summers ago with my cousin, "
               "and we spent most of our time cycling along the sea wall and eating grilled fish at night markets.", 14),
    ]),
    ("P1 - Being busy", None, [
        ("Are you busy these days?", "Yes, quite busy, because I'm preparing for an exam and working part-time.", 6),
        ("What do you do when you're busy?", "I write a short list every morning and only keep three things on it.", 6),
        ("Do you like being busy?", "In small doses. A busy week feels productive, but a busy month wears me out.", 7),
        ("How do you relax after a busy day?", "I go for a walk without my phone, which sounds simple but really helps.", 6),
    ]),
    ("P2 - A skill you learned online", None, [
        (None, "I'd like to talk about learning to edit short videos. I picked it up from free tutorials during a long holiday.", 10),
        (None, "Another time I practised the same answer more slowly, adding examples about the first video I made for my family.", 11),
    ]),
    ("P3 - Technology", None, [
        ("Has technology made people lonelier?", "In some ways yes, because we message instead of meeting, but it also keeps distant friends close.", 9),
        ("Should children have their own phones?", "Not too early. A basic phone for safety is fine; a smartphone can wait until they are older.", 9),
    ]),
    ("P2 - 一位乐于助人的邻居", "Describe a neighbour who helped you.\nYou should say:\nwho this person is\nhow you know them\nwhat they did\nand explain how you felt about it.", [
        (None, "I'm going to describe Mrs Chen, who lived across the hall from us. When my parents were away, she brought me dinner every evening.", 12),
        (None, "A second version: Mrs Chen also taught me how to fix a bicycle chain, which turned out to be surprisingly useful.", 10),
        (None, "A third, shorter version focusing on why I still visit her on holidays.", 6),
    ]),
    ("P1 - Hometown", None, [
        ("Where is your hometown?", "My hometown is a mid-sized city by a river, famous for its tea and old bridges.", 7),
        ("Do you like living there?", "Yes, I do. Life is calm, and everything I need is a short bike ride away.", 6),
        ("Is your hometown a good place for young people to pursue their careers?",
         "It's getting better. There are more design studios and small tech firms than there were five years ago.", 8),
        ("Did you learn about the culture of your hometown in your childhood?",
         "Yes, especially the local festivals. We used to make paper lanterns at school every autumn.", 8),
        ("Has your hometown changed much?", "Quite a lot. The old market became a park, and there is a new metro line.", 7),
        ("Would you like to live there in the future?", "Maybe after a few years abroad; it's a good place to raise a family.", 6),
    ]),
]

# 提前做好合集的话题（/combined 的「播放合集」能直接点）
COMBINED = ["P1 - Hometown", "P1 - Children's games", "P2 - 一位乐于助人的邻居"]


def speaking(root):
    audio_root = os.path.join(root, "audio_files")
    combined_root = os.path.join(root, "combined_audio")
    for d in (audio_root, combined_root):
        shutil.rmtree(d, ignore_errors=True)
        os.makedirs(d)
    # 按列表顺序一个个写：服务器按文件 ctime 排「最近使用」，最后写的话题排最前
    for index, (folder, cue_card, clips) in enumerate(TOPICS):
        folder_path = os.path.join(audio_root, folder)
        os.makedirs(folder_path)
        if cue_card:
            with open(os.path.join(folder_path, "question.txt"), "w", encoding="utf-8") as f:
                f.write(cue_card)
        for n, (question, answer, seconds) in enumerate(clips):
            stamp = f"202610{10 + index:02d}_{9 + n:02d}0000"
            base = os.path.join(folder_path, f"{folder}_{stamp}")
            with open(base + ".mp3", "wb") as f:
                f.write(silent_mp3(seconds))
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write((question + "\n" + answer) if question else answer)
            time.sleep(0.01)
        time.sleep(0.02)

    by_name = {t[0]: t for t in TOPICS}
    for folder in COMBINED:
        _, cue_card, clips = by_name[folder]
        kind = "part1" if folder.startswith("P1") else "part2" if folder.startswith("P2") else \
            "part3" if folder.startswith("P3") else "other"
        audio = b""
        subtitles = []
        t = 0.0
        for i, (question, answer, seconds) in enumerate(clips):
            if i:
                audio += silent_mp3(1)
                t += 1
            audio += silent_mp3(seconds)
            item = {"startTime": t, "endTime": t + seconds, "duration": seconds, "text": answer,
                    "filename": f"clip_{i + 1}.mp3"}
            if question:
                item["question"] = question
            if kind == "part2" and i == 0 and cue_card:
                item["question"] = cue_card
            subtitles.append(item)
            t += seconds
        with open(os.path.join(combined_root, folder + ".mp3"), "wb") as f:
            f.write(audio)
        write_json(root, os.path.join("combined_audio", folder + "_subtitles.json"),
                   {"type": kind, "folder": folder, "subtitles": subtitles})


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = os.path.abspath(sys.argv[1])
    if os.path.exists(os.path.join(root, ".git")):
        sys.exit(f"拒绝：{root} 是 git 仓库，请对复制出来的沙盒目录运行")
    users_and_token(root)
    if "--empty" in sys.argv[2:]:
        for d in ("audio_files", "combined_audio"):
            shutil.rmtree(os.path.join(root, d), ignore_errors=True)
            os.makedirs(os.path.join(root, d))
    else:
        speaking(root)
    print("沙盒数据已写到", root)


if __name__ == "__main__":
    main()

"""首页数据接口 /api/home 的口径测试。数据全是编的，不含真实做题记录。"""
import os
import unittest
from datetime import datetime, timedelta

from tests import test_learning_platform as platform_tests


def _week_start():
    now = datetime.now()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


class HomeSummaryTestCase(unittest.TestCase):
    # 借用学习平台测试的临时目录、登录和写文件工具；不继承，免得把那边的测试再跑一遍
    _base = platform_tests.LearningPlatformTestCase
    _patch_core_paths = _base._patch_core_paths
    _login = _base._login
    auth_headers = _base.auth_headers
    write_json = _base.write_json

    def setUp(self):
        self._base.setUp(self)
        import core

        # 时长缓存和学习技巧目录不在父类的路径表里，单独指到临时目录，免得碰到真实数据
        self._saved = (core._DURATION_CACHE_FILE, core._duration_cache, core.STUDY_TECHNIQUES_DATA_DIR)
        core._DURATION_CACHE_FILE = os.path.join(self.tmp, "durations.json")
        core._duration_cache = None
        core.STUDY_TECHNIQUES_DATA_DIR = os.path.join(self.tmp, "study_techniques", "data")
        self.paths["STUDY_TECHNIQUES_DATA_DIR"] = core.STUDY_TECHNIQUES_DATA_DIR

        start = _week_start()
        self.this_week = (start + timedelta(seconds=1)).isoformat()
        self.this_week_later = (start + timedelta(seconds=30)).isoformat()
        self.last_week = (start - timedelta(days=2)).isoformat()

    def tearDown(self):
        import core

        core._DURATION_CACHE_FILE, core._duration_cache, core.STUDY_TECHNIQUES_DATA_DIR = self._saved
        self._base.tearDown(self)

    def get_home(self):
        response = self.client.get("/api/home", headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        return data

    def touch(self, path, content=b""):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(content)

    def seed_all(self):
        p = self.paths
        # 口语：两个有音频的话题，一个空文件夹、一个隐藏文件夹都不算
        self.touch(os.path.join(p["MOTHER_DIR"], "P1 Hometown", "a.mp3"))
        self.touch(os.path.join(p["MOTHER_DIR"], "P1 Hometown", "a.txt"), b"Q\nanswer")
        self.touch(os.path.join(p["MOTHER_DIR"], "P1 Hometown", "b.mp3"))
        self.touch(os.path.join(p["MOTHER_DIR"], "P2 A gift", "c.mp3"))
        os.makedirs(os.path.join(p["MOTHER_DIR"], "P3 Empty"), exist_ok=True)
        self.touch(os.path.join(p["MOTHER_DIR"], ".trash", "d.mp3"))

        # 精读：较新的高亮决定「最近在读」，不看文章本身的新建时间
        self.write_json(os.path.join(p["INTENSIVE_DIR"], "older.json"), {
            "id": "older", "title": "Glass Making", "created_at": "2026-01-01T08:00:00",
            "highlights": [{"id": "h1", "created_at": "2026-03-05T08:00:00"}],
        })
        self.write_json(os.path.join(p["INTENSIVE_DIR"], "newer.json"), {
            "id": "newer", "title": "Desert Ants", "created_at": "2026-03-01T08:00:00", "highlights": [],
        })
        self.touch(os.path.join(p["INTENSIVE_DIR"], "broken.json"), b"{not json")

        # 写作：三栈各一份；这周 2 句，平均分只算有分数的
        self.write_json(os.path.join(p["WRITING_DATA_DIR"], "tester_practice.json"), [
            {"id": "w1", "timestamp": self.last_week, "category": "Education", "subcategory": "Homework",
             "target_chinese": "作业太多。", "score": "5.0", "in_review": True},
        ])
        self.write_json(os.path.join(p["WRITING_DATA_DIR"], "tester_small_practice.json"), [
            {"id": "w2", "timestamp": self.this_week, "example_name": "Bus use", "section_name": "Overview",
             "target_chinese": "公交使用量上升。", "score": "7.0", "in_review": True},
        ])
        self.write_json(os.path.join(p["WRITING_DATA_DIR"], "tester_template_practice.json"), [
            {"id": "w3", "timestamp": self.this_week_later, "type_name": "观点类", "section_name": "第二段",
             "target_chinese": "城市越来越拥挤。", "score": "5.5", "in_review": True},
            {"id": "w4", "timestamp": self.last_week, "type_name": "观点类", "section_name": "第一段",
             "target_chinese": "没进复习本的低分句。", "score": "4.0", "in_review": False},
            {"id": "w5", "timestamp": self.last_week, "type_name": "观点类", "section_name": "第一段",
             "target_chinese": "没打分。", "score": "", "in_review": True},
        ])

        # 听力：只有「转录完成、还没标熟」的进待复习；本周打卡按记下的打卡时间算
        self.write_json(os.path.join(p["LISTENING_REVIEW_DIR"], "tester_projects.json"), [
            {"id": "lr-a", "title": "Campus Tour", "status": "completed", "mastered": False,
             "checkin_count": 3, "checkins": [self.last_week, self.this_week, self.this_week_later],
             "created_at": "2026-02-01T08:00:00", "updated_at": self.this_week},
            {"id": "lr-b", "title": "Museum Talk", "status": "completed", "mastered": True,
             "checkin_count": 2, "created_at": "2026-02-02T08:00:00", "updated_at": "2026-02-03T08:00:00"},
            {"id": "lr-c", "title": "Still Processing", "status": "processing",
             "created_at": "2026-02-04T08:00:00", "updated_at": "2026-02-04T08:00:00"},
        ])

        # 单词本：三个词，一个收藏、两个这周加的
        self.write_json(os.path.join(p["VOCABULARY_CATEGORIES_DIR"], "reading.json"), {
            "name": "Reading", "subcategories": {"default": {"name": "Default", "words": [
                {"id": "v1", "word": "erode", "created_at": self.last_week, "is_favorited": True},
                {"id": "v2", "word": "arid", "created_at": self.this_week},
            ]}},
        })
        self.write_json(os.path.join(p["VOCABULARY_CATEGORIES_DIR"], "writing.json"), {
            "name": "Writing", "subcategories": {"s": {"name": "S", "words": [
                {"id": "v3", "word": "cohesive", "created_at": self.this_week},
            ]}},
        })

        # 学习技巧：上传示例文件不算
        tips = p["STUDY_TECHNIQUES_DATA_DIR"]
        self.write_json(os.path.join(tips, "reading_synonyms.json"), [{}, {}])
        self.write_json(os.path.join(tips, "writing_synonyms.json"), [{}])
        self.write_json(os.path.join(tips, "reading_hypernyms.json"), [{}])
        self.write_json(os.path.join(tips, "speaking_techniques.json"), [{}, {}, {}])
        self.write_json(os.path.join(tips, "synonym_upload_example.json"), {"groups": [{}, {}]})

        # 交流区：最新一帖是发起挑战
        self.write_json(os.path.join(p["MESSAGE_BOARD_DIR"], "messages.json"), [
            {"id": "m1", "type": "mixed_content", "timestamp": "2026-03-01T08:00:00",
             "user": {"username": "tester", "display_name": "Test User"},
             "content": {"text": "  今天读完了\n一篇  ", "articles": [], "audios": [], "images": []}},
            {"id": "m2", "type": "mixed_content", "timestamp": "2026-03-02T08:00:00",
             "user": {"username": "friend", "display_name": "Friend"},
             "content": {"text": "", "challenge": {"id": "c-pending", "title": "Week 3 PK"},
                         "articles": [], "audios": [], "images": []}},
        ])

        # 挑战：只有第一个算「待完成」
        challenges = p["CHALLENGES_DIR"]
        base = {"vocabulary": [{"word": "x"}], "participants": {}, "status": "active"}
        self.write_json(os.path.join(challenges, "c-pending.json"),
                        {**base, "creator": "friend", "mentioned_users": ["tester"]})
        self.write_json(os.path.join(challenges, "c-done-by-me.json"),
                        {**base, "creator": "friend", "mentioned_users": ["tester", "third"],
                         "participants": {"tester": {"score": 80}}})
        self.write_json(os.path.join(challenges, "c-finished.json"),
                        {**base, "creator": "friend", "mentioned_users": ["tester"], "status": "completed"})
        self.write_json(os.path.join(challenges, "c-not-for-me.json"),
                        {**base, "creator": "friend", "mentioned_users": ["third"]})
        self.write_json(os.path.join(challenges, "vocab_summary_tester.json"), [{"id": "r1"}])
        # 错词本：答错次数多的排前面
        self.write_json(os.path.join(challenges, "wrong_words_tester.json"), {
            "gauge": {"word": "gauge", "wrong_count": 1, "last_wrong_at": "2026-03-03T08:00:00"},
            "scarce": {"word": "scarce", "wrong_count": 4, "last_wrong_at": "2026-03-01T08:00:00"},
            "vivid": {"word": "vivid", "wrong_count": 2, "last_wrong_at": "2026-03-02T08:00:00"},
        })

    def test_home_requires_login(self):
        self.assertEqual(self.client.get("/api/home").status_code, 401)

    def test_new_account_gets_zeros_not_errors(self):
        data = self.get_home()

        self.assertEqual(data["week"], {"writing": 0, "vocabulary": 0, "listening_checkins": 0})
        self.assertIsNone(data["resume"])
        self.assertEqual(data["speaking"], {"topics": 0, "audios": 0, "seconds": 0})
        self.assertEqual(data["intensive"], {"articles": 0, "latest_title": ""})
        self.assertEqual(data["writing"], {"total": 0, "week": 0, "avg_score": None})
        self.assertEqual(data["listening"], {"projects": 0, "unmastered": 0, "checkins": 0, "week_checkins": 0})
        self.assertEqual(data["vocabulary"], {"words": 0, "favorites": 0, "week": 0})
        self.assertEqual(data["tips"], {"synonyms": 0, "hypernyms": 0, "techniques": 0})
        self.assertEqual(data["board"], {"posts": 0, "pending_challenges": 0, "latest": None})
        self.assertEqual(data["review"]["total"], 0)
        self.assertEqual(data["review"]["items"], [])

    def test_module_numbers(self):
        self.seed_all()
        data = self.get_home()

        self.assertEqual(data["speaking"]["topics"], 2)
        self.assertEqual(data["speaking"]["audios"], 3)
        self.assertEqual(data["intensive"], {"articles": 2, "latest_title": "Glass Making"})
        self.assertEqual(data["writing"], {"total": 5, "week": 2, "avg_score": 5.4})
        self.assertEqual(data["listening"], {"projects": 3, "unmastered": 1, "checkins": 5, "week_checkins": 2})
        self.assertEqual(data["vocabulary"], {"words": 3, "favorites": 1, "week": 2})
        self.assertEqual(data["tips"], {"synonyms": 3, "hypernyms": 1, "techniques": 3})
        self.assertEqual(data["week"], {"writing": 2, "vocabulary": 2, "listening_checkins": 2})

    def test_board_latest_post_and_pending_challenges(self):
        self.seed_all()
        board = self.get_home()["board"]

        self.assertEqual(board["posts"], 2)
        self.assertEqual(board["pending_challenges"], 1)
        self.assertEqual(board["latest"]["who"], "Friend")
        self.assertEqual(board["latest"]["text"], "发起了词汇挑战：Week 3 PK")
        self.assertEqual(board["latest"]["kind"], "challenge")

    def test_board_latest_text_is_collapsed(self):
        self.seed_all()
        os.remove(os.path.join(self.paths["CHALLENGES_DIR"], "c-pending.json"))
        self.write_json(os.path.join(self.paths["MESSAGE_BOARD_DIR"], "messages.json"), [
            {"id": "m1", "timestamp": "2026-03-01T08:00:00", "user": {"display_name": "Test User"},
             "content": {"text": "  今天读完了\n一篇  "}},
        ])
        board = self.get_home()["board"]

        self.assertEqual(board["latest"]["text"], "今天读完了 一篇")
        self.assertEqual(board["latest"]["kind"], "text")
        self.assertEqual(board["pending_challenges"], 0)

    def test_review_mixes_sources_and_counts_everything(self):
        self.seed_all()
        review = self.get_home()["review"]

        # 错词 3 个；写作只算进了复习本、低于 6 分、有分数的（w1 5.0、w3 5.5）；听力 lr-a
        self.assertEqual(review["counts"], {"vocabulary": 3, "writing": 2, "listening": 1})
        self.assertEqual(review["total"], 6)
        self.assertEqual(
            [(item["source"], item["title"]) for item in review["items"]],
            [
                ("vocabulary", "scarce"),
                ("writing", "作业太多。"),
                ("listening", "Campus Tour"),
                ("vocabulary", "vivid"),
                ("writing", "城市越来越拥挤。"),
                ("vocabulary", "gauge"),
            ],
        )
        self.assertEqual(review["items"][0]["wrong_count"], 4)
        self.assertEqual(review["items"][1]["score"], 5.0)
        self.assertEqual(review["items"][2]["url"], "/listening_review?project=lr-a")

    def test_favorites_are_not_review_items(self):
        self.seed_all()
        os.remove(os.path.join(self.paths["CHALLENGES_DIR"], "wrong_words_tester.json"))
        review = self.get_home()["review"]

        self.assertEqual(review["counts"]["vocabulary"], 0)

    def test_review_preview_stops_at_six_but_total_does_not(self):
        self.seed_all()
        self.write_json(os.path.join(self.paths["CHALLENGES_DIR"], "wrong_words_tester.json"), {
            f"w{i}": {"word": f"w{i}", "wrong_count": 1} for i in range(30)
        })
        review = self.get_home()["review"]

        self.assertEqual(len(review["items"]), 6)
        self.assertEqual(review["total"], 30 + 2 + 1)

    def test_resume_is_the_latest_thing_practised(self):
        self.seed_all()
        resume = self.get_home()["resume"]

        self.assertEqual(resume["module"], "writing")
        self.assertEqual(resume["title"], "模板写作 · 观点类 · 第二段")
        self.assertEqual(resume["sentence"], "城市越来越拥挤。")
        self.assertEqual(resume["score"], 5.5)
        self.assertEqual(resume["at"], self.this_week_later)

    def test_resume_falls_back_to_listening(self):
        self.seed_all()
        for name in ("practice", "small_practice", "template_practice"):
            os.remove(os.path.join(self.paths["WRITING_DATA_DIR"], f"tester_{name}.json"))
        resume = self.get_home()["resume"]

        self.assertEqual(resume["module"], "listening")
        self.assertEqual(resume["title"], "Campus Tour")
        self.assertEqual(resume["checkins"], 3)
        self.assertEqual(resume["url"], "/listening_review?project=lr-a")

    def test_checkin_is_counted_this_week(self):
        self.seed_all()
        response = self.client.post("/api/listening_review/project/lr-b/checkin", headers=self.auth_headers())
        self.assertEqual(response.status_code, 200)

        listening = self.get_home()["listening"]
        self.assertEqual(listening["checkins"], 6)
        self.assertEqual(listening["week_checkins"], 3)

    def test_home_page_is_plain_and_hides_retired_entries(self):
        html = self.client.get("/").get_data(as_text=True)

        self.assertIn("/static/plain.css", html)
        self.assertIn("/static/app-shell.js", html)
        self.assertIn("/api/home", html)
        self.assertNotIn('data-app-shell="off"', html)
        # 合集播放和 Reading 真题不给入口，网址照常能开
        self.assertNotIn('href="/combined"', html)
        self.assertNotIn('href="/reading"', html)
        for href in ("/speaking", "/intensive", "/writing_practice", "/listening_review",
                     "/vocabulary", "/study_techniques", "/message_board"):
            self.assertIn(f'href="{href}"', html)
        self.assertEqual(self.client.get("/combined").status_code, 200)
        self.assertEqual(self.client.get("/reading").status_code, 200)


if __name__ == "__main__":
    unittest.main()

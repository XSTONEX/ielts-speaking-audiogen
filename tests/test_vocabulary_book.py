"""单词本后端的回归测试：CSV 导入（表头、大写扩展名、单列文件）和「加词不再调 TTS」。

数据目录都指到临时目录（沿用 test_auth_guard 的 AppTestBase），单词都是编的；
requests.post 被换成会报错的桩，万一有代码去调付费 TTS，测试会直接失败。
"""

import io
import json
import os
import unittest
from unittest import mock

from test_auth_guard import AppTestBase


def _no_network(*args, **kwargs):
    raise AssertionError("测试里不应该发出网络请求")


class VocabularyBookTest(AppTestBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("requests.post", side_effect=_no_network)
        patcher.start()
        self.addCleanup(patcher.stop)
        # 先放好一个听力分类文件（线上每个分类都已经有文件，测试照这个情况来）
        os.makedirs(self.core.VOCABULARY_CATEGORIES_DIR, exist_ok=True)
        with open(os.path.join(self.core.VOCABULARY_CATEGORIES_DIR, "listening.json"), "w", encoding="utf-8") as f:
            json.dump({
                "name": "Listening", "icon": "🎧",
                "subcategories": {"default": {"name": "默认分类", "created_at": "2026-10-01T09:00:00", "words": []}},
                "metadata": {"created_at": "2026-10-01T09:00:00", "last_updated": "2026-10-01T09:00:00"},
            }, f, ensure_ascii=False)

    def words(self, category="listening", subcategory_id="default"):
        response = self.client.get("/api/vocabulary", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        data = response.get_json()["data"]
        return data["categories"][category]["subcategories"][subcategory_id]["words"]

    def upload(self, content, filename="words.csv", category="listening", subcategory_id="default"):
        return self.client.post(
            "/api/vocabulary/upload_csv",
            headers=self.auth(),
            data={
                "file": (io.BytesIO(content.encode("utf-8")), filename),
                "category": category,
                "subcategory_id": subcategory_id,
            },
            content_type="multipart/form-data",
        )

    def task_files(self):
        tasks_dir = self.core.VOCABULARY_TASKS_DIR
        return os.listdir(tasks_dir) if os.path.isdir(tasks_dir) else []

    def test_reimporting_an_exported_csv_skips_the_header_row(self):
        # 页面导出的格式：BOM + 表头 + 每格加双引号，释义里的双引号写成两个
        exported = '﻿单词,词义\r\n"say ""hi"", then leave","打招呼后离开"\r\n"abundant","adj. 丰富的"\r\n'
        response = self.upload(exported)
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        self.assertEqual(body["added_count"], 2)
        self.assertEqual(body["invalid_count"], 0)
        words = {w["word"]: w["meaning"] for w in self.words()}
        self.assertNotIn("单词", words)
        self.assertEqual(words['say "hi", then leave'], "打招呼后离开")
        self.assertEqual(words["abundant"], "adj. 丰富的")

    def test_english_header_is_skipped_but_a_real_first_word_is_kept(self):
        response = self.upload("word,meaning\ncanteen,n. 食堂\n")
        self.assertEqual(response.get_json()["added_count"], 1)
        response = self.upload("words,n. 词语（复数）\n", subcategory_id="default")
        # 第二列不是「释义 / meaning」这类表头字样时，第一行就是普通单词
        self.assertEqual(response.get_json()["added_count"], 1)
        self.assertEqual(sorted(w["word"] for w in self.words()), ["canteen", "words"])

    def test_uppercase_csv_extension_is_accepted(self):
        response = self.upload("hazard,n. 危险\n", filename="WEEK3.CSV")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["added_count"], 1)

    def test_non_csv_file_is_still_rejected(self):
        response = self.upload("hazard,n. 危险\n", filename="week3.txt")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.words(), [])

    def test_single_column_csv_gets_a_clear_error_instead_of_importing_nothing(self):
        # 中文逗号分隔 = 整行只有一列
        response = self.upload("abundant，adj. 丰富的\nacquire\n")
        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertIn("两列", body["error"])
        self.assertEqual(body["invalid_count"], 2)
        self.assertEqual(self.words(), [])

    def test_mixed_file_imports_good_rows_and_counts_the_rest(self):
        response = self.upload("abundant,adj. 丰富的\nacquire\n,\nportable,\n")
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()
        # portable 没写释义但有两列，照样导入；acquire 只有一列，算缺列；空行忽略
        self.assertEqual(body["added_count"], 2)
        self.assertEqual(body["invalid_count"], 1)

    def test_duplicates_inside_the_subcategory_are_still_skipped(self):
        self.upload("seminar,n. 研讨会\n")
        response = self.upload("Seminar,n. 研讨会\nrefund,n. 退款\n")
        body = response.get_json()
        self.assertEqual(body["added_count"], 1)
        self.assertEqual(body["skipped_count"], 1)
        self.assertEqual(body["skipped_words"], ["Seminar"])

    def test_adding_or_importing_words_queues_no_tts_audio(self):
        response = self.client.post("/api/vocabulary/add", headers=self.auth(),
                                    json={"category": "listening", "subcategory_id": "default",
                                          "word": "landfill", "meaning": "n. 垃圾填埋场"})
        self.assertEqual(response.status_code, 200, response.get_json())
        word = response.get_json()["data"]
        self.assertFalse(word["audio_generated"])   # 字段保留，旧数据格式不变
        self.upload("warehouse,n. 仓库\n")
        self.assertEqual(self.task_files(), [])

    def test_old_tts_audio_is_still_served_as_a_fallback(self):
        response = self.client.post("/api/vocabulary/add", headers=self.auth(),
                                    json={"category": "listening", "subcategory_id": "default",
                                          "word": "specimen", "meaning": "n. 样本"})
        word_id = response.get_json()["data"]["id"]
        audio_dir = os.path.join(self.core.VOCABULARY_AUDIO_DIR, "listening")
        os.makedirs(audio_dir, exist_ok=True)
        with open(os.path.join(audio_dir, f"{word_id}.mp3"), "wb") as f:
            f.write(b"ID3fake-mp3")
        response = self.client.get(f"/vocabulary_audio/{word_id}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"ID3fake-mp3")
        response.close()

    def add(self, word, category="listening"):
        return self.client.post("/api/vocabulary/add", headers=self.auth(),
                                json={"category": category, "subcategory_id": "default",
                                      "word": word, "meaning": "示例释义"})

    def test_first_word_in_a_category_without_a_file_is_saved(self):
        # 新装好、或者某个分类从没加过词时，分类文件还不存在：以前这里报 500，还留下半截文件
        path = os.path.join(self.core.VOCABULARY_CATEGORIES_DIR, "reading.json")
        self.assertFalse(os.path.exists(path))
        response = self.add("arid", category="reading")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual([w["word"] for w in self.words("reading")], ["arid"])
        self.assertEqual(self.read_json(path)["icon"], "📖")

    def test_every_category_can_start_from_no_file(self):
        for category in ("speaking", "reading", "writing"):
            with self.subTest(category=category):
                self.assertEqual(self.add("first", category=category).status_code, 200)

    def test_a_failed_save_keeps_the_words_already_on_disk(self):
        self.assertEqual(self.add("refund").status_code, 200)
        # 写到一半出错（磁盘满、编码出错）：以前先把文件清空再写，旧词全丢
        with mock.patch("json.dump", side_effect=RuntimeError("disk full")):
            self.assertEqual(self.add("deposit").status_code, 500)
        self.assertEqual([w["word"] for w in self.words()], ["refund"])

    # ---------- 编辑单词（以前只能删了重加，收藏和挑战记录跟着丢） ----------

    def edit(self, word_id, **fields):
        return self.client.put(f"/api/vocabulary/{word_id}", headers=self.auth(), json=fields)

    def word_by_id(self, word_id, category="listening"):
        data = self.read_json(os.path.join(self.core.VOCABULARY_CATEGORIES_DIR, f"{category}.json"))
        for sub in data["subcategories"].values():
            for w in sub["words"]:
                if w["id"] == word_id:
                    return w
        return None

    def test_editing_keeps_the_id_favourite_and_date(self):
        word = self.add("accomodation").get_json()["data"]
        self.client.put(f"/api/vocabulary/{word['id']}/favorite", headers=self.auth(), json={"is_favorited": True})
        response = self.edit(word["id"], word="  accommodation ", meaning="  n. 住处 ")
        self.assertEqual(response.status_code, 200, response.get_json())
        body = response.get_json()["data"]
        self.assertEqual((body["id"], body["word"], body["meaning"]), (word["id"], "accommodation", "n. 住处"))
        stored = self.word_by_id(word["id"])
        self.assertEqual(stored["word"], "accommodation")
        self.assertEqual(stored["meaning"], "n. 住处")
        self.assertTrue(stored["is_favorited"])
        self.assertEqual(stored["created_at"], word["created_at"])
        self.assertEqual(len(self.words()), 1)

    def test_only_the_fields_sent_are_changed(self):
        word_id = self.add("seminar").get_json()["data"]["id"]
        self.assertEqual(self.edit(word_id, meaning="n. 研讨会").status_code, 200)
        self.assertEqual(self.word_by_id(word_id)["word"], "seminar")
        self.assertEqual(self.edit(word_id, word="seminars").status_code, 200)
        self.assertEqual(self.word_by_id(word_id)["meaning"], "n. 研讨会")
        # 释义可以清空（加词时也可以不填）
        self.assertEqual(self.edit(word_id, meaning="").status_code, 200)
        self.assertEqual(self.word_by_id(word_id)["meaning"], "")
        response = self.edit(word_id)
        self.assertEqual(response.status_code, 400)
        self.assertIn("没有要修改", response.get_json()["error"])

    def test_empty_or_non_text_word_is_rejected_and_nothing_changes(self):
        word_id = self.add("deposit").get_json()["data"]["id"]
        for bad in ("", "   ", None, 42):
            with self.subTest(word=bad):
                response = self.edit(word_id, word=bad, meaning="被拒绝的释义")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.get_json()["error"], "单词不能为空")
        self.assertEqual(self.edit(word_id, meaning=["x"]).status_code, 400)
        stored = self.word_by_id(word_id)
        self.assertEqual((stored["word"], stored["meaning"]), ("deposit", "示例释义"))

    def test_duplicates_are_refused_only_inside_the_same_subcategory(self):
        refund = self.add("refund").get_json()["data"]["id"]
        deposit = self.add("deposit").get_json()["data"]["id"]
        response = self.edit(deposit, word="Refund")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "单词在该子分类中已存在")
        self.assertEqual(self.word_by_id(deposit)["word"], "deposit")
        # 只改自己的大小写不算重复
        self.assertEqual(self.edit(refund, word="Refund").status_code, 200)
        # 别的子分类里有同一个词没关系（加词也是这样）
        other = self.client.post("/api/vocabulary/subcategories", headers=self.auth(),
                                 json={"category": "listening", "name": "第二组"}).get_json()["data"]["id"]
        moved = self.client.post("/api/vocabulary/add", headers=self.auth(),
                                 json={"category": "listening", "subcategory_id": other,
                                       "word": "rebate", "meaning": ""}).get_json()["data"]["id"]
        self.assertEqual(self.edit(moved, word="deposit").status_code, 200)

    def test_unknown_word_is_404(self):
        response = self.edit("no-such-id", word="anything")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.get_json()["error"], "单词不存在")

    def test_new_spelling_drops_the_old_tts_audio_but_meaning_or_case_edits_keep_it(self):
        word_id = self.add("questionaire").get_json()["data"]["id"]
        # 旧数据：以前加词时用 TTS 生成过音频，还可能留着一个没跑完的生成任务
        path = os.path.join(self.core.VOCABULARY_CATEGORIES_DIR, "listening.json")
        data = self.read_json(path)
        data["subcategories"]["default"]["words"][0]["audio_generated"] = True
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        audio_dir = os.path.join(self.core.VOCABULARY_AUDIO_DIR, "listening")
        os.makedirs(audio_dir, exist_ok=True)
        audio_path = os.path.join(audio_dir, f"{word_id}.mp3")
        with open(audio_path, "wb") as f:
            f.write(b"ID3old-word")
        os.makedirs(self.core.VOCABULARY_TASKS_DIR, exist_ok=True)
        with open(os.path.join(self.core.VOCABULARY_TASKS_DIR, "t1.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "t1", "word_id": word_id, "word": "questionaire", "status": "pending"}, f)
        with open(os.path.join(self.core.VOCABULARY_TASKS_DIR, "t2.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "t2", "word_id": "someone-else", "word": "other", "status": "pending"}, f)

        # 只改释义、只改大小写或空白：读音不变，旧音频留着
        self.assertEqual(self.edit(word_id, meaning="n. 问卷").status_code, 200)
        self.assertEqual(self.edit(word_id, word=" Questionaire ").status_code, 200)
        self.assertTrue(os.path.exists(audio_path))
        self.assertTrue(self.word_by_id(word_id)["audio_generated"])
        self.assertEqual(sorted(self.task_files()), ["t1.json", "t2.json"])

        # 拼写改了：旧音频读的是错词，删掉；页面以后只用有道按新拼写读
        response = self.edit(word_id, word="questionnaire")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertFalse(response.get_json()["data"]["audio_generated"])
        self.assertFalse(os.path.exists(audio_path))
        self.assertFalse(self.word_by_id(word_id)["audio_generated"])
        self.assertEqual(self.task_files(), ["t2.json"])
        response = self.client.get(f"/vocabulary_audio/{word_id}")
        self.assertEqual(response.status_code, 404)
        response.close()

    def test_challenge_coverage_stays_attached_after_editing(self):
        word_id = self.add("itinerary").get_json()["data"]["id"]
        response = self.client.post("/api/vocabulary/challenge/record", headers={**self.auth(), "X-Current-User": "tester"},
                                    json={"results": [{"word_id": word_id, "is_correct": True}]})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.edit(word_id, word="itineraries", meaning="n. 行程").status_code, 200)
        coverage = self.client.get("/api/vocabulary/challenge/coverage",
                                   headers={**self.auth(), "X-Current-User": "tester"}).get_json()["data"]
        self.assertEqual(coverage[word_id]["appear_count"], 1)

    def test_editing_needs_login(self):
        word_id = self.add("ferry").get_json()["data"]["id"]
        response = self.client.put(f"/api/vocabulary/{word_id}", json={"word": "ferries"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.word_by_id(word_id)["word"], "ferry")


if __name__ == "__main__":
    unittest.main()

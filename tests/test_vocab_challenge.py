"""词汇汇总的挑战和单词发音。

- 开一局挑战不再给每个词调一次付费 TTS（以前每局都起一个线程，逐词生成到新的 challenge_<id> 文件夹，
  可这些词在精读划高亮时已经有发音了）。页面现在直接放 /vocab_audio/<文章ID>/<词>，没有就用有道。
- /vocab_audio/<文章>/<词> 不用登录就能访问，以前请求一个不存在的文章也会建一个空文件夹。

文章和单词都是编的。
"""

import os
import types
import unittest
from unittest import mock

from test_auth_guard import AppTestBase


def _no_network(*args, **kwargs):
    raise AssertionError("测试里不应该发出网络请求")


class VocabSummaryChallengeTest(AppTestBase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch("requests.post", side_effect=_no_network)
        patcher.start()
        self.addCleanup(patcher.stop)

        import routers.community as community
        # 记下挑战接口起的后台线程和 TTS 调用，但都不真的执行
        self.threads = []
        self.tts_words = []
        test = self

        class RecordingThread:
            def __init__(self, target=None, *args, **kwargs):
                test.threads.append(target)

            def start(self):
                pass

        self._patch(community, "threading", types.SimpleNamespace(Thread=RecordingThread))
        self._patch(community, "generate_challenge_vocab_audio", lambda challenge_id, word: self.tts_words.append(word))

        self.content = "The night ferry left the berth at dawn. Its cargo was perishable fruit."
        self.article_id = self.create_article("Night Ferry", self.content)
        for word, meaning in (("ferry", "n. 渡船"), ("berth", "n. 泊位"), ("perishable", "adj. 易腐烂的")):
            self.highlight(word, meaning)

    def create_article(self, title, content):
        response = self.client.post("/intensive_create", headers=self.auth(),
                                    json={"title": title, "category": "Reading", "content": content})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["id"]

    def highlight(self, word, meaning):
        start = self.content.index(word)   # 全是 ASCII，Python 下标和页面的 UTF-16 下标一样
        response = self.client.post("/intensive_add_highlight", headers=self.auth(), json={
            "id": self.article_id, "start": start, "end": start + len(word), "text": word, "meaning": meaning})
        self.assertEqual(response.status_code, 200, response.get_json())

    def test_new_challenge_starts_no_tts_thread(self):
        response = self.client.post("/api/vocab_summary_challenge", headers=self.auth(),
                                    json={"article_ids": [self.article_id], "word_count": 5})
        self.assertEqual(response.status_code, 200, response.get_json())
        challenge = response.get_json()["challenge"]
        self.assertEqual(sorted(v["word"] for v in challenge["vocabulary"]), ["berth", "ferry", "perishable"])
        # 页面放发音要靠每个词带着的文章 ID
        self.assertEqual({v["article_id"] for v in challenge["vocabulary"]}, {self.article_id})
        self.assertEqual(self.threads, [])
        self.assertEqual(self.tts_words, [])
        self.assertFalse([d for d in os.listdir(self.core.VOCAB_AUDIO_DIR) if d.startswith("challenge_")])

    def test_missing_word_audio_leaves_no_empty_folder(self):
        response = self.client.get("/vocab_audio/never-made-article/hello")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(os.path.exists(os.path.join(self.core.VOCAB_AUDIO_DIR, "never-made-article")))

    def test_word_audio_made_when_highlighting_is_still_served(self):
        path = self.core.get_vocab_audio_path(self.article_id, "berth")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(b"ID3fake-berth")
        response = self.client.get(f"/vocab_audio/{self.article_id}/berth")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"ID3fake-berth")
        response.close()

    def test_generated_audio_still_lands_in_a_new_folder(self):
        # 目录改成写文件时才建：生成发音的路径照样能写进一个还不存在的文件夹
        fake = types.SimpleNamespace(status_code=200, content=b"ID3fake-dawn")
        with mock.patch("core.requests.post", return_value=fake):
            path = self.core.generate_and_save_vocab_audio("brand-new-article", "dawn")
        self.assertTrue(path and os.path.isfile(path))
        with open(path, "rb") as f:
            self.assertEqual(f.read(), b"ID3fake-dawn")


if __name__ == "__main__":
    unittest.main()

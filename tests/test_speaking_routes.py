"""口语音频库的两处后端修复。数据全是编的。

- 合集页请求 /combined_audio/<话题>.mp3，以前路由又拼一次 .mp3，找的是 <话题>.mp3.mp3，永远 404。
- Part 2 新话题生成失败时不能留下只有 question.txt 的空文件夹（下次打开生成面板会显示「已填写（已存在）」）。
"""
import os
import unittest
from unittest import mock

from tests import test_learning_platform as platform_tests


class SpeakingRoutesTestCase(unittest.TestCase):
    # 借用学习平台测试的临时目录、登录和写文件工具；不继承，免得把那边的测试再跑一遍
    _base = platform_tests.LearningPlatformTestCase
    _patch_core_paths = _base._patch_core_paths
    _login = _base._login
    auth_headers = _base.auth_headers

    def setUp(self):
        self._base.setUp(self)
        import routers.speaking as speaking
        import routers.speaking_playlist as playlist

        # 这两个路由模块在导入时就把目录名抄走了，单独指到临时目录，免得碰到真实数据
        self._saved = (speaking.MOTHER_DIR, playlist.MOTHER_DIR, playlist.COMBINED_DIR)
        speaking.MOTHER_DIR = self.paths["MOTHER_DIR"]
        playlist.MOTHER_DIR = self.paths["MOTHER_DIR"]
        playlist.COMBINED_DIR = self.paths["COMBINED_DIR"]
        os.makedirs(self.paths["COMBINED_DIR"], exist_ok=True)

    def tearDown(self):
        import routers.speaking as speaking
        import routers.speaking_playlist as playlist

        speaking.MOTHER_DIR, playlist.MOTHER_DIR, playlist.COMBINED_DIR = self._saved
        self._base.tearDown(self)

    def write_combined(self, folder, content):
        with open(os.path.join(self.paths["COMBINED_DIR"], folder + ".mp3"), "wb") as f:
            f.write(content)

    # ---------- /combined_audio ----------
    def test_combined_audio_with_mp3_suffix_is_served(self):
        # combined.html 的写法：/combined_audio/<话题>.mp3
        self.write_combined("P1 - Rivers", b"\xff\xfb\x90\x64fake-audio")
        response = self.client.get("/combined_audio/P1%20-%20Rivers.mp3")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"\xff\xfb\x90\x64fake-audio")
        self.assertIn("audio", response.headers.get("Content-Type", ""))
        response.close()

    def test_combined_audio_without_suffix_still_works(self):
        self.write_combined("P1 - Rivers", b"abc")
        response = self.client.get("/combined_audio/P1%20-%20Rivers")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"abc")
        response.close()

    def test_topic_whose_name_ends_in_mp3_prefers_exact_file(self):
        # 话题名本身以 .mp3 结尾时，<话题>.mp3 存在就用它，不去掉后缀
        self.write_combined("Notes.mp3", b"exact")
        self.write_combined("Notes", b"stripped")
        response = self.client.get("/combined_audio/Notes.mp3")
        self.assertEqual(response.data, b"exact")
        response.close()

    def test_combined_audio_missing_and_unsafe(self):
        self.assertEqual(self.client.get("/combined_audio/Nothing%20here.mp3").status_code, 404)
        self.assertEqual(self.client.get("/combined_audio/..").status_code, 400)

    # ---------- /generate_audio 的 Part 2 题卡 ----------
    def test_failed_generation_leaves_no_orphan_question(self):
        import routers.speaking as speaking

        with mock.patch.object(speaking, "generate_tts", side_effect=Exception("TTS API错误: 401")):
            response = self.client.post("/generate_audio", headers=self.auth_headers(), json={
                "text": "A made-up answer.", "folder": "P2 - A quiet library", "question": "Describe a quiet place.",
            })
        self.assertEqual(response.status_code, 500)
        self.assertFalse(os.path.exists(os.path.join(self.paths["MOTHER_DIR"], "P2 - A quiet library", "question.txt")))

    def test_successful_generation_saves_question(self):
        import routers.speaking as speaking

        def fake_tts(text, folder):
            os.makedirs(os.path.join(self.paths["MOTHER_DIR"], folder), exist_ok=True)
            return folder, folder + "_20261101_120000.mp3"

        with mock.patch.object(speaking, "generate_tts", side_effect=fake_tts):
            response = self.client.post("/generate_audio", headers=self.auth_headers(), json={
                "text": "A made-up answer.", "folder": "P2 - A quiet library", "question": "  Describe a quiet place.\n",
            })
        self.assertEqual(response.status_code, 200)
        with open(os.path.join(self.paths["MOTHER_DIR"], "P2 - A quiet library", "question.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "Describe a quiet place.")


if __name__ == "__main__":
    unittest.main()

"""精读加高亮的范围校验：页面按 JS 的 UTF-16 下标发 start/end，服务器也要按 UTF-16 长度查。

文章里有 emoji（😴、🌧 这类在 UTF-16 里占两个单位）时，以前服务器按 Python 字符数查，
最后几个字会被当成越界，提示「选择范围无效」。文章内容都是编的。
"""

import unittest

from test_auth_guard import AppTestBase


def utf16(text, index):
    """Python 下标 → 页面（JS）里同一个位置的 UTF-16 下标"""
    return len(text[:index].encode("utf-16-le")) // 2


class HighlightRangeTest(AppTestBase):
    def setUp(self):
        super().setUp()
        # 加高亮会顺手去生成单词发音（付费 TTS），测试里只记下来
        import routers.intensive_reading as intensive
        self.tts_words = []
        self._patch(intensive, "generate_vocab_audio_async", lambda article_id, word: self.tts_words.append(word))

    def create(self, content):
        response = self.client.post("/intensive_create", headers=self.auth(),
                                    json={"title": "Rain Diary", "category": "Reading", "content": content})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["id"]

    def highlight(self, article_id, start, end, text):
        return self.client.post("/intensive_add_highlight", headers=self.auth(),
                                json={"id": article_id, "start": start, "end": end, "meaning": "示例释义", "text": text})

    def test_last_words_after_emoji_can_be_highlighted(self):
        content = "Rain 🌧 all night, then sleep 😴.\n醒来以后，他对着窗外微笑"
        article_id = self.create(content)
        i = content.index("微笑")
        response = self.highlight(article_id, utf16(content, i), utf16(content, i + 2), "微笑")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(self.tts_words, ["微笑"])

    def test_range_past_the_end_is_still_rejected(self):
        content = "Rain 🌧 again"
        article_id = self.create(content)
        end = utf16(content, len(content))
        self.assertEqual(self.highlight(article_id, end - 1, end, "n").status_code, 200)
        self.assertEqual(self.highlight(article_id, end - 1, end + 1, "n").status_code, 400)

    def test_empty_or_reversed_range_is_rejected(self):
        article_id = self.create("A plain sentence.")
        self.assertEqual(self.highlight(article_id, 3, 3, "").status_code, 400)
        self.assertEqual(self.highlight(article_id, 5, 2, "x").status_code, 400)
        self.assertEqual(self.highlight(article_id, -1, 2, "x").status_code, 400)


if __name__ == "__main__":
    unittest.main()

"""精读加高亮。

- 范围校验：页面按 JS 的 UTF-16 下标发 start/end，服务器也要按 UTF-16 长度查。文章里有 emoji
  （😴、🌧 这类在 UTF-16 里占两个单位）时，以前服务器按 Python 字符数查，最后几个字会被当成越界。
- 加高亮不再生成单词发音（以前是付费 TTS），页面点的时候直接取有道词典的。
- 题目栏里也能划词：多带一个 qk（哪一段题目文字），下标是那段文字里的。

文章、题目内容都是编的。
"""

import json
import os
import unittest

from test_auth_guard import AppTestBase


def utf16(text, index):
    """Python 下标 → 页面（JS）里同一个位置的 UTF-16 下标"""
    return len(text[:index].encode("utf-16-le")) // 2


class HighlightTestBase(AppTestBase):
    def setUp(self):
        super().setUp()
        # 不管从哪儿调到生成单词发音（付费 TTS），都记下来，测试要求一次都没有
        self.tts_words = []
        self._patch(self.core, "generate_and_save_vocab_audio", lambda article_id, word: self.tts_words.append(word))

    def create(self, content):
        response = self.client.post("/intensive_create", headers=self.auth(),
                                    json={"title": "Rain Diary", "category": "Reading", "content": content})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["id"]

    def highlight(self, article_id, start, end, text, **extra):
        body = {"id": article_id, "start": start, "end": end, "meaning": "示例释义", "text": text}
        body.update(extra)
        return self.client.post("/intensive_add_highlight", headers=self.auth(), json=body)

    def article(self, article_id):
        response = self.client.get(f"/intensive_article/{article_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        return response.get_json()["article"]


class HighlightRangeTest(HighlightTestBase):
    def test_last_words_after_emoji_can_be_highlighted(self):
        content = "Rain 🌧 all night, then sleep 😴.\n醒来以后，他对着窗外微笑"
        article_id = self.create(content)
        i = content.index("微笑")
        response = self.highlight(article_id, utf16(content, i), utf16(content, i + 2), "微笑")
        self.assertEqual(response.status_code, 200, response.get_json())

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
        self.assertEqual(self.highlight(article_id, "a", 2, "x").status_code, 400)

    def test_adding_or_updating_a_highlight_generates_no_audio(self):
        article_id = self.create("Lanterns glowed along the harbour wall.")
        self.assertEqual(self.highlight(article_id, 0, 8, "Lanterns").status_code, 200)
        r = self.highlight(article_id, 0, 8, "Lanterns")   # 同一范围再存一次 = 改释义
        self.assertTrue(r.get_json()["updated"])
        self.assertEqual(self.tts_words, [])
        self.assertFalse(os.path.exists(os.path.join(self.core.VOCAB_AUDIO_DIR, article_id)))


class QuestionHighlightTest(HighlightTestBase):
    """题目栏里的高亮。题目结构和九分学长导入后存下的 exam 一样，内容是编的。"""

    EXAM = {
        "title": "Harbour Lights",
        "paragraphs": [],
        "groups": [
            {"kind": "choice", "range": "Questions 1-2", "instruction_html": "", "content_html": "", "options": [],
             "questions": [
                 {"num": "1", "text": "Why were the lanterns relocated?", "options": [
                     {"key": "A", "text": "to reduce glare for sailors"}, {"key": "B", "text": "to save fuel"}]},
                 {"num": "2", "text": "What did the 🌊 committee propose?", "options": []},
             ]},
            {"kind": "match", "range": "Questions 3", "instruction_html": "", "content_html": "",
             "options": [{"key": "A", "text": "a reluctant volunteer"}, {"key": "B", "text": "a former keeper"}],
             "questions": [{"num": "3", "text": "", "options": []}]},
            {"kind": "blank", "range": "Questions 4", "instruction_html": "",
             "content_html": "<table><tr><td>Lamps were <b>re</b>fuelled at <span class=\"ir-blank\" data-q=\"4\">4</span> &amp; dusk</td></tr></table>",
             "options": [], "questions": [{"num": "4", "text": "Lamps were refuelled at ____", "options": []}]},
        ],
    }

    def setUp(self):
        super().setUp()
        self.article_id = self.create("The lanterns were moved inland.")
        path = os.path.join(self.core.INTENSIVE_DIR, f"{self.article_id}.json")
        data = self.read_json(path)
        data["exam"] = json.loads(json.dumps(self.EXAM))
        self.write_json(path, data)

    def qh(self, qk, block, word, occurrence=0, **extra):
        i = -1
        for _ in range(occurrence + 1):
            i = block.index(word, i + 1)
        return self.highlight(self.article_id, utf16(block, i), utf16(block, i + len(word)), word, qk=qk, **extra)

    def test_stem_option_group_option_and_layout_can_be_highlighted(self):
        cases = [
            ("g0.q1", "Why were the lanterns relocated?", "relocated"),
            ("g0.q1.A", "to reduce glare for sailors", "glare"),
            ("g0.q2", "What did the 🌊 committee propose?", "committee"),   # 题干里有 emoji，按 UTF-16 下标
            ("g1.oA", "a reluctant volunteer", "reluctant volunteer"),
        ]
        for qk, block, word in cases:
            with self.subTest(qk=qk):
                r = self.qh(qk, block, word)
                self.assertEqual(r.status_code, 200, r.get_json())
                self.assertEqual(r.get_json()["highlight"]["qk"], qk)
        # 原题版式是 HTML：页面按 textContent（去掉标签、实体还原）算下标，一个词可以跨 <b>
        plain = "Lamps were refuelled at 4 & dusk"
        r = self.qh("g2.layout", plain, "refuelled")
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.qh("g2.layout", plain, "4 & dusk")
        self.assertEqual(r.status_code, 200, r.get_json())

        hl = self.article(self.article_id)["highlights"]
        self.assertEqual(len(hl), 6)
        self.assertEqual({h["qk"] for h in hl}, {"g0.q1", "g0.q1.A", "g0.q2", "g1.oA", "g2.layout"})
        self.assertEqual(self.tts_words, [])
        # 列表里的词数、词汇挑战都把题目里的词算进去
        items = self.client.get("/intensive_list", headers=self.auth()).get_json()["items"]
        self.assertEqual(items[0]["highlight_count"], 6)

    def test_passage_highlights_have_no_qk(self):
        r = self.highlight(self.article_id, 4, 12, "lanterns")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("qk", r.get_json()["highlight"])

    def test_bad_block_range_or_text_is_rejected(self):
        block = "Why were the lanterns relocated?"
        i = block.index("relocated")
        for body in [
            {"qk": "g9.q1", "start": i, "end": i + 9, "text": "relocated"},        # 没有这段题目文字
            {"qk": "g0.q3", "start": 0, "end": 3, "text": "Why"},                  # 第 3 题在第 1 组
            {"qk": "g0.q1", "start": i, "end": i + 9, "text": "lanterns"},         # 词和下标对不上
            {"qk": "g0.q1", "start": i, "end": len(block) + 1, "text": "relocated?"},  # 越界
            {"qk": "g0.q1", "start": i, "end": i, "text": ""},                     # 空
            {"qk": "g2.layout", "start": 0, "end": 5, "text": "Sailors"},           # 版式里没有这个词
            {"qk": "", "start": 0, "end": 3, "text": "The"},                       # qk 不能是空串
            {"qk": ["g0.q1"], "start": 0, "end": 3, "text": "Why"},                # 也不能是别的类型
        ]:
            with self.subTest(body=body):
                r = self.client.post("/intensive_add_highlight", headers=self.auth(),
                                     json=dict(body, id=self.article_id, meaning="m"))
                self.assertIn(r.status_code, (400,), r.get_json())
        self.assertEqual(self.article(self.article_id)["highlights"], [])

    def test_article_without_exam_rejects_question_highlights(self):
        other = self.create("No questions here.")
        r = self.highlight(other, 0, 2, "No", qk="g0.q1")
        self.assertEqual(r.status_code, 400)

    def test_same_place_updates_meaning_and_delete_works(self):
        r1 = self.qh("g0.q1", "Why were the lanterns relocated?", "lanterns")
        r2 = self.qh("g0.q1", "Why were the lanterns relocated?", "lanterns", meaning="灯笼")
        self.assertTrue(r2.get_json()["updated"])
        hl = self.article(self.article_id)["highlights"]
        self.assertEqual(len(hl), 1)
        self.assertEqual(hl[0]["meaning"], "灯笼")
        r = self.client.post("/intensive_delete_highlight", headers=self.auth(),
                             json={"id": self.article_id, "highlight_id": r1.get_json()["highlight"]["id"]})
        self.assertEqual(r.get_json()["removed"], 1)
        self.assertEqual(self.article(self.article_id)["highlights"], [])

    def test_same_range_in_passage_and_question_are_different_places(self):
        # 正文 0-3 和题干 0-3 不是同一个位置，不能互相覆盖
        self.assertEqual(self.highlight(self.article_id, 0, 3, "The").status_code, 200)
        r = self.qh("g0.q1", "Why were the lanterns relocated?", "Why")
        self.assertNotIn("updated", r.get_json())
        self.assertEqual(len(self.article(self.article_id)["highlights"]), 2)

    def test_question_words_reach_vocab_challenge(self):
        self.qh("g1.oA", "a reluctant volunteer", "reluctant", meaning="不情愿的")
        r = self.client.post("/api/vocab_summary_challenge", headers=self.auth(),
                             json={"article_ids": [self.article_id], "word_count": 5})
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIn("reluctant", json.dumps(r.get_json(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()

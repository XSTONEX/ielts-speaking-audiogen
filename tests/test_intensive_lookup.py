"""精读三击查词：/intensive_lookup 拿选中的词和它所在的句子去问模型，回一行释义（页面再拿它存高亮）。

- 句子由服务器按下标从文章里取，不信页面传的文字；下标和词对不上就拒绝，不去调模型。
- 题目栏里的词（带 qk）用那段题目文字做上下文。
- 模型的回答收成一行，过长截断；模型出错回 502，页面会提示自己写。

模型调用换成桩，不调付费接口。文章、题目内容都是编的。
"""

import json
import os
import sys

from test_intensive_highlights import HighlightTestBase, utf16


class LookupTest(HighlightTestBase):
    CONTENT = "The harbour lights appear brighter in winter.\n港口的灯在冬天显得更亮。\nFishermen relied on them 🌊 for decades."

    def setUp(self):
        super().setUp()
        self.calls = []
        self.reply = '{"meaning": "v. 似乎；显得"}'
        router = sys.modules["routers.intensive_reading"]

        def fake_llm(cfg, messages):
            self.calls.append((cfg, messages))
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply
        self._patch(router, "call_llm", fake_llm)
        self.article_id = self.create(self.CONTENT)

    def lookup(self, word, occurrence_in=None, **extra):
        block = occurrence_in or self.CONTENT
        i = block.index(word)
        body = {"id": self.article_id, "start": utf16(block, i), "end": utf16(block, i + len(word)), "text": word}
        body.update(extra)
        return self.client.post("/intensive_lookup", headers=self.auth(), json=body)

    def test_word_is_sent_with_its_own_line_as_context(self):
        r = self.lookup("appear")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertEqual(r.get_json()["meaning"], "v. 似乎；显得")
        cfg, messages = self.calls[0]
        user = messages[-1]["content"]
        self.assertIn("单词：appear", user)
        self.assertIn("上下文句子：The harbour lights appear brighter in winter.", user)
        self.assertNotIn("港口", user)                       # 只给这一行，不带译文
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(cfg.get("response_format"), "json_object")

    def test_after_emoji_uses_utf16_offsets(self):
        r = self.lookup("decades")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIn("上下文句子：Fishermen relied on them 🌊 for decades.", self.calls[0][1][-1]["content"])

    def test_mismatched_word_or_range_is_rejected_without_calling_the_model(self):
        i = self.CONTENT.index("appear")
        for body in [
            {"start": i, "end": i + 6, "text": "winter"},           # 词和下标对不上
            {"start": i, "end": i + 400, "text": "appear"},         # 越界
            {"start": i, "end": i, "text": ""},                     # 空
            {"start": "x", "end": 3, "text": "The"},
        ]:
            with self.subTest(body=body):
                r = self.client.post("/intensive_lookup", headers=self.auth(), json=dict(body, id=self.article_id))
                self.assertEqual(r.status_code, 400, r.get_json())
        r = self.client.post("/intensive_lookup", headers=self.auth(),
                             json={"id": "../users", "start": 0, "end": 3, "text": "The"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.calls, [])

    def test_needs_login(self):
        r = self.client.post("/intensive_lookup", json={"id": self.article_id, "start": 0, "end": 3, "text": "The"})
        self.assertIn(r.status_code, (401, 403))
        self.assertEqual(self.calls, [])

    def test_reply_is_one_short_line(self):
        for reply, want in [
            ('```json\n{"meaning": "adj. 更亮的；明亮的"}\n```', "adj. 更亮的；明亮的"),
            ('{"meaning": "v. 依靠\\n依赖"}', "v. 依靠 依赖"),
            ('{"meaning": "  n. 港口  "}', "n. 港口"),
        ]:
            with self.subTest(reply=reply):
                self.reply = reply
                self.assertEqual(self.lookup("appear").get_json()["meaning"], want)
        self.reply = json.dumps({"meaning": "n. " + "很长" * 60})
        self.assertLessEqual(len(self.lookup("appear").get_json()["meaning"]), 60)

    def test_model_failure_or_empty_answer_is_502(self):
        for reply in [RuntimeError("upstream down"), '{"meaning": ""}', "not json"]:
            with self.subTest(reply=reply):
                self.reply = reply
                r = self.lookup("appear")
                self.assertEqual(r.status_code, 502, r.get_json())
                self.assertIn("error", r.get_json())

    def test_lookup_does_not_save_anything(self):
        self.lookup("appear")
        self.assertEqual(self.article(self.article_id)["highlights"], [])

    def test_question_text_uses_the_question_block_as_context(self):
        path = os.path.join(self.core.INTENSIVE_DIR, f"{self.article_id}.json")
        data = self.read_json(path)
        data["exam"] = {"title": "Harbour", "paragraphs": [], "groups": [
            {"kind": "choice", "range": "Questions 1-2", "instruction_html": "", "content_html": "", "options": [], "questions": [
                {"num": "1", "text": "Why did the fishermen rely on the lights?", "options": [
                    {"key": "A", "text": "to avoid the rocks"}, {"key": "B", "text": "to find the market"}]},
                {"num": "2", "text": "Which TWO are mentioned?", "options": []},
            ]},
        ]}
        self.write_json(path, data)
        block = "Why did the fishermen rely on the lights?"
        r = self.lookup("rely", occurrence_in=block, qk="g0.q1")
        self.assertEqual(r.status_code, 200, r.get_json())
        self.assertIn("上下文句子：Why did the fishermen rely on the lights?", self.calls[-1][1][-1]["content"])
        # 选两项的第 2 题借第 1 题的选项，那里的词也能查
        r = self.lookup("rocks", occurrence_in="to avoid the rocks", qk="g0.q2.A")
        self.assertEqual(r.status_code, 200, r.get_json())
        r = self.lookup("rocks", occurrence_in="to avoid the rocks", qk="g0.q9.A")
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    import unittest
    unittest.main()

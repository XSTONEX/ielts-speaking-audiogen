import copy
import importlib
import json
import os
import shutil
import tempfile
import unittest

from utils import jiufen_import as J

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "jiufen_reading_attempt.json")


def load_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.raw = load_fixture()

    def test_full_response_pasted_with_stray_quotes(self):
        text = "“”“\n" + json.dumps(self.raw, ensure_ascii=False) + "\n”“”"
        parts = J.parse(text)
        self.assertEqual(len(parts), 1)
        part = parts[0]
        self.assertEqual(part["title"], "The Glass Bridge")
        self.assertEqual(part["part"], "Part 1")
        self.assertEqual([p["label"] for p in part["paragraphs"]], list("ABC"))
        self.assertEqual(sum(len(p["sentences"]) for p in part["paragraphs"]), 8)
        # 段落编号从第一句里拿掉了
        self.assertEqual(part["paragraphs"][0]["sentences"][0]["en"], "The town of Marlow built its first glass bridge in 1998.")
        self.assertEqual(part["attempt"]["correct"], 2)
        self.assertEqual(part["attempt"]["total"], 5)
        self.assertEqual(part["attempt"]["elapsed_seconds"], 600)

    def test_questions_answers_and_evidence(self):
        part = J.parse(self.raw)[0]
        judge, blank = part["groups"]
        self.assertEqual((judge["range"], judge["kind"]), ("Questions 1-3", "judge"))
        self.assertEqual((blank["range"], blank["kind"]), ("Questions 4-5", "blank"))
        q2 = judge["questions"][1]
        self.assertEqual((q2["num"], q2["user_answer"], q2["answer"], q2["state"]), ("2", "A", "B", "wrong"))
        self.assertEqual(q2["evidence"], [2, 3])
        self.assertEqual([o["text"] for o in q2["options"]], ["TRUE", "FALSE", "NOT GIVEN"])
        self.assertIn("worried at first", q2["analysis"]["explain"])
        self.assertTrue(q2["analysis"]["trap"])
        # 填空题没有单独题干：从版式里取出空所在的那一行
        q4, q5 = blank["questions"]
        self.assertEqual(q4["text"], "Why did engineers choose glass? To let light reach the ____")
        self.assertEqual(q4["evidence"], [1, 1])
        self.assertEqual(q4["answer"], "river|river below")
        self.assertEqual((q5["text"], q5["state"], q5["user_answer"]), ("Where is the museum? On the ____", "blank", ""))
        self.assertIn('<span class="ir-blank" data-q="4">4</span>', blank["content_html"])
        self.assertNotIn("<input", blank["content_html"])
        self.assertNotIn("style=", blank["content_html"])
        self.assertIn("<strong>NO MORE THAN TWO WORDS</strong>", blank["instruction_html"])

    def test_exam_highlights_land_on_the_same_words(self):
        part = J.parse(self.raw)[0]
        sentences = {s["i"]: s["en"] for p in part["paragraphs"] for s in p["sentences"]}
        # 6 条划线里 5 条在原文上（一条下标偏了，按原词找回），1 条在题目上
        self.assertEqual([m["text"] for m in part["marks"]], ["glass bridge", "light", "worried", "Visitors", "museum"])
        for m in part["marks"]:
            self.assertEqual(sentences[m["s"]][m["start"]:m["end"]], m["text"], m)
        self.assertIn({"s": 6, "start": 0, "end": 8, "text": "Visitors"}, part["marks"])
        self.assertIn({"s": 2, "start": 21, "end": 28, "text": "worried"}, part["marks"])   # 按去掉 "B " 之后的句子算

    def test_answers_from_details_when_questions_lack_them(self):
        raw = copy.deepcopy(self.raw)
        for g in raw["data"]["attempt"]["parts"][0]["groups"]:
            for q in g["questions"]:
                for key in ("userAnswer", "rightAnswer", "state"):
                    q.pop(key, None)
        q2 = J.parse(raw)[0]["groups"][0]["questions"][1]
        self.assertEqual((q2["user_answer"], q2["answer"], q2["state"]), ("A", "B", "wrong"))

    def test_exam_without_attempt_and_article_json_as_object(self):
        part = copy.deepcopy(self.raw["data"]["attempt"]["parts"][0])
        part["articleJson"] = json.loads(part["articleJson"])
        for g in part["groups"]:
            for q in g["questions"]:
                for key in ("userAnswer", "state"):
                    q.pop(key, None)
        parsed = J.parse({"data": {"parts": [part]}})[0]
        self.assertIsNone(parsed["attempt"])
        self.assertEqual(parsed["groups"][0]["questions"][0]["answer"], "C")
        self.assertEqual(parsed["groups"][0]["questions"][0]["user_answer"], "")

    def test_unlabelled_paragraphs_are_left_alone(self):
        part = copy.deepcopy(self.raw["data"]["attempt"]["parts"][0])
        art = json.loads(part["articleJson"])
        art["segments"][1]["sentences"][0]["text"] = art["segments"][1]["sentences"][0]["text"][2:]   # 去掉 "B "
        part["articleJson"] = json.dumps(art)
        parsed = J.parse({"parts": [part], "details": []})[0]
        self.assertEqual({p["label"] for p in parsed["paragraphs"]}, {None})
        self.assertTrue(parsed["paragraphs"][0]["sentences"][0]["en"].startswith("A The town of Marlow"))

    def test_bad_input_explains_itself(self):
        for raw, words in [("", "没找到 JSON"), ("{not json", "没找到 JSON"), ('{"a": 1,}', "JSON 格式不对"),
                           ('{"code": "200", "data": {}}', "没找到文章")]:
            with self.assertRaises(J.JiufenFormatError) as cm:
                J.parse(raw)
            self.assertIn(words, str(cm.exception))

    def test_sanitize_drops_scripts_and_attributes(self):
        safe, blocks = J.sanitize_html('<p onclick="x()" style="color:red">Hi <script>alert(1)</script>'
                                       '<a href="javascript:x">link</a> <input placeholder="3"></p>'
                                       '<table><tr><td colspan="2" class="z">a</td><td>b</td></tr></table>')
        self.assertNotIn("script", safe.lower().replace("alert(1)", ""))
        self.assertNotIn("onclick", safe)
        self.assertNotIn("href", safe)
        self.assertNotIn("class=\"z\"", safe)
        self.assertIn('<td colspan="2">a</td>', safe)
        self.assertIn('<span class="ir-blank" data-q="3">3</span>', safe)

    def test_article_text_positions(self):
        part = J.parse(self.raw)[0]
        J.apply_translations(part, {"s0": "马洛镇在 1998 年建了第一座玻璃桥。", "q0.1": "这座桥……"})
        text = J.build_article_text(part)
        u16 = text.encode("utf-16-le")
        at = lambda o, s: u16[o * 2:(o + len(s.encode("utf-16-le")) // 2) * 2].decode("utf-16-le")
        for p in part["paragraphs"]:
            self.assertEqual(at(p["o"], p["label"]), p["label"])
            for s in p["sentences"]:
                self.assertEqual(at(s["o"], s["en"]), s["en"])
                if s["zh"]:
                    self.assertEqual(at(s["zo"], s["zh"]), s["zh"])
                else:
                    self.assertIsNone(s["zo"])
        self.assertTrue(text.startswith("A\nThe town of Marlow"))
        self.assertIn("\n马洛镇在 1998 年建了第一座玻璃桥。\n", text)
        self.assertEqual(part["groups"][0]["questions"][0]["zh"], "这座桥……")


class ImportRouteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="jiufen_import_test_")
        import core
        import routers.auth as auth
        import routers.intensive_reading as intensive
        self.intensive = intensive
        self._saved = []
        for module in (core, auth, intensive):
            for name, value in {
                "INTENSIVE_DIR": os.path.join(self.tmp, "intensive_articles"),
                "INTENSIVE_IMAGES_DIR": os.path.join(self.tmp, "intensive_articles", "images"),
                "TOKEN_FILE": os.path.join(self.tmp, "tokens.json"),
                "USERS_FILE": os.path.join(self.tmp, "users.json"),
            }.items():
                if hasattr(module, name):
                    self._saved.append((module, name, getattr(module, name)))
                    setattr(module, name, value)
        os.makedirs(os.path.join(self.tmp, "intensive_articles", "images"), exist_ok=True)
        with open(os.path.join(self.tmp, "users.json"), "w", encoding="utf-8") as f:
            json.dump({"tester": {"username": "tester", "password": "secret", "display_name": "T",
                                  "role": "admin", "avatar": "a.svg"}}, f)
        import app
        self.client = importlib.reload(app).app.test_client()
        token = self.client.post("/user_login", json={"username": "tester", "password": "secret"}).get_json()["token"]
        self.headers = {"Authorization": f"Bearer {token}"}
        self.raw = json.dumps(load_fixture(), ensure_ascii=False)

    def tearDown(self):
        for module, name, value in reversed(self._saved):
            setattr(module, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub_translate(self, result):
        original = self.intensive._translate_items
        self.intensive._translate_items = result
        self.addCleanup(setattr, self.intensive, "_translate_items", original)

    def articles(self):
        d = os.path.join(self.tmp, "intensive_articles")
        return sorted(f for f in os.listdir(d) if f.endswith(".json"))

    def test_preview_summarizes(self):
        r = self.client.post("/intensive_import_preview", json={"raw": self.raw}, headers=self.headers)
        self.assertEqual(r.status_code, 200)
        s = r.get_json()["parts"][0]
        self.assertEqual((s["title"], s["sentences"], s["questions"], s["marks"]), ("The Glass Bridge", 8, 5, 5))
        self.assertEqual([g["kind"] for g in s["groups"]], ["judge", "blank"])
        self.assertEqual(self.articles(), [])

    def test_preview_rejects_garbage(self):
        r = self.client.post("/intensive_import_preview", json={"raw": "hello"}, headers=self.headers)
        self.assertEqual(r.status_code, 400)
        self.assertIn("没找到 JSON", r.get_json()["error"])

    def test_import_with_translation(self):
        seen = {}

        def fake(items):
            seen["items"] = items
            return {it["id"]: f"译:{it['en'][:10]}" for it in items}, None

        self.stub_translate(fake)
        r = self.client.post("/intensive_import", json={"raw": self.raw, "category": "Reading"}, headers=self.headers)
        self.assertEqual(r.status_code, 200, r.get_json())
        [article_id] = r.get_json()["ids"]
        self.assertEqual(len(seen["items"]), 8 + 5)
        art = self.client.get(f"/intensive_article/{article_id}", headers=self.headers).get_json()["article"]
        self.assertEqual(art["title"], "The Glass Bridge")
        exam = art["exam"]
        self.assertTrue(exam["translated"])
        s0 = exam["paragraphs"][0]["sentences"][0]
        self.assertEqual(art["content_text"][s0["o"]:s0["o"] + len(s0["en"])], s0["en"])
        self.assertTrue(s0["zh"].startswith("译:"))
        self.assertEqual(exam["groups"][0]["questions"][0]["zh"], "译:The bridge")
        # 高亮照常按 content_text 下标存
        start = art["content_text"].index("Engineers")
        r = self.client.post("/intensive_add_highlight", headers=self.headers, json={
            "id": article_id, "start": start, "end": start + len("Engineers"), "meaning": "工程师", "text": "Engineers"})
        self.assertTrue(r.get_json()["success"], r.get_json())
        items = self.client.get("/intensive_list", headers=self.headers).get_json()["items"]
        self.assertEqual(items[0]["exam"]["correct"], 2)
        self.assertEqual(items[0]["highlight_count"], 1)

    def test_translation_failure_creates_nothing(self):
        self.stub_translate(lambda items: (None, "timeout"))
        r = self.client.post("/intensive_import", json={"raw": self.raw}, headers=self.headers)
        self.assertEqual(r.status_code, 502)
        self.assertTrue(r.get_json()["translate_failed"])
        self.assertEqual(self.articles(), [])

    def test_import_without_translation(self):
        self.stub_translate(lambda items: self.fail("should not translate"))
        r = self.client.post("/intensive_import", json={"raw": self.raw, "translate": False, "titles": ["我的标题"]},
                             headers=self.headers)
        self.assertEqual(r.status_code, 200)
        art = self.client.get(f"/intensive_article/{r.get_json()['ids'][0]}", headers=self.headers).get_json()["article"]
        self.assertEqual(art["title"], "我的标题")
        self.assertFalse(art["exam"]["translated"])
        self.assertNotIn("\n\n\n", art["content_text"])
        self.assertTrue(all(not s["zh"] for p in art["exam"]["paragraphs"] for s in p["sentences"]))

    def test_import_requires_login(self):
        r = self.client.post("/intensive_import", json={"raw": self.raw, "translate": False})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.articles(), [])


if __name__ == "__main__":
    unittest.main()

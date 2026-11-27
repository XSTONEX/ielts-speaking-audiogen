"""精读 AI 讲解的接口：后台生成、轮询进度、随文章一起返回、删文章时一起删。

模型换成假的（_explain_llm），不调任何付费接口。文章用 tests/fixtures 里编的「The Glass Bridge」。
"""

import json
import os
import time

from test_auth_guard import AppTestBase
from test_jiufen_import import load_fixture


class ExplainRouteTest(AppTestBase):
    def setUp(self):
        super().setUp()
        import routers.intensive_reading as intensive
        self.intensive = intensive
        self.calls = []
        self._patch(intensive, "_explain_ready", lambda: (True, ""))
        self._patch(intensive, "_explain_llm", self.fake_llm)
        self._patch(intensive, "_translate_items", lambda items: ({}, None))

    def fake_llm(self, cfg, messages):
        user = messages[1]["content"]
        self.calls.append(user)
        if "# 各题证据句" in user:
            return json.dumps({"paragraphs": [{"label": "A", "gist": "一座玻璃桥"}]}, ensure_ascii=False)
        # 每道题都给一句证据、不划词：够让流程走完
        nums = [line.split()[0][1:] for line in user.split("\n") if line.startswith("Q")]
        return json.dumps({"questions": [{"num": n, "evidence": [0], "marks": [], "steps": ["定位：x"]} for n in nums]})

    def import_article(self, **extra):
        body = {"raw": json.dumps(load_fixture(), ensure_ascii=False), "translate": False}
        body.update(extra)
        response = self.client.post("/intensive_import", headers=self.auth(), json=body)
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["ids"][0]

    def explain(self, article_id):
        return self.client.get(f"/intensive_explain/{article_id}", headers=self.auth()).get_json()["explain"]

    def wait_done(self, article_id):
        for _ in range(200):
            data = self.explain(article_id)
            if data and data["status"] != "running":
                return data
            time.sleep(0.02)
        self.fail("生成没有结束")

    def test_import_does_not_explain_unless_asked(self):
        article_id = self.import_article()
        self.assertIsNone(self.explain(article_id))
        self.assertEqual(self.calls, [])
        article = self.client.get(f"/intensive_article/{article_id}", headers=self.auth()).get_json()["article"]
        self.assertIsNone(article["explain"])

    def test_start_runs_in_background_and_the_result_comes_with_the_article(self):
        article_id = self.import_article()
        response = self.client.post("/intensive_explain", headers=self.auth(), json={"id": article_id})
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertIn(response.get_json()["explain"]["status"], ("running", "done"))
        data = self.wait_done(article_id)
        self.assertEqual(data["status"], "done", data)
        article = self.client.get(f"/intensive_article/{article_id}", headers=self.auth()).get_json()["article"]
        groups = article["exam"]["groups"]
        self.assertEqual(sorted(article["explain"]["groups"]), [str(i) for i in range(len(groups))])
        # 一个题组至少一次（假回复没划词、有硬伤，会再要一次），最后一次是全篇
        self.assertGreaterEqual(len(self.calls), len(groups) + 1)
        self.assertIn("# 各题证据句", self.calls[-1])
        first = groups[0]["questions"][0]["num"]
        self.assertEqual(article["explain"]["groups"]["0"]["questions"][first]["evidence"], [0])
        self.assertEqual(article["explain"]["overview"]["paragraphs"][0]["gist"], "一座玻璃桥")
        # 存在文章 JSON 旁边的 explain/ 里，文章列表不把它当文章
        self.assertTrue(os.path.exists(os.path.join(self.core.INTENSIVE_DIR, "explain", f"{article_id}.json")))
        items = self.client.get("/intensive_list", headers=self.auth()).get_json()["items"]
        self.assertEqual([i["id"] for i in items], [article_id])

    def test_import_with_explain_starts_it(self):
        article_id = self.import_article(explain=True)
        self.assertEqual(self.wait_done(article_id)["status"], "done")

    def test_deleting_the_article_deletes_its_explanation(self):
        article_id = self.import_article(explain=True)
        self.wait_done(article_id)
        path = os.path.join(self.core.INTENSIVE_DIR, "explain", f"{article_id}.json")
        self.assertTrue(os.path.exists(path))
        self.client.post("/intensive_delete_article", headers=self.auth(), json={"id": article_id})
        self.assertFalse(os.path.exists(path))

    def test_interrupted_generation_is_reported_not_left_spinning(self):
        article_id = self.import_article()
        self.write_json(os.path.join(self.core.INTENSIVE_DIR, "explain", f"{article_id}.json"),
                        {"status": "running", "done": 1, "total": 3, "groups": {"0": {"type": "judge", "questions": {}}},
                         "overview": None, "errors": []})
        data = self.explain(article_id)
        self.assertEqual(data["status"], "partial")
        self.assertIn("打断", data["errors"][0])

    def test_refuses_articles_without_questions_bad_ids_and_missing_keys(self):
        response = self.client.post("/intensive_create", headers=self.auth(),
                                    json={"title": "Plain", "category": "Reading", "content": "Just text."})
        plain = response.get_json()["id"]
        self.assertEqual(self.client.post("/intensive_explain", headers=self.auth(), json={"id": plain}).status_code, 400)
        self.assertEqual(self.client.post("/intensive_explain", headers=self.auth(), json={"id": "../users"}).status_code, 400)
        self.assertEqual(self.client.post("/intensive_explain", headers=self.auth(), json={"id": "nope"}).status_code, 404)
        self.assertEqual(self.client.get("/intensive_explain/..%2Fusers", headers=self.auth()).status_code in (400, 404), True)
        self._patch(self.intensive, "_explain_ready", lambda: (False, "服务器没有配置 WILDAPI_API_KEY"))
        article_id = self.import_article()
        response = self.client.post("/intensive_explain", headers=self.auth(), json={"id": article_id})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(self.calls, [])

    def test_requires_login(self):
        self.assertEqual(self.client.get("/intensive_explain/x").status_code, 401)
        self.assertEqual(self.client.post("/intensive_explain", json={"id": "x"}).status_code, 401)

"""全局登录检查、路径穿越防护、上传大小上限的回归测试。

所有数据目录都指到临时目录；后台音频线程不会启动；
可能触发外部付费接口的函数（转写 API）被替换成桩，测试不会发出任何网络请求。
"""

import importlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest


# core 里所有数据路径常量。各个 router 用 `from core import X` 各自存了一份，要逐个模块替换。
PATH_CONSTANTS = [
    "MOTHER_DIR", "COMBINED_DIR", "TOKEN_FILE", "USERS_FILE", "READING_DIR",
    "INTENSIVE_DIR", "INTENSIVE_IMAGES_DIR", "VOCAB_AUDIO_DIR",
    "VOCABULARY_BOOK_DIR", "VOCABULARY_CATEGORIES_DIR", "VOCABULARY_AUDIO_DIR",
    "VOCABULARY_TASKS_DIR", "VOCABULARY_CHALLENGE_DIR",
    "MESSAGE_BOARD_DIR", "MESSAGE_IMAGES_DIR", "CHALLENGES_DIR",
    "STUDY_TECHNIQUES_DIR", "STUDY_TECHNIQUES_DATA_DIR", "STUDY_TECHNIQUES_AUDIO_DIR",
    "AUDIO_TRANSCRIPTION_DIR", "USER_DATA_DIR",
    "WRITING_CORRECTION_DIR", "WRITING_DATA_DIR", "WRITING_MD_FILE", "WRITING_SMALL_MD_FILE",
    "WRITING_TEMPLATE_FILE", "WRITING_IMAGES_DIR", "WRITING_CHAT_DIR", "LISTENING_REVIEW_DIR",
]

ROUTER_MODULES = [
    "routers.auth", "routers.speaking", "routers.speaking_playlist", "routers.reading",
    "routers.intensive_reading", "routers.community", "routers.vocabulary",
    "routers.study_tips", "routers.asr_transcription", "routers.writing_logic",
    "routers.listening_review", "routers.learning",
]


class AppTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ielts_guard_test_")
        self._saved = []   # (object, attribute, original value)

        import core
        modules = [core] + [importlib.import_module(name) for name in ROUTER_MODULES]
        core_values = {name: getattr(core, name) for name in PATH_CONSTANTS}
        for name, original in core_values.items():
            # 保持原来的相对结构，只是整体挪进临时目录
            patched = os.path.join(self.tmp, original.lstrip("./")) if not os.path.isabs(original) \
                else os.path.join(self.tmp, os.path.basename(original))
            for module in modules:
                if hasattr(module, name):
                    self._patch(module, name, patched)
        self._patch(core, "_DURATION_CACHE_FILE", os.path.join(self.tmp, "audio_files", ".durations.json"))

        # 转写接口换成桩（万一校验失效，也不会真的去调付费 API）
        asr = sys.modules["routers.asr_transcription"]
        self._patch(asr, "call_transcription_api", lambda *a, **k: (None, "stubbed in tests"))
        # 精读加高亮会顺手去生成单词发音，同样是付费 TTS
        intensive = sys.modules["routers.intensive_reading"]
        self._patch(intensive, "generate_vocab_audio_async", lambda *a, **k: None)

        core.init_directories()
        import app
        self.app_module = importlib.reload(app)
        self.app = self.app_module.app
        self.client = self.app.test_client()
        self.core = core

        self.users_file = core.USERS_FILE
        self.tokens_file = core.TOKEN_FILE
        self.write_json(self.users_file, {
            "tester": {"username": "tester", "password": "secret", "display_name": "Test User",
                       "role": "admin", "avatar": "avatar_admin.svg"},
        })
        self.token = self.login("tester", "secret")

    def tearDown(self):
        for obj, name, value in reversed(self._saved):
            setattr(obj, name, value)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch(self, obj, name, value):
        self._saved.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False)

    def read_json(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def login(self, username, password):
        response = self.client.post("/user_login", json={"username": username, "password": password})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"], data)
        return data["token"]

    def auth(self, token=None):
        return {"Authorization": f"Bearer {token or self.token}"}


class LoginGuardTest(AppTestBase):
    @staticmethod
    def _example_url(rule):
        """把 /x/<int:a>/<path:b>/<c> 这样的规则填上示例值"""
        def fill(match):
            converter = match.group(1) or "default"
            return {"int": "1", "path": "x/y"}.get(converter, "x")
        return re.sub(r"<(?:(\w+)(?:\([^)]*\))?:)?\w+>", fill, rule.rule)

    def test_public_endpoint_lists_only_name_real_endpoints(self):
        endpoints = set(self.app.view_functions)
        self.assertLessEqual(set(self.app_module.PUBLIC_ENDPOINTS), endpoints)
        self.assertLessEqual(set(self.app_module.QUERY_TOKEN_ENDPOINTS), endpoints)

    def test_every_non_public_route_rejects_anonymous_and_bogus_tokens(self):
        public = self.app_module.PUBLIC_ENDPOINTS
        checked = 0
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint in public:
                continue
            url = self._example_url(rule)
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                for headers in ({}, {"Authorization": "Bearer not-a-real-token"},
                                {"Authorization": "Bearer null"}, {"Authorization": self.token}):
                    response = self.client.open(url, method=method, headers=headers)
                    self.assertEqual(
                        response.status_code, 401,
                        f"{method} {url} ({rule.endpoint}) with {headers or 'no auth'} -> {response.status_code}")
                checked += 1
        # 175 条路由规则（含 static）除去 28 个公开端点，剩下的都得被检查到
        self.assertGreater(checked, 140)

    def test_pages_login_and_verify_stay_public(self):
        page_endpoints = [e for e in self.app_module.PUBLIC_ENDPOINTS
                          if e.endswith(("_page", ".index", ".vocab_summary"))]
        self.assertEqual(len(page_endpoints), 15)
        for rule in self.app.url_map.iter_rules():
            if rule.endpoint in page_endpoints:
                response = self.client.get(rule.rule)
                self.assertEqual(response.status_code, 200, rule.rule)
                self.assertIn("text/html", response.content_type, rule.rule)
                response.close()

        response = self.client.post("/verify_token", json={"token": self.token})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["valid"])

    def test_media_routes_stay_public(self):
        for url in ["/audio/x/y.mp3", "/combined_audio/x", "/message_images/u/x.jpg",
                    "/intensive_image/a/b.png", "/vocab_audio/a/b", "/vocab_audio/articles/a/b.mp3",
                    "/vocabulary_audio/x", "/api/writing/small/image/q/x.png",
                    "/reading_exam/x/y.pdf", "/reading_view/x/y.html"]:
            response = self.client.get(url)
            self.assertNotIn(response.status_code, (401, 403), url)
            response.close()

    def test_valid_token_passes_guard(self):
        response = self.client.get("/api/user/info", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["user"]["username"], "tester")

    def test_query_token_only_accepted_on_audio_endpoints(self):
        response = self.client.get(f"/api/listening_review/audio/nope/a.mp3?token={self.token}")
        self.assertNotEqual(response.status_code, 401)
        response = self.client.get(f"/api/user/info?token={self.token}")
        self.assertEqual(response.status_code, 401)

    def test_tokens_of_deleted_users_or_without_username_are_rejected(self):
        tokens = self.read_json(self.tokens_file)
        tokens["ghost-token"] = {"created_time": "2025-01-01T00:00:00", "username": "ghost"}
        tokens["anon-token"] = {"created_time": "2025-01-01T00:00:00", "username": None}
        self.write_json(self.tokens_file, tokens)

        for token in ("ghost-token", "anon-token"):
            response = self.client.get("/api/user/info", headers=self.auth(token))
            self.assertEqual(response.status_code, 401, token)
            response = self.client.post("/verify_token", json={"token": token})
            self.assertEqual(response.status_code, 200)
            self.assertIs(response.get_json()["valid"], False, token)


class VerifyTokenTest(AppTestBase):
    def test_valid_token_returns_user(self):
        data = self.client.post("/verify_token", json={"token": self.token}).get_json()
        self.assertIs(data["valid"], True)
        self.assertEqual(data["user"]["username"], "tester")
        self.assertEqual(data["user"]["display_name"], "Test User")

    def test_unknown_missing_or_malformed_input_is_explicitly_invalid(self):
        cases = [
            dict(json={"token": "nope"}),
            dict(json={}),
            dict(json=None),
            dict(data="not json", content_type="text/plain"),
            dict(data="{broken", content_type="application/json"),
            dict(json=["token"]),
        ]
        for kwargs in cases:
            response = self.client.post("/verify_token", **kwargs)
            self.assertEqual(response.status_code, 200, kwargs)
            self.assertIs(response.get_json()["valid"], False, kwargs)

    def test_user_record_missing_optional_fields_does_not_500(self):
        users = self.read_json(self.users_file)
        users["minimal"] = {"username": "minimal", "password": "pw"}
        self.write_json(self.users_file, users)
        token = self.core.create_token("minimal")

        data = self.client.post("/verify_token", json={"token": token}).get_json()
        self.assertIs(data["valid"], True)
        self.assertEqual(data["user"]["display_name"], "minimal")

    def test_unreadable_token_store_is_503_not_invalid(self):
        with open(self.tokens_file, "w", encoding="utf-8") as f:
            f.write('{"half-written": ')

        response = self.client.post("/verify_token", json={"token": self.token})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("valid", response.get_json())

        response = self.client.get("/api/user/info", headers=self.auth())
        self.assertEqual(response.status_code, 503)

    def test_unreadable_user_store_is_503_not_invalid(self):
        with open(self.users_file, "w", encoding="utf-8") as f:
            f.write("[not a dict]")
        response = self.client.post("/verify_token", json={"token": self.token})
        self.assertEqual(response.status_code, 503)

    def test_concurrent_logins_keep_every_token(self):
        results, errors = [], []

        def worker():
            try:
                client = self.app.test_client()
                response = client.post("/user_login", json={"username": "tester", "password": "secret"})
                results.append(response.get_json()["token"])
            except Exception as exc:   # pragma: no cover - 只在失败时有用
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        stored = self.read_json(self.tokens_file)
        for token in results + [self.token]:
            self.assertIn(token, stored)
        leftovers = [f for f in os.listdir(os.path.dirname(self.tokens_file)) if f.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_save_json_atomic_accepts_bare_filename(self):
        from utils.json_store import save_json_atomic
        cwd = os.getcwd()
        os.chdir(self.tmp)
        try:
            save_json_atomic("bare.json", {"ok": True})
        finally:
            os.chdir(cwd)
        self.assertEqual(self.read_json(os.path.join(self.tmp, "bare.json")), {"ok": True})


class PathTraversalTest(AppTestBase):
    def setUp(self):
        super().setUp()
        # 两个"受害者"：项目根的 users.json（相对路径穿越）和任意位置的同名 json + 目录（绝对路径）
        self.abs_victim = os.path.join(self.tmp, "outside", "victim")
        os.makedirs(self.abs_victim)
        with open(os.path.join(self.abs_victim, "keep.txt"), "w") as f:
            f.write("keep")
        self.write_json(self.abs_victim + ".json", {"keep": True})
        self.users_before = self.read_json(self.users_file)

    def assertVictimsIntact(self):
        self.assertEqual(self.read_json(self.users_file), self.users_before)
        self.assertTrue(os.path.exists(self.tokens_file))
        self.assertTrue(os.path.exists(self.abs_victim + ".json"))
        self.assertTrue(os.path.exists(os.path.join(self.abs_victim, "keep.txt")))

    def create_article(self, title="Alpha Beta"):
        response = self.client.post("/intensive_create", headers=self.auth(), json={
            "title": title, "category": "Reading", "content": "Alpha beta gamma delta."})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["id"]

    def test_intensive_body_ids_cannot_escape_the_article_folder(self):
        bad_ids = ["../users", "../tokens", self.abs_victim, "..", ".", "a/b", "a\\b", 123, ["x"]]
        routes = [
            ("/intensive_delete_article", lambda i: {"id": i}),
            ("/intensive_update_category", lambda i: {"id": i, "category": "Reading"}),
            ("/intensive_add_highlight", lambda i: {"id": i, "start": 0, "end": 1, "meaning": "m", "text": "t"}),
            ("/intensive_delete_highlight", lambda i: {"id": i, "highlight_id": "h"}),
            ("/intensive_delete_image", lambda i: {"article_id": i, "image_id": "img"}),
            ("/intensive_update_title", lambda i: {"article_id": i, "new_title": "New"}),
            ("/generate_article_audio", lambda i: {"article_id": i, "text": "hello"}),
            ("/prepare_article_audio", lambda i: {"article_id": i, "text": "hello"}),
        ]
        for url, body in routes:
            for bad in bad_ids:
                response = self.client.post(url, headers=self.auth(), json=body(bad))
                self.assertEqual(response.status_code, 400, f"{url} id={bad!r} -> {response.status_code}")
        self.assertVictimsIntact()

    def test_intensive_url_ids_are_validated(self):
        for url in ["/intensive_article/..", "/check_article_audio/.."]:
            response = self.client.get(url, headers=self.auth())
            self.assertEqual(response.status_code, 400, url)

    def test_real_articles_still_work(self):
        article_id = self.create_article()
        path = os.path.join(self.core.INTENSIVE_DIR, f"{article_id}.json")
        self.assertTrue(os.path.exists(path))

        response = self.client.get(f"/intensive_article/{article_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/intensive_update_category", headers=self.auth(),
                                    json={"id": article_id, "category": "Writing"})
        self.assertEqual(response.status_code, 200)

        response = self.client.post("/intensive_update_title", headers=self.auth(),
                                    json={"article_id": article_id, "new_title": "Renamed Title"})
        self.assertEqual(response.status_code, 200, response.get_json())
        new_id = response.get_json()["new_article_id"]
        self.assertNotEqual(new_id, article_id)
        self.assertFalse(os.path.exists(path))

        response = self.client.post("/intensive_delete_article", headers=self.auth(), json={"id": new_id})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(os.path.exists(os.path.join(self.core.INTENSIVE_DIR, f"{new_id}.json")))
        self.assertVictimsIntact()

    def test_core_delete_helpers_refuse_unsafe_ids(self):
        core = self.core
        core.delete_article_vocab_audio(self.abs_victim)
        core.delete_article_audio_files(self.abs_victim)
        core.delete_vocab_audio(self.abs_victim, "word")
        core.delete_article_vocab_audio("..")
        with self.assertRaises(ValueError):
            core.get_vocab_audio_path("../escape", "word")
        self.assertVictimsIntact()
        self.assertTrue(os.path.isdir(core.VOCAB_AUDIO_DIR))

    def test_message_challenge_id_cannot_delete_files_outside(self):
        victim = os.path.join(self.tmp, "victim_note.json")
        self.write_json(victim, {"keep": True})
        rel = os.path.relpath(victim[:-len(".json")], self.core.CHALLENGES_DIR)   # "../victim_note"

        for challenge_id in (rel, self.abs_victim):
            response = self.client.post("/api/messages", headers=self.auth(), json={
                "type": "mixed_content", "content": {"text": "hi", "challenge": {"id": challenge_id}}})
            self.assertEqual(response.status_code, 200)
            message_id = response.get_json()["message"]["id"]
            response = self.client.delete(f"/api/messages/{message_id}", headers=self.auth())
            self.assertEqual(response.status_code, 200)

        self.assertTrue(os.path.exists(victim))
        self.assertVictimsIntact()

        response = self.client.post("/api/participate_challenge", headers=self.auth(),
                                    json={"challenge_id": rel, "answers": []})
        self.assertEqual(response.status_code, 400)

    def test_vocabulary_challenge_user_header_is_sanitised(self):
        vocabulary = sys.modules["routers.vocabulary"]
        cases = {
            "../../users": "default_user",
            '{"username": "../x"}': "default_user",
            '{"username": null}': "default_user",
            '{"display_name": "no username"}': "default_user",
            "{not json}": "{not json}",   # 解析失败时沿用原字符串（和改动前一致），它本身不含路径分隔符
            '{"username": "tester"}': "tester",
            "tester": "tester",
        }
        for header, expected in cases.items():
            with self.app.test_request_context(headers={"X-Current-User": header}):
                self.assertEqual(vocabulary.get_current_user_id(), expected, header)


class UploadLimitTest(AppTestBase):
    def test_request_limit_is_30mb(self):
        self.assertEqual(self.app.config["MAX_CONTENT_LENGTH"], 30 * 1024 * 1024)
        self.assertEqual(self.app_module.MAX_REQUEST_BYTES, 30 * 1024 * 1024)

    def test_oversized_request_gets_json_413_before_reaching_the_view(self):
        self._patch(self.app_module, "MAX_REQUEST_BYTES", 1024)
        self.app.config["MAX_CONTENT_LENGTH"] = 1024

        response = self.client.post(
            "/api/listening_review/upload", headers=self.auth(),
            data={"file": (io.BytesIO(b"x" * 4096), "a.mp3")}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 413)
        self.assertIn("error", response.get_json())

        response = self.client.post("/user_login", json={"username": "u" * 4096, "password": "p"})
        self.assertEqual(response.status_code, 413)
        self.assertEqual(os.listdir(self.core.LISTENING_REVIEW_DIR), [])

    def _jpeg_bytes(self):
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, "JPEG")
        return buf.getvalue()

    def test_message_image_limit_counts_real_bytes(self):
        images_dir = self.core.MESSAGE_IMAGES_DIR
        big = self._jpeg_bytes() + b"\0" * (10 * 1024 * 1024)
        response = self.client.post(
            "/api/upload_message_image", headers=self.auth(),
            data={"image": (io.BytesIO(big), "big.jpg", "image/jpeg"), "user_id": "tester"},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("10MB", response.get_json()["error"])
        self.assertFalse(os.path.exists(os.path.join(images_dir, "tester")) and
                         os.listdir(os.path.join(images_dir, "tester")))

        response = self.client.post(
            "/api/upload_message_image", headers=self.auth(),
            data={"image": (io.BytesIO(self._jpeg_bytes()), "small.jpg", "image/jpeg"), "user_id": "tester"},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertTrue(response.get_json()["success"])

    def test_asr_upload_limit_counts_real_bytes(self):
        asr_dir = self.core.AUDIO_TRANSCRIPTION_DIR
        before = sorted(os.listdir(asr_dir))
        response = self.client.post(
            "/api/audio_transcription/upload", headers=self.auth(),
            data={"file": (io.BytesIO(b"\0" * (25 * 1024 * 1024 + 1)), "big.mp3")},
            content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)
        self.assertIn("25MB", response.get_json()["error"])
        self.assertEqual(sorted(os.listdir(asr_dir)), before)


if __name__ == "__main__":
    unittest.main()

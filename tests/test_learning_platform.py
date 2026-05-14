import csv
import importlib
import io
import json
import os
import shutil
import tempfile
import unittest


class LearningPlatformTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ielts_learning_test_")
        self._patch_core_paths()

        import app

        self.app_module = importlib.reload(app)
        self.client = self.app_module.app.test_client()
        self.token = self._login()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _patch_core_paths(self):
        import core
        import routers.auth as auth
        import routers.vocabulary as vocabulary
        import routers.intensive_reading as intensive
        import routers.writing_logic as writing
        import routers.listening_review as listening
        import routers.community as community

        root = self.tmp
        path_map = {
            "MOTHER_DIR": os.path.join(root, "audio_files"),
            "COMBINED_DIR": os.path.join(root, "combined_audio"),
            "TOKEN_FILE": os.path.join(root, "tokens.json"),
            "USERS_FILE": os.path.join(root, "users.json"),
            "INTENSIVE_DIR": os.path.join(root, "intensive_articles"),
            "INTENSIVE_IMAGES_DIR": os.path.join(root, "intensive_articles", "images"),
            "VOCAB_AUDIO_DIR": os.path.join(root, "vocab_audio"),
            "VOCABULARY_BOOK_DIR": os.path.join(root, "vocabulary_book"),
            "VOCABULARY_CATEGORIES_DIR": os.path.join(root, "vocabulary_book", "categories"),
            "VOCABULARY_AUDIO_DIR": os.path.join(root, "vocabulary_book", "audio"),
            "VOCABULARY_TASKS_DIR": os.path.join(root, "vocabulary_book", "tasks"),
            "VOCABULARY_CHALLENGE_DIR": os.path.join(root, "vocabulary_book", "challenges"),
            "MESSAGE_BOARD_DIR": os.path.join(root, "message_board"),
            "MESSAGE_IMAGES_DIR": os.path.join(root, "message_board", "images"),
            "CHALLENGES_DIR": os.path.join(root, "challenges"),
            "AUDIO_TRANSCRIPTION_DIR": os.path.join(root, "audio_transcriptions"),
            "USER_DATA_DIR": os.path.join(root, "user_data"),
            "WRITING_DATA_DIR": os.path.join(root, "writing_correction", "data"),
            "WRITING_IMAGES_DIR": os.path.join(root, "writing_correction", "images"),
            "WRITING_CHAT_DIR": os.path.join(root, "writing_correction", "data", "chat_history"),
            "LISTENING_REVIEW_DIR": os.path.join(root, "listening_review"),
        }

        for module in (core, auth, vocabulary, intensive, writing, listening, community):
            for name, value in path_map.items():
                if hasattr(module, name):
                    setattr(module, name, value)

        core.init_directories()
        os.makedirs(path_map["VOCABULARY_CATEGORIES_DIR"], exist_ok=True)
        os.makedirs(path_map["VOCABULARY_TASKS_DIR"], exist_ok=True)
        os.makedirs(path_map["WRITING_DATA_DIR"], exist_ok=True)
        os.makedirs(path_map["LISTENING_REVIEW_DIR"], exist_ok=True)

        with open(path_map["USERS_FILE"], "w", encoding="utf-8") as f:
            json.dump(
                {
                    "tester": {
                        "username": "tester",
                        "password": "secret",
                        "display_name": "Test User",
                        "role": "admin",
                        "avatar": "avatar_admin.svg",
                    }
                },
                f,
            )

        self.paths = path_map

    def _login(self):
        response = self.client.post(
            "/user_login",
            json={"username": "tester", "password": "secret"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["success"])
        return data["token"]

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def write_json(self, path, value):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)

    def seed_vocabulary(self):
        self.write_json(
            os.path.join(self.paths["VOCABULARY_CATEGORIES_DIR"], "reading.json"),
            {
                "name": "Reading",
                "icon": "book",
                "subcategories": {
                    "default": {
                        "name": "Default",
                        "created_at": "2026-05-01T08:00:00",
                        "words": [
                            {
                                "id": "word-1",
                                "word": "erode",
                                "meaning": "to gradually destroy",
                                "created_at": "2026-05-01T08:30:00",
                                "is_favorited": True,
                                "audio_generated": True,
                            }
                        ],
                    }
                },
                "metadata": {
                    "created_at": "2026-05-01T08:00:00",
                    "last_updated": "2026-05-01T08:30:00",
                },
            },
        )

    def seed_writing(self):
        self.write_json(
            os.path.join(self.paths["WRITING_DATA_DIR"], "tester_practice.json"),
            [
                {
                    "id": "practice-1",
                    "timestamp": "2026-05-02T09:00:00",
                    "category": "People",
                    "subcategory": "Children",
                    "question": "Discuss both views.",
                    "target_chinese": "孩子更容易受影响。",
                    "user_translation": "Children are easy influenced.",
                    "score": "5.5",
                    "feedback": {"feedback_summary": "Grammar needs work."},
                    "native_version": "Children are more impressionable.",
                    "in_review": True,
                }
            ],
        )
        self.write_json(
            os.path.join(self.paths["WRITING_DATA_DIR"], "tester_small_practice.json"),
            [
                {
                    "id": "small-1",
                    "timestamp": "2026-05-03T10:00:00",
                    "chart_type": "Line",
                    "example_name": "Train use",
                    "target_chinese": "通勤人数上升。",
                    "user_translation": "The commuters increased.",
                    "score": "7.0",
                    "feedback": {},
                    "native_version": "The number of commuters rose.",
                    "in_review": True,
                }
            ],
        )

    def seed_listening(self):
        self.write_json(
            os.path.join(self.paths["LISTENING_REVIEW_DIR"], "tester_projects.json"),
            [
                {
                    "id": "lr-1",
                    "title": "Part 2 Practice",
                    "username": "tester",
                    "status": "completed",
                    "created_at": "2026-05-04T11:00:00",
                    "updated_at": "2026-05-04T12:00:00",
                    "mastered": False,
                    "checkin_count": 1,
                },
                {
                    "id": "lr-2",
                    "title": "Processing Practice",
                    "username": "tester",
                    "status": "processing",
                    "created_at": "2026-05-04T13:00:00",
                    "updated_at": "2026-05-04T13:05:00",
                },
            ],
        )
        self.write_json(
            os.path.join(self.paths["LISTENING_REVIEW_DIR"], "lr-1", "data.json"),
            {
                "segments": [{"id": 1, "text": "A useful phrase", "translation": "一个有用表达"}],
                "starred_segments": [1],
                "vocab_annotations": [{"word": "phrase", "meaning": "expression"}],
            },
        )

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/api/learning/dashboard")
        self.assertEqual(response.status_code, 401)

    def test_home_page_stays_as_quick_navigation(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("请选择模块", html)
        self.assertIn("Speaking 合集播放", html)
        self.assertIn("写作逻辑链训练", html)
        self.assertNotIn("今日复习队列", html)
        self.assertNotIn("学习首页", html)

    def test_dashboard_summarizes_learning_state(self):
        self.seed_vocabulary()
        self.seed_writing()
        self.seed_listening()

        response = self.client.get("/api/learning/dashboard", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["summary"]["vocabulary_words"], 1)
        self.assertEqual(data["summary"]["favorite_words"], 1)
        self.assertEqual(data["summary"]["writing_practices"], 2)
        self.assertEqual(data["summary"]["listening_projects"], 2)
        self.assertEqual(data["summary"]["active_tasks"], 1)
        self.assertGreaterEqual(len(data["recent_activity"]), 3)

    def test_review_queue_combines_vocab_writing_and_listening(self):
        self.seed_vocabulary()
        self.seed_writing()
        self.seed_listening()

        response = self.client.get("/api/learning/review_queue", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        items = response.get_json()["items"]
        sources = {item["source"] for item in items}
        self.assertIn("vocabulary", sources)
        self.assertIn("writing", sources)
        self.assertIn("listening", sources)

    def test_quick_vocab_adds_word_without_duplicate(self):
        self.seed_vocabulary()
        body = {
            "word": "cohesion",
            "meaning": "connection",
            "category": "writing",
            "subcategory_name": "From Writing",
            "source": "writing",
        }

        created = self.client.post("/api/learning/vocabulary", json=body, headers=self.auth_headers())
        duplicate = self.client.post("/api/learning/vocabulary", json=body, headers=self.auth_headers())

        self.assertEqual(created.status_code, 200)
        self.assertTrue(created.get_json()["success"])
        self.assertEqual(duplicate.status_code, 409)

    def test_vocabulary_export_returns_csv(self):
        self.seed_vocabulary()

        response = self.client.get("/api/learning/export/vocabulary", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "text/csv")
        rows = list(csv.DictReader(io.StringIO(response.get_data(as_text=True))))
        self.assertEqual(rows[0]["word"], "erode")

    def test_writing_export_returns_markdown(self):
        self.seed_writing()

        response = self.client.get("/api/learning/export/writing", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        text = response.get_data(as_text=True)
        self.assertIn("# Writing Practice Export", text)
        self.assertIn("Children are easy influenced.", text)

    def test_learning_tasks_reports_active_and_failed_work(self):
        self.seed_listening()
        self.write_json(
            os.path.join(self.paths["VOCABULARY_TASKS_DIR"], "task-1.json"),
            {
                "id": "task-1",
                "word": "cohesion",
                "status": "pending",
                "created_at": "2026-05-04T14:00:00",
            },
        )

        response = self.client.get("/api/learning/tasks", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        tasks = response.get_json()["tasks"]
        sources = {task["source"] for task in tasks}
        self.assertIn("vocabulary_audio", sources)
        self.assertIn("listening_review", sources)

    def test_listening_template_pauses_audio_during_vocab_lookup(self):
        response = self.client.get("/listening_review")

        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("beginVocabAudioPause", html)
        self.assertIn("endVocabAudioPause", html)
        self.assertIn("vocabAudioManualOverride", html)
        self.assertIn("hideSelectionBadge({ resumeAudio: false })", html)
        self.assertIn("markVocabAudioManualOverride", html)

    def test_json_store_round_trips_with_atomic_save(self):
        from utils.json_store import load_json, save_json_atomic

        path = os.path.join(self.tmp, "store", "sample.json")
        save_json_atomic(path, {"ok": True})

        self.assertEqual(load_json(path, {}), {"ok": True})

    def test_intensive_article_create_still_works(self):
        response = self.client.post(
            "/intensive_create",
            json={"title": "Optimization Flow", "category": "Reading", "content": "A short article."},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()

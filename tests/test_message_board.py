"""学习交流小天地：删帖时连同评论、评论里的挑战一起删。

数据目录都在临时目录里（沿用 test_auth_guard 的 AppTestBase），用户和内容都是编造的。
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402


class DeletePostCascadeTest(AppTestBase):
    def setUp(self):
        super().setUp()
        users = self.read_json(self.users_file)
        users["friend"] = {"username": "friend", "password": "secret2", "display_name": "Friend",
                           "role": "user", "avatar": "avatar_user.svg"}
        self.write_json(self.users_file, users)
        self.friend_token = self.login("friend", "secret2")
        self.challenges_dir = sys.modules["routers.community"].CHALLENGES_DIR
        self.comments_file = os.path.join(sys.modules["routers.community"].MESSAGE_BOARD_DIR, "comments.json")

    # ---------- 小工具 ----------
    def make_challenge(self, challenge_id):
        """在磁盘上放一个挑战文件和它的单词音频目录"""
        self.write_json(os.path.join(self.challenges_dir, f"{challenge_id}.json"),
                        {"id": challenge_id, "title": "t", "vocabulary": [], "participants": {}})
        audio_dir = os.path.join(self.core.VOCAB_AUDIO_DIR, f"challenge_{challenge_id}")
        os.makedirs(audio_dir, exist_ok=True)
        with open(os.path.join(audio_dir, "word.mp3"), "wb") as f:
            f.write(b"fake")
        return {"id": challenge_id, "title": "t", "description": "", "vocabulary_count": 0, "mentioned_users": []}

    def challenge_exists(self, challenge_id):
        return os.path.exists(os.path.join(self.challenges_dir, f"{challenge_id}.json"))

    def challenge_audio_exists(self, challenge_id):
        return os.path.isdir(os.path.join(self.core.VOCAB_AUDIO_DIR, f"challenge_{challenge_id}"))

    def post(self, text, challenge=None, token=None):
        response = self.client.post("/api/messages", headers=self.auth(token), json={
            "type": "mixed_content",
            "content": {"text": text, "audios": [], "articles": [], "images": [], "challenge": challenge}})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["message"]["id"]

    def comment(self, post_id, text, challenge=None, token=None):
        response = self.client.post("/api/comments", headers=self.auth(token), json={
            "post_id": post_id, "type": "mixed_content",
            "content": {"text": text, "audios": [], "articles": [], "images": [], "challenge": challenge}})
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()["comment"]["id"]

    def comment_ids(self):
        return [c["id"] for c in self.read_json(self.comments_file)]

    # ---------- 测试 ----------
    def test_deleting_a_post_removes_its_comments_and_their_challenges(self):
        post_id = self.post("today's words", self.make_challenge("ch-post-0001"))
        self.comment(post_id, "nice", token=self.friend_token)
        self.comment(post_id, "try mine", self.make_challenge("ch-comment-0001"), token=self.friend_token)
        self.comment(post_id, "thanks")

        other_post = self.post("another post")
        kept_comment = self.comment(other_post, "keep me", self.make_challenge("ch-other-0001"),
                                    token=self.friend_token)

        response = self.client.delete(f"/api/messages/{post_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"success": True, "deleted_comments": 3})

        self.assertEqual(self.comment_ids(), [kept_comment])
        self.assertEqual(self.client.get(f"/api/comments/{post_id}", headers=self.auth()).get_json()["comments"], [])
        for challenge_id in ("ch-post-0001", "ch-comment-0001"):
            self.assertFalse(self.challenge_exists(challenge_id), challenge_id)
            self.assertFalse(self.challenge_audio_exists(challenge_id), challenge_id)
        self.assertTrue(self.challenge_exists("ch-other-0001"))
        self.assertTrue(self.challenge_audio_exists("ch-other-0001"))

        remaining = [m["id"] for m in self.client.get("/api/messages", headers=self.auth()).get_json()["messages"]]
        self.assertEqual(remaining, [other_post])

    def test_challenge_still_attached_elsewhere_is_kept(self):
        shared = self.make_challenge("ch-shared-0001")
        post_id = self.post("first", shared)
        other_post = self.post("second", token=self.friend_token)
        self.comment(other_post, "same challenge here", shared, token=self.friend_token)

        response = self.client.delete(f"/api/messages/{post_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.challenge_exists("ch-shared-0001"))
        self.assertTrue(self.challenge_audio_exists("ch-shared-0001"))

    def test_post_without_comments_or_challenge_still_deletes(self):
        post_id = self.post("plain")
        other_post = self.post("other")
        kept_comment = self.comment(other_post, "hello")

        response = self.client.delete(f"/api/messages/{post_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["deleted_comments"], 0)
        self.assertEqual(self.comment_ids(), [kept_comment])

    def test_old_comment_formats_do_not_break_the_cascade(self):
        post_id = self.post("old data")
        self.comment(post_id, "fine")
        comments = self.read_json(self.comments_file)
        comments += [
            {"id": "comment_old_1", "post_id": post_id, "type": "text", "content": "plain string"},
            {"id": "comment_old_2", "post_id": post_id, "type": "mixed_content", "content": "not a dict"},
            {"id": "comment_old_3", "post_id": post_id, "type": "mixed_content", "content": {"challenge": "x"}},
        ]
        self.write_json(self.comments_file, comments)

        response = self.client.delete(f"/api/messages/{post_id}", headers=self.auth())
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["deleted_comments"], 4)
        self.assertEqual(self.comment_ids(), [])

    def test_someone_elses_post_is_refused_and_nothing_is_removed(self):
        post_id = self.post("mine", self.make_challenge("ch-mine-0001"))
        comment_id = self.comment(post_id, "reply", self.make_challenge("ch-reply-0001"), token=self.friend_token)

        response = self.client.delete(f"/api/messages/{post_id}", headers=self.auth(self.friend_token))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.comment_ids(), [comment_id])
        self.assertTrue(self.challenge_exists("ch-mine-0001"))
        self.assertTrue(self.challenge_exists("ch-reply-0001"))


if __name__ == "__main__":
    unittest.main()

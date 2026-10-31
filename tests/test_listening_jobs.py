"""听力精听的后台转录任务和项目文件读写：重启后卡住的项目、只重做翻译的重试、音频归属、并发写入。

数据目录都在临时目录里（见 AppTestBase）；转录和润色翻译换成桩，不发任何网络请求。
项目、句子都是编造的测试数据。
"""

import io
import json
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_auth_guard import AppTestBase  # noqa: E402

PID = 'lr_20260101_120000_test0001'
FAKE_ASR = {
    'segments': [
        {'id': 0, 'start': 0.0, 'end': 1.5, 'text': 'the museum opens at nine'},
        {'id': 1, 'start': 1.5, 'end': 3.0, 'text': 'tickets cost twelve pounds'},
    ],
    'duration': 3.0,
}


class ListeningJobsTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.lr = sys.modules['routers.listening_review']
        self._patch(self.lr, '_active_jobs', {})
        self.asr_calls = []
        self.polish_calls = []
        self.asr_error = None
        self.polish_error = None
        self.asr_gate = None   # threading.Event: 设了就让假转录停在那里等

        def fake_transcribe(audio_path):
            self.asr_calls.append(audio_path)
            if self.asr_gate is not None:
                self.asr_gate.wait(5)
            if self.asr_error:
                return None, self.asr_error
            return json.loads(json.dumps(FAKE_ASR)), None

        def fake_polish(segments):
            self.polish_calls.append(segments)
            if self.polish_error:
                return None, self.polish_error
            return [{'id': s['id'], 'text': s['text'].capitalize() + '.', 'translation': f'译文{s["id"]}'}
                    for s in segments], None

        self._patch(self.lr, '_transcribe', fake_transcribe)
        self._patch(self.lr, '_polish_and_translate', fake_polish)

    # ---------- helpers ----------

    def lr_path(self, *parts):
        return os.path.join(self.lr.LISTENING_REVIEW_DIR, *parts)

    def seed_project(self, status, pid=PID, user='tester', **extra):
        record = {
            'id': pid, 'title': 'Part 1 · Museum Visit', 'username': user, 'status': status,
            'created_at': '2026-01-01T12:00:00', 'updated_at': '2026-01-01T12:00:00',
            'duration': None, 'audio_filename': 'original.mp3', 'source_type': 'upload',
            'source_url': None, 'error': None,
        }
        record.update(extra)
        path = self.lr_path(f'{user}_projects.json')
        projects = self.read_json(path) if os.path.exists(path) else []
        projects.append(record)
        self.write_json(path, projects)
        os.makedirs(self.lr_path(pid), exist_ok=True)
        with open(self.lr_path(pid, 'original.mp3'), 'wb') as f:
            f.write(b'ID3 fake audio')
        return record

    def seed_transcript(self, pid=PID):
        self.write_json(self.lr_path(pid, 'transcript.json'), FAKE_ASR)

    def project(self, pid=PID, user='tester'):
        for p in self.read_json(self.lr_path(f'{user}_projects.json')):
            if p['id'] == pid:
                return p
        return None

    def wait_jobs(self):
        for thread in list(self.lr._active_jobs.values()):
            thread.join(5)
            self.assertFalse(thread.is_alive(), 'background job did not finish')

    def upload(self):
        response = self.client.post(
            '/api/listening_review/upload', headers=self.auth(),
            data={'file': (io.BytesIO(b'ID3 fake audio'), 'museum.mp3'), 'title': 'Museum'},
            content_type='multipart/form-data')
        self.assertEqual(response.status_code, 200, response.get_json())
        return response.get_json()['project_id']

    def retry(self, pid=PID):
        return self.client.post(f'/api/listening_review/project/{pid}/retry', headers=self.auth())

    # ---------- B1: 转录中途服务重启 ----------

    def test_list_marks_project_interrupted_by_restart_as_failed(self):
        self.seed_project('processing')

        projects = self.client.get('/api/listening_review/list', headers=self.auth()).get_json()['projects']

        self.assertEqual(projects[0]['status'], 'error')
        self.assertEqual(projects[0]['error_phase'], 'transcribe')
        self.assertEqual(projects[0]['error'], self.lr.INTERRUPTED_ERROR)
        self.assertEqual(self.project()['status'], 'error')   # 写回了文件

    def test_interrupted_translation_with_saved_transcript_resumes_at_polish(self):
        self.seed_project('translating', duration=3.0)
        self.seed_transcript()

        projects = self.client.get('/api/listening_review/list', headers=self.auth()).get_json()['projects']
        self.assertEqual(projects[0]['error_phase'], 'polish')

        response = self.retry()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['phase'], 'polish')
        self.wait_jobs()

        self.assertEqual(self.project()['status'], 'completed')
        self.assertEqual(self.asr_calls, [])
        data = self.read_json(self.lr_path(PID, 'data.json'))
        self.assertEqual([s['translation'] for s in data['segments']], ['译文0', '译文1'])
        self.assertEqual(data['segments'][0]['start'], 0.0)

    def test_retry_accepts_project_stuck_in_processing(self):
        self.seed_project('processing')

        response = self.retry()
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['phase'], 'transcribe')
        self.wait_jobs()

        self.assertEqual(self.project()['status'], 'completed')
        self.assertEqual(len(self.asr_calls), 1)

    def test_running_job_is_not_marked_interrupted(self):
        self.asr_gate = threading.Event()
        pid = self.upload()
        try:
            projects = self.client.get('/api/listening_review/list', headers=self.auth()).get_json()['projects']
            self.assertEqual(projects[0]['status'], 'processing')
            response = self.retry(pid)
            self.assertEqual(response.status_code, 400)   # 正在跑的不能再点重试
        finally:
            self.asr_gate.set()
        self.wait_jobs()
        self.assertEqual(self.project(pid)['status'], 'completed')
        self.assertEqual(len(self.asr_calls), 1)

    # ---------- B2: 只是润色翻译失败时，重试不再重新转录 ----------

    def test_polish_failure_keeps_transcript_and_retry_skips_asr(self):
        self.polish_error = 'WildAPI API error: HTTP 504'
        pid = self.upload()
        self.wait_jobs()
        project = self.project(pid)
        self.assertEqual((project['status'], project['error_phase']), ('error', 'polish'))
        self.assertTrue(os.path.exists(self.lr_path(pid, 'transcript.json')))
        self.assertEqual(len(self.asr_calls), 1)

        self.polish_error = None
        response = self.retry(pid)
        self.assertEqual(response.get_json()['phase'], 'polish')
        self.wait_jobs()

        self.assertEqual(self.project(pid)['status'], 'completed')
        self.assertEqual(len(self.asr_calls), 1)       # 没有再转录一次
        self.assertEqual(len(self.polish_calls), 2)
        data = self.read_json(self.lr_path(pid, 'data.json'))
        self.assertEqual(data['segments'][1]['text'], 'Tickets cost twelve pounds.')

    def test_transcription_failure_retry_transcribes_again(self):
        self.asr_error = 'WildAPI API error: HTTP 500'
        pid = self.upload()
        self.wait_jobs()
        self.assertEqual(self.project(pid)['error_phase'], 'transcribe')
        self.assertFalse(os.path.exists(self.lr_path(pid, 'transcript.json')))

        self.asr_error = None
        response = self.retry(pid)
        self.assertEqual(response.get_json()['phase'], 'transcribe')
        self.wait_jobs()

        self.assertEqual(self.project(pid)['status'], 'completed')
        self.assertEqual(len(self.asr_calls), 2)

    def test_delete_during_transcription_does_not_recreate_project_folder(self):
        self.asr_gate = threading.Event()
        pid = self.upload()
        response = self.client.delete(f'/api/listening_review/project/{pid}', headers=self.auth())
        self.assertEqual(response.status_code, 200)
        self.asr_gate.set()
        self.wait_jobs()

        self.assertFalse(os.path.exists(self.lr_path(pid)))
        self.assertIsNone(self.project(pid))

    # ---------- B3: 音频只给项目主人 ----------

    def test_audio_is_served_only_to_the_owner(self):
        users = self.read_json(self.users_file)
        users['other'] = {'username': 'other', 'password': 'secret2', 'display_name': 'Other',
                          'role': 'user', 'avatar': 'avatar_admin.svg'}
        self.write_json(self.users_file, users)
        other_token = self.login('other', 'secret2')
        self.seed_project('completed')
        self.write_json(self.lr_path(PID, 'data.json'), {'segments': []})

        url = f'/api/listening_review/audio/{PID}/original.mp3'
        own = self.client.get(f'{url}?token={self.token}')
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.get_data(), b'ID3 fake audio')
        own.close()

        self.assertEqual(self.client.get(f'{url}?token={other_token}').status_code, 404)
        self.assertEqual(self.client.get(url, headers=self.auth(other_token)).status_code, 404)
        data_url = f'/api/listening_review/audio/{PID}/data.json?token={self.token}'
        self.assertEqual(self.client.get(data_url).status_code, 404)

    # ---------- B4: 项目文件并发写入 ----------

    def _slow_down_project_reads(self):
        """读完项目列表后停一下，把「读-改-写」之间的空当拉长，没加锁的话必然互相覆盖"""
        original = self.lr._load_user_projects

        def slow(username):
            projects = original(username)
            time.sleep(0.02)
            return projects
        self._patch(self.lr, '_load_user_projects', slow)

    def test_concurrent_checkins_are_all_kept(self):
        self.seed_project('completed', checkin_count=0)
        self._slow_down_project_reads()
        statuses = []

        def checkin():
            client = self.app.test_client()
            response = client.post(f'/api/listening_review/project/{PID}/checkin', headers=self.auth())
            statuses.append(response.status_code)

        threads = [threading.Thread(target=checkin) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(10)

        self.assertEqual(statuses, [200] * 8)
        self.assertEqual(self.project()['checkin_count'], 8)

    def test_background_status_update_keeps_concurrent_user_change(self):
        self.seed_project('completed', checkin_count=0)
        self._slow_down_project_reads()

        worker = threading.Thread(target=self.lr._update_project_status, args=('tester', PID),
                                  kwargs={'duration': 99.0})
        worker.start()
        response = self.client.post(f'/api/listening_review/project/{PID}/checkin', headers=self.auth())
        worker.join(10)

        self.assertEqual(response.status_code, 200)
        project = self.project()
        self.assertEqual((project['checkin_count'], project['duration']), (1, 99.0))

    def test_failed_write_leaves_previous_project_list_intact(self):
        self.seed_project('completed')
        real_dump = json.dump

        def broken_dump(obj, fp, **kwargs):
            fp.write('[{"id": ')
            raise OSError('disk full')

        self._patch(json, 'dump', broken_dump)
        with self.assertRaises(OSError):
            self.lr._save_user_projects('tester', [])
        json.dump = real_dump

        self.assertEqual([p['id'] for p in self.lr._load_user_projects('tester')], [PID])


if __name__ == '__main__':
    unittest.main()

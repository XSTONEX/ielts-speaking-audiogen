from flask import Blueprint, request, jsonify, send_file
import os, json, re, uuid, threading, shutil, requests, time
from datetime import datetime
from core import LISTENING_REVIEW_DIR, is_token_valid, load_tokens, get_proxies

listening_review_bp = Blueprint('listening_review', __name__)

ALLOWED_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.mp4', '.webm'}
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB


# ==================== Helper Functions ====================

def _user_projects_path(username):
    return os.path.join(LISTENING_REVIEW_DIR, f'{username}_projects.json')

def _load_user_projects(username):
    path = _user_projects_path(username)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def _save_user_projects(username, projects):
    with open(_user_projects_path(username), 'w', encoding='utf-8') as f:
        json.dump(projects, f, ensure_ascii=False, indent=2)

def _project_dir(project_id):
    return os.path.join(LISTENING_REVIEW_DIR, project_id)

def _project_data_path(project_id):
    return os.path.join(_project_dir(project_id), 'data.json')

def _load_project_data(project_id):
    path = _project_data_path(project_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def _save_project_data(project_id, data):
    with open(_project_data_path(project_id), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def _generate_project_id():
    return f"lr_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

def _get_auth_username():
    """Extract and validate token, return username or None."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not token:
        token = request.args.get('token', '')
    if not token or not is_token_valid(token):
        return None
    tokens = load_tokens()
    return tokens.get(token, {}).get('username')

def _find_user_project(username, project_id):
    """Find a project by id in user's project list. Returns (projects, index) or (projects, -1)."""
    projects = _load_user_projects(username)
    for i, p in enumerate(projects):
        if p['id'] == project_id:
            return projects, i
    return projects, -1


def _call_groq_transcription(audio_file_path, max_retries=3):
    """Call Groq Whisper API with verbose_json to get timestamped segments."""
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        return None, 'GROQ_API_KEY not configured'

    url = "https://api.groq.com/openai/v1/audio/transcriptions"
    proxies = get_proxies()

    for attempt in range(max_retries):
        try:
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': (os.path.basename(audio_file_path), audio_file)}
                data = {
                    'model': 'whisper-large-v3-turbo',
                    'response_format': 'verbose_json',
                    'timestamp_granularities[]': 'segment',
                    'temperature': '0'
                }
                headers = {'Authorization': f'Bearer {api_key}'}
                response = requests.post(url, headers=headers, files=files, data=data, timeout=(10, 300), proxies=proxies)

                if response.status_code == 200:
                    result = response.json()
                    segments = []
                    for i, seg in enumerate(result.get('segments', [])):
                        segments.append({
                            'id': i,
                            'start': seg['start'],
                            'end': seg['end'],
                            'text': seg.get('text', '').strip()
                        })
                    duration = result.get('duration', 0)
                    return {'segments': segments, 'duration': duration}, None

                error_msg = f"Groq API error: HTTP {response.status_code}"
                try:
                    detail = response.json()
                    if 'error' in detail:
                        msg = detail['error'].get('message', detail['error']) if isinstance(detail['error'], dict) else detail['error']
                        error_msg += f" - {msg}"
                except:
                    error_msg += f" - {response.text[:200]}"

                if response.status_code in [400, 401, 403, 413]:
                    return None, error_msg
                if attempt == max_retries - 1:
                    return None, error_msg

        except requests.exceptions.Timeout:
            if attempt == max_retries - 1:
                return None, '请求超时'
            time.sleep(2 ** attempt)
        except requests.exceptions.ConnectionError as e:
            if attempt == max_retries - 1:
                return None, f'连接错误: {e}'
            time.sleep(2 ** attempt)
        except Exception as e:
            if attempt == max_retries - 1:
                return None, str(e)
            time.sleep(2 ** attempt)

    return None, f'转录失败，已重试 {max_retries} 次'


def _download_audio_from_url(url_str, save_path):
    """Download audio from a direct URL. Returns (path, None) or (None, error)."""
    try:
        head = requests.head(url_str, timeout=10, allow_redirects=True)
        cl = head.headers.get('Content-Length')
        if cl and int(cl) > MAX_FILE_SIZE:
            return None, '文件大小超过25MB限制'
    except:
        pass

    try:
        resp = requests.get(url_str, stream=True, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        return None, f'下载失败: {e}'

    downloaded = 0
    with open(save_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            downloaded += len(chunk)
            if downloaded > MAX_FILE_SIZE:
                f.close()
                os.remove(save_path)
                return None, '文件大小超过25MB限制'
            f.write(chunk)

    return save_path, None


def _transcribe_async(project_id, audio_path, username):
    """Run transcription in background thread and update project record."""
    try:
        result, error = _call_groq_transcription(audio_path)

        projects = _load_user_projects(username)
        for i, p in enumerate(projects):
            if p['id'] == project_id:
                if result:
                    projects[i]['status'] = 'completed'
                    projects[i]['duration'] = result['duration']
                    projects[i]['updated_at'] = datetime.now().isoformat()

                    project_data = {
                        'segments': result['segments'],
                        'starred_segments': [],
                        'vocab_annotations': []
                    }
                    _save_project_data(project_id, project_data)
                else:
                    projects[i]['status'] = 'error'
                    projects[i]['error'] = error
                    projects[i]['updated_at'] = datetime.now().isoformat()
                break
        _save_user_projects(username, projects)
        print(f"Listening review transcription done: {project_id}")

    except Exception as e:
        print(f"Listening review transcription failed: {e}")
        projects = _load_user_projects(username)
        for i, p in enumerate(projects):
            if p['id'] == project_id:
                projects[i]['status'] = 'error'
                projects[i]['error'] = str(e)
                projects[i]['updated_at'] = datetime.now().isoformat()
                break
        _save_user_projects(username, projects)


# ==================== Routes ====================

@listening_review_bp.route('/listening_review')
def listening_review_page():
    return send_file('templates/listening.html')


@listening_review_bp.route('/api/listening_review/upload', methods=['POST'])
def upload_audio():
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    if 'file' not in request.files:
        return jsonify({'error': '没有上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400

    title = request.form.get('title', '').strip() or os.path.splitext(file.filename)[0]

    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的音频格式，支持: {", ".join(ALLOWED_EXTENSIONS)}'}), 400

    # Read file to check size
    file_data = file.read()
    if len(file_data) > MAX_FILE_SIZE:
        return jsonify({'error': '文件大小不能超过25MB'}), 400

    project_id = _generate_project_id()
    proj_dir = _project_dir(project_id)
    os.makedirs(proj_dir, exist_ok=True)

    audio_filename = f"original{file_ext}"
    audio_path = os.path.join(proj_dir, audio_filename)
    with open(audio_path, 'wb') as f:
        f.write(file_data)

    project_record = {
        'id': project_id,
        'title': title,
        'username': username,
        'status': 'processing',
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'duration': None,
        'audio_filename': audio_filename,
        'source_type': 'upload',
        'source_url': None,
        'error': None
    }

    projects = _load_user_projects(username)
    projects.append(project_record)
    _save_user_projects(username, projects)

    thread = threading.Thread(target=_transcribe_async, args=(project_id, audio_path, username), daemon=True)
    thread.start()

    return jsonify({'success': True, 'project_id': project_id, 'message': '音频上传成功，正在转录中...'})


@listening_review_bp.route('/api/listening_review/url', methods=['POST'])
def download_url_audio():
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    body = request.get_json(silent=True) or {}
    url_str = body.get('url', '').strip()
    title = body.get('title', '').strip()

    if not url_str:
        return jsonify({'error': '请提供音频URL'}), 400

    # Determine extension from URL
    from urllib.parse import urlparse, unquote
    parsed = urlparse(unquote(url_str))
    path_ext = os.path.splitext(parsed.path)[1].lower()
    if path_ext not in ALLOWED_EXTENSIONS:
        path_ext = '.mp3'  # fallback

    if not title:
        title = os.path.splitext(os.path.basename(parsed.path))[0] or 'Untitled'

    project_id = _generate_project_id()
    proj_dir = _project_dir(project_id)
    os.makedirs(proj_dir, exist_ok=True)

    audio_filename = f"original{path_ext}"
    audio_path = os.path.join(proj_dir, audio_filename)

    # Download in the request handler so we can report errors immediately
    _, dl_error = _download_audio_from_url(url_str, audio_path)
    if dl_error:
        shutil.rmtree(proj_dir, ignore_errors=True)
        return jsonify({'error': dl_error}), 400

    project_record = {
        'id': project_id,
        'title': title,
        'username': username,
        'status': 'processing',
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'duration': None,
        'audio_filename': audio_filename,
        'source_type': 'url',
        'source_url': url_str,
        'error': None
    }

    projects = _load_user_projects(username)
    projects.append(project_record)
    _save_user_projects(username, projects)

    thread = threading.Thread(target=_transcribe_async, args=(project_id, audio_path, username), daemon=True)
    thread.start()

    return jsonify({'success': True, 'project_id': project_id, 'message': '音频下载成功，正在转录中...'})


@listening_review_bp.route('/api/listening_review/list', methods=['GET'])
def list_projects():
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects = _load_user_projects(username)
    projects.sort(key=lambda x: x.get('created_at', ''), reverse=True)

    return jsonify({'success': True, 'projects': projects})


@listening_review_bp.route('/api/listening_review/project/<project_id>', methods=['GET'])
def get_project(project_id):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects, idx = _find_user_project(username, project_id)
    if idx == -1:
        return jsonify({'error': '项目不存在'}), 404

    project = projects[idx]
    data = _load_project_data(project_id)

    return jsonify({
        'success': True,
        'project': project,
        'data': data  # may be None if still processing
    })


@listening_review_bp.route('/api/listening_review/project/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects, idx = _find_user_project(username, project_id)
    if idx == -1:
        return jsonify({'error': '项目不存在'}), 404

    # Remove project directory
    proj_dir = _project_dir(project_id)
    if os.path.exists(proj_dir):
        shutil.rmtree(proj_dir)

    projects.pop(idx)
    _save_user_projects(username, projects)

    return jsonify({'success': True, 'message': '项目已删除'})


@listening_review_bp.route('/api/listening_review/project/<project_id>/star', methods=['PUT'])
def toggle_star(project_id):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects, idx = _find_user_project(username, project_id)
    if idx == -1:
        return jsonify({'error': '项目不存在'}), 404

    body = request.get_json(silent=True) or {}
    segment_id = body.get('segment_id')
    if segment_id is None:
        return jsonify({'error': '缺少 segment_id'}), 400

    data = _load_project_data(project_id)
    if not data:
        return jsonify({'error': '项目数据不存在'}), 404

    starred = data.get('starred_segments', [])
    if segment_id in starred:
        starred.remove(segment_id)
    else:
        starred.append(segment_id)
    data['starred_segments'] = starred
    _save_project_data(project_id, data)

    return jsonify({'success': True, 'starred_segments': starred})


@listening_review_bp.route('/api/listening_review/project/<project_id>/vocab', methods=['PUT'])
def add_vocab(project_id):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects, idx = _find_user_project(username, project_id)
    if idx == -1:
        return jsonify({'error': '项目不存在'}), 404

    body = request.get_json(silent=True) or {}
    segment_id = body.get('segment_id')
    word = body.get('word', '').strip()
    meaning = body.get('meaning', '').strip()
    start_offset = body.get('start_offset')
    end_offset = body.get('end_offset')

    if segment_id is None or not word or not meaning or start_offset is None or end_offset is None:
        return jsonify({'error': '缺少必要参数'}), 400

    data = _load_project_data(project_id)
    if not data:
        return jsonify({'error': '项目数据不存在'}), 404

    annotations = data.get('vocab_annotations', [])

    # Check if same word at same position already exists, update it
    existing_id = body.get('id')
    if existing_id:
        for ann in annotations:
            if ann['id'] == existing_id:
                ann['meaning'] = meaning
                break
    else:
        annotation = {
            'id': f"v_{str(uuid.uuid4())[:6]}",
            'segment_id': segment_id,
            'word': word,
            'meaning': meaning,
            'start_offset': start_offset,
            'end_offset': end_offset
        }
        annotations.append(annotation)

    data['vocab_annotations'] = annotations
    _save_project_data(project_id, data)

    return jsonify({'success': True, 'data': data})


@listening_review_bp.route('/api/listening_review/project/<project_id>/vocab/<word_id>', methods=['DELETE'])
def delete_vocab(project_id, word_id):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未登录或token无效'}), 401

    projects, idx = _find_user_project(username, project_id)
    if idx == -1:
        return jsonify({'error': '项目不存在'}), 404

    data = _load_project_data(project_id)
    if not data:
        return jsonify({'error': '项目数据不存在'}), 404

    annotations = data.get('vocab_annotations', [])
    data['vocab_annotations'] = [a for a in annotations if a['id'] != word_id]
    _save_project_data(project_id, data)

    return jsonify({'success': True, 'data': data})


@listening_review_bp.route('/api/listening_review/audio/<project_id>/<filename>')
def serve_audio(project_id, filename):
    username = _get_auth_username()
    if not username:
        return jsonify({'error': '未授权'}), 401

    proj_dir = _project_dir(project_id)
    file_path = os.path.join(proj_dir, filename)

    if not os.path.exists(file_path):
        return jsonify({'error': '文件不存在'}), 404

    return send_file(file_path)

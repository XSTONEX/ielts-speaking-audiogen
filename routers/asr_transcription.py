from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json, re, uuid, threading, shutil, requests, time
from datetime import datetime
from werkzeug.utils import secure_filename
from core import AUDIO_TRANSCRIPTION_DIR, verify_token_from_request, is_token_valid, load_tokens

asr_bp = Blueprint('asr', __name__)


# ==================== 音频转文本相关辅助函数 ====================

def load_transcription_data():
    """加载转录数据"""
    transcription_file = os.path.join(AUDIO_TRANSCRIPTION_DIR, 'transcriptions.json')
    if os.path.exists(transcription_file):
        try:
            with open(transcription_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_transcription_data(transcriptions):
    """保存转录数据"""
    transcription_file = os.path.join(AUDIO_TRANSCRIPTION_DIR, 'transcriptions.json')
    with open(transcription_file, 'w', encoding='utf-8') as f:
        json.dump(transcriptions, f, ensure_ascii=False, indent=2)

def generate_transcription_id():
    """生成转录ID"""
    return f"trans_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

def create_transcription_folder(transcription_id, title):
    """创建转录文件夹"""
    # 使用安全的文件夹名称
    safe_title = re.sub(r'[^\w\-_\.]', '_', title)[:50]
    folder_name = f"{transcription_id}_{safe_title}"
    folder_path = os.path.join(AUDIO_TRANSCRIPTION_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def call_transcription_api(audio_file_path, language=None, max_retries=3):
    """调用音频转文本API，带重试机制"""
    api_key = os.getenv('DEER_API_KEY')
    if not api_key:
        return None, 'API密钥未配置'

    url = "https://api.deerapi.com/v1/audio/transcriptions"

    for attempt in range(max_retries):
        try:
            print(f"转录API调用尝试 {attempt + 1}/{max_retries}")

            # 准备请求数据
            with open(audio_file_path, 'rb') as audio_file:
                files = {'file': audio_file}
                data = {
                    'model': 'whisper-1',
                    'response_format': 'json',
                    'temperature': '0'
                }

                if language:
                    data['language'] = language

                headers = {
                    'Authorization': f'Bearer {api_key}'
                }

                # 设置不同的超时时间
                timeout = (10, 300)  # (连接超时, 读取超时)

                response = requests.post(url, headers=headers, files=files, data=data, timeout=timeout)

                if response.status_code == 200:
                    result = response.json()
                    text = result.get('text', '')
                    if text.strip():  # 确保返回的文本不为空
                        print(f"转录成功，尝试次数: {attempt + 1}")
                        return text, None
                    else:
                        print(f"转录返回空文本，尝试 {attempt + 1} 失败")
                        if attempt == max_retries - 1:
                            return None, "转录结果为空"
                        continue
                else:
                    error_msg = f"API请求失败: HTTP {response.status_code}"
                    try:
                        error_detail = response.json()
                        if 'error' in error_detail:
                            error_msg += f" - {error_detail['error'].get('message', error_detail['error'])}"
                    except:
                        error_msg += f" - {response.text[:200]}"

                    print(f"API请求失败，尝试 {attempt + 1}: {error_msg}")

                    # 对于某些错误码，不进行重试
                    if response.status_code in [400, 401, 403, 413]:  # 客户端错误
                        return None, error_msg

                    if attempt == max_retries - 1:
                        return None, error_msg

        except requests.exceptions.Timeout as e:
            error_msg = f"请求超时: {str(e)}"
            print(f"请求超时，尝试 {attempt + 1}: {error_msg}")
            if attempt == max_retries - 1:
                return None, error_msg
            # 超时后等待一段时间再重试
            time.sleep(2 ** attempt)  # 指数退避

        except requests.exceptions.ConnectionError as e:
            error_msg = f"网络连接错误: {str(e)}"
            print(f"网络连接错误，尝试 {attempt + 1}: {error_msg}")
            if attempt == max_retries - 1:
                return None, error_msg
            # 连接错误后等待更长时间
            time.sleep(5 + (2 ** attempt))

        except requests.exceptions.RequestException as e:
            error_msg = f"请求异常: {str(e)}"
            print(f"请求异常，尝试 {attempt + 1}: {error_msg}")
            if attempt == max_retries - 1:
                return None, error_msg
            time.sleep(2 ** attempt)

        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            print(f"未知错误，尝试 {attempt + 1}: {error_msg}")
            if attempt == max_retries - 1:
                return None, error_msg
            time.sleep(1 + attempt)

    return None, f"转录失败，已重试 {max_retries} 次"


# ==================== 音频转文本路由 ====================

@asr_bp.route('/audio_transcription')
def audio_transcription_page():
    """音频转文本页面"""
    return send_file('templates/audio_transcription.html')

@asr_bp.route('/api/audio_transcription/upload', methods=['POST'])
def upload_audio_for_transcription():
    """上传音频文件并进行转录"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401

        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401

        # 获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username', 'unknown')

        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400

        file = request.files['file']
        title = request.form.get('title', '').strip()
        language = request.form.get('language', '').strip()

        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400

        if not title:
            title = os.path.splitext(file.filename)[0]

        # 验证文件类型
        allowed_extensions = {'.mp3', '.wav', '.m4a', '.flac', '.ogg', '.mp4', '.webm'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': '不支持的音频格式'}), 400

        # 验证文件大小 (25MB)
        if file.content_length and file.content_length > 25 * 1024 * 1024:
            return jsonify({'error': '文件大小不能超过25MB'}), 400

        # 生成转录ID和创建文件夹
        transcription_id = generate_transcription_id()
        folder_path = create_transcription_folder(transcription_id, title)

        # 保存原始音频文件
        audio_filename = f"original{file_ext}"
        audio_path = os.path.join(folder_path, audio_filename)
        file.save(audio_path)

        # 创建转录记录
        transcription_record = {
            'id': transcription_id,
            'title': title,
            'username': username,
            'status': 'processing',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'audio_filename': audio_filename,
            'audio_url': f'/api/audio_transcription/audio/{transcription_id}/{audio_filename}',
            'folder_path': os.path.basename(folder_path),
            'text': None,
            'language': language if language else None
        }

        # 保存到数据库
        transcriptions = load_transcription_data()
        transcriptions.append(transcription_record)
        save_transcription_data(transcriptions)

        # 异步进行转录
        def transcribe_async():
            try:
                # 调用转录API
                text, error = call_transcription_api(audio_path, language if language else None)

                # 更新记录
                transcriptions = load_transcription_data()
                for i, trans in enumerate(transcriptions):
                    if trans['id'] == transcription_id:
                        if text:
                            transcriptions[i]['status'] = 'completed'
                            transcriptions[i]['text'] = text
                            transcriptions[i]['updated_at'] = datetime.now().isoformat()

                            # 保存文本文件
                            text_path = os.path.join(folder_path, 'transcription.txt')
                            with open(text_path, 'w', encoding='utf-8') as f:
                                f.write(text)
                        else:
                            transcriptions[i]['status'] = 'error'
                            transcriptions[i]['error'] = error
                            transcriptions[i]['updated_at'] = datetime.now().isoformat()
                        break

                save_transcription_data(transcriptions)
                print(f"转录完成: {transcription_id}")

            except Exception as e:
                print(f"转录异步处理失败: {e}")
                # 更新状态为错误
                transcriptions = load_transcription_data()
                for i, trans in enumerate(transcriptions):
                    if trans['id'] == transcription_id:
                        transcriptions[i]['status'] = 'error'
                        transcriptions[i]['error'] = str(e)
                        transcriptions[i]['updated_at'] = datetime.now().isoformat()
                        break
                save_transcription_data(transcriptions)

        # 启动异步转录
        thread = threading.Thread(target=transcribe_async, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'transcription_id': transcription_id,
            'message': '音频上传成功，正在转录中...'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@asr_bp.route('/api/audio_transcription/list', methods=['GET'])
def list_audio_transcriptions():
    """获取用户的转录列表"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401

        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401

        # 获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username', 'unknown')

        # 加载转录数据
        transcriptions = load_transcription_data()

        # 筛选当前用户的转录记录
        user_transcriptions = [
            trans for trans in transcriptions
            if trans.get('username') == username
        ]

        # 按时间倒序排列
        user_transcriptions.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return jsonify({
            'success': True,
            'transcriptions': user_transcriptions
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@asr_bp.route('/api/audio_transcription/audio/<transcription_id>/<filename>')
def serve_transcription_audio(transcription_id, filename):
    """提供转录音频文件"""
    try:
        # 验证用户权限
        token = request.headers.get('Authorization') or request.args.get('token')
        if token and token.startswith('Bearer '):
            token = token[7:]

        if not token or not is_token_valid(token):
            return jsonify({'error': '未授权'}), 401

        # 查找转录记录
        transcriptions = load_transcription_data()
        transcription = None
        for trans in transcriptions:
            if trans['id'] == transcription_id:
                transcription = trans
                break

        if not transcription:
            return jsonify({'error': '转录记录不存在'}), 404

        # 构建文件路径
        folder_path = os.path.join(AUDIO_TRANSCRIPTION_DIR, transcription['folder_path'])
        file_path = os.path.join(folder_path, filename)

        if not os.path.exists(file_path):
            return jsonify({'error': '文件不存在'}), 404

        return send_file(file_path, as_attachment=True, download_name=filename)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@asr_bp.route('/api/audio_transcription/retranscribe/<transcription_id>', methods=['POST'])
def retranscribe_audio(transcription_id):
    """重新转录音频"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401

        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401

        # 获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username', 'unknown')

        # 查找转录记录
        transcriptions = load_transcription_data()
        transcription_index = -1
        transcription = None

        for i, trans in enumerate(transcriptions):
            if trans['id'] == transcription_id and trans.get('username') == username:
                transcription_index = i
                transcription = trans
                break

        if not transcription:
            return jsonify({'error': '转录记录不存在或无权限'}), 404

        # 更新状态为处理中
        transcriptions[transcription_index]['status'] = 'processing'
        transcriptions[transcription_index]['updated_at'] = datetime.now().isoformat()
        transcriptions[transcription_index]['text'] = None
        if 'error' in transcriptions[transcription_index]:
            del transcriptions[transcription_index]['error']

        save_transcription_data(transcriptions)

        # 获取音频文件路径
        folder_path = os.path.join(AUDIO_TRANSCRIPTION_DIR, transcription['folder_path'])
        audio_path = os.path.join(folder_path, transcription['audio_filename'])

        if not os.path.exists(audio_path):
            return jsonify({'error': '原始音频文件不存在'}), 404

        # 异步重新转录
        def retranscribe_async():
            try:
                # 调用转录API
                text, error = call_transcription_api(audio_path, transcription.get('language'))

                # 更新记录
                transcriptions = load_transcription_data()
                for i, trans in enumerate(transcriptions):
                    if trans['id'] == transcription_id:
                        if text:
                            transcriptions[i]['status'] = 'completed'
                            transcriptions[i]['text'] = text
                            transcriptions[i]['updated_at'] = datetime.now().isoformat()

                            # 更新文本文件
                            text_path = os.path.join(folder_path, 'transcription.txt')
                            with open(text_path, 'w', encoding='utf-8') as f:
                                f.write(text)
                        else:
                            transcriptions[i]['status'] = 'error'
                            transcriptions[i]['error'] = error
                            transcriptions[i]['updated_at'] = datetime.now().isoformat()
                        break

                save_transcription_data(transcriptions)
                print(f"重新转录完成: {transcription_id}")

            except Exception as e:
                print(f"重新转录失败: {e}")
                transcriptions = load_transcription_data()
                for i, trans in enumerate(transcriptions):
                    if trans['id'] == transcription_id:
                        transcriptions[i]['status'] = 'error'
                        transcriptions[i]['error'] = str(e)
                        transcriptions[i]['updated_at'] = datetime.now().isoformat()
                        break
                save_transcription_data(transcriptions)

        # 启动异步重新转录
        thread = threading.Thread(target=retranscribe_async, daemon=True)
        thread.start()

        return jsonify({
            'success': True,
            'message': '重新转录已开始'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@asr_bp.route('/api/audio_transcription/delete/<transcription_id>', methods=['DELETE'])
def delete_audio_transcription(transcription_id):
    """删除转录记录"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401

        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401

        # 获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username', 'unknown')

        # 查找转录记录
        transcriptions = load_transcription_data()
        transcription_index = -1
        transcription = None

        for i, trans in enumerate(transcriptions):
            if trans['id'] == transcription_id and trans.get('username') == username:
                transcription_index = i
                transcription = trans
                break

        if not transcription:
            return jsonify({'error': '转录记录不存在或无权限'}), 404

        # 删除文件夹及其内容
        folder_path = os.path.join(AUDIO_TRANSCRIPTION_DIR, transcription['folder_path'])
        if os.path.exists(folder_path):
            shutil.rmtree(folder_path)

        # 从数据库中删除记录
        transcriptions.pop(transcription_index)
        save_transcription_data(transcriptions)

        return jsonify({
            'success': True,
            'message': '转录记录已删除'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

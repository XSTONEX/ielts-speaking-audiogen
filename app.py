from flask import Flask, request, jsonify, send_from_directory, send_file
import os
import requests
import json
from datetime import datetime, timedelta
import shutil
from dotenv import load_dotenv
from pydub import AudioSegment
import secrets
from werkzeug.wrappers import Response
from werkzeug.utils import secure_filename
import uuid
import threading
import time
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')

MOTHER_DIR = 'audio_files'
COMBINED_DIR = 'combined_audio'
TOKEN_FILE = 'tokens.json'
USERS_FILE = 'users.json'
READING_DIR = 'reading_exam'
INTENSIVE_DIR = 'intensive_articles'
INTENSIVE_IMAGES_DIR = 'intensive_articles/images'  # 精读文章图片存储目录
VOCAB_AUDIO_DIR = 'vocab_audio'  # 词汇音频存储目录
VOCABULARY_BOOK_DIR = 'vocabulary_book'  # 单词本存储目录
VOCABULARY_CATEGORIES_DIR = 'vocabulary_book/categories'  # 分类数据存储目录
VOCABULARY_AUDIO_DIR = 'vocabulary_book/audio'  # 单词本音频存储目录
VOCABULARY_TASKS_DIR = 'vocabulary_book/tasks'  # 音频生成任务队列目录
VOCABULARY_CHALLENGE_DIR = 'vocabulary_book/challenges'  # 挑战数据存储目录
MESSAGE_BOARD_DIR = 'message_board'
MESSAGE_IMAGES_DIR = 'message_board/images'
CHALLENGES_DIR = 'challenges'
STUDY_TECHNIQUES_DIR = 'study_techniques'
STUDY_TECHNIQUES_DATA_DIR = 'study_techniques/data'
STUDY_TECHNIQUES_AUDIO_DIR = 'study_techniques/audio'
AUDIO_TRANSCRIPTION_DIR = 'audio_transcriptions'
os.makedirs(MOTHER_DIR, exist_ok=True)
os.makedirs(COMBINED_DIR, exist_ok=True)
os.makedirs(INTENSIVE_DIR, exist_ok=True)
os.makedirs(INTENSIVE_IMAGES_DIR, exist_ok=True)
os.makedirs(VOCAB_AUDIO_DIR, exist_ok=True)
os.makedirs(VOCABULARY_BOOK_DIR, exist_ok=True)
os.makedirs(VOCABULARY_CATEGORIES_DIR, exist_ok=True)
os.makedirs(VOCABULARY_TASKS_DIR, exist_ok=True)
os.makedirs(VOCABULARY_CHALLENGE_DIR, exist_ok=True)
# 创建分类音频目录
for category in ['listening', 'speaking', 'reading', 'writing']:
    os.makedirs(os.path.join(VOCABULARY_AUDIO_DIR, category), exist_ok=True)
os.makedirs(MESSAGE_BOARD_DIR, exist_ok=True)
os.makedirs(MESSAGE_IMAGES_DIR, exist_ok=True)
os.makedirs(CHALLENGES_DIR, exist_ok=True)
os.makedirs(STUDY_TECHNIQUES_DIR, exist_ok=True)
os.makedirs(STUDY_TECHNIQUES_DATA_DIR, exist_ok=True)
os.makedirs(STUDY_TECHNIQUES_AUDIO_DIR, exist_ok=True)
os.makedirs(AUDIO_TRANSCRIPTION_DIR, exist_ok=True)

# Token管理
def load_tokens():
    """加载token数据"""
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_tokens(tokens):
    """保存token数据"""
    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)

def generate_token():
    """生成新的token"""
    return secrets.token_urlsafe(32)

def is_token_valid(token):
    """检查token是否有效"""
    tokens = load_tokens()
    if token in tokens:
        expire_time = datetime.fromisoformat(tokens[token]['expire_time'])
        if datetime.now() < expire_time:
            return True
        else:
            # token过期，删除
            del tokens[token]
            save_tokens(tokens)
    return False

def create_token(username=None):
    """创建新token"""
    token = generate_token()
    expire_time = datetime.now() + timedelta(days=7)
    tokens = load_tokens()
    tokens[token] = {
        'expire_time': expire_time.isoformat(),
        'created_time': datetime.now().isoformat(),
        'username': username
    }
    save_tokens(tokens)
    return token

# 用户管理
def load_users():
    """加载用户数据"""
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    """保存用户数据"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

def authenticate_user(username, password):
    """验证用户凭据"""
    users = load_users()
    if username in users:
        user_data = users[username]
        if user_data.get('password') == password:
            return user_data
    return None


# 你的 TTS 生成函数
def generate_tts(text, folder):
    url = "https://api.deerapi.com/v1/audio/speech"
    payload = json.dumps({
        "model": "tts-1",
        "input": text,
        "voice": "nova"
    })
    headers = {
        # 'Authorization': 'Bearer ',
        'Authorization': f"Bearer {os.getenv('DEER_API_KEY')}",
        'Content-Type': 'application/json'
    }
    response = requests.request("POST", url, headers=headers, data=payload)
    audio_data = response.content
    folder_path = os.path.join(MOTHER_DIR, folder)
    os.makedirs(folder_path, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{folder}_{timestamp}.mp3"
    filepath = os.path.join(folder_path, filename)
    with open(filepath, 'wb') as f:
        f.write(audio_data)
    # 保存同名文本文件
    txt_filename = filename.replace('.mp3', '.txt')
    txt_filepath = os.path.join(folder_path, txt_filename)
    with open(txt_filepath, 'w', encoding='utf-8') as f:
        f.write(text)
    return folder, filename

# 词汇音频管理函数
def get_vocab_audio_path(article_id, word):
    """获取词汇音频文件路径"""
    # 创建文章专用目录
    article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, article_id)
    os.makedirs(article_audio_dir, exist_ok=True)
    
    # 使用单词的哈希值作为文件名，避免特殊字符问题
    import hashlib
    word_hash = hashlib.md5(word.lower().encode('utf-8')).hexdigest()
    filename = f"{word_hash}.mp3"
    return os.path.join(article_audio_dir, filename)

def generate_and_save_vocab_audio(article_id, word):
    """生成并保存词汇音频文件"""
    audio_path = get_vocab_audio_path(article_id, word)
    
    # 如果文件已存在，直接返回
    if os.path.exists(audio_path):
        return audio_path
    
    # 生成音频数据
    url = "https://api.deerapi.com/v1/audio/speech"
    payload = json.dumps({
        "model": "tts-1",
        "input": word,
        "voice": "nova"
    })
    headers = {
        'Authorization': f"Bearer {os.getenv('DEER_API_KEY')}",
        'Content-Type': 'application/json'
    }
    
    try:
        response = requests.post(url, headers=headers, data=payload, timeout=10)
        if response.status_code == 200:
            # 保存音频文件
            with open(audio_path, 'wb') as f:
                f.write(response.content)
            print(f"Generated audio for word '{word}' in article '{article_id}'")
            return audio_path
        else:
            print(f"TTS API error for word '{word}': {response.status_code}")
            return None
    except Exception as e:
        print(f"Error generating pronunciation for '{word}': {e}")
        return None

def delete_vocab_audio(article_id, word):
    """删除特定词汇的音频文件"""
    audio_path = get_vocab_audio_path(article_id, word)
    if os.path.exists(audio_path):
        try:
            os.remove(audio_path)
            print(f"Deleted audio for word '{word}' in article '{article_id}'")
        except Exception as e:
            print(f"Error deleting audio for word '{word}': {e}")

def delete_article_vocab_audio(article_id):
    """删除整篇文章的所有词汇音频"""
    article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, article_id)
    if os.path.exists(article_audio_dir):
        try:
            shutil.rmtree(article_audio_dir)
            print(f"Deleted all vocab audio for article '{article_id}'")
        except Exception as e:
            print(f"Error deleting vocab audio for article '{article_id}': {e}")

def delete_article_audio_files(article_id):
    """删除文章的整体音频文件（包括完整音频和临时文件）"""
    article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
    
    if os.path.exists(article_audio_dir):
        try:
            deleted_files = []
            deleted_dirs = []
            
            # 遍历并删除所有文件和目录
            for item in os.listdir(article_audio_dir):
                item_path = os.path.join(article_audio_dir, item)
                
                if os.path.isfile(item_path):
                    # 删除音频文件和文本文件
                    if item.endswith(('.mp3', '.txt')):
                        os.remove(item_path)
                        deleted_files.append(item)
                elif os.path.isdir(item_path):
                    # 删除临时目录（任务目录）
                    if item.startswith('audio_') or item.startswith('temp_'):
                        shutil.rmtree(item_path)
                        deleted_dirs.append(item)
            
            # 如果目录为空，删除整个目录
            if not os.listdir(article_audio_dir):
                os.rmdir(article_audio_dir)
                deleted_dirs.append(os.path.basename(article_audio_dir))
            
            print(f"Deleted article audio for '{article_id}': {len(deleted_files)} files, {len(deleted_dirs)} directories")
            
        except Exception as e:
            print(f"Error deleting article audio for '{article_id}': {e}")

def generate_vocab_audio_async(article_id, word):
    """异步生成词汇音频"""
    def _generate():
        try:
            generate_and_save_vocab_audio(article_id, word)
            print(f"异步生成音频成功: {word} (文章: {article_id})")
        except Exception as e:
            print(f"异步生成音频失败: {word} (文章: {article_id}), 错误: {e}")
    
    # 在后台线程中生成音频
    thread = threading.Thread(target=_generate, daemon=True)
    thread.start()

def generate_challenge_vocab_audio(challenge_id, word):
    """为挑战生成词汇音频（使用challenge_id作为文章ID）"""
    return generate_and_save_vocab_audio(f"challenge_{challenge_id}", word)

@app.route('/vocab_audio/<article_id>/<word>')
def get_vocab_audio(article_id, word):
    """获取词汇音频文件"""
    # URL解码单词
    from urllib.parse import unquote
    word = unquote(word)
    
    # 获取音频文件路径
    audio_path = get_vocab_audio_path(article_id, word)
    
    if os.path.exists(audio_path):
        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name=f"{word}.mp3"
        )
    else:
        return jsonify({'error': '音频文件不存在'}), 404

@app.route('/vocab_audio/articles/<article_id>/<filename>')
def get_article_audio(article_id, filename):
    """获取文章音频文件"""
    # 构建音频文件路径
    audio_path = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id, filename)
    
    if os.path.exists(audio_path):
        return send_file(
            audio_path,
            mimetype='audio/mpeg',
            as_attachment=False,
            download_name=filename
        )
    else:
        return jsonify({'error': '音频文件不存在'}), 404

@app.route('/')
def index():
    return send_file('templates/modules.html')

@app.route('/login')
def login_page():
    """登录页面"""
    return send_file('templates/login.html')

@app.route('/generate_audio', methods=['POST'])
def generate_audio():
    data = request.json
    text = data.get('text')
    folder = data.get('folder')
    question = data.get('question')
    if not text or not folder:
        return jsonify({'error': 'Missing text or folder'}), 400
    # PART2 生成时写入 question.txt
    if folder.startswith('P2') and question:
        folder_path = os.path.join(MOTHER_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)
        question_file = os.path.join(folder_path, 'question.txt')
        with open(question_file, 'w', encoding='utf-8') as f:
            f.write(question.strip())
    folder, filename = generate_tts(text, folder)
    return jsonify({'folder': folder, 'filename': filename})

@app.route('/list_audio', methods=['GET'])
def list_audio():
    # 分类分组
    categories = {
        'Part1': [],
        'Part2': [],
        'Part3': [],
        '其他': []
    }
    for folder in os.listdir(MOTHER_DIR):
        folder_path = os.path.join(MOTHER_DIR, folder)
        if os.path.isdir(folder_path) and not folder.startswith('.'):
            files = [f for f in os.listdir(folder_path) if f.endswith('.mp3')]
            if files:
                files_info = []
                for f in files:
                    path = os.path.join(folder_path, f)
                    ctime = os.path.getctime(path)
                    # 读取 question（第一行）
                    txt_path = os.path.join(folder_path, f.replace('.mp3', '.txt'))
                    question = None
                    if os.path.exists(txt_path):
                        try:
                            with open(txt_path, 'r', encoding='utf-8') as tf:
                                question = tf.readline().strip()
                        except Exception:
                            question = None
                    files_info.append({'name': f, 'ctime': ctime, 'question': question})
                files_info.sort(key=lambda x: x['ctime'])
                folder_time = files_info[0]['ctime']
                folder_obj = {
                    'folder': folder,
                    'ctime': folder_time,
                    'files': files_info
                }
                # 分类
                if folder.startswith('P1'):
                    categories['Part1'].append(folder_obj)
                elif folder.startswith('P2'):
                    # PART2 读取 question.txt
                    question_file = os.path.join(folder_path, 'question.txt')
                    question = None
                    if os.path.exists(question_file):
                        try:
                            with open(question_file, 'r', encoding='utf-8') as qf:
                                question = qf.read().strip()
                        except Exception:
                            question = None
                    folder_obj['question'] = question
                    categories['Part2'].append(folder_obj)
                elif folder.startswith('P3'):
                    categories['Part3'].append(folder_obj)
                else:
                    categories['其他'].append(folder_obj)
    # 各分类内按时间排序（最新在前）
    for cat in categories:
        categories[cat].sort(key=lambda x: x['ctime'], reverse=True)
    return jsonify(categories)

@app.route('/list_folders', methods=['GET'])
def list_folders():
    folders = []
    for folder in os.listdir(MOTHER_DIR):
        folder_path = os.path.join(MOTHER_DIR, folder)
        if os.path.isdir(folder_path) and not folder.startswith('.'):
            ctime = os.path.getctime(folder_path)
            folders.append({'name': folder, 'ctime': ctime})
    # 按创建时间升序排列
    folders.sort(key=lambda x: x['ctime'], reverse=True)
    folder_names = [f['name'] for f in folders]
    return jsonify({'folders': folder_names})

@app.route('/audio/<folder>/<filename>')
def serve_audio(folder, filename):
    return send_from_directory(os.path.join(MOTHER_DIR, folder), filename)

@app.route('/text/<folder>/<filename>')
def get_text(folder, filename):
    txt_filename = filename.replace('.mp3', '.txt')
    txt_path = os.path.join(MOTHER_DIR, folder, txt_filename)
    if not os.path.exists(txt_path):
        return jsonify({'error': 'Text file not found'}), 404
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({'text': content})

@app.route('/delete_folder', methods=['POST'])
def delete_folder():
    data = request.json
    folder = data.get('folder')
    if not folder:
        return jsonify({'error': 'Missing folder'}), 400
    folder_path = os.path.join(MOTHER_DIR, folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
    try:
        shutil.rmtree(folder_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/delete_audio', methods=['POST'])
def delete_audio():
    data = request.json
    folder = data.get('folder')
    filename = data.get('filename')
    if not folder or not filename:
        return jsonify({'error': 'Missing folder or filename'}), 400
    folder_path = os.path.join(MOTHER_DIR, folder)
    audio_path = os.path.join(folder_path, filename)
    txt_path = audio_path.replace('.mp3', '.txt')
    if not os.path.exists(audio_path):
        return jsonify({'error': 'Audio file not found'}), 404
    try:
        os.remove(audio_path)
        if os.path.exists(txt_path):
            os.remove(txt_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/set_part2_question', methods=['POST'])
def set_part2_question():
    data = request.json
    folder = data.get('folder')
    question = data.get('question')
    if not folder or not question:
        return jsonify({'error': 'Missing folder or question'}), 400
    folder_path = os.path.join(MOTHER_DIR, folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
    question_file = os.path.join(folder_path, 'question.txt')
    try:
        with open(question_file, 'w', encoding='utf-8') as f:
            f.write(question.strip())
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/has_part2_question')
def has_part2_question():
    folder = request.args.get('folder')
    if not folder or not folder.startswith('P2'):
        return jsonify({'exists': False})
    folder_path = os.path.join(MOTHER_DIR, folder)
    question_file = os.path.join(folder_path, 'question.txt')
    exists = os.path.exists(question_file)
    return jsonify({'exists': exists})

@app.route('/get_password')
def get_password():
    password = os.getenv('PASSWORD')
    return jsonify({'password': password})

@app.route('/verify_password', methods=['POST'])
def verify_password():
    """验证密码并返回token（向后兼容旧系统）"""
    data = request.json
    password = data.get('password')
    server_password = os.getenv('PASSWORD')

    if password == server_password:
        # 尝试根据密码找到对应的用户
        username = None
        users = load_users()
        for user_key, user_data in users.items():
            if user_data.get('password') == password:
                username = user_key
                break

        # 如果没找到用户，使用默认的guest用户
        if not username:
            username = 'guest'

        token = create_token(username=username)
        return jsonify({'success': True, 'token': token})
    else:
        return jsonify({'success': False, 'error': 'Invalid password'})

@app.route('/verify_token', methods=['POST'])
def verify_token():
    """验证token是否有效"""
    data = request.json
    token = data.get('token')
    
    if token and is_token_valid(token):
        # 尝试获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username')
        
        if username:
            users = load_users()
            if username in users:
                user_data = users[username]
                user_info = {
                    'username': user_data['username'],
                    'display_name': user_data['display_name'],
                    'role': user_data['role'],
                    'avatar': user_data['avatar']
                }
                return jsonify({'valid': True, 'user': user_info})
        
        return jsonify({'valid': True})
    else:
        return jsonify({'valid': False})

@app.route('/user_login', methods=['POST'])
def user_login():
    """用户登录"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({'success': False, 'error': '用户名和密码不能为空'})
    
    user_data = authenticate_user(username, password)
    if user_data:
        token = create_token(username)
        # 返回用户信息（不包含密码）
        user_info = {
            'username': user_data['username'],
            'display_name': user_data['display_name'],
            'role': user_data['role'],
            'avatar': user_data['avatar']
        }
        return jsonify({
            'success': True, 
            'token': token,
            'user': user_info
        })
    else:
        return jsonify({'success': False, 'error': '用户名或密码错误'})

@app.route('/get_current_user', methods=['GET'])
def get_current_user():
    """获取当前登录用户信息"""
    token = request.headers.get('Authorization')
    if token and token.startswith('Bearer '):
        token = token[7:]
    
    if not token or not is_token_valid(token):
        return jsonify({'error': '未登录或token无效'}), 401
    
    # 从token获取用户名
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username')
    
    if not username:
        return jsonify({'error': '无法获取用户信息'}), 401
    
    users = load_users()
    if username in users:
        user_data = users[username]
        user_info = {
            'username': user_data['username'],
            'display_name': user_data['display_name'],
            'role': user_data['role'],
            'avatar': user_data['avatar']
        }
        return jsonify({'success': True, 'user': user_info})
    
    return jsonify({'error': '用户不存在'}), 404

@app.route('/combined')
def combined_page():
    return send_file('templates/combined.html')
 
@app.route('/speaking')
def speaking_page():
    return send_file('templates/speaking.html')

@app.route('/check_combined_audio')
def check_combined_audio():
    """检查哪些文件夹已经有合集音频"""
    existing_folders = []
    if os.path.exists(COMBINED_DIR):
        for file in os.listdir(COMBINED_DIR):
            if file.endswith('.mp3'):
                folder_name = file.replace('.mp3', '')
                existing_folders.append(folder_name)
    return jsonify({'folders': existing_folders})

@app.route('/generate_combined_audio', methods=['POST'])
def generate_combined_audio():
    """生成文件夹的合集音频"""
    data = request.json
    folder = data.get('folder')
    if not folder:
        return jsonify({'error': 'Missing folder'}), 400
    
    folder_path = os.path.join(MOTHER_DIR, folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
    
    # 获取文件夹中的所有mp3文件，按创建时间排序
    mp3_files = [f for f in os.listdir(folder_path) if f.endswith('.mp3')]
    if not mp3_files:
        return jsonify({'error': 'No audio files found'}), 404
    
    # 按创建时间排序
    mp3_files.sort(key=lambda x: os.path.getctime(os.path.join(folder_path, x)))
    
    try:
        # 合并音频文件
        combined_audio = None
        silence = AudioSegment.silent(duration=1000)  # 1秒静音间隔
        
        for mp3_file in mp3_files:
            file_path = os.path.join(folder_path, mp3_file)
            audio = AudioSegment.from_mp3(file_path)
            
            if combined_audio is None:
                combined_audio = audio
            else:
                combined_audio = combined_audio + silence + audio
        
        # 保存合集音频
        output_path = os.path.join(COMBINED_DIR, f"{folder}.mp3")
        combined_audio.export(output_path, format="mp3")
        
        # 生成字幕数据文件
        generate_subtitles_data(folder, mp3_files, combined_audio)
        
        return jsonify({'success': True})
    
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def generate_subtitles_data(folder, mp3_files, combined_audio):
    """生成字幕数据"""
    folder_path = os.path.join(MOTHER_DIR, folder)
    subtitles = []
    current_time = 0
    
    # 判断文件夹类型
    folder_type = 'other'
    if folder.startswith('P1'):
        folder_type = 'part1'
    elif folder.startswith('P2'):
        folder_type = 'part2'
    elif folder.startswith('P3'):
        folder_type = 'part3'
    
    silence_duration = 1  # 1秒静音间隔
    
    for i, mp3_file in enumerate(mp3_files):
        # 获取音频时长
        audio_path = os.path.join(folder_path, mp3_file)
        audio = AudioSegment.from_mp3(audio_path)
        duration = len(audio) / 1000.0  # 转换为秒
        
        # 获取对应的文本内容
        txt_file = mp3_file.replace('.mp3', '.txt')
        txt_path = os.path.join(folder_path, txt_file)
        text_content = ''
        question_content = ''
        
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if folder_type in ['part1', 'part3']:
                    # Part1和Part3，第一行是问题，剩余是答案
                    lines = content.split('\n', 1)
                    if len(lines) >= 2:
                        question_content = lines[0].strip()
                        text_content = lines[1].strip()
                    else:
                        text_content = content
                else:
                    # Part2，整个内容都是答案
                    text_content = content
        
        subtitle_item = {
            'startTime': current_time,
            'endTime': current_time + duration,
            'duration': duration,
            'text': text_content,
            'filename': mp3_file
        }
        
        if folder_type in ['part1', 'part3'] and question_content:
            subtitle_item['question'] = question_content
        
        # Part2需要添加问题
        if folder_type == 'part2' and i == 0:
            # 读取question.txt
            question_file = os.path.join(folder_path, 'question.txt')
            if os.path.exists(question_file):
                with open(question_file, 'r', encoding='utf-8') as f:
                    subtitle_item['question'] = f.read().strip()
        
        subtitles.append(subtitle_item)
        current_time += duration + silence_duration
    
    # 保存字幕数据
    subtitles_data = {
        'type': folder_type,
        'folder': folder,
        'subtitles': subtitles
    }
    
    subtitles_path = os.path.join(COMBINED_DIR, f"{folder}_subtitles.json")
    with open(subtitles_path, 'w', encoding='utf-8') as f:
        json.dump(subtitles_data, f, ensure_ascii=False, indent=2)

@app.route('/combined_audio/<folder>')
def serve_combined_audio(folder):
    """提供合集音频文件"""
    return send_from_directory(COMBINED_DIR, f"{folder}.mp3")

@app.route('/get_subtitles/<folder>')
def get_subtitles(folder):
    """获取文件夹的字幕数据"""
    subtitles_path = os.path.join(COMBINED_DIR, f"{folder}_subtitles.json")
    if not os.path.exists(subtitles_path):
        return jsonify({'error': 'Subtitles not found'}), 404
    
    try:
        with open(subtitles_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, **data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ------------------------
# Reading (阅读真题) 支持
# ------------------------

def build_reading_index():
    """扫描 READING_DIR 目录，返回 P1/P2/P3 分类下的层级与文件信息。"""
    result = {'P1': [], 'P2': [], 'P3': []}
    if not os.path.exists(READING_DIR):
        return result

    for part in ['P1', 'P2', 'P3']:
        part_dir = os.path.join(READING_DIR, part)
        if not os.path.isdir(part_dir):
            continue
        try:
            categories = [d for d in os.listdir(part_dir) if os.path.isdir(os.path.join(part_dir, d)) and not d.startswith('.')]
        except Exception:
            categories = []
        # 排序规则：1.名称前数字；2.高频优先；3.次高频；4.其余
        import re
        def parse_leading_number(s):
            m = re.match(r"\s*(\d+)", s)
            return int(m.group(1)) if m else 999999
        def category_sort_key(name):
            n = name
            # 高频分组优先
            priority = 2
            if '高频' in n and '次高频' not in n:
                priority = 0
            elif '次高频' in n:
                priority = 1
            return (priority, parse_leading_number(n), n)
        categories.sort(key=category_sort_key)
        for category in categories:
            cat_dir = os.path.join(part_dir, category)
            try:
                items = [d for d in os.listdir(cat_dir) if os.path.isdir(os.path.join(cat_dir, d)) and not d.startswith('.')]
            except Exception:
                items = []
            # 题目排序：按名称前导数字升序，其次按名称
            try:
                items.sort(key=lambda nm: (parse_leading_number(nm), nm))
            except Exception:
                pass
            item_objs = []
            for item in items:
                item_dir = os.path.join(cat_dir, item)
                try:
                    files = [f for f in os.listdir(item_dir) if os.path.isfile(os.path.join(item_dir, f))]
                except Exception:
                    files = []
                html_files = [f for f in files if f.lower().endswith('.html')]
                pdf_files = [f for f in files if f.lower().endswith('.pdf')]
                item_objs.append({
                    'name': item,
                    'path': f"{part}/{category}/{item}",
                    'html': html_files,
                    'pdf': pdf_files
                })
            result[part].append({'category': category, 'items': item_objs})
    return result

@app.route('/list_reading', methods=['GET'])
def list_reading():
    """返回阅读真题目录结构与可用文件（HTML/PDF）。"""
    data = build_reading_index()
    return jsonify(data)

@app.route('/reading_exam/<path:subpath>')
def serve_reading_file(subpath):
    """提供阅读真题静态文件（HTML/PDF）。"""
    return send_from_directory(READING_DIR, subpath)

@app.route('/reading')
def reading_page():
    return send_file('templates/reading.html')

@app.route('/reading_view/<path:subpath>')
def reading_view(subpath):
    """提供带有本地暂存功能的HTML预览，非侵入式注入脚本。"""
    # 仅允许 HTML 文件通过此视图
    file_path = os.path.join(READING_DIR, subpath)
    if not os.path.exists(file_path) or not file_path.lower().endswith('.html'):
        # 对于非 html，回退到静态提供
        return send_from_directory(READING_DIR, subpath)
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception:
        # 尝试以不同编码读取，失败则作为附件下载
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                content = f.read()
        except Exception:
            return send_from_directory(READING_DIR, subpath)

    inject_script = r"""
<script>(function(){
  const STORAGE_KEY = 'readingAnswers:' + decodeURIComponent(location.pathname.replace(/^.*\/reading_view\//,''));
  function $(sel){ return document.querySelector(sel); }
  function assignKey(el, idx){ return el.name || el.id || (el.type ? el.type : el.tagName.toLowerCase()) + '#' + idx; }
  function collect(){
    const inputs = document.querySelectorAll('input, textarea, select');
    const radios = {}; const values = {}; const checks = {};
    inputs.forEach((el, idx)=>{
      const type = (el.type||'').toLowerCase(); const key = assignKey(el, idx);
      if(type==='radio'){ if(el.checked){ radios[el.name || key] = el.value; } }
      else if(type==='checkbox'){ checks[key] = !!el.checked; }
      else { values[key] = el.value || ''; }
    });
    // 保存高亮（左右面板的 innerHTML）
    let hlLeftHtml = null, hlRightHtml = null;
    const left = $('#left'); const right = $('#right');
    if(left) hlLeftHtml = left.innerHTML;
    if(right) hlRightHtml = right.innerHTML;
    const state = { t: Date.now(), radios, values, checks, hlLeftHtml, hlRightHtml };
    try{ localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); showSaved('已自动保存'); }catch(e){}
  }
  function restore(){
    try{
      const raw = localStorage.getItem(STORAGE_KEY); if(!raw) return; const state = JSON.parse(raw);
      // 先恢复高亮（重建 DOM），再恢复输入值
      if(state.hlLeftHtml && $('#left')) $('#left').innerHTML = state.hlLeftHtml;
      if(state.hlRightHtml && $('#right')) $('#right').innerHTML = state.hlRightHtml;
      const inputs = document.querySelectorAll('input, textarea, select');
      inputs.forEach((el, idx)=>{
        const type = (el.type||'').toLowerCase(); const key = assignKey(el, idx);
        if(type==='radio'){ const grp = el.name || key; if(state.radios && state.radios[grp]!==undefined){ if(el.value===state.radios[grp]) el.checked = true; } }
        else if(type==='checkbox'){ if(state.checks && key in state.checks) el.checked = !!state.checks[key]; }
        else { if(state.values && key in state.values) el.value = state.values[key]; }
      });
      showSaved('已恢复上次暂存');
    }catch(e){}
  }
  function clearAll(){
    try{ localStorage.removeItem(STORAGE_KEY); }catch(e){}
    // 清除高亮（展开 .hl 包裹）
    document.querySelectorAll('.hl').forEach(function(n){ const p=n.parentNode; if(!p) return; while(n.firstChild) p.insertBefore(n.firstChild, n); p.removeChild(n); p.normalize(); });
    if(typeof window.resetForm==='function'){ try{ window.resetForm(); }catch(e){} }
    const inputs = document.querySelectorAll('input, textarea, select');
    inputs.forEach((el)=>{ const type=(el.type||'').toLowerCase(); if(type==='radio'||type==='checkbox'){ el.checked=false; } else { el.value=''; } });
    showSaved('已清空暂存');
  }
  function debounce(fn, d){ let t; return function(){ clearTimeout(t); t=setTimeout(fn, d); }; }
  const debouncedSave = debounce(collect, 250);
  window.addEventListener('input', debouncedSave, true);
  window.addEventListener('change', debouncedSave, true);
  // 监听高亮 DOM 变化以自动保存
  [$('#left'), $('#right')].filter(Boolean).forEach(function(target){
    try{ new MutationObserver(debouncedSave).observe(target, {subtree:true, childList:true, attributes:true}); }catch(e){}
  });
  if(typeof window.resetForm==='function'){ const _orig = window.resetForm; window.resetForm = function(){ try{ _orig.apply(this, arguments);}finally{ clearAll(); } }; }
  // 浮动控制条（清空暂存 + 返回阅读目录）
  const bar=document.createElement('div'); bar.style.cssText='position:fixed;right:12px;bottom:12px;z-index:3000;background:#111;color:#fff;padding:8px 12px;border-radius:10px;display:flex;gap:8px;align-items:center;opacity:.9;box-shadow:0 6px 20px rgba(0,0,0,.18);font-size:13px;';
  const msg=document.createElement('span'); msg.textContent='自动保存已启用';
  const btnClear=document.createElement('button'); btnClear.textContent='清空暂存'; btnClear.style.cssText='border:1px solid rgba(255,255,255,.25);background:transparent;color:#fff;border-radius:8px;padding:4px 8px;cursor:pointer;'; btnClear.onclick=clearAll;
  const btnBack=document.createElement('button'); btnBack.textContent='返回阅读目录'; btnBack.style.cssText='border:1px solid rgba(255,255,255,.25);background:transparent;color:#fff;border-radius:8px;padding:4px 8px;cursor:pointer;'; btnBack.onclick=function(){ try{ window.top.location.href='/reading'; }catch(e){ location.href='/reading'; } };
  bar.appendChild(msg); bar.appendChild(btnClear); bar.appendChild(btnBack); document.body.appendChild(bar);
  let toastTimer; function showSaved(text){ msg.textContent=text; clearTimeout(toastTimer); toastTimer=setTimeout(()=>{ msg.textContent='自动保存已启用'; }, 1200); }
  restore();
})();</script>
"""

    # 将脚本注入到 </body> 之前（不区分大小写）
    lower = content.lower()
    idx = lower.rfind('</body>')
    if idx != -1:
        injected = content[:idx] + inject_script + content[idx:]
    else:
        injected = content + inject_script
    return Response(injected, mimetype='text/html; charset=utf-8')

# ------------------------
# Intensive Reading (文章精读)
# ------------------------

import re

def _safe_article_id(title: str) -> str:
    base = re.sub(r"[^\w\-]+", "-", title.strip())[:60].strip('-') or 'article'
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{ts}-{base}"

def _article_path(article_id: str) -> str:
    return os.path.join(INTENSIVE_DIR, f"{article_id}.json")

@app.route('/intensive')
def intensive_page():
    return send_file('templates/intensive.html')

@app.route('/vocab_summary')
def vocab_summary():
    return send_file('templates/vocab_summary.html')

@app.route('/test_pronunciation')
def test_pronunciation():
    """单词发音功能测试页面"""
    return send_file('test_pronunciation.html')
 
@app.route('/intensive/new')
def intensive_new_page():
    return send_file('templates/intensive_new.html')

@app.route('/intensive_list', methods=['GET'])
def intensive_list():
    """列出所有文章（按时间倒序）。"""
    items = []
    try:
        for fname in os.listdir(INTENSIVE_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(INTENSIVE_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                items.append({
                    'id': data.get('id'),
                    'title': data.get('title'),
                    'category': data.get('category'),
                    'created_at': data.get('created_at'),
                    'highlight_count': len(data.get('highlights') or [])
                })
            except Exception:
                continue
    except Exception:
        pass
    # 时间倒序
    items.sort(key=lambda x: x.get('created_at') or '', reverse=True)
    return jsonify({'items': items})

@app.route('/intensive_create', methods=['POST'])
def intensive_create():
    """创建新文章（创建后不可修改内容）。"""
    data = request.json or {}
    title = (data.get('title') or '').strip() or '未命名'
    category = (data.get('category') or 'Reading').strip()
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': '内容不能为空'}), 400
    article_id = _safe_article_id(title)
    # 将简单换行转化为段落 HTML，保持只读展示友好
    paragraphs = [f"<p>{re.sub(r'<', '&lt;', p)}</p>" for p in content.split('\n') if p.strip()]
    content_html = '\n'.join(paragraphs) or f"<p>{re.sub(r'<', '&lt;', content)}</p>"
    obj = {
        'id': article_id,
        'title': title,
        'category': category if category in ['Reading','Listening','Writing'] else 'Reading',
        'created_at': datetime.now().isoformat(),
        'content_text': content,  # 原始文本（用于偏移计算）
        'content_html': content_html,  # 展示用
        'highlights': [],  # {id,start,end,meaning,created_at}
        'images': []  # 文章图片列表 {id, filename, original_name, created_at}
    }
    try:
        with open(_article_path(article_id), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True, 'id': article_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_article/<article_id>', methods=['GET'])
def intensive_article(article_id):
    path = _article_path(article_id)
    if not os.path.exists(path):
        return jsonify({'error': '文章不存在'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'success': True, 'article': {
            'id': data.get('id'),
            'title': data.get('title'),
            'category': data.get('category'),
            'created_at': data.get('created_at'),
            'content_html': data.get('content_html'),
            'content_text': data.get('content_text'),
            'highlights': data.get('highlights') or [],
            'images': data.get('images') or []
        }})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_add_highlight', methods=['POST'])
def intensive_add_highlight():
    data = request.json or {}
    article_id = data.get('id')
    start = data.get('start')
    end = data.get('end')
    meaning = (data.get('meaning') or '').strip()
    sel_text = (data.get('text') or '').strip()
    if article_id is None or start is None or end is None or not meaning:
        return jsonify({'error': '参数不完整'}), 400
    path = _article_path(article_id)
    if not os.path.exists(path):
        return jsonify({'error': '文章不存在'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        # 简单校验范围
        text_len = len(obj.get('content_text') or '')
        if not (0 <= int(start) < int(end) <= text_len):
            return jsonify({'error': '选择范围无效'}), 400
        highlights = obj.setdefault('highlights', [])
        # 去重：如果同一范围已存在高亮，则更新释义并返回，不新增
        for existing in highlights:
            same_range = int(existing.get('start', -1)) == int(start) and int(existing.get('end', -1)) == int(end)
            same_text = sel_text and sel_text == (existing.get('text') or '')
            if same_range or same_text:
                existing['meaning'] = meaning
                existing['created_at'] = datetime.now().isoformat()
                if sel_text:
                    existing['text'] = sel_text
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(obj, f, ensure_ascii=False, indent=2)
                
                # 异步生成词汇音频
                if sel_text:
                    generate_vocab_audio_async(article_id, sel_text)
                
                return jsonify({'success': True, 'highlight': existing, 'updated': True})

        hl_id = generate_token()
        hl = {
            'id': hl_id,
            'start': int(start),
            'end': int(end),
            'meaning': meaning,
            'created_at': datetime.now().isoformat(),
            'text': sel_text
        }
        highlights.append(hl)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        
        # 异步生成词汇音频
        if sel_text:
            generate_vocab_audio_async(article_id, sel_text)
        
        return jsonify({'success': True, 'highlight': hl})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_delete_highlight', methods=['POST'])
def intensive_delete_highlight():
    data = request.json or {}
    article_id = data.get('id')
    highlight_id = data.get('highlight_id')
    if not article_id or not highlight_id:
        return jsonify({'error': '参数不完整'}), 400
    path = _article_path(article_id)
    if not os.path.exists(path):
        return jsonify({'error': '文章不存在'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        
        # 找到要删除的高亮，以便删除其音频
        highlight_to_delete = None
        for h in (obj.get('highlights') or []):
            if h.get('id') == highlight_id:
                highlight_to_delete = h
                break
        
        before = len(obj.get('highlights') or [])
        obj['highlights'] = [h for h in (obj.get('highlights') or []) if h.get('id') != highlight_id]
        after = len(obj['highlights'])
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        
        # 删除对应的音频文件
        if highlight_to_delete and highlight_to_delete.get('text'):
            delete_vocab_audio(article_id, highlight_to_delete['text'])
        
        return jsonify({'success': True, 'removed': before - after})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_update_category', methods=['POST'])
def intensive_update_category():
    data = request.json or {}
    article_id = data.get('id')
    category = (data.get('category') or '').strip()
    if not article_id or category not in ['Reading','Listening','Writing']:
        return jsonify({'error': '参数不合法'}), 400
    path = _article_path(article_id)
    if not os.path.exists(path):
        return jsonify({'error': '文章不存在'}), 404
    try:
        with open(path, 'r', encoding='utf-8') as f:
            obj = json.load(f)
        obj['category'] = category
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_delete_article', methods=['POST'])
def intensive_delete_article():
    data = request.json or {}
    article_id = data.get('id')
    if not article_id:
        return jsonify({'error': '缺少文章ID'}), 400
    path = _article_path(article_id)
    if not os.path.exists(path):
        return jsonify({'error': '文章不存在'}), 404
    try:
        # 删除文章相关的图片文件
        article_image_dir = os.path.join(INTENSIVE_IMAGES_DIR, article_id)
        if os.path.exists(article_image_dir):
            shutil.rmtree(article_image_dir)
        
        # 删除文章文件
        os.remove(path)
        
        # 删除文章相关的所有词汇音频
        delete_article_vocab_audio(article_id)
        
        # 删除文章相关的整体音频文件
        delete_article_audio_files(article_id)
        
        return jsonify({'success': True, 'article_id': article_id, 'clear_cache': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_upload_image', methods=['POST'])
def intensive_upload_image():
    """为精读文章上传图片"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '没有找到图片文件'}), 400
            
        file = request.files['image']
        article_id = request.form.get('article_id')
        
        if not article_id:
            return jsonify({'error': '缺少文章ID'}), 400
            
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
            
        if file and _allowed_file(file.filename):
            # 创建文章专属图片目录
            article_image_dir = os.path.join(INTENSIVE_IMAGES_DIR, article_id)
            os.makedirs(article_image_dir, exist_ok=True)
            
            # 生成安全的文件名
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            file_ext = os.path.splitext(secure_filename(file.filename))[1]
            filename = f'{timestamp}_{str(uuid.uuid4())[:8]}{file_ext}'
            
            filepath = os.path.join(article_image_dir, filename)
            file.save(filepath)
            
            # 更新文章数据，添加图片信息
            article_path = _article_path(article_id)
            if not os.path.exists(article_path):
                return jsonify({'error': '文章不存在'}), 404
                
            with open(article_path, 'r', encoding='utf-8') as f:
                article_data = json.load(f)
            
            # 添加图片信息到文章数据
            image_info = {
                'id': str(uuid.uuid4()),
                'filename': filename,
                'original_name': secure_filename(file.filename),
                'created_at': datetime.now().isoformat()
            }
            
            if 'images' not in article_data:
                article_data['images'] = []
            article_data['images'].append(image_info)
            
            # 保存更新后的文章数据
            with open(article_path, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            
            # 返回图片URL供前端使用
            image_url = f'/intensive_image/{article_id}/{filename}'
            return jsonify({
                'success': True, 
                'image': image_info,
                'image_url': image_url
            })
            
        else:
            return jsonify({'error': '不支持的文件类型'}), 400
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_image/<article_id>/<filename>')
def serve_intensive_image(article_id, filename):
    """提供精读文章图片文件"""
    return send_from_directory(os.path.join(INTENSIVE_IMAGES_DIR, article_id), filename)

@app.route('/intensive_delete_image', methods=['POST'])
def intensive_delete_image():
    """删除精读文章图片"""
    try:
        data = request.json or {}
        article_id = data.get('article_id')
        image_id = data.get('image_id')
        
        if not article_id or not image_id:
            return jsonify({'error': '缺少参数'}), 400
            
        article_path = _article_path(article_id)
        if not os.path.exists(article_path):
            return jsonify({'error': '文章不存在'}), 404
            
        # 读取文章数据
        with open(article_path, 'r', encoding='utf-8') as f:
            article_data = json.load(f)
            
        # 查找要删除的图片
        images = article_data.get('images', [])
        image_to_delete = None
        for i, img in enumerate(images):
            if img.get('id') == image_id:
                image_to_delete = img
                images.pop(i)
                break
                
        if not image_to_delete:
            return jsonify({'error': '图片不存在'}), 404
            
        # 删除文件
        image_file_path = os.path.join(INTENSIVE_IMAGES_DIR, article_id, image_to_delete['filename'])
        if os.path.exists(image_file_path):
            os.remove(image_file_path)
            
        # 保存更新后的文章数据
        with open(article_path, 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/intensive_update_title', methods=['POST'])
def intensive_update_title():
    """更新精读文章标题"""
    try:
        data = request.json or {}
        old_article_id = data.get('article_id')
        new_title = (data.get('new_title') or '').strip()
        
        if not old_article_id or not new_title:
            return jsonify({'error': '缺少必要参数'}), 400
            
        old_article_path = _article_path(old_article_id)
        if not os.path.exists(old_article_path):
            return jsonify({'error': '文章不存在'}), 404
            
        # 读取原文章数据
        with open(old_article_path, 'r', encoding='utf-8') as f:
            article_data = json.load(f)
        
        # 生成新的文章ID（基于新标题）
        # 保持原创建时间戳，只更新标题部分
        old_timestamp = old_article_id.split('-')[0]  # 提取时间戳部分
        title_part = re.sub(r"[^\w\-]+", "-", new_title.strip())[:60].strip('-') or 'article'
        new_article_id = f"{old_timestamp}-{title_part}"
        
        # 检查新ID是否已存在
        new_article_path = _article_path(new_article_id)
        if os.path.exists(new_article_path) and new_article_id != old_article_id:
            return jsonify({'error': '标题冲突，请选择其他标题'}), 400
        
        # 如果ID没有变化，只需要更新标题
        if new_article_id == old_article_id:
            article_data['title'] = new_title
            with open(old_article_path, 'w', encoding='utf-8') as f:
                json.dump(article_data, f, ensure_ascii=False, indent=2)
            return jsonify({'success': True, 'new_article_id': old_article_id, 'renamed_files': False})
        
        # 更新文章数据中的标题和ID
        article_data['title'] = new_title
        article_data['id'] = new_article_id
        
        # 创建新的文章文件
        with open(new_article_path, 'w', encoding='utf-8') as f:
            json.dump(article_data, f, ensure_ascii=False, indent=2)
        
        renamed_files = []
        renamed_dirs = []
        
        # 重命名图片目录
        old_image_dir = os.path.join(INTENSIVE_IMAGES_DIR, old_article_id)
        new_image_dir = os.path.join(INTENSIVE_IMAGES_DIR, new_article_id)
        if os.path.exists(old_image_dir):
            os.makedirs(os.path.dirname(new_image_dir), exist_ok=True)
            shutil.move(old_image_dir, new_image_dir)
            renamed_dirs.append(f"图片目录: {old_article_id} -> {new_article_id}")
        
        # 重命名音频目录
        old_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', old_article_id)
        new_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', new_article_id)
        if os.path.exists(old_audio_dir):
            os.makedirs(os.path.dirname(new_audio_dir), exist_ok=True)
            shutil.move(old_audio_dir, new_audio_dir)
            renamed_dirs.append(f"音频目录: {old_article_id} -> {new_article_id}")
        
        # 重命名词汇音频目录
        old_vocab_audio_dir = os.path.join(VOCAB_AUDIO_DIR, old_article_id)
        new_vocab_audio_dir = os.path.join(VOCAB_AUDIO_DIR, new_article_id)
        if os.path.exists(old_vocab_audio_dir):
            os.makedirs(os.path.dirname(new_vocab_audio_dir), exist_ok=True)
            shutil.move(old_vocab_audio_dir, new_vocab_audio_dir)
            renamed_dirs.append(f"词汇音频目录: {old_article_id} -> {new_article_id}")
        
        # 删除旧文章文件
        os.remove(old_article_path)
        renamed_files.append(f"文章文件: {old_article_id}.json -> {new_article_id}.json")
        
        return jsonify({
            'success': True,
            'new_article_id': new_article_id,
            'old_article_id': old_article_id,
            'renamed_files': True,
            'details': {
                'files': renamed_files,
                'directories': renamed_dirs
            }
        })
        
    except Exception as e:
        return jsonify({'error': f'更新标题失败: {str(e)}'}), 500

def split_text_intelligently(text, target_segments=None, max_chars=2200):
    """
    智能分割文本，确保句子完整性和均匀分配
    :param text: 要分割的文本
    :param target_segments: 目标分段数量，如果指定则平均分割
    :param max_chars: 每段最大字符数
    """
    if len(text) <= max_chars:
        return [text]
    
    import re
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # 如果没有指定目标分段数，根据长度自动计算
    if not target_segments:
        target_segments = max(2, min(10, len(text) // 2000))
    
    # 计算理想的每段长度
    ideal_length = len(text) / target_segments
    
    segments = []
    current_segment = ""
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
            
        # 检查添加这句话后的长度
        test_segment = current_segment + (' ' if current_segment else '') + sentence
        
        # 决定是否开始新段落
        should_split = (
            len(test_segment) > ideal_length and  # 超过理想长度
            current_segment and  # 当前段落不为空
            len(segments) < target_segments - 1 and  # 还没到最后一段
            len(test_segment) > max_chars * 0.6  # 避免过小的段落
        )
        
        if should_split:
            segments.append(current_segment.strip())
            current_segment = sentence
        else:
            current_segment = test_segment
    
    # 添加最后一个段落
    if current_segment:
        segments.append(current_segment.strip())
    
    # 如果分段数不够，尝试进一步分割较长的段落
    while len(segments) < target_segments and len(segments) > 0:
        # 找到最长的段落进行分割
        longest_index = max(range(len(segments)), key=lambda i: len(segments[i]))
        longest_segment = segments[longest_index]
        
        if len(longest_segment) > max_chars * 0.8:  # 只分割足够长的段落
            sub_segments = split_long_segment(longest_segment, len(longest_segment) // 2)
            if len(sub_segments) > 1:
                segments[longest_index:longest_index+1] = sub_segments
            else:
                break
        else:
            break
    
    # 最终检查，确保没有段落超过限制
    final_segments = []
    for segment in segments:
        if len(segment) <= max_chars:
            final_segments.append(segment)
        else:
            sub_segments = split_long_segment(segment, max_chars)
            final_segments.extend(sub_segments)
    
    return final_segments

def redistribute_segments(segments, target_count, max_chars):
    """重新分配段落，使其更接近目标数量"""
    if len(segments) < target_count:
        # 分段太少，需要进一步分割
        result = []
        for segment in segments:
            if len(segment) > max_chars * 0.8:
                sub_segments = split_long_segment(segment, len(segment) // 2)
                result.extend(sub_segments)
            else:
                result.append(segment)
        return result
    elif len(segments) > target_count:
        # 分段太多，需要合并一些
        result = []
        current_segment = ""
        for segment in segments:
            test_merge = current_segment + (' ' if current_segment else '') + segment
            if len(test_merge) <= max_chars:
                current_segment = test_merge
            else:
                if current_segment:
                    result.append(current_segment)
                current_segment = segment
        if current_segment:
            result.append(current_segment)
        return result
    
    return segments

def split_long_segment(segment, max_chars):
    """分割过长的段落，保持句子完整"""
    if len(segment) <= max_chars:
        return [segment]
    
    import re
    sentences = re.split(r'(?<=[.!?])\s+', segment)
    
    sub_segments = []
    current_sub = ""
    
    for sentence in sentences:
        test_sub = current_sub + (' ' if current_sub else '') + sentence
        if len(test_sub) > max_chars and current_sub:
            sub_segments.append(current_sub.strip())
            current_sub = sentence
        else:
            current_sub = test_sub
    
    if current_sub:
        sub_segments.append(current_sub.strip())
    
    return sub_segments

def generate_tts_segment(text, temp_dir, segment_index, max_retries=3):
    """生成单个文本段的TTS音频，带重试机制"""
    url = "https://api.deerapi.com/v1/audio/speech"
    payload = json.dumps({
        "model": "tts-1",
        "input": text,
        "voice": "nova"
    })
    headers = {
        'Authorization': f"Bearer {os.getenv('DEER_API_KEY')}",
        'Content-Type': 'application/json'
    }
    
    segment_path = os.path.join(temp_dir, f"segment_{segment_index:03d}.mp3")
    
    # 检查是否已存在该分片文件
    if os.path.exists(segment_path) and os.path.getsize(segment_path) > 0:
        print(f"分片 {segment_index} 已存在，跳过生成")
        return segment_path
    
    last_error = None
    for attempt in range(max_retries):
        try:
            print(f"正在生成分片 {segment_index}，尝试 {attempt + 1}/{max_retries}")
            
            # 使用更长的超时时间，并设置连接和读取超时
            response = requests.post(
                url, 
                headers=headers, 
                data=payload, 
                timeout=(10, 60)  # (连接超时, 读取超时)
            )
            
            if response.status_code == 200:
                # 先写入临时文件，然后重命名，避免写入过程中的问题
                temp_path = segment_path + '.tmp'
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                
                # 验证文件完整性
                if os.path.getsize(temp_path) > 0:
                    os.rename(temp_path, segment_path)
                    print(f"分片 {segment_index} 生成成功")
                    return segment_path
                else:
                    os.remove(temp_path) if os.path.exists(temp_path) else None
                    raise Exception("生成的音频文件为空")
            else:
                raise Exception(f'TTS API错误: {response.status_code}, 响应: {response.text}')
                
        except requests.exceptions.Timeout as e:
            last_error = f"请求超时: {str(e)}"
            print(f"分片 {segment_index} 第 {attempt + 1} 次尝试超时: {last_error}")
            if attempt < max_retries - 1:
                import time
                # 指数退避：等待 2^attempt 秒
                wait_time = 2 ** attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            last_error = f"网络请求错误: {str(e)}"
            print(f"分片 {segment_index} 第 {attempt + 1} 次尝试网络错误: {last_error}")
            if attempt < max_retries - 1:
                import time
                wait_time = 2 ** attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        except Exception as e:
            last_error = str(e)
            print(f"分片 {segment_index} 第 {attempt + 1} 次尝试出错: {last_error}")
            if attempt < max_retries - 1:
                import time
                wait_time = 1 + attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    
    # 所有重试都失败了
    raise Exception(f'分片 {segment_index} 生成失败，已重试 {max_retries} 次。最后错误: {last_error}')

@app.route('/generate_article_audio', methods=['POST'])
def generate_article_audio():
    """为精听文章生成英文音频（支持长文本分段生成和合并）"""
    data = request.json or {}
    article_id = data.get('article_id')
    text = data.get('text', '').strip()
    
    if not article_id or not text:
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 检查文章是否存在
    article_path = _article_path(article_id)
    if not os.path.exists(article_path):
        return jsonify({'error': '文章不存在'}), 404
    
    try:
        # 创建文章音频目录
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        os.makedirs(article_audio_dir, exist_ok=True)
        
        # 生成最终音频文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"article_{timestamp}.mp3"
        final_audio_path = os.path.join(article_audio_dir, filename)
        
        # 检查文本长度，决定是否需要分段处理（增加40%冗余）
        MAX_CHARS = 2200  # 更保守的字符限制
        
        if len(text) <= MAX_CHARS:
            # 文本较短，直接生成
            url = "https://api.deerapi.com/v1/audio/speech"
            payload = json.dumps({
                "model": "tts-1",
                "input": text,
                "voice": "nova"
            })
            headers = {
                'Authorization': f"Bearer {os.getenv('DEER_API_KEY')}",
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, data=payload, timeout=30)
            
            if response.status_code == 200:
                with open(final_audio_path, 'wb') as f:
                    f.write(response.content)
            else:
                return jsonify({'error': f'TTS服务错误: {response.status_code}'}), 500
        else:
            # 文本较长，需要分段处理（增加40%冗余）
            base_segments = max(2, min(8, len(text) // 1800))  # 基础分段数（更小的基础单位）
            target_segments = int(base_segments * 1.4)  # 增加40%冗余
            target_segments = max(3, min(12, target_segments))  # 3-12段之间
            segments = split_text_intelligently(text, target_segments, MAX_CHARS)
            
            # 创建临时目录存储分段音频
            temp_dir = os.path.join(article_audio_dir, f"temp_{timestamp}")
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                # 生成每个分段的音频
                segment_paths = []
                for i, segment in enumerate(segments):
                    segment_path = generate_tts_segment(segment, temp_dir, i)
                    segment_paths.append(segment_path)
                
                # 使用pydub合并音频
                combined_audio = None
                silence = AudioSegment.silent(duration=800)  # 800ms静音间隔
                
                for segment_path in segment_paths:
                    audio_segment = AudioSegment.from_mp3(segment_path)
                    
                    if combined_audio is None:
                        combined_audio = audio_segment
                    else:
                        combined_audio = combined_audio + silence + audio_segment
                
                # 导出合并后的音频
                combined_audio.export(final_audio_path, format="mp3")
                
            finally:
                # 保留临时文件以支持断点续传，只在成功生成最终音频后清理
                # 临时文件会在后续的清理任务中自动删除
                pass
        
        # 保存对应的文本文件
        txt_path = final_audio_path.replace('.mp3', '.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(text)
        
        # 返回音频访问URL
        audio_url = f"/vocab_audio/articles/{article_id}/{filename}"
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': filename,
            'text_length': len(text),
            'segments_count': len(split_text_intelligently(text, MAX_CHARS)) if len(text) > MAX_CHARS else 1
        })
        
    except requests.exceptions.Timeout:
        return jsonify({'error': '音频生成超时，请稍后重试'}), 500
    except Exception as e:
        return jsonify({'error': f'音频生成失败: {str(e)}'}), 500

@app.route('/prepare_article_audio', methods=['POST'])
def prepare_article_audio():
    """准备分批音频生成，返回分段信息"""
    data = request.json or {}
    article_id = data.get('article_id')
    text = data.get('text', '').strip()
    
    if not article_id or not text:
        return jsonify({'error': '缺少必要参数'}), 400
    
    # 检查文章是否存在
    article_path = _article_path(article_id)
    if not os.path.exists(article_path):
        return jsonify({'error': '文章不存在'}), 404
    
    try:
        # 计算最优分段数量（增加40%冗余）
        MAX_CHARS = 2200  # 进一步降低单段字符限制
        if len(text) <= MAX_CHARS:
            segments = [text]
        else:
            # 根据长度计算合适的分段数，增加40%冗余
            base_segments = max(2, min(8, len(text) // 1800))  # 基础分段数（更小的基础单位）
            target_segments = int(base_segments * 1.4)  # 增加40%冗余
            target_segments = max(3, min(12, target_segments))  # 确保在3-12段之间
            segments = split_text_intelligently(text, target_segments, MAX_CHARS)
        
        # 生成任务ID
        task_id = f"audio_{article_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'segments_count': len(segments),
            'segments_info': [
                {
                    'index': i,
                    'length': len(segment),
                    'preview': segment[:100] + '...' if len(segment) > 100 else segment
                }
                for i, segment in enumerate(segments)
            ]
        })
        
    except Exception as e:
        return jsonify({'error': f'准备失败: {str(e)}'}), 500

@app.route('/generate_audio_segment', methods=['POST'])
def generate_audio_segment():
    """生成单个音频分段"""
    data = request.json or {}
    article_id = data.get('article_id')
    text = data.get('text', '').strip()
    segment_index = data.get('segment_index', 0)
    task_id = data.get('task_id')
    
    if not all([article_id, text, task_id is not None]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        # 创建任务目录
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        task_dir = os.path.join(article_audio_dir, task_id)
        os.makedirs(task_dir, exist_ok=True)
        
        # 生成单段音频
        segment_path = generate_tts_segment(text, task_dir, segment_index)
        
        return jsonify({
            'success': True,
            'segment_index': segment_index,
            'segment_path': os.path.basename(segment_path),
            'text_length': len(text)
        })
        
    except Exception as e:
        return jsonify({'error': f'分段生成失败: {str(e)}'}), 500

@app.route('/check_segment_status', methods=['POST'])
def check_segment_status():
    """检查分片音频生成状态，支持断点续传"""
    data = request.json or {}
    article_id = data.get('article_id')
    task_id = data.get('task_id')
    segments_count = data.get('segments_count', 0)
    
    if not all([article_id, task_id, segments_count]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        # 检查任务目录
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        task_dir = os.path.join(article_audio_dir, task_id)
        
        if not os.path.exists(task_dir):
            return jsonify({
                'success': True,
                'completed_segments': [],
                'missing_segments': list(range(segments_count)),
                'total_segments': segments_count,
                'completion_rate': 0.0
            })
        
        # 检查每个分片的状态
        completed_segments = []
        missing_segments = []
        
        for i in range(segments_count):
            segment_path = os.path.join(task_dir, f"segment_{i:03d}.mp3")
            if os.path.exists(segment_path) and os.path.getsize(segment_path) > 0:
                completed_segments.append(i)
            else:
                missing_segments.append(i)
        
        completion_rate = len(completed_segments) / segments_count if segments_count > 0 else 0
        
        return jsonify({
            'success': True,
            'completed_segments': completed_segments,
            'missing_segments': missing_segments,
            'total_segments': segments_count,
            'completion_rate': completion_rate,
            'task_dir_exists': True
        })
        
    except Exception as e:
        return jsonify({'error': f'状态检查失败: {str(e)}'}), 500

@app.route('/combine_audio_segments', methods=['POST'])
def combine_audio_segments():
    """合并音频分段"""
    data = request.json or {}
    article_id = data.get('article_id')
    task_id = data.get('task_id')
    segments_count = data.get('segments_count')
    original_text = data.get('original_text', '')
    
    if not all([article_id, task_id, segments_count]):
        return jsonify({'error': '缺少必要参数'}), 400
    
    try:
        # 找到任务目录
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        task_dir = os.path.join(article_audio_dir, task_id)
        
        if not os.path.exists(task_dir):
            return jsonify({'error': '任务目录不存在'}), 404
        
        # 收集所有分段音频文件
        segment_paths = []
        for i in range(segments_count):
            segment_file = f"segment_{i:03d}.mp3"
            segment_path = os.path.join(task_dir, segment_file)
            if os.path.exists(segment_path):
                segment_paths.append(segment_path)
            else:
                return jsonify({'error': f'分段文件缺失: {segment_file}'}), 404
        
        # 合并音频
        combined_audio = None
        silence = AudioSegment.silent(duration=800)  # 800ms静音间隔
        
        for segment_path in segment_paths:
            audio_segment = AudioSegment.from_mp3(segment_path)
            
            if combined_audio is None:
                combined_audio = audio_segment
            else:
                combined_audio = combined_audio + silence + audio_segment
        
        # 生成最终文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"article_{timestamp}.mp3"
        final_audio_path = os.path.join(article_audio_dir, filename)
        
        # 导出合并后的音频
        combined_audio.export(final_audio_path, format="mp3")
        
        # 保存对应的文本文件
        txt_path = final_audio_path.replace('.mp3', '.txt')
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(original_text)
        
        # 成功合并后清理任务目录
        try:
            if os.path.exists(task_dir):
                shutil.rmtree(task_dir)
                print(f"已清理任务目录: {task_dir}")
        except Exception as cleanup_error:
            print(f"清理任务目录时出错: {cleanup_error}")
            # 不影响主要功能，继续执行
        
        # 返回音频访问URL
        audio_url = f"/vocab_audio/articles/{article_id}/{filename}"
        
        return jsonify({
            'success': True,
            'audio_url': audio_url,
            'filename': filename,
            'text_length': len(original_text),
            'segments_count': segments_count
        })
        
    except Exception as e:
        return jsonify({'error': f'合并失败: {str(e)}'}), 500

@app.route('/find_unfinished_audio_tasks/<article_id>')
def find_unfinished_audio_tasks(article_id):
    """查找指定文章的未完成音频生成任务"""
    try:
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        
        if not os.path.exists(article_audio_dir):
            return jsonify({'success': True, 'unfinished_tasks': []})
        
        unfinished_tasks = []
        
        # 遍历音频目录，查找临时任务目录
        for item in os.listdir(article_audio_dir):
            item_path = os.path.join(article_audio_dir, item)
            
            if os.path.isdir(item_path) and item.startswith('audio_'):
                # 这是一个音频生成任务目录
                task_id = item
                
                # 检查目录中的分片文件
                segment_files = [f for f in os.listdir(item_path) if f.startswith('segment_') and f.endswith('.mp3')]
                
                if segment_files:
                    # 分析分片状态
                    segment_indices = []
                    for segment_file in segment_files:
                        try:
                            # 从文件名提取索引：segment_001.mp3 -> 1
                            index = int(segment_file.split('_')[1].split('.')[0])
                            segment_path = os.path.join(item_path, segment_file)
                            
                            # 检查文件是否完整
                            if os.path.getsize(segment_path) > 0:
                                segment_indices.append(index)
                        except (ValueError, IndexError):
                            continue
                    
                    if segment_indices:
                        # 估算总分片数（基于最大索引 + 一些容错）
                        max_index = max(segment_indices)
                        estimated_total = max_index + 1
                        
                        # 检查是否有缺失的分片
                        all_indices = set(range(estimated_total))
                        completed_indices = set(segment_indices)
                        missing_indices = sorted(list(all_indices - completed_indices))
                        
                        completion_rate = len(completed_indices) / estimated_total if estimated_total > 0 else 0
                        
                        # 获取任务创建时间
                        task_time = os.path.getctime(item_path)
                        
                        unfinished_tasks.append({
                            'task_id': task_id,
                            'segments_count': estimated_total,
                            'completed_segments': sorted(list(completed_indices)),
                            'missing_segments': missing_indices,
                            'completion_rate': completion_rate,
                            'created_time': task_time,
                            'task_dir': item_path
                        })
        
        # 按创建时间排序，最新的在前
        unfinished_tasks.sort(key=lambda x: x['created_time'], reverse=True)
        
        return jsonify({
            'success': True,
            'unfinished_tasks': unfinished_tasks
        })
        
    except Exception as e:
        return jsonify({'error': f'查找未完成任务失败: {str(e)}'}), 500

@app.route('/cleanup_article_audio', methods=['POST'])
def cleanup_article_audio():
    """清理文章的音频文件和临时文件"""
    data = request.json or {}
    article_id = data.get('article_id')
    
    if not article_id:
        return jsonify({'error': '缺少文章ID'}), 400
    
    try:
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        
        if not os.path.exists(article_audio_dir):
            return jsonify({'success': True, 'message': '无需清理，目录不存在'})
        
        cleaned_files = []
        cleaned_dirs = []
        
        # 遍历音频目录
        for item in os.listdir(article_audio_dir):
            item_path = os.path.join(article_audio_dir, item)
            
            if os.path.isfile(item_path):
                # 删除音频文件和文本文件
                if item.endswith(('.mp3', '.txt')):
                    os.remove(item_path)
                    cleaned_files.append(item)
            elif os.path.isdir(item_path):
                # 删除临时目录（任务目录）
                if item.startswith('audio_') or item.startswith('temp_'):
                    shutil.rmtree(item_path)
                    cleaned_dirs.append(item)
        
        # 如果目录为空，删除整个目录
        if not os.listdir(article_audio_dir):
            os.rmdir(article_audio_dir)
            cleaned_dirs.append(os.path.basename(article_audio_dir))
        
        return jsonify({
            'success': True,
            'cleaned_files': cleaned_files,
            'cleaned_dirs': cleaned_dirs,
            'message': f'清理完成：删除了{len(cleaned_files)}个文件和{len(cleaned_dirs)}个目录'
        })
        
    except Exception as e:
        return jsonify({'error': f'清理失败: {str(e)}'}), 500

@app.route('/check_article_audio/<article_id>', methods=['GET'])
def check_article_audio(article_id):
    """检查文章是否已有音频文件"""
    try:
        # 检查文章是否存在
        article_path = _article_path(article_id)
        if not os.path.exists(article_path):
            return jsonify({'error': '文章不存在'}), 404
        
        # 检查音频目录
        article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, 'articles', article_id)
        
        if not os.path.exists(article_audio_dir):
            return jsonify({'exists': False})
        
        # 查找最新的音频文件
        audio_files = [f for f in os.listdir(article_audio_dir) if f.endswith('.mp3')]
        
        if not audio_files:
            return jsonify({'exists': False})
        
        # 按修改时间排序，获取最新的音频文件
        audio_files.sort(key=lambda x: os.path.getmtime(os.path.join(article_audio_dir, x)), reverse=True)
        latest_audio = audio_files[0]
        
        # 获取对应的文本文件
        txt_file = latest_audio.replace('.mp3', '.txt')
        txt_path = os.path.join(article_audio_dir, txt_file)
        
        audio_info = {
            'exists': True,
            'filename': latest_audio,
            'audio_url': f"/vocab_audio/articles/{article_id}/{latest_audio}",
            'created_time': datetime.fromtimestamp(os.path.getmtime(os.path.join(article_audio_dir, latest_audio))).isoformat()
        }
        
        # 如果文本文件存在，读取原始文本
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                audio_info['original_text'] = f.read()
        
        return jsonify(audio_info)
        
    except Exception as e:
        return jsonify({'error': f'检查音频文件失败: {str(e)}'}), 500

# ------------------------
# Message Board (留言板)
# ------------------------

def _message_board_file():
    return os.path.join(MESSAGE_BOARD_DIR, 'messages.json')

def load_messages():
    """加载留言数据"""
    messages_file = _message_board_file()
    if os.path.exists(messages_file):
        try:
            with open(messages_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_messages(messages):
    """保存留言数据"""
    messages_file = _message_board_file()
    with open(messages_file, 'w', encoding='utf-8') as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def generate_message_id():
    """生成消息ID"""
    return f"msg_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

@app.route('/message_board')
def message_board_page():
    return send_file('templates/message_board.html')

@app.route('/api/messages', methods=['GET'])
def get_messages():
    """获取所有留言，按时间倒序"""
    try:
        messages = load_messages()
        # 按时间倒序排列（最新的在前面）
        messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages', methods=['POST'])
def post_message():
    """发送新留言"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            token = request.json.get('token') if request.json else None
            
        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401
            
        # 从token获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username')
        
        if not username:
            return jsonify({'error': '无法获取用户信息'}), 401
            
        users = load_users()
        if username not in users:
            return jsonify({'error': '用户不存在'}), 404
            
        user_data = users[username]
        user_info = {
            'username': user_data['username'],
            'display_name': user_data['display_name'],
            'role': user_data['role'],
            'avatar': user_data['avatar']
        }
        
        data = request.json or {}
        message_type = data.get('type', 'text')
        content = data.get('content', {})
        
        message = {
            'id': generate_message_id(),
            'user': user_info,
            'type': message_type,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        messages = load_messages()
        messages.append(message)
        save_messages(messages)
        
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/messages/<message_id>', methods=['DELETE'])
def delete_message(message_id):
    """删除留言"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401
            
        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401
            
        # 从token获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username')
        
        if not username:
            return jsonify({'error': '无法获取用户信息'}), 401
        
        messages = load_messages()
        
        # 找到要删除的消息
        message_to_delete = None
        message_index = -1
        for i, msg in enumerate(messages):
            if msg.get('id') == message_id:
                message_to_delete = msg
                message_index = i
                break
        
        if not message_to_delete:
            return jsonify({'error': '消息不存在'}), 404
            
        # 检查是否是消息的作者
        if message_to_delete.get('user', {}).get('username') != username:
            return jsonify({'error': '只能删除自己的消息'}), 403
        
        # 检查是否有关联的挑战需要删除
        challenge_id = None
        if (message_to_delete.get('type') == 'mixed_content' and 
            message_to_delete.get('content', {}).get('challenge')):
            challenge_id = message_to_delete['content']['challenge'].get('id')
        
        # 删除消息
        messages.pop(message_index)
        save_messages(messages)
        
        # 删除关联的挑战记录
        if challenge_id:
            try:
                delete_challenge_record(challenge_id)
            except Exception as e:
                # 挑战删除失败不影响消息删除，只记录错误
                print(f"删除挑战记录失败: {e}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/upload_message_image', methods=['POST'])
def upload_message_image():
    """上传留言板图片"""
    try:
        if 'image' not in request.files:
            return jsonify({'error': '没有找到图片文件'}), 400
            
        file = request.files['image']
        username = request.form.get('user_id')  # 前端传的是username
        
        if not username:
            return jsonify({'error': '用户信息无效'}), 400
            
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400
        
        # 检查文件大小（最大10MB）
        if file.content_length and file.content_length > 10 * 1024 * 1024:
            return jsonify({'error': '图片文件大小不能超过10MB'}), 400
        
        # 检查MIME类型
        if not _is_valid_image_file(file):
            return jsonify({'error': '不支持的图片格式。请上传JPG、PNG、GIF、WebP格式的图片'}), 400
        
        # 创建用户专属目录
        user_dir = os.path.join(MESSAGE_IMAGES_DIR, username)
        os.makedirs(user_dir, exist_ok=True)
        
        # 处理图片并保存
        try:
            processed_filename = _process_and_save_image(file, user_dir, username)
            if processed_filename:
                # 返回相对路径供前端使用
                relative_path = f'{username}/{processed_filename}'
                return jsonify({'success': True, 'filename': relative_path})
            else:
                return jsonify({'error': '图片处理失败'}), 500
        except Exception as process_error:
            return jsonify({'error': f'图片处理失败: {str(process_error)}'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _allowed_file(filename):
    """检查文件类型是否允许"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def _is_valid_image_file(file):
    """检查文件是否为有效的图片文件"""
    import imghdr
    
    # 检查文件扩展名
    if file.filename and not _allowed_file(file.filename):
        return False
    
    # 检查MIME类型
    allowed_mimes = {
        'image/jpeg', 'image/jpg', 'image/png', 'image/gif', 
        'image/webp', 'image/heic', 'image/heif'
    }
    
    if hasattr(file, 'mimetype') and file.mimetype:
        if file.mimetype not in allowed_mimes:
            return False
    
    # 通过文件头检查图片格式
    file.seek(0)  # 重置文件指针
    try:
        header = file.read(512)  # 读取文件头
        file.seek(0)  # 重置文件指针
        
        # 检查各种图片格式的文件头
        if header.startswith(b'\xff\xd8\xff'):  # JPEG
            return True
        elif header.startswith(b'\x89PNG\r\n\x1a\n'):  # PNG
            return True
        elif header.startswith(b'GIF87a') or header.startswith(b'GIF89a'):  # GIF
            return True
        elif header.startswith(b'RIFF') and b'WEBP' in header[:20]:  # WebP
            return True
        elif b'ftyp' in header[:20] and (b'heic' in header[:20] or b'heif' in header[:20]):  # HEIC/HEIF
            return True
        
        # 使用imghdr作为后备检查
        file.seek(0)
        image_type = imghdr.what(file)
        return image_type in ['jpeg', 'png', 'gif', 'webp']
        
    except Exception:
        return False

def _process_and_save_image(file, user_dir, username):
    """处理并保存图片，支持格式转换和压缩"""
    try:
        from PIL import Image, ImageOps
        import io
        
        # 生成文件名
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        random_id = str(uuid.uuid4())[:8]
        
        # 读取图片
        file.seek(0)
        image_data = file.read()
        
        # 使用PIL打开图片
        with Image.open(io.BytesIO(image_data)) as img:
            # 自动旋转图片（处理EXIF方向信息）
            img = ImageOps.exif_transpose(img)
            
            # 转换为RGB模式（处理RGBA、P等模式）
            if img.mode in ('RGBA', 'LA', 'P'):
                # 创建白色背景
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 压缩大图片
            max_size = (1920, 1920)  # 最大尺寸
            if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
            
            # 保存为JPEG格式（最佳兼容性）
            filename = f'{timestamp}_{random_id}.jpg'
            filepath = os.path.join(user_dir, filename)
            
            # 保存图片，设置质量
            img.save(filepath, 'JPEG', quality=85, optimize=True)
            
            return filename
            
    except ImportError:
        # 如果没有PIL，使用原始方法保存
        print("警告：PIL未安装，使用原始文件保存方法")
        return _save_original_image(file, user_dir, username)
    except Exception as e:
        print(f"图片处理失败: {e}")
        # 降级到原始方法
        return _save_original_image(file, user_dir, username)

def _save_original_image(file, user_dir, username):
    """原始图片保存方法（降级方案）"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_ext = os.path.splitext(secure_filename(file.filename))[1].lower()
        
        # 对于HEIC文件，改为JPG扩展名
        if file_ext in ['.heic', '.heif']:
            file_ext = '.jpg'
        
        filename = f'{timestamp}_{str(uuid.uuid4())[:8]}{file_ext}'
        filepath = os.path.join(user_dir, filename)
        
        file.seek(0)
        file.save(filepath)
        
        return filename
    except Exception as e:
        print(f"原始图片保存失败: {e}")
        return None

@app.route('/message_images/<path:filename>')
def serve_message_image(filename):
    """提供留言板图片文件"""
    return send_from_directory(MESSAGE_IMAGES_DIR, filename)

# ==================== 评论系统相关API ====================

def _comments_file():
    """获取评论文件路径"""
    return os.path.join(MESSAGE_BOARD_DIR, 'comments.json')

def load_comments():
    """加载评论数据"""
    comments_file = _comments_file()
    if os.path.exists(comments_file):
        try:
            with open(comments_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return []
    return []

def save_comments(comments):
    """保存评论数据"""
    comments_file = _comments_file()
    with open(comments_file, 'w', encoding='utf-8') as f:
        json.dump(comments, f, ensure_ascii=False, indent=2)

def generate_comment_id():
    """生成评论ID"""
    return f"comment_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"

@app.route('/api/comments/<post_id>', methods=['GET'])
def get_comments(post_id):
    """获取指定帖子的评论"""
    try:
        comments = load_comments()
        # 筛选出指定帖子的评论，按时间正序排列
        post_comments = [c for c in comments if c.get('post_id') == post_id]
        post_comments.sort(key=lambda x: x.get('timestamp', ''))
        return jsonify({'success': True, 'comments': post_comments})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/comments', methods=['POST'])
def post_comment():
    """发表评论"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401
            
        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401
            
        # 从token获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username')
        
        if not username:
            return jsonify({'error': '无法获取用户信息'}), 401
            
        users = load_users()
        if username not in users:
            return jsonify({'error': '用户不存在'}), 404
            
        user_data = users[username]
        user_info = {
            'username': user_data['username'],
            'display_name': user_data['display_name'],
            'role': user_data['role'],
            'avatar': user_data['avatar']
        }
        
        data = request.json or {}
        post_id = data.get('post_id')
        comment_type = data.get('type', 'text')
        content = data.get('content', {})
        
        if not post_id:
            return jsonify({'error': '缺少帖子ID'}), 400
        
        # 验证帖子是否存在
        messages = load_messages()
        post_exists = any(msg.get('id') == post_id for msg in messages)
        if not post_exists:
            return jsonify({'error': '帖子不存在'}), 404
        
        comment = {
            'id': generate_comment_id(),
            'post_id': post_id,
            'user': user_info,
            'type': comment_type,
            'content': content,
            'timestamp': datetime.now().isoformat()
        }
        
        comments = load_comments()
        comments.append(comment)
        save_comments(comments)
        
        return jsonify({'success': True, 'comment': comment})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/comments/<comment_id>', methods=['DELETE'])
def delete_comment(comment_id):
    """删除评论"""
    try:
        # 验证用户登录状态
        token = request.headers.get('Authorization')
        if token and token.startswith('Bearer '):
            token = token[7:]
        else:
            return jsonify({'error': '未登录或token无效'}), 401
            
        if not token or not is_token_valid(token):
            return jsonify({'error': '未登录或token无效'}), 401
            
        # 从token获取用户信息
        tokens = load_tokens()
        username = tokens.get(token, {}).get('username')
        
        if not username:
            return jsonify({'error': '无法获取用户信息'}), 401
        
        comments = load_comments()
        
        # 找到要删除的评论
        comment_to_delete = None
        comment_index = -1
        for i, comment in enumerate(comments):
            if comment.get('id') == comment_id:
                comment_to_delete = comment
                comment_index = i
                break
        
        if not comment_to_delete:
            return jsonify({'error': '评论不存在'}), 404
            
        # 检查是否是评论的作者
        if comment_to_delete.get('user', {}).get('username') != username:
            return jsonify({'error': '只能删除自己的评论'}), 403
        
        # 检查是否有关联的挑战需要删除
        challenge_id = None
        if (comment_to_delete.get('type') == 'mixed_content' and 
            comment_to_delete.get('content', {}).get('challenge')):
            challenge_id = comment_to_delete['content']['challenge'].get('id')
        
        # 删除评论
        comments.pop(comment_index)
        save_comments(comments)
        
        # 删除关联的挑战记录
        if challenge_id:
            try:
                delete_challenge_record(challenge_id)
            except Exception as e:
                # 挑战删除失败不影响评论删除，只记录错误
                print(f"删除挑战记录失败: {e}")
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_audio_list', methods=['GET'])
def get_audio_list_for_share():
    """获取音频列表供分享使用"""
    try:
        categories = {
            'Part1': [],
            'Part2': [],
            'Part3': [],
            '其他': []
        }
        
        if not os.path.exists(MOTHER_DIR):
            return jsonify({'success': True, 'categories': categories})
            
        for folder in os.listdir(MOTHER_DIR):
            folder_path = os.path.join(MOTHER_DIR, folder)
            if os.path.isdir(folder_path) and not folder.startswith('.'):
                files = [f for f in os.listdir(folder_path) if f.endswith('.mp3')]
                if files:
                    # 检查是否有合集
                    combined_file = os.path.join(COMBINED_DIR, f"{folder}.mp3")
                    has_combined = os.path.exists(combined_file)
                    
                    folder_info = {
                        'folder': folder,
                        'file_count': len(files),
                        'has_combined': has_combined
                    }
                    
                    # 对于Part2，添加问题信息
                    if folder.startswith('P2'):
                        question_file = os.path.join(folder_path, 'question.txt')
                        if os.path.exists(question_file):
                            try:
                                with open(question_file, 'r', encoding='utf-8') as f:
                                    folder_info['question'] = f.read().strip()
                            except:
                                pass
                    
                    # 分类
                    if folder.startswith('P1'):
                        categories['Part1'].append(folder_info)
                    elif folder.startswith('P2'):
                        categories['Part2'].append(folder_info)
                    elif folder.startswith('P3'):
                        categories['Part3'].append(folder_info)
                    else:
                        categories['其他'].append(folder_info)
        
        return jsonify({'success': True, 'categories': categories})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_articles_list', methods=['GET'])
def get_articles_list_for_share():
    """获取文章列表供分享使用"""
    try:
        categories = {'Reading': [], 'Listening': [], 'Writing': []}
        
        if not os.path.exists(INTENSIVE_DIR):
            return jsonify({'success': True, 'categories': categories})
            
        for fname in os.listdir(INTENSIVE_DIR):
            if not fname.endswith('.json'):
                continue
            fpath = os.path.join(INTENSIVE_DIR, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                article_info = {
                    'id': data.get('id'),
                    'title': data.get('title'),
                    'category': data.get('category', 'Reading'),
                    'highlight_count': len(data.get('highlights') or [])
                }
                category = article_info['category']
                if category in categories:
                    categories[category].append(article_info)
            except:
                continue
                
        return jsonify({'success': True, 'categories': categories})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 挑战系统相关API ====================

def _challenge_file(challenge_id):
    """获取挑战文件路径"""
    return os.path.join(CHALLENGES_DIR, f"{challenge_id}.json")

def verify_token_get_username(token):
    """从token中获取用户名"""
    if not token or not is_token_valid(token):
        return None
    
    tokens = load_tokens()
    return tokens.get(token, {}).get('username')

def delete_challenge_record(challenge_id):
    """删除挑战记录文件和相关音频"""
    challenge_path = _challenge_file(challenge_id)
    success = False
    
    if os.path.exists(challenge_path):
        os.remove(challenge_path)
        success = True
    
    # 删除挑战相关的音频文件
    challenge_audio_id = f"challenge_{challenge_id}"
    delete_article_vocab_audio(challenge_audio_id)
    
    return success

def extract_vocabulary_from_articles(article_ids, word_count):
    """从指定文章中提取词汇，优化随机算法"""
    import random
    import hashlib
    from collections import defaultdict
    
    # 按文章分组收集词汇
    articles_vocab = defaultdict(list)
    
    for article_id in article_ids:
        article_path = _article_path(article_id)
        if os.path.exists(article_path):
            try:
                with open(article_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                highlights = data.get('highlights', [])
                for highlight in highlights:
                    vocab_item = {
                        'word': highlight.get('text', '').strip(),
                        'meaning': highlight.get('meaning', '').strip(),
                        'article_id': article_id,
                        'article_title': data.get('title', ''),
                        'highlight_id': highlight.get('id')
                    }
                    if vocab_item['word'] and vocab_item['meaning']:
                        articles_vocab[article_id].append(vocab_item)
            except Exception as e:
                continue
    
    # 智能去重：基于词汇内容而不仅仅是文本
    unique_vocab = []
    seen_items = set()
    
    for article_id, vocabs in articles_vocab.items():
        # 对每篇文章的词汇进行随机打乱
        random.shuffle(vocabs)
        
        for vocab in vocabs:
            # 生成基于词汇和含义的唯一标识
            word_lower = vocab['word'].lower().strip()
            meaning_lower = vocab['meaning'].lower().strip()
            
            # 创建更严格的去重机制
            vocab_hash = hashlib.md5(f"{word_lower}::{meaning_lower}".encode()).hexdigest()
            
            if vocab_hash not in seen_items:
                seen_items.add(vocab_hash)
                unique_vocab.append(vocab)
    
    # 如果词汇数量不足，返回所有可用词汇
    if len(unique_vocab) <= word_count:
        return unique_vocab
    
    # 多重随机策略选择词汇
    selected_vocab = []
    
    # 策略1：确保每篇文章至少有一个词汇被选中（如果可能）
    article_representation = {}
    for vocab in unique_vocab:
        aid = vocab['article_id']
        if aid not in article_representation:
            article_representation[aid] = []
        article_representation[aid].append(vocab)
    
    # 从每篇文章随机选择1-2个词汇作为基础
    for aid, vocabs in article_representation.items():
        if len(selected_vocab) >= word_count:
            break
        
        # 根据剩余配额决定从这篇文章选择多少个
        remaining = word_count - len(selected_vocab)
        from_this_article = min(len(vocabs), max(1, remaining // len(article_representation)))
        
        # 随机选择
        selected_from_article = random.sample(vocabs, min(from_this_article, len(vocabs)))
        selected_vocab.extend(selected_from_article)
    
    # 策略2：如果还需要更多词汇，从剩余池中随机选择
    if len(selected_vocab) < word_count:
        remaining_vocab = [v for v in unique_vocab if v not in selected_vocab]
        if remaining_vocab:
            additional_needed = word_count - len(selected_vocab)
            additional = random.sample(remaining_vocab, 
                                     min(additional_needed, len(remaining_vocab)))
            selected_vocab.extend(additional)
    
    # 策略3：最终随机打乱顺序
    random.shuffle(selected_vocab)
    
    # 返回精确数量的词汇
    return selected_vocab[:word_count]

@app.route('/api/get_users_list', methods=['GET'])
def get_users_list():
    """获取用户列表供@功能使用"""
    try:
        users = load_users()
        user_list = []
        for username, user_data in users.items():
            user_list.append({
                'username': username,
                'display_name': user_data.get('display_name', username),
                'avatar': user_data.get('avatar', 'avatar_admin.svg')
            })
        return jsonify({'success': True, 'users': user_list})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/create_challenge', methods=['POST'])
def create_challenge():
    """创建词汇挑战"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        data = request.json
        article_ids = data.get('article_ids', [])
        word_count = int(data.get('word_count', 10))
        mentioned_users = data.get('mentioned_users', [])  # @的用户列表
        title = data.get('title', '词汇挑战').strip()
        description = data.get('description', '').strip()
        
        if not article_ids:
            return jsonify({'error': '请选择至少一篇文章'}), 400
        
        if word_count < 1 or word_count > 50:
            return jsonify({'error': '词汇数量应在1-50之间'}), 400
        
        # 提取词汇
        vocabulary = extract_vocabulary_from_articles(article_ids, word_count)
        
        if not vocabulary:
            return jsonify({'error': '从选中的文章中未找到足够的词汇'}), 400
        
        # 创建挑战
        challenge_id = str(uuid.uuid4())
        challenge_data = {
            'id': challenge_id,
            'title': title,
            'description': description,
            'creator': username,
            'created_at': datetime.now().isoformat(),
            'article_ids': article_ids,
            'vocabulary': vocabulary,
            'mentioned_users': mentioned_users,
            'participants': {},  # username: {score, completed_at, answers: []}
            'status': 'active'  # active, completed
        }
        
        # 保存挑战数据
        with open(_challenge_file(challenge_id), 'w', encoding='utf-8') as f:
            json.dump(challenge_data, f, ensure_ascii=False, indent=2)
        
        # 异步生成所有词汇的音频
        def _generate_challenge_audio():
            try:
                for vocab in vocabulary:
                    word = vocab.get('word', '').strip()
                    if word:
                        generate_challenge_vocab_audio(challenge_id, word)
                        time.sleep(0.5)  # 避免API频率限制
                print(f"挑战 {challenge_id} 的音频生成完成")
            except Exception as e:
                print(f"挑战 {challenge_id} 音频生成失败: {e}")
        
        thread = threading.Thread(target=_generate_challenge_audio, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'challenge_id': challenge_id,
            'vocabulary_count': len(vocabulary)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_challenge/<challenge_id>', methods=['GET'])
def get_challenge(challenge_id):
    """获取挑战详情"""
    try:
        challenge_path = _challenge_file(challenge_id)
        if not os.path.exists(challenge_path):
            return jsonify({'error': '挑战不存在'}), 404
        
        with open(challenge_path, 'r', encoding='utf-8') as f:
            challenge_data = json.load(f)
        
        return jsonify({'success': True, 'challenge': challenge_data})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/participate_challenge', methods=['POST'])
def participate_challenge():
    """参与挑战（提交答案）"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        data = request.json
        challenge_id = data.get('challenge_id')
        answers = data.get('answers', [])  # [{question_index, selected_option, time_taken, is_correct}]
        
        challenge_path = _challenge_file(challenge_id)
        if not os.path.exists(challenge_path):
            return jsonify({'error': '挑战不存在'}), 404
        
        # 加载挑战数据
        with open(challenge_path, 'r', encoding='utf-8') as f:
            challenge_data = json.load(f)
        
        # 计算分数
        total_questions = len(challenge_data['vocabulary'])
        correct_count = sum(1 for answer in answers if answer.get('is_correct', False))
        
        # 时间奖励计算：每个问题最多10秒，用时越少奖励越多
        time_bonus = 0
        for answer in answers:
            time_taken = answer.get('time_taken', 10)  # 默认10秒
            if answer.get('is_correct', False):
                # 正确答案才有时间奖励，1-10秒对应10-1分的时间奖励
                time_bonus += max(1, 11 - min(10, time_taken))
        
        # 总分 = (正确数/总数 * 70) + (时间奖励 * 30 / (总数 * 10))
        accuracy_score = (correct_count / total_questions) * 70
        time_score = (time_bonus * 30) / (total_questions * 10)
        total_score = round(accuracy_score + time_score, 2)
        
        # 更新参与者数据
        challenge_data['participants'][username] = {
            'score': total_score,
            'correct_count': correct_count,
            'total_questions': total_questions,
            'completed_at': datetime.now().isoformat(),
            'answers': answers,
            'time_bonus': time_bonus
        }
        
        # 检查是否所有被@的用户都已完成
        if challenge_data.get('mentioned_users'):
            all_completed = all(
                user in challenge_data['participants'] 
                for user in challenge_data['mentioned_users']
            )
            if all_completed:
                challenge_data['status'] = 'completed'
        
        # 保存更新后的挑战数据
        with open(challenge_path, 'w', encoding='utf-8') as f:
            json.dump(challenge_data, f, ensure_ascii=False, indent=2)
        
        return jsonify({
            'success': True,
            'score': total_score,
            'correct_count': correct_count,
            'total_questions': total_questions,
            'ranking_ready': challenge_data['status'] == 'completed' or not challenge_data.get('mentioned_users')
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_challenge_ranking/<challenge_id>', methods=['GET'])
def get_challenge_ranking(challenge_id):
    """获取挑战排名"""
    try:
        challenge_path = _challenge_file(challenge_id)
        if not os.path.exists(challenge_path):
            return jsonify({'error': '挑战不存在'}), 404
        
        with open(challenge_path, 'r', encoding='utf-8') as f:
            challenge_data = json.load(f)
        
        # 获取用户信息
        users = load_users()
        
        # 构建排名数据
        ranking = []
        for username, result in challenge_data['participants'].items():
            user_info = users.get(username, {})
            ranking.append({
                'username': username,
                'display_name': user_info.get('display_name', username),
                'avatar': user_info.get('avatar', 'avatar_admin.svg'),
                'score': result['score'],
                'correct_count': result['correct_count'],
                'total_questions': result['total_questions'],
                'completed_at': result['completed_at']
            })
        
        # 按分数排序
        ranking.sort(key=lambda x: x['score'], reverse=True)
        
        return jsonify({
            'success': True,
            'ranking': ranking,
            'challenge': {
                'title': challenge_data['title'],
                'description': challenge_data['description'],
                'status': challenge_data['status'],
                'vocabulary_count': len(challenge_data['vocabulary'])
            }
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocab_summary_challenge', methods=['POST'])
def create_vocab_summary_challenge():
    """为词汇汇总创建个人挑战"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        data = request.json
        article_ids = data.get('article_ids', [])
        word_count = int(data.get('word_count', 20))
        
        if not article_ids:
            return jsonify({'error': '请选择至少一篇文章'}), 400
        
        if word_count < 5 or word_count > 50:
            return jsonify({'error': '词汇数量应在5-50之间'}), 400
        
        # 使用改进的词汇提取算法
        vocabulary = extract_vocabulary_from_articles_improved(article_ids, word_count)
        
        if not vocabulary:
            return jsonify({'error': '从选中的文章中未找到足够的词汇'}), 400
        
        # 创建个人挑战数据结构（不保存到文件，直接返回）
        challenge_id = f'vocab_summary_{int(time.time())}_{username}'
        challenge_data = {
            'id': challenge_id,
            'type': 'vocab_summary',
            'creator': username,
            'created_at': datetime.now().isoformat(),
            'article_ids': article_ids,
            'vocabulary': vocabulary,
            'word_count': len(vocabulary)
        }
        
        # 异步生成所有词汇的音频
        def _generate_vocab_summary_audio():
            try:
                for vocab in vocabulary:
                    word = vocab.get('word', '').strip()
                    if word:
                        generate_challenge_vocab_audio(challenge_id, word)
                        time.sleep(0.5)  # 避免API频率限制
                print(f"词汇汇总挑战 {challenge_id} 的音频生成完成")
            except Exception as e:
                print(f"词汇汇总挑战 {challenge_id} 音频生成失败: {e}")
        
        thread = threading.Thread(target=_generate_vocab_summary_audio, daemon=True)
        thread.start()
        
        return jsonify({
            'success': True,
            'challenge': challenge_data
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def extract_vocabulary_from_articles_improved(article_ids, word_count):
    """改进的词汇提取算法，专为词汇汇总挑战优化"""
    import random
    import hashlib
    from collections import defaultdict
    
    # 按文章分组收集词汇
    articles_vocab = defaultdict(list)
    
    for article_id in article_ids:
        article_path = _article_path(article_id)
        if os.path.exists(article_path):
            try:
                with open(article_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                highlights = data.get('highlights', [])
                for highlight in highlights:
                    vocab_item = {
                        'word': highlight.get('text', '').strip(),
                        'meaning': highlight.get('meaning', '').strip(),
                        'article_id': article_id,
                        'article_title': data.get('title', ''),
                        'highlight_id': highlight.get('id')
                    }
                    if vocab_item['word'] and vocab_item['meaning']:
                        articles_vocab[article_id].append(vocab_item)
            except Exception as e:
                continue
    
    # 智能去重：基于词汇内容而不仅仅是文本
    unique_vocab = []
    seen_items = set()
    
    for article_id, vocabs in articles_vocab.items():
        # 对每篇文章的词汇进行随机打乱
        random.shuffle(vocabs)
        
        for vocab in vocabs:
            # 生成基于词汇和含义的唯一标识
            word_lower = vocab['word'].lower().strip()
            meaning_lower = vocab['meaning'].lower().strip()
            
            # 创建更严格的去重机制
            vocab_hash = hashlib.md5(f"{word_lower}::{meaning_lower}".encode()).hexdigest()
            
            if vocab_hash not in seen_items:
                seen_items.add(vocab_hash)
                unique_vocab.append(vocab)
    
    # 如果词汇数量不足，返回所有可用词汇
    if len(unique_vocab) <= word_count:
        random.shuffle(unique_vocab)
        return unique_vocab
    
    # 多重随机策略选择词汇
    selected_vocab = []
    
    # 策略1：确保每篇文章至少有一个词汇被选中（如果可能）
    article_representation = {}
    for vocab in unique_vocab:
        aid = vocab['article_id']
        if aid not in article_representation:
            article_representation[aid] = []
        article_representation[aid].append(vocab)
    
    # 从每篇文章随机选择词汇作为基础
    for aid, vocabs in article_representation.items():
        if len(selected_vocab) >= word_count:
            break
        
        # 根据剩余配额决定从这篇文章选择多少个
        remaining = word_count - len(selected_vocab)
        articles_left = len([a for a in article_representation.keys() if a >= aid])
        from_this_article = min(len(vocabs), max(1, remaining // articles_left))
        
        # 随机选择
        selected_from_article = random.sample(vocabs, min(from_this_article, len(vocabs)))
        selected_vocab.extend(selected_from_article)
    
    # 策略2：如果还需要更多词汇，从剩余池中随机选择
    if len(selected_vocab) < word_count:
        remaining_vocab = [v for v in unique_vocab if v not in selected_vocab]
        if remaining_vocab:
            additional_needed = word_count - len(selected_vocab)
            additional = random.sample(remaining_vocab, 
                                     min(additional_needed, len(remaining_vocab)))
            selected_vocab.extend(additional)
    
    # 策略3：最终随机打乱顺序，确保每次挑战顺序不同
    random.shuffle(selected_vocab)
    
    # 返回精确数量的词汇
    return selected_vocab[:word_count]

@app.route('/api/vocab_challenge_record', methods=['POST'])
def save_vocab_challenge_record():
    """保存词汇挑战记录"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        data = request.json
        challenge_record = data.get('challenge_record')
        
        if not challenge_record:
            return jsonify({'error': '挑战记录不能为空'}), 400
        
        # 确保记录包含用户信息
        challenge_record['username'] = username
        challenge_record['saved_at'] = datetime.now().isoformat()
        
        # 保存到用户专用的挑战记录文件
        user_challenge_file = os.path.join(CHALLENGES_DIR, f'vocab_summary_{username}.json')
        
        # 创建目录（如果不存在）
        os.makedirs(CHALLENGES_DIR, exist_ok=True)
        
        # 读取现有记录
        existing_records = []
        if os.path.exists(user_challenge_file):
            try:
                with open(user_challenge_file, 'r', encoding='utf-8') as f:
                    existing_records = json.load(f)
            except:
                existing_records = []
        
        # 添加新记录到开头
        existing_records.insert(0, challenge_record)
        
        # 只保留最近100条记录
        if len(existing_records) > 100:
            existing_records = existing_records[:100]
        
        # 保存记录
        with open(user_challenge_file, 'w', encoding='utf-8') as f:
            json.dump(existing_records, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'record_count': len(existing_records)})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocab_challenge_records', methods=['GET'])
def get_vocab_challenge_records():
    """获取用户的词汇挑战记录"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        # 读取用户的挑战记录
        user_challenge_file = os.path.join(CHALLENGES_DIR, f'vocab_summary_{username}.json')
        
        records = []
        if os.path.exists(user_challenge_file):
            try:
                with open(user_challenge_file, 'r', encoding='utf-8') as f:
                    records = json.load(f)
            except:
                records = []
        
        return jsonify({'success': True, 'records': records})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocab_wrong_words', methods=['POST'])
def save_vocab_wrong_words():
    """保存错词记录"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        data = request.json
        wrong_words = data.get('wrong_words', {})
        
        # 保存到用户专用的错词记录文件
        user_wrong_words_file = os.path.join(CHALLENGES_DIR, f'wrong_words_{username}.json')
        
        # 创建目录（如果不存在）
        os.makedirs(CHALLENGES_DIR, exist_ok=True)
        
        # 保存错词记录
        with open(user_wrong_words_file, 'w', encoding='utf-8') as f:
            json.dump(wrong_words, f, ensure_ascii=False, indent=2)
        
        return jsonify({'success': True, 'word_count': len(wrong_words)})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/vocab_wrong_words', methods=['GET'])
def get_vocab_wrong_words():
    """获取用户的错词记录"""
    try:
        # 验证token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        # 读取用户的错词记录
        user_wrong_words_file = os.path.join(CHALLENGES_DIR, f'wrong_words_{username}.json')
        
        wrong_words = {}
        if os.path.exists(user_wrong_words_file):
            try:
                with open(user_wrong_words_file, 'r', encoding='utf-8') as f:
                    wrong_words = json.load(f)
            except:
                wrong_words = {}
        
        return jsonify({'success': True, 'wrong_words': wrong_words})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/cleanup_orphaned_challenges', methods=['POST'])
def cleanup_orphaned_challenges():
    """清理孤立的挑战记录（没有对应帖子的挑战）"""
    try:
        # 验证管理员权限
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': '未授权'}), 401
        
        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': '无效token'}), 401
        
        # 获取所有消息中的挑战ID
        messages = load_messages()
        active_challenge_ids = set()
        
        for message in messages:
            if (message.get('type') == 'mixed_content' and 
                message.get('content', {}).get('challenge')):
                challenge_id = message['content']['challenge'].get('id')
                if challenge_id:
                    active_challenge_ids.add(challenge_id)
        
        # 检查挑战文件夹中的所有挑战
        orphaned_challenges = []
        if os.path.exists(CHALLENGES_DIR):
            for filename in os.listdir(CHALLENGES_DIR):
                if filename.endswith('.json'):
                    challenge_id = filename.replace('.json', '')
                    if challenge_id not in active_challenge_ids:
                        orphaned_challenges.append(challenge_id)
        
        # 删除孤立的挑战记录
        deleted_count = 0
        for challenge_id in orphaned_challenges:
            try:
                if delete_challenge_record(challenge_id):
                    deleted_count += 1
            except Exception as e:
                print(f"删除孤立挑战记录失败 {challenge_id}: {e}")
        
        return jsonify({
            'success': True,
            'orphaned_count': len(orphaned_challenges),
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==================== 单词本相关API ====================

def load_category_data(category):
    """加载单个分类的数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    if os.path.exists(category_file):
        try:
            with open(category_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 数据迁移：为现有单词添加 is_favorited 字段
                updated = False
                for subcategory_id in data['subcategories']:
                    for word in data['subcategories'][subcategory_id]['words']:
                        if 'is_favorited' not in word:
                            word['is_favorited'] = False
                            updated = True
                
                # 如果有更新，直接保存数据（避免递归调用）
                if updated:
                    data['metadata']['last_updated'] = datetime.now().isoformat()
                    with open(category_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                
                return data
        except:
            pass
    
    # 返回默认结构
    now = datetime.now().isoformat()
    return {
        "name": category.capitalize(),
        "icon": {"listening": "🎧", "speaking": "🗣️", "reading": "📖", "writing": "✍️"}[category],
        "subcategories": {
            "default": {
                "name": "默认分类",
                "created_at": now,
                "words": []
            }
        },
        "metadata": {
            "created_at": now,
            "last_updated": now
        }
    }

def save_category_data(category, data):
    """保存单个分类的数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    data['metadata']['last_updated'] = datetime.now().isoformat()
    with open(category_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_vocabulary_data():
    """加载完整的词汇数据（兼容旧接口）"""
    categories = {}
    for category in ['listening', 'speaking', 'reading', 'writing']:
        categories[category] = load_category_data(category)
    
    return {
        "categories": categories,
        "metadata": {
            "version": "3.0",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    }

def save_vocabulary_data(vocab_data):
    """保存完整的词汇数据（兼容旧接口）"""
    for category, data in vocab_data['categories'].items():
        save_category_data(category, data)

def add_audio_task(word_id, word, category, subcategory_id):
    """添加音频生成任务到持久化队列"""
    task = {
        'id': str(uuid.uuid4()),
        'word_id': word_id,
        'word': word,
        'category': category,
        'subcategory_id': subcategory_id,
        'status': 'pending',
        'created_at': datetime.now().isoformat(),
        'attempts': 0,
        'max_attempts': 3
    }
    
    task_file = os.path.join(VOCABULARY_TASKS_DIR, f'{task["id"]}.json')
    with open(task_file, 'w', encoding='utf-8') as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
    
    return task['id']

def get_pending_audio_tasks():
    """获取所有待处理的音频任务"""
    tasks = []
    if not os.path.exists(VOCABULARY_TASKS_DIR):
        return tasks
    
    for filename in os.listdir(VOCABULARY_TASKS_DIR):
        if filename.endswith('.json'):
            try:
                task_file = os.path.join(VOCABULARY_TASKS_DIR, filename)
                with open(task_file, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                    if task['status'] == 'pending' and task['attempts'] < task['max_attempts']:
                        tasks.append(task)
            except:
                continue
    
    # 按创建时间排序
    tasks.sort(key=lambda x: x['created_at'])
    return tasks

def update_audio_task_status(task_id, status, error_msg=None):
    """更新音频任务状态"""
    task_file = os.path.join(VOCABULARY_TASKS_DIR, f'{task_id}.json')
    if os.path.exists(task_file):
        try:
            with open(task_file, 'r', encoding='utf-8') as f:
                task = json.load(f)
            
            task['status'] = status
            task['last_updated'] = datetime.now().isoformat()
            
            if status == 'failed':
                task['attempts'] += 1
                task['error'] = error_msg
                if task['attempts'] >= task['max_attempts']:
                    task['status'] = 'max_attempts_reached'
            
            with open(task_file, 'w', encoding='utf-8') as f:
                json.dump(task, f, ensure_ascii=False, indent=2)
                
            # 如果任务完成或失败达到最大次数，删除任务文件
            if status in ['completed', 'max_attempts_reached']:
                os.remove(task_file)
                
        except Exception as e:
            print(f"更新任务状态失败: {e}")

def generate_word_audio(word, word_id, category):
    """为单词生成音频文件"""
    try:
        # 使用现有的TTS API生成音频
        api_key = os.getenv('DEER_API_KEY')
        if not api_key:
            return False
        
        url = "https://api.deerapi.com/v1/audio/speech"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": "tts-1",
            "input": word,
            "voice": "nova",
            "response_format": "mp3"
        }
        
        response = requests.post(url, headers=headers, json=data)
        if response.status_code == 200:
            # 按分类存储音频文件
            category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)
            audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
            with open(audio_path, 'wb') as f:
                f.write(response.content)
            return True
        return False
    except Exception as e:
        print(f"生成单词音频失败: {e}")
        return False

def process_audio_tasks():
    """处理音频生成任务队列"""
    tasks = get_pending_audio_tasks()
    
    for task in tasks[:5]:  # 每次最多处理5个任务
        try:
            # 更新任务状态为处理中
            update_audio_task_status(task['id'], 'processing')
            
            # 生成音频
            success = generate_word_audio(task['word'], task['word_id'], task['category'])
            
            if success:
                # 更新数据库中的音频状态
                category_data = load_category_data(task['category'])
                if task['subcategory_id'] in category_data['subcategories']:
                    for word in category_data['subcategories'][task['subcategory_id']]['words']:
                        if word['id'] == task['word_id']:
                            word['audio_generated'] = True
                            break
                    save_category_data(task['category'], category_data)
                
                # 标记任务完成
                update_audio_task_status(task['id'], 'completed')
                print(f"音频生成成功: {task['word']}")
            else:
                # 标记任务失败
                update_audio_task_status(task['id'], 'failed', '音频生成API调用失败')
                print(f"音频生成失败: {task['word']}")
            
            # 避免API限制
            time.sleep(0.5)
            
        except Exception as e:
            update_audio_task_status(task['id'], 'failed', str(e))
            print(f"处理音频任务失败: {e}")

# 启动后台任务处理线程
def start_audio_task_processor():
    """启动音频任务处理器"""
    def task_processor():
        while True:
            try:
                process_audio_tasks()
                time.sleep(10)  # 每10秒检查一次任务队列
            except Exception as e:
                print(f"音频任务处理器错误: {e}")
                time.sleep(30)  # 发生错误时等待更长时间
    
    processor_thread = threading.Thread(target=task_processor, daemon=True)
    processor_thread.start()
    print("音频任务处理器已启动")

# 在应用启动时启动任务处理器
start_audio_task_processor()

@app.route('/vocabulary')
def vocabulary_page():
    """单词本页面"""
    return send_file('templates/vocabulary.html')

@app.route('/api/vocabulary', methods=['GET'])
def get_vocabulary():
    """获取单词本数据"""
    try:
        vocab_data = load_vocabulary_data()
        return jsonify({'success': True, 'data': vocab_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/subcategories/<category>', methods=['GET'])
def get_subcategories(category):
    """获取指定分类的子分类列表"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        category_data = load_category_data(category)
        subcategories = category_data['subcategories']
        
        # 转换为列表格式，方便前端使用
        subcategory_list = []
        for sub_id, sub_data in subcategories.items():
            subcategory_list.append({
                'id': sub_id,
                'name': sub_data['name'],
                'created_at': sub_data['created_at'],
                'word_count': len(sub_data['words'])
            })
        
        # 按创建时间排序
        subcategory_list.sort(key=lambda x: x['created_at'])
        
        return jsonify({'success': True, 'data': subcategory_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/subcategories', methods=['POST'])
def create_subcategory():
    """创建新的子分类"""
    try:
        data = request.json
        category = data.get('category')
        name = data.get('name', '').strip()
        
        if not category or category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        if not name:
            return jsonify({'success': False, 'error': '子分类名称不能为空'}), 400
        
        category_data = load_category_data(category)
        
        # 检查子分类名称是否已存在
        existing_names = [sub['name'] for sub in category_data['subcategories'].values()]
        if name in existing_names:
            return jsonify({'success': False, 'error': '子分类名称已存在'}), 400
        
        # 生成唯一ID
        subcategory_id = str(uuid.uuid4())
        
        # 创建子分类
        category_data['subcategories'][subcategory_id] = {
            'name': name,
            'created_at': datetime.now().isoformat(),
            'words': []
        }
        
        save_category_data(category, category_data)
        
        return jsonify({
            'success': True, 
            'data': {
                'id': subcategory_id,
                'name': name,
                'created_at': category_data['subcategories'][subcategory_id]['created_at'],
                'word_count': 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/subcategories/<category>/<subcategory_id>', methods=['PUT'])
def update_subcategory(category, subcategory_id):
    """更新子分类名称"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        data = request.json
        new_name = data.get('name', '').strip()
        
        if not new_name:
            return jsonify({'success': False, 'error': '子分类名称不能为空'}), 400
        
        category_data = load_category_data(category)
        
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 404
        
        # 检查新名称是否与其他子分类重复
        existing_names = [sub['name'] for sub_id, sub in category_data['subcategories'].items() if sub_id != subcategory_id]
        if new_name in existing_names:
            return jsonify({'success': False, 'error': '子分类名称已存在'}), 400
        
        # 更新名称
        category_data['subcategories'][subcategory_id]['name'] = new_name
        save_category_data(category, category_data)
        
        return jsonify({'success': True, 'message': '子分类名称更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/subcategories/<category>/<subcategory_id>', methods=['DELETE'])
def delete_subcategory(category, subcategory_id):
    """删除子分类"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        category_data = load_category_data(category)
        
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 404
        
        # 检查是否是最后一个子分类（至少保留一个）
        if len(category_data['subcategories']) <= 1:
            return jsonify({'success': False, 'error': '至少需要保留一个子分类'}), 400
        
        # 删除子分类中所有单词的音频文件
        words = category_data['subcategories'][subcategory_id]['words']
        category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)
        
        for word in words:
            # 删除音频文件
            audio_path = os.path.join(category_audio_dir, f"{word['id']}.mp3")
            if os.path.exists(audio_path):
                os.remove(audio_path)
            
            # 删除相关的音频生成任务
            for task_file in os.listdir(VOCABULARY_TASKS_DIR):
                if task_file.endswith('.json'):
                    try:
                        task_path = os.path.join(VOCABULARY_TASKS_DIR, task_file)
                        with open(task_path, 'r', encoding='utf-8') as f:
                            task = json.load(f)
                        if task.get('word_id') == word['id']:
                            os.remove(task_path)
                    except:
                        continue
        
        # 删除子分类
        del category_data['subcategories'][subcategory_id]
        save_category_data(category, category_data)
        
        return jsonify({'success': True, 'message': '子分类删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/add', methods=['POST'])
def add_vocabulary_word():
    """添加单词"""
    try:
        data = request.json
        category = data.get('category')  # speaking, writing, listening, reading
        subcategory_id = data.get('subcategory_id', 'default')
        word = data.get('word', '').strip()
        meaning = data.get('meaning', '').strip()
        
        if not category or category not in ['speaking', 'writing', 'listening', 'reading']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        if not word:
            return jsonify({'success': False, 'error': '单词不能为空'}), 400
        
        category_data = load_category_data(category)
        
        # 检查子分类是否存在
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 400
        
        # 检查是否已存在（仅在该子分类内判重）
        subcategory_words = category_data['subcategories'][subcategory_id]['words']
        for existing_word in subcategory_words:
            if existing_word['word'].lower() == word.lower():
                return jsonify({'success': False, 'error': '单词在该子分类中已存在'}), 400
        
        # 生成唯一ID
        word_id = str(uuid.uuid4())
        
        # 创建单词对象
        word_obj = {
            'id': word_id,
            'word': word,
            'meaning': meaning,
            'created_at': datetime.now().isoformat(),
            'audio_generated': False,
            'is_favorited': False  # 默认未收藏
        }
        
        # 添加到对应子分类
        category_data['subcategories'][subcategory_id]['words'].append(word_obj)
        save_category_data(category, category_data)
        
        # 添加到音频生成任务队列
        add_audio_task(word_id, word, category, subcategory_id)
        
        return jsonify({'success': True, 'data': word_obj})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/upload_csv', methods=['POST'])
def upload_vocabulary_csv():
    """批量上传CSV文件"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'}), 400
        
        file = request.files['file']
        category = request.form.get('category')
        subcategory_id = request.form.get('subcategory_id', 'default')
        
        if not category or category not in ['speaking', 'writing', 'listening', 'reading']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400
        
        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'}), 400
        
        if not file.filename.endswith('.csv'):
            return jsonify({'success': False, 'error': '只支持CSV文件'}), 400
        
        # 读取CSV文件
        import csv
        import io
        
        content = file.read().decode('utf-8')
        csv_reader = csv.reader(io.StringIO(content))
        
        category_data = load_category_data(category)
        
        # 检查子分类是否存在
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 400
        
        existing_words = {w['word'].lower() for w in category_data['subcategories'][subcategory_id]['words']}
        
        added_words = []
        skipped_words = []
        
        for row in csv_reader:
            if len(row) >= 2:
                word = row[0].strip()
                meaning = row[1].strip()
                
                if not word:
                    continue
                
                # 判重（仅在该子分类内）
                if word.lower() in existing_words:
                    skipped_words.append(word)
                    continue
                
                # 生成唯一ID
                word_id = str(uuid.uuid4())
                
                word_obj = {
                    'id': word_id,
                    'word': word,
                    'meaning': meaning,
                    'created_at': datetime.now().isoformat(),
                    'audio_generated': False
                }
                
                category_data['subcategories'][subcategory_id]['words'].append(word_obj)
                added_words.append(word_obj)
                existing_words.add(word.lower())
                
                # 添加到音频生成任务队列
                add_audio_task(word_id, word, category, subcategory_id)
        
        save_category_data(category, category_data)
        
        return jsonify({
            'success': True,
            'added_count': len(added_words),
            'skipped_count': len(skipped_words),
            'skipped_words': skipped_words[:10]  # 只返回前10个重复的单词
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/<word_id>', methods=['DELETE'])
def delete_vocabulary_word(word_id):
    """删除单词"""
    try:
        deleted = False
        deleted_category = None
        
        # 在所有分类和子分类中查找并删除
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_data = load_category_data(category)
            
            for subcategory_id in category_data['subcategories']:
                words = category_data['subcategories'][subcategory_id]['words']
                original_length = len(words)
                category_data['subcategories'][subcategory_id]['words'] = [
                    w for w in words if w['id'] != word_id
                ]
                
                if len(category_data['subcategories'][subcategory_id]['words']) < original_length:
                    deleted = True
                    deleted_category = category
                    save_category_data(category, category_data)
                    break
            
            if deleted:
                break
        
        if not deleted:
            return jsonify({'success': False, 'error': '单词不存在'}), 404
        
        # 删除音频文件（按分类存储）
        if deleted_category:
            category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, deleted_category)
            audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
            if os.path.exists(audio_path):
                os.remove(audio_path)
        
        # 删除相关的音频生成任务
        if os.path.exists(VOCABULARY_TASKS_DIR):
            for task_file in os.listdir(VOCABULARY_TASKS_DIR):
                if task_file.endswith('.json'):
                    try:
                        task_path = os.path.join(VOCABULARY_TASKS_DIR, task_file)
                        with open(task_path, 'r', encoding='utf-8') as f:
                            task = json.load(f)
                        if task.get('word_id') == word_id:
                            os.remove(task_path)
                    except:
                        continue
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/<word_id>/favorite', methods=['PUT'])
def toggle_word_favorite(word_id):
    """切换单词收藏状态"""
    try:
        data = request.json
        is_favorited = data.get('is_favorited', False)
        
        found = False
        updated_word = None
        
        # 在所有分类和子分类中查找并更新
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_data = load_category_data(category)
            
            for subcategory_id in category_data['subcategories']:
                words = category_data['subcategories'][subcategory_id]['words']
                
                for word in words:
                    if word['id'] == word_id:
                        word['is_favorited'] = is_favorited
                        updated_word = word
                        found = True
                        save_category_data(category, category_data)
                        break
                
                if found:
                    break
            
            if found:
                break
        
        if not found:
            return jsonify({'success': False, 'error': '单词不存在'}), 404
        
        return jsonify({'success': True, 'data': updated_word})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 单词挑战相关API ====================

def load_user_challenge_data(user_id):
    """加载用户的挑战数据"""
    user_file = os.path.join(VOCABULARY_CHALLENGE_DIR, f'{user_id}.json')
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass

    # 返回默认结构
    return {
        "word_coverage": {},
        "challenge_stats": {
            "total_challenges": 0,
            "total_correct": 0,
            "total_questions": 0,
            "last_challenge": None
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    }

def save_user_challenge_data(user_id, data):
    """保存用户的挑战数据"""
    user_file = os.path.join(VOCABULARY_CHALLENGE_DIR, f'{user_id}.json')
    data['metadata']['last_updated'] = datetime.now().isoformat()
    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_current_user_id():
    """获取当前用户ID从请求头中获取"""
    try:
        # 从请求头中获取用户信息
        auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        current_user = request.headers.get('X-Current-User', '')

        if current_user:
            # 如果是JSON字符串，解析并提取username
            if current_user.startswith('{') and current_user.endswith('}'):
                try:
                    user_obj = json.loads(current_user)
                    return user_obj.get('username', 'default_user')
                except json.JSONDecodeError:
                    pass

            # 如果已经是字符串，直接使用
            return current_user

        # 如果没有用户信息，使用默认值
        return "default_user"
    except:
        return "default_user"

@app.route('/api/vocabulary/challenge/coverage')
def get_challenge_coverage():
    """获取用户的挑战覆盖率数据"""
    try:
        user_id = get_current_user_id()
        challenge_data = load_user_challenge_data(user_id)
        return jsonify({'success': True, 'data': challenge_data['word_coverage']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/vocabulary/challenge/record', methods=['POST'])
def record_challenge_result():
    """记录挑战结果"""
    try:
        user_id = get_current_user_id()
        data = request.json
        challenge_results = data.get('results', [])
        scope = data.get('scope')
        category = data.get('category')
        subcategory_id = data.get('subcategory_id')

        # 加载用户挑战数据
        challenge_data = load_user_challenge_data(user_id)

        # 更新单词覆盖率
        for result in challenge_results:
            word_id = result['word_id']
            if word_id not in challenge_data['word_coverage']:
                challenge_data['word_coverage'][word_id] = {
                    'appear_count': 0,
                    'last_appeared': None
                }
            challenge_data['word_coverage'][word_id]['appear_count'] += 1
            challenge_data['word_coverage'][word_id]['last_appeared'] = datetime.now().isoformat()

        # 更新挑战统计
        total_questions = len(challenge_results)
        correct_answers = sum(1 for r in challenge_results if r.get('is_correct', False))

        challenge_data['challenge_stats']['total_challenges'] += 1
        challenge_data['challenge_stats']['total_correct'] += correct_answers
        challenge_data['challenge_stats']['total_questions'] += total_questions
        challenge_data['challenge_stats']['last_challenge'] = datetime.now().isoformat()

        # 保存数据
        save_user_challenge_data(user_id, challenge_data)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/vocabulary_audio/<word_id>')
def serve_vocabulary_audio(word_id):
    """提供单词音频文件"""
    try:
        # 在各个分类目录中查找音频文件
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)
            audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
            if os.path.exists(audio_path):
                return send_from_directory(category_audio_dir, f"{word_id}.mp3")
        
        return jsonify({'error': '音频文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/vocabulary/regenerate_audio/<word_id>', methods=['POST'])
def regenerate_vocabulary_audio(word_id):
    """重新生成单词音频"""
    try:
        # 查找单词
        target_word = None
        target_category = None
        target_subcategory = None
        
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_data = load_category_data(category)
            for subcategory_id in category_data['subcategories']:
                for word_obj in category_data['subcategories'][subcategory_id]['words']:
                    if word_obj['id'] == word_id:
                        target_word = word_obj
                        target_category = category
                        target_subcategory = subcategory_id
                        break
                if target_word:
                    break
            if target_word:
                break
        
        if not target_word:
            return jsonify({'success': False, 'error': '单词不存在'}), 404
        
        # 添加到音频生成任务队列
        add_audio_task(word_id, target_word['word'], target_category, target_subcategory)
        
        return jsonify({'success': True, 'message': '音频重新生成任务已添加到队列'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 用户完成状态管理 ====================

import os
import json
from functools import wraps

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), 'user_data')

def get_user_data_file(username):
    """获取用户数据文件路径"""
    if not username:
        return None
    return os.path.join(USER_DATA_DIR, f"{username}_completed.json")

def load_user_completed_status(username):
    """加载用户的完成状态"""
    if not username:
        return {}

    file_path = get_user_data_file(username)
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_user_completed_status(username, completed_items):
    """保存用户的完成状态"""
    if not username:
        return False

    # 确保用户数据目录存在
    os.makedirs(USER_DATA_DIR, exist_ok=True)

    file_path = get_user_data_file(username)
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(completed_items, f, ensure_ascii=False, indent=2)
        return True
    except:
        return False

def require_auth(f):
    """装饰器：要求认证"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid token'}), 401

        token = auth_header.split(' ')[1]
        username = verify_token_get_username(token)
        if not username:
            return jsonify({'error': 'Invalid token'}), 401

        # 将username添加到request对象中
        request.username = username
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/user/completed_status', methods=['GET'])
@require_auth
def get_user_completed_status():
    """获取用户的完成状态"""
    username = request.username
    completed_items = load_user_completed_status(username)
    return jsonify({
        'success': True,
        'completed_items': completed_items
    })

@app.route('/api/user/completed_status', methods=['POST'])
@require_auth
def update_user_completed_status():
    """更新用户的完成状态"""
    username = request.username
    data = request.json

    if not data or 'completed_items' not in data:
        return jsonify({'success': False, 'error': 'Missing completed_items'}), 400

    completed_items = data['completed_items']

    # 验证数据格式
    if not isinstance(completed_items, dict):
        return jsonify({'success': False, 'error': 'Invalid data format'}), 400

    success = save_user_completed_status(username, completed_items)
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to save data'}), 500

@app.route('/api/user/info', methods=['GET'])
@require_auth
def get_user_info():
    """获取用户信息"""
    username = request.username
    users = load_users()

    if username in users:
        user_data = users[username]
        return jsonify({
            'success': True,
            'user': {
                'username': user_data.get('username'),
                'display_name': user_data.get('display_name'),
                'role': user_data.get('role'),
                'avatar': user_data.get('avatar')
            }
        })
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404

# ====== 学习技巧功能 ======

@app.route('/study_techniques')
def study_techniques_page():
    """学习技巧页面"""
    return send_file('templates/study_techniques.html')

def load_study_data(category, data_type):
    """加载学习技巧数据"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return []
    return []

def save_study_data(category, data_type, data):
    """保存学习技巧数据"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}")
        return False

def generate_id():
    """生成唯一ID"""
    return str(uuid.uuid4())

# 同义词替换API - 重新排序路由，确保DELETE路由能正确匹配
@app.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['PUT'])
def update_synonym(category, item_id):
    """更新同义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        synonyms = data.get('synonyms', [])
        title = data.get('title')

        if not synonyms:
            return jsonify({'error': 'At least one synonym is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['synonyms'] = synonyms
                if title is not None:
                    if title:
                        item['title'] = title
                    elif 'title' in item:
                        del item['title']
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'synonyms', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error updating synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['DELETE'])
def delete_synonym(category, item_id):
    """删除同义词"""
    print(f"DELETE request received for synonym: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')
        print(f"Loaded {len(existing_data)} synonyms for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'synonyms', updated_data):
            print(f"Successfully deleted synonym: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error deleting synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/study_techniques/synonyms/<category>', methods=['GET'])
def get_synonyms(category):
    """获取同义词数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    data = load_study_data(category, 'synonyms')
    return jsonify(data)

@app.route('/api/study_techniques/synonyms/<category>', methods=['POST'])
def add_synonym(category):
    """添加同义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        synonyms = data.get('synonyms', [])
        title = data.get('title')

        if not synonyms:
            return jsonify({'error': 'At least one synonym is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'synonyms': synonyms,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        if title:
            new_entry['title'] = title

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'synonyms', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error adding synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 上下义词API - 重新排序路由，确保DELETE路由能正确匹配
@app.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['PUT'])
def update_hypernym(category, item_id):
    """更新上下义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        upper_words = data.get('upper_words', [])
        lower_words = data.get('lower_words', [])
        title = data.get('title')

        if not upper_words and not lower_words:
            return jsonify({'error': 'At least one upper or lower word is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['upper_words'] = upper_words
                item['lower_words'] = lower_words
                if title is not None:
                    if title:
                        item['title'] = title
                    elif 'title' in item:
                        del item['title']
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'hypernyms', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error updating hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['DELETE'])
def delete_hypernym(category, item_id):
    """删除上下义词"""
    print(f"DELETE request received for hypernym: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')
        print(f"Loaded {len(existing_data)} hypernyms for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'hypernyms', updated_data):
            print(f"Successfully deleted hypernym: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error deleting hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/study_techniques/hypernyms/<category>', methods=['GET'])
def get_hypernyms(category):
    """获取上下义词数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    data = load_study_data(category, 'hypernyms')
    return jsonify(data)

@app.route('/api/study_techniques/hypernyms/<category>', methods=['POST'])
def add_hypernym(category):
    """添加上下义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        upper_words = data.get('upper_words', [])
        lower_words = data.get('lower_words', [])
        title = data.get('title')

        if not upper_words and not lower_words:
            return jsonify({'error': 'At least one upper or lower word is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'upper_words': upper_words,
            'lower_words': lower_words,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        if title:
            new_entry['title'] = title

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'hypernyms', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error adding hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 做题技巧API - 重新排序路由，确保DELETE路由能正确匹配
@app.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['PUT'])
def update_technique(category, item_id):
    """更新做题技巧"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['title'] = title
                item['content'] = content
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'techniques', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error updating technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['DELETE'])
def delete_technique(category, item_id):
    """删除做题技巧"""
    print(f"DELETE request received for technique: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')
        print(f"Loaded {len(existing_data)} techniques for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'techniques', updated_data):
            print(f"Successfully deleted technique: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error deleting technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500
@app.route('/api/study_techniques/techniques/<category>', methods=['GET'])
def get_techniques(category):
    """获取做题技巧数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    data = load_study_data(category, 'techniques')
    return jsonify(data)

@app.route('/api/study_techniques/techniques/<category>', methods=['POST'])
def add_technique(category):
    """添加做题技巧"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'title': title,
            'content': content,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'techniques', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except Exception as e:
        print(f"Error adding technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500


def verify_token_from_request():
    """从请求中验证token"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return False
    
    token = auth_header.split(' ')[1]
    return is_token_valid(token)

# ==================== 音频转文本相关API ====================

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

@app.route('/audio_transcription')
def audio_transcription_page():
    """音频转文本页面"""
    return send_file('templates/audio_transcription.html')

@app.route('/api/audio_transcription/upload', methods=['POST'])
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

@app.route('/api/audio_transcription/list', methods=['GET'])
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

@app.route('/api/audio_transcription/audio/<transcription_id>/<filename>')
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

@app.route('/api/audio_transcription/retranscribe/<transcription_id>', methods=['POST'])
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

@app.route('/api/audio_transcription/delete/<transcription_id>', methods=['DELETE'])
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

# ===================== 写作批改模块 =====================

WRITING_CORRECTION_DIR = 'writing_correction'
WRITING_DATA_DIR = 'writing_correction/data'
WRITING_MD_FILE = 'writing_correction/resource/九分学长雅思写作论证块.md'
os.makedirs(WRITING_DATA_DIR, exist_ok=True)

_writing_cache = None

def _has_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def _parse_writing_md():
    global _writing_cache
    if _writing_cache is not None:
        return _writing_cache
    with open(WRITING_MD_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    categories = []
    cur_cat = cur_sub = cur_chain = cur_example = None
    section = example_phase = None
    for raw in lines:
        s = raw.strip()
        if s.startswith('<div'):
            continue
        if s.startswith('# ') and not s.startswith('## '):
            continue
        if s.startswith('## ') and not s.startswith('### '):
            cur_cat = {'name': s[3:].strip(), 'subcategories': []}
            categories.append(cur_cat)
            cur_sub = section = None
            continue
        if s.startswith('### ') and not s.startswith('#### '):
            cur_sub = {'name': s[4:].strip(), 'keywords': [], 'chains': [], 'examples': []}
            if cur_cat:
                cur_cat['subcategories'].append(cur_sub)
            section = cur_example = None
            continue
        if s.startswith('#### ') and not s.startswith('##### '):
            h = s[5:].strip()
            if '关键词' in h:
                section = 'kw'
            elif '逻辑链' in h:
                section = 'ch'
                cur_chain = None
            elif '细节' in h or '举例' in h:
                section = 'ex'
            continue
        if s.startswith('##### '):
            cur_example = {'title': s[6:].strip(), 'question': '', 'hints': [], 'sentences': []}
            if cur_sub:
                cur_sub['examples'].append(cur_example)
            example_phase = 'question'
            continue
        if not s or not cur_sub:
            continue
        if section == 'kw':
            if s.startswith('- '):
                cur_sub['keywords'].append(s[2:].strip())
        elif section == 'ch':
            m = re.match(r'^链\s*(\d+)', s)
            if m:
                cur_chain = {'id': int(m.group(1)), 'chinese': '', 'english': ''}
                cur_sub['chains'].append(cur_chain)
            elif s.startswith('- ') and cur_chain:
                t = s[2:].strip()
                if _has_chinese(t):
                    cur_chain['chinese'] = t
                else:
                    cur_chain['english'] = t
        elif section == 'ex' and cur_example:
            if example_phase == 'question':
                if s.startswith('使用'):
                    example_phase = 'hints'
                    cur_example['hints'].append(s)
                else:
                    cur_example['question'] = (cur_example['question'] + ' ' + s).strip()
            elif example_phase == 'hints':
                if s.startswith('- 使用') or s.startswith('- 写作') or s.startswith('使用'):
                    cur_example['hints'].append(s)
                else:
                    example_phase = 'sentences'
                    if _has_chinese(s):
                        if cur_example['sentences'] and not cur_example['sentences'][-1].get('chinese'):
                            cur_example['sentences'][-1]['chinese'] = s
                    else:
                        cur_example['sentences'].append({'english': s, 'chinese': ''})
            elif example_phase == 'sentences':
                if _has_chinese(s):
                    if cur_example['sentences'] and not cur_example['sentences'][-1].get('chinese'):
                        cur_example['sentences'][-1]['chinese'] = s
                else:
                    cur_example['sentences'].append({'english': s, 'chinese': ''})
    _writing_cache = categories
    return categories


@app.route('/writing_practice')
def writing_practice_page():
    return send_file('templates/writing_practice.html')


@app.route('/api/writing/categories', methods=['GET'])
def writing_categories():
    cats = _parse_writing_md()
    result = []
    for ci, c in enumerate(cats):
        subs = [{'index': si, 'name': s['name'], 'keyword_count': len(s['keywords']),
                 'chain_count': len(s['chains']), 'example_count': len(s['examples'])}
                for si, s in enumerate(c['subcategories'])]
        result.append({'index': ci, 'name': c['name'], 'subcategories': subs})
    return jsonify(result)


@app.route('/api/writing/subcategory/<int:cat_idx>/<int:sub_idx>', methods=['GET'])
def writing_subcategory(cat_idx, sub_idx):
    cats = _parse_writing_md()
    if cat_idx >= len(cats):
        return jsonify({'error': 'Category not found'}), 404
    cat = cats[cat_idx]
    if sub_idx >= len(cat['subcategories']):
        return jsonify({'error': 'Subcategory not found'}), 404
    sub = cat['subcategories'][sub_idx]
    return jsonify({'category': cat['name'], **sub})


@app.route('/api/writing/correct', methods=['POST'])
def writing_correct():
    data = request.json or {}
    question = data.get('question_text', '')
    target = data.get('target_chinese', '')
    translation = data.get('user_translation', '')
    if not translation.strip():
        return jsonify({'error': '翻译内容不能为空'}), 400

    system_prompt = (
        "你是一位精通中英双语的雅思前考官。任务是评估用户的英文翻译，并按雅思写作标准（TR, CC, LR, GRA）进行批改。\n\n"
        "评估重点：\n1. 语法与拼写准确性。\n2. 词汇多样性与地道程度。\n3. 句间逻辑连贯性。\n\n"
        "【强制要求】\n必须且仅以纯 JSON 格式输出，不要包含 Markdown 符号或额外解释，结构如下：\n"
        '{"score":"预估单句分数 (如 5.5, 6.0, 6.5)",'
        '"feedback_summary":"一句话核心评价",'
        '"grammar_corrections":[{"original":"原词","corrected":"修改后","reason":"原因"}],'
        '"vocabulary_upgrade":"1-2个高阶替换建议及中文解释",'
        '"native_version":"符合高分水平的完美示范译文"}'
    )
    user_prompt = (
        f"【雅思例题】\n{question}\n\n"
        f"【目标中文句】\n{target}\n\n"
        f"【用户英文翻译】\n{translation}"
    )
    try:
        api_key = os.getenv('DEER_API_KEY')
        resp = requests.post(
            'https://api.deerapi.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.3
            },
            timeout=30
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        result = json.loads(content)
        return jsonify(result)
    except requests.exceptions.Timeout:
        return jsonify({'error': 'AI 服务超时，请重试'}), 504
    except json.JSONDecodeError:
        return jsonify({'error': 'AI 返回格式异常', 'raw': content}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _practice_path(username):
    return os.path.join(WRITING_DATA_DIR, f'{username}_practice.json')

def _load_practice(username):
    p = _practice_path(username)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def _save_practice(username, data):
    with open(_practice_path(username), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.route('/api/writing/save_practice', methods=['POST'])
def writing_save_practice():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    data = request.json or {}
    records = _load_practice(username)
    record = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'category': data.get('category', ''),
        'subcategory': data.get('subcategory', ''),
        'question': data.get('question', ''),
        'target_chinese': data.get('target_chinese', ''),
        'user_translation': data.get('user_translation', ''),
        'score': data.get('score', ''),
        'feedback': data.get('feedback', {}),
        'native_version': data.get('native_version', '')
    }
    records.insert(0, record)
    _save_practice(username, records)
    return jsonify({'success': True, 'id': record['id']})


@app.route('/api/writing/practice_history', methods=['GET'])
def writing_practice_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_practice(username)
    return jsonify(records)


@app.route('/api/writing/delete_practice/<record_id>', methods=['POST'])
def writing_delete_practice(record_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_practice(username)
    records = [r for r in records if r['id'] != record_id]
    _save_practice(username, records)
    return jsonify({'success': True})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
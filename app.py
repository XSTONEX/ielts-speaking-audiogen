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
MESSAGE_BOARD_DIR = 'message_board'
MESSAGE_IMAGES_DIR = 'message_board/images'
CHALLENGES_DIR = 'challenges'
os.makedirs(MOTHER_DIR, exist_ok=True)
os.makedirs(COMBINED_DIR, exist_ok=True)
os.makedirs(INTENSIVE_DIR, exist_ok=True)
os.makedirs(INTENSIVE_IMAGES_DIR, exist_ok=True)
os.makedirs(VOCAB_AUDIO_DIR, exist_ok=True)
os.makedirs(MESSAGE_BOARD_DIR, exist_ok=True)
os.makedirs(MESSAGE_IMAGES_DIR, exist_ok=True)
os.makedirs(CHALLENGES_DIR, exist_ok=True)

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
        token = create_token()
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

def generate_tts_segment(text, temp_dir, segment_index):
    """生成单个文本段的TTS音频"""
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
        segment_path = os.path.join(temp_dir, f"segment_{segment_index:03d}.mp3")
        with open(segment_path, 'wb') as f:
            f.write(response.content)
        return segment_path
    else:
        raise Exception(f'TTS API错误: {response.status_code}')

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
                # 清理临时文件
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
        
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
        
        # 清理任务目录
        if os.path.exists(task_dir):
            shutil.rmtree(task_dir)
        
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
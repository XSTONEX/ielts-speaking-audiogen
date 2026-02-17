"""
公共依赖模块 - 全局常量、目录初始化、认证函数、TTS 基础函数、词汇音频工具函数
"""

import os
import json
import secrets
import hashlib
import shutil
import threading
import requests
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify
from dotenv import load_dotenv

load_dotenv()

# ==================== 全局常量 ====================

MOTHER_DIR = 'audio_files'
COMBINED_DIR = 'combined_audio'
TOKEN_FILE = 'tokens.json'
USERS_FILE = 'users.json'
READING_DIR = 'reading_exam'
INTENSIVE_DIR = 'intensive_articles'
INTENSIVE_IMAGES_DIR = 'intensive_articles/images'
VOCAB_AUDIO_DIR = 'vocab_audio'
VOCABULARY_BOOK_DIR = 'vocabulary_book'
VOCABULARY_CATEGORIES_DIR = 'vocabulary_book/categories'
VOCABULARY_AUDIO_DIR = 'vocabulary_book/audio'
VOCABULARY_TASKS_DIR = 'vocabulary_book/tasks'
VOCABULARY_CHALLENGE_DIR = 'vocabulary_book/challenges'
MESSAGE_BOARD_DIR = 'message_board'
MESSAGE_IMAGES_DIR = 'message_board/images'
CHALLENGES_DIR = 'challenges'
STUDY_TECHNIQUES_DIR = 'study_techniques'
STUDY_TECHNIQUES_DATA_DIR = 'study_techniques/data'
STUDY_TECHNIQUES_AUDIO_DIR = 'study_techniques/audio'
AUDIO_TRANSCRIPTION_DIR = 'audio_transcriptions'
USER_DATA_DIR = os.path.join(os.path.dirname(__file__), 'user_data')
WRITING_CORRECTION_DIR = 'writing_correction'
WRITING_DATA_DIR = 'writing_correction/data'
WRITING_MD_FILE = 'writing_correction/resource/九分学长雅思写作论证块.md'
LISTENING_REVIEW_DIR = 'listening_review'


# ==================== 目录初始化 ====================

def init_directories():
    """初始化所有必要的目录"""
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
    os.makedirs(WRITING_DATA_DIR, exist_ok=True)
    os.makedirs(LISTENING_REVIEW_DIR, exist_ok=True)


# ==================== Token 管理 ====================

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


# ==================== 用户管理 ====================

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


# ==================== 认证辅助函数 ====================

def verify_token_get_username(token):
    """从token中获取用户名"""
    if not token or not is_token_valid(token):
        return None

    tokens = load_tokens()
    return tokens.get(token, {}).get('username')

def verify_token_from_request():
    """从请求中验证token"""
    auth_header = request.headers.get('Authorization')
    if not auth_header or not auth_header.startswith('Bearer '):
        return False

    token = auth_header.split(' ')[1]
    return is_token_valid(token)

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


# ==================== TTS 基础函数 ====================

def generate_tts(text, folder):
    """生成 TTS 音频并保存到指定文件夹"""
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


# ==================== 词汇音频工具函数 ====================

def get_vocab_audio_path(article_id, word):
    """获取词汇音频文件路径"""
    article_audio_dir = os.path.join(VOCAB_AUDIO_DIR, article_id)
    os.makedirs(article_audio_dir, exist_ok=True)

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

            for item in os.listdir(article_audio_dir):
                item_path = os.path.join(article_audio_dir, item)

                if os.path.isfile(item_path):
                    if item.endswith(('.mp3', '.txt')):
                        os.remove(item_path)
                        deleted_files.append(item)
                elif os.path.isdir(item_path):
                    if item.startswith('audio_') or item.startswith('temp_'):
                        shutil.rmtree(item_path)
                        deleted_dirs.append(item)

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

    thread = threading.Thread(target=_generate, daemon=True)
    thread.start()

def generate_challenge_vocab_audio(challenge_id, word):
    """为挑战生成词汇音频（使用challenge_id作为文章ID）"""
    return generate_and_save_vocab_audio(f"challenge_{challenge_id}", word)

import os
import json
import uuid
import shutil
import random
import hashlib
import requests
import time
import threading
from datetime import datetime
from collections import defaultdict
from werkzeug.utils import secure_filename

from flask import Blueprint, request, jsonify, send_file, send_from_directory

from core import (
    MOTHER_DIR, COMBINED_DIR, INTENSIVE_DIR,
    MESSAGE_BOARD_DIR, MESSAGE_IMAGES_DIR,
    CHALLENGES_DIR, VOCABULARY_CHALLENGE_DIR,
    is_token_valid, load_tokens, load_users,
    verify_token_get_username,
    delete_article_vocab_audio, generate_challenge_vocab_audio,
    get_vocab_audio_path
)
from routers.intensive_reading import _article_path

community_bp = Blueprint('community', __name__)

# ==================== 留言板相关辅助函数 ====================

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

# ==================== 留言板路由 ====================

@community_bp.route('/message_board')
def message_board_page():
    return send_file('templates/message_board.html')

@community_bp.route('/api/messages', methods=['GET'])
def get_messages():
    """获取所有留言，按时间倒序"""
    try:
        messages = load_messages()
        # 按时间倒序排列（最新的在前面）
        messages.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return jsonify({'success': True, 'messages': messages})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@community_bp.route('/api/messages', methods=['POST'])
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

@community_bp.route('/api/messages/<message_id>', methods=['DELETE'])
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

@community_bp.route('/api/upload_message_image', methods=['POST'])
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

# ==================== 图片处理辅助函数 ====================

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

@community_bp.route('/message_images/<path:filename>')
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

@community_bp.route('/api/comments/<post_id>', methods=['GET'])
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

@community_bp.route('/api/comments', methods=['POST'])
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

@community_bp.route('/api/comments/<comment_id>', methods=['DELETE'])
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

# ==================== 分享相关API ====================

@community_bp.route('/api/get_audio_list', methods=['GET'])
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

@community_bp.route('/api/get_articles_list', methods=['GET'])
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

@community_bp.route('/api/get_users_list', methods=['GET'])
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

# ==================== 挑战系统相关API ====================

def _challenge_file(challenge_id):
    """获取挑战文件路径"""
    return os.path.join(CHALLENGES_DIR, f"{challenge_id}.json")

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

def extract_vocabulary_from_articles_improved(article_ids, word_count):
    """改进的词汇提取算法，专为词汇汇总挑战优化"""
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

@community_bp.route('/api/create_challenge', methods=['POST'])
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

@community_bp.route('/api/get_challenge/<challenge_id>', methods=['GET'])
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

@community_bp.route('/api/participate_challenge', methods=['POST'])
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

@community_bp.route('/api/get_challenge_ranking/<challenge_id>', methods=['GET'])
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

@community_bp.route('/api/vocab_summary_challenge', methods=['POST'])
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

@community_bp.route('/api/vocab_challenge_record', methods=['POST'])
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

@community_bp.route('/api/vocab_challenge_records', methods=['GET'])
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

@community_bp.route('/api/vocab_wrong_words', methods=['POST'])
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

@community_bp.route('/api/vocab_wrong_words', methods=['GET'])
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

@community_bp.route('/api/cleanup_orphaned_challenges', methods=['POST'])
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

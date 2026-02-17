from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json, re, uuid, shutil, time, requests
from datetime import datetime
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from urllib.parse import unquote

from core import (
    INTENSIVE_DIR, INTENSIVE_IMAGES_DIR, VOCAB_AUDIO_DIR,
    generate_tts, generate_token, get_vocab_audio_path,
    generate_and_save_vocab_audio, delete_vocab_audio,
    delete_article_vocab_audio, delete_article_audio_files,
    generate_vocab_audio_async
)

intensive_reading_bp = Blueprint('intensive_reading', __name__)

# ------------------------
# Helper functions
# ------------------------

def _safe_article_id(title: str) -> str:
    base = re.sub(r"[^\w\-]+", "-", title.strip())[:60].strip('-') or 'article'
    ts = datetime.now().strftime('%Y%m%d%H%M%S')
    return f"{ts}-{base}"

def _article_path(article_id: str) -> str:
    return os.path.join(INTENSIVE_DIR, f"{article_id}.json")

def _allowed_file(filename):
    """检查文件类型是否允许"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def split_text_intelligently(text, target_segments=None, max_chars=2200):
    """
    智能分割文本，确保句子完整性和均匀分配
    :param text: 要分割的文本
    :param target_segments: 目标分段数量，如果指定则平均分割
    :param max_chars: 每段最大字符数
    """
    if len(text) <= max_chars:
        return [text]

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
                # 指数退避：等待 2^attempt 秒
                wait_time = 2 ** attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        except requests.exceptions.RequestException as e:
            last_error = f"网络请求错误: {str(e)}"
            print(f"分片 {segment_index} 第 {attempt + 1} 次尝试网络错误: {last_error}")
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
        except Exception as e:
            last_error = str(e)
            print(f"分片 {segment_index} 第 {attempt + 1} 次尝试出错: {last_error}")
            if attempt < max_retries - 1:
                wait_time = 1 + attempt
                print(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)

    # 所有重试都失败了
    raise Exception(f'分片 {segment_index} 生成失败，已重试 {max_retries} 次。最后错误: {last_error}')

# ------------------------
# Routes
# ------------------------

@intensive_reading_bp.route('/intensive')
def intensive_page():
    return send_file('templates/intensive.html')

@intensive_reading_bp.route('/vocab_summary')
def vocab_summary():
    return send_file('templates/vocab_summary.html')

@intensive_reading_bp.route('/test_pronunciation')
def test_pronunciation():
    """单词发音功能测试页面"""
    return send_file('test_pronunciation.html')

@intensive_reading_bp.route('/intensive/new')
def intensive_new_page():
    return send_file('templates/intensive_new.html')

@intensive_reading_bp.route('/intensive_list', methods=['GET'])
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

@intensive_reading_bp.route('/intensive_create', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_article/<article_id>', methods=['GET'])
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

@intensive_reading_bp.route('/intensive_add_highlight', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_delete_highlight', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_update_category', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_delete_article', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_upload_image', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_image/<article_id>/<filename>')
def serve_intensive_image(article_id, filename):
    """提供精读文章图片文件"""
    return send_from_directory(os.path.join(INTENSIVE_IMAGES_DIR, article_id), filename)

@intensive_reading_bp.route('/intensive_delete_image', methods=['POST'])
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

@intensive_reading_bp.route('/intensive_update_title', methods=['POST'])
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

@intensive_reading_bp.route('/vocab_audio/<article_id>/<word>')
def get_vocab_audio(article_id, word):
    """获取词汇音频文件"""
    # URL解码单词
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

@intensive_reading_bp.route('/vocab_audio/articles/<article_id>/<filename>')
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

@intensive_reading_bp.route('/generate_article_audio', methods=['POST'])
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

@intensive_reading_bp.route('/prepare_article_audio', methods=['POST'])
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

@intensive_reading_bp.route('/generate_audio_segment', methods=['POST'])
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

@intensive_reading_bp.route('/check_segment_status', methods=['POST'])
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

@intensive_reading_bp.route('/combine_audio_segments', methods=['POST'])
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

@intensive_reading_bp.route('/find_unfinished_audio_tasks/<article_id>')
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

@intensive_reading_bp.route('/cleanup_article_audio', methods=['POST'])
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

@intensive_reading_bp.route('/check_article_audio/<article_id>', methods=['GET'])
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

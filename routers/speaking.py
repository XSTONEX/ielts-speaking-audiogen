from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json, shutil
from core import (MOTHER_DIR, generate_tts, is_safe_path_segment,
                  get_audio_duration, flush_duration_cache)

speaking_bp = Blueprint('speaking', __name__)

@speaking_bp.route('/speaking')
def speaking_page():
    return send_file('templates/speaking.html')

@speaking_bp.route('/generate_audio', methods=['POST'])
def generate_audio():
    data = request.json
    text = data.get('text')
    folder = data.get('folder')
    question = data.get('question')
    if not text or not folder:
        return jsonify({'error': 'Missing text or folder'}), 400
    if not is_safe_path_segment(folder):
        return jsonify({'error': 'Invalid folder name'}), 400
    # PART2 生成时写入 question.txt
    if folder.startswith('P2') and question:
        folder_path = os.path.join(MOTHER_DIR, folder)
        os.makedirs(folder_path, exist_ok=True)
        question_file = os.path.join(folder_path, 'question.txt')
        with open(question_file, 'w', encoding='utf-8') as f:
            f.write(question.strip())
    try:
        folder, filename = generate_tts(text, folder)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    return jsonify({'folder': folder, 'filename': filename})

@speaking_bp.route('/list_audio', methods=['GET'])
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
                # Part1/Part3 的文本首行是问题、其余是答案；Part2 和「其他」整篇都是答案。
                # 摘要只取答案部分，列表行才不会全是同一句问题。
                q_on_first_line = folder.startswith('P1') or folder.startswith('P3')
                files_info = []
                for f in files:
                    path = os.path.join(folder_path, f)
                    ctime = os.path.getctime(path)
                    # 读取 question（第一行）与正文摘要。Part1/Part3 的首行是问题，
                    # 剩下才是答案；Part2 整篇都是答案。摘要给列表行做一句话预览用。
                    txt_path = os.path.join(folder_path, f.replace('.mp3', '.txt'))
                    question = None
                    preview = None
                    if os.path.exists(txt_path):
                        try:
                            with open(txt_path, 'r', encoding='utf-8') as tf:
                                content = tf.read()
                            lines = content.split('\n', 1)
                            question = lines[0].strip()
                            if q_on_first_line and len(lines) > 1 and lines[1].strip():
                                body = lines[1]
                            else:
                                body = content
                            preview = ' '.join(body.split())[:140]
                        except Exception:
                            question = None
                    files_info.append({
                        'name': f,
                        'ctime': ctime,
                        'question': question,
                        'preview': preview,
                        'duration': get_audio_duration(folder, f),
                    })
                files_info.sort(key=lambda x: x['ctime'])
                folder_time = files_info[0]['ctime']
                folder_obj = {
                    'folder': folder,
                    'ctime': folder_time,
                    # latest 给「最近使用」排序；ctime 保持原语义（最早一条）不动，
                    # combined.html 和留言板页还在用它。
                    'latest': files_info[-1]['ctime'],
                    'duration': round(sum(x['duration'] for x in files_info), 2),
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
    flush_duration_cache()
    return jsonify(categories)

@speaking_bp.route('/list_folders', methods=['GET'])
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

# 音频文件名里带生成时间戳，内容一旦写入就不会再变，可以放心长缓存。
# 默认的 Cache-Control: no-cache 会让浏览器每次播放前都回源校验一次，
# 手机网络下这一个往返就是每句话开头的卡顿；缓存被淘汰时更是整段重下。
AUDIO_CACHE_SECONDS = 31536000  # 1 年


@speaking_bp.route('/audio/<folder>/<filename>')
def serve_audio(folder, filename):
    if not is_safe_path_segment(folder):
        return jsonify({'error': 'Invalid folder name'}), 400
    resp = send_from_directory(
        os.path.join(MOTHER_DIR, folder), filename,
        max_age=AUDIO_CACHE_SECONDS, conditional=True,
    )
    resp.headers['Cache-Control'] = f'public, max-age={AUDIO_CACHE_SECONDS}, immutable'
    # Werkzeug 会响应 206，却不主动声明 Accept-Ranges；
    # 部分移动端播放器据此判断能否边下边播，缺了它就会先整段下载再出声。
    resp.headers.setdefault('Accept-Ranges', 'bytes')
    return resp

@speaking_bp.route('/text/<folder>/<filename>')
def get_text(folder, filename):
    if not is_safe_path_segment(folder) or not is_safe_path_segment(filename):
        return jsonify({'error': 'Invalid path'}), 400
    txt_filename = filename.replace('.mp3', '.txt')
    txt_path = os.path.join(MOTHER_DIR, folder, txt_filename)
    if not os.path.exists(txt_path):
        return jsonify({'error': 'Text file not found'}), 404
    with open(txt_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return jsonify({'text': content})

@speaking_bp.route('/delete_folder', methods=['POST'])
def delete_folder():
    data = request.json
    folder = data.get('folder')
    if not folder:
        return jsonify({'error': 'Missing folder'}), 400
    if not is_safe_path_segment(folder):
        return jsonify({'error': 'Invalid folder name'}), 400
    folder_path = os.path.join(MOTHER_DIR, folder)
    if not os.path.exists(folder_path):
        return jsonify({'error': 'Folder not found'}), 404
    try:
        shutil.rmtree(folder_path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@speaking_bp.route('/delete_audio', methods=['POST'])
def delete_audio():
    data = request.json
    folder = data.get('folder')
    filename = data.get('filename')
    if not folder or not filename:
        return jsonify({'error': 'Missing folder or filename'}), 400
    if not is_safe_path_segment(folder) or not is_safe_path_segment(filename):
        return jsonify({'error': 'Invalid path'}), 400
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

@speaking_bp.route('/set_part2_question', methods=['POST'])
def set_part2_question():
    data = request.json
    folder = data.get('folder')
    question = data.get('question')
    if not folder or not question:
        return jsonify({'error': 'Missing folder or question'}), 400
    if not is_safe_path_segment(folder):
        return jsonify({'error': 'Invalid folder name'}), 400
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

@speaking_bp.route('/has_part2_question')
def has_part2_question():
    folder = request.args.get('folder')
    if not folder or not folder.startswith('P2'):
        return jsonify({'exists': False})
    folder_path = os.path.join(MOTHER_DIR, folder)
    question_file = os.path.join(folder_path, 'question.txt')
    exists = os.path.exists(question_file)
    return jsonify({'exists': exists})


@speaking_bp.route('/search_audio')
def search_audio():
    """在所有音频的英文原文里做全文检索。

    话题名的过滤前端拿已加载的列表就能做，不必回服务器；但 319 条原文
    加起来有几百 KB，全塞进 /list_audio 会把首屏拖慢，所以单独开一个接口，
    输入时防抖调用。
    """
    query = (request.args.get('q') or '').strip()
    if len(query) < 2:
        return jsonify({'query': query, 'results': []})
    needle = query.lower()
    results = []
    limit = 60
    for folder in sorted(os.listdir(MOTHER_DIR)):
        folder_path = os.path.join(MOTHER_DIR, folder)
        if not os.path.isdir(folder_path) or folder.startswith('.'):
            continue
        for name in sorted(os.listdir(folder_path)):
            if not name.endswith('.txt') or name == 'question.txt':
                continue
            audio_name = name[:-4] + '.mp3'
            if not os.path.exists(os.path.join(folder_path, audio_name)):
                continue
            try:
                with open(os.path.join(folder_path, name), 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue
            pos = content.lower().find(needle)
            if pos < 0:
                continue
            flat = ' '.join(content.split())
            flat_pos = flat.lower().find(needle)
            if flat_pos < 0:
                flat_pos = 0
            start = max(0, flat_pos - 50)
            snippet = flat[start:flat_pos + len(query) + 90]
            results.append({
                'folder': folder,
                'filename': audio_name,
                'snippet': ('…' if start > 0 else '') + snippet + ('…' if len(flat) > flat_pos + len(query) + 90 else ''),
            })
            if len(results) >= limit:
                return jsonify({'query': query, 'results': results, 'truncated': True})
    return jsonify({'query': query, 'results': results, 'truncated': False})

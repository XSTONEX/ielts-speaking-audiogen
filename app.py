from flask import Flask, request, jsonify, send_from_directory, send_file
import os
import requests
import json
from datetime import datetime
import shutil
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)

MOTHER_DIR = 'audio_files'
os.makedirs(MOTHER_DIR, exist_ok=True)


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

@app.route('/')
def index():
    return send_file('index.html')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
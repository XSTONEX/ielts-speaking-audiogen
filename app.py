from flask import Flask, request, jsonify, send_from_directory, send_file
import os
import requests
import json
from datetime import datetime
import shutil
from dotenv import load_dotenv
from pydub import AudioSegment
load_dotenv()

app = Flask(__name__)

MOTHER_DIR = 'audio_files'
COMBINED_DIR = 'combined_audio'
os.makedirs(MOTHER_DIR, exist_ok=True)
os.makedirs(COMBINED_DIR, exist_ok=True)


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

@app.route('/get_password')
def get_password():
    password = os.getenv('PASSWORD')
    return jsonify({'password': password})

@app.route('/combined')
def combined_page():
    return send_file('combined.html')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json
from pydub import AudioSegment
from core import MOTHER_DIR, COMBINED_DIR

speaking_playlist_bp = Blueprint('speaking_playlist', __name__)

@speaking_playlist_bp.route('/combined')
def combined_page():
    return send_file('templates/combined.html')

@speaking_playlist_bp.route('/check_combined_audio')
def check_combined_audio():
    """检查哪些文件夹已经有合集音频"""
    existing_folders = []
    if os.path.exists(COMBINED_DIR):
        for file in os.listdir(COMBINED_DIR):
            if file.endswith('.mp3'):
                folder_name = file.replace('.mp3', '')
                existing_folders.append(folder_name)
    return jsonify({'folders': existing_folders})

@speaking_playlist_bp.route('/generate_combined_audio', methods=['POST'])
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

@speaking_playlist_bp.route('/combined_audio/<folder>')
def serve_combined_audio(folder):
    """提供合集音频文件"""
    return send_from_directory(COMBINED_DIR, f"{folder}.mp3")

@speaking_playlist_bp.route('/get_subtitles/<folder>')
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

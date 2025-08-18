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
load_dotenv()

app = Flask(__name__, static_folder='static', static_url_path='/static')

MOTHER_DIR = 'audio_files'
COMBINED_DIR = 'combined_audio'
TOKEN_FILE = 'tokens.json'
USERS_FILE = 'users.json'
READING_DIR = 'reading_exam'
INTENSIVE_DIR = 'intensive_articles'
os.makedirs(MOTHER_DIR, exist_ok=True)
os.makedirs(COMBINED_DIR, exist_ok=True)
os.makedirs(INTENSIVE_DIR, exist_ok=True)

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
        'highlights': []  # {id,start,end,meaning,created_at}
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
            'highlights': data.get('highlights') or []
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
        before = len(obj.get('highlights') or [])
        obj['highlights'] = [h for h in (obj.get('highlights') or []) if h.get('id') != highlight_id]
        after = len(obj['highlights'])
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
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
        os.remove(path)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
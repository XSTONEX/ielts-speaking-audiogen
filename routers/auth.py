import os
import json
from flask import Blueprint, request, jsonify, send_file
from core import (
    load_tokens, save_tokens, is_token_valid, create_token,
    load_users, save_users, authenticate_user,
    verify_token_get_username, require_auth, USER_DATA_DIR
)

auth_bp = Blueprint('auth', __name__)


# ====== Helper functions ======

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


# ====== Routes ======

@auth_bp.route('/')
def index():
    return send_file('templates/modules.html')

@auth_bp.route('/login')
def login_page():
    """登录页面"""
    return send_file('templates/login.html')

@auth_bp.route('/get_password')
def get_password():
    password = os.getenv('PASSWORD')
    return jsonify({'password': password})

@auth_bp.route('/verify_password', methods=['POST'])
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

@auth_bp.route('/verify_token', methods=['POST'])
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

@auth_bp.route('/user_login', methods=['POST'])
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

@auth_bp.route('/get_current_user', methods=['GET'])
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

@auth_bp.route('/api/user/completed_status', methods=['GET'])
@require_auth
def get_user_completed_status():
    """获取用户的完成状态"""
    username = request.username
    completed_items = load_user_completed_status(username)
    return jsonify({
        'success': True,
        'completed_items': completed_items
    })

@auth_bp.route('/api/user/completed_status', methods=['POST'])
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

@auth_bp.route('/api/user/info', methods=['GET'])
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

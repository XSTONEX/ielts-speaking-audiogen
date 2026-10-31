from flask import Blueprint, request, jsonify, send_file
import os, json, uuid, threading
from datetime import datetime
from functools import wraps

from core import STUDY_TECHNIQUES_DIR, STUDY_TECHNIQUES_DATA_DIR, STUDY_TECHNIQUES_AUDIO_DIR, verify_token_from_request
from utils.json_store import save_json_atomic

study_tips_bp = Blueprint('study_tips', __name__)

# 学习技巧的数据全站共用一份，谁登录都能改。读-改-写必须排队，否则两个人同时保存，
# 后存的会把先存的那条冲掉。服务是单进程多线程（python app.py），一把线程锁就够。
_study_data_lock = threading.Lock()


class StudyDataUnreadable(Exception):
    """数据文件读不出来（写坏了、不是列表）。不能当成空列表，否则下一次保存会把整份覆盖掉。"""


def load_study_data(category, data_type):
    """加载学习技巧数据。文件不存在算空列表；文件在但读不出来就报错，交给调用方拒绝写入"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    if not os.path.exists(file_path):
        return []
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise StudyDataUnreadable(f'{file_path}: {e}') from e
    if not isinstance(data, list):
        raise StudyDataUnreadable(f'{file_path}: expected a list, got {type(data).__name__}')
    return data

def save_study_data(category, data_type, data):
    """保存学习技巧数据：先写临时文件再整体替换，写到一半出错也不会留下半截文件"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    try:
        save_json_atomic(file_path, data)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}")
        return False

def _serialized(view):
    """写接口整段排队：读、改、存之间不让别的写请求插进来"""
    @wraps(view)
    def wrapper(*args, **kwargs):
        with _study_data_lock:
            return view(*args, **kwargs)
    return wrapper

def _unreadable_response(error):
    print(f"Study data unreadable: {error}")
    return jsonify({'error': 'Data file is unreadable'}), 500

def generate_id():
    """生成唯一ID"""
    return str(uuid.uuid4())


@study_tips_bp.route('/study_techniques')
def study_techniques_page():
    """学习技巧页面"""
    return send_file('templates/study_techniques.html')

# 同义词替换API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['PUT'])
@_serialized
def update_synonym(category, item_id):
    """更新同义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        synonyms = data.get('synonyms', [])
        title = data.get('title')

        if not synonyms:
            return jsonify({'error': 'At least one synonym is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['synonyms'] = synonyms
                if title is not None:
                    if title:
                        item['title'] = title
                    elif 'title' in item:
                        del item['title']
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'synonyms', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error updating synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['DELETE'])
@_serialized
def delete_synonym(category, item_id):
    """删除同义词"""
    print(f"DELETE request received for synonym: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')
        print(f"Loaded {len(existing_data)} synonyms for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'synonyms', updated_data):
            print(f"Successfully deleted synonym: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error deleting synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/synonyms/<category>', methods=['GET'])
def get_synonyms(category):
    """获取同义词数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = load_study_data(category, 'synonyms')
    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/synonyms/<category>', methods=['POST'])
@_serialized
def add_synonym(category):
    """添加同义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        synonyms = data.get('synonyms', [])
        title = data.get('title')

        if not synonyms:
            return jsonify({'error': 'At least one synonym is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'synonyms')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'synonyms': synonyms,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        if title:
            new_entry['title'] = title

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'synonyms', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error adding synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 上下义词API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['PUT'])
@_serialized
def update_hypernym(category, item_id):
    """更新上下义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        upper_words = data.get('upper_words', [])
        lower_words = data.get('lower_words', [])
        title = data.get('title')

        if not upper_words and not lower_words:
            return jsonify({'error': 'At least one upper or lower word is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['upper_words'] = upper_words
                item['lower_words'] = lower_words
                if title is not None:
                    if title:
                        item['title'] = title
                    elif 'title' in item:
                        del item['title']
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'hypernyms', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error updating hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['DELETE'])
@_serialized
def delete_hypernym(category, item_id):
    """删除上下义词"""
    print(f"DELETE request received for hypernym: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')
        print(f"Loaded {len(existing_data)} hypernyms for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'hypernyms', updated_data):
            print(f"Successfully deleted hypernym: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error deleting hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/hypernyms/<category>', methods=['GET'])
def get_hypernyms(category):
    """获取上下义词数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = load_study_data(category, 'hypernyms')
    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/hypernyms/<category>', methods=['POST'])
@_serialized
def add_hypernym(category):
    """添加上下义词"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        upper_words = data.get('upper_words', [])
        lower_words = data.get('lower_words', [])
        title = data.get('title')

        if not upper_words and not lower_words:
            return jsonify({'error': 'At least one upper or lower word is required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'hypernyms')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'upper_words': upper_words,
            'lower_words': lower_words,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        if title:
            new_entry['title'] = title

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'hypernyms', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error adding hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 做题技巧API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['PUT'])
@_serialized
def update_technique(category, item_id):
    """更新做题技巧"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')

        # 查找并更新条目
        updated = False
        for item in existing_data:
            if item.get('id') == item_id:
                item['title'] = title
                item['content'] = content
                item['updated_at'] = datetime.now().isoformat()
                updated = True
                break

        if not updated:
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'techniques', existing_data):
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error updating technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['DELETE'])
@_serialized
def delete_technique(category, item_id):
    """删除做题技巧"""
    print(f"DELETE request received for technique: {category}/{item_id}")  # 添加调试信息

    if not verify_token_from_request():
        print(f"Token verification failed for DELETE {category}/{item_id}")  # 添加调试信息
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        print(f"Invalid category for DELETE: {category}")  # 添加调试信息
        return jsonify({'error': 'Invalid category'}), 400

    try:
        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')
        print(f"Loaded {len(existing_data)} techniques for category {category}")  # 添加调试信息

        # 查找并删除条目
        updated_data = [item for item in existing_data if item.get('id') != item_id]

        if len(updated_data) == len(existing_data):
            print(f"Item not found for DELETE: {item_id}")  # 添加调试信息
            return jsonify({'error': 'Item not found'}), 404

        # 保存数据
        if save_study_data(category, 'techniques', updated_data):
            print(f"Successfully deleted technique: {item_id}")  # 添加调试信息
            return jsonify({'success': True})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error deleting technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/techniques/<category>', methods=['GET'])
def get_techniques(category):
    """获取做题技巧数据"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = load_study_data(category, 'techniques')
    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/techniques/<category>', methods=['POST'])
@_serialized
def add_technique(category):
    """添加做题技巧"""
    if not verify_token_from_request():
        return jsonify({'error': 'Unauthorized'}), 401

    if category not in ['listening', 'speaking', 'reading', 'writing']:
        return jsonify({'error': 'Invalid category'}), 400

    try:
        data = request.json
        title = data.get('title', '').strip()
        content = data.get('content', '').strip()

        if not title or not content:
            return jsonify({'error': 'Title and content are required'}), 400

        # 加载现有数据
        existing_data = load_study_data(category, 'techniques')

        # 创建新条目
        new_entry = {
            'id': generate_id(),
            'title': title,
            'content': content,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }

        existing_data.append(new_entry)

        # 保存数据
        if save_study_data(category, 'techniques', existing_data):
            return jsonify({'success': True, 'id': new_entry['id']})
        else:
            return jsonify({'error': 'Failed to save data'}), 500

    except StudyDataUnreadable as e:
        return _unreadable_response(e)
    except Exception as e:
        print(f"Error adding technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

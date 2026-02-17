from flask import Blueprint, request, jsonify, send_file
import os, json, uuid
from datetime import datetime

from core import STUDY_TECHNIQUES_DIR, STUDY_TECHNIQUES_DATA_DIR, STUDY_TECHNIQUES_AUDIO_DIR, verify_token_from_request

study_tips_bp = Blueprint('study_tips', __name__)


def load_study_data(category, data_type):
    """加载学习技巧数据"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {file_path}: {e}")
            return []
    return []

def save_study_data(category, data_type, data):
    """保存学习技巧数据"""
    file_path = os.path.join(STUDY_TECHNIQUES_DATA_DIR, f'{category}_{data_type}.json')
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {file_path}: {e}")
        return False

def generate_id():
    """生成唯一ID"""
    return str(uuid.uuid4())


@study_tips_bp.route('/study_techniques')
def study_techniques_page():
    """学习技巧页面"""
    return send_file('templates/study_techniques.html')

# 同义词替换API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['PUT'])
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

    except Exception as e:
        print(f"Error updating synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/synonyms/<category>/<item_id>', methods=['DELETE'])
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

    data = load_study_data(category, 'synonyms')
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/synonyms/<category>', methods=['POST'])
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

    except Exception as e:
        print(f"Error adding synonym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 上下义词API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['PUT'])
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

    except Exception as e:
        print(f"Error updating hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/hypernyms/<category>/<item_id>', methods=['DELETE'])
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

    data = load_study_data(category, 'hypernyms')
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/hypernyms/<category>', methods=['POST'])
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

    except Exception as e:
        print(f"Error adding hypernym: {e}")
        return jsonify({'error': 'Internal server error'}), 500

# 做题技巧API - 重新排序路由，确保DELETE路由能正确匹配
@study_tips_bp.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['PUT'])
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

    except Exception as e:
        print(f"Error updating technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@study_tips_bp.route('/api/study_techniques/techniques/<category>/<item_id>', methods=['DELETE'])
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

    data = load_study_data(category, 'techniques')
    return jsonify(data)

@study_tips_bp.route('/api/study_techniques/techniques/<category>', methods=['POST'])
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

    except Exception as e:
        print(f"Error adding technique: {e}")
        return jsonify({'error': 'Internal server error'}), 500

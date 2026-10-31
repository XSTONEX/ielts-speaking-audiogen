from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json, uuid
from datetime import datetime
from werkzeug.utils import secure_filename

from core import (
    VOCABULARY_BOOK_DIR, VOCABULARY_CATEGORIES_DIR, VOCABULARY_AUDIO_DIR,
    VOCABULARY_TASKS_DIR, VOCABULARY_CHALLENGE_DIR,
    is_safe_path_segment
)

vocabulary_bp = Blueprint('vocabulary', __name__)

# ==================== Helper Functions ====================

def load_category_data(category):
    """加载单个分类的数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    if os.path.exists(category_file):
        try:
            with open(category_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

                # 数据迁移：为现有单词添加 is_favorited 字段
                updated = False
                for subcategory_id in data['subcategories']:
                    for word in data['subcategories'][subcategory_id]['words']:
                        if 'is_favorited' not in word:
                            word['is_favorited'] = False
                            updated = True

                # 如果有更新，直接保存数据（避免递归调用）
                if updated:
                    data['metadata']['last_updated'] = datetime.now().isoformat()
                    with open(category_file, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)

                return data
        except:
            pass

    # 返回默认结构
    now = datetime.now().isoformat()
    return {
        "name": category.capitalize(),
        "icon": {"listening": "\ud83c\udfa7", "speaking": "\ud83d\udde3\ufe0f", "reading": "\ud83d\udcd6", "writing": "\u270d\ufe0f"}[category],
        "subcategories": {
            "default": {
                "name": "\u9ed8\u8ba4\u5206\u7c7b",
                "created_at": now,
                "words": []
            }
        },
        "metadata": {
            "created_at": now,
            "last_updated": now
        }
    }

def save_category_data(category, data):
    """保存单个分类的数据"""
    category_file = os.path.join(VOCABULARY_CATEGORIES_DIR, f'{category}.json')
    data['metadata']['last_updated'] = datetime.now().isoformat()
    with open(category_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_vocabulary_data():
    """加载完整的词汇数据（兼容旧接口）"""
    categories = {}
    for category in ['listening', 'speaking', 'reading', 'writing']:
        categories[category] = load_category_data(category)

    return {
        "categories": categories,
        "metadata": {
            "version": "3.0",
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    }

def save_vocabulary_data(vocab_data):
    """保存完整的词汇数据（兼容旧接口）"""
    for category, data in vocab_data['categories'].items():
        save_category_data(category, data)

CSV_HEADER_WORDS = {'单词', 'word', 'words'}
CSV_HEADER_MEANINGS = {'词义', '释义', 'meaning', 'meanings', 'definition'}


def is_csv_header(row):
    """第一行是不是表头：页面导出的是「单词,词义,…」，也认英文的 word,meaning"""
    if not row or row[0].strip().lower() not in CSV_HEADER_WORDS:
        return False
    return len(row) < 2 or row[1].strip().lower() in CSV_HEADER_MEANINGS


# ==================== 单词挑战相关 Helper Functions ====================

def load_user_challenge_data(user_id):
    """加载用户的挑战数据"""
    user_file = os.path.join(VOCABULARY_CHALLENGE_DIR, f'{user_id}.json')
    if os.path.exists(user_file):
        try:
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass

    # 返回默认结构
    return {
        "word_coverage": {},
        "challenge_stats": {
            "total_challenges": 0,
            "total_correct": 0,
            "total_questions": 0,
            "last_challenge": None
        },
        "metadata": {
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
    }

def save_user_challenge_data(user_id, data):
    """保存用户的挑战数据"""
    user_file = os.path.join(VOCABULARY_CHALLENGE_DIR, f'{user_id}.json')
    data['metadata']['last_updated'] = datetime.now().isoformat()
    with open(user_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_current_user_id():
    """获取当前用户ID从请求头中获取"""
    try:
        # 从请求头中获取用户信息
        auth_token = request.headers.get('Authorization', '').replace('Bearer ', '')
        current_user = request.headers.get('X-Current-User', '')

        user_id = None
        if current_user:
            # 如果是JSON字符串，解析并提取username
            if current_user.startswith('{') and current_user.endswith('}'):
                try:
                    user_obj = json.loads(current_user)
                    user_id = user_obj.get('username', 'default_user')
                except json.JSONDecodeError:
                    # 解析失败时和原来一样，直接用原字符串
                    user_id = current_user
            else:
                # 如果已经是字符串，直接使用
                user_id = current_user

        # 返回值会被拼成 challenges/<user_id>.json 读写，"../../users" 这类值会写穿到目录外面
        if isinstance(user_id, str) and is_safe_path_segment(user_id):
            return user_id

        # 如果没有用户信息（或用户信息不合法），使用默认值
        return "default_user"
    except:
        return "default_user"

# ==================== Routes ====================

@vocabulary_bp.route('/vocabulary')
def vocabulary_page():
    """单词本页面"""
    return send_file('templates/vocabulary.html')

@vocabulary_bp.route('/api/vocabulary', methods=['GET'])
def get_vocabulary():
    """获取单词本数据"""
    try:
        vocab_data = load_vocabulary_data()
        return jsonify({'success': True, 'data': vocab_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/subcategories/<category>', methods=['GET'])
def get_subcategories(category):
    """获取指定分类的子分类列表"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        category_data = load_category_data(category)
        subcategories = category_data['subcategories']

        # 转换为列表格式，方便前端使用
        subcategory_list = []
        for sub_id, sub_data in subcategories.items():
            subcategory_list.append({
                'id': sub_id,
                'name': sub_data['name'],
                'created_at': sub_data['created_at'],
                'word_count': len(sub_data['words'])
            })

        # 按创建时间排序
        subcategory_list.sort(key=lambda x: x['created_at'])

        return jsonify({'success': True, 'data': subcategory_list})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/subcategories', methods=['POST'])
def create_subcategory():
    """创建新的子分类"""
    try:
        data = request.json
        category = data.get('category')
        name = data.get('name', '').strip()

        if not category or category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        if not name:
            return jsonify({'success': False, 'error': '子分类名称不能为空'}), 400

        category_data = load_category_data(category)

        # 检查子分类名称是否已存在
        existing_names = [sub['name'] for sub in category_data['subcategories'].values()]
        if name in existing_names:
            return jsonify({'success': False, 'error': '子分类名称已存在'}), 400

        # 生成唯一ID
        subcategory_id = str(uuid.uuid4())

        # 创建子分类
        category_data['subcategories'][subcategory_id] = {
            'name': name,
            'created_at': datetime.now().isoformat(),
            'words': []
        }

        save_category_data(category, category_data)

        return jsonify({
            'success': True,
            'data': {
                'id': subcategory_id,
                'name': name,
                'created_at': category_data['subcategories'][subcategory_id]['created_at'],
                'word_count': 0
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/subcategories/<category>/<subcategory_id>', methods=['PUT'])
def update_subcategory(category, subcategory_id):
    """更新子分类名称"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        data = request.json
        new_name = data.get('name', '').strip()

        if not new_name:
            return jsonify({'success': False, 'error': '子分类名称不能为空'}), 400

        category_data = load_category_data(category)

        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 404

        # 检查新名称是否与其他子分类重复
        existing_names = [sub['name'] for sub_id, sub in category_data['subcategories'].items() if sub_id != subcategory_id]
        if new_name in existing_names:
            return jsonify({'success': False, 'error': '子分类名称已存在'}), 400

        # 更新名称
        category_data['subcategories'][subcategory_id]['name'] = new_name
        save_category_data(category, category_data)

        return jsonify({'success': True, 'message': '子分类名称更新成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/subcategories/<category>/<subcategory_id>', methods=['DELETE'])
def delete_subcategory(category, subcategory_id):
    """删除子分类"""
    try:
        if category not in ['listening', 'speaking', 'reading', 'writing']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        category_data = load_category_data(category)

        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 404

        # 检查是否是最后一个子分类（至少保留一个）
        if len(category_data['subcategories']) <= 1:
            return jsonify({'success': False, 'error': '至少需要保留一个子分类'}), 400

        # 删除子分类中所有单词的音频文件
        words = category_data['subcategories'][subcategory_id]['words']
        category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)

        for word in words:
            # 删除音频文件
            audio_path = os.path.join(category_audio_dir, f"{word['id']}.mp3")
            if os.path.exists(audio_path):
                os.remove(audio_path)

            # 删除相关的音频生成任务
            for task_file in os.listdir(VOCABULARY_TASKS_DIR):
                if task_file.endswith('.json'):
                    try:
                        task_path = os.path.join(VOCABULARY_TASKS_DIR, task_file)
                        with open(task_path, 'r', encoding='utf-8') as f:
                            task = json.load(f)
                        if task.get('word_id') == word['id']:
                            os.remove(task_path)
                    except:
                        continue

        # 删除子分类
        del category_data['subcategories'][subcategory_id]
        save_category_data(category, category_data)

        return jsonify({'success': True, 'message': '子分类删除成功'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/add', methods=['POST'])
def add_vocabulary_word():
    """添加单词"""
    try:
        data = request.json
        category = data.get('category')  # speaking, writing, listening, reading
        subcategory_id = data.get('subcategory_id', 'default')
        word = data.get('word', '').strip()
        meaning = data.get('meaning', '').strip()

        if not category or category not in ['speaking', 'writing', 'listening', 'reading']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        if not word:
            return jsonify({'success': False, 'error': '单词不能为空'}), 400

        category_data = load_category_data(category)

        # 检查子分类是否存在
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 400

        # 检查是否已存在（仅在该子分类内判重）
        subcategory_words = category_data['subcategories'][subcategory_id]['words']
        for existing_word in subcategory_words:
            if existing_word['word'].lower() == word.lower():
                return jsonify({'success': False, 'error': '单词在该子分类中已存在'}), 400

        # 生成唯一ID
        word_id = str(uuid.uuid4())

        # 创建单词对象
        word_obj = {
            'id': word_id,
            'word': word,
            'meaning': meaning,
            'created_at': datetime.now().isoformat(),
            'audio_generated': False,
            'is_favorited': False  # 默认未收藏
        }

        # 添加到对应子分类（发音由页面点击时实时取有道词典，不再提前用 TTS 生成）
        category_data['subcategories'][subcategory_id]['words'].append(word_obj)
        save_category_data(category, category_data)

        return jsonify({'success': True, 'data': word_obj})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/upload_csv', methods=['POST'])
def upload_vocabulary_csv():
    """批量上传CSV文件"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '没有上传文件'}), 400

        file = request.files['file']
        category = request.form.get('category')
        subcategory_id = request.form.get('subcategory_id', 'default')

        if not category or category not in ['speaking', 'writing', 'listening', 'reading']:
            return jsonify({'success': False, 'error': '无效的分类'}), 400

        if file.filename == '':
            return jsonify({'success': False, 'error': '没有选择文件'}), 400

        if not file.filename.lower().endswith('.csv'):
            return jsonify({'success': False, 'error': '只支持CSV文件'}), 400

        # 读取CSV文件
        import csv
        import io

        # utf-8-sig 兼容 Excel 导出的带 BOM 文件，避免首个单词带上
        content = file.read().decode('utf-8-sig')
        csv_reader = csv.reader(io.StringIO(content))

        category_data = load_category_data(category)

        # 检查子分类是否存在
        if subcategory_id not in category_data['subcategories']:
            return jsonify({'success': False, 'error': '子分类不存在'}), 400

        existing_words = {w['word'].lower() for w in category_data['subcategories'][subcategory_id]['words']}

        added_words = []
        skipped_words = []
        invalid_rows = 0  # 只有一列（没有释义那一列）的行
        first_row = True

        for row in csv_reader:
            is_first_row, first_row = first_row, False
            # 页面导出的 CSV 第一行是表头「单词,词义,…」，再导入时跳过，别当成一个单词
            if is_first_row and is_csv_header(row):
                continue
            if len(row) >= 2:
                word = row[0].strip()
                meaning = row[1].strip()

                if not word:
                    continue

                # 判重（仅在该子分类内）
                if word.lower() in existing_words:
                    skipped_words.append(word)
                    continue

                # 生成唯一ID
                word_id = str(uuid.uuid4())

                word_obj = {
                    'id': word_id,
                    'word': word,
                    'meaning': meaning,
                    'created_at': datetime.now().isoformat(),
                    'audio_generated': False
                }

                category_data['subcategories'][subcategory_id]['words'].append(word_obj)
                added_words.append(word_obj)
                existing_words.add(word.lower())
            elif row and row[0].strip():
                invalid_rows += 1

        # 一行能用的都没有、却有只写了一列的行：多半是用了中文逗号或漏了释义列，明确告诉用户而不是静默导入 0 个
        if not added_words and not skipped_words and invalid_rows:
            return jsonify({
                'success': False,
                'error': '没有读到单词：每行要有两列，第一列单词、第二列释义，中间用英文逗号分隔',
                'invalid_count': invalid_rows
            }), 400

        save_category_data(category, category_data)

        return jsonify({
            'success': True,
            'added_count': len(added_words),
            'skipped_count': len(skipped_words),
            'skipped_words': skipped_words[:10],  # 只返回前10个重复的单词
            'invalid_count': invalid_rows
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/<word_id>', methods=['DELETE'])
def delete_vocabulary_word(word_id):
    """删除单词"""
    try:
        deleted = False
        deleted_category = None

        # 在所有分类和子分类中查找并删除
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_data = load_category_data(category)

            for subcategory_id in category_data['subcategories']:
                words = category_data['subcategories'][subcategory_id]['words']
                original_length = len(words)
                category_data['subcategories'][subcategory_id]['words'] = [
                    w for w in words if w['id'] != word_id
                ]

                if len(category_data['subcategories'][subcategory_id]['words']) < original_length:
                    deleted = True
                    deleted_category = category
                    save_category_data(category, category_data)
                    break

            if deleted:
                break

        if not deleted:
            return jsonify({'success': False, 'error': '单词不存在'}), 404

        # 删除音频文件（按分类存储）
        if deleted_category:
            category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, deleted_category)
            audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
            if os.path.exists(audio_path):
                os.remove(audio_path)

        # 删除相关的音频生成任务
        if os.path.exists(VOCABULARY_TASKS_DIR):
            for task_file in os.listdir(VOCABULARY_TASKS_DIR):
                if task_file.endswith('.json'):
                    try:
                        task_path = os.path.join(VOCABULARY_TASKS_DIR, task_file)
                        with open(task_path, 'r', encoding='utf-8') as f:
                            task = json.load(f)
                        if task.get('word_id') == word_id:
                            os.remove(task_path)
                    except:
                        continue

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/<word_id>/favorite', methods=['PUT'])
def toggle_word_favorite(word_id):
    """切换单词收藏状态"""
    try:
        data = request.json
        is_favorited = data.get('is_favorited', False)

        found = False
        updated_word = None

        # 在所有分类和子分类中查找并更新
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_data = load_category_data(category)

            for subcategory_id in category_data['subcategories']:
                words = category_data['subcategories'][subcategory_id]['words']

                for word in words:
                    if word['id'] == word_id:
                        word['is_favorited'] = is_favorited
                        updated_word = word
                        found = True
                        save_category_data(category, category_data)
                        break

                if found:
                    break

            if found:
                break

        if not found:
            return jsonify({'success': False, 'error': '单词不存在'}), 404

        return jsonify({'success': True, 'data': updated_word})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ==================== 单词挑战相关API ====================

@vocabulary_bp.route('/api/vocabulary/challenge/coverage')
def get_challenge_coverage():
    """获取用户的挑战覆盖率数据"""
    try:
        user_id = get_current_user_id()
        challenge_data = load_user_challenge_data(user_id)
        return jsonify({'success': True, 'data': challenge_data['word_coverage']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/api/vocabulary/challenge/record', methods=['POST'])
def record_challenge_result():
    """记录挑战结果"""
    try:
        user_id = get_current_user_id()
        data = request.json
        challenge_results = data.get('results', [])
        scope = data.get('scope')
        category = data.get('category')
        subcategory_id = data.get('subcategory_id')

        # 加载用户挑战数据
        challenge_data = load_user_challenge_data(user_id)

        # 更新单词覆盖率
        for result in challenge_results:
            word_id = result['word_id']
            if word_id not in challenge_data['word_coverage']:
                challenge_data['word_coverage'][word_id] = {
                    'appear_count': 0,
                    'last_appeared': None
                }
            challenge_data['word_coverage'][word_id]['appear_count'] += 1
            challenge_data['word_coverage'][word_id]['last_appeared'] = datetime.now().isoformat()

        # 更新挑战统计
        total_questions = len(challenge_results)
        correct_answers = sum(1 for r in challenge_results if r.get('is_correct', False))

        challenge_data['challenge_stats']['total_challenges'] += 1
        challenge_data['challenge_stats']['total_correct'] += correct_answers
        challenge_data['challenge_stats']['total_questions'] += total_questions
        challenge_data['challenge_stats']['last_challenge'] = datetime.now().isoformat()

        # 保存数据
        save_user_challenge_data(user_id, challenge_data)

        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@vocabulary_bp.route('/vocabulary_audio/<word_id>')
def serve_vocabulary_audio(word_id):
    """提供单词音频文件"""
    try:
        # 在各个分类目录中查找音频文件
        for category in ['listening', 'speaking', 'reading', 'writing']:
            category_audio_dir = os.path.join(VOCABULARY_AUDIO_DIR, category)
            audio_path = os.path.join(category_audio_dir, f"{word_id}.mp3")
            if os.path.exists(audio_path):
                return send_from_directory(category_audio_dir, f"{word_id}.mp3")

        return jsonify({'error': '音频文件不存在'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 404

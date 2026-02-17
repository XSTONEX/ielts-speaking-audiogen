import os
import json
import re
import requests
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file
from core import (
    WRITING_CORRECTION_DIR, WRITING_DATA_DIR, WRITING_MD_FILE,
    is_token_valid, load_tokens
)

writing_bp = Blueprint('writing', __name__)


# ===================== 写作批改模块 =====================

_writing_cache = None

def _has_chinese(text):
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def _parse_writing_md():
    global _writing_cache
    if _writing_cache is not None:
        return _writing_cache
    with open(WRITING_MD_FILE, 'r', encoding='utf-8') as f:
        lines = f.read().split('\n')
    categories = []
    cur_cat = cur_sub = cur_chain = cur_example = None
    section = example_phase = None
    for raw in lines:
        s = raw.strip()
        if s.startswith('<div'):
            continue
        if s.startswith('# ') and not s.startswith('## '):
            continue
        if s.startswith('## ') and not s.startswith('### '):
            cur_cat = {'name': s[3:].strip(), 'subcategories': []}
            categories.append(cur_cat)
            cur_sub = section = None
            continue
        if s.startswith('### ') and not s.startswith('#### '):
            cur_sub = {'name': s[4:].strip(), 'keywords': [], 'chains': [], 'examples': []}
            if cur_cat:
                cur_cat['subcategories'].append(cur_sub)
            section = cur_example = None
            continue
        if s.startswith('#### ') and not s.startswith('##### '):
            h = s[5:].strip()
            if '关键词' in h:
                section = 'kw'
            elif '逻辑链' in h:
                section = 'ch'
                cur_chain = None
            elif '细节' in h or '举例' in h:
                section = 'ex'
            continue
        if s.startswith('##### '):
            cur_example = {'title': s[6:].strip(), 'question': '', 'hints': [], 'sentences': []}
            if cur_sub:
                cur_sub['examples'].append(cur_example)
            example_phase = 'question'
            continue
        if not s or not cur_sub:
            continue
        if section == 'kw':
            if s.startswith('- '):
                cur_sub['keywords'].append(s[2:].strip())
        elif section == 'ch':
            m = re.match(r'^链\s*(\d+)', s)
            if m:
                cur_chain = {'id': int(m.group(1)), 'chinese': '', 'english': ''}
                cur_sub['chains'].append(cur_chain)
            elif s.startswith('- ') and cur_chain:
                t = s[2:].strip()
                if _has_chinese(t):
                    cur_chain['chinese'] = t
                else:
                    cur_chain['english'] = t
        elif section == 'ex' and cur_example:
            if example_phase == 'question':
                if s.startswith('使用'):
                    example_phase = 'hints'
                    cur_example['hints'].append(s)
                else:
                    cur_example['question'] = (cur_example['question'] + ' ' + s).strip()
            elif example_phase == 'hints':
                if s.startswith('- 使用') or s.startswith('- 写作') or s.startswith('使用'):
                    cur_example['hints'].append(s)
                else:
                    example_phase = 'sentences'
                    if _has_chinese(s):
                        if cur_example['sentences'] and not cur_example['sentences'][-1].get('chinese'):
                            cur_example['sentences'][-1]['chinese'] = s
                    else:
                        cur_example['sentences'].append({'english': s, 'chinese': ''})
            elif example_phase == 'sentences':
                if _has_chinese(s):
                    if cur_example['sentences'] and not cur_example['sentences'][-1].get('chinese'):
                        cur_example['sentences'][-1]['chinese'] = s
                else:
                    cur_example['sentences'].append({'english': s, 'chinese': ''})
    _writing_cache = categories
    return categories


@writing_bp.route('/writing_practice')
def writing_practice_page():
    return send_file('templates/writing_practice.html')


@writing_bp.route('/api/writing/categories', methods=['GET'])
def writing_categories():
    cats = _parse_writing_md()
    result = []
    for ci, c in enumerate(cats):
        subs = [{'index': si, 'name': s['name'], 'keyword_count': len(s['keywords']),
                 'chain_count': len(s['chains']), 'example_count': len(s['examples'])}
                for si, s in enumerate(c['subcategories'])]
        result.append({'index': ci, 'name': c['name'], 'subcategories': subs})
    return jsonify(result)


@writing_bp.route('/api/writing/subcategory/<int:cat_idx>/<int:sub_idx>', methods=['GET'])
def writing_subcategory(cat_idx, sub_idx):
    cats = _parse_writing_md()
    if cat_idx >= len(cats):
        return jsonify({'error': 'Category not found'}), 404
    cat = cats[cat_idx]
    if sub_idx >= len(cat['subcategories']):
        return jsonify({'error': 'Subcategory not found'}), 404
    sub = cat['subcategories'][sub_idx]
    return jsonify({'category': cat['name'], **sub})


@writing_bp.route('/api/writing/correct', methods=['POST'])
def writing_correct():
    data = request.json or {}
    question = data.get('question_text', '')
    target = data.get('target_chinese', '')
    translation = data.get('user_translation', '')
    if not translation.strip():
        return jsonify({'error': '翻译内容不能为空'}), 400

    system_prompt = (
        "你是一位精通中英双语的雅思前考官。任务是评估用户的英文翻译，并按雅思写作标准（TR, CC, LR, GRA）进行批改。\n\n"
        "评估重点：\n1. 语法与拼写准确性。\n2. 词汇多样性与地道程度。\n3. 句间逻辑连贯性。\n\n"
        "【强制要求】\n必须且仅以纯 JSON 格式输出，不要包含 Markdown 符号或额外解释，结构如下：\n"
        '{"score":"预估单句分数 (如 5.5, 6.0, 6.5)",'
        '"feedback_summary":"一句话核心评价",'
        '"grammar_corrections":[{"original":"原词","corrected":"修改后","reason":"原因"}],'
        '"vocabulary_upgrade":"1-2个高阶替换建议及中文解释",'
        '"native_version":"符合高分水平的完美示范译文"}'
    )
    user_prompt = (
        f"【雅思例题】\n{question}\n\n"
        f"【目标中文句】\n{target}\n\n"
        f"【用户英文翻译】\n{translation}"
    )
    try:
        api_key = os.getenv('DEER_API_KEY')
        resp = requests.post(
            'https://api.deerapi.com/v1/chat/completions',
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': 'gpt-4o-mini',
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': 0.3
            },
            timeout=30
        )
        resp.raise_for_status()
        content = resp.json()['choices'][0]['message']['content'].strip()
        content = re.sub(r'^```(?:json)?\s*', '', content)
        content = re.sub(r'\s*```$', '', content)
        result = json.loads(content)
        return jsonify(result)
    except requests.exceptions.Timeout:
        return jsonify({'error': 'AI 服务超时，请重试'}), 504
    except json.JSONDecodeError:
        return jsonify({'error': 'AI 返回格式异常', 'raw': content}), 502
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _practice_path(username):
    return os.path.join(WRITING_DATA_DIR, f'{username}_practice.json')

def _load_practice(username):
    p = _practice_path(username)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def _save_practice(username, data):
    with open(_practice_path(username), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@writing_bp.route('/api/writing/save_practice', methods=['POST'])
def writing_save_practice():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    data = request.json or {}
    records = _load_practice(username)
    record = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'category': data.get('category', ''),
        'subcategory': data.get('subcategory', ''),
        'question': data.get('question', ''),
        'target_chinese': data.get('target_chinese', ''),
        'user_translation': data.get('user_translation', ''),
        'score': data.get('score', ''),
        'feedback': data.get('feedback', {}),
        'native_version': data.get('native_version', '')
    }
    records.insert(0, record)
    _save_practice(username, records)
    return jsonify({'success': True, 'id': record['id']})


@writing_bp.route('/api/writing/practice_history', methods=['GET'])
def writing_practice_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_practice(username)
    return jsonify(records)


@writing_bp.route('/api/writing/delete_practice/<record_id>', methods=['POST'])
def writing_delete_practice(record_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_practice(username)
    records = [r for r in records if r['id'] != record_id]
    _save_practice(username, records)
    return jsonify({'success': True})

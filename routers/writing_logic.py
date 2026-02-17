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
    reference = data.get('standard_reference', '') # 【新增】从前端获取标准参考答案
    
    if not translation.strip():
        return jsonify({'error': '翻译内容不能为空'}), 400

    system_prompt = (
        "你是一位专业的雅思写作考官。你的点评客观、直接、切中要害，不带任何主观情绪色彩。\n\n"
        "【评分与评估重点】\n"
        "1. **评分基准（满分7.0）**：以用户提供的【标准参考答案】作为 7.0 分的基准。如果用户的翻译在准确度与地道倾向上与参考答案差别不大，请直接给 7.0 分。如果有语法错误、逻辑不通或明显的中式英语，再酌情减分。\n"
        "2. **客观纠错**：直接指出语法与拼写错误，无需任何客套话，该怎么改就怎么改。\n"
        "3. **深度拓展**：提供至少3组高阶同义词替换建议及中文解释，帮助用户丰富词汇库。\n"
        "4. **贴近原句修改**：这是最重要的要求。在最终示范中，必须先列出标准答案，然后提供一个【基于用户原句结构】的 7分优化版。尽量保留用户原本的语法框架，只修正错误和替换不地道的表达，以便用户对照理解。\n\n"
        "【强制要求】\n必须且仅以纯 JSON 格式输出，而且以下结构必须全部包含，不要包含 Markdown 符号或额外解释，结构如下：\n"
        "{\n"
        '  "score": "预估单句分数 (以参考例句为7.0基准，如 5.5, 6.0, 6.5, 7.0)",\n'
        '  "feedback_summary": "客观直接的一句话核心评价（一针见血地指出问题或亮点）",\n'
        '  "grammar_corrections": [{"original": "原词", "corrected": "修改后", "reason": "客观修改原因"}],\n'
        '  "vocabulary_upgrade": "必须写出具体的英文替换词！格式示范：\'1. [原英文] -> [高阶英文] (中文解释与适用语境)\'。提供至少3组同义词替换及句型优化建议，切忌只写中文解释不写英文单词！",\n'
        '  "native_version": "1. 标准答案：[填入标准参考答案]\\n\\n2. 你的结构优化版：[在保留用户原句语法框架的基础上，修改而成的 7.0 分地道表达]"\n'
        "}"
    )
    
    user_prompt = (
        f"【雅思例题】\n{question}\n\n"
        f"【目标中文句】\n{target}\n\n"
        f"【标准参考答案】\n{reference}\n\n"  # 【新增】将标准答案喂给 AI 当基准
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
        
        # 兼容处理可能携带的 markdown JSON 代码块标记
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

    # save_to_review controls whether this record goes into the review center
    save_to_review = data.get('save_to_review', False)

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
        'native_version': data.get('native_version', ''),
        'in_review': save_to_review
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

    # Only show records marked for review in the review center
    review_records = [r for r in records if r.get('in_review', True)]

    grouped = {}
    for r in review_records:
        cat = r.get('category', '未分类')
        sub = r.get('subcategory', '未分类')
        if cat not in grouped:
            grouped[cat] = {}
        if sub not in grouped[cat]:
            grouped[cat][sub] = {'records': [], 'avg_score': 0, 'count': 0}
        grouped[cat][sub]['records'].append(r)

    for cat in grouped:
        for sub in grouped[cat]:
            recs = grouped[cat][sub]['records']
            grouped[cat][sub]['count'] = len(recs)
            scores = []
            for rec in recs:
                try:
                    scores.append(float(rec.get('score', 0)))
                except (ValueError, TypeError):
                    pass
            grouped[cat][sub]['avg_score'] = round(sum(scores) / len(scores), 1) if scores else 0

    return jsonify(grouped)


@writing_bp.route('/api/writing/practice_progress', methods=['GET'])
def writing_practice_progress():
    """Return per-subcategory sentence-level completion info for progress bars."""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_practice(username)

    # Only sentences with at least one in_review=true record count as completed.
    # Old records without in_review field default to True (backward compat).
    # Collect full feedback records per sentence for detail display.
    completed = {}
    for r in records:
        if not r.get('in_review', True):
            continue
        key = f"{r.get('category','')}||{r.get('subcategory','')}||{r.get('question','')}||{r.get('target_chinese','')}"
        if key not in completed:
            completed[key] = []
        completed[key].append({
            'score': r.get('score', ''),
            'user_translation': r.get('user_translation', ''),
            'feedback': r.get('feedback', {}),
            'timestamp': r.get('timestamp', '')
        })

    # Walk through all categories/subcategories and compute progress
    cats = _parse_writing_md()
    progress = {}
    for ci, cat in enumerate(cats):
        cat_name = cat['name']
        for si, sub in enumerate(cat['subcategories']):
            sub_name = sub['name']
            total_sentences = 0
            done_sentences = 0
            example_details = []
            for ei, ex in enumerate(sub['examples']):
                ex_total = len(ex['sentences'])
                ex_done = 0
                sent_status = []
                for sent in ex['sentences']:
                    key = f"{cat_name}||{sub_name}||{ex['question']}||{sent['chinese']}"
                    scores = completed.get(key, [])
                    is_done = len(scores) > 0
                    if is_done:
                        ex_done += 1
                    sent_status.append(scores if is_done else None)
                total_sentences += ex_total
                done_sentences += ex_done
                example_details.append({
                    'example_idx': ei,
                    'total': ex_total,
                    'done': ex_done,
                    'sentences': sent_status
                })
            pkey = f"{ci}_{si}"
            progress[pkey] = {
                'total': total_sentences,
                'done': done_sentences,
                'examples': example_details
            }
    return jsonify(progress)


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

import os
import json
import re
import logging
import requests
import uuid
from datetime import datetime
from flask import Blueprint, request, jsonify, send_file, send_from_directory
from core import (
    WRITING_CORRECTION_DIR, WRITING_DATA_DIR, WRITING_MD_FILE,
    WRITING_SMALL_MD_FILE, WRITING_IMAGES_DIR,
    is_token_valid, load_tokens, load_prompt
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


# ===================== 小作文仿写模块 =====================

_small_writing_cache = None

def _extract_tags(text):
    """从句子标题中提取【】标签，支持复合标签和双层括号"""
    tags = []
    # 匹配 【xxx】 或 【【xxx】】
    for m in re.finditer(r'【【?([^】]+?)】】?', text):
        tag = m.group(1).strip()
        tags.append(tag)
    # 处理 / 分割的复合标签行，如 **句子四【极端趋势】 / 【趋势非常相反】**
    if ' / ' in text:
        parts = text.split(' / ')
        if len(parts) > 1:
            tags = []
            for part in parts:
                for m in re.finditer(r'【【?([^】]+?)】】?', part):
                    tags.append(m.group(1).strip())
    return tags


def _parse_vocab_table(lines):
    """解析 Markdown 表格格式的表达积累"""
    try:
        rows = []
        for line in lines:
            line = line.strip()
            if not line.startswith('|') or line.startswith('| :') or line.startswith('|:'):
                continue
            cells = [c.strip() for c in line.split('|')]
            cells = [c for c in cells if c]
            if len(cells) >= 3 and cells[0] not in ('类别',):
                rows.append({
                    'category': re.sub(r'\*\*', '', cells[0]),
                    'english': re.sub(r'\*\*', '', cells[1]),
                    'chinese': re.sub(r'\*\*', '', cells[2])
                })
        return rows if rows else None
    except Exception:
        return None


def _parse_small_writing_md():
    """解析小作文仿写 Markdown 文件"""
    global _small_writing_cache
    if _small_writing_cache is not None:
        return _small_writing_cache

    with open(WRITING_SMALL_MD_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    chart_types = []
    parse_warnings = []
    current_type = None
    # 按 ### 分割出每道例题
    type_sections = re.split(r'^## ', content, flags=re.MULTILINE)

    for type_sec in type_sections:
        type_sec = type_sec.strip()
        if not type_sec or type_sec.startswith('#'):
            continue
        type_lines = type_sec.split('\n')
        type_name = type_lines[0].strip()
        if not type_name:
            continue

        current_type = {'name': type_name, 'examples': []}
        # 按 ### 分割例题
        example_sections = re.split(r'^### ', '\n'.join(type_lines[1:]), flags=re.MULTILINE)

        for ex_idx, ex_sec in enumerate(example_sections):
            ex_sec = ex_sec.strip()
            if not ex_sec:
                continue
            try:
                ex_lines = ex_sec.split('\n')
                ex_name = ex_lines[0].strip()
                if not ex_name or ex_name.startswith('---'):
                    continue

                example = {
                    'id': f"{type_name}_{ex_idx}",
                    'name': ex_name,
                    'chart_subtype': '',
                    'question': '',
                    'image_path': None,
                    'sections': [],
                    'vocabulary_table': None
                }

                current_section = None
                collecting_question = False
                collecting_vocab = False
                vocab_lines = []

                for line in ex_lines[1:]:
                    s = line.strip()
                    if not s:
                        continue

                    # 图表类型
                    m = re.match(r'\*\*图表类型\*\*[：:]\s*(.+)', s)
                    if m:
                        example['chart_subtype'] = m.group(1).strip()
                        continue

                    # 题目开始
                    if s.startswith('**题目**') or s == '**题目**：':
                        collecting_question = True
                        # 提取同行内容
                        q = re.sub(r'^\*\*题目\*\*[：:]\s*', '', s).strip()
                        if q:
                            example['question'] = q
                        continue

                    # #### 段落标题
                    if s.startswith('#### '):
                        collecting_question = False
                        if collecting_vocab and vocab_lines:
                            example['vocabulary_table'] = _parse_vocab_table(vocab_lines)
                            collecting_vocab = False
                            vocab_lines = []

                        heading = s[5:].strip()
                        if '表达积累' in heading:
                            collecting_vocab = True
                            vocab_lines = []
                            current_section = None
                            continue

                        # 提取 [xxx] 中的注释
                        annotation = None
                        ann_match = re.search(r'\[(.+?)\]', heading)
                        if ann_match:
                            annotation = ann_match.group(1)
                        sec_name = re.sub(r'\s*\[.+?\]\s*', '', heading).strip()

                        current_section = {
                            'name': sec_name,
                            'annotation': annotation,
                            'sentences': []
                        }
                        example['sections'].append(current_section)
                        continue

                    # 收集表达积累表格行
                    if collecting_vocab:
                        vocab_lines.append(line)
                        continue

                    # 收集题目文本（多行）
                    if collecting_question:
                        if s.startswith('#### ') or s.startswith('- **'):
                            collecting_question = False
                        else:
                            example['question'] = (example['question'] + ' ' + s).strip()
                            continue

                    if not current_section:
                        continue

                    # 句子标题行: - **句子一【极端数值】**
                    sent_match = re.match(r'^-\s*\*\*(.+?)\*\*\s*$', s)
                    if sent_match:
                        title = sent_match.group(1)
                        tags = _extract_tags(title)
                        current_section['sentences'].append({
                            'tags': tags,
                            'original': '',
                            'translation': ''
                        })
                        continue

                    # 改写段特殊格式: - **原句**：xxx
                    orig_match = re.match(r'^-?\s*\*\*原句\*\*[：:]\s*(.+)', s)
                    if orig_match:
                        text = orig_match.group(1).strip()
                        if current_section['sentences']:
                            current_section['sentences'][-1]['original'] = text
                        else:
                            current_section['sentences'].append({
                                'tags': [],
                                'original': text,
                                'translation': ''
                            })
                        continue

                    trans_match = re.match(r'^-?\s*\*\*翻译\*\*[：:]\s*(.+)', s)
                    if trans_match:
                        text = trans_match.group(1).strip()
                        if current_section['sentences']:
                            current_section['sentences'][-1]['translation'] = text
                        continue

                    # 子项原句/翻译: - **原句**：xxx
                    sub_orig = re.match(r'^\s*-\s*\*\*原句\*\*[：:]\s*(.+)', s)
                    if sub_orig:
                        text = sub_orig.group(1).strip()
                        if current_section['sentences']:
                            current_section['sentences'][-1]['original'] = text
                        continue

                    sub_trans = re.match(r'^\s*-\s*\*\*翻译\*\*[：:]\s*(.+)', s)
                    if sub_trans:
                        text = sub_trans.group(1).strip()
                        if current_section['sentences']:
                            current_section['sentences'][-1]['translation'] = text
                        continue

                # 处理末尾的词汇表
                if collecting_vocab and vocab_lines:
                    example['vocabulary_table'] = _parse_vocab_table(vocab_lines)

                # 校验：必须有题目和至少一个段落
                if not example['question'] or not example['sections']:
                    parse_warnings.append(f"{type_name}/{ex_name}: 缺少题目或段落，已跳过")
                    continue

                # 加载已绑定的图片
                bindings = _load_image_bindings()
                if example['id'] in bindings:
                    example['image_path'] = bindings[example['id']]

                current_type['examples'].append(example)

            except Exception as e:
                parse_warnings.append(f"{type_name}/例题{ex_idx}: 解析失败 - {str(e)}")
                logging.warning(f"小作文例题解析失败: {type_name}/例题{ex_idx}: {e}")
                continue

        if current_type['examples']:
            chart_types.append(current_type)

    result = {'chart_types': chart_types, 'parse_warnings': parse_warnings}
    _small_writing_cache = result
    if parse_warnings:
        logging.warning(f"小作文解析警告: {parse_warnings}")
    return result


# ===================== 图片绑定管理 =====================

_IMAGE_BINDINGS_FILE = os.path.join(WRITING_IMAGES_DIR, 'image_bindings.json')

def _load_image_bindings():
    if os.path.exists(_IMAGE_BINDINGS_FILE):
        try:
            with open(_IMAGE_BINDINGS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def _save_image_bindings(bindings):
    os.makedirs(WRITING_IMAGES_DIR, exist_ok=True)
    with open(_IMAGE_BINDINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bindings, f, ensure_ascii=False, indent=2)


# ===================== 小作文练习数据 =====================

def _small_practice_path(username):
    return os.path.join(WRITING_DATA_DIR, f'{username}_small_practice.json')

def _load_small_practice(username):
    p = _small_practice_path(username)
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def _save_small_practice(username, data):
    with open(_small_practice_path(username), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ===================== 小作文 API 路由 =====================

@writing_bp.route('/api/writing/small/chart_types', methods=['GET'])
def small_chart_types():
    data = _parse_small_writing_md()
    result = []
    for i, ct in enumerate(data['chart_types']):
        result.append({
            'index': i,
            'name': ct['name'],
            'example_count': len(ct['examples'])
        })
    return jsonify(result)


@writing_bp.route('/api/writing/small/chart_type/<int:type_idx>', methods=['GET'])
def small_chart_type_detail(type_idx):
    data = _parse_small_writing_md()
    if type_idx >= len(data['chart_types']):
        return jsonify({'error': '图表类型不存在'}), 404
    ct = data['chart_types'][type_idx]
    examples = []
    for i, ex in enumerate(ct['examples']):
        examples.append({
            'index': i,
            'name': ex['name'],
            'chart_subtype': ex['chart_subtype'],
            'image_path': ex['image_path'],
            'section_count': len(ex['sections']),
            'sentence_count': sum(len(s['sentences']) for s in ex['sections'])
        })
    return jsonify({'name': ct['name'], 'examples': examples})


@writing_bp.route('/api/writing/small/example/<int:type_idx>/<int:example_idx>', methods=['GET'])
def small_example_detail(type_idx, example_idx):
    data = _parse_small_writing_md()
    if type_idx >= len(data['chart_types']):
        return jsonify({'error': '图表类型不存在'}), 404
    ct = data['chart_types'][type_idx]
    if example_idx >= len(ct['examples']):
        return jsonify({'error': '例题不存在'}), 404
    ex = ct['examples'][example_idx]
    return jsonify({
        'chart_type': ct['name'],
        **ex
    })


@writing_bp.route('/api/writing/small/upload_image', methods=['POST'])
def small_upload_image():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    if 'image' not in request.files:
        return jsonify({'error': '没有找到图片文件'}), 400

    file = request.files['image']
    type_idx = request.form.get('type_idx')
    example_idx = request.form.get('example_idx')
    if type_idx is None or example_idx is None:
        return jsonify({'error': '缺少参数'}), 400

    data = _parse_small_writing_md()
    try:
        ct = data['chart_types'][int(type_idx)]
        ex = ct['examples'][int(example_idx)]
    except (IndexError, ValueError):
        return jsonify({'error': '参数无效'}), 400

    question_id = ex['id']
    img_dir = os.path.join(WRITING_IMAGES_DIR, question_id)
    # 删除旧图片
    if os.path.isdir(img_dir):
        for old_file in os.listdir(img_dir):
            try:
                os.remove(os.path.join(img_dir, old_file))
            except OSError:
                pass
    os.makedirs(img_dir, exist_ok=True)

    filename = file.filename or 'image.png'
    ext = os.path.splitext(filename)[1].lower() or '.png'
    allowed = {'.png', '.jpg', '.jpeg', '.gif', '.webp'}
    if ext not in allowed:
        return jsonify({'error': '不支持的图片格式'}), 400

    save_name = f"{uuid.uuid4().hex[:8]}{ext}"
    save_path = os.path.join(img_dir, save_name)

    try:
        from PIL import Image
        img = Image.open(file.stream)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        save_name = save_name.rsplit('.', 1)[0] + '.webp'
        save_path = os.path.join(img_dir, save_name)
        img.save(save_path, 'WEBP', quality=85)
    except ImportError:
        file.save(save_path)

    image_url = f'/api/writing/small/image/{question_id}/{save_name}'

    # 更新绑定
    bindings = _load_image_bindings()
    bindings[question_id] = image_url
    _save_image_bindings(bindings)

    # 清除缓存使下次读取时能获取新图片路径
    global _small_writing_cache
    _small_writing_cache = None

    return jsonify({'success': True, 'image_url': image_url})


@writing_bp.route('/api/writing/small/image/<question_id>/<filename>')
def small_serve_image(question_id, filename):
    img_dir = os.path.join(WRITING_IMAGES_DIR, question_id)
    return send_from_directory(img_dir, filename)


@writing_bp.route('/api/writing/small/correct', methods=['POST'])
def small_writing_correct():
    data = request.json or {}
    question = data.get('question_text', '')
    target = data.get('target_chinese', '')
    translation = data.get('user_translation', '')
    reference = data.get('standard_reference', '')

    if not translation.strip():
        return jsonify({'error': '翻译内容不能为空'}), 400

    cfg = load_prompt('writing_small_correct')
    user_prompt = cfg['user_prompt'].format(
        question=question,
        target=target,
        reference=reference,
        translation=translation,
    )

    try:
        api_key = os.getenv('DEER_API_KEY')
        resp = requests.post(
            cfg['api_url'],
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': cfg['model'],
                'messages': [
                    {'role': 'system', 'content': cfg['system_prompt']},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': cfg['temperature']
            },
            timeout=cfg.get('timeout', 30)
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


@writing_bp.route('/api/writing/small/save_practice', methods=['POST'])
def small_save_practice():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    data = request.json or {}
    save_to_review = data.get('save_to_review', False)

    records = _load_small_practice(username)
    record = {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'chart_type': data.get('chart_type', ''),
        'chart_subtype': data.get('chart_subtype', ''),
        'example_name': data.get('example_name', ''),
        'question': data.get('question', ''),
        'section_name': data.get('section_name', ''),
        'sentence_tags': data.get('sentence_tags', []),
        'target_chinese': data.get('target_chinese', ''),
        'user_translation': data.get('user_translation', ''),
        'score': data.get('score', ''),
        'feedback': data.get('feedback', {}),
        'native_version': data.get('native_version', ''),
        'in_review': save_to_review
    }
    records.insert(0, record)
    _save_small_practice(username, records)
    return jsonify({'success': True, 'id': record['id']})


@writing_bp.route('/api/writing/small/practice_history', methods=['GET'])
def small_practice_history():
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_small_practice(username)

    chart_type_filter = request.args.get('chart_type', '')
    review_records = [r for r in records if r.get('in_review', True)]
    if chart_type_filter:
        review_records = [r for r in review_records if r.get('chart_type') == chart_type_filter]

    # Three-level grouping: chart_type → example_name → sentence_key
    grouped = {}
    for r in review_records:
        ct = r.get('chart_type', '未分类')
        ex_name = r.get('example_name', '未知例题')
        section = r.get('section_name', '')
        target = r.get('target_chinese', '')
        sent_key = f"{section}||{target}"

        if ct not in grouped:
            grouped[ct] = {'avg_score': 0, 'count': 0, 'examples': {}}
        if ex_name not in grouped[ct]['examples']:
            grouped[ct]['examples'][ex_name] = {'avg_score': 0, 'count': 0, 'sentences': {}}
        if sent_key not in grouped[ct]['examples'][ex_name]['sentences']:
            grouped[ct]['examples'][ex_name]['sentences'][sent_key] = {
                'section_name': section,
                'target_chinese': target,
                'records': []
            }
        grouped[ct]['examples'][ex_name]['sentences'][sent_key]['records'].append(r)

    # Compute stats at each level
    def _avg(scores_list):
        vals = []
        for s in scores_list:
            try:
                vals.append(float(s))
            except (ValueError, TypeError):
                pass
        return round(sum(vals) / len(vals), 1) if vals else 0

    for ct in grouped:
        ct_scores = []
        ct_count = 0
        for ex_name in grouped[ct]['examples']:
            ex_info = grouped[ct]['examples'][ex_name]
            ex_scores = []
            ex_count = 0
            for sent_key in ex_info['sentences']:
                recs = ex_info['sentences'][sent_key]['records']
                ex_count += len(recs)
                ex_scores.extend(rec.get('score', '') for rec in recs)
            ex_info['avg_score'] = _avg(ex_scores)
            ex_info['count'] = ex_count
            ct_scores.extend(ex_scores)
            ct_count += ex_count
        grouped[ct]['avg_score'] = _avg(ct_scores)
        grouped[ct]['count'] = ct_count

    return jsonify(grouped)


@writing_bp.route('/api/writing/small/delete_practice/<record_id>', methods=['POST'])
def small_delete_practice(record_id):
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_small_practice(username)
    records = [r for r in records if r['id'] != record_id]
    _save_small_practice(username, records)
    return jsonify({'success': True})


@writing_bp.route('/api/writing/small/practice_progress', methods=['GET'])
def small_practice_progress():
    """返回小作文各图表类型、各例题的句子级完成进度（含历史记录详情）"""
    token = request.headers.get('Authorization', '').replace('Bearer ', '')
    if not is_token_valid(token):
        return jsonify({'error': '未登录'}), 401
    tokens = load_tokens()
    username = tokens.get(token, {}).get('username', 'anonymous')
    records = _load_small_practice(username)

    # Collect full records per sentence (like big essay practice_progress)
    completed = {}
    for r in records:
        if not r.get('in_review', True):
            continue
        key = f"{r.get('chart_type', '')}||{r.get('example_name', '')}||{r.get('target_chinese', '')}"
        if key not in completed:
            completed[key] = []
        completed[key].append({
            'score': r.get('score', ''),
            'user_translation': r.get('user_translation', ''),
            'feedback': r.get('feedback', {}),
            'timestamp': r.get('timestamp', '')
        })

    parsed = _parse_small_writing_md()
    progress = {}
    for ti, ct in enumerate(parsed['chart_types']):
        type_total = 0
        type_done = 0
        examples = {}
        for ei, ex in enumerate(ct['examples']):
            ex_total = 0
            ex_done = 0
            sent_status = []
            sent_idx = 0
            for section in ex['sections']:
                for sent in section['sentences']:
                    key = f"{ct['name']}||{ex['name']}||{sent['translation']}"
                    scores = completed.get(key, [])
                    is_done = len(scores) > 0
                    if is_done:
                        ex_done += 1
                    sent_status.append(scores if is_done else None)
                    sent_idx += 1
                    ex_total += 1
            type_total += ex_total
            type_done += ex_done
            examples[str(ei)] = {
                'total': ex_total,
                'done': ex_done,
                'sentences': sent_status
            }
        progress[str(ti)] = {
            'total': type_total,
            'done': type_done,
            'examples': examples
        }

    return jsonify(progress)


# ===================== 页面路由 =====================

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

    cfg = load_prompt('writing_correct')
    user_prompt = cfg['user_prompt'].format(
        question=question,
        target=target,
        reference=reference,
        translation=translation,
    )

    try:
        api_key = os.getenv('DEER_API_KEY')
        resp = requests.post(
            cfg['api_url'],
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
            json={
                'model': cfg['model'],
                'messages': [
                    {'role': 'system', 'content': cfg['system_prompt']},
                    {'role': 'user', 'content': user_prompt}
                ],
                'temperature': cfg['temperature']
            },
            timeout=cfg.get('timeout', 30)
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

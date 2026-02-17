from flask import Blueprint, request, jsonify, send_file, send_from_directory
import os, json, re
from werkzeug.wrappers import Response

from core import READING_DIR

reading_bp = Blueprint('reading', __name__)


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


@reading_bp.route('/list_reading', methods=['GET'])
def list_reading():
    """返回阅读真题目录结构与可用文件（HTML/PDF）。"""
    data = build_reading_index()
    return jsonify(data)


@reading_bp.route('/reading_exam/<path:subpath>')
def serve_reading_file(subpath):
    """提供阅读真题静态文件（HTML/PDF）。"""
    return send_from_directory(READING_DIR, subpath)


@reading_bp.route('/reading')
def reading_page():
    return send_file('templates/reading.html')


@reading_bp.route('/reading_view/<path:subpath>')
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

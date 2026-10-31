"""沙盒里没有翻译接口：把卡在「润色翻译失败」的九分学长篇用 transcript.json 补成完成（译文是编的）。
用法: python3 jiufen_fake_translate.py <沙盒目录>
"""
import json, os, sys
LR = os.path.join(sys.argv[1], 'listening_review')
path = os.path.join(LR, 'demo_projects.json')
projects = json.load(open(path))
for p in projects:
    if p.get('source_type') == 'jiufen' and p['status'] == 'error' and p.get('error_phase') == 'polish':
        d = os.path.join(LR, p['id'])
        tr = json.load(open(os.path.join(d, 'transcript.json')))
        segs = [dict(s, translation=f'（编的译文 {s["id"]}）') for s in tr['segments']]
        json.dump({'segments': segs, 'starred_segments': [], 'vocab_annotations': [], 'notes': [], 'error_tags': {}},
                  open(os.path.join(d, 'data.json'), 'w'), ensure_ascii=False)
        p.update(status='completed', error=None, error_phase=None)
        print('completed', p['id'], p['title'], sorted(os.listdir(d)))
json.dump(projects, open(path, 'w'), ensure_ascii=False)

"""九分学长 JSON 导入的浏览器检查用数据：把 tests/fixtures 里编造的两份 JSON 配上 say 合成的音频。

按合成出来的时长重排每句的起止时间；看题那句前面空 25 秒，并把这段静音并进 "Now"（真实数据就是这样）。
音频和 JSON 都写进 <沙盒>/static/e2e/，JSON 里的音频链接指向沙盒服务自己（serve.sh 只放行本机）。
另外造一份「第二次做同一篇」的 JSON（换 attempt id、第 3 题改对、只留一处划线），测再导入。
用法: python3 jiufen_data.py <沙盒目录> [沙盒端口，默认 5073]
"""
import json, os, subprocess, sys, tempfile

if len(sys.argv) not in (2, 3):
    sys.exit('用法: python3 jiufen_data.py <沙盒目录> [端口]')
SB = os.path.abspath(sys.argv[1])
REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if os.path.exists(os.path.join(SB, '.git')) or SB == REPO or not os.path.exists(os.path.join(SB, 'app.py')):
    sys.exit(f'{SB} 不像沙盒副本（要有 app.py、不能是 git 仓库本身）')
OUT = os.path.join(SB, 'static', 'e2e')
BASE = f"http://127.0.0.1:{sys.argv[2] if len(sys.argv) == 3 else 5073}/static/e2e"
os.makedirs(OUT, exist_ok=True)

def dur(path):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                                capture_output=True, text=True).stdout.strip())

def synth(texts, out_mp3):
    tmp = tempfile.mkdtemp()
    pieces, times, t = [], [], 0.0
    def silence(sec):
        p = os.path.join(tmp, f's{len(pieces)}.wav')
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=22050:cl=mono', '-t', str(sec), p], check=True)
        pieces.append(p)
    silence(1.0); t = 1.0
    for i, text in enumerate(texts):
        if text.startswith('Now listen'):
            silence(25.0)
            gap_start = t
            t += 25.0
        else:
            gap_start = None
        a = os.path.join(tmp, f'a{i}.aiff'); w = os.path.join(tmp, f'a{i}.wav')
        subprocess.run(['say', '-v', 'Daniel' if i % 2 else 'Samantha', '-o', a, text], check=True)
        subprocess.run(['ffmpeg', '-loglevel', 'error', '-i', a, '-ar', '22050', '-ac', '1', w], check=True)
        d = dur(w)
        pieces.append(w)
        times.append((gap_start if gap_start is not None else t, t, t + d))   # (句子在 JSON 里的开头, 真开口, 结束)
        t += d
        silence(0.5); t += 0.5
    lst = os.path.join(tmp, 'list.txt')
    with open(lst, 'w') as f:
        f.writelines(f"file '{p}'\n" for p in pieces)
    subprocess.run(['ffmpeg', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst, '-c:a', 'libmp3lame', '-q:a', '6', out_mp3], check=True)
    return times

def retime(part, name):
    art = json.loads(part['articleJson'])
    texts = [s['sentences'][0]['text'] for s in art['segments']]
    times = synth(texts, os.path.join(OUT, name))
    for seg, (st, speak, en) in zip(art['segments'], times):
        st, speak, en = round(st, 2), round(speak, 2), round(en, 2)
        seg['start_time'], seg['end_time'] = st, en
        s = seg['sentences'][0]; s['start_time'], s['end_time'] = st, en
        words = [w for w in seg['words'] if w['text'].strip()]
        step = (en - speak) / max(1, len(words))
        k = 0
        for w in seg['words']:
            if not w['text'].strip():
                continue
            w['start_time'] = st if k == 0 else round(speak + k * step, 2)
            w['end_time'] = round(speak + (k + 1) * step, 2)
            k += 1
    part['articleJson'] = json.dumps(art, ensure_ascii=False)
    part['audioUrl'] = f'{BASE}/{name}'

single = json.load(open(f'{REPO}/tests/fixtures/jiufen_listening_single.json'))
retime(single['data']['attempt']['parts'][0], 'riverside.mp3')
json.dump(single, open(f'{OUT}/e2e_single.json', 'w'), ensure_ascii=False, indent=1)
mixed = json.load(open(f'{REPO}/tests/fixtures/jiufen_listening_mixed.json'))
retime(mixed['data']['parts'][0], 'ferry.mp3')
retime(mixed['data']['parts'][1], 'beekeeping.mp3')
json.dump(mixed, open(f'{OUT}/e2e_mixed.json', 'w'), ensure_ascii=False, indent=1)
# 第二次做同一篇：换一个 attempt id，第 3 题改对，只留一处划线
again = json.load(open(f'{OUT}/e2e_single.json'))
att = again['data']['attempt']; att['id'] = '9100000000000000599'; att['submittedAt'] = '2026-10-31 09:00:00'
q3 = att['parts'][0]['groups'][0]['questions'][2]; q3['userAnswer'], q3['state'] = 'mill', '1'
again['data']['annotationSnapshot']['annotations'] = again['data']['annotationSnapshot']['annotations'][:1]
json.dump(again, open(f'{OUT}/e2e_single_again.json', 'w'), ensure_ascii=False, indent=1)
for n in ('riverside.mp3', 'ferry.mp3', 'beekeeping.mp3'):
    print(n, round(dur(f'{OUT}/{n}'), 2))

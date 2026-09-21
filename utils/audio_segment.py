"""按长静音把音频切段，供 ASR 逐段转录。

为什么要切：雅思听力每段中间都有 20~30 秒的「看题静音」，Whisper 的滚动解码
扛不住——解码器在那里崩坏后会退化成均匀时间戳，并把自己的输出反复喂回去，
锁进重复循环。实测线上 48 条音频里，4 次循环全部发生在有中段长静音的音频上，
12 条没有长静音的音频零循环。

做法：在长静音处把音频切开，长静音本身两边都不要，首尾的长静音直接裁掉。
这样每一段都不必「穿过」静音，一段崩了也影响不到别的段。

为什么用响度而不是 VAD：这些停顿实测是 -91dB（16-bit 本底，字面意义的全零），
不是低电平人声，神经 VAD 给不出比阈值法更好的边界。等哪天要支持用户自录音频
（停顿里有真实房间声）再换。
"""
import os
import re
import shutil
import subprocess
import tempfile

# 认定为「看题停顿」的时长下限；比这短的是说话人换气，是 Whisper 的断句线索，必须留着
LONG_SILENCE = 8.0
# 切点两侧各留一点余量，避免削掉词头词尾
EDGE_PAD = 0.30
# 比这还短的段并回相邻段：Whisper 在短片段上特别容易幻觉
MIN_CHUNK = 15.0
# 静音判定电平。真题停顿是 -91dB，-40dB 有极大余量
SILENCE_NOISE = '-40dB'


class FFmpegUnavailable(RuntimeError):
    """ffmpeg / ffprobe 不可用，调用方应回退到整篇转录。"""


def _run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError as e:
        raise FFmpegUnavailable(str(e)) from e


def probe_duration(path):
    out = _run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', path])
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def detect_silences(path, noise=SILENCE_NOISE, min_dur=1.0):
    """返回 [(起, 止)]，单位秒。"""
    proc = _run(['ffmpeg', '-hide_banner', '-nostats', '-i', path,
                 '-af', f'silencedetect=noise={noise}:d={min_dur}', '-f', 'null', '-'])
    out, start = [], None
    for line in proc.stderr.splitlines():
        m = re.search(r'silence_start:\s*([-\d.]+)', line)
        if m:
            start = max(0.0, float(m.group(1)))
            continue
        m = re.search(r'silence_end:\s*([\d.]+)', line)
        if m and start is not None:
            out.append((start, float(m.group(1))))
            start = None
    return out


def plan_segments(path):
    """规划切段，返回 ([(起, 止), ...], 整篇时长)。

    长静音整段剔除——不要在静音「中点」切，那样会把半截静音留在下一段开头，
    而段首静音本身就是幻觉诱因。
    """
    total = probe_duration(path)
    if total <= 0:
        return [], 0.0

    sil = detect_silences(path)
    longs = [(a, b) for a, b in sil if b - a >= LONG_SILENCE]

    # 掐头去尾：紧贴音频两端的静音不是停顿是空白，整段丢掉。
    # Whisper 在纯静音上会凭空生成 "Thank you for watching." 这类训练残留。
    lo, hi = 0.0, total
    lead = [s for s in sil if s[0] <= 0.5]
    if lead:
        lo = max(lo, lead[0][1] - EDGE_PAD)
    trail = [s for s in sil if s[1] >= total - 0.5]
    if trail:
        hi = min(hi, trail[0][0] + EDGE_PAD)
    if hi - lo < MIN_CHUNK:
        return [(0.0, total)], total

    inner = [(a, b) for a, b in longs if a > lo + 1.0 and b < hi - 1.0]
    segs, pos = [], lo
    for a, b in inner:
        end = min(a + EDGE_PAD, hi)
        if end - pos >= 1.0:
            segs.append((pos, end))
        pos = max(pos, b - EDGE_PAD)
    if hi - pos >= 1.0:
        segs.append((pos, hi))

    # 过短的段并回前一段
    merged = []
    for s in segs:
        if merged and s[1] - s[0] < MIN_CHUNK:
            merged[-1] = (merged[-1][0], s[1])
        else:
            merged.append(s)
    return (merged or [(0.0, total)]), total


def cut(path, start, end, out_path):
    """流拷贝切片，不重编码。实测误差 ~17ms，各段时长之和与原文件相差微秒级。

    out_path 必须沿用源文件的扩展名：`-c copy` 不转码，把 wav 的 PCM 塞进 .mp3
    容器 ffmpeg 会直接拒绝（Invalid audio stream），而上传是允许 wav/m4a/webm 的。
    """
    res = _run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', path,
                '-ss', f'{start:.3f}', '-to', f'{end:.3f}', '-c', 'copy', out_path])
    if res.returncode != 0 or not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
        raise RuntimeError(f'ffmpeg 切片失败 [{start:.1f}, {end:.1f}]: {res.stderr[-200:]}')
    return out_path


def detect_loop(segments, min_run=4):
    """检测 ASR 重复循环，返回 (最长重复句数, 周期, 起始下标)。

    周期要查到 6：Health Club 那次是三句一轮（Oh good / sauna / keen on that）
    循环了 20 轮，只查周期 1 会完全漏掉。
    """
    texts = [re.sub(r'[^a-z0-9]+', '', (s.get('text') or '').lower()) for s in segments]
    best = (0, 0, 0)
    for k in range(1, 7):
        cur, start = 0, 0
        for i in range(k, len(texts)):
            if texts[i] and texts[i] == texts[i - k]:
                if cur == 0:
                    start = i - k
                cur += 1
                if cur > best[0]:
                    best = (cur, k, start)
            else:
                cur = 0
    return best if best[0] >= min_run else (0, 0, 0)


def transcribe_segmented(path, call_asr, retry_offset=2.0):
    """切段 → 逐段转录 → 时间戳回填原始时间轴 → id 全局重编号。

    call_asr(path) -> (result, error)，result 形如 {'segments': [...], 'duration': x}。

    串行而非并发：限流窗口很窄（实测约 3 请求），并发只会自己把自己打成 429。
    """
    try:
        segs, total = plan_segments(path)
    except FFmpegUnavailable:
        return call_asr(path)

    if len(segs) <= 1:
        result, error = call_asr(path)
        if result:
            result['duration'] = total or result.get('duration', 0)
        return result, error

    ext = os.path.splitext(path)[1].lower() or '.mp3'
    tmpdir = tempfile.mkdtemp(prefix='lr_seg_')
    try:
        merged = []
        for i, (a, b) in enumerate(segs):
            chunk = cut(path, a, b, os.path.join(tmpdir, f'seg{i:02d}{ext}'))
            result, error = call_asr(chunk)
            if error:
                return None, f'第 {i + 1}/{len(segs)} 段（{a:.0f}-{b:.0f}s）转录失败: {error}'

            chunk_segs = result.get('segments') or []
            # 该段崩了就挪个起点重切一次：Whisper 对起始偏移很敏感，换个对齐往往就正常了
            if detect_loop(chunk_segs)[0]:
                a2 = min(a + retry_offset, b - MIN_CHUNK)
                if a2 > a:
                    retry_chunk = cut(path, a2, b, os.path.join(tmpdir, f'seg{i:02d}r{ext}'))
                    retry_result, retry_error = call_asr(retry_chunk)
                    if not retry_error and not detect_loop(retry_result.get('segments') or [])[0]:
                        chunk_segs, a = retry_result['segments'], a2
                if detect_loop(chunk_segs)[0]:
                    n, k, _ = detect_loop(chunk_segs)
                    return None, (f'第 {i + 1}/{len(segs)} 段（{a:.0f}-{b:.0f}s）'
                                  f'检测到 ASR 重复循环（{n} 句，周期 {k}），已重试仍未恢复')

            for s in chunk_segs:
                merged.append({
                    'id': len(merged),
                    'start': round(s['start'] + a, 3),
                    'end': round(s['end'] + a, 3),
                    'text': (s.get('text') or '').strip(),
                })

        if not merged:
            return None, '切段转录未产出任何字幕'

        # 跨段总检只是兜底：每段已经单独查过，真正的解码循环不会跨独立请求发生。
        # 阈值放宽到 8，避免相邻段各有几句「Oh, good.」被拼成假循环——误报会让
        # 整个项目报错，而 ASR 是确定性的，用户点重试也出不来。
        n, k, _ = detect_loop(merged, min_run=8)
        if n:
            return None, f'合并后仍检测到 ASR 重复循环（{n} 句，周期 {k}）'

        # duration 必须是整篇时长：播放器放的是完整音频，裁掉的只是送给 ASR 的部分
        return {'segments': merged, 'duration': total}, None
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

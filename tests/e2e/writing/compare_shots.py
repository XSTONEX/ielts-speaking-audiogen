"""逐张比较两套桌面截图（desktop_shots.js 的输出），报告哪些不一样、差在哪一块。

用法：python compare_shots.py <改版前目录> <改版后目录> [差异图输出目录]
全部一样时退出码 0；有不一样的退出码 1，差异图（不一样的像素标红）写到第三个参数指定的目录。
"""
import os
import sys

from PIL import Image, ImageChops

if len(sys.argv) < 3:
    sys.exit('用法：python compare_shots.py <改版前目录> <改版后目录> [差异图输出目录]')
a_dir, b_dir = sys.argv[1], sys.argv[2]
out = sys.argv[3] if len(sys.argv) > 3 else ''
if out:
    os.makedirs(out, exist_ok=True)

names = sorted(f for f in os.listdir(a_dir) if f.endswith('.png'))
missing = sorted(set(f for f in os.listdir(b_dir) if f.endswith('.png')) ^ set(names))
bad = 0
for name in names:
    pb = os.path.join(b_dir, name)
    if not os.path.exists(pb):
        continue
    a = Image.open(os.path.join(a_dir, name)).convert('RGB')
    b = Image.open(pb).convert('RGB')
    if a.size != b.size:
        bad += 1
        print(f'DIFF {name}: 尺寸不同 {a.size} vs {b.size}')
        continue
    diff = ImageChops.difference(a, b)
    bbox = diff.getbbox()
    if not bbox:
        print(f'SAME {name}')
        continue
    bad += 1
    px = sum(1 for p in diff.getdata() if p != (0, 0, 0))
    delta = max(hi for lo, hi in diff.getextrema())
    print(f'DIFF {name}: {px} 个像素不同，范围 {bbox}，单通道最大差 {delta}')
    if out:
        mask = diff.convert('L').point(lambda v: 255 if v else 0)
        red = Image.new('RGB', a.size, (255, 0, 0))
        Image.composite(red, b, mask).save(os.path.join(out, name))
for name in missing:
    bad += 1
    print(f'MISSING {name}: 只有一边有')
print(f'合计 {len(names)} 张，不一样 {bad} 张')
sys.exit(1 if bad else 0)

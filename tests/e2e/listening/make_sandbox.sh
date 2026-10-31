#!/bin/bash
# 把当前工作区的代码（不含 .gitignore 里的数据目录和 .env）复制到一个新目录，再灌编造的听力数据。
# 用法: bash tests/e2e/listening/make_sandbox.sh <沙盒目录>
set -euo pipefail
SB="${1:?用法: make_sandbox.sh <沙盒目录>}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
if [ -e "$SB" ] && [ -n "$(ls -A "$SB")" ]; then
  echo "$SB 已存在且不是空目录；换一个新目录，或者只重跑 seed.py 刷新数据" >&2
  exit 1
fi
mkdir -p "$SB"
git -C "$REPO" ls-files -co --exclude-standard | rsync -a --files-from=- "$REPO/" "$SB/"
python3 "$HERE/seed.py" "$SB"
echo "沙盒就绪：$SB"

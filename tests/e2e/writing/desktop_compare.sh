#!/usr/bin/env bash
# 桌面像素对比：改版前（比如 mobile/base）和改版后的代码各起一个沙盒服务器，
# 用同一份假数据、同一串操作截图，逐张比像素。桌面（>820px）应该一张都不差。
# 用法：desktop_compare.sh <改版前沙盒> <改版后沙盒> <输出目录>
#   两个沙盒的服务器要先起好：BEFORE_URL（默认 http://localhost:5132）、AFTER_URL（默认 http://localhost:5131）
#   环境变量：PLAYWRIGHT_CORE、NODE、PYTHON、ENGINES（默认 "chromium webkit"）、WIDTHS（默认 "1280 1440"）
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
[ $# -ge 3 ] || { echo "用法：desktop_compare.sh <改版前沙盒> <改版后沙盒> <输出目录>"; exit 1; }
BEFORE="$(cd "$1" && pwd)"; AFTER="$(cd "$2" && pwd)"; OUT="$3"
mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)"
PY="${PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PY" ] || PY="$(cd "$(git -C "$REPO" rev-parse --git-common-dir)/.." && pwd)/.venv/bin/python"
NODE="${NODE:-node}"
BEFORE_URL="${BEFORE_URL:-http://localhost:5132}"
AFTER_URL="${AFTER_URL:-http://localhost:5131}"

# 一份假数据，两边用完全一样的拷贝（记录里的时间是按生成那一刻往前推的，不能各自生成）
"$PY" "$HERE/make_fake_data.py" "$AFTER" > /dev/null || exit 1
GOLD="$OUT/_data"
rm -rf "$GOLD"; mkdir -p "$GOLD"
for d in writing_correction users.json tokens.json _e2e; do cp -R "$AFTER/$d" "$GOLD/"; done
reset() { for d in writing_correction users.json tokens.json _e2e; do rm -rf "${1:?}/$d"; cp -R "$GOLD/$d" "$1/"; done; }

fail=0
for engine in ${ENGINES:-chromium webkit}; do
  for w in ${WIDTHS:-1280 1440}; do
    for side in before after; do
      if [ $side = before ]; then sb="$BEFORE"; url="$BEFORE_URL"; else sb="$AFTER"; url="$AFTER_URL"; fi
      reset "$sb"
      rm -rf "$OUT/$engine-$w-$side"
      WP_SANDBOX="$sb" WP_BASE_URL="$url" WP_SHOTS="$OUT/$engine-$w-$side" ENGINE=$engine WIDTH=$w \
        "$NODE" "$HERE/desktop_shots.js" | grep -E 'SHOTS|CRASH|FAIL|pageerror|console.error' || true
    done
    echo "== $engine $w"
    "$PY" "$HERE/compare_shots.py" "$OUT/$engine-$w-before" "$OUT/$engine-$w-after" "$OUT/$engine-$w-diff" > "$OUT/$engine-$w.txt"
    rc=$?
    grep -vE '^SAME' "$OUT/$engine-$w.txt"
    [ $rc = 0 ] || fail=1
  done
done
reset "$AFTER"
if [ $fail = 0 ]; then echo "桌面截图全部一致"; else echo "有不一致：差异图在 $OUT/*-diff"; fi
exit $fail

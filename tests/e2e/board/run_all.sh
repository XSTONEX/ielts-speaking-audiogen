#!/usr/bin/env bash
# 从头跑一遍学习交流小天地的浏览器测试：重建假数据 → 端口上没有服务器就起一个沙盒服务器 → 01–06 → 再重建假数据 → 07。
# 用法：run_all.sh <沙盒目录> [chromium|webkit]
# 环境变量（都可不设）：PLAYWRIGHT_CORE、MB_SHOTS（截图目录）、PORT（默认 5066）、PYTHON、NODE
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
[ -n "${1:-}" ] || { echo "用法：run_all.sh <沙盒目录> [chromium|webkit]"; exit 1; }
SB="$(cd "$1" && pwd)" || exit 1
export MB_SANDBOX="$SB"
export ENGINE="${2:-${ENGINE:-chromium}}"
PORT="${PORT:-5066}"
export MB_BASE_URL="${MB_BASE_URL:-http://localhost:$PORT}"
PY="${PYTHON:-$REPO/.venv/bin/python}"
NODE="${NODE:-node}"

up() { curl -s -o /dev/null --noproxy '*' "$MB_BASE_URL/login"; }

"$PY" "$HERE/make_fake_data.py" "$SB" || exit 1

server_pid=""
if ! up; then
  PORT="$PORT" "$HERE/run_sandbox.sh" "$SB" > "$SB/_e2e_server.log" 2>&1 &
  server_pid=$!
  trap 'kill "$server_pid" 2>/dev/null' EXIT
  for _ in $(seq 50); do up && break; sleep 0.2; done
  up || { echo "沙盒服务器没起来，看 $SB/_e2e_server.log"; exit 1; }
fi

fail=0
for t in 01_render 02_post_and_quiz 03_invitees_and_comments 04_misc 05_phone 06_dark; do
  echo "== $t ($ENGINE)"
  "$NODE" "$HERE/$t.js" || fail=1
done
# 07 要在刚建好的数据上跑（04 已经把 msg_fake_0002 删了）
"$PY" "$HERE/make_fake_data.py" "$SB" > /dev/null || exit 1
echo "== 07_delete_cascade ($ENGINE)"
"$NODE" "$HERE/07_delete_cascade.js" || fail=1

if [ "$fail" = 0 ]; then echo "全部通过（$ENGINE）"; else echo "有失败（$ENGINE）：往上找 FAIL / ERRORS / CRASH"; fi
exit "$fail"

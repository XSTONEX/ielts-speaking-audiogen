#!/usr/bin/env bash
# 从头跑一遍写作页的手机测试：重建假数据 → 端口上没有服务器就起一个沙盒服务器 → phone.js。
# 用法：run_all.sh <沙盒目录> [webkit|chromium]
# 环境变量（都可不设）：PLAYWRIGHT_CORE、WP_SHOTS（截图目录）、PORT（默认 5131）、PYTHON、NODE
set -uo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
[ -n "${1:-}" ] || { echo "用法：run_all.sh <沙盒目录> [webkit|chromium]"; exit 1; }
SB="$(cd "$1" && pwd)" || exit 1
export WP_SANDBOX="$SB"
export ENGINE="${2:-${ENGINE:-webkit}}"
PORT="${PORT:-5131}"
export WP_BASE_URL="${WP_BASE_URL:-http://localhost:$PORT}"
PY="${PYTHON:-$REPO/.venv/bin/python}"
[ -x "$PY" ] || PY="$(cd "$(git -C "$REPO" rev-parse --git-common-dir)/.." && pwd)/.venv/bin/python"
NODE="${NODE:-node}"

up() { curl -s -o /dev/null --noproxy '*' "$WP_BASE_URL/login"; }

"$PY" "$HERE/make_fake_data.py" "$SB" > /dev/null || exit 1

server_pid=""
if ! up; then
  PORT="$PORT" "$HERE/run_sandbox.sh" "$SB" > "$SB/_e2e_server.log" 2>&1 &
  server_pid=$!
  trap 'kill "$server_pid" 2>/dev/null' EXIT
  for _ in $(seq 50); do up && break; sleep 0.2; done
  up || { echo "沙盒服务器没起来，看 $SB/_e2e_server.log"; exit 1; }
fi

echo "== phone ($ENGINE)"
"$NODE" "$HERE/phone.js"
rc=$?
if [ "$rc" = 0 ]; then echo "全部通过（$ENGINE）"; else echo "有失败（$ENGINE）：往上找 FAIL / ERRORS / CRASH"; fi
exit "$rc"

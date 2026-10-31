#!/bin/sh
# 在沙盒目录里启动网站，所有对外请求都堵死、API key 全部置空，不会花钱也不会碰真实数据。
# 用法：tests/e2e/vocabulary/run_sandbox.sh <沙盒目录> [端口，默认 5174]
# Python 默认用仓库根目录的 .venv；在 git worktree 里没有 .venv 时，用 PYTHON=/path/to/.venv/bin/python 指定。
set -eu

if [ $# -lt 1 ]; then
  echo "用法：$0 <沙盒目录> [端口]" >&2
  exit 2
fi

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
SANDBOX=$(cd "$1" && pwd)
PORT=${2:-5174}
if [ -z "${PYTHON:-}" ]; then
  if [ -x "$ROOT/.venv/bin/python" ]; then PYTHON="$ROOT/.venv/bin/python"; else PYTHON=python3; fi
fi

if [ ! -f "$SANDBOX/app.py" ] || [ ! -d "$SANDBOX/vocabulary_book.pristine" ]; then
  echo "$SANDBOX 不像是 make_sandbox.sh 建的沙盒" >&2
  exit 2
fi

cd "$SANDBOX"
export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9
export NO_PROXY= no_proxy=
export DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= DEEPSEEK_API_KEY= PROXY_URL=
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -c "from app import app; app.run(port=$PORT)"

#!/bin/sh
# 在沙盒目录里起应用：网络走一个不存在的代理（发不出去）、API key 全空，不会花钱，也碰不到真实数据。
# 用法：PYTHON=<项目 .venv/bin/python> run_sandbox.sh <沙盒目录> [端口，默认 5071]
set -e
SANDBOX="$1"
PORT="${2:-5071}"
if [ -z "$SANDBOX" ] || [ ! -f "$SANDBOX/app.py" ]; then
  echo "用法：PYTHON=<.venv/bin/python> $0 <沙盒目录> [端口]（沙盒里要有 app.py）" >&2
  exit 2
fi
if [ -e "$SANDBOX/.git" ]; then
  echo "$SANDBOX 里有 .git，像是真实仓库而不是沙盒，不起" >&2
  exit 2
fi
PYTHON="${PYTHON:-python3}"

export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9
export NO_PROXY= no_proxy=
export DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= DEEPSEEK_API_KEY=
export PYTHONDONTWRITEBYTECODE=1

cd "$SANDBOX"
exec "$PYTHON" -c "from app import app; app.run(port=$PORT, debug=False)"

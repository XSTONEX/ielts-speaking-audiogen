#!/usr/bin/env bash
# 用沙盒目录里的代码和假数据启动网站：断网（代理指向关着的端口）、API key 全部清空，不会调用任何付费接口。
# 用法：run_sandbox.sh <沙盒目录>     端口默认 5066（PORT=xxxx 可改），Python 默认用仓库的 .venv（PYTHON=... 可改）
set -euo pipefail
SB="${1:-${MB_SANDBOX:-}}"
[ -n "$SB" ] || { echo "用法：run_sandbox.sh <沙盒目录>（或设置 MB_SANDBOX）"; exit 1; }
REPO="$(cd "$(dirname "$0")/../../.." && pwd)"
PY="${PYTHON:-$REPO/.venv/bin/python}"
cd "$SB"
[ ! -e .git ] || { echo "拒绝：$SB 是 git 仓库，请用仓库外的拷贝目录"; exit 1; }

export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9
export NO_PROXY= no_proxy=
export DEEPSEEK_API_KEY= DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= PROXY_URL=
export DEEPSEEK_BASE_URL=http://127.0.0.1:9 WILDAPI_BASE_URL=http://127.0.0.1:9
export PYTHONDONTWRITEBYTECODE=1
exec "$PY" -c "from app import app; app.run(port=${PORT:-5066}, threaded=True)"

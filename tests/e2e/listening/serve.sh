#!/bin/bash
# 在沙盒副本里起服务：代理指向一个没人监听的端口、所有 API key 置空，
# 所以不会调用任何付费接口（转录 / 翻译会直接失败），也碰不到真实数据。
# 用法: bash tests/e2e/listening/serve.sh <沙盒目录> [端口，默认 5073]
# 默认用仓库 .venv 里的 python（在 git worktree 里会找主仓库的 .venv），可用 PYTHON=... 覆盖。
set -euo pipefail
SB="$(cd "${1:?用法: serve.sh <沙盒目录> [端口]}" && pwd)"
PORT="${2:-5073}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
if [ -z "${PYTHON:-}" ]; then
  PYTHON="$REPO/.venv/bin/python"
  if [ ! -x "$PYTHON" ]; then
    MAIN="$(cd "$(git -C "$REPO" rev-parse --git-common-dir)/.." && pwd)"
    PYTHON="$MAIN/.venv/bin/python"
  fi
fi
if [ -e "$SB/.git" ]; then
  echo "$SB 是 git 仓库本身，不是沙盒副本" >&2
  exit 1
fi

export HTTPS_PROXY=http://127.0.0.1:9 HTTP_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9
export https_proxy=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9
# 只放行本机：九分学长导入的浏览器检查从沙盒服务自己下载音频；别的地址照样走不通的代理
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
export DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= GEMINI_API_KEY= OPENAI_API_KEY= DEEPSEEK_API_KEY=
export PYTHONDONTWRITEBYTECODE=1

cd "$SB"
exec "$PYTHON" -c "from app import app; app.run(port=$PORT, debug=False, threaded=True)"

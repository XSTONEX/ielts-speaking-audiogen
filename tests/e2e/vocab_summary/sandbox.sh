#!/usr/bin/env bash
# 「词汇汇总 + 登录」浏览器测试用的沙盒服务器。
#   ./sandbox.sh start <沙盒目录> [端口]   复制代码 → 造编造数据 → 后台启动服务器（默认端口 5073）
#   ./sandbox.sh stop  <沙盒目录>          停掉这个沙盒的服务器
#
# 为什么要这样：import app 会起后台线程，仓库根目录的 .env 里是真的付费 API key，
# 真数据也在仓库根目录（被 gitignore 的那些目录）。所以服务器只在沙盒里跑：
# 代码从 git ls-files 复制，不带 .env，不带数据；所有出站请求都指到一个不存在的代理（127.0.0.1:9），
# API key 全部置空，调不到任何付费接口。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
PY="${PYTHON:-$REPO/.venv/bin/python}"
cmd="${1:-}"
dir="${2:-}"
if [ -z "$cmd" ] || [ -z "$dir" ]; then sed -n '2,4p' "$0"; exit 2; fi

case "$cmd" in
start)
  port="${3:-5073}"
  mkdir -p "$dir"
  dir="$(cd "$dir" && pwd -P)"
  case "$dir/" in "$(cd "$REPO" && pwd -P)/"*) echo "沙盒不能放在仓库里面：$dir" >&2; exit 1;; esac
  if [ -e "$dir/.git" ] || [ -e "$dir/.env" ]; then echo "$dir 里有 .git 或 .env，不像沙盒，不动它" >&2; exit 1; fi
  if [ -f "$dir/server.pid" ] && kill -0 "$(cat "$dir/server.pid")" 2>/dev/null; then
    echo "这个沙盒的服务器已经在跑（pid $(cat "$dir/server.pid")），先 ./sandbox.sh stop $dir" >&2; exit 1
  fi
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "端口 $port 已经有程序在监听，换一个端口：./sandbox.sh start $dir <端口>" >&2; exit 1
  fi

  # 只复制代码（已跟踪 + 未跟踪但没被 ignore 的文件），不带 .env 和数据目录
  (cd "$REPO" && git ls-files -co --exclude-standard -z | while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done \
    | tar --null -T - -cf -) | tar -xf - -C "$dir"
  "$PY" "$HERE/make_fake_data.py" "$dir"

  dead=http://127.0.0.1:9
  (
    cd "$dir"
    env HTTPS_PROXY=$dead HTTP_PROXY=$dead ALL_PROXY=$dead https_proxy=$dead http_proxy=$dead all_proxy=$dead \
        NO_PROXY= no_proxy= PROXY_URL=$dead \
        DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= DEEPSEEK_API_KEY= \
        PYTHONDONTWRITEBYTECODE=1 \
        nohup "$PY" -c "from app import app; app.run(port=$port)" > "$dir/server.log" 2>&1 &
    echo $! > "$dir/server.pid"
  )
  for _ in $(seq 1 60); do
    if curl -s -o /dev/null "http://127.0.0.1:$port/login"; then break; fi
    sleep 0.5
  done
  if ! kill -0 "$(cat "$dir/server.pid")" 2>/dev/null || ! curl -s -o /dev/null "http://127.0.0.1:$port/login"; then
    echo "服务器没起来，看日志：$dir/server.log" >&2; tail -20 "$dir/server.log" >&2; exit 1
  fi
  echo
  echo "沙盒服务器已启动（pid $(cat "$dir/server.pid")，日志 $dir/server.log）。跑测试前设置："
  echo "  export E2E_BASE_URL=http://127.0.0.1:$port"
  echo "  export E2E_TOKEN_FILE=$dir/e2e_token.txt"
  ;;
stop)
  dir="$(cd "$dir" && pwd -P)"
  if [ -f "$dir/server.pid" ]; then
    kill "$(cat "$dir/server.pid")" 2>/dev/null || true
    rm -f "$dir/server.pid"
    echo "已停止 $dir 的沙盒服务器"
  else
    echo "$dir 里没有 server.pid，没有要停的" >&2
  fi
  ;;
*)
  sed -n '2,4p' "$0"; exit 2
  ;;
esac

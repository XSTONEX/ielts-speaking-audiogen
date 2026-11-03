#!/usr/bin/env bash
# 横屏手机检查：给九个模块各建一个沙盒（数据用各模块自己的造数据脚本），起服务，跑 landscape_e2e.js，跑完停服务。
#   tests/e2e/landscape/run.sh <工作目录> [webkit] [chromium]
# 环境变量：
#   CODE_FROM=<目录>   从别的检出复制被测的代码（比如 git archive main 解出来的目录），默认是本仓库
#   PORT_BASE=5600     九个服务用 PORT_BASE+1 … PORT_BASE+9（别落到 5060 / 5061）
#   PLAYWRIGHT_CORE    playwright-core 的路径；NODE 用哪个 node（要 ≥ 20）；PYTHON 用哪个 Python（默认仓库的 .venv）
#   LS_OUT             截图目录（默认 <工作目录>/out）
# 工作目录必须在仓库外面；里面已有的同名沙盒会被删掉重建。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(git -C "$HERE" rev-parse --show-toplevel)"
COMMON="$(cd "$(git -C "$HERE" rev-parse --git-common-dir)/.." && pwd)"
PY="${PYTHON:-$( [ -x "$REPO/.venv/bin/python" ] && echo "$REPO/.venv/bin/python" || echo "$COMMON/.venv/bin/python")}"
NODE="${NODE:-node}"
SRC="${CODE_FROM:-$REPO}"
PORT_BASE="${PORT_BASE:-5600}"
WORK="${1:-}"
if [ -z "$WORK" ]; then sed -n '2,9p' "$0"; exit 2; fi
shift
mkdir -p "$WORK"
WORK="$(cd "$WORK" && pwd -P)"
case "$WORK/" in "$(cd "$REPO" && pwd -P)/"*|"$(cd "$COMMON" && pwd -P)/"*) echo "工作目录不能放在仓库里面：$WORK" >&2; exit 1;; esac
E2E="$REPO/tests/e2e"
MODULES=(home speaking intensive vocab_summary listening vocabulary study_tips board writing)
PIDS=()

stop_all() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null || true; done; }
trap stop_all EXIT

copy_code() {   # 只复制代码（git 跟踪的 + 没被 ignore 的新文件），不带 .env 和数据
  local dst="$1"
  if git -C "$SRC" rev-parse --show-toplevel >/dev/null 2>&1; then
    (cd "$SRC" && git ls-files -co --exclude-standard -z | while IFS= read -r -d '' f; do [ -e "$f" ] && printf '%s\0' "$f"; done | tar --null -T - -cf -) | tar -xf - -C "$dst"
  else
    (cd "$SRC" && tar --exclude=.git --exclude=.env -cf - .) | tar -xf - -C "$dst"
  fi
}

seed() {   # 各模块自己的造数据脚本；登录凭证统一写成 <沙盒>/e2e_token.txt
  local m="$1" sb="$2" port="$3"
  case "$m" in
    home|speaking|intensive|vocab_summary) "$PY" "$E2E/$m/make_fake_data.py" "$sb" ;;
    board|writing) "$PY" "$E2E/$m/make_fake_data.py" "$sb"
      "$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["linxia"]["token"])' "$sb/_e2e/tokens.json" > "$sb/e2e_token.txt" ;;
    vocabulary) "$PY" "$E2E/vocabulary/make_fake_data.py" "$sb"
      (cd "$sb" && "$PY" -c "import core; open('e2e_token.txt', 'w').write(core.create_token('demo'))") ;;
    study_tips) "$PY" "$E2E/study_tips/make_fixtures.py" "$sb" --mint-token ;;
    listening) python3 "$E2E/listening/seed.py" "$sb" && python3 "$E2E/listening/jiufen_data.py" "$sb" "$port"
      "$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["demo"])' "$sb/e2e_tokens.json" > "$sb/e2e_token.txt" ;;
  esac
}

i=0
CONFIG="$WORK/config.json"
echo '{' > "$CONFIG"
for m in "${MODULES[@]}"; do
  i=$((i + 1))
  port=$((PORT_BASE + i))
  sb="$WORK/$m"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then echo "端口 $port 已被占用，换一个 PORT_BASE" >&2; exit 1; fi
  rm -rf "$sb"; mkdir -p "$sb"
  copy_code "$sb"
  seed "$m" "$sb" "$port" > "$sb/seed.log" 2>&1 || { echo "$m 造数据失败，看 $sb/seed.log" >&2; exit 1; }
  dead=http://127.0.0.1:9
  (
    cd "$sb"
    env HTTPS_PROXY=$dead HTTP_PROXY=$dead ALL_PROXY=$dead https_proxy=$dead http_proxy=$dead all_proxy=$dead \
        NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost PROXY_URL=$dead \
        DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= DEEPSEEK_API_KEY= GEMINI_API_KEY= OPENAI_API_KEY= \
        PYTHONDONTWRITEBYTECODE=1 \
        "$PY" -c "from app import app; app.run(port=$port, threaded=True)" > "$sb/server.log" 2>&1 &
    echo $! > "$sb/server.pid"
  )
  PIDS+=("$(cat "$sb/server.pid")")
  sep=','; [ "$i" = "${#MODULES[@]}" ] && sep=''
  printf '  "%s": { "base": "http://127.0.0.1:%s", "sandbox": "%s" }%s\n' "$m" "$port" "$sb" "$sep" >> "$CONFIG"
done
echo '}' >> "$CONFIG"

i=0
for m in "${MODULES[@]}"; do
  i=$((i + 1)); port=$((PORT_BASE + i))
  for _ in $(seq 1 80); do curl -s -o /dev/null "http://127.0.0.1:$port/login" && break; sleep 0.25; done
  curl -s -o /dev/null "http://127.0.0.1:$port/login" || { echo "$m 的服务没起来，看 $WORK/$m/server.log" >&2; exit 1; }
done

LS_CONFIG="$CONFIG" LS_OUT="${LS_OUT:-$WORK/out}" "$NODE" "$HERE/landscape_e2e.js" "$@"

#!/bin/sh
# 建一个单词本测试沙盒：把仓库里 git 跟踪的代码（工作区当前版本）拷到一个仓库外的目录，
# 再写进编造的数据。.env、真实数据目录都是 git 不跟踪的，不会被带过去。
# 用法：tests/e2e/vocabulary/make_sandbox.sh <沙盒目录>
set -eu

if [ $# -ne 1 ]; then
  echo "用法：$0 <沙盒目录（放在仓库外面）>" >&2
  exit 2
fi

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
mkdir -p "$1"
SANDBOX=$(cd "$1" && pwd)

case "$SANDBOX/" in
  "$ROOT"/*) rmdir "$SANDBOX" 2>/dev/null || true; echo "沙盒目录不能放在仓库里面：$SANDBOX" >&2; exit 2 ;;
esac

(cd "$ROOT" && git ls-files -z | tar --null -T - -cf -) | tar -xf - -C "$SANDBOX"
python3 "$HERE/make_fake_data.py" "$SANDBOX"
echo "沙盒建好了：$SANDBOX"

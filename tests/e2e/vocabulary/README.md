# 单词本浏览器测试

在沙盒里用编造的数据，把 `/vocabulary` 的每个功能实际点一遍：Chromium + WebKit，亮色 + 暗色，1280 和 390 两种宽度。

查的内容：
- 目录栏和排序：分类、子分类、自然排序。
- 加词、收藏、删除、隐藏释义（H 键）、查找。
- 子分类：新建、重命名、删除。
- 导入、导出 CSV/TXT/JSON，以及导出再导入的往返。
- 单词挑战：出题、1–4 键作答、退出确认、成绩记录、「再来一次」。
- 有道发音，有道取不到时退回旧 TTS 音频。
- 旧偏好设置能不能读、手机布局有没有横向溢出、控制台有没有报错。

不花 API 的钱，不碰真实数据：
- 沙盒是仓库外的一个目录，只拷 git 跟踪的代码。
- 数据由 `make_fake_data.py` 编出来，全是假的，账号是 `demo` / `not-a-real-password`。
- 服务器的对外请求全堵死，API key 全置空。

仓库是公开的：别把截图、真实数据或沙盒目录提交进来。

## 文件

| 文件 | 作用 |
|---|---|
| `make_sandbox.sh <沙盒目录>` | 把工作区里 git 跟踪的代码拷进沙盒，再调 `make_fake_data.py` 写数据 |
| `make_fake_data.py <沙盒目录>` | 只重写数据：`vocabulary_book/`、同样内容的 `vocabulary_book.pristine/`、`users.json`、空的 `tokens.json` |
| `run_sandbox.sh <沙盒目录> [端口]` | 堵掉代理、清空 key 后启动网站，默认端口 5174 |
| `vocabulary_e2e.js [chromium] [webkit]` | 测试本体，每一轮开始前把 `vocabulary_book` 重置成 `vocabulary_book.pristine` |

## 1. 建沙盒

沙盒必须放在仓库外面，脚本会拒绝仓库里的目录。代码改了以后要重新建一次，因为沙盒里是代码的拷贝。

```bash
tests/e2e/vocabulary/make_sandbox.sh /tmp/vocab-sandbox
```

## 2. 启动沙盒服务

默认用仓库根目录的 `.venv`。在 git worktree 里没有 `.venv`，要用 `PYTHON` 指到主仓库的那份：

```bash
PYTHON=/path/to/ielts-speaking-audiogen/.venv/bin/python tests/e2e/vocabulary/run_sandbox.sh /tmp/vocab-sandbox 5174
```

这个命令会一直占着终端，测试要在另一个终端里跑。

## 3. 跑测试（node 22）

仓库没装 node 依赖时，用 `PLAYWRIGHT_CORE` 指到别处装好的 `playwright-core`，WebKit 和 Chromium 要已经用 playwright 装过：

```bash
PATH=~/.nvm/versions/node/v22.23.1/bin:$PATH \
PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core \
VOCAB_E2E_SANDBOX=/tmp/vocab-sandbox \
node tests/e2e/vocabulary/vocabulary_e2e.js chromium webkit
```

最后一行是 `N/N passed`，退出码 0 表示全过。有失败的检查会以 `FAIL` 开头打出来。

环境变量：

| 变量 | 默认 | 说明 |
|---|---|---|
| `VOCAB_E2E_SANDBOX` | 必填 | 第 1 步建的沙盒目录 |
| `VOCAB_E2E_BASE` | `http://localhost:5174` | 沙盒服务地址 |
| `VOCAB_E2E_OUT` | 系统临时目录下的 `vocab-e2e` | 截图（`shots/`）、下载的导出文件、`e2e-results.json` |
| `VOCAB_E2E_USER` / `VOCAB_E2E_PASSWORD` | `demo` / `not-a-real-password` | 沙盒里的假账号 |
| `VOCAB_E2E_OFFLINE` | 不设 | 设成 `1` 就不连有道，发音请求换成本地生成的提示音，其余检查照跑 |
| `PLAYWRIGHT_CORE` | `playwright-core` | playwright-core 的路径 |

不设 `VOCAB_E2E_OFFLINE` 时，浏览器会真的去请求有道词典的发音。这个接口免费，但要能上网。

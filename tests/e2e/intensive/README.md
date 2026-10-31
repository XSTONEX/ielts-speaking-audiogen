# 文章精读浏览器测试

用真浏览器（Chromium + WebKit，也就是 Safari 的内核）把「文章精读」两个页面从头点一遍：

- `templates/intensive.html`（`/intensive`）：文章列表、阅读页、划词高亮、题目栏
- `templates/intensive_new.html`（`/intensive/new`）：导入九分学长 JSON、粘贴文本建文章
- 后端是 `routers/intensive_reading.py`

数据全是编的（`make_fake_data.py` 现造），服务器只在临时沙盒里跑，碰不到真数据，也调不到任何付费接口。

## 测了什么

| 套件 | 文件 | 内容 |
| --- | --- | --- |
| select | `suite_select.js` | 桌面划词。5 篇格式各不相同的文章（普通对照、含不间断空格、「第1段」小标题、emoji、普通）：已有高亮原样画回来（同一范围存了两次只画一个）；每篇取最多 6 个行首单词，用 5 种鼠标手势（从左边空白拖进来、往左拖出去、拖到上一行、从行间空隙拖、双击）和 3 种「端点落在元素上」的选区去选，都要弹出「高亮」浮层、文字正好是这个词、不出「请在同一段内」提示；最后给行首词存一条释义，刷新后原样回来；emoji 文章末尾的「微笑」也能存成高亮（页面按 UTF-16 下标发，服务器也按 UTF-16 长度查） |
| touch | `suite_touch.js` | 手机（390×844，真实触摸点击）。列表往下翻过再点卡片打开；长按选词 → 浮层在词下方、不出屏幕；高亮 → 释义框 → 保存，词汇数 +1；点高亮看释义气泡；长按高亮不弹删除确认；选中已有高亮 → 删除高亮；选区收起浮层跟着收；跨两行的选区只提示不弹浮层；词汇底部面板和「跳到原文」；「译文」开关刷新后还记得 |
| import | `suite_import.js` | `/intensive/new` 粘贴 `tests/fixtures/jiufen_reading_attempt.json`（编的「The Glass Bridge」，前后故意多带引号）：乱码给出说明、预览里的段数 / 句数 / 题数 / 划线数 / 成绩 / 用时 / 题型；沙盒没有翻译 key → 说明翻译失败 → 「不翻译，直接导入」；文章页：A–C 段标、8 句、5 题对错、`对 2 / 5`、用时、5 处做题划线；行首词照样能划、自己的高亮盖在划线上两样都在；定位原文、解析、你的答案 / 正确答案、只看错题、隐藏答案（刷新后还记得）、原题版式里的空格编号跳题、划线开关；带译文的导入文章（原文和题目下面都有中文，「译文」开关一起藏）；普通旧文章没有题目栏；列表卡片显示成绩；粘贴文本模式；手机上「原文 / 题目」两个标签，定位后切回题目还在原来的位置 |
| misc | `suite_misc.js` | 桌面和手机各一遍：删除文章先确认（取消就不删）；图片条缩略图、大图、Esc 关；改标题（桌面铅笔 / 手机 ⋯ 菜单）、Esc 取消；⋯ 菜单改分类再改回来，分类计数跟着变；已有朗读音频时音频条贴底、最后一行不被挡；手机上「生成中」进度文字看得见。截图存到输出目录 |

每个套件在两个浏览器里各跑一遍。现在的代码应该是 **Chromium 315 项、WebKit 315 项全部通过**。

## 准备

- 项目自己的 Python 虚拟环境：仓库根目录的 `.venv`（`uv sync` 建的）
- Node 20 以上（本机默认的 node 是 v16，可以用 nvm 里的 `~/.nvm/versions/node/v22.23.1/bin/node`）
- `playwright-core` 和它的 Chromium、WebKit 浏览器。仓库里没装，用环境变量 `PLAYWRIGHT_CORE` 指到任意一份现成的：
  本机 `~/my_project/my_own_odyssey/frontend/node_modules/playwright-core` 就有（浏览器已在 `~/Library/Caches/ms-playwright`）。
  别的机器可以 `npm i playwright-core && npx playwright-core install chromium webkit`。

## 跑法

下面的命令都在这个目录（`tests/e2e/intensive/`）里执行：

```bash
cd tests/e2e/intensive

# 1. 建沙盒：复制代码（git ls-files，不带 .env 和数据）→ 造编造数据 → 后台启动服务器
SANDBOX="$(mktemp -d)/app"
./sandbox.sh start "$SANDBOX"            # 默认端口 5071；被占用就换一个：./sandbox.sh start "$SANDBOX" 5072

# 2. 跑测试（端口和上面一致）
export E2E_BASE_URL=http://127.0.0.1:5071
export E2E_TOKEN_FILE="$SANDBOX/e2e_token.txt"
export PLAYWRIGHT_CORE=~/my_project/my_own_odyssey/frontend/node_modules/playwright-core
~/.nvm/versions/node/v22.23.1/bin/node run.js

# 3. 停掉服务器
./sandbox.sh stop "$SANDBOX"
```

只跑一部分：套件名、浏览器名随便组合。

```bash
~/.nvm/versions/node/v22.23.1/bin/node run.js import webkit
~/.nvm/versions/node/v22.23.1/bin/node run.js select touch chromium
```

输出大概是这样，失败的检查会逐条列出（`FAIL ...`），有失败时退出码是 1：

```
chromium select 通过 231，失败 0（27.0s）
chromium touch  通过 22，失败 0（9.1s）
chromium import 通过 38，失败 0（10.8s）
chromium misc   通过 24，失败 0（5.8s）
webkit   select 通过 231，失败 0（14.1s）
...
== 合计
chromium 通过 315，失败 0
webkit   通过 315，失败 0
```

### 参数

| 命令行 | 环境变量 | 说明 |
| --- | --- | --- |
| `--base-url URL` | `E2E_BASE_URL` | 沙盒服务器地址，默认 `http://127.0.0.1:5071`。只接受本机地址 |
| `--token-file 文件` | `E2E_TOKEN_FILE` | 必填。`make_fake_data.py` 写出的 `e2e_token.txt` |
| `--out 目录` | `E2E_OUT` | 截图目录（misc 的截图、套件出错时的截图），默认系统临时目录下的 `intensive-e2e/` |
| | `PLAYWRIGHT_CORE` | playwright-core 的路径，默认 `require('playwright-core')` |

## 几点说明

- **为什么非要沙盒**：`import app` 会起后台线程；仓库根目录的 `.env` 里是真的付费 API key；真数据也在仓库根目录（被 gitignore 的那些目录），服务器按相对路径读写。`sandbox.sh` 只复制代码，把 HTTP(S) 代理都指到不存在的 `127.0.0.1:9`、`PROXY_URL` 也指过去，各家 API key 置空，所以「带翻译导入」一定失败——测试正好拿它测「翻译失败 → 不翻译直接导入」。浏览器这边也把发往本机以外的请求全部掐掉。
- **保护措施**：`sandbox.sh` 不肯把沙盒建在仓库里面；`make_fake_data.py` 遇到 `.git`、`.env` 或 `users.json` 里有别的用户就退出；`run.js` 只连本机地址，开跑前确认 token 属于测试用户 `reader01`、编造的文章都在，否则不跑。
- **跑完会自己收拾**：测试建的文章（标题以「（chromium）」「（webkit）」结尾，或叫 `Plain chromium` / `Plain webkit`）、存的释义（含 `e2e`）、改过的分类，每个套件前后都会清理 / 还原，所以同一个沙盒可以反复跑。真乱了就重造数据（服务器不用停）：

  ```bash
  ../../../.venv/bin/python make_fake_data.py "$SANDBOX"
  ```

- **改了代码要重建沙盒**：沙盒是代码的一份拷贝，仓库里改了模板或后端，`./sandbox.sh stop` 之后换个新目录重新 `start`。
- **数据是编的**：仓库是公开的，不要把九分学长真实的作答 JSON、题目原文或真实用户数据放进来。要更多题型就照 `tests/fixtures/jiufen_reading_attempt.json` 的格式自己编。

## 编造数据（`make_fake_data.py`）

| 文章 | 分类 | 用来测 |
| --- | --- | --- |
| The Lighthouse Keeper's Log | Reading | 普通一句英文一句译文；8 个高亮，其中一条同一范围存了两次 |
| Night Ferry Timetable | Reading | 行内不间断空格（U+00A0）、只有 NBSP 的「空行」、含 NBSP 的高亮 |
| The Cold Chain | Reading | 「第1段」「Paragraph C」小标题、空行、行首就是高亮（Sales） |
| 助记小文章-天气与心情 | Reading | emoji（UTF-16 代理对）在高亮前面、一行好几句、中文标题 |
| The Rope Bridge Builders | Reading | 手机测试；Reading 里最旧，排在列表最下面，要往下翻 |
| Task1-饼图-城市用电来源 | Writing | 一张图片（脚本现画的小 PNG） |
| The Salt Marsh Survey | Listening | 一段已生成的朗读音频（3 秒静音 MP3），正文够长能滚动 |
| The Glass Bridge | Reading | 九分学长导入 + 编的中文译文，用 `utils/jiufen_import` 按导入接口的方式生成 |
| 另外 9 篇短文 | Reading | 只为让列表够长 |

登录用户是 `reader01`（测试读者），token 写在 `<沙盒>/e2e_token.txt`，测试把它放进 localStorage，不输密码。文章 ID 是固定的，`lib.js` 里的 `IDS` 要和 `make_fake_data.py` 保持一致。

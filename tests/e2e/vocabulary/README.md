# 单词本浏览器测试

在沙盒里用编造的数据，把 `/vocabulary` 的每个功能实际点一遍：Chromium + WebKit，亮色 + 暗色，桌面 1280 宽，手机 WebKit 390×844 / Chromium 360×780。

查的内容：
- 目录栏和排序：分类、子分类、自然排序。
- 加词、收藏、删除、隐藏释义（H 键）、查找。
- 编辑单词（见下面「编辑单词检查」）。
- 子分类：新建、重命名、删除。
- 导入、导出 CSV/TXT/JSON，以及导出再导入的往返。
- 单词挑战：出题、1–4 键作答、退出确认、成绩记录、「再来一次」。
- 有道发音，有道取不到时退回旧 TTS 音频。
- 旧偏好设置能不能读、控制台有没有报错。
- 分类文件还不存在时（新装、或某个分类从没加过词）：打开是空状态，加第一个词能存上，文件写得完整。
- 手机（见下面「手机检查」）。

## 手机检查

WebKit 用 390×844 + 触屏（macOS 上的 WebKit 不支持 isMobile），Chromium 用 360×780 + isMobile + 触屏，亮色、暗色各跑一遍：

- 首屏：不横向溢出；不用滚就能看到至少 8 张单词卡；一行两张；英文单词 ≥ 16px；日期、垃圾桶、H 键提示、页面里的加词表单、页头三个按钮都不出现。
- 点击区：卡片右上 ⋯ 和右下 ★ 至少 40×40、上下隔 8px；分类分段 ≥ 40px；子分类 / 查找 / 排序、页头 ⋯、底部操作条 ≥ 44px。
- 滚到列表深处：吸顶条贴在顶部导航下面、还能点；滚到底，底部操作条不挡最后一张卡；`--ui-bottom-bar-h` 等于底部条高度（提示条浮在它上面）。
- 点卡片听发音；底部「遮释义」遮住全部释义（等于桌面的 H 键），点被遮住的释义偷看一张；★ 一下就收藏，提示条在底部条上面。
- 单词卡 ⋯：播放 / 收藏 / 编辑 / 删除（先确认）；子分类面板：选、在面板里新建、对别的子分类重命名和删除，从列表深处换子分类回到新列表开头；排序面板（选了就关，收藏置顶开关就地切换）；查找（吸顶条里换成搜索框）。
- 加词面板：单词框回车跳到释义框（不提交），释义框回车才添加；加完面板不关、结果写在面板里，不弹提示条盖住输入框。
- 页头 ⋯：导入 / 导出 / 子分类管理；导出、挑战设置里「范围」分段不比面板宽；面板都铺满宽度贴着底边。
- 单词挑战：答题铺满全屏、选项在下半屏、没有 1–4 键提示；结果里的单词不在词中间断行；点「开始挑战」这一下里就 play() 过一次（iOS 自动读题要靠它解锁），之后自动读题用的是同一个 audio。
- 返回键（`page.goBack()`）：关掉最上面那层面板、答题时先问要不要退出，页面不离开、不重新加载。
- 视口只剩 470px（模拟键盘弹出）：加词面板、搜索框、新建子分类的输入框和按钮都还看得见。
- 加载中 / 出错：不显示空的子分类下拉、点不动的底部条和 ⋯；「重新加载」以后都回来。

## 编辑单词检查（`edit` 组）

桌面 1280 和手机（WebKit 390×844 / Chromium 360×780），亮色跑完整流程，暗色看编辑面板：

- 桌面：卡片上的铅笔在删除左边、大小和删除一样，和删除一样悬停卡片才出现；点开是居中的「编辑单词」弹窗，单词、释义已经填好，光标在单词框，按钮是「保存」。
- 手机：卡片上没有铅笔，单词卡 ⋯ 里「编辑」紧挨在「删除这个单词」上面；点开是底部面板，输入框 ≥ 16px 字、≥ 44px 高，取消 / 保存 ≥ 44px；单词框回车跳到释义框，释义框回车保存。
- 单词清空点保存：单词框下面提示「单词不能为空」，弹窗不关，不发请求；改成同一子分类里已有的词：边打边提示重复，点保存也不发请求。
- 取消、Esc、返回键（`page.goBack()`）：什么都不改，再打开还是原来的字。
- 保存：提示条「已保存「…」」；同一张卡（id 不变）原地换成新字，位置、滚动位置都不变，焦点回到这张卡；服务器上 id、收藏、添加时间不变；刷新以后还是新字。
- 拼写改了：旧的 TTS 音频文件删掉，有道取不到时不再退回去读旧词；只改释义：音频文件留着，请求里只带释义。
- 遮释义开着时保存，卡片释义照样遮着；查找中保存，结果和「找到 N 个」跟着变；按 A→Z 排时改名，卡片挪到新位置。
- 视口只剩 470px（模拟键盘弹出）：编辑面板的标题、两个输入框和「保存」都看得见。

只跑编辑检查：

```bash
VOCAB_E2E_SUITES=edit node tests/e2e/vocabulary/vocabulary_e2e.js chromium webkit
```

只跑手机检查（比如拿新的检查去跑旧版本的沙盒，看它们在旧版本上确实失败）：

```bash
VOCAB_E2E_SUITES=phone node tests/e2e/vocabulary/vocabulary_e2e.js chromium webkit
```

Playwright 的 WebKit 不会拦自动播放、没有 iOS 的动态工具栏和真键盘，下面几样只能在真 iPhone 上看：挑战第一题自动读出来、键盘弹出时加词面板跟着升到键盘上面、右滑返回关面板。

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
| `VOCAB_E2E_SUITES` | 全跑 | 只跑其中几组，逗号分隔：`desktop,prefs,missing,phone,edit` |
| `PLAYWRIGHT_CORE` | `playwright-core` | playwright-core 的路径 |

不设 `VOCAB_E2E_OFFLINE` 时，浏览器会真的去请求有道词典的发音。这个接口免费，但要能上网。

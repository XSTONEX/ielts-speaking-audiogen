# 听力精听复习 · 浏览器端到端检查

改版后的「听力精听复习」（`templates/listening.html`）和「听力笔记本」（`templates/listening_notes.html`）的浏览器实测脚本，用 Playwright 在 Chromium 和 WebKit（Safari 内核）里把每个功能点一遍：列表卡片、上传、重试、删除、精听页的字幕/星标/听错原因/生词/笔记/播放条/快捷键、笔记本浏览和复习，以及亮色/暗色、1280/1000/390 宽度。还覆盖后端修复：服务重启后卡住的项目、只重做翻译的重试、音频只给项目主人。

**全部跑在沙盒副本上，数据是 `seed.py` 编造的。** 仓库是公开的，这里不放任何真实用户数据和截图；截图默认输出到系统临时目录。

| 文件 | 作用 |
| --- | --- |
| `make_sandbox.sh` | 把当前代码（不含数据目录和 `.env`）复制到新目录，再灌数据 |
| `seed.py` | 灌编造的数据：用户 `demo`（5 个项目）和 `demo2`（无项目），音频用 macOS `say` 合成；登录 token 写进 `<沙盒>/e2e_tokens.json` |
| `serve.sh` | 在沙盒里起服务：代理指向不存在的端口、API key 全部置空 |
| `e2e.js` | 检查脚本 |
| `jiufen_data.py` | 九分学长 JSON 导入用：把 `tests/fixtures/jiufen_listening_*.json`（编造的）配上 `say` 合成的音频，写进 `<沙盒>/static/e2e/` |
| `jiufen_fake_translate.py` | 沙盒里没有翻译接口，导入的篇会停在「润色翻译失败」；这个脚本补上编的译文，把它改成完成 |
| `jiufen_e2e.js` | 九分学长 JSON 导入的检查：粘贴 → 预解析 → 导入 → 字幕上的题号和出处 → 题目栏 → 再导入第二次做题 |
| `phone_e2e.js` | 手机版的检查（2026-11 手机改版）：WebKit 390×844（iPhone Safari 内核）/ Chromium 360×780（安卓），亮色 + 暗色。列表两列和卡片「⋯」→ 上传底部面板 → 精听页的页签、底部播放条（上一句 / 下一句 / 单句循环 / 倍速）、正在播那句的操作行、听错原因面板、跟随播放和「回到当前句」、选词条和生词 / 笔记面板（键盘弹起时视口 470 高）、返回键先关面板再回列表、刷新还在这篇 → 导入的篇：题目页签、题号 ↔ 原文出处、重做的卷子 / 答题卡 / 字母面板 → 笔记本：吸顶筛选、搜索、复习的底部按钮和筛选面板。没有横向滚动、按钮够大、底部的条不挡最后一项都在里面 |
| `redo_e2e.js` | 「显示答案 / 重做」的检查：导入填空 + 单选、地图 + 多选、版式里选字母的配对三份 → 重做时各题型作答（填空横线、选项卡片、地图 / 配对的答题纸表格、字母槽 + 选项菜单、字母键 / 方向键）→ 刷新后接着做 → 显示 / 隐藏原文 → 交卷判分 → 显示答案的同款外形 → 做题记录（本站 / 九分、删本站的）→ 暗色、390 宽（字母菜单从底部弹出） |
| `flag_e2e.js` | 「错题标注」的检查（页头第一档、默认打开，画布第 10 行）：同样导入三份 → 卷子 / 原文显示两种排法里都不露答案（正确答案、你填的、对错颜色、解析、出处、划线、字幕 Q 标签）→ 做错和没答的框红、答对的不标 → 点框起来的题 / 红题号从出处句子开始放、原文不露 → 错题卡（错几题、那次答对、题号总览、做题记录、打卡 / 标熟）→ 换一次记录就按那一次标 → 刷新、换篇回来还是这一档，笔记跳过来的开在显示答案 → 切回显示答案 / 重做 → 抽屉宽度、暗色、390 手机 |

## 准备

- macOS（`seed.py` 要用 `say`），装好 `ffmpeg` / `ffprobe`
- 仓库的 `.venv`（`serve.sh` 默认用它；在 git worktree 里会自动找主仓库的 `.venv`，也可以 `PYTHON=... bash serve.sh ...` 指定）
- Node 22，以及一份 `playwright-core` 和它的 Chromium / WebKit 浏览器。仓库本身没有 node 依赖，用 `PLAYWRIGHT_CORE` 指向任意一个装好的 `playwright-core` 目录即可（浏览器用 `npx playwright-core install chromium webkit` 安装）

## 1. 建沙盒

```bash
SB=$(mktemp -d)/sb
bash tests/e2e/listening/make_sandbox.sh "$SB"
```

沙盒必须是复制出来的目录：`seed.py` 会清空沙盒的 `listening_review/`、覆盖 `users.json`，所以它拒绝对着 git 仓库本身运行。

## 2. 起沙盒服务

另开一个终端：

```bash
bash tests/e2e/listening/serve.sh "$SB" 5073
```

沙盒里调不到任何付费接口：上传后的转录、翻译会直接失败（`WILDAPI_API_KEY not configured`），脚本就是按这个结果检查的。

## 3. 跑检查

脚本会改动沙盒数据（打卡、星标、上传、删除、重试），**每跑一次之前先重新灌数据**（服务不用重启）：

```bash
python3 tests/e2e/listening/seed.py "$SB" && LR_SANDBOX="$SB" PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node tests/e2e/listening/e2e.js chromium all
```

- 第一个参数：`chromium` 或 `webkit`
- 第二个参数：`all`（默认）、`desktop`、`phone`、`recovery`（只测后端修复那几项）
- `LR_BASE_URL`：服务地址，默认 `http://localhost:5073`
- `LR_OUT_DIR`：截图和结果 JSON（`e2e-<内核>.json`）的输出目录，默认 `$TMPDIR/listening-e2e`

每一项打印 `PASS` / `FAIL`，最后一行是通过数；有失败时退出码为 1。2026-10-31 两个内核都是 217 项全过。

## 4. 九分学长 JSON 导入

`serve.sh` 只放行本机地址，所以导入时音频从沙盒服务自己的 `/static/e2e/` 下载，碰不到外网；转录不会发生（字幕直接用 JSON 里的），翻译因为没有 key 会失败，脚本接着用 `jiufen_fake_translate.py` 补成完成再看精听页。同样每跑一次前先重灌：

```bash
python3 tests/e2e/listening/seed.py "$SB" && python3 tests/e2e/listening/jiufen_data.py "$SB" && LR_SANDBOX="$SB" PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node tests/e2e/listening/jiufen_e2e.js webkit
```

2026-10-31 两个内核都是 23 项全过（含题目栏放宽：4 列表格不挤、解析在表格下面、分隔条拖动 / 记住 / 双击恢复）。

## 5. 显示答案 / 重做

数据和第 4 步一样（`jiufen_data.py` 另外造了一份地图题 + 多选题的 JSON，平面图是沙盒里画的 SVG）。同样每跑一次前先重灌：

```bash
python3 tests/e2e/listening/seed.py "$SB" && python3 tests/e2e/listening/jiufen_data.py "$SB" && LR_SANDBOX="$SB" PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node tests/e2e/listening/redo_e2e.js webkit
```

2026-11-01 题型样式改版（画布第 9 行）后，两个内核都是 61 项全过；同一天 `e2e.js` 217 项、`jiufen_e2e.js` 23 项也都重跑全过。

单元测试里写作批改重试那几项要用 node 跑页面里的脚本，需要 Node 18 以上；本机默认的 node 太旧时把 Node 22 放到 `PATH` 前面再跑。

## 6. 手机版（2026-11 手机改版）

数据和第 4、5 步一样，每跑一次前先重灌。第一个参数是内核：`webkit` 用 390×844 + 触摸（WebKit 不支持 `isMobile`），`chromium` 用 360×780 + `isMobile`：

```bash
python3 tests/e2e/listening/seed.py "$SB" && python3 tests/e2e/listening/jiufen_data.py "$SB" && LR_SANDBOX="$SB" PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node tests/e2e/listening/phone_e2e.js webkit
```

截图在 `LR_OUT_DIR` 下，文件名 `phone-<内核>-*.png`。键盘弹起用「把视口改成 470 高」模拟；长按选词造不出来，脚本先点一下再用 Range 选中。复习卡片的左右滑在 WebKit 里造不出真的 TouchEvent，脚本发的是带 `touches` 的普通事件，测的是页面自己的滑动处理。

2026-11-01：WebKit、Chromium 都是 133 项全过；同一份脚本对着改版前（`mobile/base`）的页面跑，两个内核都只过 12 / 74 项（过的只有「没有横向滚动」「暗色生效」「点句子能播」和 2ab6302 就有的字母底部面板；其余都失败，后面的检查因为元素不存在整段跳过），证明检查的是新东西。每段检查出错只记一项失败、接着跑下一段，所以对着旧页面也能跑完。同一天 `e2e.js`、`jiufen_e2e.js`、`redo_e2e.js` 两个内核也都重跑全过；其中 `e2e.js` 的手机部分和深链接、`redo_e2e.js` 的手机开关位置按新布局改了断言（列表两列、页签代替抽屉、倍速收成一个按钮、深链接后地址栏留着 `?project=`）。

### 手机版的样子（宽屏不变）

- 精听页：页头下面吸顶「原文 / 题目 / 本篇」页签 + 译文开关 + 「⋯」（跟随播放、重做时显示原文、去笔记本）；字幕去掉时间和星星两列，正在播的那句下面一行「收藏 · 原因（收藏了才有）· 重听 · 笔记」；字幕最后一张「听完了」卡片放打卡 / 标熟
- 底部播放条：进度（两头是时间），下面「倍速 · 上一句 · 播放 · 下一句 · 单句循环」；用户自己翻走了不再拽回来，改成「回到当前句」；提示条浮在播放条上面
- 选中文字后「释义 / 笔记」停在播放条上面；生词 / 笔记 / 听错原因都是底部面板，键盘弹起时抬到键盘上面
- 导入的篇：「显示答案 / 重做」和做题记录在题目页签顶上；点字幕里的 Q 标签跳到那道题，题目里「看原文出处」跳回原文、页签条下面挂着这道题；重做时卷子顶上吸着「已答 · 用时 · 答题卡 · 交卷」，第三个页签变成答题卡
- 返回键 / 侧滑返回：先关面板，再从这篇回到列表（地址栏带 `?project=`，刷新还在这篇；这一条宽屏也一样）
- 笔记本：文章 / 类型 / 放大镜一行吸顶；复习时筛选收成一行摘要（点「筛选」从底部升起），「上一张 / 翻面·记住了 / 下一张」固定在屏幕底部，点卡片翻面、左右滑换卡

## 7. 错题标注（2026-11-08）

页头开关是三档「错题标注 | 显示答案 | 重做」，导入的篇打开就是「错题标注」（这一档最早叫「标出错题」、放在中间，当天改了名、挪到最左、改成默认）。数据和第 4、5 步一样，每跑一次前先重灌：

```bash
python3 tests/e2e/listening/seed.py "$SB" && python3 tests/e2e/listening/jiufen_data.py "$SB" && LR_SANDBOX="$SB" PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core node tests/e2e/listening/flag_e2e.js webkit
```

2026-11-08：第一版两个内核 43 项全过（对着之前的 f8cf9e5 只过 2 / 16）；改名、默认、点错题听原文以后 60 项（对着第一版 e77fecf 只过 9 / 27）；对的题也能点、一直往下放以后 65 项全过（对着 897b28d Chromium 只过 49 / 59）。

### 错题标注的样子

- 题目照原卷排，空格空着、选项一个都不选；不显示正确答案、你当时填的、对错颜色、解析、播放出处、九分学长上划的黄色关键词，字幕上也没有 Q 标签、答案下划线和出处框
- 按「做题记录」里选的那一次（默认最新一次）：做错和没答的题号变红、整道题浅红底加红框；填空只框那一个空（表格里那一格也浅红），配对 / 地图是那一行浅红，多选错一个就框整组；答对的不标绿
- 「显示原文」和重做共用：关着时题目像卷子摆在左边，右栏是「错题标注」卡（错几题、那次答对、题号总览、做题记录、打卡 / 标熟）；开着时就是平常的精听页，题目在右栏、顶上题号总览
- 点任意一道题（对的错的都行：空格、那一行的字、表格那一格、整道选择题、配对那一行、字母槽）或题号：音频跳到这题的出处句子（`sentenceIndex`）开头，一直往下放，不在出处末尾停（开着单句循环就循环那句）；原文照样藏着，不切到原文页签、不展开解析。刚点的那道外面多一圈（错的红圈、对的蓝圈）。键盘 Tab 到题上按回车也行，空格还是播放 / 暂停
- 每道能点的题上有个小三角（错的红、对的灰；选择题是「▶ 听原文」小标签）；没错的题平时不加框，悬停才显出一个浅框。音频和字幕对不上（改成重新转录、没有出处）时照样框红，但都不能点、也不提「点题听」
- 抽屉宽度（821–1099）和手机上，卷子顶上那条后面跟着红题号
- 每次打开导入的篇都是这一档（重做到一半离开的除外，回来接着重做）；从笔记本 / 生词本点「原句」过来的（`?project=…&seg=…`）开在「显示答案」，那一句才看得到
- 页头多了一档、按钮变宽：宽屏（>820）标题 + 时长那行和按钮挤不下一行时，按钮换到第二行靠右，标题不再被截掉（821–1280 宽、显示原文开着时以前会被挤没）；时长那行不折断


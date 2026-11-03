# 横着拿的手机 · 浏览器检查

手机横过来是 844–932 宽、只有 350–430 高。以前所有页面只按宽度（≤ 820px）判断手机，横屏的手机拿到的是桌面版：七个链接平铺的导航、只能悬停的按钮、很小的点击区；听力、口语的导航 + 页头 + 播放条叠起来，内容只剩 ~150px。

2026-11 起「手机布局」= **窄屏（≤ 820px）或者矮的触摸屏**：

- CSS：每个手机媒体查询都写成 `@media (max-width: 820px), (max-height: 540px) and (pointer: coarse)`；只给桌面的 `(min-width: 821px)` 规则加了「不是矮触摸屏」的条件。
- 脚本：`static/theme.js` 提供 `window.IELTSPhone`（`query`、`mq`、`matches()`、`onChange(fn)`），各页面和 `app-shell.js` 都用它，不再各写一遍。theme.js 因此不加 `defer`，页面里的内联脚本一解析就能读到。
- 带鼠标的电脑窗口拉得再矮也不算（`pointer: fine`）；iPad 横竖都够高，也不算。
- `≤ 640px` 的规则还是只看宽度，所以横屏拿到的是各页 641–820 的那一档。

只在矮屏上生效的收紧写在 `@media (max-height: 540px) and (pointer: coarse)` 里：全站导航跟着页面滚走（`theme.css` 末尾），弹窗贴底、标题和按钮固定只滚中间（`plain.css` 末尾），听力播放条一行，口语搜索框和 Part 筛选并成一行，精读阅读页正文占 ~90% 高、题目放到右边一栏，单词本吸顶条一行、答题四个选项两列，卡片一行三张，等等（各页样式表里「横着拿的手机」一段）。

转屏（竖 → 横 → 竖）现在一直是手机布局，不会再跨过分界线把打开着的面板、阅读页、播放器收掉。

## 检查什么

`landscape_e2e.js`，设备：WebKit 844×390、932×430（iPhone 横屏，触屏），Chromium 915×412（安卓横屏，`isMobile` + 触屏）。开跑前先确认模拟环境里 `(max-height: 540px)` 和 `(pointer: coarse)` 都成立，否则这个设备整段不算。

每个导航能去的页面（首页、登录、口语、精读 + 添加文章 + 词汇汇总、写作、听力 + 笔记本、单词本、技巧、交流）：

- 手机布局生效（导航收成「模块 ▾」）、不横向溢出、往下翻时全站导航滚走；
- 主要按钮在屏幕里且 ≥ 40 / 44px（底部操作条、播放条、提交、导入、生成音频…）；
- 面板 / 弹窗（上传、⋯ 菜单、加词、挑战设置、发帖、完整播放器）整个在屏幕里，按钮看得见；
- 页面自己的矮屏收紧：口语搜索 + 筛选一行、精读正文 ≥ 80% 高且题目左右并排、精听页签贴顶且原文 ≥ 60% 高、单词本吸顶一行、单词挑战选项一屏看全、写作实战输入框一进来就露出来；
- 转屏：先竖屏打开一层（首页模块面板、口语完整播放器、精读阅读页 + 题目、词汇挑战设置、写作句子面板 + 写了一半的译文、精听 ⋯ 面板、单词挑战答题、技巧 ⋯ 面板、交流发帖 + 草稿），转成横屏再转回来，这一层还开着、内容还在、`history.length` 不变，返回手势只关这一层；
- 隐藏页面（/combined、/reading、/audio_transcription）横屏不溢出、不报错；
- 反例：带鼠标的 1280×500 窗口、iPad 1180×820 触屏还是桌面布局。

## 跑法

需要仓库的 `.venv`、node 22、`playwright-core`（本机借用 `my_own_odyssey/frontend/node_modules` 里的那份）、macOS 的 `say` 和 `ffmpeg`（听力的造数据脚本要用）。

```bash
PLAYWRIGHT_CORE=/path/to/node_modules/playwright-core NODE=~/.nvm/versions/node/v22.23.1/bin/node \
  tests/e2e/landscape/run.sh "$(mktemp -d)/ls" webkit chromium
```

`run.sh` 给九个模块各建一个沙盒（代码用 `git ls-files` 复制，数据用各模块自己的造数据脚本：`home/`、`speaking/`、`intensive/`、`vocab_summary/`、`listening/`（seed + 九分学长 JSON）、`vocabulary/`、`study_tips/`、`board/`、`writing/`），端口 `PORT_BASE+1 … +9`（默认 5601–5609），断网、API key 全空，跑完把服务都停掉。

- 测别的代码（比如证明这些检查在改之前会失败）：`CODE_FROM=<目录>`，例如 `git archive main | tar -x -C /tmp/main_code` 后 `CODE_FROM=/tmp/main_code`。
- 截图在 `LS_OUT`（默认 `<工作目录>/out`），文件名 `<设备>-<画面>.png`。
- 最后一行是「横屏检查：通过 N 项，失败 M 项」，有失败时列出失败项、退出码 1。
- 已经有起好的沙盒时，可以直接跑 `LS_CONFIG=<config.json> node landscape_e2e.js`，config 的格式见 `run.sh` 写出的 `<工作目录>/config.json`（每个模块的 `base` 和 `sandbox`，沙盒里要有 `e2e_token.txt`）。

2026-11-03：改动后的代码 WebKit + Chromium 共 367 项全过；同一份脚本对着 `main`（11fd016）跑，通过 169 项、失败 147 项（手机布局、导航滚走、矮屏收紧那些都失败；能过的是不溢出、不报错、转屏历史条数这类本来就对的项）。

真机才看得到的：Safari 横屏时自己的地址栏 / 标签栏占多少高、横屏弹键盘以后还剩多少高（模拟器里只能把视口压矮）、刘海在左右两边时的安全区。

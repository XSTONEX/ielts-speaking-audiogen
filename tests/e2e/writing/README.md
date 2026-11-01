# 写作逻辑训练 · 浏览器测试

用真的浏览器（WebKit / Safari 内核和 Chromium）把 `/writing_practice` 在手机上走一遍，并检查电脑上的样子一个像素都没变。

全程在**仓库外的一份代码拷贝**里跑：
- 数据都是编的：一个假用户「林夏」，几个思维链话题、仿写例题、模板语料和练习记录。
- 网络断开、API key 清空。
- AI 批改、追问、AI 写作助手全在浏览器里拦下，回一份编好的结果，不会调用任何大模型。

仓库是公开的，不要把真实语料、练习记录、截图或沙盒目录提交进来。

## 需要准备的

- 仓库的 `.venv`（Flask、Pillow）。
- Node 22。
- `playwright-core` 和它对应版本的 Chromium、WebKit。在任意目录 `npm install playwright-core`，再 `npx playwright-core install chromium webkit`。已经装过的话，把 `PLAYWRIGHT_CORE` 指到那份 `node_modules/playwright-core`。

## 1. 建沙盒

沙盒是仓库代码的拷贝，必须放在仓库外面。在仓库根目录（或 worktree 根目录）执行：

```bash
SB=~/ielts-writing-sandbox
mkdir -p "$SB" && git ls-files -co --exclude-standard | rsync -a --files-from=- ./ "$SB/"
.venv/bin/python tests/e2e/writing/make_fake_data.py "$SB"
```

注意几点：
- 改了代码要重新跑第一条，沙盒里才会更新。
- 模板是每次请求现读的，只改 `templates/` 不用重启服务器。
- 在 git worktree 里没有 `.venv`，用主仓库那份 Python 跑 worktree 里的 `make_fake_data.py`。

`make_fake_data.py` 每次都把数据恢复成同样的初始状态，内容如下：
- `writing_correction/` 下的三份语料、两张假题图、林夏的练习记录 / 速记 / 一段 AI 对话。
- `users.json`、`tokens.json`。
- `_e2e/tokens.json`，浏览器脚本用这里的 token 登录。

目录是仓库本身或在仓库里面时，它会拒绝执行。

## 2. 启动沙盒服务器

```bash
tests/e2e/writing/run_sandbox.sh "$SB"
```

默认端口 5131（`PORT=xxxx` 可改）。代理指向关着的端口，API key 全部清空。`run_all.sh` 发现端口上没有服务器时会自己起一个，跑完关掉，所以这一步也可以跳过。

语料在服务器进程里有缓存。重新生成数据后，如果题图出了问题，重启一下服务器。

## 3. 手机测试

```bash
PATH=<node 22 的 bin 目录>:$PATH PLAYWRIGHT_CORE=<playwright-core 目录> \
  tests/e2e/writing/run_all.sh "$SB" webkit
```

把最后的 `webkit` 换成 `chromium` 再跑一遍。
- 全部通过时最后一行是「全部通过」，退出码 0。
- 有问题时往上找 `FAIL`、`ERRORS`、`CRASH`。
- 想要截图就加 `WP_SHOTS=<截图目录>`。截图只留在本地，不要提交。

`phone.js` 用两种手机尺寸：WebKit 390×844（iPhone Safari）、Chromium 360×780（Android）。亮色全走一遍，暗色抽首页和批改结果。查的内容：

- **每一页都不横向溢出**：首页、思维链目录 / 学习 / 实战 / 结果，仿写列表 / 学习 / 实战 / 结果，模板题型 / 范文 / 骨架对照 / 实战 / 结果，模板小作文段落 / 例题 / 句型库 / 实战 / 结果，复习中心。
- **布局**：
  - 右下角三个浮动按钮不显示，首页「返回主站」隐藏。
  - 入口卡、子类卡、题目卡、题型卡、范文卡都是两张一行。
  - 话题条吸在导航条下面。
  - 学习页关键词和逻辑链上下排。
  - 例句、范文拆解的英文有整行宽（不再被隐藏的按钮挤成一两个词一行）。
- **点得到**：页头按钮、进度行、操作条按钮 ≥ 44px；学习 / 实战切换、话题胶囊、卡片上的按钮 ≥ 40px。输入框字号 ≥ 16px（作答、追问、AI、速记）。
- **页头工具**：
  - 实战页页头有速记、AI 两个图标。
  - 「⋯」打开工具弹层（复习中心 / 练习速记 / AI 写作助手，加上这一页的「只看骨架」之类）。
- **实战**：
  - 输入框一进页面就在屏幕里，「提交批改」在底部操作条上。
  - 进度行点开是句子列表，选一句就跳过去；「题干」弹层里是完整题目（小作文带题图）。
  - 小作文任务卡上有题图缩略条。
- **键盘弹起**（视口压到 470px 高）：原句、输入框都在导航条和操作条之间，「提交批改」不用滚就点得到。
- **批改后**：
  - 分数条就在眼前，操作条换成「改一遍 / 下一句」（模板是「偷看 / 再试一次 / 下一句」）。
  - 滚到底最后一块不被操作条盖住。
  - 追问能发。
  - 「下一句」后句子卡回到屏幕上方。
- **触屏代替拖拽 / 悬停**：
  - 每句右上角的「⋯」里有复制英文 / 中文、问 AI、就练这句；「问 AI」把这一句带进 AI 助手。
  - 长按选词（用程序设选区模拟）后「高亮」出现在屏幕下方，点了能标上，点标记能取消。
  - 大图右上角「⋯」里有「换一张题图」，题图上不再压着「换一张」。
- **整屏的层**：AI 助手、练习速记、复习中心、大图、底部弹层都在屏幕里，安卓返回 / iOS 侧滑返回先关它们，人还在原来那页。
- **复习中心**：排序是一个按钮，点开选；删除放到详情底部的「删除这条」，不再挨着「收起详情」。

在手机改版前的代码（`mobile/base`）上跑同一个 `phone.js`，上面这些大部分会 FAIL，这是预期的。

## 4. 桌面像素对比

桌面（>820px）在手机改版前后应该一模一样。做法如下：

1. 准备两份沙盒：一份放改版前的代码，比如 `git archive mobile/base | tar -x -C <目录>`；一份放改版后的代码。
2. 两个沙盒各起一个服务器：改版前用 5132，改版后用 5131。
3. 跑对比：

```bash
PATH=<node 22 的 bin 目录>:$PATH PLAYWRIGHT_CORE=<playwright-core 目录> \
  tests/e2e/writing/desktop_compare.sh <改版前沙盒> <改版后沙盒> <输出目录>
```

对比脚本会这样做：
- 只生成一份假数据，两边用完全一样的拷贝。
- `desktop_shots.js` 在 Chromium 和 WebKit、1280 和 1440 两种宽度下，各走一遍 34 个画面：首页、复习中心、速记、AI、四个模块的列表 / 学习 / 实战 / 结果 / 历史、参考资料、荧光笔、大图、暗色。
- 保存练习记录的接口在浏览器里拦下，页面时间固定在 2026-11-01 10:00，所以两次截图可以逐像素比。
- `compare_shots.py` 逐张比较，打印 `SAME` / `DIFF`。不一样的画面在 `<输出目录>/<引擎>-<宽度>-diff/` 里，差异像素标红。
- 全部一致时最后一行是「桌面截图全部一致」。

## 脚本

| 文件 | 内容 |
| --- | --- |
| `make_fake_data.py` | 建假数据和 token |
| `run_sandbox.sh` | 断网、清空 key 后启动沙盒服务器 |
| `run_all.sh` | 重建数据，必要时起服务器，跑 `phone.js` |
| `lib.js` | 公共部分：登录、断网、拦截批改和 AI、截图、计数 |
| `phone.js` | 手机检查（见第 3 节） |
| `desktop_shots.js` | 桌面截图（给像素对比用） |
| `compare_shots.py` | 两套截图逐张比像素 |
| `desktop_compare.sh` | 改版前后各截一套再比 |

环境变量：
- `WP_SANDBOX`：沙盒目录，单独跑脚本时必填。
- `WP_BASE_URL`：默认 `http://localhost:5131`。
- `ENGINE`：`webkit` 或 `chromium`。
- `WP_SHOTS`：截图目录。
- `PLAYWRIGHT_CORE`：playwright-core 所在目录。
- `WIDTH`：只有 `desktop_shots.js` 用。
- `run_all.sh` 和 `run_sandbox.sh` 还认 `PORT`、`PYTHON`、`NODE`。

页面设计稿见 `templates/writing_practice.html` 第二行注释里的画布链接。手机版的做法写在样式表「手机版（≤820px）」那一段和脚本里 `var Phone` 的注释里。

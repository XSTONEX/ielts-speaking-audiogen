# 词汇汇总 + 登录 浏览器测试

用真浏览器（Chromium + WebKit，也就是 Safari 的内核）把两个页面从头点一遍：

- `templates/vocab_summary.html`（`/vocab_summary`）：精读里高亮过的词按文章汇总，词汇挑战的四个弹窗
- `templates/login.html`（`/login`）
- 设计稿：[登录 · 词汇汇总 · 改版](https://claude.ai/artifact/MhSvUwJm3kfprXehaKM2nu)

数据全是编的（`make_fake_data.py` 现造），服务器只在临时沙盒里跑，碰不到真数据，也调不到任何付费接口。
有道词典的发音请求在浏览器里直接拦掉，测试不连外网。

## 测了什么

**词汇汇总**（`summary`）

- 左边只列出高亮过词的文章，分类计数、「另有 N 篇还没高亮过词」，第一篇自动打开；刷新后记得分类和文章
- 对齐：左边分类条和右边标题行顶边对齐，第一篇文章和第一行词卡顶边对齐，一行 3 张、同一行一样高
- 单词、释义里的 `<i>`、`<b>`、双引号、撇号都原样显示，不当成 HTML
- 搜索；连点两篇文章时只认后一篇；没写释义的词有说明；没词的分类有空状态
- 发音：先取精读划词时存下的 `/vocab_audio/<文章>/<词>`，再取有道的，都不行才提示；带撇号的词也能点
- 跳到原文：新标签页拿到要滚到的高亮，本页过一会儿删掉这个标记
- 导出当前文章 / 当前分类：文件名、BOM、表头（和单词本导入认的一样）、双引号转义、去重
- 开始挑战：只列有词的文章，按分类筛，全选，题数输入框和滑块互相带动，点弹窗外面关掉、再打开还记得选过的；选文章时不再整篇下载每篇文章
- 答题：答错标出对错，等下一题时「跳过」不生效（以前会多记一题、跳掉下一题），跳过也标出正确答案，答题时 Esc 不关弹窗，等下一题时退出不报错
- 结果：副标题和存到后端的记录都带文章名（以前是空的），答错和跳过的词进错词本，「复习这 N 个」，「再来一次」勾回上次的文章
- 挑战记录：旧记录按文章 ID 补回文章名，详情原地展开，从记录复习错词；错词本按次数排、里面的 HTML 不执行、带撇号的词能「记住了」移出；统计；导出记录
- 服务器没去生成发音，`vocab_audio/` 里没多出挑战文件夹和空文件夹
- 暗色、手机（390 宽）

**登录**（`login`）

- 标题、没有导航栏、光标在用户名；空着提交、密码错的提示，失败后按钮恢复；显示 / 隐藏密码
- 末尾带空格的密码能登录（以前会把空格删掉）；回车只提交一次
- 没登录打开词汇汇总 → 跳登录页 → 登录后回到词汇汇总；`?next=` 只认本站路径（`//example.com`、`https://example.com` 都回首页）
- 已登录的人打开登录页直接放行；暗色；矮屏幕能滚到底、不横向溢出

每个浏览器开跑前都会重新造一遍数据。现在的代码应该是 **Chromium 130 项、WebKit 130 项全部通过**。

## 跑法

需要项目的 `.venv`、node 22，以及一份 `playwright-core`（本机借用 `my_own_odyssey/frontend/node_modules` 里的那份）。

```bash
cd tests/e2e/vocab_summary

# 1. 建沙盒：复制代码（git ls-files，不带 .env 和数据）→ 造编造数据 → 后台启动服务器
SANDBOX="$(mktemp -d)/app"
./sandbox.sh start "$SANDBOX"            # 默认端口 5073；被占用就换一个：./sandbox.sh start "$SANDBOX" 5074

# 2. 跑测试（端口和上面一致）
export E2E_BASE_URL=http://127.0.0.1:5073
export E2E_TOKEN_FILE="$SANDBOX/e2e_token.txt"
export PLAYWRIGHT_CORE=~/my_project/my_own_odyssey/frontend/node_modules/playwright-core
~/.nvm/versions/node/v22.23.1/bin/node vocab_summary_e2e.js

# 3. 停掉服务器
./sandbox.sh stop "$SANDBOX"
```

只跑一部分：`node vocab_summary_e2e.js summary webkit`、`node vocab_summary_e2e.js login chromium`。
设了 `OUT_DIR` 会把截图和导出的文件存到那里（默认系统临时目录下的 `vocab_summary_e2e/`）。
测试会用 `make_fake_data.py` 重置沙盒数据，默认用仓库的 `.venv/bin/python`，别的 Python 用 `PYTHON=` 指定。

## 文件

| 文件 | 作用 |
| --- | --- |
| `make_fake_data.py` | 造数据：用户 reader02（密码故意以空格结尾）、8 篇文章（4 篇有词）、一个存好的发音、一条旧格式的挑战记录（文章名是空的）、3 个错词（带撇号、带 HTML） |
| `sandbox.sh` | 建沙盒、起停服务器（和 `../intensive/sandbox.sh` 一样，只是默认端口和数据脚本不同） |
| `vocab_summary_e2e.js` | 测试本身，文章 ID 和单词写在开头的 `DATA` 里，要和造数据脚本一致 |

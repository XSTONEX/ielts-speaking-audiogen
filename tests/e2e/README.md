# 浏览器测试（E2E）

每个页面的测试都放在自己的文件夹里，用 Playwright 在 Chromium 和 WebKit（Safari 的内核）下打开沙盒，真的点、真的看。

| 文件夹 | 页面 |
|---|---|
| `home/` | 首页 |
| `intensive/` | 文章精读、添加文章 |
| `listening/` | 听力精听复习、听力笔记本 |
| `vocabulary/` | 单词本 |
| `study_tips/` | 学习技巧 |
| `board/` | 学习交流小天地（不能叫 `message_board/`：`.gitignore` 会把任何层级叫这个名字的目录都忽略掉） |

各文件夹的 README 写了具体命令，套路都一样：

1. **只用编的数据。** 仓库是公开的。每个文件夹都有一个造数据的脚本，把用户、凭证和各模块数据写进沙盒。
2. **沙盒是代码的一份副本。** 用 `git ls-files -co --exclude-standard` 复制到临时目录，数据目录建在副本里，所以碰不到仓库根目录下的真实数据。
3. **起服务时断网、清空密钥。** 把 `HTTP(S)_PROXY` / `ALL_PROXY`（大小写各一份）都指到 `http://127.0.0.1:9`，`DEER_API_KEY`、`WILDAPI_API_KEY`、`GROQ_API_KEY`、`SILICONFLOW_API_KEY` 设成空，再用项目的 `.venv/bin/python -c 'from app import app; app.run(port=…)'` 启动。端口别用 5060 / 5061，Chrome 不让打开。
4. **用 node 22 跑。** `playwright-core` 通过环境变量 `PLAYWRIGHT_CORE` 指过去（本机借用 `/Users/shiqiwen/my_project/my_own_odyssey/frontend/node_modules/playwright-core`）。

文件夹里的 Python 文件不要以 `test_` 开头，免得被 `python -m unittest discover -s tests` 当成单元测试收进去。

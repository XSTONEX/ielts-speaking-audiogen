# 首页浏览器测试

测的是 `templates/modules.html` 和 `/api/home`（`routers/home.py`）。

在 Chromium 和 WebKit 两个内核下，分别用亮色、暗色，以及 1280 / 1440 / 900 / 375 四种宽度检查：

- **边线对齐**：宽屏三列时，同一列的左右边、同一排的上下边、同一排卡片底部的细线，都要落在同一条线上（误差 0.5px 以内）。
- **页面基本状况**：不横向溢出，控制台没有报错。
- **入口**：七个模块的入口都在，合集播放和 Reading 不放入口。
- **数据**：每张卡片的数据行都有内容；有数据的账号显示「继续上次」和 6 行待复习，新账号显示空状态。
- **交互**：主题按钮能切暗色、切回亮色；点待复习、点「继续上次」、点卡片都能去到对应页面。
- **时区**：浏览器在上海或洛杉矶时区下，「继续上次」的时间都按本地钟显示。
- **登录**：没登录时会跳到登录页。

数据全是 `make_fake_data.py` 编的。仓库是公开的，不要换成真实数据。

## 跑法

需要 node 22，以及一份 `playwright-core`（本机借用 `my_own_odyssey/frontend/node_modules` 里的那份）。

1. 复制两份代码作沙盒，一份有数据，一份是新账号。数据目录都建在沙盒里，碰不到仓库根目录下的真实数据：

```bash
cd /Users/shiqiwen/my_project/ielts-speaking-audiogen
for d in /tmp/home_full /tmp/home_empty; do mkdir -p $d && git ls-files -co --exclude-standard | rsync -a --files-from=- ./ $d/; done
.venv/bin/python tests/e2e/home/make_fake_data.py /tmp/home_full
.venv/bin/python tests/e2e/home/make_fake_data.py /tmp/home_empty --empty
```

2. 两个沙盒各起一个服务。启动时断网、清空 API 密钥，免得调用付费接口：

```bash
cd /tmp/home_full && env -u NO_PROXY HTTP_PROXY=http://127.0.0.1:9 HTTPS_PROXY=http://127.0.0.1:9 ALL_PROXY=http://127.0.0.1:9 http_proxy=http://127.0.0.1:9 https_proxy=http://127.0.0.1:9 all_proxy=http://127.0.0.1:9 DEER_API_KEY= WILDAPI_API_KEY= GROQ_API_KEY= SILICONFLOW_API_KEY= PYTHONDONTWRITEBYTECODE=1 /Users/shiqiwen/my_project/ielts-speaking-audiogen/.venv/bin/python -c 'from app import app; app.run(port=5062)'
```

另一个沙盒命令相同，把目录换成 `/tmp/home_empty`、端口换成 5063。不要用 5060 / 5061，Chrome 认为那两个端口不安全，会直接拒绝打开。

3. 跑测试：

```bash
cd /Users/shiqiwen/my_project/ielts-speaking-audiogen/tests/e2e/home
PLAYWRIGHT_CORE=/Users/shiqiwen/my_project/my_own_odyssey/frontend/node_modules/playwright-core FULL_URL=http://localhost:5062 FULL_TOKEN_FILE=/tmp/home_full/e2e_token.txt EMPTY_URL=http://localhost:5063 EMPTY_TOKEN_FILE=/tmp/home_empty/e2e_token.txt OUT_DIR=/tmp/home_shots ~/.nvm/versions/node/v22.23.1/bin/node home_e2e.js
```

最后一行输出「通过 N 项，失败 M 项」，有失败时退出码是 1。

- 不设 `EMPTY_URL` 时，只测有数据的账号。
- 设了 `OUT_DIR` 会把截图存到那里。

2026-10-31 的结果：两个内核共 328 项全部通过。在沙盒里把「待复习」挪下 8px，「第一排上边」会报错。

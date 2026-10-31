# 听力精听复习 · 浏览器端到端检查

改版后的「听力精听复习」（`templates/listening.html`）和「听力笔记本」（`templates/listening_notes.html`）的浏览器实测脚本，用 Playwright 在 Chromium 和 WebKit（Safari 内核）里把每个功能点一遍：列表卡片、上传、重试、删除、精听页的字幕/星标/听错原因/生词/笔记/播放条/快捷键、笔记本浏览和复习，以及亮色/暗色、1280/1000/390 宽度。还覆盖后端修复：服务重启后卡住的项目、只重做翻译的重试、音频只给项目主人。

**全部跑在沙盒副本上，数据是 `seed.py` 编造的。** 仓库是公开的，这里不放任何真实用户数据和截图；截图默认输出到系统临时目录。

| 文件 | 作用 |
| --- | --- |
| `make_sandbox.sh` | 把当前代码（不含数据目录和 `.env`）复制到新目录，再灌数据 |
| `seed.py` | 灌编造的数据：用户 `demo`（5 个项目）和 `demo2`（无项目），音频用 macOS `say` 合成；登录 token 写进 `<沙盒>/e2e_tokens.json` |
| `serve.sh` | 在沙盒里起服务：代理指向不存在的端口、API key 全部置空 |
| `e2e.js` | 检查脚本 |

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

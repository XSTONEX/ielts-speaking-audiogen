# 学习技巧页的浏览器测试

在真浏览器（Chromium、WebKit 即 Safari 内核）里把 `/study_techniques` 的每个功能点一遍。
只在一份**代码沙盒**里跑：数据全是 `make_fixtures.py` 编造的，网络被挡住、API key 为空，
不碰真实数据，也不花 API 的钱。仓库是公开的，这里不放真实数据，截图也不要提交。

| 文件 | 做什么 |
| --- | --- |
| `make_fixtures.py` | 往沙盒里写编造的学习技巧数据和测试账号 `demo`；`--mint-token` 顺便发一个登录 token |
| `run_sandbox.sh` | 在沙盒里起应用（挡网络、清空 key） |
| `page.js` | 功能测试：排序、新建/编辑/改名/删除、全屏、导入、阅读和目录、编辑器、防 XSS 等 130 多项 |
| `corrupt.js` | 数据文件写坏时，页面显示「没加载出来」，不会把坏文件盖掉 |
| `shots.js` | 亮/暗 × 1280/390 宽，每个画面截图并检查横向溢出 |
| `common.js` | 上面三个脚本共用的配置 |

脚本每次开跑都会用 `make_fixtures.py` 把沙盒数据重置一遍，跑的过程中会增删数据。
它们拒绝对有 `.git` 的目录（真实仓库）或非本机地址运行。

## 需要

- 能连上 cdn.jsdelivr.net：页面从那里加载 marked 和 DOMPurify。连不上时脚本会先报出来并以退出码 3 退出
- 项目的 Python 虚拟环境 `.venv`（起服务器、发 token 要用；在 worktree 里没有 `.venv`，用主仓库的）
- node ≥ 20（playwright-core 的要求；例如 nvm 装的 node 22）
- playwright-core 和它的浏览器。本仓库不带，装在仓库外面任何地方都行，用 `PLAYWRIGHT_CORE` 指过去：

  ```bash
  mkdir -p ~/pw && cd ~/pw && npm i playwright-core && npx playwright-core install chromium webkit
  export PLAYWRIGHT_CORE=~/pw/node_modules/playwright-core
  ```

## 1. 建沙盒（在仓库根目录执行）

只复制受 git 管的代码文件（真实数据都在 .gitignore 里，不会被带过去），再写入编造的数据：

```bash
PY=$PWD/.venv/bin/python        # worktree 里换成主仓库的 .venv/bin/python
SBX=$(mktemp -d)/sbx && mkdir -p "$SBX"
git ls-files -co --exclude-standard -z | rsync -a --from0 --files-from=- ./ "$SBX/"
"$PY" tests/e2e/study_tips/make_fixtures.py "$SBX" --mint-token
```

`--mint-token` 会把 demo 的 token 写到 `$SBX/e2e_token.txt`，脚本默认从这里读。
改了代码想再测，重新执行 rsync 那一行即可（数据和 token 留着）。

## 2. 起沙盒服务器（另开一个终端，一直开着）

```bash
PYTHON="$PY" tests/e2e/study_tips/run_sandbox.sh "$SBX" 5071
```

## 3. 跑测试

```bash
export STUDY_TIPS_SANDBOX="$SBX"
node tests/e2e/study_tips/page.js chromium
node tests/e2e/study_tips/page.js webkit
node tests/e2e/study_tips/corrupt.js chromium
node tests/e2e/study_tips/shots.js chromium     # 截图，可选
```

每个脚本逐项打印 PASS / FAIL，全部通过退出码为 0；连不上 jsdelivr 时退出码为 3。

## 环境变量

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `STUDY_TIPS_SANDBOX` | （必填） | 沙盒目录 |
| `STUDY_TIPS_BASE_URL` | `http://localhost:5071` | 沙盒服务器地址，只接受本机 |
| `STUDY_TIPS_TOKEN_FILE` | `$STUDY_TIPS_SANDBOX/e2e_token.txt` | demo 的登录 token |
| `STUDY_TIPS_OUT` | 系统临时目录下的 `study_tips_e2e` | 截图和结果写到这里 |
| `PYTHON` | `python3` | 脚本重置数据时用来跑 `make_fixtures.py`（只用标准库） |
| `PLAYWRIGHT_CORE` | `playwright-core` | playwright-core 的路径 |

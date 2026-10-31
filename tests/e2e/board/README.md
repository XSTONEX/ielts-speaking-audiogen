# 学习交流小天地 · 浏览器测试

用真的浏览器（Chromium 和 WebKit / Safari 内核）把 `/message_board` 的每个功能点一遍：发帖带录音 / 文章 / 图片 / 挑战、做挑战、被 @ 的人和没被邀请的人、评论、看大图、播放、删除、手机宽度、暗色、删帖连带删评论。

全程在**仓库外的一份代码拷贝**里跑，数据都是编造的（林夏 / 周屿 / 陈默三个假用户），网络断开、API key 清空，不会花钱，也不会碰到真实数据。仓库是公开的，不要把真实用户数据或截图提交进来。

## 需要准备的

- 仓库的 `.venv`（Python 依赖，里面有 Pillow），以及 `ffmpeg`（生成静音录音）。
- Node 22。
- `playwright-core` 和它对应版本的 Chromium、WebKit：在任意目录 `npm install playwright-core`，再 `npx playwright-core install chromium webkit`。已经装过的话，把 `PLAYWRIGHT_CORE` 指到那份 `node_modules/playwright-core` 就行。

## 1. 建沙盒

沙盒是仓库代码的拷贝（只拷 git 管理的文件，不带任何数据），必须放在仓库外面：

```bash
SB=~/ielts-mb-sandbox
mkdir -p "$SB" && git ls-files -z | rsync -a --from0 --files-from=- ./ "$SB/"
```

在仓库根目录执行。改了代码以后重新跑一次这条命令，沙盒里的代码才会更新。

然后写入假数据（每次都会恢复成同样的初始状态）：

```bash
.venv/bin/python tests/e2e/board/make_fake_data.py "$SB"
```

它会写 `users.json`、`tokens.json`、录音、精读文章、帖子、评论，以及 `$SB/_e2e/` 下的 token 和上传用测试文件。目录是仓库本身或在仓库里面时会拒绝执行。

## 2. 启动沙盒服务器

```bash
tests/e2e/board/run_sandbox.sh "$SB"
```

默认端口 5066（`PORT=xxxx` 可改）。代理指向关着的端口、所有 API key 设为空，单词发音之类要联网的东西会静默失败，这是正常的。`run_all.sh` 发现端口上没有服务器时会自己起一个，跑完关掉，所以这一步也可以跳过。

## 3. 跑测试

一次跑完（重建数据 → 01–06 → 再重建数据 → 07）：

```bash
PATH=<node 22 的 bin 目录>:$PATH PLAYWRIGHT_CORE=<playwright-core 目录> \
  tests/e2e/board/run_all.sh "$SB" chromium
```

把最后的 `chromium` 换成 `webkit` 再跑一遍。全部通过时最后一行是「全部通过」，退出码 0；有问题时往上找 `FAIL`、`ERRORS`、`CRASH`。

想要截图就再加 `MB_SHOTS=<截图目录>`（不设就不截图）。截图只留在本地，不要提交。

单独跑某一个脚本：

```bash
MB_SANDBOX="$SB" ENGINE=webkit PLAYWRIGHT_CORE=<playwright-core 目录> node tests/e2e/board/04_misc.js
```

注意 02–06 是接着前一个脚本的数据往下走的（比如 03 要做 02 发起的挑战），单独跑时先按顺序把前面的跑完；07 要在刚建好的假数据上跑。

## 脚本

| 文件 | 内容 |
| --- | --- |
| `make_fake_data.py` | 建假数据和 token |
| `run_sandbox.sh` | 断网、清空 key 后启动沙盒服务器 |
| `run_all.sh` | 按顺序跑全部脚本 |
| `lib.js` | 公共部分：登录、打开页面、截图、答题、统计失败 |
| `01_render.js` | 亮色 / 暗色打开页面 |
| `02_post_and_quiz.js` | 林夏发帖（录音含撇号、搜索、文章、多图和超大 / 非图片文件、挑战），自己做挑战（数字键、退出再继续、超时揭晓、交卷、排名），描述里的 HTML 当文字显示 |
| `03_invitees_and_comments.js` | 周屿被 @ 做挑战、待完成列表、评论带四种附件和挑战；陈默「我也做一次」 |
| `04_misc.js` | 看大图、帖子里播放、链接、删评论、删帖、空列表、读取失败、没登录跳登录页 |
| `05_phone.js` | 390 宽不横向溢出，手机上发帖、答题、看大图、排名 |
| `06_dark.js` | 暗色下的各个弹窗 |
| `07_delete_cascade.js` | 删帖时评论和评论里的挑战一起删掉，别的帖子的评论不受影响 |

环境变量：`MB_SANDBOX`（沙盒目录，单独跑脚本时必填）、`MB_BASE_URL`（默认 `http://localhost:5066`）、`ENGINE`（`chromium` 或 `webkit`）、`MB_SHOTS`、`PLAYWRIGHT_CORE`；`run_all.sh` 和 `run_sandbox.sh` 还认 `PORT`、`PYTHON`、`NODE`。

设计稿：<https://claude.ai/artifact/K2TS66ABkrU6WCRkdvsrhM>「学习交流小天地 · 改版」。

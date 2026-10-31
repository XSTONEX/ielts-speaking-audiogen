// 学习交流小天地浏览器测试的公共部分。配置全走环境变量，见 README.md。
const fs = require('fs');
const path = require('path');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const SANDBOX = process.env.MB_SANDBOX;
if (!SANDBOX) {
  console.log('CRASH 请设置 MB_SANDBOX=<沙盒目录>（先跑 make_fake_data.py）');
  process.exit(1);
}
const BASE = (process.env.MB_BASE_URL || 'http://localhost:5066').replace(/\/$/, '');
const SHOTS = process.env.MB_SHOTS || '';          // 不设就不截图
const ENGINE = process.env.ENGINE || 'chromium';   // chromium 或 webkit
const FX = path.join(SANDBOX, '_e2e', 'fixtures');
const toks = JSON.parse(fs.readFileSync(path.join(SANDBOX, '_e2e', 'tokens.json'), 'utf8'));
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const errors = [];
const allowed = [];     // 故意制造的错误（比如模拟服务器 500），不算失败
let fails = 0;

function ok(cond, msg) {
  if (!cond) fails++;
  console.log((cond ? 'PASS ' : 'FAIL ') + msg);
}
function allowError(pattern) { allowed.push(pattern); }
function report(m) {
  if (allowed.some(p => p.test(m))) return;
  errors.push(m);
  console.log(m);
}

// 只放行沙盒服务器的请求：外部字体、CDN 一律拦掉，测试完全离线（登录页的谷歌字体会卡住 load）
async function offline(ctx) {
  const origin = new URL(BASE).origin;
  await ctx.route('**/*', r => {
    const u = new URL(r.request().url());
    return /^https?:$/.test(u.protocol) && u.origin !== origin ? r.abort() : r.continue();
  });
}

// 以某个假用户身份打开一个浏览器上下文（直接塞 token，不走登录页）
async function login(browser, who, opts = {}) {
  const vp = opts.width ? { width: opts.width, height: opts.height || 860 } : { width: 1280, height: 860 };
  const ctx = await browser.newContext({ viewport: vp, colorScheme: opts.dark ? 'dark' : 'light' });
  await offline(ctx);
  await ctx.addInitScript(([t, u, theme]) => {
    localStorage.setItem('authToken', t);
    localStorage.setItem('currentUser', JSON.stringify(u));
    localStorage.setItem('ui-theme', theme);
  }, [toks[who].token, toks[who].user, opts.dark ? 'dark' : 'light']);
  const page = await ctx.newPage();
  page.on('pageerror', e => report(`[${who}] pageerror: ${e.message}`));
  // 404 是沙盒里没有的头像 / 单词音频，不算页面错误
  page.on('console', m => { if (m.type() === 'error' && !/404/.test(m.text())) report(`[${who}] console.error: ${m.text()}`); });
  page.on('dialog', async d => { report(`[${who}] 弹出了浏览器原生对话框: ${JSON.stringify(d.message())}`); await d.accept(); });
  return { ctx, page };
}

async function open(page) {
  await page.goto(BASE + '/message_board');
  await page.waitForSelector('.mb-post', { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(1200);
}

async function shot(page, name, opts = {}) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${ENGINE}-${name}.png`), ...opts });
}

// 一直按 1 / 2 答题直到交卷
async function doQuiz(page) {
  await page.waitForSelector('.mb-quiz .mb-opt');
  for (let i = 0; i < 150; i++) {
    if (await page.locator('.ui-dialog:has-text("交卷了")').count()) return;
    const free = await page.locator('.mb-quiz .mb-opt:not(:disabled)').count();
    if (free) await page.keyboard.press(String(1 + (i % 2)));
    await page.waitForTimeout(400);
  }
}

// 跑一个测试脚本：有 FAIL、页面报错或崩溃时退出码为 1
function run(main) {
  (async () => {
    const browser = await pw[ENGINE].launch();
    try {
      await main(browser);
    } finally {
      await browser.close();
    }
    console.log(`ERRORS ${errors.length} ${JSON.stringify(errors)}`);
    process.exitCode = fails || errors.length ? 1 : 0;
  })().catch(e => { console.log('CRASH ' + e.message); process.exit(1); });
}

module.exports = { ok, login, offline, open, shot, doQuiz, run, allowError, BASE, ENGINE, FX, SANDBOX, toks };

// 写作逻辑训练浏览器测试的公共部分。配置全走环境变量，见 README.md。
const fs = require('fs');
const path = require('path');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const SANDBOX = process.env.WP_SANDBOX;
if (!SANDBOX) {
  console.log('CRASH 请设置 WP_SANDBOX=<沙盒目录>（先跑 make_fake_data.py）');
  process.exit(1);
}
const BASE = (process.env.WP_BASE_URL || 'http://localhost:5131').replace(/\/$/, '');
const SHOTS = process.env.WP_SHOTS || '';          // 不设就不截图
const ENGINE = process.env.ENGINE || 'webkit';     // webkit 或 chromium
const TOKEN = JSON.parse(fs.readFileSync(path.join(SANDBOX, '_e2e', 'tokens.json'), 'utf8')).linxia.token;
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

// 批改、追问、AI 助手一律在浏览器里拦下，回一份编好的结果：不连任何大模型
const FAKE_GRADE = {
  score: '5.5',
  feedback_summary: '意思基本到位，但主谓一致和时态有问题，个别搭配不够地道。',
  grammar_corrections: [
    { type: '主谓一致', original: 'technology have changed', corrected: 'technology has changed', reason: 'technology 是不可数名词，谓语用单数。' },
    { type: '时态', original: 'people communicate', corrected: 'people have communicated', reason: '变化从过去持续到现在，用现在完成时。' },
    { type: '拼写', original: 'enviroment', corrected: 'environment', reason: '' },
  ],
  vocabulary_upgrade: [
    { original: 'very important', replacement: 'crucial', reason: '更简洁，学术语气更强。' },
    { original: 'a lot of', replacement: 'a considerable number of', reason: '正式写作里替代口语表达。' },
  ],
  native_version: '1. 标准答案：Technology has fundamentally transformed the way people communicate with each other. 2. 你的结构优化版：Technology has changed how people communicate, which is crucial for a considerable number of families.',
};

const errors = [];
let fails = 0;
function ok(cond, msg) {
  if (!cond) fails++;
  console.log((cond ? 'PASS ' : 'FAIL ') + msg);
}
function report(m) { errors.push(m); console.log(m); }

// 一个检查出了异常（比如旧页面上根本没有这个按钮）记成 FAIL，后面的检查照跑
async function step(name, fn) {
  try { await fn(); } catch (e) { ok(false, `${name}：${String(e.message || e).split('\n')[0]}`); }
}

// 只放行沙盒服务器；marked / DOMPurify 两个 CDN 脚本换成本地小桩，测试完全离线
async function offline(ctx) {
  const origin = new URL(BASE).origin;
  await ctx.route('**/*', r => {
    const u = new URL(r.request().url());
    if (/^https?:$/.test(u.protocol) && u.origin !== origin) {
      if (/marked/.test(u.pathname)) return r.fulfill({ contentType: 'text/javascript', body: 'window.marked={parse:function(s){return String(s).replace(/</g,"&lt;")}};' });
      if (/purify/.test(u.pathname)) return r.fulfill({ contentType: 'text/javascript', body: 'window.DOMPurify={sanitize:function(s){return s}};' });
      return r.abort();
    }
    return r.continue();
  });
  const json = body => route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  await ctx.route(/\/api\/writing\/(small\/|template\/)?correct(\?|$)/, json(FAKE_GRADE));
  await ctx.route(/\/api\/writing\/ai_chat\/practice/, json({ content: '这里用现在完成时，是因为变化从过去持续到现在。' }));
  await ctx.route(/\/api\/writing\/ai_chat\/global/, json({ content: '可以这样开头：It is widely believed that…' }));
}

// 手机：WebKit 390×844（iPhone Safari，WebKit 不认 isMobile）、Chromium 360×780（Android）
// opts.width/height 改尺寸，opts.desktop 用桌面（无触屏），opts.dark 暗色
async function open(browser, opts = {}) {
  const isW = ENGINE === 'webkit';
  const vp = opts.width ? { width: opts.width, height: opts.height || 900 }
    : (isW ? { width: 390, height: 844 } : { width: 360, height: 780 });
  const co = { viewport: vp, colorScheme: opts.dark ? 'dark' : 'light' };
  if (!opts.desktop) { co.hasTouch = true; if (!isW) co.isMobile = true; }
  const ctx = await browser.newContext(co);
  await offline(ctx);
  if (opts.fixedTime && ctx.clock) await ctx.clock.setFixedTime(new Date(opts.fixedTime));
  await ctx.addInitScript(([t, theme]) => {
    if (location.protocol === 'about:') return;
    localStorage.setItem('authToken', t);
    localStorage.setItem('ui-theme', theme);
  }, [TOKEN, opts.dark ? 'dark' : 'light']);
  const page = await ctx.newPage();
  page.on('pageerror', e => report(`pageerror: ${e.message}`));
  page.on('console', m => { if (m.type() === 'error' && !/404|Failed to load resource/.test(m.text())) report(`console.error: ${m.text()}`); });
  // 删除确认之类的原生对话框一律点「确定」
  page.on('dialog', d => d.accept().catch(() => {}));
  await page.goto(BASE + '/writing_practice');
  await page.waitForSelector('.entry-card', { timeout: 8000 });
  await page.waitForTimeout(900);
  return { ctx, page };
}

async function shot(page, name, opts = {}) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${ENGINE}-${name}.png`), animations: 'disabled', ...opts });
}

// 页面有没有横向溢出（滚动宽度超过视口）
async function overflowX(page) {
  return page.evaluate(() => document.scrollingElement.scrollWidth - window.innerWidth);
}

// 元素的位置（视口坐标）；不存在或不可见返回 null
async function box(page, sel) {
  return page.evaluate(s => {
    const e = typeof s === 'string' ? document.querySelector(s) : null;
    if (!e) return null;
    const cs = getComputedStyle(e);
    const b = e.getBoundingClientRect();
    if (cs.display === 'none' || cs.visibility === 'hidden' || !b.width || !b.height) return null;
    return { top: b.top, bottom: b.bottom, left: b.left, right: b.right, width: b.width, height: b.height };
  }, sel);
}

function run(main) {
  (async () => {
    const browser = await pw[ENGINE].launch();
    try {
      await main(browser);
    } finally {
      await browser.close();
    }
    console.log(`ERRORS ${errors.length} ${JSON.stringify(errors)}`);
    console.log(`SUMMARY ${ENGINE} fails=${fails} errors=${errors.length}`);
    process.exitCode = fails || errors.length ? 1 : 0;
  })().catch(e => { console.log('CRASH ' + e.message); process.exit(1); });
}

module.exports = { ok, step, open, shot, overflowX, box, run, report, BASE, ENGINE, SANDBOX, SHOTS, FAKE_GRADE };

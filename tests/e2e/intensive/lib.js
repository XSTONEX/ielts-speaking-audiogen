// 文章精读浏览器测试的公共部分：读配置、开浏览器上下文、计数、清理测试留下的东西。
// 只连本机的沙盒服务器（make_fake_data.py 造的编造数据），不碰真数据。
const fs = require('fs');
const os = require('os');
const path = require('path');

const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

// 和 make_fake_data.py 里的文章 ID 保持一致
const IDS = {
  lighthouse: '20261020090000-The-Lighthouse-Keeper-s-Log',
  ferry: '20261019090000-Night-Ferry-Timetable',
  coldChain: '20261018090000-The-Cold-Chain',
  emoji: '20261017090000-助记小文章-天气与心情',
  ropeBridge: '20261001090000-The-Rope-Bridge-Builders',
  chart: '20261016090000-Task1-饼图-城市用电来源',
  saltMarsh: '20261015090000-The-Salt-Marsh-Survey',
  glassBridge: '20261021090000-The-Glass-Bridge',
};
const FAKE_USER = 'reader01';
// 测试自己建的文章（导入 / 粘贴文本）和自己存的释义，用这些规则认出来，跑完删掉
const TEST_TITLE = /（(chromium|webkit)）$|^Plain (chromium|webkit)$/;
const TEST_MEANING = /e2e/;

const SUITES = ['select', 'touch', 'import', 'misc'];
const ENGINES = ['chromium', 'webkit'];

function usage(msg) {
  if (msg) console.error(msg + '\n');
  console.error(`用法：node run.js [套件...] [浏览器...] [--base-url URL] [--token-file 文件] [--out 目录]
  套件：${SUITES.join(' ')}（默认全部）   浏览器：${ENGINES.join(' ')}（默认两个都跑）
  环境变量：E2E_BASE_URL（默认 http://127.0.0.1:5071）、E2E_TOKEN_FILE（必填）、E2E_OUT、PLAYWRIGHT_CORE`);
  process.exit(2);
}

function loadConfig(argv) {
  const opt = {};
  const names = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '-h' || a === '--help') usage();
    else if (a.startsWith('--')) {
      const [k, v] = a.includes('=') ? a.slice(2).split(/=(.*)/s) : [a.slice(2), argv[++i]];
      if (v === undefined) usage(`${a} 缺少取值`);
      opt[k] = v;
    } else names.push(a);
  }
  const unknown = names.filter(n => !SUITES.includes(n) && !ENGINES.includes(n));
  if (unknown.length) usage(`不认识：${unknown.join(' ')}`);
  const baseUrl = (opt['base-url'] || process.env.E2E_BASE_URL || 'http://127.0.0.1:5071').replace(/\/+$/, '');
  const host = new URL(baseUrl).hostname;
  // 测试会往服务器上写东西（导入文章、存高亮、改分类再改回来），只允许连本机的沙盒
  if (!['127.0.0.1', 'localhost', '[::1]', '::1'].includes(host)) usage(`只能对本机沙盒跑，${baseUrl} 不是本机地址`);
  const tokenFile = opt['token-file'] || process.env.E2E_TOKEN_FILE;
  if (!tokenFile) usage('缺少 token 文件：用 --token-file 或 E2E_TOKEN_FILE 指定 make_fake_data.py 写出的 e2e_token.txt');
  const token = fs.readFileSync(tokenFile, 'utf8').trim();
  const out = path.resolve(opt.out || process.env.E2E_OUT || path.join(os.tmpdir(), 'intensive-e2e'));
  fs.mkdirSync(out, { recursive: true });
  return {
    baseUrl, token, out,
    suites: names.filter(n => SUITES.includes(n)).length ? SUITES.filter(s => names.includes(s)) : SUITES,
    engines: names.filter(n => ENGINES.includes(n)).length ? ENGINES.filter(e => names.includes(e)) : ENGINES,
  };
}

// 一个套件在一个浏览器里的检查结果
class Checks {
  constructor(engine, suite) { this.engine = engine; this.suite = suite; this.pass = 0; this.fail = 0; this.fails = []; }
  ok(cond, what) {
    if (cond) this.pass++;
    else { this.fail++; this.fails.push(what); }
    return !!cond;
  }
}

// 页面上的变量是 let 声明的（currentArticle、selectionRange、highlights、allItems），不在 window 上，
// page.evaluate 里直接写名字用。
async function newContext(cfg, browser, options = {}) {
  const ctx = await browser.newContext(options);
  const origin = new URL(cfg.baseUrl).origin;
  // 兜底：页面只该请求本机服务器，别的一律掐掉（页面本来也没有外链）
  await ctx.route(url => /^https?:$/.test(url.protocol) && url.origin !== origin, route => route.abort());
  await ctx.addInitScript(t => {
    if (location.protocol === 'about:') return;
    try { localStorage.setItem('authToken', t); } catch (e) {}
  }, cfg.token);
  return ctx;
}

async function apiContext(cfg) {
  return pw.request.newContext({ baseURL: cfg.baseUrl, extraHTTPHeaders: { Authorization: 'Bearer ' + cfg.token } });
}

// 确认连的是 make_fake_data.py 造的沙盒：token 属于测试用户、编造的文章都在
async function preflight(cfg) {
  const api = await apiContext(cfg);
  try {
    let r;
    try { r = await api.post('/verify_token', { data: { token: cfg.token } }); } catch (e) {
      throw new Error(`连不上 ${cfg.baseUrl}：先用 sandbox.sh start 启动沙盒服务器（${e.message.split('\n')[0]}）`);
    }
    const v = await r.json();
    if (!v.valid || (v.user && v.user.username) !== FAKE_USER) {
      throw new Error(`token 不是测试用户 ${FAKE_USER} 的（${JSON.stringify(v)}）。这不是 make_fake_data.py 造的沙盒，不跑。`);
    }
    const items = (await (await api.get('/intensive_list')).json()).items || [];
    const missing = Object.values(IDS).filter(id => !items.some(it => it.id === id));
    if (missing.length) throw new Error(`沙盒里缺编造的文章 ${missing.join(', ')}：重新跑一遍 make_fake_data.py`);
  } finally {
    await api.dispose();
  }
}

// 删掉测试建的文章、存的释义，还原被改过的分类。每个套件前后各跑一次，上次中途崩了也不影响这次。
async function cleanup(cfg) {
  const api = await apiContext(cfg);
  try {
    const items = (await (await api.get('/intensive_list')).json()).items || [];
    for (const it of items) {
      if (TEST_TITLE.test(it.title || '')) await api.post('/intensive_delete_article', { data: { id: it.id } });
    }
    for (const id of [IDS.lighthouse, IDS.ropeBridge, IDS.glassBridge, IDS.emoji]) {
      const art = (await (await api.get('/intensive_article/' + encodeURIComponent(id))).json()).article;
      for (const h of art.highlights || []) {
        if (TEST_MEANING.test(h.meaning || '')) await api.post('/intensive_delete_highlight', { data: { id, highlight_id: h.id } });
      }
    }
    const want = { [IDS.chart]: 'Writing', [IDS.saltMarsh]: 'Listening' };
    for (const it of items) {
      if (want[it.id] && it.category !== want[it.id]) await api.post('/intensive_update_category', { data: { id: it.id, category: want[it.id] } });
    }
  } finally {
    await api.dispose();
  }
}

// 新开一个页面，并记下它还有几个请求没回来。跳页 / 刷新前先 settle(page)：
// 不然 WebKit 会把被打断的 fetch 报成 "Load failed" / "access control checks" 错误，测出来的不是页面的问题。
async function newPage(ctx, timeout = 8000) {
  const page = await ctx.newPage();
  page.setDefaultTimeout(timeout);
  let pending = 0;
  page.on('request', () => { pending++; });
  const done = () => { pending = Math.max(0, pending - 1); };
  page.on('requestfinished', done);
  page.on('requestfailed', done);
  page.__pending = () => pending;
  return page;
}
async function settle(page, quietMs = 300, timeoutMs = 5000) {
  const end = Date.now() + timeoutMs;
  let quietSince = Date.now();
  while (Date.now() < end) {
    if (page.__pending() > 0) quietSince = Date.now();
    else if (Date.now() - quietSince >= quietMs) return;
    await page.waitForTimeout(50);
  }
}

// 打开列表页，等文章列表加载完
async function openList(page, cfg) {
  await page.goto(cfg.baseUrl + '/intensive');
  await page.waitForFunction(() => typeof openArticle === 'function' && typeof allItems !== 'undefined' && allItems.length > 0, null, { timeout: 15000 });
}

// 在页面里打开一篇文章，等正文画出来
async function openArticle(page, id) {
  await page.evaluate(id => openArticle(id), id);
  await page.waitForFunction(id => typeof currentArticle !== 'undefined' && currentArticle && currentArticle.id === id && document.querySelector('#vContent .reader p'), id);
  await page.waitForTimeout(200);
}

module.exports = { pw, IDS, SUITES, ENGINES, loadConfig, Checks, newContext, newPage, settle, apiContext, preflight, cleanup, openList, openArticle };

// 横着拿的手机：每个导航能去的页面都要用手机布局，并且按「矮屏」收紧（2026-11）。
// 设备：WebKit 844×390、932×430（iPhone 横屏，触屏；WebKit 不认 isMobile），Chromium 915×412（安卓横屏，isMobile + 触屏）。
// 每页查：手机布局生效、不横向溢出、全站导航不钉在顶上（往下翻就滚走）、主要按钮在屏幕里且 ≥ 40px、
// 面板 / 弹窗的按钮看得见（只滚中间的内容）、转屏（竖 → 横 → 竖）以后打开着的东西还在、历史记录不多不少。
// 另外查两条反例：带鼠标的电脑窗口再矮也不用手机布局，iPad 横屏（1180×820 触屏）也不用。
// 用法见 README.md；一般用 run.sh 起沙盒再跑。参数：webkit / chromium（默认两个都跑）。
const fs = require('fs');
const os = require('os');
const path = require('path');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const CFG = JSON.parse(fs.readFileSync(process.env.LS_CONFIG || '', 'utf8'));
const OUT = process.env.LS_OUT || path.join(os.tmpdir(), 'landscape-e2e');
fs.mkdirSync(OUT, { recursive: true });
for (const m of Object.values(CFG)) {
  if (!/^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(m.base)) { console.error('只连本机沙盒：' + m.base); process.exit(2); }
  m.token = fs.readFileSync(path.join(m.sandbox, 'e2e_token.txt'), 'utf8').trim();
  const users = path.join(m.sandbox, '_e2e', 'tokens.json');
  m.user = fs.existsSync(users) ? (JSON.parse(fs.readFileSync(users, 'utf8')).linxia || {}).user || null : null;
}

const ENGINES = process.argv.slice(2).filter(a => a === 'webkit' || a === 'chromium');
if (!ENGINES.length) ENGINES.push('webkit', 'chromium');
const DEVICES = {
  webkit: [
    { name: 'wk844', viewport: { width: 844, height: 390 }, portrait: { width: 390, height: 844 } },
    { name: 'wk932', viewport: { width: 932, height: 430 }, portrait: { width: 430, height: 932 } },
  ],
  chromium: [
    { name: 'cr915', viewport: { width: 915, height: 412 }, portrait: { width: 412, height: 915 }, isMobile: true },
  ],
};
// 九分学长导入的听力篇：沙盒里的 JSON 和音频由 jiufen_data.py 造好
const HALL = 'lr_20261028_201500_demo0001';
const IR = { lighthouse: '20261020090000-The-Lighthouse-Keeper-s-Log', glassBridge: '20261021090000-The-Glass-Bridge' };
const HOMETOWN = 'P1 - Hometown';

let pass = 0, fail = 0;
const fails = [];
let TAG = '';
function ok(cond, name, detail) {
  if (cond) pass++; else { fail++; fails.push(`${TAG} ${name}`); }
  console.log(`${cond ? 'PASS' : 'FAIL'} [${TAG}] ${name}${cond || detail === undefined ? '' : '  → ' + JSON.stringify(detail)}`);
  return !!cond;
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
// 一段检查出错（比如对着改版前的页面跑，元素不存在）只记一项失败，接着跑下一段
async function section(name, fn) {
  try { await fn(); } catch (e) { ok(false, `${name}：跑完整段`, String(e && e.message || e).split('\n')[0]); }
}

async function newPage(browser, dev, mod, opts = {}) {
  const co = { viewport: opts.viewport || dev.viewport, hasTouch: true, deviceScaleFactor: 1, colorScheme: opts.dark ? 'dark' : 'light' };
  if (dev.isMobile) co.isMobile = true;
  const ctx = await browser.newContext(co);
  const origin = mod ? new URL(mod.base).origin : null;
  // 只放行沙盒自己（写作 / 技巧页的 marked、DOMPurify 换成本地小桩），完全离线，不碰付费接口
  await ctx.route('**/*', r => {
    const u = new URL(r.request().url());
    if (!/^https?:$/.test(u.protocol) || u.origin === origin) return r.continue();
    if (/marked/.test(u.pathname)) return r.fulfill({ contentType: 'text/javascript', body: 'window.marked={parse:function(s){return String(s).replace(/</g,"&lt;")}};' });
    if (/purify/.test(u.pathname)) return r.fulfill({ contentType: 'text/javascript', body: 'window.DOMPurify={sanitize:function(s){return s}};' });
    return r.abort();
  });
  await ctx.addInitScript(([t, u, theme]) => {
    if (location.protocol === 'about:') return;
    if (t) localStorage.setItem('authToken', t);
    if (u) localStorage.setItem('currentUser', JSON.stringify(u));
    localStorage.setItem('ui-theme', theme);
  }, [mod && !opts.anon ? mod.token : null, mod && !opts.anon ? mod.user : null, opts.dark ? 'dark' : 'light']);
  const page = await ctx.newPage();
  page.setDefaultTimeout(6000);
  page.errors = [];
  page.on('pageerror', e => page.errors.push(e.message));
  page.on('dialog', d => d.dismiss().catch(() => {}));
  return { ctx, page };
}
async function shot(page, name) { await sleep(250); await page.screenshot({ path: path.join(OUT, `${TAG}-${name}.png`) }); }

// ---------- 页面里的小工具 ----------
const R = (page, sel) => page.evaluate(s => {
  const e = document.querySelector(s);
  if (!e) return null;
  const r = e.getBoundingClientRect(), cs = getComputedStyle(e);
  return { t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height),
    shown: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden', vw: innerWidth, vh: innerHeight };
}, sel);
const overflow = page => page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth);
const histLen = page => page.evaluate(() => history.length);
// 完整地在屏幕里、够大
function inView(r, min = 40) { return !!r && r.shown && r.t >= -1 && r.b <= r.vh + 1 && r.l >= -1 && r.r <= r.vw + 1 && r.h >= min; }

async function checkPhoneNav(page, where) {
  const s = await page.evaluate(() => {
    const vis = sel => { const e = document.querySelector(sel); if (!e) return null; const cs = getComputedStyle(e); return cs.display !== 'none' && cs.visibility !== 'hidden' && e.getBoundingClientRect().width > 0; };
    return { current: vis('.app-shell-current'), links: vis('.app-shell-links') };
  });
  ok(s.current === true && s.links === false, `${where}：手机布局（导航收成「模块 ▾」，没有七个平铺的链接）`, s);
}
async function checkOverflow(page, where) {
  const o = await overflow(page);
  ok(o <= 0, `${where}：不横向溢出`, o);
}
// 往下翻 300px 以后全站导航已经滚出屏幕（不再钉在顶上占 52px）
async function checkNavScrolls(page, where) {
  const st = await page.evaluate(async () => {
    const room = document.documentElement.scrollHeight - innerHeight;
    window.scrollTo(0, 300);
    await new Promise(r => setTimeout(r, 250));
    const n = document.querySelector('.app-shell-nav');
    const b = n ? Math.round(n.getBoundingClientRect().bottom) : null;
    const y = window.scrollY;
    window.scrollTo(0, 0);
    await new Promise(r => setTimeout(r, 150));
    return { room, y, navBottom: b };
  });
  ok(st.navBottom !== null && st.y > 60 && st.navBottom <= 0, `${where}：往下翻时全站导航跟着滚走`, st);
}
// 转屏：竖 → 横 → 竖，打开着的东西还在，历史记录条数不变
async function rotate(page, dev, isOpen, where) {
  const before = { open: await isOpen(), hist: await histLen(page) };
  await page.setViewportSize(dev.viewport); await sleep(500);
  const mid = await isOpen();
  await page.setViewportSize(dev.portrait); await sleep(500);
  const after = { open: await isOpen(), hist: await histLen(page) };
  ok(before.open && mid && after.open, `${where}：竖 → 横 → 竖转屏以后还开着`, { before, mid, after });
  ok(before.hist === after.hist, `${where}：转屏不多压、不退历史记录`, { before: before.hist, after: after.hist });
  return before.open && mid && after.open;
}

// ==================== 首页、登录 ====================
async function home(browser, dev) {
  const M = CFG.home;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('首页', async () => {
    await page.goto(M.base + '/'); await page.waitForSelector('.app-shell-nav'); await sleep(800);
    await checkPhoneNav(page, '首页');
    await checkOverflow(page, '首页');
    await checkNavScrolls(page, '首页');
    await page.tap('.app-shell-current'); await sleep(300);
    const p = await R(page, '#appShellPanel');
    const tiles = await page.$$eval('.app-shell-tile', ts => ts.map(t => Math.round(t.getBoundingClientRect().height)));
    ok(inView(p, 10) && tiles.length === 7 && tiles.every(h => h >= 40), '首页：模块面板整个在屏幕里，七个入口 ≥ 40px', { p, tiles });
    await shot(page, 'home-panel');
    await page.tap('.app-shell-current'); await sleep(200);
  });
  await section('首页转屏', async () => {
    await page.setViewportSize(dev.portrait); await page.goto(M.base + '/'); await page.waitForSelector('.app-shell-nav'); await sleep(600);
    await page.tap('.app-shell-current'); await sleep(300);
    await rotate(page, dev, () => page.evaluate(() => { const p = document.getElementById('appShellPanel'); return !p.hidden && p.getBoundingClientRect().height > 60; }), '首页模块面板');
  });
  ok(!page.errors.length, '首页：没有脚本报错', page.errors);
  await ctx.close();

  const lg = await newPage(browser, dev, M, { anon: true });
  await section('登录', async () => {
    await lg.page.goto(M.base + '/login'); await sleep(600);
    await checkOverflow(lg.page, '登录');
    const f = await lg.page.evaluate(() => [...document.querySelectorAll('input, button[type=submit]')].filter(e => e.offsetWidth).map(e => Math.round(e.getBoundingClientRect().height)));
    ok(f.length >= 3 && f.every(h => h >= 40), '登录：输入框和登录按钮 ≥ 40px', f);
    const room = await lg.page.evaluate(() => { const b = document.querySelector('button[type=submit]'); b.scrollIntoView({ block: 'end' }); const r = b.getBoundingClientRect(); return { b: Math.round(r.bottom), vh: innerHeight }; });
    ok(room.b <= room.vh, '登录：翻下去能点到「登录」', room);
  });
  await lg.ctx.close();
}

// ==================== 口语 ====================
async function speaking(browser, dev) {
  const M = CFG.speaking;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('口语音频库', async () => {
    await page.goto(M.base + '/speaking'); await page.waitForSelector('#topicList .sp-tcard', { timeout: 10000 }); await sleep(500);
    await checkPhoneNav(page, '口语');
    await checkOverflow(page, '口语');
    await checkNavScrolls(page, '口语');
    const cols = await page.$$eval('#topicList > .sp-tcard', cs => new Set(cs.slice(0, 6).map(c => Math.round(c.getBoundingClientRect().top))).size);
    ok(cols <= 2, '口语：话题卡一行三张（前六张只占两排）', cols);
    await page.evaluate(() => window.scrollTo(0, 500)); await sleep(300);
    const s = await page.evaluate(() => { const r = s => { const e = document.querySelector(s); return e ? e.getBoundingClientRect() : null; }; const a = r('.sp-searchbar'), c = r('#partChips'); return a && c ? { searchTop: Math.round(a.top), chipsTop: Math.round(c.top), chromeBottom: Math.round(Math.max(a.bottom, c.bottom)) } : null; });
    ok(!!s && Math.abs(s.searchTop) <= 1 && Math.abs(s.chipsTop - s.searchTop) <= 2 && s.chromeBottom <= 70, '口语：搜索框和 Part 筛选并成一行吸在屏幕顶上（≤ 70px）', s);
    await shot(page, 'speaking-lib');
    await page.evaluate(() => window.scrollTo(0, 0)); await sleep(200);
    await page.tap('#composerFab'); await sleep(600);
    const gen = await R(page, '#generateBtn'), txt = await R(page, '#textInput');
    ok(inView(gen, 44) && !!txt && txt.shown && txt.t < txt.vh - 60, '口语新建音频：英文框露出来、「生成音频」在屏幕里', { gen, txt });
    await shot(page, 'speaking-composer');
    await page.goBack(); await sleep(500);
  });
  await section('口语播放', async () => {
    await page.goto(M.base + '/speaking#folder=' + encodeURIComponent(HOMETOWN)); await page.waitForSelector('.sp-clip'); await sleep(500);
    await page.tap('.sp-clip .sp-play'); await sleep(700);
    const bar = await R(page, '#playerBar');
    ok(inView(bar, 44) && bar.h <= 80 && bar.b === bar.vh, '口语：迷你播放条贴底、一行（≤ 80px）', bar);
    await page.tap('#playerTitle'); await sleep(700);
    const fp = await R(page, '#fullPlayer'), play = await R(page, '#fullPlayer .sp-play--lg'), text = await R(page, '#fullPlayer .sp-fp__text');
    ok(inView(fp, 100) && inView(play, 44) && !!text && text.shown && text.t < text.vh - 40, '口语完整播放器：原文和播放按钮都在屏幕里', { fp, play, text });
    await shot(page, 'speaking-fullplayer');
    await page.goBack(); await sleep(500);
  });
  await section('口语转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/speaking#folder=' + encodeURIComponent(HOMETOWN)); await page.waitForSelector('.sp-clip'); await sleep(500);
    await page.tap('.sp-clip .sp-play'); await sleep(600);
    await page.tap('#playerTitle'); await sleep(700);
    if (await rotate(page, dev, () => page.evaluate(() => { const f = document.getElementById('fullPlayer'); return !f.hidden && f.getBoundingClientRect().height > 100 && !document.getElementById('viewTopic').hidden; }), '口语完整播放器')) {
      await page.goBack(); await sleep(500);
      const st = await page.evaluate(() => ({ fp: document.getElementById('fullPlayer').hidden, topic: !document.getElementById('viewTopic').hidden, path: location.pathname }));
      ok(st.fp && st.topic && st.path === '/speaking', '口语：转屏后返回手势只关播放器，还在话题页', st);
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '口语：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 精读、添加文章 ====================
async function intensive(browser, dev) {
  const M = CFG.intensive;
  const { ctx, page } = await newPage(browser, dev, M);
  const open = async id => { await page.evaluate(id => openArticle(id), id); await page.waitForFunction(id => typeof currentArticle !== 'undefined' && currentArticle && currentArticle.id === id && document.querySelector('#vContent .reader p'), id, { timeout: 8000 }); await sleep(500); };
  await section('精读列表', async () => {
    await page.goto(M.base + '/intensive'); await page.waitForSelector('.ir-card'); await sleep(500);
    await checkPhoneNav(page, '精读列表');
    await checkOverflow(page, '精读列表');
    await checkNavScrolls(page, '精读列表');
    const more = await R(page, '.ir-card .ir-card-more');
    ok(!!more && more.shown && more.w >= 44 && more.h >= 44, '精读列表：卡片上是 44px 的 ⋯（不是垃圾桶）', more);
    const rows = await page.$$eval('#list .ir-card', cs => new Set(cs.slice(0, 6).map(c => Math.round(c.getBoundingClientRect().top))).size);
    ok(rows <= 2, '精读列表：一行三张', rows);
    await page.tap('.ir-card .ir-card-more'); await sleep(400);
    const sheet = await R(page, '#cardSheet');
    ok(inView(sheet, 60), '精读列表：卡片 ⋯ 面板整个在屏幕里', sheet);
    await page.goBack(); await sleep(400);
  });
  await section('精读阅读页', async () => {
    await open(IR.lighthouse);
    const nav = await R(page, '.app-shell-nav');
    ok(!nav || !nav.shown, '阅读页：全站导航收起', nav);
    await checkOverflow(page, '阅读页');
    await page.evaluate(() => window.scrollTo(0, 300)); await sleep(300);
    const v = await page.evaluate(() => { const bar = document.querySelector('#viewer .ir-bar').getBoundingClientRect(), tools = document.querySelector('#viewer .ir-tools').getBoundingClientRect(); const top = Math.max(0, bar.bottom); return { top: Math.round(top), bottom: Math.round(tools.top), toolsH: Math.round(tools.height), vh: innerHeight, ratio: +((tools.top - top) / innerHeight).toFixed(2) }; });
    ok(v.ratio >= 0.8, '阅读页：翻下去以后正文占屏幕高度 ≥ 80%', v);
    const tools = await page.$$eval('#viewer .ir-tools > .ir-icon-btn', bs => bs.filter(b => getComputedStyle(b).display !== 'none').map(b => { const r = b.getBoundingClientRect(); return { h: Math.round(r.height), b: Math.round(r.bottom), t: b.textContent.replace(/\s+/g, '') }; }));
    ok(tools.length >= 3 && tools.every(t => t.h >= 40 && t.b <= v.vh) && tools.some(t => /译文/.test(t.t)), '阅读页：底部工具栏「译文 / 朗读 / 词汇」在屏幕里、≥ 40px', tools);
    const line = await page.evaluate(() => Math.round(document.querySelector('#vContent .reader p.en').getBoundingClientRect().width));
    ok(line <= 760, '阅读页：正文一行不铺满整个横屏（≤ 760px）', line);
    await shot(page, 'intensive-reader');
    await page.tap('#moreBtn'); await sleep(400);
    const menu = await R(page, '#moreMenu');
    ok(inView(menu, 60), '阅读页 ⋯ 面板整个在屏幕里', menu);
    await page.goBack(); await sleep(400);
  });
  await section('精读题目', async () => {
    await open(IR.glassBridge);
    await page.tap('#examSheetBtn'); await sleep(500);
    const st = await page.evaluate(() => { const pane = document.getElementById('examPane').getBoundingClientRect(); const p = document.querySelector('#vContent .reader p[data-s]').getBoundingClientRect(); const nav = [...document.querySelectorAll('#examPane .ir-qs-nav button')].map(b => { const r = b.getBoundingClientRect(); return { h: Math.round(r.height), b: Math.round(r.bottom) }; }); return { paneL: Math.round(pane.left), paneT: Math.round(pane.top), textR: Math.round(p.right), vw: innerWidth, vh: innerHeight, nav }; });
    ok(st.paneL > st.vw * 0.4 && st.textR <= st.paneL + 1, '精读题目：题目在右边一栏，和原文左右并排', st);
    ok(st.nav.length === 4 && st.nav.every(n => n.h >= 44 && n.b <= st.vh), '精读题目：上一题 / 定位 / 解析 / 下一题 在屏幕里、44px', st.nav);
    await page.tap('.ir-qs-nav [data-act="qs-locate"]'); await sleep(900);
    const loc = await page.evaluate(() => { const ev = document.querySelector('#vContent p.ir-ev'); const r = ev && ev.getBoundingClientRect(); return r ? { t: Math.round(r.top), b: Math.round(r.bottom), vh: innerHeight } : null; });
    ok(!!loc && loc.t >= 0 && loc.b <= loc.vh, '精读题目：定位以后证据句就在屏幕里', loc);
    await shot(page, 'intensive-questions');
  });
  await section('精读转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/intensive'); await page.waitForSelector('.ir-card'); await sleep(400);
    await open(IR.glassBridge);
    await page.tap('#examSheetBtn'); await sleep(500);
    if (await rotate(page, dev, () => page.evaluate(() => document.getElementById('viewer').classList.contains('active') && document.getElementById('examPane').classList.contains('is-open')), '精读阅读页 + 题目面板')) {
      await page.goBack(); await sleep(500);
      const a = await page.evaluate(() => ({ pane: document.getElementById('examPane').classList.contains('is-open'), reader: document.getElementById('viewer').classList.contains('active') }));
      await page.goBack(); await sleep(500);
      const b = await page.evaluate(() => ({ reader: document.getElementById('viewer').classList.contains('active'), path: location.pathname }));
      ok(!a.pane && a.reader && !b.reader && b.path === '/intensive', '精读：转屏后返回先关题目，再回列表', { a, b });
    }
    await page.setViewportSize(dev.viewport);
  });
  await section('添加文章', async () => {
    await page.goto(M.base + '/intensive/new'); await sleep(800);
    await checkPhoneNav(page, '添加文章');
    await checkOverflow(page, '添加文章');
    await checkNavScrolls(page, '添加文章');
    const b = await R(page, '#importBtn');
    ok(inView(b, 44), '添加文章：「导入」钉在底部、在屏幕里', b);
  });
  ok(!page.errors.length, '精读：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 词汇汇总 ====================
async function vocabSummary(browser, dev) {
  const M = CFG.vocab_summary;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('词汇汇总', async () => {
    await page.goto(M.base + '/vocab_summary'); await page.waitForSelector('.vs-art'); await sleep(600);
    await checkPhoneNav(page, '词汇汇总');
    await checkOverflow(page, '词汇汇总');
    const bar = await R(page, '#vsBarStart');
    ok(inView(bar, 44), '词汇汇总：「开始挑战」钉在底部、在屏幕里', bar);
    await page.tap('.vs-art'); await sleep(500);
    const words = await page.$$eval('.vs-words > *', ws => new Set(ws.slice(0, 6).map(w => Math.round(w.getBoundingClientRect().top))).size);
    ok(words <= 2, '词汇汇总：词卡一行三张', words);
    await checkNavScrolls(page, '词汇汇总第二屏');
    await page.tap('#vsBarStart'); await sleep(600);
    const go = await page.evaluate(() => { const b = [...document.querySelectorAll('.vs-dlg--setup .vs-dlg__foot .ui-btn')].filter(x => x.offsetWidth).pop(); const r = b.getBoundingClientRect(); return { t: Math.round(r.top), b: Math.round(r.bottom), h: Math.round(r.height), vh: innerHeight }; });
    ok(go.t >= 0 && go.b <= go.vh && go.h >= 44, '词汇挑战设置：开始按钮在屏幕里', go);
    await shot(page, 'vocab-summary-setup');
  });
  await section('词汇汇总转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/vocab_summary'); await page.waitForSelector('.vs-art'); await sleep(500);
    await page.tap('.vs-art'); await sleep(400);
    await page.tap('#vsBarStart'); await sleep(600);
    if (await rotate(page, dev, () => page.evaluate(() => { const d = document.querySelector('.vs-dlg--setup'); return !!d && d.offsetWidth > 0 && document.body.classList.contains('vs-detail'); }), '词汇挑战设置（第二屏上打开）')) {
      await page.goBack(); await sleep(500);
      const st = await page.evaluate(() => ({ dlg: !!document.querySelector('.vs-dlg--setup') && document.querySelector('.vs-dlg--setup').offsetWidth > 0, detail: document.body.classList.contains('vs-detail') }));
      ok(!st.dlg && st.detail, '词汇汇总：转屏后返回只关设置，还在这篇的词', st);
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '词汇汇总：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 写作 ====================
async function writing(browser, dev) {
  const M = CFG.writing;
  const { ctx, page } = await newPage(browser, dev, M);
  // 写作页会记住上次停在哪一页（刷新回到原处），所以先回首页再一步步点进实战
  const toPractice = async () => {
    await page.goto(M.base + '/writing_practice'); await page.waitForFunction(() => typeof state !== 'undefined' && !!state.view); await sleep(700);
    if (await page.evaluate(() => state.view !== 'entryView')) { await page.evaluate(() => backToEntry()); await sleep(500); }
    await page.waitForSelector('.entry-card');
    await page.locator('.entry-card', { hasText: '写作思维链' }).first().tap(); await page.waitForSelector('#subList .sub-card'); await sleep(400);
    await page.locator('#subList .mode-btn.learn').first().tap(); await page.waitForSelector('#exampleList .ex-sent'); await sleep(400);
    await page.evaluate(() => gotoPractice()); await page.waitForFunction(() => state.view === 'practiceView'); await sleep(700);
  };
  await section('写作首页', async () => {
    await page.goto(M.base + '/writing_practice'); await page.waitForSelector('.entry-card'); await sleep(700);
    await checkPhoneNav(page, '写作');
    await checkOverflow(page, '写作');
    await checkNavScrolls(page, '写作');
  });
  await section('写作实战', async () => {
    await toPractice();
    await checkOverflow(page, '写作实战');
    const sub = await R(page, '#wpActBar .is-primary'), ta = await R(page, '#transInput');
    ok(inView(sub, 44), '写作实战：「提交批改」在底部操作条上、在屏幕里', sub);
    ok(!!ta && ta.shown && ta.t < (sub ? sub.t : ta.vh) - 20, '写作实战：一进来输入框就露在操作条上面', { ta, sub });
    const seg = await R(page, '#practiceView .view-head .seg-switch'), title = await R(page, '#practiceView .view-head-main');
    ok(!!seg && !!title && Math.abs(seg.t - title.t) <= 24, '写作实战：学习 / 实战切换和标题在同一行', { seg, title });
    await shot(page, 'writing-practice');
    await page.tap('#practiceView .wp-prow-main'); await sleep(500);
    const sh = await R(page, '.wp-sheet-panel');
    ok(inView(sh, 60), '写作：句子列表面板整个在屏幕里', sh);
    await page.goBack(); await sleep(600);
  });
  await section('写作转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await toPractice();
    await page.fill('#transInput', 'Families can notice small health problems early.');
    await page.tap('#practiceView .wp-prow-main'); await sleep(500);
    if (await rotate(page, dev, () => page.evaluate(() => { const s = document.querySelector('.wp-sheet'), p = document.querySelector('.wp-sheet-panel'); return !!s && !s.hidden && !!p && p.getBoundingClientRect().height > 60 && state.view === 'practiceView'; }), '写作句子列表面板')) {
      await page.goBack(); await sleep(600);
      const st = await page.evaluate(() => ({ sheet: !!document.querySelector('.wp-sheet') && !document.querySelector('.wp-sheet').hidden, view: state.view, text: document.getElementById('transInput').value }));
      ok(!st.sheet && st.view === 'practiceView' && /health problems/.test(st.text), '写作：转屏后返回只关面板，写了一半的译文还在', st);
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '写作：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 听力、笔记本 ====================
async function listening(browser, dev) {
  const M = CFG.listening;
  const { ctx, page } = await newPage(browser, dev, M);
  const openHall = async () => {
    await page.goto(M.base + '/listening_review?project=' + HALL); await page.waitForSelector('.lr-line', { timeout: 10000 }); await sleep(700);
  };
  await section('听力列表', async () => {
    await page.goto(M.base + '/listening_review'); await page.waitForSelector('.lr-proj'); await sleep(500);
    await checkPhoneNav(page, '听力列表');
    await checkOverflow(page, '听力列表');
    await checkNavScrolls(page, '听力列表');
    const more = await R(page, '.lr-proj [data-act="more"]'), trash = await R(page, '.lr-proj [data-act="delete"]');
    ok(!!more && more.shown && more.h >= 44 && !(trash && trash.shown), '听力列表：卡片上是 44px 的 ⋯（没有 30px 的垃圾桶）', { more, trash });
    await page.tap('.lr-head__upload'); await sleep(400);
    await page.evaluate(async () => { switchTab('json'); const text = await (await fetch('/static/e2e/e2e_single.json')).text(); const dt = new DataTransfer(); dt.setData('text/plain', text); document.getElementById('jsonPaste').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true })); });
    await page.waitForFunction(() => !document.getElementById('jsonPreview').hidden, null, { timeout: 5000 }).catch(() => {});
    await sleep(300);
    const imp = await R(page, '#uploadJsonBtn'), head = await R(page, '#uploadTitle');
    ok(inView(imp, 40) && inView(head, 10), '听力上传：标题和「导入」都在屏幕里，只滚中间', { imp, head });
    await shot(page, 'listening-upload');
    await page.goBack(); await sleep(400);
  });
  await section('听力精听', async () => {
    await openHall();
    await checkOverflow(page, '精听');
    const pl = await R(page, '#lrPlayer'), play = await R(page, '#playBtn');
    ok(inView(pl, 44) && pl.h <= 80 && pl.b === pl.vh, '精听：播放条一行、贴底（≤ 80px）', pl);
    const ctrls = await page.evaluate(() => ['speedChip', 'prevSegBtn', 'playBtn', 'nextSegBtn', 'loopBtn'].map(id => { const r = document.getElementById(id).getBoundingClientRect(); return { id, h: Math.round(r.height), w: Math.round(r.width), t: Math.round(r.top) }; }));
    ok(ctrls.every(c => c.h >= 44 && c.w >= 44) && new Set(ctrls.map(c => Math.round(c.t / 12))).size <= 2, '精听：倍速 / 上一句 / 播放 / 下一句 / 单句循环 ≥ 44px、排成一行', ctrls);
    await page.evaluate(() => window.scrollTo(0, 500)); await sleep(300);
    const v = await page.evaluate(() => { const t = document.getElementById('ptabs').getBoundingClientRect(), p = document.getElementById('lrPlayer').getBoundingClientRect(); return { tabsTop: Math.round(t.top), tabsBottom: Math.round(t.bottom), playerTop: Math.round(p.top), vh: innerHeight, ratio: +((p.top - t.bottom) / innerHeight).toFixed(2) }; });
    ok(v.tabsBottom > 40 && Math.abs(v.tabsTop) <= 1 && v.ratio >= 0.6, '精听：翻下去以后页签条贴着屏幕顶，原文占屏幕 ≥ 60%', v);
    await shot(page, 'listening-detail');
    await page.evaluate(() => openMoreSheet()); await sleep(400);
    const sh = await R(page, '#moreSheet .ui-dialog');
    ok(inView(sh, 60), '精听 ⋯ 面板整个在屏幕里', sh);
    await page.goBack(); await sleep(400);
  });
  await section('听力转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await openHall();
    // 正在放的时候转屏：接着放，还停在这篇
    await page.evaluate(() => { const l = document.querySelectorAll('.lr-line')[2]; l.click(); }); await sleep(800);
    if (await rotate(page, dev, () => page.evaluate(() => state.view === 'detail' && !document.getElementById('audioEl').paused && document.getElementById('lrPlayer').getBoundingClientRect().height > 40), '精听播放中')) {
      ok(await page.evaluate(() => document.getElementById('audioEl').currentTime > 0.5), '听力：转屏以后音频接着往下放');
    }
    await page.evaluate(() => { const a = document.getElementById('audioEl'); a.pause(); });
    await page.evaluate(() => openMoreSheet()); await sleep(400);
    if (await rotate(page, dev, () => page.evaluate(() => { const d = document.querySelector('#moreSheet .ui-dialog'); return !document.getElementById('moreSheet').hidden && !!d && d.getBoundingClientRect().height > 60 && state.view === 'detail'; }), '精听 ⋯ 面板')) {
      await page.goBack(); await sleep(500);
      const st = await page.evaluate(() => ({ sheet: document.getElementById('moreSheet').hidden, view: state.view }));
      ok(st.sheet && st.view === 'detail', '听力：转屏后返回只关面板，还在这篇', st);
    }
    await page.setViewportSize(dev.viewport);
  });
  await section('听力笔记本', async () => {
    await page.goto(M.base + '/listening_review/notes'); await sleep(1200);
    await checkPhoneNav(page, '听力笔记本');
    await checkOverflow(page, '听力笔记本');
    await checkNavScrolls(page, '听力笔记本');
    const f = await R(page, '.lr-nb__filters');
    ok(!!f && f.shown && f.h <= 70, '听力笔记本：文章 / 类型 / 搜索一行', f);
  });
  ok(!page.errors.length, '听力：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 单词本 ====================
async function vocabulary(browser, dev) {
  const M = CFG.vocabulary;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('单词本', async () => {
    await page.goto(M.base + '/vocabulary'); await page.waitForSelector('#vbGrid .vb-word'); await sleep(600);
    await checkPhoneNav(page, '单词本');
    await checkOverflow(page, '单词本');
    await checkNavScrolls(page, '单词本');
    const bar = await page.$$eval('.vb-pbar .ui-btn', bs => bs.map(b => { const r = b.getBoundingClientRect(); return { h: Math.round(r.height), b: Math.round(r.bottom), vh: innerHeight }; }));
    ok(bar.length === 3 && bar.every(b => b.h >= 44 && b.b <= b.vh), '单词本：底部「遮释义 / 加词 / 单词挑战」在屏幕里、44px', bar);
    const row = await page.evaluate(() => { const a = document.getElementById('vbCats').getBoundingClientRect(), b = document.querySelector('.vb-prow').getBoundingClientRect(); return { cats: Math.round(a.top), prow: Math.round(b.top), h: Math.round(document.querySelector('.vb-rail-col').getBoundingClientRect().height) }; });
    ok(Math.abs(row.cats - row.prow) <= 4 && row.h <= 64, '单词本：分类和子分类 / 查找 / 排序并成一行吸顶', row);
    await page.tap('#vbPAdd'); await sleep(400);
    const add = await R(page, '#vbAddBtn');
    ok(inView(add, 44), '单词本加词：「添加」在屏幕里', add);
    await page.goBack(); await sleep(400);
    // 弹窗是贴底的面板：底边就是屏幕底边（单词本竖屏平板那条 16px 留白不能带到横屏上）
    const sheetBottom = sel => page.$eval(sel, e => ({ b: Math.round(e.closest('.ui-dialog').getBoundingClientRect().bottom), vh: innerHeight }));
    await page.locator('#vbGrid .vb-card').nth(1).locator('.vb-act--more').tap(); await sleep(400);
    await page.locator('#actList .vb-actitem', { hasText: /^编辑$/ }).tap(); await sleep(500);
    const save = await R(page, '#edOk'), edWord = await R(page, '#edWord');
    const edSheet = await sheetBottom('#edOk');
    ok(inView(save, 44) && inView(edWord, 44) && Math.abs(edSheet.b - edSheet.vh) <= 1, '单词本编辑：输入框和「保存」在屏幕里，面板贴着屏幕底边', { save, edWord, edSheet });
    await page.goBack(); await sleep(400);
    await page.tap('#vbPChallenge'); await sleep(400);
    const go = await R(page, '#chOk');
    const chSheet = await sheetBottom('#chOk');
    ok(inView(go, 44) && Math.abs(chSheet.b - chSheet.vh) <= 1, '单词挑战设置：「开始挑战」在屏幕里，面板贴着屏幕底边', { go, chSheet });
    await page.tap('#chOk'); await sleep(900);
    const opts = await page.$$eval('#qOptions .vb-option', os => os.map(o => { const r = o.getBoundingClientRect(); return { t: Math.round(r.top), b: Math.round(r.bottom), h: Math.round(r.height), vh: innerHeight }; }));
    ok(opts.length >= 2 && opts.every(o => o.t >= 0 && o.b <= o.vh && o.h >= 44), '单词挑战：所有选项一屏看全、≥ 44px', opts);
    await shot(page, 'vocabulary-quiz');
  });
  await section('单词本转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/vocabulary'); await page.waitForSelector('#vbGrid .vb-word'); await sleep(500);
    await page.tap('#vbPChallenge'); await sleep(400);
    await page.tap('#chOk'); await sleep(900);
    const q0 = await page.evaluate(() => document.getElementById('qQuestion').textContent);
    if (await rotate(page, dev, () => page.evaluate(() => !document.getElementById('dlgQuiz').hidden && document.getElementById('qOptions').getBoundingClientRect().height > 60), '单词挑战答题')) {
      const q1 = await page.evaluate(() => document.getElementById('qQuestion').textContent);
      ok(q0 && q0 === q1, '单词挑战：转屏后还是同一道题', { q0, q1 });
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '单词本：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 技巧 ====================
async function studyTips(browser, dev) {
  const M = CFG.study_tips;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('技巧', async () => {
    await page.goto(M.base + '/study_techniques'); await page.waitForSelector('#listBody [data-action="more"]'); await sleep(600);
    await checkPhoneNav(page, '技巧');
    await checkOverflow(page, '技巧');
    await checkNavScrolls(page, '技巧');
    const tools = await page.$$eval('#listTools .ui-btn', bs => bs.filter(b => b.offsetWidth).map(b => { const r = b.getBoundingClientRect(); return { h: Math.round(r.height), b: Math.round(r.bottom), vh: innerHeight }; }));
    ok(tools.length >= 2 && tools.every(b => b.h >= 44 && b.b <= b.vh), '技巧：底部操作条在屏幕里、44px', tools);
    await page.tap('#listBody [data-action="more"]'); await sleep(400);
    const dlg = await R(page, '#actDlg .ui-dialog'), cancel = await R(page, '#actDlg .ui-dialog__foot .ui-btn');
    ok(inView(dlg, 60) && inView(cancel, 40), '技巧 ⋯ 面板：整个在屏幕里，「取消」看得见', { dlg, cancel });
    await page.goBack(); await sleep(400);
  });
  await section('技巧转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/study_techniques'); await page.waitForSelector('#listBody [data-action="more"]'); await sleep(500);
    await page.tap('#listBody [data-action="more"]'); await sleep(400);
    if (await rotate(page, dev, () => page.evaluate(() => !document.getElementById('actDlg').hidden && document.querySelector('#actDlg .ui-dialog').getBoundingClientRect().height > 60), '技巧 ⋯ 面板')) {
      await page.goBack(); await sleep(500);
      const st = await page.evaluate(() => ({ dlg: document.getElementById('actDlg').hidden, path: location.pathname }));
      ok(st.dlg && st.path === '/study_techniques', '技巧：转屏后返回只关面板', st);
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '技巧：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 交流 ====================
async function board(browser, dev) {
  const M = CFG.board;
  const { ctx, page } = await newPage(browser, dev, M);
  await section('交流', async () => {
    await page.goto(M.base + '/message_board'); await page.waitForSelector('.mb-composer__fake', { timeout: 10000 }); await sleep(800);
    await checkPhoneNav(page, '交流');
    await checkOverflow(page, '交流');
    await checkNavScrolls(page, '交流');
    await page.tap('.mb-composer__fake'); await sleep(600);
    const pub = await R(page, '#composer .mb-composer__send .ui-btn--primary');
    const tools = await page.$$eval('#composer .mb-tools .ui-btn', bs => bs.filter(b => b.offsetWidth).map(b => { const r = b.getBoundingClientRect(); return { h: Math.round(r.height), b: Math.round(r.bottom), vh: innerHeight }; }));
    ok(inView(pub, 40) && tools.length >= 4 && tools.every(t => t.h >= 40 && t.b <= t.vh), '交流发帖：「发布」和四个附件按钮都在屏幕里', { pub, tools });
    await shot(page, 'board-composer');
  });
  await section('交流转屏', async () => {
    await page.setViewportSize(dev.portrait);
    await page.goto(M.base + '/message_board'); await page.waitForSelector('.mb-composer__fake'); await sleep(700);
    await page.tap('.mb-composer__fake'); await sleep(600);
    await page.fill('#composer textarea', '横屏也能接着写');
    if (await rotate(page, dev, () => page.evaluate(() => { const c = document.getElementById('composer'); return !!c && c.classList.contains('is-open') && getComputedStyle(c).position === 'fixed' && c.getBoundingClientRect().height >= innerHeight - 2; }), '交流发帖面板')) {
      const t = await page.evaluate(() => document.querySelector('#composer textarea').value);
      ok(t === '横屏也能接着写', '交流：转屏后写了一半的帖子还在', t);
    }
    await page.setViewportSize(dev.viewport);
  });
  ok(!page.errors.length, '交流：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 隐藏页面：只要不坏 ====================
async function hidden(browser, dev) {
  for (const [m, url] of [['speaking', '/combined'], ['home', '/reading'], ['home', '/audio_transcription']]) {
    const M = CFG[m];
    const { ctx, page } = await newPage(browser, dev, M);
    await section(url, async () => {
      await page.goto(M.base + url); await sleep(1200);
      await checkOverflow(page, url);
      ok(!page.errors.length, `${url}：没有脚本报错`, page.errors);
    });
    await ctx.close();
  }
}

// ==================== 反例：电脑窗口、iPad 不用手机布局 ====================
async function negatives(browser, engine) {
  const M = CFG.vocabulary;
  const cases = [
    { name: '带鼠标的电脑窗口拉矮到 1280×500', co: { viewport: { width: 1280, height: 500 } } },
    { name: 'iPad 横屏 1180×820（触屏）', co: { viewport: { width: 1180, height: 820 }, hasTouch: true } },
  ];
  for (const c of cases) {
    await section(c.name, async () => {
      const ctx = await browser.newContext(c.co);
      await ctx.addInitScript(t => { if (location.protocol === 'about:') return; localStorage.setItem('authToken', t); }, M.token);
      const page = await ctx.newPage();
      await page.goto(M.base + '/vocabulary'); await page.waitForSelector('.app-shell-nav'); await sleep(500);
      const s = await page.evaluate(() => ({ links: getComputedStyle(document.querySelector('.app-shell-links')).display !== 'none', pbar: getComputedStyle(document.querySelector('.vb-pbar')).display, navPos: getComputedStyle(document.querySelector('.app-shell-nav')).position, js: window.IELTSPhone ? IELTSPhone.matches() : null }));
      ok(s.links && s.pbar === 'none' && s.navPos === 'fixed' && s.js !== true, `${c.name}：还是桌面布局`, s);
      await ctx.close();
    });
  }
}

(async () => {
  const t0 = Date.now();
  for (const engine of ENGINES) {
    const browser = await pw[engine].launch();
    for (const dev of DEVICES[engine]) {
      TAG = dev.name;
      // 先确认这个模拟环境真的是「矮的触摸屏」，不然后面的截图和检查都不算数
      const probe = await newPage(browser, dev, null);
      const mq = await probe.page.evaluate(() => ({ short: matchMedia('(max-height: 540px)').matches, coarse: matchMedia('(pointer: coarse)').matches, w: innerWidth, h: innerHeight }));
      await probe.ctx.close();
      if (!ok(mq.short && mq.coarse, '模拟环境是矮的触摸屏（max-height: 540px 且 pointer: coarse）', mq)) continue;
      for (const fn of [home, speaking, intensive, vocabSummary, writing, listening, vocabulary, studyTips, board, hidden]) {
        const t = Date.now();
        await fn(browser, dev);
        console.log(`-- ${TAG} ${fn.name} ${((Date.now() - t) / 1000).toFixed(1)}s`);
      }
    }
    TAG = engine;
    await negatives(browser, engine);
    await browser.close();
  }
  console.log(`\n横屏检查：通过 ${pass} 项，失败 ${fail} 项（${((Date.now() - t0) / 1000).toFixed(0)}s）`);
  if (fail) { console.log('失败的项：\n  ' + fails.join('\n  ')); process.exit(1); }
})().catch(e => { console.error(e); process.exit(1); });

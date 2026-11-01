// 手机版式（≤820px）：WebKit 390×844（iPhone 尺寸、触摸）和 Chromium 360×780（安卓手机模式）各跑一遍，亮色 + 暗色。
// 每一段单独计分，前面一段出错不影响后面（在改版前的代码上跑，能看出每一项都是新加的）。
// 长按选词合成不了：先真实点一下那个词，再用 Range 设出长按会得到的选区（和 suite_touch 一样）。
// 键盘弹起用「把视口改成 470 高」模拟；真键盘、系统的拷贝菜单只有真 iPhone 上才看得到。
const fs = require('fs');
const path = require('path');

const FIXTURE = path.join(__dirname, '..', '..', 'fixtures', 'jiufen_reading_attempt.json');
const KB_H = 470;   // 键盘弹起后剩下的可视高度

module.exports = async function suitePhone({ cfg, browser, engine, t, lib }) {
  const { IDS } = lib;
  const BASE = cfg.baseUrl;
  const device = engine === 'webkit'
    ? { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 }   // WebKit 不认 isMobile
    : { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 };
  const W = device.viewport.width, H = device.viewport.height;
  const shotDir = path.join(cfg.out, 'phone');
  fs.mkdirSync(shotDir, { recursive: true });

  const ctx = await lib.newContext(cfg, browser, Object.assign({ acceptDownloads: true }, device));
  const p = await lib.newPage(ctx, 10000);
  const errs = []; const dialogs = []; let acceptNext = false;
  // 预期内的：发音文件不存在（404）、沙盒没有翻译 key（502）
  const expected = s => /status of (404|502)/.test(s) || /pronunciation|Audio playback|Load failed|NotSupportedError|音频文件不存在/.test(s);
  p.on('pageerror', e => errs.push(String(e)));
  p.on('console', m => { if (m.type() === 'error' && !expected(m.text())) errs.push('console ' + m.text()); });
  p.on('dialog', d => { dialogs.push(d.message()); if (acceptNext) { acceptNext = false; d.accept(); } else d.dismiss(); });
  // 付费接口：一个都不许碰（沙盒里也调不通，这里再看一眼页面有没有发出去）
  const paid = [];
  p.on('request', r => { if (/\/(generate_article_audio|prepare_article_audio|generate_audio_segment|cleanup_article_audio|combine_audio_segments)/.test(r.url())) paid.push(r.url()); });

  const ok = (c, what) => t.ok(c, `${what}`);
  const sleep = ms => p.waitForTimeout(ms);
  const shot = name => p.screenshot({ path: path.join(shotDir, `${engine}-${name}.png`) }).catch(() => {});
  const rect = sel => p.evaluate(sel => { const e = document.querySelector(sel); if (!e) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return { x: r.left, y: r.top, w: r.width, h: r.height, b: r.bottom, r: r.right, vis: cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0, fs: parseFloat(cs.fontSize) }; }, sel);
  const noOverflow = () => p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
  const histLen = () => p.evaluate(() => history.length);
  const back = async () => { await p.evaluate(() => history.back()); await sleep(450); };
  async function section(name, fn) {
    try { await fn(); } catch (e) {
      ok(false, `${name}：中途出错 ${e.message.split('\n').slice(0, 3).join(' | ')}`);
      await shot(`crash-${name}`);
    }
  }
  const open = async id => { await p.evaluate(id => openArticle(id), id); await p.waitForFunction(id => typeof currentArticle !== 'undefined' && currentArticle && currentArticle.id === id && document.querySelector('#vContent .reader p'), id); await sleep(350); };
  const toList = async () => { await lib.settle(p); await p.goto(BASE + '/intensive'); await p.waitForFunction(() => typeof allItems !== 'undefined' && allItems.length > 0, null, { timeout: 15000 }); await sleep(400); };
  // 第 n 行英文开头的词：滚到屏幕上半部分，先真点一下，再设选区（长按的效果）
  async function longPressLine(n) {
    const w = await p.evaluate(n => { const pp = document.querySelectorAll('#vContent .reader p.en')[n]; window.scrollBy(0, pp.getBoundingClientRect().top - 160); const t = pp.firstChild; const m = /^[A-Za-z]+/.exec(t.nodeValue); const r = document.createRange(); r.setStart(t, 0); r.setEnd(t, m[0].length); const rc = r.getBoundingClientRect(); return { n, word: m[0], len: m[0].length, x: rc.left + rc.width / 2, y: rc.top + rc.height / 2, bottom: rc.bottom }; }, n);
    await p.touchscreen.tap(w.x, w.y); await sleep(80);
    await p.evaluate(([n, len]) => { const t = document.querySelectorAll('#vContent .reader p.en')[n].firstChild; const r = document.createRange(); r.setStart(t, 0); r.setEnd(t, len); getSelection().removeAllRanges(); getSelection().addRange(r); }, [w.n, w.len]);
    await sleep(600);
    return w;
  }

  try {
    // ==================== 文章列表 ====================
    await section('list', async () => {
      await toList();
      ok(await noOverflow(), 'list: no horizontal overflow');
      const cards = await p.$$eval('.ir-card', els => els.slice(0, 4).map(e => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), fs: parseFloat(getComputedStyle(e.querySelector('h3')).fontSize) }; }));
      ok(cards[0].y === cards[1].y && cards[1].x > cards[0].x && cards[2].y > cards[0].y, `list: two cards per row ${JSON.stringify(cards)}`);
      ok(cards[0].fs >= 15, `list: card titles ≥ 15px (${cards[0].fs})`);
      ok(cards[0].y < 240, `list: first card starts high on the screen (y=${cards[0].y}, was 266+ before)`);
      const del = await rect('.ir-card .ir-card-del');
      const more = await rect('.ir-card .ir-card-more');
      ok(!del.vis && more.vis && more.w >= 44 && more.h >= 44, `list: no trash on cards, ⋯ is 44×44 ${JSON.stringify({ del: del.vis, more })}`);
      const tab = await rect('#tab-Reading');
      ok(tab.h >= 40, `list: category segment buttons ≥ 40px (${tab.h})`);
      await shot('01-list');
      // 分类吸顶：往下翻还在导航栏下面
      await p.evaluate(() => window.scrollTo(0, 700)); await sleep(200);
      const tab2 = await rect('#tab-Reading');
      ok(tab2.y > 40 && tab2.y < 120, `list: category segment sticks under the nav (y=${tab2.y})`);
      // 添加文章：右下角悬浮按钮，翻到底也不挡最后一张卡
      const fab = await rect('.ir-head-actions .ir-btn-primary');
      ok(fab.vis && fab.h >= 44 && fab.b <= H && fab.r <= W, `list: 添加文章 floats bottom-right ${JSON.stringify(fab)}`);
      await p.evaluate(() => window.scrollTo(0, 99999)); await sleep(200);
      const last = await p.evaluate(() => { const cs = document.querySelectorAll('.ir-card'); return Math.round(cs[cs.length - 1].getBoundingClientRect().bottom); });
      const fab2 = await rect('.ir-head-actions .ir-btn-primary');
      ok(last <= fab2.y, `list: last card ends above the floating button (${last} ≤ ${fab2.y})`);
      await shot('02-list-bottom');
    });

    await section('card-sheet', async () => {
      // ⋯ → 面板（遮罩、改分类、删除）；系统返回关掉面板，还在列表上
      await toList();
      const h0 = await histLen();
      await p.tap('.ir-card .ir-card-more'); await sleep(350);
      const sh = await p.evaluate(() => ({ open: !document.getElementById('cardSheet').hidden, scrim: !document.getElementById('irScrim').hidden, title: document.getElementById('cardSheetTitle').textContent }));
      ok(sh.open && sh.scrim && sh.title === 'The Glass Bridge', `card ⋯ opens its sheet ${JSON.stringify(sh)}`);
      ok((await histLen()) === h0 + 1, 'card sheet pushed one history entry');
      const del = await rect('#cardSheet .ir-sheet-row.is-danger');
      ok(del.h >= 44 && del.b <= H, `card sheet: 删除文章 row ≥ 44px and on screen ${JSON.stringify(del)}`);
      await shot('03-card-sheet');
      await back();
      const after = await p.evaluate(() => ({ open: !document.getElementById('cardSheet').hidden, path: location.pathname, reading: document.body.classList.contains('ir-reading') }));
      ok(!after.open && after.path === '/intensive' && !after.reading, `back closes the card sheet and stays on the list ${JSON.stringify(after)}`);
      // 改分类：Writing 里的图表文章挪到 Listening（跑完 cleanup 会改回来）
      await p.tap('#tab-Writing'); await sleep(200);
      const c0 = await p.evaluate(() => [document.getElementById('count-Writing').textContent, document.getElementById('count-Listening').textContent]);
      await p.tap('.ir-card .ir-card-more'); await sleep(300);
      await p.tap('#cardCatSeg [data-cat="Listening"]');
      await p.waitForFunction(() => document.getElementById('cardSheet').hidden, null, { timeout: 5000 });
      await sleep(300);
      const c1 = await p.evaluate(() => [document.getElementById('count-Writing').textContent, document.getElementById('count-Listening').textContent]);
      ok(+c1[0] === +c0[0] - 1 && +c1[1] === +c0[1] + 1, `card sheet moves the article to another category ${JSON.stringify([c0, c1])}`);
      await p.tap('#tab-Reading'); await sleep(200);
    });

    // ==================== 阅读页 ====================
    await section('reader', async () => {
      await toList();
      await p.evaluate(() => window.scrollTo(0, 500)); await sleep(150);
      const listY = await p.evaluate(() => window.scrollY);
      const card = await p.evaluate(() => { const c = [...document.querySelectorAll('.ir-card')].find(c => c.querySelector('h3').textContent === "The Lighthouse Keeper's Log"); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { x: r.left + 30, y: r.top + 20 }; });
      const listY2 = await p.evaluate(() => window.scrollY);
      await p.touchscreen.tap(card.x, card.y);
      await p.waitForFunction(() => currentArticle && document.querySelector('#vContent .reader p')); await sleep(400);
      const st = await p.evaluate(() => { const nav = document.querySelector('.app-shell-nav'); const bar = document.querySelector('#viewer .ir-bar').getBoundingClientRect(); return { nav: nav ? getComputedStyle(nav).display : 'none', barTop: Math.round(bar.top), scrollY: window.scrollY, hash: location.hash, en: parseFloat(getComputedStyle(document.querySelector('#vContent .reader p.en')).fontSize) }; });
      ok(st.nav === 'none' && st.barTop === 0, `reader replaces the global nav with its own top bar ${JSON.stringify(st)}`);
      ok(st.en >= 16, `reader: English text ≥ 16px (${st.en})`);
      ok(/^#article-/.test(st.hash) && (await p.evaluate(() => !!(history.state && history.state.irReader))), 'reader: opening pushed #article- onto history');
      for (const sel of ['#viewer .ir-bar > .ir-icon-btn', '#moreBtn']) { const r = await rect(sel); ok(r.w >= 44 && r.h >= 44, `reader: ${sel} is 44×44 (${r.w}×${r.h})`); }
      const tools = await p.evaluate(() => [...document.querySelectorAll('#viewer .ir-tools > .ir-icon-btn')].filter(b => getComputedStyle(b).display !== 'none').map(b => { const r = b.getBoundingClientRect(); return { t: b.textContent.replace(/\s+/g, ''), h: Math.round(r.height), b: Math.round(r.bottom) }; }));
      ok(tools.length >= 3 && tools.every(b => b.h >= 44 && b.b === H) && /译文/.test(tools[0].t) && tools.some(b => /朗读/.test(b.t)) && tools.some(b => /词汇/.test(b.t)), `reader: labelled bottom toolbar ${JSON.stringify(tools)}`);
      // 正文就是整页滚动
      await p.evaluate(() => window.scrollTo(0, 400)); await sleep(150);
      ok((await p.evaluate(() => window.scrollY)) > 300, 'reader: the article scrolls the page itself (Safari bars can collapse)');
      ok(await noOverflow(), 'reader: no horizontal overflow');
      await p.evaluate(() => window.scrollTo(0, 0)); await sleep(100);
      await shot('10-reader');
      // 系统返回：关掉阅读页，回到列表原来的位置
      await back();
      const b1 = await p.evaluate(() => ({ open: document.getElementById('viewer').classList.contains('active'), hash: location.hash, y: window.scrollY, nav: getComputedStyle(document.querySelector('.app-shell-nav')).display }));
      ok(!b1.open && b1.hash === '' && Math.abs(b1.y - listY2) < 3 && b1.nav !== 'none', `back closes the reader and returns to the same list position ${JSON.stringify({ ...b1, listY, listY2 })}`);
      // ‹ 返回：关掉阅读页，不再多压一条历史
      await open(IDS.lighthouse);
      const h1 = await histLen();
      await p.tap('#viewer .ir-bar > .ir-icon-btn'); await sleep(450);
      const b2 = await p.evaluate(() => ({ open: document.getElementById('viewer').classList.contains('active'), hash: location.hash }));
      ok(!b2.open && b2.hash === '' && (await histLen()) === h1, `‹ closes the reader without adding history ${JSON.stringify(b2)}`);
      // 从链接直接打开（词汇汇总「打开原文」、导入后）：‹ 回列表，网址里的 #article- 去掉
      await lib.settle(p); await p.goto(BASE + '/intensive#article-' + encodeURIComponent(IDS.lighthouse));
      await p.waitForFunction(() => currentArticle && document.querySelector('#vContent .reader p')); await sleep(300);
      await p.tap('#viewer .ir-bar > .ir-icon-btn'); await sleep(400);
      const b3 = await p.evaluate(() => ({ open: document.getElementById('viewer').classList.contains('active'), hash: location.hash, cards: document.querySelectorAll('.ir-card').length }));
      ok(!b3.open && b3.hash === '' && b3.cards > 0, `deep link: ‹ goes to the list and clears the hash ${JSON.stringify(b3)}`);
    });

    // ==================== 划词 → 写释义 ====================
    await section('select', async () => {
      await toList(); await open(IDS.lighthouse);
      const w = await longPressLine(1);
      const fb = await rect('#floatBox');
      const tools = await rect('#viewer .ir-tools');
      const btns = await p.evaluate(() => [...document.querySelectorAll('#floatBox button')].filter(b => getComputedStyle(b).display !== 'none').map(b => ({ t: b.textContent, h: Math.round(b.getBoundingClientRect().height) })));
      const word = await p.evaluate(() => document.getElementById('popWord').textContent);
      ok(fb.vis && Math.round(fb.b) === Math.round(tools.y) && fb.y > w.bottom, `selection bar docks on the toolbar, away from the word ${JSON.stringify({ fb, toolsTop: tools.y, wordBottom: w.bottom })}`);
      ok(word === w.word && btns.length === 2 && btns.every(b => b.h >= 44) && btns[0].t === '划线并写释义', `selection bar shows the word and 44px buttons ${JSON.stringify({ word, btns })}`);
      await shot('11-select-bar');
      // 划线并写释义 → 贴着键盘的面板；输入框 16px，键盘弹起时输入框和保存都看得见
      const h0 = await histLen();
      await p.tap('#floatBox .ir-pop-main'); await sleep(400);
      const mb = await p.evaluate(() => ({ open: document.getElementById('meaningBox').style.display === 'block', focus: document.activeElement && document.activeElement.id, fs: parseFloat(getComputedStyle(document.getElementById('meaningInput')).fontSize), word: document.getElementById('mbWord').textContent }));
      ok(mb.open && mb.focus === 'meaningInput' && mb.fs >= 16 && mb.word === w.word, `meaning sheet opens focused, 16px input ${JSON.stringify(mb)}`);
      ok((await histLen()) === h0 + 1, 'meaning sheet pushed one history entry');
      await shot('12-meaning');
      await p.setViewportSize({ width: W, height: KB_H }); await sleep(350);
      const inp = await rect('#meaningInput'), save = await rect('#meaningBox .ir-pop-main');
      ok(inp.y >= 0 && inp.b <= KB_H && save.b <= KB_H && save.h >= 44 && inp.h >= 44, `keyboard (${KB_H}px): input and 保存 still visible ${JSON.stringify({ inp, save })}`);
      await shot('12b-meaning-keyboard');
      await p.setViewportSize(device.viewport); await sleep(200);
      // 系统返回关掉面板，选区操作栏也收起
      await back();
      const mb2 = await p.evaluate(() => ({ meaning: document.getElementById('meaningBox').style.display, float: document.getElementById('floatBox').style.display, open: document.getElementById('viewer').classList.contains('active') }));
      ok(mb2.meaning === 'none' && mb2.float === 'none' && mb2.open, `back closes the meaning sheet, reader stays ${JSON.stringify(mb2)}`);
      // 真存一条
      await longPressLine(1);
      await p.tap('#floatBox .ir-pop-main'); await sleep(300);
      await p.fill('#meaningInput', 'phone-e2e-释义');
      await p.tap('#meaningBox .ir-pop-main');
      await p.waitForFunction(() => (highlights || []).some(h => h.meaning === 'phone-e2e-释义'));
      await sleep(400);
      ok((await p.evaluate(() => document.getElementById('meaningBox').style.display)) === 'none', 'saving closes the meaning sheet');
    });

    // ==================== 点高亮 → 单词卡 ====================
    await section('word-card', async () => {
      const tapMark = async () => { const mk = await p.evaluate(() => { const h = highlights.find(h => h.meaning === 'phone-e2e-释义'); const m = document.querySelector(`#vContent mark.hl[data-hid="${h.id}"]`); window.scrollBy(0, m.getBoundingClientRect().top - 200); const r = m.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }); await p.touchscreen.tap(mk.x, mk.y); await sleep(350); };
      await tapMark();
      const wc = await p.evaluate(() => ({ open: !document.getElementById('wordCard').hidden, mean: document.getElementById('wcMean').textContent, tip: [...document.querySelectorAll('#vContent mark.hl .tooltip')].some(t => getComputedStyle(t).display !== 'none') }));
      ok(wc.open && wc.mean === 'phone-e2e-释义' && !wc.tip, `tapping a highlight opens the word card (no 13px bubble) ${JSON.stringify(wc)}`);
      const play = await rect('#wordCard .ir-pill'); const del = await rect('#wordCard .is-danger');
      ok(play.h >= 44 && del.h >= 44, `word card: ▶ and 删除 are ≥ 44px ${JSON.stringify([play.h, del.h])}`);
      await shot('13-word-card');
      // 点正文别处就收起
      await p.touchscreen.tap(W / 2, 150); await sleep(400);
      ok(await p.evaluate(() => document.getElementById('wordCard').hidden), 'tapping elsewhere closes the word card');
      // 在词汇表中查看 → 词汇面板（遮罩），系统返回关掉
      await tapMark();
      await p.tap('#wordCard .ir-wc-actions .ir-btn:not(.is-danger)'); await sleep(450);
      const vs = await p.evaluate(() => ({ panel: document.getElementById('highlightsPanel').classList.contains('active'), card: !document.getElementById('wordCard').hidden, scrim: !document.getElementById('irScrim').hidden, flash: !!document.querySelector('#hpBody .ir-vi.is-flash') }));
      ok(vs.panel && !vs.card && vs.scrim && vs.flash, `在词汇表中查看 opens the vocab sheet at that word ${JSON.stringify(vs)}`);
      await back();
      ok(!(await p.evaluate(() => document.getElementById('highlightsPanel').classList.contains('active'))) && await p.evaluate(() => document.getElementById('viewer').classList.contains('active')), 'back closes the vocab sheet, reader stays');
      // 删除：先问一句；确认后只拿掉这一个，不整篇重载（读到的位置不变）
      await tapMark();
      const n0 = dialogs.length;
      await p.tap('#wordCard .is-danger'); await sleep(300);
      ok(dialogs.length === n0 + 1 && (await p.evaluate(() => (highlights || []).some(h => h.meaning === 'phone-e2e-释义'))), 'word card delete asks first (dismiss keeps it)');
      await tapMark();
      const y0 = await p.evaluate(() => window.scrollY);
      acceptNext = true;
      await p.tap('#wordCard .is-danger');
      await p.waitForFunction(() => !(highlights || []).some(h => h.meaning === 'phone-e2e-释义'), null, { timeout: 5000 });
      await sleep(400);
      const d = await p.evaluate(() => ({ y: window.scrollY, marks: [...document.querySelectorAll('#vContent mark.hl')].length, card: document.getElementById('wordCard').hidden }));
      ok(Math.abs(d.y - y0) < 3 && d.card, `deleting removes just that highlight in place ${JSON.stringify({ ...d, y0 })}`);
    });

    // ==================== 词汇面板 ====================
    await section('vocab-sheet', async () => {
      await p.tap('#vocabToggle'); await sleep(400);
      const s = await p.evaluate(() => { const panel = document.getElementById('highlightsPanel').getBoundingClientRect(); const btn = document.querySelector('#hpBody .ir-vi .ir-icon-btn').getBoundingClientRect(); return { scrim: !document.getElementById('irScrim').hidden, fs: parseFloat(getComputedStyle(document.getElementById('hpSearch')).fontSize), btn: [Math.round(btn.width), Math.round(btn.height)], b: Math.round(panel.bottom), rows: document.querySelectorAll('#hpBody .ir-vi').length, assumed: [...document.querySelectorAll('#hpBody .ir-vi-word')].filter(e => e.textContent === 'assumed').length }; });
      ok(s.scrim && s.fs >= 16 && s.btn[0] >= 44 && s.btn[1] >= 44 && s.b === H, `vocab sheet: scrim, 16px search, 44px row buttons ${JSON.stringify(s)}`);
      ok(s.assumed === 1, `vocab sheet lists a word saved twice only once (assumed ×${s.assumed})`);
      await shot('14-vocab-sheet');
      await p.touchscreen.tap(W / 2, 60); await sleep(400);
      ok(!(await p.evaluate(() => document.getElementById('highlightsPanel').classList.contains('active'))), 'tapping the scrim closes the vocab sheet');
    });

    // ==================== ⋯ 面板、改标题 ====================
    await section('more-title', async () => {
      await p.tap('#moreBtn'); await sleep(400);
      const rows = await p.evaluate(() => [...document.querySelectorAll('#moreMenu .ir-menu-item')].filter(r => getComputedStyle(r).display !== 'none').map(r => Math.round(r.getBoundingClientRect().height)));
      const m = await rect('#moreMenu');
      ok(rows.length >= 3 && rows.every(h => h >= 52) && Math.round(m.b) === H && await p.evaluate(() => !document.getElementById('irScrim').hidden), `⋯ is a bottom sheet with 52px rows ${JSON.stringify({ rows, b: m.b })}`);
      await shot('15-more-sheet');
      await back();
      ok(!(await p.evaluate(() => document.getElementById('moreMenu').classList.contains('open'))), 'back closes the ⋯ sheet');
      await p.tap('#moreBtn'); await sleep(350);
      await p.tap('#moreMenu .ir-menu-item:has-text("修改标题")'); await sleep(400);
      const te = await p.evaluate(() => { const c = document.getElementById('titleEditContainer'); const i = document.getElementById('titleEditInput'); return { sheet: c.classList.contains('is-sheet') && c.style.display === 'flex', menu: document.getElementById('moreMenu').classList.contains('open'), focus: document.activeElement === i, fs: parseFloat(getComputedStyle(i).fontSize), w: Math.round(i.getBoundingClientRect().width), title: getComputedStyle(document.getElementById('vTitle')).display }; });
      ok(te.sheet && !te.menu && te.focus && te.fs >= 16 && te.w >= W * 0.5 && te.title !== 'none', `修改标题 opens a sheet with a wide 16px input ${JSON.stringify(te)}`);
      await p.setViewportSize({ width: W, height: KB_H }); await sleep(350);
      const inp = await rect('#titleEditInput'), save = await rect('#titleEditContainer .title-edit-save');
      ok(inp.y >= 0 && inp.b <= KB_H && save.b <= KB_H && save.h >= 44, `keyboard (${KB_H}px): title input and 保存 visible ${JSON.stringify({ inp, save })}`);
      await shot('16-title-keyboard');
      await p.setViewportSize(device.viewport); await sleep(200);
      await back();
      const te2 = await p.evaluate(() => ({ shown: document.getElementById('titleEditContainer').style.display, title: document.getElementById('vTitle').textContent }));
      ok(te2.shown === 'none' && te2.title === "The Lighthouse Keeper's Log", `back cancels the title edit ${JSON.stringify(te2)}`);
    });

    // ==================== 朗读 ====================
    await section('audio', async () => {
      // 没有音频的文章：点「朗读」先问一句，不会随手就调付费接口
      const n0 = dialogs.length;
      await p.tap('#generateAudioBtn'); await sleep(400);
      ok(dialogs.length === n0 + 1 && /生成/.test(dialogs[dialogs.length - 1] || '') && paid.length === 0, `朗读 without audio asks before generating ${JSON.stringify(dialogs.slice(-1))}`);
      await open(IDS.saltMarsh);
      await p.waitForFunction(() => document.getElementById('audioPanel').style.display === 'block'); await sleep(400);
      const ap = await rect('#audioPanel'), tl = await rect('#viewer .ir-tools'), bar = await rect('#viewer .ir-bar'), play = await rect('#apPlay');
      const textShare = (ap.y - bar.b) / H;
      ok(Math.round(ap.b) === Math.round(tl.y) && play.w >= 44 && play.h >= 44, `mini player sits on the toolbar, 44px play ${JSON.stringify({ ap, tl: tl.y, play })}`);
      ok(textShare >= 0.6, `with the player open, ≥ 60% of the screen is still passage (${Math.round(textShare * 100)}%)`);
      await shot('20-audio');
      await p.evaluate(() => window.scrollTo(0, 99999)); await sleep(200);
      const last = await p.evaluate(() => { const ps = document.querySelectorAll('#vContent .reader p'); return Math.round(ps[ps.length - 1].getBoundingClientRect().bottom); });
      ok(last <= Math.round(ap.y), `last line clears the player (${last} ≤ ${ap.y})`);
      await shot('21-audio-bottom');
      // ˅ 收起不卸载；「朗读」再展开
      await p.tap('#audioPanel .ir-ap-btn:not(#apPlay)'); await sleep(250);
      const c1 = await p.evaluate(() => ({ shown: getComputedStyle(document.getElementById('audioPanel')).display, src: !!document.getElementById('articleAudio').getAttribute('src') }));
      await p.tap('#generateAudioBtn'); await sleep(250);
      const c2 = await p.evaluate(() => ({ shown: getComputedStyle(document.getElementById('audioPanel')).display, on: document.getElementById('generateAudioBtn').classList.contains('is-on') }));
      ok(c1.shown === 'none' && c1.src && c2.shown !== 'none' && c2.on, `˅ collapses without unloading, 朗读 brings it back ${JSON.stringify([c1, c2])}`);
      // 重新生成只在 ⋯ 里，而且要确认；取消就什么都不发
      const regenInBar = await p.evaluate(() => [...document.querySelectorAll('#viewer .ir-tools .ir-icon-btn')].some(b => /重新生成/.test(b.textContent) && getComputedStyle(b).display !== 'none'));
      await p.tap('#moreBtn'); await sleep(350);
      const n1 = dialogs.length;
      await p.tap('#menuRegenBtn'); await sleep(400);
      ok(!regenInBar && dialogs.length === n1 + 1 && /重新生成/.test(dialogs[dialogs.length - 1]) && paid.length === 0, `重新生成 lives only in ⋯, confirms first, cancel sends nothing ${JSON.stringify({ regenInBar, paid })}`);
      // 下载也在 ⋯ 里；下载完返回键还对得上（WebKit 里下载会取消还没做完的退历史）
      await p.tap('#moreBtn'); await sleep(350);
      const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 8000 }), p.tap('#menuDownloadBtn')]);
      await sleep(500);
      const afterDl = await p.evaluate(() => ({ menu: document.getElementById('moreMenu').classList.contains('open'), layer: !!(history.state && history.state.irLayer), reader: !!(history.state && history.state.irReader) }));
      ok(/\.mp3$/.test(dl.suggestedFilename()) && !afterDl.menu && !afterDl.layer && afterDl.reader, `⋯ → 下载朗读音频 downloads the mp3 and leaves history in step ${JSON.stringify({ name: dl.suggestedFilename(), ...afterDl })}`);
    });

    // ==================== 图片 ====================
    await section('images', async () => {
      await open(IDS.chart);
      await p.waitForFunction(() => { const i = document.querySelector('#imagesGrid .image-item img'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 5000 });
      const x = await rect('#imagesGrid .image-delete-btn');
      ok(!x.vis, 'image strip: no ✕ on thumbnails (delete is in the viewer)');
      const h0 = await histLen();
      await p.tap('#imagesGrid .image-item'); await sleep(450);
      const close = await rect('.image-modal-close'), del = await rect('#deleteImageBtn');
      ok(close.w >= 44 && close.h >= 44 && del.h >= 44 && (await histLen()) === h0 + 1, `image viewer: 44px ✕ and 删除这张 ${JSON.stringify({ close, del })}`);
      await shot('22-image-viewer');
      await back(); await sleep(150);
      const v = await p.evaluate(() => ({ modal: document.getElementById('imageModal').style.display, reader: document.getElementById('viewer').classList.contains('active') }));
      ok(v.modal === 'none' && v.reader, `back closes the image viewer, reader stays ${JSON.stringify(v)}`);
    });

    // ==================== 九分学长导入：题目面板 ====================
    await section('questions', async () => {
      await open(IDS.glassBridge);
      ok((await rect('#examSheetBtn')).vis && !(await rect('#examTabs')).vis, 'imported article: 题目 in the toolbar, no 原文 / 题目 tabs');
      const h0 = await histLen();
      await p.tap('#examSheetBtn'); await sleep(400);
      const pk = await p.evaluate(() => { const pane = document.getElementById('examPane'); const r = pane.getBoundingClientRect(); return { shown: [...pane.querySelectorAll('.ir-q')].filter(q => getComputedStyle(q).display !== 'none').map(q => q.dataset.num), top: r.top, h: r.height, nav: [...pane.querySelectorAll('.ir-qs-nav button')].map(b => Math.round(b.getBoundingClientRect().height)) }; });
      ok(JSON.stringify(pk.shown) === '["1"]' && pk.h <= H * 0.56 && pk.nav.length === 4 && pk.nav.every(h => h >= 44), `peek: only the current question, ≤ 56% of the screen, 44px nav ${JSON.stringify(pk)}`);
      ok((await histLen()) === h0 + 1, 'questions sheet pushed one history entry');
      await p.tap('.ir-qs-nav [data-act="qs-next"]'); await sleep(200);
      ok((await p.evaluate(() => document.querySelector('#examPane .ir-q.is-cur').dataset.num)) === '2', '下一题 › moves to question 2');
      // 定位：证据句滚到顶栏和面板之间，题目还在面板里
      await p.tap('.ir-qs-nav [data-act="qs-locate"]'); await sleep(900);
      const loc = await p.evaluate(() => { const ev = [...document.querySelectorAll('#vContent p.ir-ev')]; const a = ev[0].getBoundingClientRect(), z = ev[ev.length - 1].getBoundingClientRect(); const bar = document.querySelector('#viewer .ir-bar').getBoundingClientRect().bottom; const pane = document.getElementById('examPane'); return { s: ev.map(p => p.dataset.s).join(), top: Math.round(a.top), bottom: Math.round(z.bottom), bar: Math.round(bar), paneTop: Math.round(pane.getBoundingClientRect().top), open: pane.classList.contains('is-peek'), cur: pane.querySelector('.ir-q.is-cur').dataset.num }; });
      ok(loc.s === '2,3' && loc.top >= loc.bar && loc.bottom <= loc.paneTop && loc.open && loc.cur === '2', `定位 shows the evidence between the top bar and the question ${JSON.stringify(loc)}`);
      await shot('30-questions-located');
      await p.tap('.ir-qs-nav [data-act="qs-analysis"]'); await sleep(250);
      ok(await p.evaluate(() => !document.querySelector('#examPane .ir-q.is-cur .ir-analysis').hidden), '解析 opens the analysis in the peek');
      // 划词时操作栏贴在面板上面
      await longPressLine(4);
      const fb = await rect('#floatBox'), pane = await rect('#examPane');
      ok(fb.vis && Math.abs(fb.b - pane.y) < 2, `selection bar docks on top of the questions sheet ${JSON.stringify({ fb: fb.b, pane: pane.y })}`);
      await p.evaluate(() => cancelFloat()); await sleep(300);
      // 展开：成绩、全部 / 只看错题、显示答案开关
      await p.tap('#examPane .ir-qs-head'); await sleep(400);
      const full = await p.evaluate(() => { const pane = document.getElementById('examPane'); const seg = pane.querySelector('[data-act="qs-wrong"]').getBoundingClientRect(); const sw = pane.querySelector('[data-act="qs-answers"]').getBoundingClientRect(); return { full: pane.classList.contains('is-full'), h: pane.getBoundingClientRect().height, seg: Math.round(seg.height), sw: Math.round(sw.height), scrim: !document.getElementById('irScrim').hidden }; });
      ok(full.full && full.h > H * 0.8 && full.seg >= 38 && full.sw >= 44 && full.scrim, `header tap expands the full list ${JSON.stringify(full)}`);
      await p.tap('#examPane [data-act="qs-wrong"]'); await sleep(200);
      const wrong = await p.evaluate(() => [...document.querySelectorAll('#examPane .ir-q')].filter(q => getComputedStyle(q).display !== 'none').map(q => q.dataset.num).join());
      await p.tap('#examPane [data-act="qs-all"]'); await sleep(200);
      ok(wrong === '2,4,5', `只看错题 in the sheet: ${wrong}`);
      await p.tap('#examPane [data-act="qs-answers"]'); await sleep(200);
      const hid = await p.evaluate(() => ({ hide: document.getElementById('examPane').classList.contains('hide-ans'), aria: document.querySelector('#examPane [data-act="qs-answers"]').getAttribute('aria-checked') }));
      await p.tap('#examPane [data-act="qs-answers"]'); await sleep(200);
      ok(hid.hide && hid.aria === 'false' && !(await p.evaluate(() => document.getElementById('examPane').classList.contains('hide-ans'))), `显示答案 switch hides and shows answers ${JSON.stringify(hid)}`);
      await shot('31-questions-full');
      // 系统返回：先收成一题，再关掉面板，阅读页还在
      await back();
      const b1 = await p.evaluate(() => { const pane = document.getElementById('examPane'); return { peek: pane.classList.contains('is-peek'), full: pane.classList.contains('is-full') }; });
      await back();
      const b2 = await p.evaluate(() => ({ open: document.getElementById('examPane').classList.contains('is-open'), reader: document.getElementById('viewer').classList.contains('active') }));
      ok(b1.peek && !b1.full && !b2.open && b2.reader, `back: full list → one question → closed, reader stays ${JSON.stringify([b1, b2])}`);
      ok(await noOverflow(), 'imported article: no horizontal overflow');
    });

    // ==================== 暗色 ====================
    await section('dark', async () => {
      await p.emulateMedia({ colorScheme: 'dark' });
      await lib.settle(p); await p.reload(); await p.waitForFunction(() => currentArticle && document.querySelector('#vContent .reader p')); await sleep(400);
      const d = await p.evaluate(() => ({ tools: getComputedStyle(document.querySelector('#viewer .ir-tools')).backgroundColor, bar: getComputedStyle(document.querySelector('#viewer .ir-bar')).backgroundColor, text: getComputedStyle(document.querySelector('#vContent .reader p.en')).color }));
      ok(d.tools === 'rgb(30, 30, 30)' && d.bar === 'rgb(30, 30, 30)' && d.text === 'rgb(236, 236, 234)', `dark: toolbar, top bar and text use the dark tokens ${JSON.stringify(d)}`);
      await p.tap('#examSheetBtn'); await sleep(400);
      const s = await p.evaluate(() => getComputedStyle(document.getElementById('examPane')).backgroundColor);
      ok(s === 'rgb(30, 30, 30)', `dark: questions sheet surface ${s}`);
      await shot('40-dark-questions');
      await back();
      await p.tap('#vocabToggle'); await sleep(400);
      await shot('41-dark-vocab');
      await back();
      await p.emulateMedia({ colorScheme: 'light' });
    });

    // ==================== 添加文章 ====================
    await section('new', async () => {
      await lib.settle(p); await p.goto(BASE + '/intensive/new');
      await p.evaluate(() => { try { localStorage.setItem('intensiveNewMode', 'json'); } catch (e) {} });
      await lib.settle(p); await p.reload(); await sleep(400);
      ok(await noOverflow(), '/intensive/new: no horizontal overflow');
      const raw = await rect('#raw'), back1 = await rect('.ir-back'), tab = await rect('#tab-json');
      ok(raw.fs >= 16 && back1.h >= 44 && tab.h >= 40, `/intensive/new: 16px JSON box, 44px back link, 40px tabs ${JSON.stringify({ fs: raw.fs, back: back1.h, tab: tab.h })}`);
      const clip = await p.evaluate(() => ({ api: !!(navigator.clipboard && navigator.clipboard.readText), shown: getComputedStyle(document.querySelector('.ir-paste')).display !== 'none' }));
      ok(clip.api === clip.shown, `从剪贴板粘贴 shows only when the browser can read the clipboard ${JSON.stringify(clip)}`);
      await shot('50-new-json');
      await p.fill('#raw', fs.readFileSync(FIXTURE, 'utf8'));
      await p.waitForSelector('#preview .ir-part');
      await sleep(200);
      const imp = await rect('#importBtn');
      ok(imp.vis && imp.b <= H && imp.h >= 44 && imp.w >= W * 0.8, `导入 is a full-width bar at the bottom, visible right after pasting ${JSON.stringify(imp)}`);
      await p.evaluate(() => window.scrollTo(0, 99999)); await sleep(150);
      const chk = await rect('#pane-json .ir-check'), bar = await rect('#pane-json .ir-actions');
      ok(chk.b <= bar.y, `翻到底，最后一个开关不被底部导入栏挡住 (${chk.b} ≤ ${bar.y})`);
      const sw = await rect('#pane-json .ir-check');
      ok(sw.h >= 44, `逐句翻译 is a ≥ 44px switch row (${sw.h})`);
      await p.tap('#pane-json .ir-segs [data-cat="Listening"]');
      const cat = await p.evaluate(() => document.getElementById('jsonCategory').value);
      await p.tap('#pane-json .ir-segs [data-cat="Reading"]');
      ok(cat === 'Listening', `category segment writes the select (${cat})`);
      await shot('51-new-preview');
      // 翻译失败：底栏换成「不翻译，直接导入」（主按钮）和「重试翻译」，说明写在上面
      await p.tap('#importBtn');
      await p.waitForSelector('#importNoZhBtn', { state: 'visible', timeout: 60000 });
      await sleep(200);
      const f = await p.evaluate(() => { const no = document.getElementById('importNoZhBtn').getBoundingClientRect(), re = document.getElementById('importBtn').getBoundingClientRect(), msg = document.getElementById('importMsg').getBoundingClientRect(); return { noLeft: no.left < re.left, noBg: getComputedStyle(document.getElementById('importNoZhBtn')).backgroundColor, retry: document.getElementById('importBtn').innerText.trim(), msgAbove: msg.bottom <= no.top + 1, bottom: Math.round(no.bottom) }; });
      ok(f.noLeft && f.retry === '重试翻译' && f.msgAbove && f.bottom <= H && f.noBg !== 'rgb(255, 255, 255)', `translate failure: 不翻译，直接导入 becomes primary, 重试翻译 secondary ${JSON.stringify(f)}`);
      await shot('52-new-failed');
      // 粘贴文本：键盘弹起时「创建」托在键盘上，输入框看得见
      await p.tap('#tab-text'); await sleep(200);
      const ti = await rect('#title'), co = await rect('#content');
      ok(ti.fs >= 16 && co.fs >= 16, `text mode: 16px title and body (${ti.fs}, ${co.fs})`);
      await p.focus('#content');
      await p.setViewportSize({ width: W, height: KB_H }); await sleep(300);
      await p.evaluate(() => document.getElementById('content').scrollIntoView({ block: 'center' })); await sleep(200);
      const cb = await rect('#createBtn'), co2 = await rect('#content');
      ok(cb.vis && cb.b <= KB_H && cb.h >= 44 && co2.y < cb.y, `keyboard (${KB_H}px): 创建 sits above the keyboard, body field visible ${JSON.stringify({ cb, co: co2.y })}`);
      await shot('53-new-text-keyboard');
      await p.setViewportSize(device.viewport);
      const add = await rect('.ir-add-img');
      ok(add.vis && add.h >= 44, `text mode: ＋ 添加图片 tile ${JSON.stringify(add)}`);
      await p.tap('#tab-json');
    });

    ok(paid.length === 0, `no paid audio endpoint was called ${JSON.stringify(paid)}`);
    ok(errs.length === 0, `page errors ${errs.join(' | ')}`);
  } finally {
    await ctx.close();
  }
};

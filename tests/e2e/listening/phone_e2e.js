// 手机版「听力精听复习 / 听力笔记本」的浏览器检查（沙盒、编造数据）：
// WebKit 390×844（iPhone Safari 内核）或 Chromium 360×780（安卓），亮色 + 暗色。
// 列表两列和卡片「⋯」→ 上传底部面板 → 精听页的页签、底部播放条（上一句 / 下一句 / 单句循环 / 倍速）、
// 正在播那句的操作行、听错原因面板、跟随播放和「回到当前句」、选词条和生词 / 笔记面板（键盘高 470）、
// 返回键先关面板再回列表、刷新还在这篇 → 导入的篇：题目页签、题号 ↔ 原文出处、重做的卷子 / 答题卡 / 字母面板 →
// 笔记本：吸顶筛选、搜索、复习的底部按钮和筛选面板。
// 用法见 README（第 6 步）；每跑一次前先重灌 seed.py 和 jiufen_data.py。
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const engine = process.argv[2] || 'webkit';
const sb = process.env.LR_SANDBOX;
if (!sb) { console.error('请用 LR_SANDBOX 指定沙盒目录（先跑 seed.py 和 jiufen_data.py），见 README.md'); process.exit(2); }
const fake = path.join(__dirname, 'jiufen_fake_translate.py');
const BASE = (process.env.LR_BASE_URL || 'http://localhost:5073').replace(/\/$/, '');
const OUT = process.env.LR_OUT_DIR || path.join(os.tmpdir(), 'listening-e2e');
fs.mkdirSync(OUT, { recursive: true });
const token = JSON.parse(fs.readFileSync(`${sb}/e2e_tokens.json`, 'utf8')).demo;
const HALL = 'lr_20261028_201500_demo0001';
const W = engine === 'webkit' ? 390 : 360, H = engine === 'webkit' ? 844 : 780;
let pass = 0, fail = 0, skip = 0;
const check = (name, ok, got) => { ok ? pass++ : fail++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + JSON.stringify(got)}`); };
const skipped = (name, why) => { skip++; console.log(`SKIP  ${name}  (${why})`); };
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
// 在老页面上跑（证明这些检查对改版前会失败）时元素可能不存在：点不到就记下来，不让整个脚本卡死
const tryTap = async (page, sel) => { try { await page.tap(sel, { timeout: 2500 }); return true; } catch { return false; } };

async function newPage(browser, theme) {
  const opts = { viewport: { width: W, height: H }, hasTouch: true, deviceScaleFactor: 2, colorScheme: theme };
  if (engine === 'chromium') opts.isMobile = true;   // WebKit 不支持 isMobile
  const ctx = await browser.newContext(opts);
  await ctx.addInitScript(([t, th]) => { if (location.protocol === 'about:') return; localStorage.setItem('authToken', t); localStorage.setItem('ui-theme', th); }, [token, theme]);
  const page = await ctx.newPage();
  page.on('pageerror', e => check(`${theme}: no page errors`, false, e.message));
  return { ctx, page };
}
const shot = async (page, name) => { await sleep(300); await page.screenshot({ path: path.join(OUT, `phone-${engine}-${name}.png`) }); };
const overflow = (page) => page.evaluate(() => Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth);
const rect = (page, sel) => page.evaluate((s) => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); const cs = getComputedStyle(e); return { t: Math.round(r.top), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right), w: Math.round(r.width), h: Math.round(r.height), shown: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' }; }, sel);
const shown = async (page, sel) => !!(await rect(page, sel) || {}).shown;
// 一段检查出错（比如对着改版前的页面跑、元素不存在）只记一项失败，接着跑下一段
async function section(name, fn) {
  try { await fn(); } catch (e) { check(`${name}: ran to the end`, false, String(e && e.message || e).split('\n')[0]); }
}
async function ensureListening(page) {
  const ok = await page.evaluate(() => location.pathname === '/listening_review' && typeof state !== 'undefined' && state.projects.length > 0).catch(() => false);
  if (ok) return;
  await page.goto(`${BASE}/listening_review`);
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
}
async function openByTitle(page, re) {
  await ensureListening(page);
  await page.evaluate(async (src) => {
    if (state.view === 'detail') backToList();
    await loadProjects();
    const p = state.projects.find(p => new RegExp(src).test(p.title));
    await openProject(p.id);
  }, re.source);
  await page.waitForFunction(() => state.view === 'detail', null, { timeout: 5000 });
  await sleep(300);
}

(async () => {
  const browser = await pw[engine].launch();

  // ---------- 准备：导入三份九分学长 JSON（填空 + 单选；地图 + 多选；版式里的字母槽），补上编的译文 ----------
  {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    await ctx.addInitScript(t => { if (location.protocol === 'about:') return; localStorage.setItem('authToken', t); }, token);
    const page = await ctx.newPage();
    await page.goto(`${BASE}/listening_review`);
    await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
    for (const file of ['e2e_single.json', 'e2e_map.json', 'e2e_mixed.json']) {
      await page.evaluate(async (file) => {
        openUploadModal(); switchTab('json');
        const text = await (await fetch('/static/e2e/' + file)).text();
        const dt = new DataTransfer(); dt.setData('text/plain', text);
        document.getElementById('jsonPaste').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
      }, file);
      await page.waitForFunction(() => !document.getElementById('uploadJsonBtn').disabled, null, { timeout: 5000 });
      await page.click('#uploadJsonBtn');
      await page.waitForFunction(() => document.getElementById('uploadModal').hidden, null, { timeout: 5000 });
    }
    await page.waitForFunction(() => state.projects.filter(p => p.source_type === 'jiufen' && p.status === 'error' && p.error_phase === 'polish').length === 4, null, { timeout: 30000 });
    execFileSync('python3', [fake, sb]);
    await ctx.close();
  }

  for (const theme of ['light', 'dark']) {
    const T = theme;
    const { ctx, page } = await newPage(browser, theme);

    // ================= 列表 =================
    await section(`${T} list`, async () => {
    await page.goto(`${BASE}/listening_review`);
    await page.waitForSelector('.lr-proj');
    await sleep(300);
    check(`${T} list: no horizontal overflow`, await overflow(page) <= 0, await overflow(page));
    const cols = await page.$$eval('.lr-proj', els => new Set(els.map(e => Math.round(e.getBoundingClientRect().left))).size);
    check(`${T} list: two cards per row`, cols === 2, cols);
    const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
    check(`${T} list: theme applies`, theme === 'dark' ? bg !== 'rgb(247, 247, 245)' : bg === 'rgb(247, 247, 245)', bg);
    if (theme === 'light') {
      const head = await page.evaluate(() => { const u = document.querySelector('.lr-head__upload'); if (!u) return null; const r = u.getBoundingClientRect(); return { h: Math.round(r.height), filled: getComputedStyle(u).backgroundColor !== getComputedStyle(document.querySelector('#listView .lr-head .ui-btn')).backgroundColor }; });
      check('list: 上传音频 is the filled primary button, 44px', head && head.h >= 44 && head.filled, head);
      const chips = await page.$$eval('#listToolbar .ui-chip', els => els.map(e => Math.round(e.getBoundingClientRect().height)));
      check('list: filter chips 44px', chips.length === 3 && chips.every(h => h >= 44), chips);
      const more = await rect(page, '.lr-proj [data-act="more"]');
      const trash = await rect(page, '.lr-proj [data-act="delete"]');
      check('list: card delete moved into a 44px「⋯」(no bare trash icon)', more && more.shown && more.h >= 44 && !(trash && trash.shown), { more, trash });
      await shot(page, 'list');
      await tryTap(page, '.lr-proj [data-act="more"]');
      await sleep(300);
      const cs = await rect(page, '#cardSheet .ui-dialog');
      check('list: 「⋯」 opens an action sheet at the bottom', cs && cs.shown && Math.abs(cs.b - H) <= 1, cs);
      await shot(page, 'card-sheet');
      await page.goBack().catch(() => {});
      await sleep(400);
      const afterBack = await page.evaluate(() => ({ sheet: !document.getElementById('cardSheet') || document.getElementById('cardSheet').hidden, url: location.pathname, list: !document.getElementById('listView').hidden }));
      check('list: back closes the action sheet and stays on the list', afterBack.sheet && afterBack.list && afterBack.url === '/listening_review', afterBack);
      // 转录中的卡片点了有提示
      await page.evaluate(() => { const p = state.projects.find(x => x.status === 'error'); if (p) { p.status = 'processing'; renderListView(); } });
      await tryTap(page, '.lr-proj.is-busy .lr-proj__title');
      const busyToast = await page.waitForFunction(() => [...document.querySelectorAll('.ielts-toast')].some(t => /还在转录/.test(t.textContent)), null, { timeout: 2500 }).then(() => true).catch(() => false);
      check('list: tapping a busy card explains why it does not open', busyToast, busyToast);
      await page.evaluate(() => loadProjects());

      // ================= 上传面板 =================
      await tryTap(page, '.lr-head__upload');
      await sleep(300);
      const tabs = await page.$$eval('.modal-tab', els => els.map(e => ({ h: Math.round(e.getBoundingClientRect().height), t: e.innerText.trim() })));
      check('upload: three 44px source tabs with short phone labels', tabs.length === 3 && tabs.every(t => t.h >= 44) && tabs.map(t => t.t).join('|') === '文件|链接|九分学长', tabs);
      const fsz = await page.evaluate(() => ['fileTitle', 'urlInput', 'jsonPaste'].map(id => parseFloat(getComputedStyle(document.getElementById(id)).fontSize)));
      check('upload: typed fields are 16px', fsz.every(s => s >= 16), fsz);
      await page.evaluate(() => switchTab('url'));
      await tryTap(page, '#urlInput');
      await page.setViewportSize({ width: W, height: 470 });
      await sleep(400);
      const kb = await page.evaluate(() => { const i = document.getElementById('urlInput').getBoundingClientRect(); const b = document.getElementById('uploadUrlBtn').getBoundingClientRect(); return { it: Math.round(i.top), ib: Math.round(i.bottom), bt: Math.round(b.top), bb: Math.round(b.bottom), vh: innerHeight, hint: document.getElementById('urlInput').getAttribute('enterkeyhint') }; });
      check('upload: link field and 下载并转录 both visible with the keyboard up (470px)', kb.it >= 0 && kb.ib <= kb.vh && kb.bt >= kb.ib && kb.bb <= kb.vh && kb.hint === 'go', kb);
      await page.evaluate(() => document.activeElement.blur());
      await page.setViewportSize({ width: W, height: H });
      await page.evaluate(async () => {
        switchTab('json');
        const text = await (await fetch('/static/e2e/e2e_mixed.json')).text();
        const dt = new DataTransfer(); dt.setData('text/plain', text);
        document.getElementById('jsonPaste').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
      });
      await page.waitForFunction(() => !document.getElementById('jsonPreview').hidden, null, { timeout: 5000 }).catch(() => {});
      await sleep(300);
      const imp = await page.evaluate(() => {
        const btn = document.getElementById('uploadJsonBtn').getBoundingClientRect();
        const dlg = document.getElementById('uploadDialog').getBoundingClientRect();
        const segs = [...document.querySelectorAll('.lr-imp__merge .ui-seg__btn')].map(b => { const r = b.getBoundingClientRect(); return { r: Math.round(r.right), h: Math.round(r.height) }; });
        return { btnTop: Math.round(btn.top), btnBottom: Math.round(btn.bottom), vh: innerHeight, dlgRight: Math.round(dlg.right), segs };
      });
      check('upload: 导入 button visible without scrolling the sheet', imp.btnBottom <= imp.vh && imp.btnTop >= 0, imp);
      check('upload: 更新那一篇 / 另建一篇 fit inside the sheet, 44px', imp.segs.length >= 2 && imp.segs.every(s => s.r <= imp.dlgRight && s.h >= 44), imp);
      await shot(page, 'upload-json');
      await page.goBack().catch(() => {});
      await sleep(400);
      const up = await page.evaluate(() => ({ closed: document.getElementById('uploadModal').hidden, list: !document.getElementById('listView').hidden }));
      check('upload: back closes the sheet, still on the list', up.closed && up.list, up);
      await page.evaluate(() => closeUploadModal());
    }

    });

    // ================= 精听页（没有题的篇） =================
    await section(`${T} detail`, async () => {
    await ensureListening(page);
    if (await page.evaluate(() => state.view === 'detail')) await page.evaluate(() => backToList());
    await tryTap(page, `[data-act="open"][data-id="${HALL}"] .lr-proj__title`);
    await page.waitForSelector('.lr-line');
    await sleep(500);
    check(`${T} detail: no horizontal overflow`, await overflow(page) <= 0, await overflow(page));
    const bar = await rect(page, '#ptabs');
    const tabNames = await page.$$eval('.ptab-btn', els => els.filter(e => !e.hidden).map(e => e.innerText.replace(/\s+/g, '')));
    check(`${T} detail: tab bar 原文 | 本篇 with 译 and ⋯ (44px)`, bar && bar.shown && tabNames.length === 2 && /^原文/.test(tabNames[0]) && /^本篇/.test(tabNames[1]) && (await rect(page, '#ptabTrans') || {}).h >= 44, { bar, tabNames });
    await page.evaluate(() => window.scrollTo(0, 600));
    await sleep(300);
    const stuck = await page.evaluate(() => { const b = document.getElementById('ptabs'); const n = document.querySelector('.app-shell-nav'); return b && n ? Math.round(b.getBoundingClientRect().top - n.getBoundingClientRect().bottom) : null; });
    check(`${T} detail: tab bar sticks under the nav when scrolled`, stuck !== null && Math.abs(stuck) <= 1, stuck);
    const lines = await page.evaluate(() => { const l = document.querySelector('.lr-line'); const en = l.querySelector('.lr-line__en').getBoundingClientRect(); const t = l.querySelector('.lr-line__time'); return { enW: Math.round(en.width), timeShown: !!t && getComputedStyle(t).display !== 'none', w: innerWidth }; });
    check(`${T} detail: transcript uses the full width (no time / star columns)`, !lines.timeShown && lines.enW >= lines.w - 64, lines);

    // 播放条
    const pl = await page.evaluate(() => {
      const r = (id) => { const e = document.getElementById(id); if (!e) return null; const b = e.getBoundingClientRect(); return { w: Math.round(b.width), h: Math.round(b.height), l: Math.round(b.left), r: Math.round(b.right), cx: Math.round(b.left + b.width / 2), shown: b.width > 0 }; };
      return { speed: r('speedChip'), prev: r('prevSegBtn'), play: r('playBtn'), next: r('nextSegBtn'), loop: r('loopBtn'), cur: r('curTime'), tot: r('totTime2'), w: innerWidth, bar: Math.round(document.getElementById('lrPlayer').getBoundingClientRect().height) };
    });
    const ctrls = ['speed', 'prev', 'next', 'loop'].map(k => pl[k]);
    check(`${T} player: speed, 上一句, 下一句, 单句循环 on screen, ≥44px`, ctrls.every(c => c && c.shown && c.h >= 44 && c.w >= 44 && c.l >= 0 && c.r <= pl.w), pl);
    check(`${T} player: play 56px in the middle`, pl.play && pl.play.h >= 56 && Math.abs(pl.play.cx - pl.w / 2) <= 4, pl.play);
    check(`${T} player: times at both ends of the seek bar`, pl.cur && pl.tot && pl.tot.shown && pl.cur.l < 40 && pl.tot.r > pl.w - 40, { cur: pl.cur, tot: pl.tot });
    const barVar = await page.evaluate(() => parseFloat(getComputedStyle(document.body).getPropertyValue('--ui-bottom-bar-h')) || 0);
    check(`${T} player: --ui-bottom-bar-h = player height (toasts float above it)`, barVar > 0 && Math.abs(barVar - pl.bar) <= 2, { barVar, bar: pl.bar });
    if (theme === 'light') await shot(page, 'detail-top');

    // 点一句：从这句播；正在播的这句下面一行操作，收藏在最前，没收藏时没有「原因」
    await page.evaluate(() => window.scrollTo(0, 0));
    await tryTap(page, '.lr-line[data-seg-id="3"] .lr-line__zh');
    await sleep(700);
    const act = await page.evaluate(() => {
      const line = document.querySelector('.lr-line.is-active');
      const btns = line ? [...line.querySelectorAll('.lr-acts .lr-act')].filter(b => b.getBoundingClientRect().width > 0) : [];
      return { seg: line && line.dataset.segId, starred: !!line && line.classList.contains('is-starred'), paused: audioEl.paused, names: btns.map(b => b.innerText.replace(/\s+/g, '')), hs: btns.map(b => Math.round(b.getBoundingClientRect().height)) };
    });
    check(`${T} line: tapping a line plays from it`, act.seg === '3' && !act.paused, act);
    // 亮色那一轮已经收藏了第 3 句（还选了原因），暗色这一轮看到的是收藏过的样子
    const wantActs = act.starred ? ['收藏', '原因', '重听', '笔记'] : ['收藏', '重听', '笔记'];
    check(`${T} line: active line shows 收藏 first; 原因 only once starred; 40px`, act.names.length === wantActs.length && act.names.every((n, i) => n.startsWith(wantActs[i])) && act.hs.every(h => h >= 40), act);
    await page.evaluate(() => audioEl.pause());
    if (theme === 'light') {
      await tryTap(page, '.lr-line.is-active .lr-act--star');
      await sleep(500);
      const why = await page.evaluate(() => { const b = document.querySelector('.lr-line.is-active .lr-act--why'); return b && b.getBoundingClientRect().width > 0; });
      check('line: 原因 appears once the line is starred', why, why);
      await tryTap(page, '.lr-line.is-active .lr-act--why');
      await sleep(300);
      const ws = await page.evaluate(() => { const s = document.getElementById('whySheet'); if (!s || s.hidden) return null; const rows = [...s.querySelectorAll('.lr-whyrow')].map(r => Math.round(r.getBoundingClientRect().height)); return { rows, bottom: Math.round(s.querySelector('.ui-dialog').getBoundingClientRect().bottom) }; });
      check('why: 听错原因 opens a bottom sheet with five rows ≥48px', ws && ws.rows.length === 5 && ws.rows.every(h => h >= 48) && Math.abs(ws.bottom - H) <= 1, ws);
      await shot(page, 'why-sheet');
      await tryTap(page, '#whyList [data-tag="phonetic"]');
      await page.waitForFunction(() => (state.currentData.error_tags['3'] || []).includes('phonetic'), null, { timeout: 3000 }).catch(() => {});
      const chip = await page.evaluate(() => ({ on: document.querySelector('#whyList [data-tag="phonetic"]')?.classList.contains('is-on'), chip: document.querySelector('.lr-line[data-seg-id="3"] .error-rest-chip')?.textContent, n: document.querySelector('.lr-line[data-seg-id="3"] .lr-act__n')?.textContent }));
      check('why: picking a reason marks the row and shows the chip under the line', chip.on && /辨音/.test(chip.chip || '') && chip.n === '1', chip);
      await page.goBack().catch(() => {});
      await sleep(400);
      const wb = await page.evaluate(() => ({ sheet: document.getElementById('whySheet').hidden, detail: state.view === 'detail' }));
      check('why: back closes the sheet, stays on the article', wb.sheet && wb.detail, wb);
    }

    // 上一句 / 下一句 / 单句循环 / 倍速
    await page.evaluate(() => { const s = state.currentData.segments[3]; audioEl.currentTime = s.start + 0.3; });
    await sleep(200);
    await tryTap(page, '#nextSegBtn');
    await sleep(600);
    const n1 = await page.evaluate(() => ({ seg: state.activeSegmentId, playing: !audioEl.paused }));
    await tryTap(page, '#prevSegBtn');   // 刚开始 1 秒内：回到上一句
    await sleep(300);
    const p1 = await page.evaluate(() => state.activeSegmentId);
    check(`${T} player: 下一句 jumps on and plays, 上一句 goes back`, n1.seg === 4 && n1.playing && p1 === 3, { n1, p1 });
    await tryTap(page, '#loopBtn');
    const seg3 = await page.evaluate(() => { const s = state.currentData.segments[3]; return { start: s.start, end: s.end }; });
    await page.evaluate((t) => { audioEl.currentTime = t; audioEl.play(); }, seg3.end - 0.6);
    await sleep(1600);
    const lp = await page.evaluate(() => ({ t: audioEl.currentTime, seg: state.activeSegmentId, pressed: document.getElementById('loopBtn')?.getAttribute('aria-pressed') }));
    check(`${T} player: 单句循环 jumps back to the start of the sentence`, lp.pressed === 'true' && lp.seg === 3 && lp.t >= seg3.start && lp.t < seg3.end, { lp, seg3 });
    await tryTap(page, '#loopBtn');
    await page.evaluate(() => audioEl.pause());
    await tryTap(page, '#speedChip');
    const sp = await page.evaluate(() => ({ rate: audioEl.playbackRate, text: document.getElementById('speedChip')?.textContent }));
    check(`${T} player: speed chip cycles 1.0× → 1.2×`, sp.rate === 1.2 && sp.text === '1.2×', sp);
    await page.evaluate(() => setSpeed(1));

    // 跟随播放：自己翻走了不拽回来，出现「回到当前句」，点了回去
    await page.evaluate(() => { const s = state.currentData.segments[1]; audioEl.currentTime = s.start; state.follow = true; audioEl.play(); });
    await sleep(800);
    await page.mouse.move(W / 2, H / 2);
    await page.mouse.wheel(0, 1400);
    await sleep(500);
    const y0 = await page.evaluate(() => scrollY);
    await page.evaluate(() => { const s = state.currentData.segments[2]; audioEl.currentTime = s.start + 0.05; });   // 换下一句
    await sleep(1500);
    const fy = await page.evaluate(() => ({ y: scrollY, seg: state.activeSegmentId, pill: !!document.getElementById('followPill') && !document.getElementById('followPill').hidden }));
    check(`${T} follow: scrolling away stops the auto-scroll (no yank on the next sentence)`, fy.seg === 2 && Math.abs(fy.y - y0) < 5, { y0, fy });
    check(`${T} follow: 「回到当前句」 pill appears`, fy.pill, fy);
    if (theme === 'light') await shot(page, 'follow-pill');
    await tryTap(page, '#followPill');
    await sleep(900);
    const back = await page.evaluate(() => { const l = document.querySelector('.lr-line.is-active').getBoundingClientRect(); return { top: Math.round(l.top), bottom: Math.round(l.bottom), vh: innerHeight, pill: document.getElementById('followPill').hidden, follow: state.follow }; });
    check(`${T} follow: tapping the pill brings the current line back and resumes following`, back.pill && back.follow && back.top > 100 && back.bottom < back.vh - 100, back);
    await page.evaluate(() => audioEl.pause());

    // 选词：停在播放条上面的一条；释义面板从底部升起，键盘高 470 时输入框和保存都看得见
    await page.evaluate(() => {
      const el = document.querySelector('.line-text[data-seg-id="5"]');
      el.scrollIntoView({ block: 'center' });
      state.lastPointer = 'touch';
      const n = el.firstChild; const i = n.textContent.indexOf('guests');
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 6);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    });
    await sleep(900);
    const tb = await page.evaluate(() => { const t = document.getElementById('selectionToolbar'); const p = document.getElementById('lrPlayer').getBoundingClientRect(); const r = t.getBoundingClientRect(); const b = [...t.querySelectorAll('.lr-pop__btn')].filter(x => x.getBoundingClientRect().width > 0).map(x => Math.round(x.getBoundingClientRect().height)); return { shown: !t.hidden, bottom: Math.round(r.bottom), playerTop: Math.round(p.top), l: Math.round(r.left), r: Math.round(r.right), quote: (document.getElementById('selQuote') || {}).textContent, b }; });
    check(`${T} select: 释义 / 笔记 bar docks right above the player, with the word, 44px buttons`, tb.shown && tb.bottom <= tb.playerTop && tb.playerTop - tb.bottom <= 16 && tb.l >= 0 && tb.r <= W && tb.quote === 'guests' && tb.b.length >= 3 && tb.b.every(h => h >= 44), tb);
    if (theme === 'light') await shot(page, 'select-bar');
    await tryTap(page, '#selVocabBtn');
    await page.setViewportSize({ width: W, height: 470 });
    await sleep(400);
    const vs = await page.evaluate(() => { const p = document.getElementById('vocabPopover').getBoundingClientRect(); const i = document.getElementById('vpInput').getBoundingClientRect(); const s = document.querySelector('#vpAddMode .ui-btn--primary').getBoundingClientRect(); return { pl: Math.round(p.left), pr: Math.round(p.right), pb: Math.round(p.bottom), it: Math.round(i.top), ib: Math.round(i.bottom), sb: Math.round(s.bottom), sh: Math.round(s.height), vh: innerHeight, fs: parseFloat(getComputedStyle(document.getElementById('vpInput')).fontSize), focus: document.activeElement.id, scrim: !document.getElementById('panelScrim')?.hidden }; });
    check(`${T} vocab: sheet spans the bottom, input + 保存 visible with the keyboard up (470px)`, vs.pl === 0 && vs.pr === W && vs.pb <= vs.vh && vs.it >= 0 && vs.sb <= vs.vh && vs.sh >= 44 && vs.focus === 'vpInput' && vs.scrim, vs);
    check(`${T} vocab: meaning field is 16px`, vs.fs >= 16, vs.fs);
    if (theme === 'light') await shot(page, 'vocab-sheet-kbd');
    await page.fill('#vpInput', '客人');
    await tryTap(page, '#vpAddMode .ui-btn--primary');
    const saved = await page.waitForFunction(() => [...document.querySelectorAll('.ielts-toast')].some(t => /生词已保存/.test(t.textContent)), null, { timeout: 3000 }).then(() => true).catch(() => false);
    await page.setViewportSize({ width: W, height: H });
    await sleep(300);
    const toast = await page.evaluate(() => { const t = [...document.querySelectorAll('.ielts-toast')].pop(); const p = document.getElementById('lrPlayer').getBoundingClientRect(); return t ? { tb: Math.round(t.getBoundingClientRect().bottom), pt: Math.round(p.top) } : null; });
    check(`${T} vocab: saved; the toast floats above the player`, saved && toast && toast.tb <= toast.pt, { saved, toast });
    await page.evaluate(async (pid) => { const a = state.currentData.vocab_annotations.find(x => x.word === 'guests'); if (a) await API.del(`/api/listening_review/project/${pid}/vocab/${a.id}`); }, HALL);
    // 整句笔记：编辑面板，键盘高 470 时保存还在
    await page.evaluate(() => { const s = state.currentData.segments[5]; seekToSegment(s.id); audioEl.pause(); });
    await sleep(300);
    await tryTap(page, '.lr-line.is-active .lr-act[data-act="snote"]');
    await page.setViewportSize({ width: W, height: 470 });
    await sleep(400);
    const ns = await page.evaluate(() => { const p = document.getElementById('notePopover'); if (p.hidden) return null; const i = document.getElementById('npInput').getBoundingClientRect(); const s = document.querySelector('#npEditMode .ui-btn--primary').getBoundingClientRect(); return { quote: document.getElementById('npQuote').textContent, it: Math.round(i.top), sb: Math.round(s.bottom), vh: innerHeight, hint: getComputedStyle(document.querySelector('#npEditMode .lr-meta')).display }; });
    check(`${T} note: ✎ 笔记 opens the sentence note sheet; textarea + 保存 visible at 470px, no ⌘ hint`, ns && /How many guests/.test(ns.quote) && ns.it >= 0 && ns.sb <= ns.vh && ns.hint === 'none', ns);
    if (theme === 'light') await shot(page, 'note-sheet-kbd');
    await page.goBack().catch(() => {});
    await sleep(400);
    const nb = await page.evaluate(() => ({ closed: document.getElementById('notePopover').hidden, detail: state.view === 'detail' }));
    check(`${T} note: back closes the sheet first`, nb.closed && nb.detail, nb);
    await page.evaluate(() => hideNotePopover());
    await page.setViewportSize({ width: W, height: H });

    // 本篇页签：打卡 / 标熟；字幕最后也有
    await tryTap(page, '.ptab-btn[data-ptab="side"]');
    await sleep(300);
    const side = await page.evaluate(() => { const c = document.getElementById('checkinBtn').getBoundingClientRect(); const m = document.getElementById('masteredBtn').getBoundingClientRect(); return { c: Math.round(c.height), m: Math.round(m.height), script: document.getElementById('lyricsContainer').getBoundingClientRect().height, notes: document.querySelectorAll('#notesViewBody .lr-entry').length }; });
    check(`${T} 本篇 tab: 打卡 / 标熟 48px, notes listed, transcript hidden`, side.c >= 48 && side.m >= 48 && side.script === 0 && side.notes > 0, side);
    if (theme === 'light') await shot(page, 'side-tab');
    await tryTap(page, '.ptab-btn[data-ptab="script"]');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await sleep(400);
    const end = await page.evaluate(() => { const c = document.querySelector('.lr-endcard'); const p = document.getElementById('lrPlayer').getBoundingClientRect(); const lines = document.querySelectorAll('.lr-line'); const last = lines[lines.length - 1].getBoundingClientRect(); return c ? { shown: c.getBoundingClientRect().height > 0, cb: Math.round(c.getBoundingClientRect().bottom), pt: Math.round(p.top), lb: Math.round(last.bottom), n: c.querySelector('.js-checkin-n').textContent } : null; });
    check(`${T} end: 听完了 card with 打卡 / 标熟 after the last line; nothing hidden under the player`, end && end.shown && end.cb <= end.pt && end.lb <= end.pt, end);
    if (theme === 'light') {
      await tryTap(page, '.lr-endcard [data-act="end-checkin"]');
      await page.waitForFunction((n) => document.querySelector('.lr-endcard .js-checkin-n').textContent === String(+n + 1), end && end.n, { timeout: 3000 }).catch(() => {});
      const n2 = await page.evaluate(() => document.querySelector('.lr-endcard .js-checkin-n').textContent);
      check('end: 打卡 from the end card counts up', end && +n2 === +end.n + 1, { before: end && end.n, after: n2 });
    }

    // 返回键：精听页 → 列表；刷新还在这篇
    if (theme === 'light') {
      await page.reload();
      await page.waitForFunction(() => typeof state !== 'undefined' && state.view === 'detail', null, { timeout: 5000 }).catch(() => {});
      const rl = await page.evaluate(() => ({ view: state.view, pid: state.currentProject && state.currentProject.id }));
      check('history: refreshing keeps you in the article', rl.view === 'detail' && rl.pid === HALL, rl);
      await page.goBack().catch(() => {});
      await sleep(600);
      const bl = await page.evaluate(() => ({ view: typeof state !== 'undefined' && state.view, path: location.pathname, search: location.search }));
      check('history: back from the article goes to the project list', bl.view === 'list' && bl.path === '/listening_review' && !bl.search, bl);
    }

    });

    // ================= 导入的篇：题目页签、题号 ↔ 出处 =================
    await section(`${T} exam`, async () => {
    await openByTitle(page, /Riverside Bike Hire/);
    await page.evaluate(() => setMode('answers'));
    const et = await page.$$eval('.ptab-btn', els => els.filter(e => !e.hidden).map(e => e.innerText.replace(/\s+/g, '')));
    check(`${T} exam: tabs 原文 | 题目 5 | 本篇`, et.length === 3 && et[1] === '题目5', et);
    await page.evaluate(() => window.scrollTo(0, 0));
    await tryTap(page, '.lr-qtag[data-q="3"]');
    await sleep(700);
    const qt = await page.evaluate(() => { const x = document.querySelector('#questionsPane .lr-qx'); const r = x && x.getBoundingClientRect(); return { tab: state.ptab, selQ: state.selQ, qx: r ? { t: Math.round(r.top), b: Math.round(r.bottom) } : null, vh: innerHeight }; });
    check(`${T} exam: tapping Q3 in the transcript opens 题目 with its explanation on screen`, qt.tab === 'questions' && qt.selQ === '3' && qt.qx && qt.qx.t >= 100 && qt.qx.t < qt.vh - 150, qt);
    const qh = await page.evaluate(() => { const s = document.getElementById('modeSeg'); const r = s.getBoundingClientRect(); const b = s.querySelector('.ui-seg__btn').getBoundingClientRect(); return { inQ: !!s.closest('#pQHead'), w: Math.round(r.width), h: Math.round(b.height) }; });
    check(`${T} exam: 显示答案 / 重做 sits at the top of 题目, full width, 44px`, qh.inQ && qh.w >= W - 40 && qh.h >= 44, qh);
    if (theme === 'light') await shot(page, 'exam-questions');
    await tryTap(page, '#questionsPane [data-act="q-script"]');
    await sleep(900);
    const ev = await page.evaluate(() => { const b = document.querySelector('#lyricsContainer .lr-evi'); const c = document.getElementById('qChip'); const r = b && b.getBoundingClientRect(); const cr = c.getBoundingClientRect(); return { tab: state.ptab, band: r ? { t: Math.round(r.top), b: Math.round(r.bottom) } : null, chip: !c.hidden && cr.height > 0, chipB: Math.round(cr.bottom), chipText: c.innerText.replace(/\s+/g, ' '), vh: innerHeight }; });
    check(`${T} exam: 看原文出处 switches to 原文 with the evidence on screen and the question pinned`, ev.tab === 'script' && ev.band && ev.band.t >= ev.chipB && ev.band.t < ev.vh - 200 && ev.chip && /3/.test(ev.chipText) && /mill/.test(ev.chipText), ev);
    if (theme === 'light') await shot(page, 'exam-evidence');
    await tryTap(page, '#qChip [data-act="chip-play"]');
    await sleep(500);
    const pe = await page.evaluate(() => ({ tab: state.ptab, playing: !audioEl.paused, until: state.playUntil }));
    check(`${T} exam: ▶ 出处 plays the range without leaving 原文`, pe.tab === 'script' && pe.playing && pe.until !== null, pe);
    await page.evaluate(() => audioEl.pause());
    const qtagHit = await page.evaluate(() => { const t = document.querySelector('.lr-qtag'); const cs = getComputedStyle(t, '::before'); const r = t.getBoundingClientRect(); return { h: Math.round(r.height - parseFloat(cs.top) - parseFloat(cs.bottom)) }; });
    check(`${T} exam: Q tags have a ≥44px tap area`, qtagHit.h >= 44, qtagHit);

    });

    // ================= 重做 =================
    await section(`${T} redo`, async () => {
    await openByTitle(page, /Riverside Bike Hire/);
    await page.evaluate(() => localStorage.setItem('listening-redo-script', '0'));
    await page.evaluate(() => { state.showScript = false; setMode('redo'); });
    await sleep(400);
    const rd = await page.evaluate(() => { const g = [...document.querySelectorAll('#paperQs .lq-gap__in')]; const box = g[0] && g[0].closest('.lq-gap').getBoundingClientRect(); return { tab: state.ptab, side: document.getElementById('ptabSideName').textContent, paper: document.getElementById('paperPane').getBoundingClientRect().height > 0, fs: g[0] && parseFloat(getComputedStyle(g[0]).fontSize), h: box && Math.round(box.height), hints: g.map(i => i.getAttribute('enterkeyhint')).join(',') }; });
    check(`${T} redo: opens 题目 with the paper; third tab becomes 答题卡`, rd.tab === 'questions' && rd.paper && rd.side === '答题卡', rd);
    check(`${T} redo: blanks are 40px tall, 16px text, keyboard says 下一项 / 完成`, rd.fs >= 16 && rd.h >= 40 && rd.hints === 'next,next,next,done', rd);
    await page.evaluate(() => window.scrollTo(0, 500));
    await sleep(300);
    const strip = await page.evaluate(() => { const b = document.querySelector('.lr-paper__bar'); const t = document.getElementById('ptabs').getBoundingClientRect(); const r = b.getBoundingClientRect(); const s = document.querySelector('.lr-paper__submit').getBoundingClientRect(); const c = document.querySelector('.lr-paper__card'); return { gap: Math.round(r.top - t.bottom), submit: s.height > 0, card: !!c && c.getBoundingClientRect().height > 0, prog: document.getElementById('paperProg').textContent }; });
    check(`${T} redo: 已答 · 用时 · 答题卡 · 交卷 strip sticks under the tabs while scrolling`, Math.abs(strip.gap) <= 1 && strip.submit && strip.card && /已答 0\/5/.test(strip.prog), strip);
    if (theme === 'light') await shot(page, 'redo-paper');
    await page.evaluate(() => window.scrollTo(0, 0));
    await tryTap(page, '#paperQs .lq-gap__in[data-q="3"]');
    await page.setViewportSize({ width: W, height: 470 });
    await sleep(300);
    await page.evaluate(() => document.activeElement.scrollIntoView({ block: 'nearest' }));
    await sleep(300);
    const ty = await page.evaluate(() => { const i = document.activeElement; const r = i.getBoundingClientRect(); const top = document.querySelector('.lr-paper__bar').getBoundingClientRect().bottom; const p = document.getElementById('lrPlayer'); return { q: i.dataset.q, t: Math.round(r.top), b: Math.round(r.bottom), top: Math.round(top), vh: innerHeight, player: getComputedStyle(p).display }; });
    check(`${T} redo: typing with the keyboard up (470px) keeps the blank visible, player tucked away`, ty.q === '3' && ty.t >= ty.top - 1 && ty.b <= ty.vh && ty.player === 'none', ty);
    if (theme === 'light') await shot(page, 'redo-typing-kbd');
    await page.keyboard.type('mill');
    await page.evaluate(() => document.activeElement.blur());
    await page.setViewportSize({ width: W, height: H });
    await sleep(200);
    await tryTap(page, '.lr-paper__card');
    await sleep(300);
    const card = await page.evaluate(() => { const m = [...document.querySelectorAll('#redoMap .lr-qnum')]; return { tab: state.ptab, n: m.length, h: m.map(b => Math.round(b.getBoundingClientRect().height)), done: document.getElementById('redoDone').textContent }; });
    check(`${T} redo: 答题卡 shows progress and 44px question numbers`, card.tab === 'side' && card.n === 5 && card.h.every(h => h >= 44) && card.done === '1', card);
    if (theme === 'light') await shot(page, 'redo-card');
    await tryTap(page, '#redoMap .lr-qnum[data-q="5"]');
    await sleep(500);
    const jump = await page.evaluate(() => ({ tab: state.ptab, focus: document.activeElement && (document.activeElement.dataset.unit || document.activeElement.dataset.q || document.activeElement.className) }));
    check(`${T} redo: a number on the 答题卡 jumps to that question in 题目`, jump.tab === 'questions', jump);
    await tryTap(page, '.ptab-btn[data-ptab="script"]');
    await sleep(300);
    const hid = await page.evaluate(() => { const s = document.getElementById('scriptHidden'); return s && !s.hidden && s.getBoundingClientRect().height > 0 && /原文已隐藏/.test(s.textContent); });
    check(`${T} redo: 原文 tab says the transcript is hidden, with a 显示原文 button`, hid, hid);
    await tryTap(page, '#ptabs .lr-ptabs__btn[aria-label="更多"]');
    await sleep(300);
    const more = await page.evaluate(() => { const m = document.getElementById('moreSheet'); const s = document.getElementById('moreScript'); return { open: !m.hidden, script: !s.hidden && s.getAttribute('aria-checked') }; });
    check(`${T} more: ⋯ sheet has 跟随播放 and (in 重做) 显示原文`, more.open && more.script === 'false', more);
    await tryTap(page, '#moreScript');
    await sleep(300);
    const shownScript = await page.evaluate(() => ({ lyrics: document.getElementById('lyricsContainer').getBoundingClientRect().height > 0, aria: document.getElementById('moreScript').getAttribute('aria-checked') }));
    check(`${T} more: 显示原文 brings the transcript back`, shownScript.lyrics && shownScript.aria === 'true', shownScript);
    await page.evaluate(() => { closeMoreSheet(); toggleScript(false); setMode('answers'); });

    });

    // 字母槽：手机是底部面板；返回键先关它
    await section(`${T} slot + map`, async () => {
    await openByTitle(page, /^Part 2$/);
    await page.evaluate(() => setMode('redo'));
    await sleep(300);
    const slotH = await page.evaluate(() => Math.round(document.querySelector('#paperQs .lq-slot[data-slot="12"]').getBoundingClientRect().height));
    check(`${T} slot: letter slots are 40px tall`, slotH >= 40, slotH);
    await tryTap(page, '#paperQs .lq-slot[data-slot="12"]');
    await sleep(300);
    const sm = await page.evaluate(() => { const m = document.querySelector('.lq-menu'); return m ? { sheet: m.classList.contains('is-sheet'), b: Math.round(m.getBoundingClientRect().bottom) } : null; });
    check(`${T} slot: the option menu is a bottom sheet`, sm && sm.sheet && Math.abs(sm.b - H) <= 1, sm);
    await page.goBack().catch(() => {});
    await sleep(400);
    const sb2 = await page.evaluate(() => ({ menu: !!document.querySelector('.lq-menu'), detail: state.view === 'detail' }));
    check(`${T} slot: back closes the letter sheet first`, !sb2.menu && sb2.detail, sb2);
    await page.evaluate(() => setMode('answers'));

    // 地图题：答题纸表格放得下、圈够大
    await openByTitle(page, /Greenfield Library Tour/);
    await page.evaluate(() => setMode('redo'));
    await sleep(300);
    const grid = await page.evaluate(() => { const g = document.querySelector('#paperQs .lq-grid'); const c = [...g.querySelectorAll('.lq-cell')]; return { scroll: g.scrollWidth - g.clientWidth, cell: Math.round(c[0].getBoundingClientRect().width), page: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth }; });
    check(`${T} map: answer grid fits the phone (no sideways scroll), 32px circles`, grid.scroll <= 0 && grid.page <= 0 && grid.cell >= 32, grid);
    if (theme === 'light') await shot(page, 'map-redo');
    await page.evaluate(() => setMode('answers'));
    check(`${T} detail screens: no horizontal overflow at the end`, await overflow(page) <= 0, await overflow(page));

    });

    // ================= 听力笔记本 =================
    await section(`${T} notebook`, async () => {
    await page.goto(`${BASE}/listening_review/notes`);
    await page.waitForSelector('.np-card');
    await sleep(300);
    check(`${T} notebook: no horizontal overflow`, await overflow(page) <= 0, await overflow(page));
    const fb = await page.evaluate(() => { const f = document.getElementById('nbFilters'); if (!f) return null; const kids = [f.querySelector('#articleSelect'), ...f.querySelectorAll('.filter-chip'), f.querySelector('#searchToggle')].filter(Boolean).map(e => e.getBoundingClientRect()); return { n: kids.length, tops: [...new Set(kids.map(r => Math.round(r.top)))].length, hs: kids.map(r => Math.round(r.height)), rmax: Math.round(Math.max(...kids.map(r => r.right))) }; });
    check(`${T} notebook: 文章 / 类型 / 搜索 in one 44px row`, fb && fb.n === 5 && fb.tops === 1 && fb.hs.every(h => h >= 44) && fb.rmax <= W, fb);
    await page.evaluate(() => window.scrollTo(0, 600));
    await sleep(200);
    const nst = await page.evaluate(() => { const f = document.getElementById('nbFilters'); const n = document.querySelector('.app-shell-nav'); return f ? Math.round(f.getBoundingClientRect().top - n.getBoundingClientRect().bottom) : null; });
    check(`${T} notebook: the filter row sticks under the nav`, nst !== null && Math.abs(nst) <= 1, nst);
    const play = await page.evaluate(() => Math.round(document.querySelector('.lr-card__play').getBoundingClientRect().height));
    check(`${T} notebook: ▶ play pill ≥40px`, play >= 40, play);
    if (theme === 'light') {
      await page.evaluate(() => window.scrollTo(0, 0));
      await shot(page, 'notebook');
      await tryTap(page, '#searchToggle');
      await page.setViewportSize({ width: W, height: 470 });
      await page.keyboard.type('deposit');
      await sleep(500);
      const se = await page.evaluate(() => { const i = document.getElementById('searchInput'); const r = i.getBoundingClientRect(); return { focus: document.activeElement === i, t: Math.round(r.top), b: Math.round(r.bottom), fs: parseFloat(getComputedStyle(i).fontSize), cards: document.querySelectorAll('.np-card').length, cancel: (document.getElementById('searchCancel') || { getBoundingClientRect: () => ({ width: 0 }) }).getBoundingClientRect().width > 0 }; });
      check('notebook: 🔍 opens a 16px search field with 取消, visible with the keyboard up', se.focus && se.t >= 0 && se.b <= 470 && se.fs >= 16 && se.cancel && se.cards === 1, se);
      await tryTap(page, '#searchCancel');
      await page.setViewportSize({ width: W, height: H });
      await sleep(300);
    }
    await tryTap(page, '#modeReviewBtn');
    await sleep(500);
    await page.evaluate(() => audio.pause());
    const rv = await page.evaluate(() => { const nav = document.querySelector('.lr-review__nav'); const b = [...nav.querySelectorAll('.ui-btn')].map(x => { const r = x.getBoundingClientRect(); return { t: x.innerText.trim(), h: Math.round(r.height), b: Math.round(r.bottom), l: Math.round(r.left), r: Math.round(r.right) }; }); const f = document.getElementById('nbFilters'); return { b, vh: innerHeight, filters: f ? getComputedStyle(f).display : 'none', sum: !!document.querySelector('.lr-review__sum') && document.querySelector('.lr-review__sum').getBoundingClientRect().height > 0 }; });
    check(`${T} review: filters fold into one summary row`, rv.filters === 'none' && rv.sum, rv);
    check(`${T} review: 上一张 / 翻面 / 下一张 sit at the bottom of the screen, 48px`, rv.b.length === 3 && /翻面/.test(rv.b[1].t) && rv.b.every(x => x.h >= 48 && x.b <= rv.vh && x.b >= rv.vh - 90 && x.l >= 0 && x.r <= W), rv);
    if (theme === 'light') await shot(page, 'review');
    await tryTap(page, '#flashCard .lr-flash__en');
    await sleep(300);
    const flip = await page.evaluate(() => ({ revealed: state.revealed, mid: document.querySelectorAll('.lr-review__nav .ui-btn')[1]?.innerText.trim() }));
    check(`${T} review: tapping the card flips it; the middle button becomes 记住了`, flip.revealed && /记住了/.test(flip.mid || ''), flip);
    // 左滑下一张、右滑上一张。WebKit 造不出真的 TouchEvent，就发一个带 touches 的普通事件，测的是页面的滑动处理
    const swipe = (dir) => page.evaluate((dir) => {
      const card = document.getElementById('flashCard');
      const r = card.getBoundingClientRect(), y = r.top + 40;
      const a = { clientX: dir < 0 ? r.right - 30 : r.left + 30, clientY: y }, b = { clientX: dir < 0 ? r.left + 30 : r.right - 30, clientY: y + 4 };
      const ev = (type, touches, changed) => { const e = new Event(type, { bubbles: true }); Object.defineProperty(e, 'touches', { value: touches }); Object.defineProperty(e, 'changedTouches', { value: changed }); return e; };
      const before = state.idx;
      card.dispatchEvent(ev('touchstart', [a], [a]));
      card.dispatchEvent(ev('touchend', [], [b]));
      return state.idx - before;
    }, dir);
    const sl = await swipe(-1);
    const sr = await swipe(1);
    check(`${T} review: swipe left = next card, swipe right = previous`, sl === 1 && sr === -1, { sl, sr });
    await page.evaluate(() => audio.pause());
    if (theme === 'light') {
      await tryTap(page, '.lr-review__sum .ui-btn');
      await sleep(300);
      const fs2 = await page.evaluate(() => { const f = document.getElementById('nbFilters'); const r = f.getBoundingClientRect(); return { sheet: f.classList.contains('is-sheet'), b: Math.round(r.bottom), shown: r.height > 0 }; });
      check('review: 筛选 opens the filters as a bottom sheet', fs2.sheet && fs2.shown && Math.abs(fs2.b - H) <= 1, fs2);
      await shot(page, 'review-filter');
      await page.goBack().catch(() => {});
      await sleep(400);
      const fb2 = await page.evaluate(() => ({ sheet: document.getElementById('nbFilters').classList.contains('is-sheet'), mode: state.mode }));
      check('review: back closes the filter sheet, still reviewing', !fb2.sheet && fb2.mode === 'review', fb2);
      await page.goBack().catch(() => {});
      await sleep(400);
      const fb3 = await page.evaluate(() => ({ mode: typeof state !== 'undefined' && state.mode, path: location.pathname }));
      check('review: back again leaves review for browse (stays on the notebook)', fb3.mode === 'browse' && fb3.path === '/listening_review/notes', fb3);
    }
    });
    await ctx.close();
  }

  console.log(`${engine}: ${pass}/${pass + fail} passed${skip ? `, ${skip} skipped` : ''}`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });

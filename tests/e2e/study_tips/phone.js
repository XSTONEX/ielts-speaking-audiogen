// 学习技巧页的手机测试：webkit 用 390×844（iPhone），chromium 用 360×780 + isMobile（安卓），亮色和暗色。
// 查：不横向溢出、底部操作条和 ⋯ 菜单够大、点标题不弹键盘、排序开关、吸顶的科目 / 类型、底栏不挡最后一张卡、
// 改名 / 编辑 / 删除走 ⋯ 面板、返回键先关面板、全屏复习只读、导入面板、技巧详情的目录面板和跳转、
// 键盘弹出（视口 470 高）时编辑器和词组弹窗的保存按钮还在屏幕里。
// 用法：node phone.js chromium|webkit（环境变量见 README.md）。全部通过退出码为 0。截图写到 STUDY_TIPS_OUT/<引擎>-phone/。
const fs = require('fs');
const path = require('path');
const { pw, BASE, OUT, ENGINE, token, checkCdn, resetFixtures, readData } = require('./common');
const TOKEN = token();
const SHOTS = path.join(OUT, ENGINE + '-phone');
fs.mkdirSync(SHOTS, { recursive: true });

const DEVICE = ENGINE === 'webkit'
  ? { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 }
  : { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 };
const W = DEVICE.viewport.width, H = DEVICE.viewport.height, KB_H = 470;

const results = [];
function check(name, cond, detail) {
  results.push({ name, ok: !!cond, detail });
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail !== undefined && !cond ? '  -> ' + JSON.stringify(detail) : ''));
}
// 一段流程出错（比如旧版页面上根本没有这个按钮）只记一条 FAIL，接着跑下一段
async function step(name, fn) {
  try { await fn(); } catch (e) { check(name + ' (step crashed)', false, String(e.message || e).split('\n')[0]); }
}

async function newPage(browser, theme) {
  const ctx = await browser.newContext(Object.assign({ colorScheme: theme }, DEVICE));
  await ctx.addInitScript(([t, th]) => {
    if (location.protocol === 'about:') return;
    localStorage.setItem('authToken', t);
    localStorage.setItem('currentUser', JSON.stringify({ username: 'demo', display_name: '测试同学', avatar: 'avatar_teacher.svg' }));
    localStorage.setItem('ui-theme', th);
  }, [TOKEN, theme]);
  const page = await ctx.newPage();
  page._errors = [];
  page.on('pageerror', e => page._errors.push(e.message));
  page.on('dialog', d => { if (d.type() === 'beforeunload') d.accept(); else { page._errors.push('native dialog ' + d.message()); d.dismiss(); } });
  return { ctx, page };
}

const settle = (page, ms) => page.waitForTimeout(ms || 350);
const rect = (page, sel) => page.evaluate(s => {
  const el = document.querySelector(s);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height, visible: r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' };
}, sel);
const visible = async (page, sel) => { const r = await rect(page, sel); return !!(r && r.visible); };
// 模拟返回键 / 右滑返回。推迟一拍再退：退出页面时 evaluate 本身别跟着报「上下文没了」
const back = async (page) => { await page.evaluate(() => { setTimeout(() => history.back(), 0); }); await settle(page, 500); };
const hash = (page) => page.evaluate(() => location.hash);
// 横向溢出：整页 scrollWidth 和每个可见元素（自己能横向滚的容器里面的不算）
const overflow = (page) => page.evaluate(() => {
  const vw = document.documentElement.clientWidth;
  const bad = [];
  document.querySelectorAll('body *').forEach(el => {
    if (el.closest('[hidden]') || el.closest('.app-shell-panel') || el.closest('.app-shell-scrim')) return;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') return;
    const b = el.getBoundingClientRect();
    if (b.width === 0 && b.height === 0) return;
    let p = el.parentElement, scroller = false;
    while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { scroller = true; break; } p = p.parentElement; }
    if (!scroller && (b.right > vw + 1 || b.left < -1)) bad.push(el.tagName.toLowerCase() + '.' + [...el.classList].join('.') + ' ' + Math.round(b.left) + '..' + Math.round(b.right));
  });
  return { sw: document.documentElement.scrollWidth, vw, bad: bad.slice(0, 4) };
});
async function noOverflow(page, label) {
  const r = await overflow(page);
  check(label + ' no horizontal overflow', r.sw <= r.vw && !r.bad.length, r);
}
const shot = (page, name) => page.screenshot({ path: path.join(SHOTS, name + '.png') });
const openList = async (page, h) => {
  await page.goto('about:blank');
  await page.goto(BASE + '/study_techniques' + h);
  await page.waitForSelector('#listBody .st-group, #listBody .st-doc, #listBody .ui-empty__title');
  await settle(page, 500);
};
// 卡片右上角的 ⋯ → 面板里的某一项
const cardMenu = async (page, id, act) => {
  await page.tap(`#listBody [data-id="${id}"] [data-action="more"]`);
  await settle(page, 350);
  if (act) { await page.tap(`#actList [data-act="${act}"]`); await settle(page, 600); }
};
const toastOverBar = (page) => page.evaluate(() => {
  const bar = document.querySelector('#listTools');
  const ts = [...document.querySelectorAll('.ielts-toast')].map(t => t.getBoundingClientRect());
  if (!bar || !ts.length) return { toasts: ts.length };
  const b = bar.getBoundingClientRect();
  return { toasts: ts.length, overlap: ts.some(t => t.bottom > b.top + 1 && t.top < b.bottom), barTop: b.top, toastBottoms: ts.map(t => Math.round(t.bottom)) };
});

async function lightRun(browser) {
  const { ctx, page } = await newPage(browser, 'light');
  const syn = () => readData('reading_synonyms');

  // ---------- 列表 ----------
  await step('L list', async () => {
    await openList(page, '#reading/synonyms');
    await shot(page, '01-list');
    await noOverflow(page, 'L0 list');
    const bar = await rect(page, '#listTools');
    check('L1 action bar pinned to the bottom', bar && bar.visible && Math.abs(bar.bottom - H) <= 1 && bar.left <= 0 && bar.right >= W - 1, bar);
    const btns = await page.$$eval('#listTools .ui-btn', els => els.map(e => { const r = e.getBoundingClientRect(); return { h: r.height, w: r.width, text: e.innerText.trim(), fits: e.scrollWidth <= e.clientWidth + 1 }; }));
    check('L2 bar buttons 复习 / 导入 / 新建一组, ≥44px, text fits', btns.length === 3 && btns.every(b => b.h >= 44 && b.fits) && btns.map(b => b.text).join('|') === '复习|导入|新建一组', btns);
    const first = await rect(page, '#listBody .st-group');
    check('L3 first card starts on the first screen (≤ 340px)', first && first.top <= 340, first && first.top);
    const id0 = await page.getAttribute('#listBody .st-group', 'data-id');
    const more = await rect(page, `#listBody [data-id="${id0}"] [data-action="more"]`);
    check('L4 ⋯ button ≥ 44×44', more && more.visible && more.width >= 44 && more.height >= 44, more);
    check('L5 edit / delete text buttons hidden on the card', !(await visible(page, `#listBody [data-id="${id0}"] .st-act`)));
    const en = await page.$eval('#listBody .st-word__en', e => parseFloat(getComputedStyle(e).fontSize));
    check('L6 English words ≥ 16px', en >= 16, en);
    const tabs = await page.$$eval('#rail .ui-rail__item, #typeSeg .ui-seg__btn', els => els.map(e => Math.round(e.getBoundingClientRect().height)));
    check('L7 subject tabs and type switch ≥ 40px', tabs.length === 7 && tabs.every(h => h >= 40), tabs);
    // 点标题：不能进入改名、不能弹键盘
    await page.tap(`#listBody [data-id="${id0}"] .st-group__title`);
    await settle(page);
    const t = await page.evaluate(id => { const el = document.querySelector(`#listBody [data-id="${id}"] .st-group__title`); return { ce: el.getAttribute('contenteditable'), focused: document.activeElement === el || document.activeElement.isContentEditable }; }, id0);
    check('L8 tapping a title does not start rename', t.ce === null && !t.focused, t);
  });

  await step('S sort', async () => {
    await openList(page, '#reading/synonyms');
    const chips = await page.$$eval('#listSort .ui-chip', els => els.filter(e => e.getBoundingClientRect().width > 0).map(e => e.textContent.trim()));
    check('S1 one sort toggle visible', chips.length === 1 && chips[0] === '最新在前', chips);
    const oldest = [...syn()].sort((a, b) => a.created_at.localeCompare(b.created_at))[0];
    await page.tap('#listSort .ui-chip.is-on');
    await settle(page);
    check('S2 tapping it flips to 最早在前', (await page.textContent('#listSort .ui-chip.is-on')).trim() === '最早在前' && (await page.getAttribute('#listBody .st-group', 'data-id')) === oldest.id);
    await page.tap('#listSort .ui-chip.is-on');
    await settle(page);
    check('S3 and back to 最新在前', (await page.textContent('#listSort .ui-chip.is-on')).trim() === '最新在前');
  });

  await step('K sticky', async () => {
    await openList(page, '#reading/synonyms');
    await page.evaluate(() => window.scrollTo(0, 1400));
    await settle(page, 500);
    const shell = await rect(page, '.app-shell-nav');
    const segDown = await rect(page, '#typeSeg');
    check('K1 subject / type rows tuck under the nav while scrolling down', segDown && shell && segDown.bottom <= shell.bottom + 1, { seg: segDown && segDown.bottom, nav: shell && shell.bottom });
    await page.evaluate(() => window.scrollTo(0, 1200));
    await settle(page, 500);
    const rail = await rect(page, '#rail');
    const segUp = await rect(page, '#typeSeg');
    check('K2 they come back on scroll up, right under the nav', rail && segUp && Math.abs(rail.top - shell.bottom) <= 2 && segUp.top > rail.bottom - 2 && segUp.bottom < 260, { rail, segUp });
    await shot(page, '02-list-scrolled-up');
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await settle(page, 500);
    const last = await page.evaluate(() => { const c = [...document.querySelectorAll('#listBody .st-group')].pop(); return c.getBoundingClientRect().bottom; });
    const bar = await rect(page, '#listTools');
    check('K3 bottom bar does not cover the last card', last <= bar.top, { last, barTop: bar.top });
    await page.evaluate(() => window.scrollTo(0, 0));
    await settle(page, 400);
  });

  await step('M menu', async () => {
    await openList(page, '#reading/synonyms');
    const id = await page.getAttribute('#listBody .st-group', 'data-id');
    const h0 = await hash(page);
    await cardMenu(page, id);
    await shot(page, '03-card-menu');
    const sheet = await rect(page, '#actDlg .ui-dialog');
    check('M1 ⋯ opens a bottom sheet', sheet && sheet.visible && Math.abs(sheet.bottom - H) <= 2, sheet);
    const rows = await page.$$eval('#actList button', els => els.map(e => ({ t: e.textContent.trim(), h: e.getBoundingClientRect().height })));
    check('M2 sheet rows 编辑 / 改名 / 删除, ≥ 44px', rows.length === 3 && rows.every(r => r.h >= 44) && /编辑/.test(rows[0].t) && /改/.test(rows[1].t) && /删除/.test(rows[2].t), rows);
    await back(page);
    check('M3 back closes the sheet and stays on the page', (await page.isHidden('#actDlg')) && (await hash(page)) === h0 && page.url().includes('/study_techniques'), await hash(page));
    await cardMenu(page, id);
    await page.tap('#actDlg .ui-dialog__foot [data-action="dlg-close"]');
    await settle(page, 500);
    check('M4 取消 closes the sheet', await page.isHidden('#actDlg'));
    await back(page);
    check('M5 closing with 取消 leaves no extra history entry (back now leaves the list)', (await hash(page)) !== h0 || !page.url().includes('/study_techniques'), await hash(page));
  });

  await step('R rename', async () => {
    await openList(page, '#reading/synonyms');
    const id = await page.getAttribute('#listBody .st-group', 'data-id');
    const before = syn().find(g => g.id === id);
    await cardMenu(page, id, 'rename');
    await shot(page, '04-rename-sheet');
    check('R1 rename sheet with the current title', (await visible(page, '#renameInput')) && (await page.inputValue('#renameInput')) === before.title);
    const fs16 = await page.$eval('#renameInput', e => parseFloat(getComputedStyle(e).fontSize));
    check('R2 rename input ≥ 16px', fs16 >= 16, fs16);
    await page.fill('#renameInput', '手机上改的名字');
    await page.tap('#renameSave');
    await settle(page, 700);
    const after = syn().find(g => g.id === id);
    check('R3 rename saved, words kept', after.title === '手机上改的名字' && after.synonyms.length === before.synonyms.length && (await page.textContent(`#listBody [data-id="${id}"] .st-group__title`)) === '手机上改的名字', after);
    const tb = await toastOverBar(page);
    check('R4 toast floats above the bottom bar', tb.toasts > 0 && !tb.overlap, tb);
    await shot(page, '05-toast-above-bar');
    // ⋯ 面板 → 改名面板 → 保存：两层的历史记录都退干净了，再按返回就离开列表
    await back(page);
    check('R5 no history left behind after menu → rename → save', !page.url().includes('/study_techniques'), page.url());
  });

  await step('G group dialog', async () => {
    await openList(page, '#reading/synonyms');
    const id = await page.getAttribute('#listBody .st-group', 'data-id');
    await cardMenu(page, id, 'edit');
    check('G1 ⋯ → 编辑 opens the group sheet', await visible(page, '#groupDlg .ui-dialog'));
    const del = await rect(page, '#groupDlgBody .st-row__del');
    const add = await rect(page, '#groupDlgBody .st-add-row');
    check('G2 row delete ≥ 44×44, 加一行 ≥ 44 tall and full width', del && del.width >= 44 && del.height >= 44 && add && add.height >= 44 && add.width > W - 60, { del, add });
    await shot(page, '06-group-sheet');
    // 键盘弹出：视口只剩 470 高
    await page.setViewportSize({ width: W, height: KB_H });
    await page.tap('#groupDlgBody .st-row:nth-child(2) [data-field="word"]');
    await settle(page, 400);
    const save = await rect(page, '#groupDlgSave');
    const input = await page.evaluate(() => { const r = document.activeElement.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, tag: document.activeElement.tagName }; });
    check('G3 keyboard open: 保存 fully on screen', save && save.top >= 0 && save.bottom <= KB_H && save.height >= 44, save);
    check('G4 keyboard open: focused input on screen', input.tag === 'INPUT' && input.top >= 0 && input.bottom <= (save ? save.top : KB_H), input);
    await shot(page, '07-group-sheet-keyboard');
    await page.setViewportSize(DEVICE.viewport);
    await settle(page);
    await back(page);
    check('G5 back closes the unchanged sheet', await page.isHidden('#groupDlg'));
    await back(page);
    check('G6 and the next back leaves the list (no stale entries)', !page.url().includes('/study_techniques'), page.url());
  });

  await step('D delete', async () => {
    await openList(page, '#reading/synonyms');
    const id = await page.getAttribute('#listBody .st-group:nth-child(2)', 'data-id');
    await cardMenu(page, id, 'delete');
    check('D1 ⋯ → 删除 asks first', await visible(page, '#confirmDlg .ui-dialog'));
    await shot(page, '08-delete-confirm');
    await back(page);
    check('D2 back cancels the confirm, nothing deleted', (await page.isHidden('#confirmDlg')) && syn().some(g => g.id === id));
    await cardMenu(page, id, 'delete');
    await page.tap('#confirmOk');
    await settle(page, 700);
    check('D3 删除 deletes the group', !syn().some(g => g.id === id) && !(await page.$(`#listBody [data-id="${id}"]`)));
    const tb = await toastOverBar(page);
    check('D4 toast not over the bottom bar', tb.toasts > 0 && !tb.overlap, tb);
  });

  await step('F review', async () => {
    await openList(page, '#reading/synonyms');
    const h0 = await hash(page);
    await page.tap('#listTools [data-action="focus-open"]');
    await settle(page, 500);
    await shot(page, '09-review');
    check('F1 复习 opens full screen', await visible(page, '#focus'));
    const acts = await page.$$eval('#focusInner .st-more, #focusInner .st-act', els => els.filter(e => e.getBoundingClientRect().width > 0).length);
    check('F2 review is read-only (no ⋯ / 编辑 / 删除)', acts === 0, acts);
    const close = await rect(page, '#focusClose');
    check('F3 关闭 ≥ 44px', close && close.height >= 44, close);
    await noOverflow(page, 'F4 review');
    await back(page);
    check('F5 back closes review and stays on the list', (await page.isHidden('#focus')) && (await hash(page)) === h0);
    await page.tap('#listTools [data-action="focus-open"]');
    await settle(page, 400);
    await page.tap('#focusClose');
    await settle(page, 500);
    check('F6 关闭 closes review', await page.isHidden('#focus'));
  });

  await step('I import', async () => {
    await openList(page, '#reading/synonyms');
    await page.tap('#listTools [data-action="import-open"]');
    await settle(page, 400);
    check('I1 import hint does not mention dragging', !(await page.textContent('#importFileHint')).includes('拖'));
    check('I2 sample collapsed, 查看示例 shown', !(await visible(page, '#importSample')) && (await visible(page, '#importSampleToggle')));
    const pick = await rect(page, '#importPick');
    check('I3 选择文件 is a big button', pick && pick.height >= 44 && pick.width > W - 80, pick);
    await shot(page, '10-import');
    await page.tap('#importSampleToggle');
    await settle(page);
    const pre = await page.$eval('#importSample', e => ({ sw: e.scrollWidth, cw: e.clientWidth, sh: e.scrollHeight, ch: e.clientHeight }));
    check('I4 expanded sample wraps (no sideways or inner scroll)', (await visible(page, '#importSample')) && pre.sw <= pre.cw + 1 && pre.sh <= pre.ch + 1, pre);
    await page.setInputFiles('#importFile', { name: 'phone.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ groups: [{ title: '手机导入', synonyms: [{ word: 'mobile', definition: '手机' }] }] })) });
    await page.waitForSelector('#importStatus .st-check');
    await page.tap('#importRun');
    await page.waitForSelector('#importDlg', { state: 'hidden' });
    await settle(page, 400);
    check('I5 import works', syn().some(g => g.title === '手机导入'));
    const tb = await toastOverBar(page);
    check('I6 toast not over the bottom bar', tb.toasts > 0 && !tb.overlap, tb);
  });

  await step('E empty', async () => {
    await openList(page, '#speaking/hypernyms');
    check('E1 empty state text shown', (await page.textContent('#listBody')).includes('口语还没有上下义词'));
    const dup = await page.$$eval('#listBody .st-state__actions .ui-btn', els => els.filter(e => e.getBoundingClientRect().width > 0).length);
    check('E2 empty state does not repeat the bar buttons', dup === 0 && (await visible(page, '#listTools [data-action="group-new"]')), dup);
    await shot(page, '11-empty');
  });

  // ---------- 做题技巧：列表、详情、目录、编辑 ----------
  const longId = readData('writing_techniques').find(t => t.title === '大作文论证块').id;
  await step('T techniques list', async () => {
    await openList(page, '#writing/techniques');
    await shot(page, '12-techniques');
    const bar = await page.$$eval('#listTools .ui-btn', els => els.map(e => ({ t: e.textContent.trim(), h: e.getBoundingClientRect().height })));
    check('T1 techniques bar = 写一篇 (≥ 44px)', bar.length === 1 && bar[0].t === '写一篇' && bar[0].h >= 44, bar);
    const more = await rect(page, `#listBody [data-id="${longId}"] [data-action="more"]`);
    check('T2 doc card ⋯ ≥ 44×44', more && more.visible && more.width >= 44 && more.height >= 44, more);
    await cardMenu(page, longId);
    const rows = await page.$$eval('#actList button', els => els.map(e => e.textContent.trim()));
    check('T3 doc menu = 编辑 / 删除', rows.length === 2 && /编辑/.test(rows[0]) && /删除/.test(rows[1]), rows);
    await back(page);
    await noOverflow(page, 'T4 techniques');
  });

  await step('V reader', async () => {
    await page.tap(`#listBody [data-id="${longId}"] .st-doc__title a`);
    await page.waitForSelector('#articleBody h1');
    await settle(page, 600);
    await shot(page, '13-reader');
    check('V1 global nav hidden in the reader', !(await visible(page, '.app-shell-nav')));
    const bar = await rect(page, '#viewReader > .st-head');
    check('V2 reader top bar at the top (≤ 64px tall)', bar && bar.top <= 0.5 && bar.height <= 64, bar);
    const h1 = await rect(page, '#articleBody h1');
    check('V3 article starts right under the bar', h1 && h1.top < bar.bottom + 40, { h1: h1 && h1.top, bar: bar.bottom });
    check('V4 table of contents not stacked above the article', !(await visible(page, '#toc')));
    const tocBtn = await rect(page, '#readerTocBtn');
    const edit = await rect(page, '#readerEdit');
    check('V5 目录 and 编辑 buttons ≥ 44×44', tocBtn && tocBtn.visible && tocBtn.width >= 44 && tocBtn.height >= 44 && edit && edit.width >= 44 && edit.height >= 44, { tocBtn, edit });
    const md = await page.$eval('#articleBody p', e => parseFloat(getComputedStyle(e).fontSize));
    check('V6 article text ≥ 16px', md >= 16, md);
    await noOverflow(page, 'V7 reader');
    const h0 = await hash(page);
    await page.tap('#readerTocBtn');
    await settle(page, 500);
    await shot(page, '14-toc-sheet');
    const rows = await page.$$eval('#tocSheetList a', els => els.map(e => e.getBoundingClientRect().height));
    check('V8 目录 opens a sheet with every heading, rows ≥ 44px', rows.length === 15 && rows.every(h => h >= 44), rows.length);
    check('V9 current section highlighted', (await page.$$('#tocSheetList .is-active')).length === 1);
    await back(page);
    check('V10 back closes the 目录 sheet, reader stays', (await page.isHidden('#tocDlg')) && (await hash(page)) === h0);
    await page.tap('#readerTocBtn');
    await settle(page, 400);
    const target = await page.$$eval('#tocSheetList a', els => ({ id: els[5].dataset.target, text: els[5].textContent.trim() }));
    await page.tap(`#tocSheetList a[data-target="${target.id}"]`);
    await settle(page, 1400);
    const hr = await rect(page, '#' + target.id);
    const bar2 = await rect(page, '#viewReader > .st-head');
    check('V11 tapping a heading closes the sheet and jumps there', (await page.isHidden('#tocDlg')) && hr && hr.top >= bar2.bottom - 2 && hr.top <= bar2.bottom + 40, { head: hr && hr.top, bar: bar2 && bar2.bottom });
    check('V12 top bar shows the current section', (await page.textContent('#readerNow')).trim() === target.text, await page.textContent('#readerNow'));
    await shot(page, '15-reader-jumped');
    await back(page);
    check('V13 back from the reader goes to the list', (await hash(page)) === '#writing/techniques' && (await visible(page, '.app-shell-nav')), await hash(page));
  });

  await step('W editor', async () => {
    await page.goto('about:blank');
    await page.goto(BASE + '/study_techniques#writing/techniques/' + longId + '/edit');
    await page.waitForSelector('#viewEditor:not([hidden])');
    await settle(page, 500);
    await shot(page, '16-editor');
    check('W1 global nav hidden in the editor', !(await visible(page, '.app-shell-nav')));
    check('W2 Ctrl/⌘ + S hint hidden', !(await page.evaluate(() => document.querySelector('#editorWriteField').innerText.includes('Ctrl'))));
    const fs16 = await page.$$eval('#editorTitle, #editorContent', els => els.map(e => parseFloat(getComputedStyle(e).fontSize)));
    check('W3 title and text ≥ 16px', fs16.every(f => f >= 16), fs16);
    await page.setViewportSize({ width: W, height: KB_H });
    await page.tap('#editorContent');
    await page.keyboard.press(process.platform === 'darwin' ? 'Meta+ArrowDown' : 'Control+End');
    await page.keyboard.type('\n手机上加的一行');
    await settle(page, 400);
    const save = await page.evaluate(() => {
      const b = [...document.querySelectorAll('[data-action="editor-save"]')].find(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.bottom > 0 && r.top < innerHeight; });
      if (!b) return null;
      const r = b.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom, h: r.height };
    });
    check('W4 keyboard open: 保存 on screen', save && save.top >= 0 && save.bottom <= KB_H && save.h >= 40, save);
    const ta = await page.$eval('#editorContent', e => ({ sh: e.scrollHeight, ch: e.clientHeight }));
    check('W5 text box grows with the text (no scroll inside the box)', ta.sh <= ta.ch + 2, ta);
    await shot(page, '17-editor-keyboard');
    await page.tap('#editorSaveTop');
    await page.waitForFunction(() => /\/techniques\/[^/]+$/.test(location.hash), null, { timeout: 5000 });
    await settle(page, 500);
    check('W6 saved from the top bar', readData('writing_techniques').find(t => t.id === longId).content.includes('手机上加的一行'));
    await page.setViewportSize(DEVICE.viewport);
  });

  check('Z no page errors (light)', !page._errors.length, page._errors);
  await ctx.close();
}

async function darkRun(browser) {
  const { ctx, page } = await newPage(browser, 'dark');
  const longId = readData('writing_techniques').find(t => t.title === '大作文论证块').id;
  await step('N dark', async () => {
    await openList(page, '#reading/hypernyms');
    check('N1 dark theme applied', (await page.evaluate(() => document.documentElement.dataset.theme)) === 'dark');
    await noOverflow(page, 'N2 dark list');
    await shot(page, '20-dark-list');
    const id = await page.getAttribute('#listBody .st-group', 'data-id');
    await cardMenu(page, id);
    const bg = await page.$eval('#actDlg .ui-dialog', e => getComputedStyle(e).backgroundColor);
    check('N3 dark sheet surface', bg !== 'rgb(255, 255, 255)', bg);
    await shot(page, '21-dark-menu');
    await back(page);
    await page.goto('about:blank');
    await page.goto(BASE + '/study_techniques#writing/techniques/' + longId);
    await page.waitForSelector('#articleBody h1');
    await settle(page, 500);
    await noOverflow(page, 'N4 dark reader');
    await shot(page, '22-dark-reader');
  });
  check('Z no page errors (dark)', !page._errors.length, page._errors);
  await ctx.close();
}

async function main() {
  await checkCdn();
  resetFixtures();
  const browser = await pw[ENGINE].launch();
  await lightRun(browser);
  await darkRun(browser);
  await browser.close();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${ENGINE} phone: ${results.length - failed.length}/${results.length} passed`);
  fs.writeFileSync(path.join(SHOTS, 'results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
}
main().catch(e => { console.error('CRASH', e); process.exit(2); });

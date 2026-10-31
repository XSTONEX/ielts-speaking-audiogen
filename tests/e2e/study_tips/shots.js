// 每个画面截图（引擎 × 亮/暗 × 1280/390 宽），顺便检查有没有横向溢出。截图写到 STUDY_TIPS_OUT，别提交。
// 用法：node shots.js chromium|webkit（环境变量见 README.md）。有溢出或页面报错时退出码为 1。
const fs = require('fs');
const path = require('path');
const { pw, BASE, OUT, ENGINE, token, checkCdn, resetFixtures, readData } = require('./common');
const TOKEN = token();

let longId;
const reportLines = [];

async function run(theme, width) {
  const browser = await pw[ENGINE].launch();
  const mobile = width < 800;
  const ctx = await browser.newContext({
    viewport: { width, height: mobile ? 844 : 860 },
    deviceScaleFactor: mobile ? 2 : 1,
    isMobile: mobile && ENGINE === 'chromium',
    hasTouch: mobile
  });
  await ctx.addInitScript(([t, th]) => {
    if (location.protocol === 'about:') return;
    localStorage.setItem('authToken', t);
    localStorage.setItem('ui-theme', th);
  }, [TOKEN, theme]);
  const page = await ctx.newPage();
  const errs = [];
  page.on('pageerror', e => errs.push(e.message));
  // 编辑器里故意留了改动，跳走时 beforeunload 会问，这里直接确认离开
  page.on('dialog', d => { if (d.type() === 'beforeunload') d.accept(); else { errs.push('dialog ' + d.message()); d.dismiss(); } });
  const dir = path.join(OUT, `${ENGINE}-${theme}-${width}`);
  fs.mkdirSync(dir, { recursive: true });
  const overflow = async (label) => {
    const r = await page.evaluate(() => {
      const vw = document.documentElement.clientWidth;
      const bad = [];
      document.querySelectorAll('body *').forEach(el => {
        if (el.closest('[hidden]') || el.closest('.app-shell-panel') || el.closest('.app-shell-scrim')) return;
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') return;
        const b = el.getBoundingClientRect();
        if (b.width === 0 && b.height === 0) return;
        // 自己能横向滚动的容器（表格、代码块、目录）里面超出不算
        let p = el.parentElement, scroller = false;
        while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') { scroller = true; break; } p = p.parentElement; }
        if (!scroller && (b.right > vw + 1 || b.left < -1)) bad.push(el.tagName.toLowerCase() + '.' + [...el.classList].join('.') + ' ' + Math.round(b.left) + '..' + Math.round(b.right));
      });
      return { sw: document.documentElement.scrollWidth, vw, bad: bad.slice(0, 5) };
    });
    const ok = r.sw <= r.vw && !r.bad.length;
    reportLines.push(`${ok ? 'ok  ' : 'OVER'} ${ENGINE} ${theme} ${width} ${label} scrollWidth=${r.sw} vw=${r.vw} ${r.bad.join(' | ')}`);
  };
  const shot = async (name, full) => {
    await page.waitForTimeout(250);
    await overflow(name);
    await page.screenshot({ path: path.join(dir, name + '.png'), fullPage: !!full });
  };
  const go = async (hash, waitSel) => {
    // 只改 # 是同页跳转，会被编辑器的「放弃改动？」拦住；每次先离开再进来，保证整页重新加载
    await page.goto('about:blank');
    await page.goto(BASE + '/study_techniques' + hash);
    await page.waitForSelector(waitSel);
    await page.waitForTimeout(400);
  };

  await go('#reading/synonyms', '#listBody .st-group');
  await shot('01-reading-synonyms');
  if (!mobile) await shot('01b-reading-synonyms-full', true);
  await go('#reading/hypernyms', '#listBody .st-group');
  await shot('02-reading-hypernyms');
  await go('#writing/techniques', '#listBody .st-doc');
  await shot('03-writing-techniques');
  await go('#speaking/hypernyms', '#listBody .ui-empty__title');
  await shot('04-speaking-hypernyms-empty');
  await go('#writing/techniques/' + longId, '#articleBody h1');
  await shot('05-reader');
  await page.evaluate(() => { const hs = document.querySelectorAll('#articleBody h3'); hs[2] && hs[2].scrollIntoView(); });
  await page.waitForTimeout(300);
  await shot('05b-reader-scrolled');
  if (!mobile) {
    await page.click('#readerTools [data-layout="wide"]');
    await shot('05c-reader-wide');
    await page.click('#readerTools [data-layout="narrow"]');
    await page.click('#toc [data-action="toc-toggle"]');
    await shot('05d-reader-toc-off');
    await page.click('#tocOpen [data-action="toc-toggle"]');
  }
  await go('#writing/techniques/' + longId + '/edit', '#viewEditor:not([hidden])');
  await page.fill('#editorContent', (await page.inputValue('#editorContent')) + '\n');
  await shot('06-editor');
  await page.click('[data-action="editor-tab"][data-tab="preview"]');
  await shot('06b-editor-preview');
  await go('#reading/synonyms', '#listBody .st-group');
  await page.click('[data-action="focus-open"]');
  await page.click('#focus [data-layout="' + (mobile ? 'narrow' : 'wide') + '"]').catch(() => {});
  await shot('07-focus' + (mobile ? '' : '-wide'));
  if (!mobile) {
    await page.click('#focus [data-layout="narrow"]');
    await shot('07b-focus-narrow');
  }
  await page.click('#focusClose');
  await page.click('#listBody .st-group:nth-child(5) [data-action="edit"]');
  await shot('08-synonym-edit-dialog');
  await page.keyboard.press('Escape');
  await go('#reading/hypernyms', '#listBody .st-group');
  await page.click('[data-action="group-new"]');
  await page.fill('#groupTitle', '天气');
  await page.fill('#groupDlgBody [data-rows="upper"] .st-row [data-field="word"]', 'weather');
  await shot('09-hypernym-new-dialog');
  await page.click('#groupDlg [data-action="dlg-close"]');
  await page.click('#confirmOk').catch(() => {});
  await page.waitForTimeout(200);
  await go('#reading/synonyms', '#listBody .st-group');
  await page.click('#listTools [data-action="import-open"]');
  await page.setInputFiles('#importFile', { name: 'reading-synonyms.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ groups: [{ title: '甲', synonyms: [{ word: 'a', definition: '一' }, { word: 'b' }] }, { synonyms: [{ word: 'c' }] }] })) });
  await page.waitForSelector('#importStatus .st-check');
  await shot('10-import-ready');
  await page.setInputFiles('#importFile', { name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify({ groups: [{ title: 'x' }, { synonyms: [{ word: 'ok' }, { definition: 'no word' }] }] })) });
  await page.waitForSelector('#importStatus .st-check--err');
  await shot('10b-import-error');
  await page.keyboard.press('Escape');
  await page.click('#listBody .st-group:nth-child(5) [data-action="delete"]');
  await shot('11-delete-confirm');
  await page.keyboard.press('Escape');
  if (mobile) {
    await page.click('.app-shell-current').catch(() => {});
    await shot('12-nav-panel-open');
  }
  if (errs.length) reportLines.push(`ERR  ${ENGINE} ${theme} ${width} pageerror: ${errs.join(' | ')}`);
  await browser.close();
}

(async () => {
  await checkCdn();
  resetFixtures();
  longId = readData('writing_techniques').find(t => t.title === '大作文论证块').id;
  for (const theme of ['light', 'dark']) {
    for (const width of [1280, 390]) {
      await run(theme, width);
    }
  }
  fs.mkdirSync(OUT, { recursive: true });
  const out = path.join(OUT, `overflow-${ENGINE}.txt`);
  fs.writeFileSync(out, reportLines.join('\n') + '\n');
  console.log(reportLines.filter(l => !l.startsWith('ok')).join('\n') || 'no overflow, no page errors');
  console.log(reportLines.length + ' checks');
  console.log('截图在 ' + OUT);
  process.exit(reportLines.some(l => !l.startsWith('ok')) ? 1 : 0);
})().catch(e => { console.error('CRASH', e); process.exit(2); });

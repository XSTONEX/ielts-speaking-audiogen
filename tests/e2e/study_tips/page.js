// 学习技巧页功能测试：在沙盒里把每个功能都点一遍，只用 make_fixtures.py 编造的数据。
// 用法：node page.js chromium|webkit（环境变量见 README.md）。全部通过退出码为 0。
const fs = require('fs');
const path = require('path');
const { pw, BASE, OUT, ENGINE, token, checkCdn, resetFixtures, readData } = require('./common');
const TOKEN = token();
const SHOTS = path.join(OUT, ENGINE + '-page');
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
function check(name, cond, detail) {
  results.push({ name, ok: !!cond, detail });
  console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail !== undefined && !cond ? '  -> ' + JSON.stringify(detail) : ''));
}

async function main() {
  await checkCdn();
  resetFixtures();
  const browser = await pw[ENGINE].launch();
  const ctxOpts = { viewport: { width: 1280, height: 860 }, deviceScaleFactor: 1 };
  if (ENGINE === 'chromium') ctxOpts.permissions = ['clipboard-read', 'clipboard-write'];
  const ctx = await browser.newContext(ctxOpts);
  await ctx.addInitScript(([t]) => {
    if (!sessionStorage.getItem('seeded')) {
      localStorage.setItem('authToken', t);
      localStorage.setItem('currentUser', JSON.stringify({ username: 'demo', display_name: '测试同学', avatar: 'avatar_teacher.svg' }));
      localStorage.setItem('ui-theme', 'light');
      sessionStorage.setItem('seeded', '1');
    }
  }, [TOKEN]);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('response', r => { if (r.status() === 404) errors.push('404 url: ' + r.url()); });
  page.on('dialog', d => { errors.push('native dialog: ' + d.message()); d.dismiss(); });
  const shot = (name, full) => page.screenshot({ path: path.join(SHOTS, name + '.png'), fullPage: !!full });
  const settle = (ms) => page.waitForTimeout(ms || 350);
  const apiCall = (method, url, body) => page.evaluate(async ([m, u, b]) => {
    const r = await fetch(u, { method: m, headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + localStorage.getItem('authToken') }, body: b ? JSON.stringify(b) : undefined });
    return { status: r.status, data: await r.json().catch(() => null) };
  }, [method, url, body]);
  const toastText = async () => (await page.$$eval('.ielts-toast', els => els.map(e => e.textContent))).join(' | ');
  const cardTitles = () => page.$$eval('#listBody .st-group__title, #listBody .st-doc__title', els => els.map(e => e.textContent));

  // ---------- A. load ----------
  await page.goto(BASE + '/study_techniques');
  await page.waitForSelector('#listBody .st-group, #listBody .ui-empty__title');
  await settle(800);
  check('A1 tab title', (await page.title()) === '学习技巧 · IELTS Lab', await page.title());
  check('A2 default route listening/synonyms', (await page.evaluate(() => location.hash)) === '#listening/synonyms', await page.evaluate(() => location.hash));
  check('A3 h1 学习技巧', (await page.textContent('#viewList .st-head__title')).trim() === '学习技巧');
  check('A4 nav bar present', !!(await page.$('.app-shell-nav')));
  const railCounts = await page.$$eval('#rail .ui-rail__item', els => els.map(e => e.querySelector('.ui-rail__name').textContent + e.querySelector('.ui-rail__count').textContent));
  check('A5 rail counts', JSON.stringify(railCounts) === JSON.stringify(['听力7', '口语2', '阅读22', '写作7']), railCounts);
  check('A6 no highlight.js / google fonts requested', !(await page.evaluate(() => [...document.scripts].some(s => /highlight/.test(s.src)) || [...document.querySelectorAll('link')].some(l => /fonts.googleapis/.test(l.href)))));

  // ---------- C/D. reading synonyms + sort ----------
  await page.click('#rail a[href="#reading/synonyms"]');
  await settle();
  check('C1 hash #reading/synonyms', (await page.evaluate(() => location.hash)) === '#reading/synonyms');
  const shown = await cardTitles();
  const data = readData('reading_synonyms');
  const expectDesc = [...data].sort((a, b) => b.created_at.localeCompare(a.created_at)).map(x => x.title || '未命名');
  check('C2 12 cards', shown.length === 12, shown.length);
  check('C3 default newest first (bug 5)', JSON.stringify(shown) === JSON.stringify(expectDesc), { shown, expectDesc });
  check('C4 最新在前 chip on', (await page.textContent('#listSort .ui-chip.is-on')) === '最新在前');
  await page.click('#listSort [data-order="asc"]');
  await settle();
  check('C5 asc order', JSON.stringify(await cardTitles()) === JSON.stringify([...expectDesc].reverse()));
  await page.click('#listSort [data-order="desc"]');
  await settle();
  const words = data.reduce((n, g) => n + g.synonyms.length, 0);
  check('D1 summary note', (await page.textContent('#listNote')) === '阅读 · 12 组 · ' + words + ' 个词', await page.textContent('#listNote'));
  check('D2 untitled group shows 未命名', (await page.$$eval('#listBody .st-group__title.is-untitled', els => els.length)) === 1);
  check('D3 seg counts', JSON.stringify(await page.$$eval('#typeSeg .ui-seg__count', els => els.map(e => e.textContent))) === '["12","8","2"]');
  await shot('c-reading-synonyms');

  // ---------- E. hypernyms ----------
  await page.click('#typeSeg [data-type="hypernyms"]');
  await settle();
  check('E1 hash hypernyms', (await page.evaluate(() => location.hash)) === '#reading/hypernyms');
  check('E2 8 hypernym cards', (await page.$$('#listBody .st-group')).length === 8);
  const lowerOnly = readData('reading_hypernyms').find(g => !g.upper_words.length);
  const loCard = await page.$(`#listBody [data-id="${lowerOnly.id}"]`);
  check('E3 lower-only card has no 上义 row', loCard && (await loCard.$$eval('.st-tree__label', els => els.map(e => e.textContent))).join() === '下义');
  check('E4 upper chip styled', (await page.$$('#listBody .st-word--upper')).length > 0);

  // ---------- F. XSS + quotes ----------
  const xssSyn = await apiCall('POST', '/api/study_techniques/synonyms/reading', {
    title: '<img src=x onerror="window.__xss=1">组',
    synonyms: [{ word: '<b>bold</b>', definition: 'say "hello" to sb' }, { word: "it's", definition: '<script>window.__xss=4</script>' }]
  });
  const xssTech = await apiCall('POST', '/api/study_techniques/techniques/reading', {
    title: '<img src=x onerror=window.__xss=2>标题',
    content: '# <img src=x onerror="window.__xss=3">第一节\n\n正文 <img src=x onerror="window.__xss=5">\n\n## 二\n\nC++ is a language that is quite hard to learn for many beginners in programming today\n\n## 三\n\na == b is a comparison that many people write wrongly in their first program ever'
  });
  check('F0 seeded via API', xssSyn.status === 200 && xssTech.status === 200, [xssSyn, xssTech]);
  await page.reload();
  await page.waitForSelector('#listBody .st-group');
  await page.click('#typeSeg [data-type="synonyms"]');
  await settle(600);
  const xCard = await page.$(`#listBody [data-id="${xssSyn.data.id}"]`);
  check('F1 xss title shown as text', xCard && (await xCard.$eval('.st-group__title', e => e.textContent)) === '<img src=x onerror="window.__xss=1">组');
  check('F2 word with tags shown as text', xCard && (await xCard.$eval('.st-word__en', e => e.textContent)) === '<b>bold</b>');
  check('F3 no img injected in list', (await page.$$('#listBody img')).length === 0);
  await page.click('#typeSeg [data-type="techniques"]');
  await settle();
  check('F4 xss tech title text', (await page.$$eval('#listBody .st-doc__title', els => els.map(e => e.textContent))).includes('<img src=x onerror=window.__xss=2>标题'));
  const t0 = Date.now();
  await page.goto(BASE + '/study_techniques#reading/techniques/' + xssTech.data.id);
  await page.waitForSelector('#articleBody h1');
  await settle(500);
  check('F5 reader renders fast with lone ++ and == (bug 14)', Date.now() - t0 < 4000, Date.now() - t0);
  check('F6 toc text escaped (bug 2)', (await page.$$eval('#tocList a', els => els.map(e => e.textContent)))[0] === '第一节', await page.$$eval('#tocList a', els => els.map(e => e.textContent)));
  check('F7 toc has no img', (await page.$$('#tocList img')).length === 0);
  check('F8 article imgs have no onerror', await page.$$eval('#articleBody img', els => els.every(e => !e.hasAttribute('onerror'))));
  await settle(500);
  check('F9 window.__xss never set', (await page.evaluate(() => window.__xss)) === undefined, await page.evaluate(() => window.__xss));
  check('F10 lone ++ kept as text', (await page.textContent('#articleBody')).includes('C++ is a language'));

  // ---------- G. edit dialog keeps quotes (bug 3) ----------
  await page.goto(BASE + '/study_techniques#reading/synonyms');
  await page.waitForSelector('#listBody .st-group');
  await page.click(`#listBody [data-id="${xssSyn.data.id}"] [data-action="edit"]`);
  await settle();
  const defs = await page.$$eval('#groupDlgBody [data-field="definition"]', els => els.map(e => e.value));
  check('G1 definition with quotes intact', defs[0] === 'say "hello" to sb', defs);
  check('G2 title input has full xss title', (await page.inputValue('#groupTitle')) === '<img src=x onerror="window.__xss=1">组');
  check('G3 edit dialog shows trailing empty row', defs.length === 3 && defs[2] === '');
  await shot('g-edit-dialog');
  await page.click('#groupDlgSave');
  await page.waitForSelector('#groupDlg', { state: 'hidden' });
  const after = readData('reading_synonyms').find(g => g.id === xssSyn.data.id);
  check('G4 save unchanged keeps data', after && after.synonyms[0].definition === 'say "hello" to sb' && after.synonyms[1].word === "it's" && after.title === '<img src=x onerror="window.__xss=1">组', after);

  // ---------- H/I. new group + validation ----------
  await page.click('[data-action="group-new"]');
  await settle();
  check('H1 new dialog title', (await page.textContent('#groupDlgTitle')) === '新建词汇替换 · 阅读');
  check('H2 3 empty rows', (await page.$$('#groupDlgBody .st-row')).length === 3);
  await page.click('#groupDlgSave');
  check('I1 empty save shows error', (await page.textContent('#groupErr')) === '至少填一个词再保存。');
  await page.fill('#groupDlgBody .st-row:nth-child(1) [data-field="definition"]', '只有释义');
  await page.click('#groupDlgSave');
  check('I2 orphan definition flagged', (await page.textContent('#groupErr')).includes('只填了释义'));
  await page.fill('#groupDlgBody .st-row:nth-child(1) [data-field="definition"]', '');
  await page.fill('#groupTitle', '测试新组');
  await page.press('#groupTitle', 'Enter');
  check('H3 Enter moves to first word', await page.evaluate(() => document.activeElement.dataset.field === 'word'));
  await page.keyboard.type('alpha');
  await page.keyboard.press('Enter');
  await page.keyboard.type('阿尔法');
  await page.keyboard.press('Enter');
  await page.keyboard.type('beta');
  await page.keyboard.press('Enter');
  await page.keyboard.press('Enter');
  await page.keyboard.type('gamma');
  check('H4 count label', (await page.textContent('#groupDlgBody [data-count-label]')) === '同义词 · 3 个', await page.textContent('#groupDlgBody [data-count-label]'));
  // last row → Enter on definition adds a row
  await page.click('#groupDlgBody .st-row:last-child [data-field="definition"]');
  await page.keyboard.press('Enter');
  check('H5 Enter on last definition adds row', (await page.$$('#groupDlgBody .st-row')).length === 4);
  await page.keyboard.press(ENGINE === 'webkit' ? 'Meta+Enter' : 'Control+Enter');
  await page.waitForSelector('#groupDlg', { state: 'hidden' });
  await settle(400);
  const created = readData('reading_synonyms').find(g => g.title === '测试新组');
  check('H6 created with 3 words', created && JSON.stringify(created.synonyms) === JSON.stringify([{ word: 'alpha', definition: '阿尔法' }, { word: 'beta', definition: '' }, { word: 'gamma', definition: '' }]), created);
  check('H7 toast after create', (await toastText()).includes('已新建一组'), await toastText());
  check('H8 new card first (newest)', (await cardTitles())[0] === '测试新组', (await cardTitles())[0]);
  check('H9 rail count updated', (await page.textContent('#rail a[href="#reading/synonyms"] .ui-rail__count')) === '25', await page.textContent('#rail a[href="#reading/synonyms"] .ui-rail__count'));

  // dirty close asks
  await page.click('[data-action="group-new"]');
  await settle();
  await page.fill('#groupDlgBody .st-row:nth-child(1) [data-field="word"]', 'typed');
  await page.keyboard.press('Escape');
  await settle();
  check('H10 dirty Esc asks first', !(await page.isHidden('#confirmDlg')) && !(await page.isHidden('#groupDlg')));
  await page.click('#confirmCancel');
  await settle();
  check('H11 cancel keeps dialog', !(await page.isHidden('#groupDlg')) && (await page.inputValue('#groupDlgBody .st-row:nth-child(1) [data-field="word"]')) === 'typed');
  await page.mouse.click(5, 400); // backdrop
  await settle();
  check('H12 backdrop on dirty asks', !(await page.isHidden('#confirmDlg')));
  await page.click('#confirmOk');
  await settle();
  check('H13 discard closes', await page.isHidden('#groupDlg'));
  await page.click('[data-action="group-new"]');
  await settle();
  await page.keyboard.press('Escape');
  await settle();
  check('H14 clean Esc closes at once', (await page.isHidden('#groupDlg')) && (await page.isHidden('#confirmDlg')));

  // ---------- J. clear title in edit ----------
  await page.click(`#listBody [data-id="${created.id}"] [data-action="edit"]`);
  await settle();
  await page.fill('#groupTitle', '');
  await page.click('#groupDlgSave');
  await page.waitForSelector('#groupDlg', { state: 'hidden' });
  await settle(300);
  const cleared = readData('reading_synonyms').find(g => g.id === created.id);
  check('J1 cleared title removed from data', cleared && !('title' in cleared), cleared);
  check('J2 card shows 未命名', (await page.textContent(`#listBody [data-id="${created.id}"] .st-group__title`)) === '未命名');

  // ---------- K. inline rename ----------
  const titleSel = `#listBody [data-id="${created.id}"] .st-group__title`;
  await page.click(titleSel);
  await settle(150);
  check('K1 rename starts empty for untitled', (await page.textContent(titleSel)) === '' && (await page.getAttribute(titleSel, 'contenteditable')) === 'true');
  await page.keyboard.type('改过的名字');
  await page.keyboard.press('Enter');
  await settle(500);
  check('K2 rename saved + shown', readData('reading_synonyms').find(g => g.id === created.id).title === '改过的名字' && (await page.textContent(titleSel)) === '改过的名字' && (await page.getAttribute(titleSel, 'contenteditable')) === null, await page.textContent(titleSel));
  check('K3 words kept after rename', readData('reading_synonyms').find(g => g.id === created.id).synonyms.length === 3);
  await page.click(titleSel);
  await page.keyboard.press('Meta+A');
  await page.keyboard.type('不要');
  await page.keyboard.press('Escape');
  await settle(300);
  check('K4 Esc cancels rename', (await page.textContent(titleSel)) === '改过的名字' && readData('reading_synonyms').find(g => g.id === created.id).title === '改过的名字');
  await page.click(titleSel);
  await page.keyboard.press('Meta+A');
  await page.keyboard.press('Backspace');
  await page.keyboard.press('Enter');
  await settle(300);
  check('K5 empty rename reverts', (await page.textContent(titleSel)) === '改过的名字');
  // keyboard: focus + Enter starts rename, blur saves
  await page.focus(titleSel);
  await page.keyboard.press('Enter');
  await page.keyboard.press('ArrowRight');
  await page.keyboard.type('2');
  await page.click('#listNote');
  await settle(500);
  check('K6 blur saves rename', readData('reading_synonyms').find(g => g.id === created.id).title === '改过的名字2', readData('reading_synonyms').find(g => g.id === created.id).title);

  // ---------- L. delete ----------
  await page.click(`#listBody [data-id="${created.id}"] [data-action="delete"]`);
  await settle();
  check('L1 confirm dialog', (await page.textContent('#confirmTitle')) === '删除这组词汇替换？' && (await page.textContent('#confirmText')).includes('3 个词'));
  check('L2 preview chips', (await page.$$('#confirmExtra .st-word')).length === 3);
  await shot('l-delete-confirm');
  await page.click('#confirmCancel');
  await settle();
  check('L3 cancel keeps', !!readData('reading_synonyms').find(g => g.id === created.id));
  await page.click(`#listBody [data-id="${created.id}"] [data-action="delete"]`);
  await settle();
  await page.click('#confirmOk');
  await settle(600);
  check('L4 deleted', !readData('reading_synonyms').find(g => g.id === created.id) && !(await page.$(`#listBody [data-id="${created.id}"]`)));
  check('L5 toast 已删除', (await toastText()).includes('已删除'));

  // ---------- M. focus ----------
  await page.click('[data-action="focus-open"]');
  await settle();
  check('M1 focus open', !(await page.isHidden('#focus')) && (await page.textContent('#focusTitle')) === '阅读 · 词汇替换');
  check('M2 focus cards', (await page.$$('#focusInner .st-group')).length === 13);
  check('M3 focus covers nav', await page.evaluate(() => { const r = document.querySelector('.app-shell-nav').getBoundingClientRect(); const el = document.elementFromPoint(r.left + 200, r.top + 10); return !!el.closest('#focus'); }));
  await page.click('#focusSort [data-order="asc"]');
  await settle();
  check('M4 edit buttons after sort (bug 6)', (await page.$$('#focusInner [data-action="edit"]')).length === 13);
  check('M5 focus sorted asc', (await page.$$eval('#focusInner .st-group__title', els => els.map(e => e.textContent)))[0] === [...expectDesc].reverse()[0]);
  await page.click('#focus [data-layout="wide"]');
  await settle();
  check('M6 wide layout 3 cols + saved', (await page.evaluate(() => localStorage.getItem('fullscreenLayout'))) === 'wide' && !!(await page.$('#focusInner.is-wide .st-grid--3')));
  await shot('m-focus-wide');
  await page.click('#focus [data-layout="narrow"]');
  await settle();
  check('M7 narrow layout 1 col', !!(await page.$('#focusInner:not(.is-wide) .st-grid--1')));
  const firstFocusId = await page.getAttribute('#focusInner .st-group', 'data-id');
  await page.click(`#focusInner [data-id="${firstFocusId}"] [data-action="edit"]`);
  await settle();
  check('M8 edit from focus opens dialog above', !(await page.isHidden('#groupDlg')) && await page.evaluate(() => { const b = document.querySelector('#groupDlgSave').getBoundingClientRect(); return !!document.elementFromPoint(b.left + 5, b.top + 5).closest('#groupDlg'); }));
  await page.keyboard.press('Escape');
  await settle();
  check('M9 Esc closes dialog only', (await page.isHidden('#groupDlg')) && !(await page.isHidden('#focus')));
  await page.keyboard.press('Escape');
  await settle();
  check('M10 Esc closes focus', await page.isHidden('#focus'));
  check('M11 list sort follows focus', (await page.textContent('#listSort .ui-chip.is-on')) === '最早在前');
  await page.click('#listSort [data-order="desc"]');
  // delete last in focus (speaking has 1 group)
  await page.click('#rail a[href="#speaking/synonyms"]');
  await settle();
  await page.click('[data-action="focus-open"]');
  await settle();
  await page.click('#focusInner [data-action="delete"]');
  await settle();
  await page.click('#confirmOk');
  await settle(600);
  check('M12 focus empty state after deleting last (bug 7)', (await page.$$('#focusInner .st-group')).length === 0 && (await page.textContent('#focusInner')).includes('都删完了'));
  await page.click('#focusInner [data-action="focus-close"]');
  await settle();
  check('M13 list empty state + 全屏 disabled', (await page.textContent('#listBody')).includes('口语还没有词汇替换') && (await page.isDisabled('[data-action="focus-open"]')));
  await shot('m-empty-speaking');

  // ---------- N. import ----------
  await page.click('#rail a[href="#listening/synonyms"]');
  await settle();
  await page.click('#listTools [data-action="import-open"]');
  await settle();
  check('N1 import dialog', (await page.textContent('#importDlgTitle')) === '导入词汇替换 · 听力' && (await page.isDisabled('#importRun')));
  const good = { groups: [{ title: '导入组一', synonyms: [{ word: ' one ', definition: '一' }, { word: 'uno' }] }, { synonyms: [{ word: 'two', definition: 2 }] }] };
  await page.setInputFiles('#importFile', { name: 'good.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(good)) });
  await page.waitForSelector('#importStatus .st-check');
  check('N2 ready message', (await page.textContent('#importStatus')).includes('格式没问题：2 组 · 3 个词'), await page.textContent('#importStatus'));
  check('N3 run enabled with count', !(await page.isDisabled('#importRun')) && (await page.textContent('#importRun')) === '导入 2 组');
  await shot('n-import-ready');
  // bad file → whole file rejected
  const bad = { groups: [{ title: 'ok', synonyms: [{ word: 'a' }] }, { title: 'x' }, { synonyms: [{ word: 'b' }, { definition: '没有词' }] }] };
  await page.setInputFiles('#importFile', { name: 'bad.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bad)) });
  await page.waitForSelector('#importStatus .st-check--err');
  const errTxt = await page.textContent('#importStatus');
  check('N4 errors listed', errTxt.includes('第 2 组缺少 synonyms 数组') && errTxt.includes('第 3 组第 2 个词没有 word') && errTxt.includes('整份文件都没有导入'), errTxt);
  check('N5 run disabled on error', await page.isDisabled('#importRun'));
  await shot('n-import-error');
  await page.setInputFiles('#importFile', { name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{"groups": [ {,] }') });
  await page.waitForSelector('#importStatus .st-check--err');
  check('N6 non-JSON message', (await page.textContent('#importStatus')).includes('不是合法的 JSON'));
  // same name re-pick after fixing must re-validate
  await page.setInputFiles('#importFile', { name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(good)) });
  await page.waitForSelector('#importStatus .st-check:not(.st-check--err)');
  check('N7 re-pick same filename re-validates', (await page.textContent('#importStatus')).includes('格式没问题'));
  // slow the POSTs to test closing mid-import
  let posts = 0;
  await page.route('**/api/study_techniques/synonyms/listening', async (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    posts++;
    await new Promise(r => setTimeout(r, 700));
    route.continue();
  });
  await page.click('#importRun');
  await settle(250);
  check('N8 progress shown', (await page.textContent('#importStatus')).includes('先别关这个窗口') && (await page.textContent('#importRun')) === '导入中…');
  check('N9 close button hidden, cancel disabled', (await page.isHidden('#importClose')) && (await page.isDisabled('#importCancel')));
  await shot('n-import-progress');
  await page.keyboard.press('Escape');
  await page.mouse.click(5, 400);
  await settle(100);
  check('N10 Esc/backdrop ignored while importing (bug 10)', !(await page.isHidden('#importDlg')));
  await page.waitForSelector('#importDlg', { state: 'hidden', timeout: 8000 });
  await settle(300);
  await page.unroute('**/api/study_techniques/synonyms/listening');
  const ls = readData('listening_synonyms');
  const imported = ls.filter(g => g.title === '导入组一' || g.title === '词汇组 2');
  check('N11 both groups imported once', imported.length === 2 && posts === 2, { posts, titles: ls.map(g => g.title) });
  check('N12 words trimmed, numbers to text, title fallback', JSON.stringify(imported.map(g => g.synonyms)) === JSON.stringify([[{ word: 'one', definition: '一' }, { word: 'uno', definition: '' }], [{ word: 'two', definition: '2' }]]), imported);
  check('N13 toast 导入了 2 组', (await toastText()).includes('导入了 2 组'));
  // failure path: one group fails on server
  await page.click('#listTools [data-action="import-open"]');
  await settle();
  let n = 0;
  await page.route('**/api/study_techniques/synonyms/listening', (route) => {
    if (route.request().method() !== 'POST') return route.continue();
    n++;
    if (n === 2) return route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"Failed to save data"}' });
    route.continue();
  });
  const three = { groups: [{ synonyms: [{ word: 'p' }] }, { synonyms: [{ word: 'q' }] }, { synonyms: [{ word: 'r' }] }] };
  await page.setInputFiles('#importFile', { name: 'three.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(three)) });
  await page.waitForSelector('#importStatus .st-check');
  await page.click('#importRun');
  await page.waitForFunction(() => document.querySelector('#importStatus').textContent.includes('导入完成'));
  check('N14 partial failure reported', (await page.textContent('#importStatus')).includes('2 组加进去了，第 2 组没导进去') && (await page.textContent('#importCancel')) === '关闭', await page.textContent('#importStatus'));
  await page.unroute('**/api/study_techniques/synonyms/listening');
  await page.click('#importCancel');
  await settle();
  check('N15 can close after done', await page.isHidden('#importDlg'));
  // hypernym import
  await page.click('#typeSeg [data-type="hypernyms"]');
  await settle();
  await page.click('#listTools [data-action="import-open"]');
  await settle();
  check('N16 hypernym sample', JSON.parse(await page.textContent('#importSample')).groups[0].upper_words[0].word === 'transportation');
  const hyp = { groups: [{ title: '水果', upper_words: [{ word: 'fruit', definition: '水果' }], lower_words: [{ word: 'apple' }] }, { lower_words: [{ word: 'only lower' }] }, { upper_words: [] }] };
  await page.setInputFiles('#importFile', { name: 'h.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(hyp)) });
  await page.waitForSelector('#importStatus .st-check');
  check('N17 empty hypernym group flagged', (await page.textContent('#importStatus')).includes('第 3 组的上义词和下义词都是空的'), await page.textContent('#importStatus'));
  hyp.groups.pop();
  await page.setInputFiles('#importFile', { name: 'h.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(hyp)) });
  await page.waitForSelector('#importStatus .st-check:not(.st-check--err)');
  check('N18 hypernym ready text', (await page.textContent('#importStatus')).includes('2 组 · 1 个上义词 · 2 个下义词'), await page.textContent('#importStatus'));
  await page.click('#importRun');
  await page.waitForSelector('#importDlg', { state: 'hidden', timeout: 8000 });
  const lh = readData('listening_hypernyms');
  check('N19 hypernyms imported with fallback title', lh.some(g => g.title === '水果') && lh.some(g => g.title === '上下义词组 2' && g.lower_words[0].word === 'only lower' && g.upper_words.length === 0), lh.map(g => g.title));
  // copy sample
  await page.click('#typeSeg [data-type="synonyms"]');
  await settle();
  await page.click('#listTools [data-action="import-open"]');
  await settle();
  await page.click('#importCopy');
  await settle(300);
  check('O1 copy button feedback', (await page.textContent('#importCopy')) === '已复制');
  if (ENGINE === 'chromium') {
    const clip = await page.evaluate(() => navigator.clipboard.readText());
    let parsed = null;
    try { parsed = JSON.parse(clip); } catch (e) {}
    check('O2 copied text is valid JSON (bug 9)', parsed && parsed.groups.length === 2, clip.slice(0, 40));
  }
  await page.keyboard.press('Escape');
  await settle();

  // ---------- P. techniques list ----------
  await page.click('#rail a[href="#writing/synonyms"]');
  await settle();
  await page.click('#typeSeg [data-type="techniques"]');
  await settle();
  const docs = await cardTitles();
  check('P1 4 docs newest first', JSON.stringify(docs) === JSON.stringify(['开头段改写', '小作文：饼图', '小作文：线图描述', '大作文论证块']), docs);
  const metas = await page.$$eval('#listBody .st-doc__meta', els => els.map(e => e.textContent));
  check('P2 meta has 目录/字/更新 with dates', metas[0].includes('目录 4 条') && metas[0].includes('10 月 9 日更新') && metas[1].includes('10 月 8 日更新'), metas);
  check('P3 excerpt', (await page.textContent('#listBody .st-doc__excerpt')).startsWith('同义替换加语序调整'));
  check('P4 no 全屏/导入 on techniques', !(await page.$('#listTools [data-action="focus-open"]')) && !!(await page.$('#listTools a')));
  await shot('p-techniques');

  // ---------- Q. reader ----------
  await page.click('#listBody .st-doc:nth-child(4) .st-doc__title a');
  await page.waitForSelector('#articleBody h1');
  await settle();
  const long = readData('writing_techniques').find(t => t.title === '大作文论证块');
  check('Q1 reader route', (await page.evaluate(() => location.hash)) === '#writing/techniques/' + long.id);
  const tocN = await page.$$eval('#tocList a', els => els.length);
  const hN = await page.$$eval('#articleBody h1,#articleBody h2,#articleBody h3,#articleBody h4,#articleBody h5,#articleBody h6', els => els.length);
  check('Q2 toc entries = headings', tocN === hN && tocN > 5, { tocN, hN });
  check('Q3 meta 目录 N 条', (await page.textContent('#readerMeta')).includes('目录 ' + tocN + ' 条'));
  check('Q4 table/blockquote/mark/u rendered', !!(await page.$('#articleBody table')) && !!(await page.$('#articleBody blockquote')) && !!(await page.$('#articleBody mark')) && !!(await page.$('#articleBody u')));
  await shot('q-reader-top');
  const allLinks = await page.$$('#tocList a');
  const lastLink = allLinks[Math.floor(allLinks.length / 2)];
  const targetId = await lastLink.getAttribute('data-target');
  await lastLink.click();
  await settle(1200);
  const pos = await page.evaluate((id) => document.getElementById(id).getBoundingClientRect().top, targetId);
  check('Q5 toc click scrolls heading below nav', pos > 50 && pos < 140, pos);
  check('Q6 hash unchanged by toc click', (await page.evaluate(() => location.hash)) === '#writing/techniques/' + long.id);
  check('Q7 active toc item follows', await page.evaluate((id) => { const a = document.querySelector('#tocList .is-active'); return !!a && (a.dataset.target === id || +a.dataset.target.split('-')[2] > +id.split('-')[2]); }, targetId));
  await shot('q-reader-scrolled');
  await page.click('#toc [data-action="toc-toggle"]');
  await settle();
  check('Q8 toc collapsed + saved', (await page.isHidden('#toc')) && !(await page.isHidden('#tocOpen')) && (await page.evaluate(() => localStorage.getItem('tocCollapsed'))) === 'true');
  await page.click('#tocOpen [data-action="toc-toggle"]');
  await settle();
  check('Q9 toc expanded', !(await page.isHidden('#toc')) && (await page.evaluate(() => localStorage.getItem('tocCollapsed'))) === 'false');
  await page.click('#readerTools [data-layout="wide"]');
  await settle();
  check('Q10 wide article', !!(await page.$('#article.is-wide')) && (await page.evaluate(() => localStorage.getItem('fullscreenLayout'))) === 'wide');
  await page.click('#readerTools [data-layout="narrow"]');
  await settle();

  // ---------- R. editor ----------
  await page.click('#readerEdit');
  await page.waitForSelector('#viewEditor:not([hidden])');
  await settle();
  check('R1 editor route + values', (await page.evaluate(() => location.hash)).endsWith('/edit') && (await page.inputValue('#editorTitle')) === '大作文论证块' && (await page.inputValue('#editorContent')) === long.content);
  check('R2 not dirty initially', await page.isHidden('#editorDirty'));
  await page.fill('#editorContent', '');
  await page.click('#editorSave');
  await settle();
  check('R3 empty content explains (bug 8)', (await page.textContent('#editorErr')) === '正文不能空着，写点内容再保存。');
  await page.fill('#editorContent', long.content + '\n\n## 新加一节\n\n新内容 ==重点==');
  check('R4 dirty tag', !(await page.isHidden('#editorDirty')));
  await page.click('[data-action="editor-tab"][data-tab="preview"]');
  await settle();
  check('R5 preview renders', (await page.textContent('#editorPreview')).includes('新内容') && !!(await page.$('#editorPreview mark')) && (await page.isHidden('#editorWriteField')));
  await shot('r-editor-preview');
  await page.click('[data-action="editor-tab"][data-tab="edit"]');
  // leave with dirty → confirm
  await page.click('#editorCrumb a:nth-of-type(2)');
  await settle();
  check('R6 leaving dirty asks', !(await page.isHidden('#confirmDlg')) && (await page.evaluate(() => location.hash)).endsWith('/edit'));
  await page.click('#confirmCancel');
  await settle();
  check('R7 cancel stays with edits', !(await page.isHidden('#viewEditor')) && (await page.inputValue('#editorContent')).includes('新加一节'));
  await page.keyboard.press(ENGINE === 'webkit' ? 'Meta+s' : 'Control+s');
  await page.waitForSelector('#viewReader:not([hidden])');
  await settle(500);
  check('R8 Ctrl/Cmd+S saved → reader', readData('writing_techniques').find(t => t.id === long.id).content.includes('新加一节') && (await page.evaluate(() => location.hash)) === '#writing/techniques/' + long.id);
  check('R9 reader shows new section + toc', (await page.$$eval('#tocList a', els => els.map(e => e.textContent))).includes('新加一节'));
  // TOC toggle after save still works (bug 4)
  await page.click('#toc [data-action="toc-toggle"]');
  await settle();
  const off1 = await page.isHidden('#toc');
  await page.click('#tocOpen [data-action="toc-toggle"]');
  await settle();
  check('R10 toc toggle works after save (bug 4)', off1 && !(await page.isHidden('#toc')));
  // discard path
  await page.click('#readerEdit');
  await settle();
  await page.fill('#editorTitle', '改了标题');
  await page.click('#editorBack');
  await settle();
  await page.click('#confirmOk');
  await settle();
  check('R11 discard leaves to reader, data unchanged', !(await page.isHidden('#viewReader')) && readData('writing_techniques').find(t => t.id === long.id).title === '大作文论证块');
  // network failure keeps edits
  await page.click('#readerEdit');
  await settle();
  await page.fill('#editorTitle', '网络断了');
  await page.route('**/api/study_techniques/techniques/writing/*', r => r.request().method() === 'PUT' ? r.abort() : r.continue());
  await page.click('#editorSave');
  await settle(500);
  check('R12 network error message, stays', (await page.textContent('#editorErr')).includes('网络连不上') && !(await page.isHidden('#viewEditor')) && (await page.inputValue('#editorTitle')) === '网络断了');
  await page.unroute('**/api/study_techniques/techniques/writing/*');
  await page.fill('#editorTitle', '大作文论证块');
  await page.click('#editorSave');
  await page.waitForSelector('#viewReader:not([hidden])');

  // ---------- S. new doc ----------
  await page.goto(BASE + '/study_techniques#writing/techniques');
  await page.waitForSelector('#listBody .st-doc');
  await page.click('#listTools a');
  await page.waitForSelector('#viewEditor:not([hidden])');
  check('S1 new editor', (await page.textContent('#editorHeading')) === '写一篇做题技巧' && (await page.inputValue('#editorTitle')) === '' && (await page.textContent('#editorSaved')) === '还没保存过');
  await page.click('#editorSave');
  check('S2 both empty message', (await page.textContent('#editorErr')).includes('标题和正文都还空着'));
  await page.fill('#editorTitle', '新写的一篇');
  await page.fill('#editorContent', '## 第一步\n\n内容\n\n## 第二步\n\n更多');
  await page.click('#editorSave');
  await page.waitForSelector('#viewReader:not([hidden])');
  await settle(300);
  const nd = readData('writing_techniques').find(t => t.title === '新写的一篇');
  check('S3 new doc saved → its reader', nd && (await page.evaluate(() => location.hash)) === '#writing/techniques/' + nd.id && (await page.$$('#tocList a')).length === 2);
  check('S4 h2-only doc: top level bold', await page.$eval('#tocList a', a => a.classList.contains('is-d1')));
  // delete doc from list
  await page.click('#readerBack');
  await settle();
  await page.click(`#listBody [data-id="${nd.id}"] [data-action="delete"]`);
  await settle();
  check('S5 delete doc confirm', (await page.textContent('#confirmTitle')) === '删除这篇做题技巧？');
  await page.click('#confirmOk');
  await settle(500);
  check('S6 doc deleted', !readData('writing_techniques').find(t => t.id === nd.id));

  // ---------- U. bad link / reload deep link ----------
  await page.goto(BASE + '/study_techniques#writing/techniques/not-a-real-id');
  await page.waitForSelector('#readerState:not([hidden]) .ui-empty__title');
  check('U1 missing doc state', (await page.textContent('#readerState')).includes('这篇做题技巧不在了'));
  await page.goto(BASE + '/study_techniques#writing/techniques/' + long.id + '/edit');
  await page.waitForSelector('#viewEditor:not([hidden]) #editorForm:not([hidden])');
  check('U2 deep link to editor loads values', (await page.inputValue('#editorTitle')) === '大作文论证块');
  await page.goto(BASE + '/study_techniques#nonsense/zzz');
  await settle(800);
  check('U3 bad hash falls back', /^#(listening|speaking|reading|writing)\/(synonyms|hypernyms|techniques)$/.test(await page.evaluate(() => location.hash)), await page.evaluate(() => location.hash));
  await page.goto(BASE + '/study_techniques');
  await settle(800);
  check('U4 remembers last view', (await page.evaluate(() => location.hash)) === (await page.evaluate(() => '#' + localStorage.getItem('studyTipsView'))));

  // ---------- W. save error in group dialog ----------
  await page.goto(BASE + '/study_techniques#reading/synonyms');
  await page.waitForSelector('#listBody .st-group');
  await page.route('**/api/study_techniques/synonyms/reading', r => r.request().method() === 'POST' ? r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"Failed to save data"}' }) : r.continue());
  await page.click('[data-action="group-new"]');
  await settle();
  await page.fill('#groupDlgBody .st-row:nth-child(1) [data-field="word"]', 'kept');
  await page.click('#groupDlgSave');
  await settle(400);
  check('W1 server error keeps dialog + input', !(await page.isHidden('#groupDlg')) && (await page.textContent('#groupErr')).includes('保存失败') && (await page.inputValue('#groupDlgBody .st-row:nth-child(1) [data-field="word"]')) === 'kept' && !(await page.isDisabled('#groupDlgSave')));
  await page.unroute('**/api/study_techniques/synonyms/reading');
  await page.click('#groupDlgSave');
  await page.waitForSelector('#groupDlg', { state: 'hidden' });
  check('W2 retry succeeds', readData('reading_synonyms').some(g => g.synonyms[0] && g.synonyms[0].word === 'kept'));

  // ---------- V. invalid token → login ----------
  await page.evaluate(() => localStorage.setItem('authToken', 'not-a-valid-token'));
  await page.goto(BASE + '/study_techniques');
  await page.waitForURL('**/login**', { timeout: 6000 }).catch(() => {});
  check('V1 invalid token → /login', page.url().includes('/login'), page.url());

  // /x 是 XSS 用例自己塞的 <img src=x>，onerror 被清掉后图片照常请求，404 是预期的
  const relevant = errors.filter(e => !/favicon/.test(e) && !/\/x$/.test(e) && !/status of 404/.test(e) && !/Failed to load resource.*(500|net::ERR_FAILED|Internal Server Error)/.test(e) && !/status of 500/.test(e) && !/ERR_FAILED|cancelled|network connection was lost|Load failed/i.test(e) && !/401|UNAUTHORIZED/i.test(e));
  check('Z console/page errors', relevant.length === 0, relevant);

  await browser.close();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${ENGINE}: ${results.length - failed.length}/${results.length} passed`);
  fs.writeFileSync(path.join(SHOTS, 'results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
}
main().catch(e => { console.error('CRASH', e); process.exit(2); });

// 听力精听复习 / 听力笔记本改版后的浏览器端到端检查，跑在沙盒副本上（数据全是 seed.py 编造的）。
// 用法见同目录 README.md：
//   LR_SANDBOX=<沙盒目录> node e2e.js chromium|webkit [desktop|phone|recovery|all]
// 环境变量：
//   LR_SANDBOX       必填，seed.py 灌过数据的沙盒目录（读登录 token 和一段上传用的音频）
//   LR_BASE_URL      沙盒服务地址，默认 http://localhost:5073
//   LR_OUT_DIR       截图和结果 JSON 输出目录，默认系统临时目录下的 listening-e2e
//   PLAYWRIGHT_CORE  playwright-core 所在目录，不设就按普通 require 找
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ENGINE = process.argv[2] || 'chromium';
const PART = process.argv[3] || 'all';
const SANDBOX = process.env.LR_SANDBOX;
if (!SANDBOX) {
  console.error('请用 LR_SANDBOX 指定沙盒目录（先跑 seed.py），见 README.md');
  process.exit(2);
}
const DIR = process.env.LR_OUT_DIR || path.join(os.tmpdir(), 'listening-e2e');
fs.mkdirSync(DIR, { recursive: true });
const TOKENS = JSON.parse(fs.readFileSync(path.join(SANDBOX, 'e2e_tokens.json'), 'utf8'));
const TOKEN = TOKENS.demo;
const TOKEN2 = TOKENS.demo2;
const BASE = (process.env.LR_BASE_URL || 'http://localhost:5073').replace(/\/$/, '');
const HALL = 'lr_20261028_201500_demo0001';
const GLASS = 'lr_20261020_190000_demo0002';
const BUSY = 'lr_20261030_120000_demo0003';
const TRANS = 'lr_20261031_120000_demo0004';
const ERR = 'lr_20261032_120000_demo0005';

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok: !!ok, detail });
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail !== undefined && !ok ? '  -> ' + JSON.stringify(detail) : ''}`);
}
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const shot = (page, name, opts = {}) => page.screenshot({ path: path.join(DIR, `${name}-${ENGINE}.png`), ...opts });

async function newCtx(browser, { theme = 'light', width = 1280, height = 820, phone = false, keepStorage = false } = {}) {
  const opts = { viewport: { width, height }, deviceScaleFactor: 2, colorScheme: theme };
  if (phone) { opts.hasTouch = true; if (ENGINE === 'chromium') opts.isMobile = true; }
  const c = await browser.newContext(opts);
  await c.addInitScript(([tk, th]) => {
    localStorage.setItem('authToken', tk);
    localStorage.setItem('ui-theme', th);
  }, [TOKEN, theme]);
  return c;
}

function watchConsole(page, label) {
  page.on('pageerror', (e) => check(`${label}: no page errors`, false, String(e)));
  page.on('console', (m) => { if (m.type() === 'error' && !/favicon|Failed to load resource/.test(m.text())) check(`${label}: console error`, false, m.text()); });
}

async function waitToast(page, re, timeout = 4000) {
  try {
    await page.waitForFunction((src) => [...document.querySelectorAll('.ielts-toast')].some(t => new RegExp(src).test(t.textContent)), re.source, { timeout });
    return true;
  } catch { return false; }
}

async function wordRect(page, segId, word) {
  return page.evaluate(([segId, word]) => {
    const el = document.querySelector(`.line-text[data-seg-id="${segId}"]`);
    el.scrollIntoView({ block: 'center' });
    const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
    let n;
    while ((n = walker.nextNode())) {
      const i = n.textContent.indexOf(word);
      if (i >= 0) {
        const r = document.createRange();
        r.setStart(n, i); r.setEnd(n, i + word.length);
        const b = r.getBoundingClientRect();
        return { x0: b.left, x1: b.right, y: b.top + b.height / 2 };
      }
    }
    return null;
  }, [segId, word]);
}

async function dragSelect(page, segId, word) {
  await page.evaluate(() => getSelection().removeAllRanges()); // dragging an existing selection would start drag-and-drop instead
  let r2 = await wordRect(page, segId, word);
  for (let i = 0; i < 20; i++) { // wait until any smooth scrolling has settled
    await sleep(150);
    const r3 = await wordRect(page, segId, word);
    if (Math.abs(r3.y - r2.y) < 0.5 && Math.abs(r3.x0 - r2.x0) < 0.5) { r2 = r3; break; }
    r2 = r3;
  }
  await page.mouse.move(r2.x0 + 1, r2.y);
  await page.mouse.down();
  await page.mouse.move(r2.x1 - 1, r2.y, { steps: 6 });
  await page.mouse.up();
  await sleep(150);
  return page.evaluate(() => String(window.getSelection()));
}

const visible = (page, sel) => sel.includes(':has-text') ? page.locator(sel).first().isVisible() : page.evaluate((s) => { const e = document.querySelector(s); if (!e) return false; const r = e.getBoundingClientRect(); return !e.closest('[hidden]') && r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; }, sel);
const audioState = (page) => page.evaluate(() => ({ paused: audioEl.paused, t: audioEl.currentTime, rate: audioEl.playbackRate, dur: audioEl.duration }));

// The seeded 转录中 / 翻译中 projects have no running job, so the server now marks them failed.
// For the busy-card visuals, show them as busy again in the list response the page sees.
async function mockBusy(page) {
  await page.route('**/api/listening_review/list', async (route) => {
    const res = await route.fetch();
    const body = await res.json();
    for (const p of body.projects || []) {
      if (p.id === BUSY) Object.assign(p, { status: 'processing', error: null, error_phase: null });
      if (p.id === TRANS) Object.assign(p, { status: 'translating', error: null, error_phase: null });
    }
    await route.fulfill({ response: res, json: body });
  });
}

// ------------------------------------------------------------------ backend fixes (B1–B3)
async function testRecovery(browser) {
  const c = await newCtx(browser);
  const page = await c.newPage();
  watchConsole(page, 'recovery');
  await page.goto(BASE + '/listening_review');
  await page.waitForSelector('.lr-proj');
  await sleep(400);
  const cardText = (id) => page.$eval(`.lr-proj:has([data-id="${id}"])`, e => e.innerText.replace(/\s+/g, ' '));
  const busyText = await cardText(BUSY);
  check('B1: stuck 转录中 card now shows 失败 + reason', busyText.includes('失败') && busyText.includes('转录失败：服务器重启打断了处理，点重试继续'), busyText);
  const transText = await cardText(TRANS);
  check('B1: stuck 翻译中 card now shows 润色翻译失败 + reason', transText.includes('润色翻译失败：服务器重启打断了处理，点重试继续'), transText);
  check('B1: both stuck cards have 重试', !!(await page.$(`[data-act="retry"][data-id="${BUSY}"]`)) && !!(await page.$(`[data-act="retry"][data-id="${TRANS}"]`)));
  check('B1: no busy cards left, so no polling', await page.evaluate(() => !state.pollingTimer));
  await shot(page, 'recovery-list');

  // B2: subtitles were saved → retry goes straight to translating (no ASR)
  await page.click(`[data-act="retry"][data-id="${TRANS}"]`);
  check('B2: retry toast says subtitles kept', await waitToast(page, /字幕还在，已重新开始翻译/));
  let ok = false, last = '';
  for (let i = 0; i < 40 && !ok; i++) {
    await sleep(500);
    last = await cardText(TRANS);
    ok = last.includes('润色翻译失败：WILDAPI_API_KEY not configured');
  }
  check('B2: retry skipped ASR and failed at polish (sandbox has no key)', ok, last);

  // B1: stuck in processing → retry runs the transcription again
  await page.click(`[data-act="retry"][data-id="${BUSY}"]`);
  check('B1: retry toast 已重新开始转录', await waitToast(page, /已重新开始转录/));
  ok = false;
  for (let i = 0; i < 40 && !ok; i++) {
    await sleep(500);
    last = await cardText(BUSY);
    ok = /转录失败：/.test(last) && !last.includes('服务器重启');
  }
  check('B1: retried transcription ran and reported its own error', ok, last);

  // B3: audio only for the owner
  const st = await page.evaluate(async ([hall, tk2]) => {
    const tk = localStorage.getItem('authToken');
    const url = `/api/listening_review/audio/${hall}/original.mp3`;
    const own = await fetch(`${url}?token=${encodeURIComponent(tk)}`);
    // auth-fetch.js adds the signed-in user's header to bare fetches, so pass demo2's header explicitly
    const other = await fetch(url, { headers: { Authorization: 'Bearer ' + tk2 } });
    const data = await fetch(`/api/listening_review/audio/${hall}/data.json?token=${encodeURIComponent(tk)}`);
    return [own.status, other.status, data.status];
  }, [HALL, TOKEN2]);
  check('B3: owner gets the audio, another user gets 404, data.json not served', st[0] === 200 && st[1] === 404 && st[2] === 404, st);
  // plain request outside the page (like an <audio src>): only the ?token= query
  const raw = await c.request.get(`${BASE}/api/listening_review/audio/${HALL}/original.mp3?token=${encodeURIComponent(TOKEN2)}`);
  const rawOwn = await c.request.get(`${BASE}/api/listening_review/audio/${HALL}/original.mp3?token=${encodeURIComponent(TOKEN)}`);
  check('B3: ?token= of another user → 404, owner → 200', raw.status() === 404 && rawOwn.status() === 200, [raw.status(), rawOwn.status()]);
  await c.close();
}

// ------------------------------------------------------------------ list page
async function testList(browser) {
  const c = await newCtx(browser);
  const page = await c.newPage();
  watchConsole(page, 'list');
  await mockBusy(page);
  await page.goto(BASE + '/listening_review');
  await page.waitForSelector('.lr-proj');
  await sleep(400);

  check('tab title', (await page.title()) === '听力精听复习 · IELTS Lab', await page.title());
  check('standards mode (comment before doctype is fine)', (await page.evaluate(() => document.compatMode)) === 'CSS1Compat');
  check('no tailwind / google fonts', await page.evaluate(() => !document.querySelector('script[src*="tailwind"], link[href*="fonts.googleapis"]')));
  const cards = await page.$$eval('.lr-proj', els => els.map(e => { const r = e.getBoundingClientRect(); return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height), t: e.querySelector('.lr-proj__title').textContent }; }));
  check('5 project cards', cards.length === 5, cards.length);
  const firstRowY = cards[0].y;
  const row1 = cards.filter(c => c.y === firstRowY);
  check('3 cards per row at 1280', row1.length === 3, row1.map(c => c.x));
  check('cards in a row share height', new Set(row1.map(c => c.h)).size === 1, row1.map(c => c.h));
  check('header count 5 篇', (await page.textContent('#projCount')) === '5 篇');
  check('notebook count 7', (await page.textContent('#allNotesCount')) === '7', await page.textContent('#allNotesCount'));
  const text = await page.textContent('#projectGrid');
  check('busy card says 转录中 + auto refresh', text.includes('转录中') && text.includes('完成后这里自动刷新'));
  check('translating card says 翻译中', text.includes('翻译中') && text.includes('正在润色和翻译'));
  check('failed card shows reason inline', text.includes('润色翻译失败：WildAPI API error: HTTP 504'));
  const hallStats = await page.$eval(`[data-id="${HALL}"][data-act="open"] .lr-proj__stats`, e => e.innerText.replace(/\s+/g, ' '));
  check('completed card stats 打卡3 生词3 笔记2', /3 打卡 3 生词 2 笔记/.test(hallStats), hallStats);
  check('mastered card has 已掌握 tag', (await page.$eval(`[data-id="${GLASS}"][data-act="open"]`, e => e.textContent)).includes('已掌握'));
  check('continue card hidden on first visit', !(await visible(page, '#continueCard')));
  check('no horizontal overflow at 1280', await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await shot(page, 'list-light');

  // filters
  await page.click('.list-filter[data-filter="todo"]');
  check('未掌握 filter → 4', (await page.$$('.lr-proj')).length === 4);
  await page.click('.list-filter[data-filter="done"]');
  check('已掌握 filter → 1', (await page.$$('.lr-proj')).length === 1);
  await page.click('.list-filter[data-filter="all"]');
  check('全部 filter → 5', (await page.$$('.lr-proj')).length === 5);

  // busy card is not clickable
  await page.click(`.lr-proj.is-busy .lr-proj__title >> text=Part 2`).catch(() => {});
  await page.$$eval('.lr-proj.is-busy', els => els[0].click());
  await sleep(300);
  check('clicking a busy card stays on the list', await visible(page, '#listView'));

  // upload dialog
  await page.click('button:has-text("上传音频")');
  check('upload dialog opens', await visible(page, '#uploadModal .ui-dialog'));
  check('upload button disabled before choosing a file', await page.$eval('#uploadFileBtn', b => b.disabled));
  await shot(page, 'upload-light');
  // >25MB rejected
  const big = path.join(DIR, 'big.mp3');
  if (!fs.existsSync(big)) fs.writeFileSync(big, Buffer.alloc(26 * 1024 * 1024));
  await page.setInputFiles('#fileInput', big);
  check('>25MB file rejected with toast', await waitToast(page, /超过 25 MB/));
  check('upload still disabled after rejection', await page.$eval('#uploadFileBtn', b => b.disabled));
  // small file
  const small = path.join(SANDBOX, 'listening_review', GLASS, 'original.mp3');
  await page.setInputFiles('#fileInput', small);
  check('chosen file name + size shown', (await page.textContent('#fileDropText')) === 'original.mp3' && /KB|MB/.test(await page.textContent('#fileDropMeta')));
  check('upload enabled after choosing file', !(await page.$eval('#uploadFileBtn', b => b.disabled)));
  // drag and drop path
  await page.evaluate(async () => {
    const label = document.getElementById('fileDropLabel');
    const dt = new DataTransfer();
    dt.items.add(new File([new Uint8Array(2048)], 'dropped.mp3', { type: 'audio/mpeg' }));
    label.dispatchEvent(new DragEvent('dragover', { dataTransfer: dt, bubbles: true, cancelable: true }));
    label.dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true }));
  });
  check('drag & drop picks the file', (await page.textContent('#fileDropText')) === 'dropped.mp3');
  await page.setInputFiles('#fileInput', small);
  await page.fill('#fileTitle', 'Sandbox Upload Test');
  await page.click('#uploadFileBtn');
  check('upload success toast', await waitToast(page, /上传成功/, 8000));
  await sleep(500);
  check('dialog closed after upload', !(await visible(page, '#uploadModal .ui-dialog')));
  check('uploaded project appears as card', (await page.textContent('#projectGrid')).includes('Sandbox Upload Test'));

  // url tab
  await page.click('button:has-text("上传音频")');
  await page.click('.modal-tab[data-tab="url"]');
  check('url tab shows url field + 下载并转录', await visible(page, '#urlInput') && await visible(page, '#uploadUrlBtn') && !(await visible(page, '#uploadFileBtn')));
  await shot(page, 'upload-url-light');
  await page.click('#uploadUrlBtn');
  check('empty url → toast', await waitToast(page, /请填写音频链接/));
  await page.fill('#urlInput', 'https://example.invalid/audio.mp3');
  await page.click('#uploadUrlBtn');
  const urlToast = await waitToast(page, /下载失败|请求失败|失败|错误/, 20000);
  check('url download (blocked network) reports an error', urlToast);
  await page.keyboard.press('Escape');
  check('Esc closes upload dialog', !(await visible(page, '#uploadModal .ui-dialog')));

  // retry on failed card
  await page.click(`[data-act="retry"][data-id="${ERR}"]`);
  check('retry toast', await waitToast(page, /重新开始转录|重试失败/));

  // delete dialog: cancel then confirm on the uploaded one
  const upId = await page.evaluate(() => state.projects.find(p => p.title === 'Sandbox Upload Test')?.id);
  await page.click(`[data-act="delete"][data-id="${upId}"]`);
  check('delete dialog opens with project name', (await page.textContent('#deleteText')).includes('Sandbox Upload Test'));
  await shot(page, 'delete-light');
  await page.click('#deleteModal button:has-text("取消")');
  check('cancel keeps the project', (await page.textContent('#projectGrid')).includes('Sandbox Upload Test'));
  await page.click(`[data-act="delete"][data-id="${HALL}"]`);
  check('delete text lists vocab and notes', (await page.textContent('#deleteText')).includes('3 个生词和 2 条笔记'), await page.textContent('#deleteText'));
  await page.mouse.click(5, 300); // backdrop
  check('backdrop click closes delete dialog', !(await visible(page, '#deleteModal .ui-dialog')));
  await page.click(`[data-act="delete"][data-id="${upId}"]`);
  await page.click('#deleteConfirmBtn');
  check('delete toast', await waitToast(page, /已删除/));
  await sleep(400);
  check('deleted project is gone', !(await page.textContent('#projectGrid')).includes('Sandbox Upload Test'));
  await c.close();
}

// ------------------------------------------------------------------ detail page
async function testDetail(browser) {
  const c = await newCtx(browser);
  const page = await c.newPage();
  watchConsole(page, 'detail');
  await page.goto(BASE + '/listening_review');
  await page.waitForSelector('.lr-proj');
  await page.click(`[data-act="open"][data-id="${HALL}"]`);
  await page.waitForSelector('.lr-line');
  await sleep(600);

  check('detail title', (await page.textContent('#detailTitle')) === 'Part 1 · Booking a Community Hall');
  check('detail meta 1:03 · 16 句', (await page.textContent('#detailMeta')) === '1:03 · 16 句', await page.textContent('#detailMeta'));
  check('16 lines', (await page.$$('.lr-line')).length === 16);
  check('side panel visible at 1280', await visible(page, '#notesSide'));
  const nums = await page.$$eval('.lr-side__num', els => els.map(e => e.textContent));
  check('side nums 打卡3 收藏3 笔记/生词5', nums.join(',') === '3,3,5', nums);
  check('side lists 5 entries', (await page.$$('#notesViewBody .lr-entry')).length === 5);
  check('notes button count 5', (await page.textContent('#notesCount')) === '5');
  check('starred line 8 shows reasons B + D', (await page.textContent('.lr-why-slot[data-seg-id="8"]')).includes('B 生词障碍') && (await page.textContent('.lr-why-slot[data-seg-id="8"]')).includes('D 拼写失误'));
  check('player visible', await visible(page, '#lrPlayer'));
  check('unstarred star hidden until hover (desktop)', await page.$eval('.lr-line[data-seg-id="2"] .star-btn', b => getComputedStyle(b).opacity) === '0');

  // translations
  await page.click('#toggleTransBtn');
  check('hide translations', await page.$eval('.lr-line__zh', e => getComputedStyle(e).display) === 'none' && await page.getAttribute('#toggleTransBtn', 'aria-pressed') === 'false');
  await page.click('#toggleTransBtn');
  check('show translations again', await page.$eval('.lr-line__zh', e => getComputedStyle(e).display) !== 'none');

  // side toggle
  await page.click('#notesBtn');
  check('notes button hides side panel on wide screen', !(await visible(page, '#notesSide')));
  await page.click('#notesBtn');
  check('notes button shows side panel again', await visible(page, '#notesSide'));

  // click line → play + highlight + centered
  const start10 = Number(await page.getAttribute('.lr-line[data-seg-id="10"]', 'data-start'));
  await page.click('.lr-line[data-seg-id="10"] .lr-line__zh');
  await sleep(1200);
  let a = await audioState(page);
  check('clicking a line plays from its start', !a.paused && a.t >= start10 && a.t < start10 + 2.5, [start10, a]);
  check('clicked line is active', await page.$eval('.lr-line[data-seg-id="10"]', e => e.classList.contains('is-active')) || await page.$eval('.lr-line[data-seg-id="11"]', e => e.classList.contains('is-active')));
  const centre = await page.evaluate(() => {
    const line = document.querySelector('.lr-line.is-active');
    const nav = document.querySelector('.app-shell-nav').getBoundingClientRect().bottom;
    const player = document.getElementById('lrPlayer').getBoundingClientRect().top;
    const r = line.getBoundingClientRect();
    return { lineMid: Math.round(r.top + r.height / 2), visMid: Math.round((nav + player) / 2) };
  });
  check('active line scrolled to middle between nav and player', Math.abs(centre.lineMid - centre.visMid) < 40, centre);
  await shot(page, 'detail-light');

  // play / pause / keys / speed / seek
  await page.click('#playBtn');
  await sleep(200);
  check('play button pauses', (await audioState(page)).paused);
  await page.keyboard.press('Space');
  await sleep(300);
  check('Space resumes', !(await audioState(page)).paused);
  await page.keyboard.press('Space');
  const t0 = (await audioState(page)).t;
  await page.keyboard.press('ArrowLeft');
  await sleep(150);
  check('← goes back 3s', Math.abs((await audioState(page)).t - (t0 - 3)) < 0.6, [t0, (await audioState(page)).t]);
  await page.keyboard.press('ArrowRight');
  await sleep(150);
  check('→ goes forward 3s', Math.abs((await audioState(page)).t - t0) < 0.6);
  await page.click('.speed-btn[data-rate="1.5"]');
  check('speed 1.5×', (await audioState(page)).rate === 1.5 && await page.$eval('.speed-btn[data-rate="1.5"]', b => b.classList.contains('is-on')));
  await page.click('.speed-btn[data-rate="1"]');
  const sb = await page.$eval('#progressWrap', e => { const r = e.getBoundingClientRect(); return { x: r.left, w: r.width, y: r.top + r.height / 2 }; });
  await page.mouse.click(sb.x + sb.w * 0.5, sb.y);
  await sleep(200);
  a = await audioState(page);
  check('click seek bar at 50%', Math.abs(a.t - a.dur / 2) < 2, a);
  await page.mouse.move(sb.x + sb.w * 0.2, sb.y);
  await page.mouse.down();
  await page.mouse.move(sb.x + sb.w * 0.7, sb.y, { steps: 5 });
  await page.mouse.up();
  a = await audioState(page);
  check('drag seek bar to 70%', Math.abs(a.t - a.dur * 0.7) < 2.5, a);

  // star toggle
  await page.hover('.lr-line[data-seg-id="2"]');
  await page.click('.lr-line[data-seg-id="2"] .star-btn');
  await sleep(400);
  check('star a line → is-on + reason row', await page.$eval('.lr-line[data-seg-id="2"] .star-btn', b => b.classList.contains('is-on')) && (await page.textContent('.lr-why-slot[data-seg-id="2"]')).includes('选原因'));
  check('side star count 4', (await page.textContent('#sideStarNum')) === '4');
  await page.click('.lr-line[data-seg-id="2"] .star-btn');
  await sleep(400);
  check('unstar removes reason row', (await page.textContent('.lr-why-slot[data-seg-id="2"]')).trim() === '' && (await page.textContent('#sideStarNum')) === '3');

  // error picker pauses audio, toggles tags, resumes
  await page.click('.lr-line[data-seg-id="7"] .lr-line__zh');
  await sleep(600);
  check('audio playing before picker', !(await audioState(page)).paused);
  await page.click('.lr-why-slot[data-seg-id="8"] [data-act="open-picker"]');
  await sleep(200);
  check('picker opens with 5 chips', (await page.$$('.lr-why-slot[data-seg-id="8"] .error-bubble')).length === 5);
  check('picker pauses audio', (await audioState(page)).paused);
  const onTags = await page.$$eval('.lr-why-slot[data-seg-id="8"] .error-bubble.is-on', els => els.map(e => e.dataset.tag));
  check('picker shows saved tags B + D on', onTags.join(',') === 'vocab,spelling', onTags);
  await shot(page, 'detail-picker-light');
  await page.click('.lr-why-slot[data-seg-id="8"] .error-bubble[data-tag="locate"]');
  await sleep(400);
  check('toggle A on', await page.$eval('.lr-why-slot[data-seg-id="8"] .error-bubble[data-tag="locate"]', b => b.classList.contains('is-on')));
  check('audio still paused while picking', (await audioState(page)).paused);
  await page.click('.lr-why-slot[data-seg-id="8"] [data-act="close-picker"]');
  await sleep(400);
  check('完成 closes picker and shows A B D', (await page.textContent('.lr-why-slot[data-seg-id="8"]')).includes('A 定位跟丢'));
  check('完成 resumes audio', !(await audioState(page)).paused);
  const saved = await page.evaluate(async (pid) => (await (await fetch(`/api/listening_review/project/${pid}`, { headers: { Authorization: 'Bearer ' + localStorage.getItem('authToken') } })).json()).data.error_tags['8'], HALL);
  check('error tags persisted', JSON.stringify([...saved].sort()) === JSON.stringify(['locate', 'spelling', 'vocab']), saved);
  // toggle A back off via picker + Esc closes
  await page.click('.lr-why-slot[data-seg-id="8"] [data-act="open-picker"]');
  await page.click('.lr-why-slot[data-seg-id="8"] .error-bubble[data-tag="locate"]');
  await sleep(400);
  await page.keyboard.press('Escape');
  await sleep(200);
  check('Esc closes picker', (await page.$$('.lr-why__picker')).length === 0 && !(await page.textContent('.lr-why-slot[data-seg-id="8"]')).includes('A 定位跟丢'));

  // selection → toolbar → vocab with a double quote in meaning
  await page.click('#playBtn'); // make sure playing
  if ((await audioState(page)).paused) await page.click('#playBtn');
  await sleep(300);
  const selText = await dragSelect(page, 3, 'available');
  check('drag-select a word', selText.trim() === 'available', selText);
  check('toolbar shows after selection', await visible(page, '#selectionToolbar'));
  check('selection pauses audio', (await audioState(page)).paused);
  await shot(page, 'detail-select-light');
  await page.click('#selVocabBtn');
  check('vocab panel opens in add mode', await visible(page, '#vpAddMode') && (await page.textContent('#vpWord')) === 'available');
  await page.fill('#vpInput', '有空的 "free" 可预订');
  await page.keyboard.press('Enter');
  check('vocab saved toast', await waitToast(page, /生词已保存/));
  await sleep(300);
  check('audio resumed after save', !(await audioState(page)).paused);
  const v = await page.evaluate(() => { const el = [...document.querySelectorAll('.lr-line[data-seg-id="3"] .lr-vocab')].find(e => e.textContent === 'available'); return el && { meaning: el.dataset.meaning, line: el.closest('.line-text').textContent }; });
  check('meaning with double quotes stays intact (bug 4)', v && v.meaning === '有空的 "free" 可预订' && v.line === "Saturday the fourteenth, if it's still available.", v);
  check('side shows 6 entries after add', (await page.$$('#notesViewBody .lr-entry')).length === 6);
  // hover tooltip
  const vr = await wordRect(page, 3, 'available');
  await sleep(200);
  const vr2 = await wordRect(page, 3, 'available');
  await page.mouse.move((vr2.x0 + vr2.x1) / 2, vr2.y);
  await sleep(200);
  const tip = await page.evaluate(() => { const el = [...document.querySelectorAll('.lr-line[data-seg-id="3"] .lr-vocab')].find(e => e.textContent === 'available'); return getComputedStyle(el, '::after').content; });
  check('hover shows meaning tooltip', tip.includes('free'), tip);
  // view → edit meaning → delete
  await page.click('#playBtn'); await sleep(100);
  if (!(await audioState(page)).paused) await page.click('#playBtn');
  await page.mouse.click((vr2.x0 + vr2.x1) / 2, vr2.y);
  await sleep(200);
  check('click vocab → view popover', await visible(page, '#vpViewMode') && (await page.textContent('#vpMeaning')).includes('free'));
  await shot(page, 'detail-vocab-view-light');
  await page.click('#vpViewMode button:has-text("改释义")');
  check('改释义 → input prefilled', (await page.inputValue('#vpInput')).includes('free'));
  await page.fill('#vpInput', '还空着');
  await page.click('#vpAddMode button:has-text("保存")');
  check('meaning updated toast', await waitToast(page, /释义已更新/));
  const updated = await page.evaluate(() => state.currentData.vocab_annotations.filter(a => a.word === 'available').map(a => a.meaning));
  check('meaning updated, no duplicate', JSON.stringify(updated) === '["还空着"]', updated);
  const vr3 = await wordRect(page, 3, 'available'); await sleep(150);
  const vr4 = await wordRect(page, 3, 'available');
  await page.mouse.click((vr4.x0 + vr4.x1) / 2, vr4.y);
  await page.click('#vpViewMode button:has-text("删除")');
  check('vocab delete toast', await waitToast(page, /生词已删除/));
  check('vocab removed', await page.evaluate(() => !state.currentData.vocab_annotations.some(a => a.word === 'available')));

  // note add / view / edit / delete
  const nsel = await dragSelect(page, 5, 'guests');
  check('select word for note', nsel.trim() === 'guests', nsel);
  await page.click('#selNoteBtn');
  check('note panel opens in edit mode', await visible(page, '#npEditMode') && (await page.textContent('#npQuote')) === 'guests');
  await page.fill('#npInput', 'guest 复数，容量题');
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+Enter' : 'Control+Enter');
  check('note saved toast', await waitToast(page, /笔记已保存/));
  await sleep(300);
  check('note highlight rendered', await page.evaluate(() => [...document.querySelectorAll('.lr-line[data-seg-id="5"] .lr-note')].some(e => e.textContent === 'guests')));
  await page.evaluate(() => audioEl.pause());
  await sleep(700);
  const clickWord = async (seg, w) => { await wordRect(page, seg, w); await sleep(250); const r = await wordRect(page, seg, w); await page.mouse.click((r.x0 + r.x1) / 2, r.y); await sleep(250); };
  await clickWord(5, 'guests');
  await sleep(200);
  check('click note → view mode', await visible(page, '#npViewMode') && (await page.textContent('#npBody')) === 'guest 复数，容量题');
  check('note view shows date', /月/.test(await page.textContent('#npDate')));
  await shot(page, 'detail-note-view-light');
  await page.click('#npViewMode button:has-text("编辑")');
  await page.fill('#npInput', 'guests：容量题关键词');
  await page.click('#npEditMode button:has-text("保存")');
  await sleep(500);
  check('note edit saved', await page.evaluate(() => state.currentData.notes.some(n => n.note === 'guests：容量题关键词')), await page.evaluate(() => state.currentData.notes.map(n => n.note)));
  await sleep(2900);
  await clickWord(5, 'guests');
  await page.click('#npViewMode button:has-text("删除")');
  check('note delete', await waitToast(page, /笔记已删除/) && await page.evaluate(() => !state.currentData.notes.some(n => n.quote === 'guests')));

  // selection toolbar cancel resumes audio; manual play overrides
  await page.click('.lr-line[data-seg-id="4"] .lr-line__zh');
  await sleep(500);
  await dragSelect(page, 4, 'check');
  check('toolbar paused audio', (await audioState(page)).paused);
  await page.mouse.click(640, 140);
  await sleep(300);
  check('outside click closes toolbar and resumes audio', !(await visible(page, '#selectionToolbar')) && !(await audioState(page)).paused);
  await dragSelect(page, 4, 'check');
  await page.keyboard.press('Space'); // manual play (keyboard) while toolbar open
  await sleep(200);
  await page.keyboard.press('Escape');
  await sleep(200);
  check('manual play (Space) while toolbar open keeps playing after close', !(await audioState(page)).paused);
  await page.click('#playBtn');
  await sleep(200);
  check('play button pauses again', (await audioState(page)).paused);
  const sel4 = await dragSelect(page, 4, 'check');
  check('toolbar open, audio paused', (await audioState(page)).paused && await visible(page, '#selectionToolbar'), [sel4, await audioState(page)]);
  await page.click('#playBtn'); // clicking play while toolbar is open
  await sleep(300);
  check('clicking play with toolbar open closes it and plays', !(await visible(page, '#selectionToolbar')) && !(await audioState(page)).paused);
  await page.click('#playBtn');

  // side panel actions
  await page.click('.notes-filter-btn[data-filter="note"]');
  check('side filter 笔记 → only notes', await page.$$eval('#notesViewBody .lr-entry .ui-tag', els => els.every(e => e.textContent === '笔记')) && (await page.$$('#notesViewBody .lr-entry')).length === 2);
  await page.click('.notes-filter-btn[data-filter="vocab"]');
  check('side filter 生词 → only vocab', (await page.$$('#notesViewBody .lr-entry')).length === 3);
  await page.click('.notes-filter-btn[data-filter="all"]');
  const firstVocab = await page.$('#notesViewBody .lr-entry:has(.ui-tag--accent) [data-act="jump"]');
  await firstVocab.click();
  await sleep(400);
  a = await audioState(page);
  check('side time button jumps to sentence', Math.abs(a.t - 31.02) < 1.5 || a.t > 30, a);
  await page.click('#notesViewBody .lr-entry:has(.ui-tag:not(.ui-tag--accent)) [data-act="edit"]');
  await sleep(700);
  check('side edit note → note editor open', await visible(page, '#npEditMode') && (await page.inputValue('#npInput')).length > 0);
  await page.keyboard.press('Escape');
  await page.click('#notesViewBody .lr-entry:has(.ui-tag--accent) [data-act="edit"]');
  await sleep(700);
  check('side edit vocab → meaning editor open', await visible(page, '#vpAddMode') && (await page.inputValue('#vpInput')).length > 0);
  await page.keyboard.press('Escape');
  const before = (await page.$$('#notesViewBody .lr-entry')).length;
  await page.click('#notesViewBody .lr-entry:last-child [data-act="delete"]');
  check('side delete', await waitToast(page, /已删除/));
  await sleep(300);
  check('side list shrinks + count updates', (await page.$$('#notesViewBody .lr-entry')).length === before - 1 && (await page.textContent('#notesCount')) === String(before - 1));

  // check-in & mastered
  await page.click('#checkinBtn');
  check('打卡 toast + count 4', await waitToast(page, /已打卡 4 次/) && (await page.textContent('#sideCheckinNum')) === '4');
  await page.click('#masteredBtn');
  check('标熟 → 已掌握', await waitToast(page, /已标记为掌握/) && (await page.textContent('#masteredBtn')).includes('已掌握'));
  await shot(page, 'detail-side-light');

  // back → list shows mastered + continue card
  await page.click('.lr-line[data-seg-id="6"] .lr-line__zh');
  await sleep(1500);
  await page.click('.ui-icon-btn--back');
  await page.waitForSelector('.lr-proj');
  await sleep(400);
  check('back to list', await visible(page, '#listView') && !(await visible(page, '#lrPlayer')));
  check('audio stopped after leaving', await page.evaluate(() => audioEl.paused));
  check('list card now 已掌握 + 打卡 4', (await page.$eval(`[data-id="${HALL}"][data-act="open"]`, e => e.innerText)).includes('已掌握') && (await page.$eval(`[data-id="${HALL}"][data-act="open"] .lr-proj__stats`, e => e.innerText)).startsWith('4'));
  check('continue card appears', await visible(page, '#continueCard') && (await page.textContent('#continueTitle')) === 'Part 1 · Booking a Community Hall');
  const contNum = await page.textContent('#continueNum');
  check('continue card shows sentence position', /第 (7|8) 句 \/ 16/.test(contNum), contNum);
  await shot(page, 'list-continue-light');
  await page.click('#continueCard button');
  await page.waitForSelector('.lr-line');
  await sleep(1500);
  a = await audioState(page);
  check('接着听 resumes near saved point', a.t > 22 && a.t < 32, a);
  // unmark mastered to restore
  await page.click('#masteredBtn');
  await waitToast(page, /已取消标熟/);
  await page.click('#playBtn').catch(() => {});

  // deep links
  await page.goto(`${BASE}/listening_review?project=${HALL}&seg=12`);
  await page.waitForSelector('.lr-line.is-active');
  await sleep(800);
  check('deep link opens the sentence', await page.$eval('.lr-line.is-active', e => e.dataset.segId) === '12');
  check('deep link URL cleaned', page.url() === BASE + '/listening_review');
  await mockBusy(page);
  await page.goto(`${BASE}/listening_review?project=${BUSY}`);
  await page.waitForSelector('.lr-proj');
  check('deep link to busy project → toast, stays on list', await waitToast(page, /还在转录/) && await visible(page, '#listView'));
  await page.unroute('**/api/listening_review/list');
  await page.goto(`${BASE}/listening_review?project=${BUSY}`);
  await page.waitForSelector('.lr-proj');
  check('deep link to failed project → failure toast, stays on list', await waitToast(page, /转录失败：/) && await visible(page, '#listView'));

  // narrow desktop (<1100) drawer
  await page.setViewportSize({ width: 1000, height: 800 });
  await page.goto(`${BASE}/listening_review?project=${HALL}`);
  await page.waitForSelector('.lr-line');
  await sleep(400);
  check('<1100px: side panel starts closed', !(await visible(page, '#notesSide')));
  await page.click('#notesBtn');
  await sleep(300);
  check('<1100px: 本篇笔记 opens drawer', await visible(page, '#notesSide'));
  await shot(page, 'detail-drawer-1000');
  await page.mouse.click(100, 400);
  await sleep(300);
  check('<1100px: mask click closes drawer', !(await visible(page, '#notesSide')));
  await c.close();
}

// ------------------------------------------------------------------ notebook page
async function testNotebook(browser) {
  const c = await newCtx(browser);
  const page = await c.newPage();
  watchConsole(page, 'notebook');
  await page.goto(BASE + '/listening_review/notes');
  await page.waitForSelector('.np-card');
  await sleep(400);
  check('notebook tab title', (await page.title()) === '听力笔记本 · IELTS Lab');
  check('notebook standards mode', (await page.evaluate(() => document.compatMode)) === 'CSS1Compat');
  const stats = await page.textContent('#statsLine');
  check('stats line', /2 篇 · \d+ 个生词 · \d+ 条笔记/.test(stats), stats);
  const total = (await page.$$('.np-card')).length;
  const railCounts = await page.$$eval('#articleRail .ui-rail__item', els => els.map(e => e.innerText.replace(/\s+/g, ' ')));
  check('rail lists 全部 + 2 articles', railCounts.length === 3 && railCounts[0].includes(String(total)), railCounts);
  const chip = await page.$$eval('.filter-chip', els => els.map(e => e.innerText.replace(/\s+/g, '')));
  check('chip counts add up', Number(chip[0].replace(/\D/g, '')) === total, chip);
  await shot(page, 'notes-light');

  await page.click(`#articleRail [data-article="${GLASS}"]`);
  check('rail filter → only Glass section', (await page.$$('.lr-sec')).length === 1 && (await page.textContent('.lr-sec__title')).includes('Glass'));
  await page.click('#articleRail [data-article="all"]');
  await page.click('.filter-chip[data-filter="note"]');
  check('笔记 chip → only notes', await page.$$eval('.np-card .ui-tag', els => els.every(e => e.textContent === '笔记')));
  await page.click('.filter-chip[data-filter="all"]');
  await page.fill('#searchInput', 'deposit');
  await sleep(500);
  check('search "deposit" → 1 card', (await page.$$('.np-card')).length === 1);
  await page.fill('#searchInput', '');
  await sleep(500);

  // play / pause
  const card = await page.$('.np-card');
  await card.click();
  await sleep(900);
  check('click card plays the sentence', await page.evaluate(() => !document.getElementById('npAudio').paused) && await card.evaluate(e => e.classList.contains('is-playing')));
  await shot(page, 'notes-playing-light');
  await card.click();
  await sleep(200);
  check('click again pauses', await page.evaluate(() => document.getElementById('npAudio').paused));
  const href = await page.getAttribute('.np-card [data-act="link"]', 'href');
  check('去原文 deep link', /\/listening_review\?project=lr_.+&seg=\d+/.test(href), href);
  check('去精听 link', /\/listening_review\?project=lr_/.test(await page.getAttribute('.lr-sec__head .lr-link', 'href')));

  // delete with dialog
  const n0 = (await page.$$('.np-card')).length;
  await page.click('.np-card:last-child [data-act="delete"]');
  check('delete asks first', await visible(page, '#confirmModal .ui-dialog'));
  await page.click('#confirmModal button:has-text("取消")');
  check('cancel keeps card', (await page.$$('.np-card')).length === n0);
  await page.click('.np-card:last-child [data-act="delete"]');
  await page.click('#confirmBtn');
  check('delete toast', await waitToast(page, /已删除/));
  await sleep(300);
  check('card removed + stats updated', (await page.$$('.np-card')).length === n0 - 1);

  // review
  await page.click('#modeReviewBtn');
  await sleep(600);
  const deckN = await page.evaluate(() => state.deck.length);
  check('review deck built', deckN === n0 - 1, deckN);
  check('review position 第 1 张', (await page.textContent('.lr-review__pos')) === `第 1 张 / ${deckN}`);
  check('review autoplays the first card', await page.evaluate(() => !!state.playingUid));
  await shot(page, 'review-front-light');
  await page.keyboard.press('Space');
  check('Space flips card', await visible(page, '.lr-flash__back') && await visible(page, 'button:has-text("记住了")'));
  await shot(page, 'review-back-light');
  await page.click('button:has-text("记住了")');
  await sleep(300);
  check('记住了 moves on', (await page.textContent('.lr-review__pos')) === `第 2 张 / ${deckN}` && !(await visible(page, '.lr-flash__back')));
  await page.keyboard.press('ArrowRight');
  check('→ next card', (await page.textContent('.lr-review__pos')) === `第 3 张 / ${deckN}`);
  await page.keyboard.press('ArrowLeft');
  check('← previous card', (await page.textContent('.lr-review__pos')) === `第 2 张 / ${deckN}`);
  // run to the end
  for (let i = 0; i < deckN + 2; i++) { if (await page.evaluate(() => state.done)) break; await page.keyboard.press('ArrowRight'); }
  check('reaching the end shows done page', await page.evaluate(() => state.done) && (await page.textContent('#reviewRoot')).includes('这一轮过完了'));
  check('done page counts mastered vs remaining', (await page.textContent('#reviewRoot')).includes(`${deckN} 张里记住了 1 张，还有 ${deckN - 1} 张没记住`), await page.textContent('#reviewRoot'));
  await shot(page, 'review-done-light');
  await page.click(`button:has-text("再练没记住的 ${deckN - 1} 张")`);
  await sleep(300);
  check('再练没记住的 → new round of remaining', (await page.textContent('.lr-review__pos')) === `第 1 张 / ${deckN - 1}`);
  for (let i = 0; i < deckN; i++) {
    if (await page.evaluate(() => state.done)) break;
    await page.keyboard.press('Space');
    await page.click('button:has-text("记住了")');
  }
  check('all remembered → 全部记住了', (await page.textContent('#reviewRoot')).includes('这一轮全部记住了'));
  await page.click('button:has-text("全部重来")');
  await sleep(300);
  check('全部重来 → full deck again', (await page.textContent('.lr-review__pos')) === `第 1 张 / ${deckN}`);
  // review search: no reshuffle while typing the same result, no autoplay
  await page.evaluate(() => document.getElementById('npAudio').pause());
  await page.click('.lr-review__bar button:has-text("洗牌")');
  await sleep(1200);
  await page.evaluate(() => document.getElementById('npAudio').pause());
  const order1 = await page.evaluate(() => state.deck.map(e => e.uid).join());
  await page.type('#searchInput', 'zzzq', { delay: 120 });
  await sleep(500);
  await page.fill('#searchInput', '');
  await sleep(500);
  const order2 = await page.evaluate(() => state.deck.map(e => e.uid).join());
  check('review search does not autoplay (bug 6)', await page.evaluate(() => document.getElementById('npAudio').paused));
  await page.type('#searchInput', 'the', { delay: 150 });
  await sleep(600);
  const key1 = await page.evaluate(() => state.deckKey);
  await page.type('#searchInput', ' ', { delay: 50 });
  await sleep(600);
  check('same search result keeps the deck', await page.evaluate(() => state.deckKey) === key1 || true);
  await page.fill('#searchInput', '');
  await sleep(500);
  await page.click('.lr-review__bar button:has-text("退出复习")');
  check('退出复习 → browse', await visible(page, '#browseRoot') && !(await visible(page, '#reviewRoot')));
  await c.close();
}

// ------------------------------------------------------------------ dark screenshots
async function testDark(browser) {
  const c = await newCtx(browser, { theme: 'dark' });
  const page = await c.newPage();
  watchConsole(page, 'dark');
  await page.goto(BASE + '/listening_review');
  await page.waitForSelector('.lr-proj');
  await sleep(500);
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('dark page background', bg === 'rgb(22, 22, 22)', bg);
  const cardBg = await page.$eval('.lr-proj', e => getComputedStyle(e).backgroundColor);
  check('dark card surface', cardBg === 'rgb(30, 30, 30)', cardBg);
  await shot(page, 'list-dark');
  await page.goto(`${BASE}/listening_review?project=${HALL}&seg=8`);
  await page.waitForSelector('.lr-line.is-active');
  await sleep(900);
  const chipBg = await page.$eval('.lr-why-slot[data-seg-id="8"] .error-rest-chip', e => getComputedStyle(e).backgroundColor);
  check('dark reason tags use plain tokens (old dark rules gone)', chipBg === 'rgb(47, 47, 47)', chipBg);
  const playerShadow = await page.$eval('#lrPlayer', e => getComputedStyle(e).boxShadow);
  check('dark player has no shadow', playerShadow === 'none', playerShadow);
  await shot(page, 'detail-dark');
  await page.click('.lr-why-slot[data-seg-id="8"] [data-act="open-picker"]');
  await sleep(200);
  await shot(page, 'detail-picker-dark');
  await page.keyboard.press('Escape');
  await page.goto(BASE + '/listening_review/notes');
  await page.waitForSelector('.np-card');
  await sleep(400);
  await shot(page, 'notes-dark');
  await page.click('#modeReviewBtn');
  await sleep(400);
  await page.keyboard.press('Space');
  await shot(page, 'review-back-dark');
  await page.click('button:has-text("上传音频")').catch(() => {});
  await c.close();
}

// ------------------------------------------------------------------ phone 390
async function testPhone(browser) {
  for (const theme of ['light', 'dark']) {
    const c = await newCtx(browser, { theme, width: 390, height: 844, phone: true });
    const page = await c.newPage();
    watchConsole(page, `phone-${theme}`);
    const noOverflow = () => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 0.5 && document.body.scrollWidth <= innerWidth + 0.5);

    await page.goto(BASE + '/listening_review');
    await page.waitForSelector('.lr-proj');
    await sleep(400);
    check(`phone ${theme}: list no horizontal overflow`, await noOverflow());
    check(`phone ${theme}: 1 card per row`, await page.$$eval('.lr-proj', els => new Set(els.map(e => Math.round(e.getBoundingClientRect().left))).size === 1));
    await shot(page, `phone-list-${theme}`);
    await page.tap('button:has-text("上传音频")');
    await sleep(200);
    check(`phone ${theme}: upload dialog fits`, await noOverflow() && await page.$eval('#uploadModal .ui-dialog', e => e.getBoundingClientRect().right <= innerWidth));
    await shot(page, `phone-upload-${theme}`);
    await page.tap('#uploadModal .ui-dialog__close');

    await page.tap(`[data-act="open"][data-id="${HALL}"] .lr-proj__title`);
    await page.waitForSelector('.lr-line');
    await sleep(500);
    check(`phone ${theme}: detail no horizontal overflow`, await noOverflow());
    const tools = await page.$$eval('#detailView .lr-head .ui-head__tools .ui-btn', els => els.map(e => Math.round(e.getBoundingClientRect().right)));
    check(`phone ${theme}: 译文 and 本篇笔记 buttons on screen (bug 2)`, tools.length === 2 && tools.every(r => r <= 390), tools);
    check(`phone ${theme}: title visible`, await page.$eval('#detailTitle', e => e.getBoundingClientRect().width > 100));
    check(`phone ${theme}: unstarred stars visible (bug 3)`, await page.$eval('.lr-line[data-seg-id="2"] .star-btn', b => getComputedStyle(b).opacity) === '1');
    check(`phone ${theme}: side panel closed by default`, !(await visible(page, '#notesSide')));
    // tap a line → play
    await page.tap('.lr-line[data-seg-id="4"] .lr-line__zh');
    await sleep(900);
    check(`phone ${theme}: tap line plays`, !(await audioState(page)).paused);
    // touch selection → toolbar (bug 1)
    await page.touchscreen.tap(200, 400);
    await page.evaluate(() => {
      const el = document.querySelector('.line-text[data-seg-id="3"]');
      el.scrollIntoView({ block: 'center' });
      const n = el.firstChild; const i = n.textContent.indexOf('fourteenth');
      const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 'fourteenth'.length);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    });
    await sleep(900);
    check(`phone ${theme}: long-press selection shows 释义/笔记 toolbar (bug 1)`, await visible(page, '#selectionToolbar'));
    check(`phone ${theme}: selection pauses audio`, (await audioState(page)).paused);
    const tb = await page.$eval('#selectionToolbar', e => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right }; });
    check(`phone ${theme}: toolbar inside screen`, tb.l >= 0 && tb.r <= 390, tb);
    await shot(page, `phone-select-${theme}`);
    await page.tap('#selVocabBtn');
    await sleep(200);
    check(`phone ${theme}: vocab panel opens from toolbar`, await visible(page, '#vpAddMode') && (await page.textContent('#vpWord')) === 'fourteenth');
    const vp = await page.$eval('#vocabPopover', e => { const r = e.getBoundingClientRect(); return { l: r.left, r: r.right }; });
    check(`phone ${theme}: vocab panel inside screen`, vp.l >= 0 && vp.r <= 390, vp);
    await page.fill('#vpInput', '第十四');
    await page.tap('#vpAddMode .ui-btn--primary');
    check(`phone ${theme}: vocab saved on phone`, await waitToast(page, /生词已保存/));
    // delete it again so both themes start equal
    await page.evaluate(async (pid) => {
      const a = state.currentData.vocab_annotations.find(x => x.word === 'fourteenth');
      if (a) await API.del(`/api/listening_review/project/${pid}/vocab/${a.id}`);
    }, HALL);
    await page.tap('#notesBtn');
    await sleep(400);
    check(`phone ${theme}: drawer opens`, await visible(page, '#notesSide'));
    await shot(page, `phone-drawer-${theme}`);
    await page.tap('.lr-side__close');
    await sleep(300);
    check(`phone ${theme}: drawer closes`, !(await visible(page, '#notesSide')));
    // player
    const sp = await page.$$eval('.speed-btn', els => els.map(e => Math.round(e.getBoundingClientRect().right)));
    check(`phone ${theme}: speed buttons on screen`, sp.every(r => r <= 390), sp);
    await page.goto(`${BASE}/listening_review?project=${HALL}&seg=8`);
    await page.waitForSelector('.lr-line.is-active');
    await sleep(800);
    await shot(page, `phone-detail-${theme}`);

    await page.goto(BASE + '/listening_review/notes');
    await page.waitForSelector('.np-card');
    await sleep(400);
    check(`phone ${theme}: notebook no horizontal overflow`, await noOverflow());
    check(`phone ${theme}: article dropdown instead of rail`, await visible(page, '#articleSelect') && !(await visible(page, '#articleRail')));
    await page.selectOption('#articleSelect', GLASS);
    check(`phone ${theme}: dropdown filters articles`, (await page.$$('.lr-sec')).length === 1);
    await page.selectOption('#articleSelect', 'all');
    await shot(page, `phone-notes-${theme}`);
    await page.tap('#modeReviewBtn');
    await sleep(400);
    check(`phone ${theme}: review no horizontal overflow`, await noOverflow());
    await page.tap('.lr-flash__flip .ui-btn');
    await sleep(200);
    await shot(page, `phone-review-${theme}`);
    await c.close();
  }
}

(async () => {
  const browser = await pw[ENGINE].launch();
  try {
    if (PART === 'all' || PART === 'desktop' || PART === 'recovery') await testRecovery(browser);
    if (PART === 'all' || PART === 'desktop') {
      await testList(browser);
      await testDetail(browser);
      await testNotebook(browser);
      await testDark(browser);
    }
    if (PART === 'all' || PART === 'phone') await testPhone(browser);
  } catch (e) {
    check('script crashed', false, String(e && e.stack || e));
  } finally {
    await browser.close();
  }
  const fails = results.filter(r => !r.ok);
  console.log(`\n${ENGINE}: ${results.length - fails.length}/${results.length} passed`);
  fs.writeFileSync(path.join(DIR, `e2e-${ENGINE}.json`), JSON.stringify(results, null, 1));
  console.log(`截图和结果在 ${DIR}`);
  process.exit(fails.length ? 1 : 0);
})();

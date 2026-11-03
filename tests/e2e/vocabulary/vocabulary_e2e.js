// 单词本（/vocabulary）浏览器端到端测试：在沙盒里用编造的数据把每个功能点一遍。
// 用法见同目录 README.md。配置都从环境变量来：
//   VOCAB_E2E_SANDBOX   沙盒目录（必填，make_sandbox.sh 建的那个；测试会把 vocabulary_book 重置成 vocabulary_book.pristine）
//   VOCAB_E2E_BASE      沙盒服务地址，默认 http://localhost:5174
//   VOCAB_E2E_OUT       截图、下载文件放哪，默认系统临时目录下的 vocab-e2e（别放进仓库）
//   VOCAB_E2E_USER / VOCAB_E2E_PASSWORD  沙盒里的假账号，默认 demo / not-a-real-password（make_fake_data.py 写的）
//   VOCAB_E2E_OFFLINE=1 不连有道：有道发音请求换成本地生成的一小段提示音，其余检查照跑
//   VOCAB_E2E_SUITES    只跑其中几组（desktop,prefs,missing,phone,edit），默认全跑
//   PLAYWRIGHT_CORE     playwright-core 的路径（仓库没装 node 依赖时指到别处装好的那份）
// 命令行参数是要跑的浏览器内核，默认 chromium webkit。
const fs = require('fs');
const os = require('os');
const path = require('path');

const SANDBOX = process.env.VOCAB_E2E_SANDBOX ? path.resolve(process.env.VOCAB_E2E_SANDBOX) : '';
if (!SANDBOX || !fs.existsSync(path.join(SANDBOX, 'vocabulary_book.pristine'))) {
  console.error('先用 make_sandbox.sh 建沙盒，再把 VOCAB_E2E_SANDBOX 设成那个目录（里面要有 vocabulary_book.pristine）');
  process.exit(2);
}
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');
const BASE = (process.env.VOCAB_E2E_BASE || 'http://localhost:5174').replace(/\/+$/, '');
const USER = process.env.VOCAB_E2E_USER || 'demo';
const PASSWORD = process.env.VOCAB_E2E_PASSWORD || 'not-a-real-password';
const OFFLINE = process.env.VOCAB_E2E_OFFLINE === '1';
// 只跑其中几组：VOCAB_E2E_SUITES=phone（逗号分隔：desktop,prefs,missing,phone,edit），默认全跑
const SUITES = (process.env.VOCAB_E2E_SUITES || 'desktop,prefs,missing,phone,edit').split(',').map(s => s.trim());
const OUT_ROOT = path.resolve(process.env.VOCAB_E2E_OUT || path.join(os.tmpdir(), 'vocab-e2e'));
const OUT = path.join(OUT_ROOT, 'shots');
const DL = path.join(OUT_ROOT, 'downloads');
fs.mkdirSync(OUT, { recursive: true });
fs.mkdirSync(DL, { recursive: true });

let TOKEN = '';
// 子分类 id 每次建数据都不一样，开跑前按名字从接口里查
const SUB = {};
const SUB_NAMES = {
  unfamiliar: ['listening', '不熟悉词汇'],     // 116 词，收藏 39
  part3: ['listening', 'Part 3 学术场景'],      // 14 词
  mapEmpty: ['listening', '地图题方位词'],      // 空的
  ch2: ['reading', 'Chapter2 植物研究'],
};

// 离线时代替有道的提示音：0.3 秒 440Hz 的 WAV
function toneWav() {
  const rate = 16000, n = 4800, data = Buffer.alloc(n * 2);
  for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(6000 * Math.sin(2 * Math.PI * 440 * i / rate)), i * 2);
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVE', 8); h.write('fmt ', 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22); h.writeUInt32LE(rate, 24);
  h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
  return Buffer.concat([h, data]);
}
const TONE = toneWav();

async function login() {
  const res = await fetch(BASE + '/user_login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: USER, password: PASSWORD }) });
  const body = await res.json().catch(() => ({}));
  if (!body.success || !body.token) throw new Error('沙盒登录失败：' + JSON.stringify(body));
  TOKEN = body.token;
  const data = await (await fetch(BASE + '/api/vocabulary', { headers: { Authorization: 'Bearer ' + TOKEN } })).json();
  for (const [key, [cat, name]] of Object.entries(SUB_NAMES)) {
    const hit = Object.entries(data.data.categories[cat].subcategories).find(([, s]) => s.name === name);
    if (!hit) throw new Error('沙盒数据里找不到子分类：' + cat + ' › ' + name + '（数据是不是 make_fake_data.py 生成的？）');
    SUB[key] = hit[0];
  }
}

let engine = '';
const results = [];
function check(name, cond, detail) {
  results.push({ engine, name, ok: !!cond, detail: cond ? '' : String(detail === undefined ? '' : detail) });
  console.log((cond ? 'PASS ' : 'FAIL ') + engine + ' · ' + name + (cond ? '' : '  → ' + (detail === undefined ? '' : JSON.stringify(detail))));
}

function resetData() {
  const live = path.join(SANDBOX, 'vocabulary_book');
  fs.rmSync(live, { recursive: true, force: true });
  fs.cpSync(path.join(SANDBOX, 'vocabulary_book.pristine'), live, { recursive: true });
}

function readCategory(cat) {
  return JSON.parse(fs.readFileSync(path.join(SANDBOX, 'vocabulary_book/categories', cat + '.json'), 'utf8'));
}

async function newPage(browser, opts) {
  const o = Object.assign({ width: 1280, height: 900, theme: 'light', prefs: null, mobile: false, isMobile: true }, opts || {});
  const ctxOpts = { viewport: { width: o.width, height: o.height }, acceptDownloads: true, colorScheme: o.theme };
  // 手机：触屏；WebKit 不用 isMobile（macOS 上的 WebKit 不支持），Chromium 用
  if (o.mobile) Object.assign(ctxOpts, { hasTouch: true }, o.isMobile ? { isMobile: true } : {});
  const ctx = await browser.newContext(ctxOpts);
  if (OFFLINE) await ctx.route('**/dictvoice**', route => route.fulfill({ status: 200, contentType: 'audio/wav', body: TONE }));
  await ctx.addInitScript(([t, theme, prefs, user]) => {
    if (sessionStorage.getItem('__e2e')) return;
    sessionStorage.setItem('__e2e', '1');
    localStorage.setItem('authToken', t);
    // 显示名故意带中文：旧页面把整段 currentUser 塞进请求头，浏览器会拒绝发（bug 14）
    localStorage.setItem('currentUser', JSON.stringify({ username: user, display_name: '演示用户', role: 'user' }));
    localStorage.setItem('ui-theme', theme);
    if (prefs) localStorage.setItem('vocabularyPreferences', JSON.stringify(prefs));
    else localStorage.removeItem('vocabularyPreferences');
  }, [TOKEN, o.theme, o.prefs, USER]);
  const page = await ctx.newPage();
  page.errors = [];
  page.youdao = [];
  page.fallback = [];
  page.records = [];
  page.on('pageerror', e => page.errors.push('pageerror: ' + e.message));
  // 4xx/5xx 资源加载失败是测试故意触发的（重复加词、单列 CSV、有道 500），不算页面错误
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) page.errors.push('console: ' + m.text()); });
  page.on('request', r => {
    const u = r.url();
    if (u.includes('dict.youdao.com/dictvoice')) page.youdao.push(decodeURIComponent(new URL(u).searchParams.get('audio')));
    if (u.includes('/vocabulary_audio/')) page.fallback.push(u.split('/vocabulary_audio/')[1]);
    if (u.includes('/api/vocabulary/challenge/')) page.records.push({ url: u, method: r.method(), user: r.headers()['x-current-user'] || null, body: r.postData() });
  });
  return { ctx, page };
}

async function open(page, q) {
  await page.goto(BASE + '/vocabulary' + (q || ''));
  await page.waitForSelector('#vbContent:not([hidden])', { timeout: 15000 });
  await page.waitForTimeout(250);
}

const cards = page => page.$$eval('#vbGrid .vb-card .vb-word', els => els.map(e => e.textContent.trim()));
const text = (page, sel) => page.$eval(sel, e => e.textContent.trim());
const prefs = page => page.evaluate(() => JSON.parse(localStorage.getItem('vocabularyPreferences') || 'null'));
const overflow = page => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
async function toastSeen(page, needle, timeout) {
  try {
    await page.waitForFunction(n => Array.from(document.querySelectorAll('.ielts-toast')).some(t => t.textContent.includes(n)), needle, { timeout: timeout || 4000 });
    return true;
  } catch (e) { return false; }
}
async function shot(page, name, full) {
  await page.screenshot({ path: path.join(OUT, `${engine}-${name}.png`), fullPage: !!full });
}
async function clickSub(page, id) {
  await page.click(`#vbSubs [data-sub="${id}"]`);
  await page.waitForTimeout(120);
}
async function clickCat(page, key) {
  await page.click(`#vbCats [data-cat="${key}"]`);
  await page.waitForTimeout(120);
}
async function hoverCard(page, word) {
  const card = page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: new RegExp('^' + word + '$') }) }).first();
  await card.hover();
  return card;
}

// ============================================================ desktop, light
async function desktopSuite(browser) {
  resetData();
  let { ctx, page } = await newPage(browser);
  await open(page);

  check('title', (await page.title()) === '单词本 · IELTS Lab', await page.title());
  check('standards mode (comment above doctype is fine)', (await page.evaluate(() => document.compatMode)) === 'CSS1Compat');
  check('total count', (await text(page, '#vbTotal')) === '共 314 词', await text(page, '#vbTotal'));
  const catCounts = await page.$$eval('#vbCats .ui-rail__item', els => els.map(e => e.textContent.replace(/\s+/g, '')));
  check('category counts', JSON.stringify(catCounts) === JSON.stringify(['听力160', '口语12', '阅读133', '写作9']), catCounts);
  const subNames = await page.$$eval('#vbSubs .ui-rail__name', els => els.map(e => e.textContent));
  check('listening subs natural A-Z', JSON.stringify(subNames) === JSON.stringify(['Part 1 拼写易错词', 'Part 3 学术场景', '不熟悉词汇', '地图题方位词', '默认分类']), subNames);
  check('first visit opens first sub', (await text(page, '#vbSubName')) === 'Part 1 拼写易错词', await text(page, '#vbSubName'));
  check('no horizontal overflow @1280', (await overflow(page)) <= 0, await overflow(page));
  check('sticky rail top uses app shell height', (await page.$eval('#vbRail', e => getComputedStyle(e).top)) === '56px', await page.$eval('#vbRail', e => getComputedStyle(e).top));

  await clickSub(page, SUB.unfamiliar);
  check('switch sub', (await text(page, '#vbSubName')) === '不熟悉词汇');
  check('sub stat', (await text(page, '#vbSubStat')) === '116 词 · 收藏 39', await text(page, '#vbSubStat'));
  check('116 cards', (await cards(page)).length === 116);
  // favorites first, newest: first 39 cards are favorited
  const favFlags = await page.$$eval('#vbGrid .vb-act--fav', els => els.map(e => e.getAttribute('aria-pressed') === 'true'));
  check('favorites on top', favFlags.slice(0, 39).every(Boolean) && !favFlags.slice(39).some(Boolean), favFlags.slice(36, 42));
  await shot(page, 'light-1280-main');
  await shot(page, 'light-1280-main-full', true);
  check('prefs saved sub', (await prefs(page)).subcategory === SUB.unfamiliar);

  // ---- hover: trash appears left of the star, star stays put
  const card = await hoverCard(page, (await cards(page))[0]);
  const box = await card.boundingBox();
  const star = await card.locator('.vb-act--fav').boundingBox();
  const del = await card.locator('.vb-act--del').boundingBox();
  check('star in bottom-right corner', Math.abs((box.x + box.width) - (star.x + star.width)) < 20 && star.y > box.y + box.height / 2, { box, star });
  check('trash left of star', del.x < star.x);
  await page.waitForTimeout(250);
  check('trash visible on hover', (await card.locator('.vb-act--del').evaluate(e => getComputedStyle(e).opacity)) === '1');
  await shot(page, 'light-1280-hover');

  // ---- playback: Youdao on click
  page.youdao = [];
  await page.click('#vbGrid .vb-card .vb-word >> text=biodiversity');
  await page.waitForTimeout(150);
  check('click plays youdao', page.youdao.includes('biodiversity'), page.youdao);
  const playingNow = await page.$eval('#vbGrid .vb-card.is-playing .vb-word', e => e.textContent.trim()).catch(() => null);
  check('card shows playing', playingNow === 'biodiversity', playingNow);
  await page.waitForFunction(() => !document.querySelector('#vbGrid .vb-card.is-playing'), null, { timeout: 8000 }).then(() => check('playing state clears after audio ends', true)).catch(() => check('playing state clears after audio ends', false));
  // clicking anywhere on the card body plays too
  page.youdao = [];
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: /^canteen$/ }) }).locator('.vb-date').click();
  await page.waitForTimeout(150);
  check('click card body plays', page.youdao.includes('canteen'), page.youdao);

  // Youdao fails → old TTS file fallback
  await page.route('**/dictvoice**', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"msg":"null audio"}' }));
  page.fallback = [];
  await page.click('#vbGrid .vb-word >> text=canteen');
  await page.waitForTimeout(800);
  check('youdao 500 falls back to stored audio', page.fallback.length >= 1 && new Set(page.fallback).size === 1, page.fallback);
  // word without stored audio → toast
  await page.click('#vbGrid .vb-word >> text=insulation');
  check('no audio anywhere → toast', await toastSeen(page, '没取到「insulation」的发音'));
  await page.unroute('**/dictvoice**');

  // ---- sort + favorites-first
  await page.selectOption('#vbSort', 'alphabetical');
  let order = await cards(page);
  const favs = await page.$$eval('#vbGrid .vb-act--fav', els => els.map(e => e.getAttribute('aria-pressed') === 'true'));
  const favWords = order.filter((w, i) => favs[i]);
  check('alphabetical within favorites', JSON.stringify(favWords) === JSON.stringify([...favWords].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))));
  check('prefs sortType alphabetical', (await prefs(page)).sortType === 'alphabetical');
  await page.click('#vbFavFirst');
  order = await cards(page);
  check('pure alphabetical', JSON.stringify(order) === JSON.stringify([...order].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()))));
  check('prefs sortType alphabetical-pure', (await prefs(page)).sortType === 'alphabetical-pure', (await prefs(page)).sortType);
  await page.selectOption('#vbSort', 'length-desc');
  check('fav chip disabled for length', await page.$eval('#vbFavFirst', e => e.disabled));
  order = await cards(page);
  check('length desc', order.every((w, i) => i === 0 || order[i - 1].length >= w.length));
  check('prefs sortType length-desc', (await prefs(page)).sortType === 'length-desc');
  await page.selectOption('#vbSort', 'random');
  const r1 = await cards(page);
  // favourite / unfavourite one word: random order must not reshuffle
  const target = r1[5];
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: new RegExp('^' + target + '$') }) }).locator('.vb-act--fav').click();
  await page.waitForTimeout(300);
  const r2 = await cards(page);
  check('random order stable after favourite (bug 7)', JSON.stringify(r1) === JSON.stringify(r2));
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: new RegExp('^' + target + '$') }) }).locator('.vb-act--fav').click();
  await page.waitForTimeout(300);
  await page.selectOption('#vbSort', 'newest');
  check('fav chip remembers off state', (await page.$eval('#vbFavFirst', e => e.getAttribute('aria-pressed'))) === 'false');
  await page.click('#vbFavFirst');
  check('prefs back to newest', (await prefs(page)).sortType === 'newest');

  // ---- favourite toggle persists
  const first = (await cards(page)).find((w, i, arr) => true);
  const lastWord = (await cards(page)).slice(-1)[0];
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: new RegExp('^' + lastWord + '$') }) }).locator('.vb-act--fav').click();
  check('favourite toast', await toastSeen(page, '已收藏 ' + lastWord));
  const afterFav = await cards(page);
  check('favourited word jumps to favourites block', afterFav.indexOf(lastWord) < 40, afterFav.indexOf(lastWord));
  check('stat updates', (await text(page, '#vbSubStat')) === '116 词 · 收藏 40', await text(page, '#vbSubStat'));
  const stored = readCategory('listening').subcategories[SUB.unfamiliar].words.find(w => w.word === lastWord);
  check('favourite saved on server', stored && stored.is_favorited === true);

  // ---- hide meanings: H key, chip, peek on hover, ignore typing / modifiers
  await page.click('#vbHide');
  check('hide chip masks meanings', await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => e.classList.contains('is-masked'))));
  check('prefs meaningsVisible false', (await prefs(page)).meaningsVisible === false);
  await page.mouse.move(5, 5);
  await shot(page, 'light-1280-hidden');
  await page.keyboard.press('h');
  check('H shows meanings', await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => !e.classList.contains('is-masked'))));
  await page.focus('#vbWord');
  await page.keyboard.type('h');
  check('H inside input types, does not toggle', (await page.$eval('#vbWord', e => e.value)) === 'h' && (await page.$$eval('#vbGrid .vb-meaning.is-masked', els => els.length)) === 0);
  await page.fill('#vbWord', '');
  await page.click('#vbSubName');
  await page.keyboard.press(process.platform === 'darwin' ? 'Meta+h' : 'Control+h').catch(() => {});
  await page.keyboard.press('Alt+h');
  check('modifier+H does not toggle', (await page.$$eval('#vbGrid .vb-meaning.is-masked', els => els.length)) === 0);
  await page.focus('#vbSort');
  await page.keyboard.press('h');
  check('H on sort select does not toggle', (await page.$$eval('#vbGrid .vb-meaning.is-masked', els => els.length)) === 0);

  // ---- search
  await page.fill('#vbSearch', 'can');
  await page.waitForTimeout(100);
  const found = await cards(page);
  check('search filters by word', found.includes('canteen') && found.length < 116, found);
  await page.fill('#vbSearch', '食堂');
  check('search by meaning', JSON.stringify(await cards(page)) === JSON.stringify(['canteen']), await cards(page));
  await page.fill('#vbSearch', 'zzzz');
  check('search no result message', (await text(page, '#vbCountLine')).includes('没有包含「zzzz」'));
  await page.fill('#vbSearch', '');
  check('search cleared shows all', (await cards(page)).length === 116);

  // ---- add word (Enter), duplicate hint, Ctrl+Enter, XSS
  await page.fill('#vbWord', 'canteen');
  check('duplicate hint', (await text(page, '#vbAddHint')).includes('已经在这个子分类里了') && await page.$eval('#vbAddHint', e => e.classList.contains('is-warn')));
  await page.press('#vbWord', 'Enter');
  check('duplicate rejected by server', await toastSeen(page, '单词在该子分类中已存在'));
  await page.fill('#vbWord', 'meticulous');
  await page.fill('#vbMeaning', 'adj. 一丝不苟的');
  await page.press('#vbMeaning', 'Enter');
  check('add toast', await toastSeen(page, '已添加「meticulous」'));
  check('added card shows', (await cards(page)).includes('meticulous'));
  check('inputs cleared + focus back on word', (await page.$eval('#vbWord', e => e.value)) === '' && (await page.evaluate(() => document.activeElement.id)) === 'vbWord');
  check('count 117', (await text(page, '#vbSubStat')).startsWith('117 词'));
  const tasksDir = path.join(SANDBOX, 'vocabulary_book/tasks');
  check('no TTS task queued', fs.readdirSync(tasksDir).filter(f => f.endsWith('.json')).length === 0, fs.readdirSync(tasksDir));
  page.youdao = [];
  await page.click('#vbGrid .vb-word >> text=meticulous');
  await page.waitForTimeout(200);
  check('new word plays from youdao right away', page.youdao.includes('meticulous'));
  await page.fill('#vbWord', 'punctilious');
  await page.press('#vbWord', process.platform === 'darwin' ? 'Meta+Enter' : 'Control+Enter');
  check('Cmd/Ctrl+Enter adds', await toastSeen(page, '已添加「punctilious」'));
  await page.fill('#vbWord', '<img src=x onerror="window.__xss=1">');
  await page.fill('#vbMeaning', '<b onmouseover="window.__xss=2">bold</b> "quoted" & \'apos\'');
  await page.press('#vbMeaning', 'Enter');
  await toastSeen(page, '已添加');
  await page.waitForTimeout(300);
  const xssCard = await page.$$eval('#vbGrid .vb-word', els => els.map(e => e.textContent).find(t => t.includes('onerror')));
  check('xss word rendered as text (bug 1)', !!xssCard && (await page.evaluate(() => window.__xss)) === undefined && (await page.$$('#vbGrid img')).length === 0, xssCard);
  await page.hover('#vbGrid .vb-meaning >> text=bold');
  check('xss meaning inert', (await page.evaluate(() => window.__xss)) === undefined);

  // ---- delete word with in-page confirm
  await hoverCard(page, 'punctilious');
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: /^punctilious$/ }) }).locator('.vb-act--del').click();
  await page.waitForSelector('#dlgConfirm:not([hidden])');
  check('delete confirm text', (await text(page, '#cfTitle')) === '删除单词「punctilious」？');
  await shot(page, 'light-1280-confirm-delete-word');
  await page.click('#cfCancel');
  check('cancel keeps word', (await cards(page)).includes('punctilious'));
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: /^punctilious$/ }) }).locator('.vb-act--del').click();
  await page.keyboard.press('Escape');
  check('Esc cancels delete', (await cards(page)).includes('punctilious') && await page.$eval('#dlgConfirm', e => e.hidden));
  await page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: /^punctilious$/ }) }).locator('.vb-act--del').click();
  await page.click('#cfOk');
  check('delete toast', await toastSeen(page, '已删除「punctilious」'));
  check('word gone', !(await cards(page)).includes('punctilious'));

  // ---- subcategory: new (with tricky name), rename, empty state, delete current
  await page.click('#vbSubNew');
  await page.waitForSelector('#dlgSub:not([hidden])');
  check('new sub dialog focused input', (await page.evaluate(() => document.activeElement.id)) === 'dlgSubName');
  await shot(page, 'light-1280-new-sub');
  await page.fill('#dlgSubName', "Writer's <i>words</i>");
  await page.press('#dlgSubName', 'Enter');
  check('new sub toast', await toastSeen(page, "已新建「Writer's <i>words</i>」"));
  check('new sub selected', (await text(page, '#vbSubName')) === "Writer's <i>words</i>");
  check('empty state', await page.$eval('#vbEmpty', e => !e.hidden) && (await text(page, '#vbEmptyTitle')).includes("Writer's"));
  await shot(page, 'light-1280-empty');
  await page.click('#vbRenameBtn');
  check('rename prefilled (bug 2)', (await page.$eval('#dlgSubName', e => e.value)) === "Writer's <i>words</i>");
  await page.fill('#dlgSubName', "Writer's words");
  await page.click('#dlgSubOk');
  check('rename toast', await toastSeen(page, "已改名为「Writer's words」"));
  check('rail shows new name', (await page.$$eval('#vbSubs .ui-rail__name', els => els.map(e => e.textContent))).includes("Writer's words"));
  await page.click('#vbRenameBtn');
  await page.fill('#dlgSubName', '不熟悉词汇');
  await page.click('#dlgSubOk');
  check('duplicate name rejected', await toastSeen(page, '子分类名称已存在'));
  await page.keyboard.press('Escape');
  await page.click('#vbDeleteSubBtn');
  check('delete empty sub text', (await text(page, '#cfText')).includes('是空的'));
  await page.click('#cfOk');
  await page.waitForFunction(() => document.getElementById('vbSubName').textContent !== "Writer's words", null, { timeout: 4000 }).catch(() => {});
  check('after deleting current sub → first sub, not 未知 (bug 3)', (await text(page, '#vbSubName')) === 'Part 1 拼写易错词', await text(page, '#vbSubName'));
  await page.fill('#vbWord', 'itinerary');
  await page.press('#vbWord', 'Enter');
  check('can add after deleting current sub', await toastSeen(page, '已添加「itinerary」'));
  await clickSub(page, SUB.part3);
  await page.click('#vbDeleteSubBtn');
  check('delete sub warns word count', (await text(page, '#cfText')).includes('14 个单词'));
  await shot(page, 'light-1280-confirm-delete-sub');
  await page.click('#cfCancel');
  // last sub cannot be deleted (writing default has 1 word + 趋势动词 8; use speaking: delete until one left)
  await clickCat(page, 'writing');
  await clickSub(page, 'default');
  await page.click('#vbDeleteSubBtn');
  await page.click('#cfOk');
  await toastSeen(page, '已删除');
  await page.click('#vbDeleteSubBtn');
  await page.click('#cfOk');
  check('last sub refused', await toastSeen(page, '至少需要保留一个子分类'));

  // ---- category switch + natural sort + order toggle
  await clickCat(page, 'reading');
  const readingSubs = await page.$$eval('#vbSubs .ui-rail__name', els => els.map(e => e.textContent));
  check('reading natural order (Chapter2 before Chapter10)', JSON.stringify(readingSubs) === JSON.stringify(['Chapter1 自然地理', 'Chapter2 植物研究', 'Chapter3 动物保护', 'Chapter10 物品材料', 'Chapter11 时尚潮流', '[同义替换] 动词', '默认分类']), readingSubs);
  check('category switch picks first sub', (await text(page, '#vbSubName')) === 'Chapter1 自然地理');
  await page.click('#vbSubSort');
  const desc = await page.$$eval('#vbSubs .ui-rail__name', els => els.map(e => e.textContent));
  check('Z–A reverses', JSON.stringify(desc) === JSON.stringify([...readingSubs].reverse()), desc);
  check('prefs subcategorySortOrder', (await prefs(page)).subcategorySortOrder.reading === 'desc');
  await page.click('#vbSubSort');

  // ---- prefs survive reload
  await clickSub(page, SUB.ch2);
  await page.selectOption('#vbSort', 'oldest');
  await page.click('#vbFavFirst');
  await page.click('#vbHide');
  await page.reload();
  await page.waitForSelector('#vbContent:not([hidden])');
  check('reload keeps category/sub', (await text(page, '#vbSubName')) === 'Chapter2 植物研究');
  check('reload keeps sort + fav toggle', (await page.$eval('#vbSort', e => e.value)) === 'oldest' && (await page.$eval('#vbFavFirst', e => e.getAttribute('aria-pressed'))) === 'false');
  check('reload keeps hidden meanings', await page.$$eval('#vbGrid .vb-meaning', els => els.length > 0 && els.every(e => e.classList.contains('is-masked'))));
  await page.click('#vbHide');

  // ---- import: exported-format CSV with header + quotes, uppercase .CSV, single-column error
  await clickCat(page, 'listening');
  await clickSub(page, SUB.mapEmpty);
  await page.click('#vbEmptyImport');
  await page.waitForSelector('#dlgImport:not([hidden])');
  check('import defaults to current sub', (await page.$eval('#impSub', e => e.value)) === SUB.mapEmpty);
  await page.click('#impOk');
  check('import without file warns', await toastSeen(page, '先选一个 CSV 文件'));
  const csv1 = path.join(DL, 'map-words.CSV');
  fs.writeFileSync(csv1, '﻿单词,词义\r\n"roundabout","n. 环岛"\r\n"say ""hi"", then leave","打招呼后离开"\r\nopposite,prep. 在…对面\r\n');
  await page.setInputFiles('#impFile', csv1);
  check('file shown in drop zone', (await text(page, '#impDropTitle')) === 'map-words.CSV');
  await shot(page, 'light-1280-import');
  await page.click('#impOk');
  check('import toast', await toastSeen(page, '导入了 3 个单词'));
  const imported = await cards(page);
  check('import header skipped + quotes kept', imported.length === 3 && imported.includes('say "hi", then leave') && !imported.includes('单词'), imported);
  await page.click('#vbImportBtn');
  const csv2 = path.join(DL, 'one-col.csv');
  fs.writeFileSync(csv2, 'abundant，adj. 丰富的\nacquire\n');
  await page.setInputFiles('#impFile', csv2);
  await page.click('#impOk');
  check('single column CSV error', await toastSeen(page, '每行要有两列'));
  const txt = path.join(DL, 'notes.txt');
  fs.writeFileSync(txt, 'x,y');
  await page.setInputFiles('#impFile', txt);
  check('non-csv rejected in page', await toastSeen(page, '只支持 CSV 文件'));
  await page.keyboard.press('Escape');

  // ---- export: CSV (BOM, escaping, 中文分类名), TXT, JSON; then round-trip re-import
  await page.click('#vbExportBtn');
  await page.waitForSelector('#dlgExport:not([hidden])');
  check('export summary', (await text(page, '#expSummary')).includes('3') && (await text(page, '#expSummary')).includes('listening_地图题方位词_单词.csv'), await text(page, '#expSummary'));
  await page.check('#expCategory');
  await page.check('#expSubcategory');
  await shot(page, 'light-1280-export');
  let [dl] = await Promise.all([page.waitForEvent('download'), page.click('#expOk')]);
  const csvPath = path.join(DL, engine + '-export.csv');
  await dl.saveAs(csvPath);
  const csvText = fs.readFileSync(csvPath, 'utf8');
  check('csv has BOM (bug 4)', csvText.charCodeAt(0) === 0xFEFF);
  check('csv escapes quotes (bug 4)', csvText.includes('"say ""hi"", then leave"'), csvText.slice(0, 200));
  check('csv category in Chinese (D)', csvText.includes('"听力"') && !csvText.includes('Listening'), csvText.slice(0, 200));
  check('export filename', dl.suggestedFilename() === 'listening_地图题方位词_单词.csv', dl.suggestedFilename());
  await page.click('#vbExportBtn');
  await page.click('#expFormat [data-value="txt"]');
  [dl] = await Promise.all([page.waitForEvent('download'), page.click('#expOk')]);
  await dl.saveAs(path.join(DL, engine + '-export.txt'));
  check('txt export', fs.readFileSync(path.join(DL, engine + '-export.txt'), 'utf8').includes('1. roundabout - n. 环岛') || fs.readFileSync(path.join(DL, engine + '-export.txt'), 'utf8').includes('. roundabout - n. 环岛'));
  await page.click('#vbExportBtn');
  await page.click('#expScope [data-value="all"]');
  await page.click('#expFormat [data-value="json"]');
  check('export all summary', (await text(page, '#expSummary')).includes('所有单词.json'));
  [dl] = await Promise.all([page.waitForEvent('download'), page.click('#expOk')]);
  await dl.saveAs(path.join(DL, engine + '-export.json'));
  const js = JSON.parse(fs.readFileSync(path.join(DL, engine + '-export.json'), 'utf8'));
  check('json export all words', js.word_count === js.words.length && js.word_count > 300, js.word_count);
  // round trip: export (word + meaning only) and re-import into a fresh sub
  await page.click('#vbExportBtn');
  await page.uncheck('#expCategory');
  await page.uncheck('#expSubcategory');
  await page.click('#expFormat [data-value="csv"]');
  [dl] = await Promise.all([page.waitForEvent('download'), page.click('#expOk')]);
  const rt = path.join(DL, engine + '-roundtrip.csv');
  await dl.saveAs(rt);
  await page.click('#vbSubNew');
  await page.fill('#dlgSubName', '导回测试');
  await page.press('#dlgSubName', 'Enter');
  await toastSeen(page, '已新建');
  await page.click('#vbImportBtn');
  await page.setInputFiles('#impFile', rt);
  await page.evaluate(() => document.querySelectorAll('.ielts-toast').forEach(t => t.remove()));
  await page.click('#impOk');
  check('round trip imports 3', await toastSeen(page, '导入了 3 个单词'));
  await page.waitForFunction(() => document.getElementById('dlgImport').hidden && document.querySelectorAll('#vbGrid .vb-card').length === 3, null, { timeout: 5000 }).catch(() => {});
  const rtWords = readCategory('listening');
  const rtSub = Object.values(rtWords.subcategories).find(s => s.name === '导回测试');
  check('round trip keeps text exactly', rtSub && rtSub.words.some(w => w.word === 'say "hi", then leave' && w.meaning === '打招呼后离开'), rtSub && rtSub.words);

  // ---- challenge: setup summary, keyboard answers, unique options, record with ASCII header, 再来一次
  await clickSub(page, SUB.unfamiliar);
  page.records = [];
  await page.click('#vbChallengeBtn');
  await page.waitForSelector('#dlgChallenge:not([hidden])');
  await page.waitForTimeout(400);
  const chSummary = await text(page, '#chSummary');
  check('challenge summary with coverage', /这个范围有 118 个单词，挑战里出现过 \d+ 个/.test(chSummary), chSummary);
  const covReq = page.records.find(r => r.url.includes('coverage'));
  check('coverage request sends ASCII user header (bug 14)', covReq && covReq.user === JSON.stringify({ username: USER }), covReq);
  await page.click('#chCount [data-value="5"]');
  await shot(page, 'light-1280-challenge-setup');
  await page.click('#chOk');
  await page.waitForSelector('#dlgQuiz:not([hidden])');
  let uniqueOk = true;
  const answered = [];
  for (let i = 0; i < 5; i++) {
    await page.waitForFunction(n => document.getElementById('qCount').textContent.includes('第 ' + n + ' / 5 题') && !document.querySelector('#qOptions .vb-option:disabled'), i + 1, { timeout: 6000 });
    const opts = await page.$$eval('#qOptions .vb-option__text', els => els.map(e => e.textContent.trim().toLowerCase()));
    if (new Set(opts).size !== opts.length) uniqueOk = false;
    if (i === 1) await shot(page, 'light-1280-challenge-question');
    if (i % 2 === 0) await page.keyboard.press(String((i % 4) + 1)); else await page.click('#qOptions .vb-option >> nth=0');
    await page.waitForSelector('#qOptions .vb-option.is-right');
    if (i === 0) await shot(page, 'light-1280-challenge-answered');
    answered.push(await page.$$eval('#qOptions .vb-option.is-wrong', els => els.length));
  }
  check('options unique within question', uniqueOk);
  await page.waitForSelector('#dlgResult:not([hidden])', { timeout: 6000 });
  await page.waitForFunction(() => !document.getElementById('rSummary').textContent.includes('正在'), null, { timeout: 5000 });
  const rs = await text(page, '#rSummary');
  check('result saved', rs.includes('已记进挑战记录'), rs);
  const rec = page.records.find(r => r.url.includes('/record'));
  check('record request with ASCII header', rec && rec.user === JSON.stringify({ username: USER }) && JSON.parse(rec.body).results.length === 5, rec);
  const wrongN = parseInt(await text(page, '#rWrong'), 10);
  check('result numbers add up', parseInt(await text(page, '#rRight'), 10) + wrongN === 5 && answered.filter(Boolean).length === wrongN);
  check('result title', (await text(page, '#rTitle')) === '挑战完成 · 不熟悉词汇');
  await shot(page, 'light-1280-challenge-result');
  const chal = JSON.parse(fs.readFileSync(path.join(SANDBOX, 'vocabulary_book/challenges', USER + '.json'), 'utf8'));
  check('challenge file updated for the user', chal.challenge_stats.total_challenges === 7, chal.challenge_stats);
  await page.click('#rAgain');
  await page.waitForSelector('#dlgChallenge:not([hidden])');
  check('再来一次 keeps 5 题 + scope (bug 10)', (await page.$eval('#chCount .is-on', e => e.dataset.value)) === '5' && (await page.$eval('#chScope .is-on', e => e.dataset.value)) === 'subcategory' && (await page.$eval('#chSub', e => e.value)) === SUB.unfamiliar);

  // ---- challenge exit: Esc / backdrop ask first; no result pops up later (bug 8)
  await page.click('#chScope [data-value="all"]');
  await page.click('#chCount [data-value="30"]');
  await page.click('#chOk');
  await page.waitForSelector('#dlgQuiz:not([hidden])');
  // run through the 30-question "all" quiz quickly checking duplicate option texts (bug 9)
  let dupFree = true;
  for (let i = 0; i < 6; i++) {
    await page.waitForFunction(n => document.getElementById('qCount').textContent.includes('第 ' + n + ' / 30 题') && !document.querySelector('#qOptions .vb-option:disabled'), i + 1, { timeout: 6000 });
    const opts = await page.$$eval('#qOptions .vb-option__text', els => els.map(e => e.textContent.trim().toLowerCase()));
    if (new Set(opts).size !== opts.length) dupFree = false;
    await page.keyboard.press('2');
  }
  check('scope all: no duplicate options (bug 9)', dupFree);
  await page.waitForFunction(() => !document.querySelector('#qOptions .vb-option:disabled'), null, { timeout: 6000 });
  await page.keyboard.press('1');           // answered → auto-advance pending
  await page.keyboard.press('Escape');
  await page.waitForSelector('#dlgConfirm:not([hidden])');
  check('Esc asks before quitting', (await text(page, '#cfTitle')) === '退出这次挑战？');
  await shot(page, 'light-1280-challenge-quit');
  await page.waitForTimeout(2000);
  check('no auto-advance behind the confirm', (await text(page, '#qCount')).includes('第 7 / 30 题'), await text(page, '#qCount'));
  await page.click('#cfCancel');
  await page.waitForFunction(() => document.getElementById('qCount').textContent.includes('第 8 / 30 题'), null, { timeout: 4000 }).then(() => check('continue resumes', true)).catch(async () => check('continue resumes', false, await text(page, '#qCount')));
  await page.mouse.click(10, 10);           // backdrop
  await page.waitForSelector('#dlgConfirm:not([hidden])');
  await page.click('#cfOk');
  await page.waitForTimeout(2500);
  check('quit closes quiz, no result later', await page.$eval('#dlgQuiz', e => e.hidden) && await page.$eval('#dlgResult', e => e.hidden));

  check('no page errors (desktop)', page.errors.length === 0, page.errors);
  await ctx.close();
}

// ============================================================ category with no data file yet (bug 15)
async function missingCategoryFile(browser) {
  resetData();
  // 新装好、或某个分类从没加过词时还没有分类文件：以前往里加第一个词报 500，还留下半截文件
  fs.rmSync(path.join(SANDBOX, 'vocabulary_book/categories/speaking.json'));
  const { ctx, page } = await newPage(browser);
  await open(page);
  await clickCat(page, 'speaking');
  check('missing file: category opens on 默认分类', (await text(page, '#vbSubName')) === '默认分类', await text(page, '#vbSubName'));
  // 空子分类显示空状态、整块列表藏起来（上一个子分类的卡片还留在 DOM 里，但看不见）
  const emptyState = await page.evaluate(() => ({
    empty: !document.getElementById('vbEmpty').hidden, list: !document.getElementById('vbList').hidden,
    title: document.getElementById('vbEmptyTitle').textContent.trim(),
  }));
  check('missing file: shows the empty state', emptyState.empty && !emptyState.list && emptyState.title === '「默认分类」还没有单词', emptyState);
  await page.fill('#vbWord', 'hospitable');
  await page.fill('#vbMeaning', 'adj. 好客的');
  await page.press('#vbMeaning', 'Enter');
  check('missing file: first word added', await toastSeen(page, '已添加「hospitable」'));
  check('missing file: card shows', (await cards(page)).includes('hospitable'), await cards(page));
  let saved = null;
  try { saved = readCategory('speaking'); } catch (e) { saved = { error: e.message }; }
  check('missing file: file written with the word',
    saved && saved.icon === '🗣️' && saved.subcategories && saved.subcategories.default.words.some(w => w.word === 'hospitable'), saved);
  check('no page errors (missing file)', page.errors.length === 0, page.errors);
  await ctx.close();
}

// ============================================================ prefs migration + dark + phone
async function prefsAndThemes(browser) {
  resetData();
  // old 'audio-first' preference → newest with favourites on top; old reading/desc prefs honoured
  let { ctx, page } = await newPage(browser, { prefs: { category: 'reading', subcategory: SUB.ch2, sortType: 'audio-first', subcategorySortOrder: { reading: 'desc' }, meaningsVisible: false } });
  await open(page);
  check('old prefs: category/sub', (await text(page, '#vbSubName')) === 'Chapter2 植物研究');
  check('old prefs: audio-first → newest + 收藏置顶', (await page.$eval('#vbSort', e => e.value)) === 'newest' && (await page.$eval('#vbFavFirst', e => e.getAttribute('aria-pressed'))) === 'true');
  check('old prefs: Z–A', (await page.$eval('#vbSubs .ui-rail__name', e => e.textContent)) === '默认分类');
  check('old prefs: hidden meanings', await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => e.classList.contains('is-masked'))));
  await ctx.close();

  ({ ctx, page } = await newPage(browser, { prefs: { category: 'listening', subcategory: 'gone-id', sortType: 'reverse-alphabetical-pure' } }));
  await open(page);
  check('stale sub id → first sub', (await text(page, '#vbSubName')) === 'Part 1 拼写易错词');
  check('pure sort pref', (await page.$eval('#vbSort', e => e.value)) === 'reverse-alphabetical' && (await page.$eval('#vbFavFirst', e => e.getAttribute('aria-pressed'))) === 'false');
  await ctx.close();

  // dark desktop
  ({ ctx, page } = await newPage(browser, { theme: 'dark', prefs: { category: 'listening', subcategory: SUB.unfamiliar, sortType: 'newest', meaningsVisible: true } }));
  await open(page);
  check('dark theme applied', (await page.evaluate(() => document.documentElement.dataset.theme)) === 'dark');
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  const cardBg = await page.$eval('.vb-card', e => getComputedStyle(e).backgroundColor);
  check('dark backgrounds are dark', [bg, cardBg].every(c => { const n = c.match(/\d+/g).slice(0, 3).map(Number); return n.reduce((a, b) => a + b, 0) < 200; }), [bg, cardBg]);
  await shot(page, 'dark-1280-main');
  await hoverCard(page, 'canteen');
  await shot(page, 'dark-1280-hover');
  await page.click('#vbChallengeBtn');
  await page.waitForTimeout(300);
  await page.click('#chOk');
  await page.waitForSelector('#dlgQuiz:not([hidden])');
  await page.waitForTimeout(400);
  await shot(page, 'dark-1280-challenge-question');
  await page.keyboard.press('1');
  await page.waitForTimeout(300);
  await shot(page, 'dark-1280-challenge-answered');
  await page.keyboard.press('Escape');
  await page.click('#cfOk');
  await page.click('#vbExportBtn');
  await shot(page, 'dark-1280-export');
  await page.keyboard.press('Escape');
  check('no page errors (dark)', page.errors.length === 0, page.errors);
  await ctx.close();
}

// ============================================================ phone: WebKit 390×844 / Chromium 360×780, light + dark
// 手机布局：首屏就看到单词卡；吸顶条（分类 / 子分类 / 查找 / 排序）；底部操作条（遮释义 / 加词 / 单词挑战）；
// 子分类、排序、加词、⋯ 菜单都是底部面板；返回键先关面板；键盘弹出（视口约 470px 高）时输入框和按钮还看得见
const PHONE = { webkit: { width: 390, height: 844, isMobile: false }, chromium: { width: 360, height: 780, isMobile: true } };
const KB_HEIGHT = 470;

const rect = (page, sel) => page.$eval(sel, e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom, r: r.right }; }).catch(() => null);
const shown = (page, sel) => page.isVisible(sel).catch(() => false);
const isOpenAdd = page => page.$eval('#vbAddSheet', e => e.classList.contains('is-open')).catch(() => false);
const activeId = page => page.evaluate(() => document.activeElement && document.activeElement.id);
// 一段流程出错就记一条 FAIL，接着跑下一段（在 mobile/base 上跑时这些元素都不存在，要能数出每一段都失败）
async function section(name, fn) {
  try { await fn(); } catch (e) { check(name + ' (crashed)', false, String(e.message).split('\n')[0]); }
}
// 面板从底部滑上来要 0.22 秒，等它停稳再量位置
const waitShown = async (page, sel, timeout) => { await page.waitForSelector(sel, { state: 'visible', timeout: timeout || 3000 }); await page.waitForTimeout(280); };
const waitHidden = (page, sel, timeout) => page.waitForSelector(sel, { state: 'hidden', timeout: timeout || 3000 });
// 底部面板：铺满宽度、贴着屏幕底边
async function isBottomSheet(page, sel, vw, vh) {
  const r = await rect(page, sel);
  return !!r && Math.abs(r.x) <= 1 && Math.abs(r.w - vw) <= 1 && Math.abs(r.b - vh) <= 1;
}
// 手机的返回（iOS 右滑 / 安卓返回键）：退一条历史后页面没重新加载（window.__stay 还在），还在单词本
async function pressBack(page) {
  await page.evaluate(() => { window.__stay = 1; });
  await page.goBack({ timeout: 5000 }).catch(() => {});
  await page.waitForTimeout(300);
  return page.evaluate(() => window.__stay === 1 && location.pathname === '/vocabulary' && !document.getElementById('vbContent').hidden).catch(() => false);
}
const cardByWord = (page, word) => page.locator('#vbGrid .vb-card', { has: page.locator('.vb-word', { hasText: new RegExp('^' + word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$') }) }).first();
const isDark = c => { const n = (String(c).match(/\d+(\.\d+)?/g) || []).slice(0, 3).map(Number); return n.length === 3 && n.reduce((a, b) => a + b, 0) < 200; };

async function phoneSuite(browser) {
  const dev = PHONE[engine] || PHONE.webkit;
  for (const theme of ['light', 'dark']) {
    resetData();
    const { ctx, page } = await newPage(browser, { width: dev.width, height: dev.height, mobile: true, isMobile: dev.isMobile, theme, prefs: { category: 'listening', subcategory: SUB.unfamiliar, sortType: 'newest', meaningsVisible: true } });
    const P = n => `phone ${dev.width} ${theme}: ${n}`;
    await open(page);
    await phoneLayout(page, P, dev.width, dev.height);
    if (theme === 'light') await phoneFlows(page, P, dev.width, dev.height);
    else await phoneDark(page, P);
    check(P('no page errors'), page.errors.length === 0, page.errors);
    await ctx.close();
  }
  await phoneAudioUnlock(browser, dev);
  await phoneLoadingAndError(browser, dev);
}

async function phoneLayout(page, P, vw, vh) {
  await section(P('first screen'), async () => {
    check(P('no horizontal overflow'), (await overflow(page)) <= 0, await overflow(page));
    const bar = await rect(page, '#vbPbar');
    check(P('bottom bar fixed at the bottom'), !!bar && Math.abs(bar.b - vh) <= 1 && bar.w >= vw - 1 && (await page.$eval('#vbPbar', e => getComputedStyle(e).position)) === 'fixed', bar);
    const first = await rect(page, '#vbGrid .vb-card');
    check(P('first word cards on the first screen'), !!first && !!bar && first.b <= bar.y, { first, bar });
    const full = await page.$$eval('#vbGrid .vb-card', (els, limit) => els.filter(e => { const r = e.getBoundingClientRect(); return r.top >= 0 && r.bottom <= limit; }).length, bar ? bar.y : vh);
    check(P('at least 8 cards fully visible before scrolling'), full >= 8, full);
    check(P('2 cards per row'), (await page.$eval('#vbGrid', e => getComputedStyle(e).gridTemplateColumns.split(' ').length)) === 2);
    const wordPx = await page.$eval('#vbGrid .vb-word', e => parseFloat(getComputedStyle(e).fontSize));
    check(P('English word >= 16px'), wordPx >= 16, wordPx);
    const hiddenBits = await page.evaluate(() => ['#vbGrid .vb-date', '#vbGrid .vb-act--del', '.vb-toolbar', '.vb-kbd', '.vb-head__desc', '#vbImportBtn', '#vbExportBtn', '#vbChallengeBtn', '.vb-main-head', '#vbAddForm']
      .filter(s => { const e = document.querySelector(s); return e && e.getClientRects().length > 0; }));
    check(P('no date / trash / H-key hint / inline add form / head buttons on phones'), hiddenBits.length === 0, hiddenBits);
  });
  await section(P('tap sizes'), async () => {
    const card = await rect(page, '#vbGrid .vb-card');
    const more = await rect(page, '#vbGrid .vb-card .vb-act--more');
    const star = await rect(page, '#vbGrid .vb-card .vb-act--fav');
    check(P('card ⋯ and ★ >= 40×40, 8px apart, inside the card'),
      !!(more && star && card) && more.w >= 40 && more.h >= 40 && star.w >= 40 && star.h >= 40 && star.y - more.b >= 8 && more.y >= card.y - 0.5 && star.b <= card.b + 0.5 && more.r <= card.r + 0.5, { card, more, star });
    const sizes = await page.evaluate(() => {
      const r = s => Array.from(document.querySelectorAll(s)).map(e => { const b = e.getBoundingClientRect(); return [Math.round(b.width), Math.round(b.height)]; });
      return { tabs: r('#vbCats .ui-rail__item'), row: r('#vbSubToggle, #vbSearchBtn, #vbSortBtn'), more: r('#vbMoreBtn'), bar: r('#vbPbar .ui-btn') };
    });
    check(P('category tabs >= 40px tall'), sizes.tabs.length === 4 && sizes.tabs.every(([, h]) => h >= 40), sizes.tabs);
    check(P('sub picker / search / sort >= 44px'), sizes.row.length === 3 && sizes.row.every(([w, h]) => w >= 44 && h >= 44), sizes.row);
    check(P('page ⋯ is 44×44'), sizes.more.length === 1 && sizes.more[0][0] >= 44 && sizes.more[0][1] >= 44, sizes.more);
    check(P('bottom bar buttons >= 44px'), sizes.bar.length === 3 && sizes.bar.every(([, h]) => h >= 44), sizes.bar);
  });
  await section(P('scrolled'), async () => {
    await page.evaluate(() => window.scrollTo(0, 3000));
    await page.waitForTimeout(150);
    const stuck = await page.evaluate(() => {
      const col = document.querySelector('.vb-rail-col');
      const t = document.getElementById('vbSubToggle').getBoundingClientRect();
      const hit = document.elementFromPoint(t.x + t.width / 2, t.y + t.height / 2);
      return { y: window.scrollY, top: col.getBoundingClientRect().top, want: parseFloat(getComputedStyle(col).top), hit: !!(hit && hit.closest('#vbSubToggle')) };
    });
    check(P('sticky bar stays under the top nav deep in the list'), stuck.y > 1000 && Math.abs(stuck.top - stuck.want) <= 1 && stuck.hit, stuck);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await page.waitForTimeout(150);
    const last = await page.evaluate(() => { const c = document.querySelectorAll('#vbGrid .vb-card'); return c[c.length - 1].getBoundingClientRect().bottom; });
    const bar = await rect(page, '#vbPbar');
    check(P('bottom bar does not cover the last card'), last <= bar.y, { last, bar: bar && bar.y });
    const barVar = await page.evaluate(() => parseFloat(getComputedStyle(document.body).getPropertyValue('--ui-bottom-bar-h')));
    check(P('--ui-bottom-bar-h = bar height (toasts float above it)'), Math.abs(barVar - bar.h) <= 1, { barVar, h: bar.h });
    await page.evaluate(() => window.scrollTo(0, 0));
  });
}

async function phoneFlows(page, P, vw, vh) {
  await shot(page, 'phone-main');
  await page.evaluate(() => window.scrollTo(0, 2400));
  await page.waitForTimeout(150);
  await shot(page, 'phone-deep');
  await page.evaluate(() => window.scrollTo(0, 0));

  // ---- 点卡片听发音；底部「遮释义」等于桌面的 H 键；被遮住的释义点一下偷看
  await section(P('play + mask'), async () => {
    page.youdao = [];
    await page.locator('#vbGrid .vb-word').first().tap();
    await page.waitForTimeout(200);
    check(P('tap word plays'), page.youdao.length >= 1 && new Set(page.youdao).size === 1, page.youdao);
    await page.tap('#vbPHide');
    check(P('遮释义 (bottom bar) masks every meaning'), (await page.$eval('#vbPHide', e => e.getAttribute('aria-pressed'))) === 'true' && await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => e.classList.contains('is-masked'))) && (await prefs(page)).meaningsVisible === false);
    const m = page.locator('#vbGrid .vb-meaning').nth(2);
    page.youdao = [];
    await m.tap();
    await page.waitForTimeout(150);
    check(P('tap a masked meaning peeks, does not play'), await m.evaluate(e => e.classList.contains('is-peek')) && page.youdao.length === 0);
    await shot(page, 'phone-masked');
    await page.tap('#vbPHide');
    check(P('遮释义 again shows them'), (await page.$$eval('#vbGrid .vb-meaning.is-masked', els => els.length)) === 0);
  });

  // ---- ★ 一下就收藏；提示条浮在底部操作条上面
  await section(P('star'), async () => {
    const card = page.locator('#vbGrid .vb-card').nth(40);
    const word = (await card.locator('.vb-word').textContent()).trim();
    await card.locator('.vb-act--fav').tap();
    check(P('★ is one tap'), await toastSeen(page, '已收藏 ' + word));
    check(P('★ saved'), (await cardByWord(page, word).locator('.vb-act--fav').getAttribute('aria-pressed')) === 'true');
    const t = await rect(page, '.ielts-toast');
    const bar = await rect(page, '#vbPbar');
    check(P('toast floats above the bottom bar'), !!t && !!bar && t.b <= bar.y, { t, bar });
    await cardByWord(page, word).locator('.vb-act--fav').tap();
    await toastSeen(page, '已取消收藏 ' + word);
  });

  // ---- 单词卡 ⋯：播放 / 收藏 / 删除（删除先确认）；返回键关面板
  await section(P('card ⋯'), async () => {
    await page.evaluate(() => window.scrollTo(0, 0));
    const card = page.locator('#vbGrid .vb-card').nth(5);   // 收藏的词；别删 canteen，后面查找要用
    const word = (await card.locator('.vb-word').textContent()).trim();
    await card.locator('.vb-act--more').tap();
    await waitShown(page, '#dlgActions');
    const items = await page.$$eval('#actList .vb-actitem', els => els.map(e => e.textContent.trim()));
    check(P('card ⋯ → play / star / edit / delete'), (await text(page, '#actTitle')) === word && items.join('|') === '播放发音|取消收藏|编辑|删除这个单词', { title: await text(page, '#actTitle'), items });
    check(P('action sheet is a bottom sheet'), await isBottomSheet(page, '#dlgActions .ui-dialog', vw, vh));
    const rowH = await page.$$eval('#actList .vb-actitem', els => els.map(e => e.getBoundingClientRect().height));
    check(P('action rows >= 44px'), rowH.every(h => h >= 44), rowH);
    await shot(page, 'phone-word-actions');
    check(P('back closes the action sheet, stays on the page'), (await pressBack(page)) && !(await shown(page, '#dlgActions')));
    await card.locator('.vb-act--more').tap();
    await waitShown(page, '#dlgActions');
    await page.tap('#actList .vb-actitem.is-danger');
    await waitShown(page, '#dlgConfirm');
    check(P('delete asks first'), (await text(page, '#cfTitle')) === '删除单词「' + word + '」？');
    await shot(page, 'phone-confirm-delete');
    await page.tap('#cfCancel');
    check(P('cancel keeps the word'), (await cards(page)).includes(word));
    await cardByWord(page, word).locator('.vb-act--more').tap();
    await waitShown(page, '#dlgActions');
    await page.tap('#actList .vb-actitem.is-danger');
    await waitShown(page, '#dlgConfirm');
    await page.tap('#cfOk');
    check(P('delete via ⋯'), await toastSeen(page, '已删除「' + word + '」') && !(await cards(page)).includes(word));
  });

  // ---- 子分类面板：选、返回键关、从列表深处换子分类回到新列表开头
  await section(P('sub sheet'), async () => {
    await page.evaluate(() => window.scrollTo(0, 2400));
    await page.tap('#vbSubToggle');
    await waitShown(page, '#dlgSubs');
    const rows = await page.$$eval('#subsList .vb-row', els => els.map(e => ({ name: e.querySelector('.vb-row__name').textContent, on: e.classList.contains('is-on'), h: Math.round(e.getBoundingClientRect().height), more: Math.round(e.querySelector('.vb-row__more').getBoundingClientRect().width) })));
    check(P('sub sheet lists subs, current one checked'), rows.length === 5 && rows.filter(r => r.on).map(r => r.name).join() === '不熟悉词汇', rows);
    check(P('sub rows >= 44px, row ⋯ >= 44px wide'), rows.every(r => r.h >= 44 && r.more >= 44), rows);
    const add = await rect(page, '#subsNew');
    check(P('「新建子分类」 is a full-size button in the sheet'), !!add && add.h >= 44 && add.w >= vw / 2, add);
    check(P('sub sheet is a bottom sheet'), await isBottomSheet(page, '#dlgSubs .ui-dialog', vw, vh));
    await shot(page, 'phone-subs');
    check(P('back closes the sub sheet'), (await pressBack(page)) && !(await shown(page, '#dlgSubs')));
    await page.tap('#vbSubToggle');
    await waitShown(page, '#dlgSubs');
    await page.tap(`#subsList [data-sub="${SUB.part3}"]`);
    await waitHidden(page, '#dlgSubs');
    check(P('picking a sub switches the list'), (await text(page, '#vbSubName')) === 'Part 3 学术场景' && (await cards(page)).length === 14);
    const top = await page.evaluate(() => ({ list: document.querySelector('#vbGrid .vb-card').getBoundingClientRect().top, bar: document.querySelector('.vb-rail-col').getBoundingClientRect().bottom }));
    check(P('switching mid-list shows the top of the new list'), top.list >= top.bar - 1 && top.list <= top.bar + 40, top);
  });

  // ---- 子分类：在面板里新建（不靠 29px 的小加号）、重命名别的子分类、删除
  await section(P('sub create / rename / delete'), async () => {
    await page.tap('#vbSubToggle');
    await waitShown(page, '#dlgSubs');
    await page.tap('#subsNew');
    await waitShown(page, '#dlgSub');
    check(P('new sub: name field focused'), (await activeId(page)) === 'dlgSubName');
    await page.fill('#dlgSubName', '手机新建');
    await page.tap('#dlgSubOk');
    check(P('new sub created and opened'), await toastSeen(page, '已新建「手机新建」') && (await text(page, '#vbSubName')) === '手机新建');
    check(P('empty sub: phone wording + 加词 button'), await shown(page, '#vbEmpty') && (await text(page, '#vbEmptyPhoneText')).includes('加词') && await shown(page, '#vbEmptyAdd') && !(await page.isVisible('#vbEmpty .vb-only-desk')));
    await shot(page, 'phone-empty');
    await page.tap('#vbEmptyAdd');
    check(P('empty state 加词 opens the add sheet'), await isOpenAdd(page));
    await page.tap('#vbAddClose');
    await page.tap('#vbSubToggle');
    await waitShown(page, '#dlgSubs');
    await page.tap(`#subsList [data-more="${SUB.part3}"]`);
    await waitShown(page, '#dlgActions');
    check(P('row ⋯ → rename / delete that sub'), (await text(page, '#actTitle')) === '「Part 3 学术场景」' && (await page.$$eval('#actList .vb-actitem', els => els.map(e => e.textContent.trim()).join('|'))) === '重命名|删除这个子分类');
    await shot(page, 'phone-sub-actions');
    await page.tap('#actList .vb-actitem:not(.is-danger)');
    await waitShown(page, '#dlgSub');
    check(P('rename prefilled with that sub'), (await page.$eval('#dlgSubName', e => e.value)) === 'Part 3 学术场景');
    await page.fill('#dlgSubName', 'Part 3 改名');
    await page.tap('#dlgSubOk');
    const names = async () => page.$$eval('#subsList .vb-row__name', els => els.map(e => e.textContent));
    check(P('rename a non-current sub from the sheet'), await toastSeen(page, '已改名为「Part 3 改名」') && await shown(page, '#dlgSubs') && (await names()).includes('Part 3 改名') && (await text(page, '#vbSubName')) === '手机新建');
    const curId = await page.$eval('#subsList .vb-row.is-on [data-sub]', e => e.dataset.sub);
    await page.tap(`#subsList [data-more="${curId}"]`);
    await waitShown(page, '#dlgActions');
    await page.tap('#actList .vb-actitem.is-danger');
    await waitShown(page, '#dlgConfirm');
    await page.tap('#cfOk');
    check(P('delete from the sheet'), await toastSeen(page, '已删除「手机新建」') && !(await names()).includes('手机新建'));
    await page.tap(`#subsList [data-sub="${SUB.unfamiliar}"]`);
    await waitHidden(page, '#dlgSubs');
  });

  // ---- 排序面板：选一种就关；收藏置顶开关就地切换
  await section(P('sort sheet'), async () => {
    await page.tap('#vbSortBtn');
    await waitShown(page, '#dlgSort');
    const opts = await page.$$eval('#sortList [role=radio]', els => els.map(e => ({ v: e.dataset.sort, on: e.getAttribute('aria-checked') === 'true', h: Math.round(e.getBoundingClientRect().height) })));
    check(P('sort sheet: 7 options, current checked, rows >= 44px'), opts.length === 7 && (opts.find(o => o.on) || {}).v === 'newest' && opts.every(o => o.h >= 44), opts);
    await shot(page, 'phone-sort');
    await page.tap('#sortList [data-sort="alphabetical"]');
    await waitHidden(page, '#dlgSort');
    let order = await cards(page);
    const favs = await page.$$eval('#vbGrid .vb-act--fav', els => els.map(e => e.getAttribute('aria-pressed') === 'true'));
    const favWords = order.filter((w, i) => favs[i]);
    const az = list => JSON.stringify(list) === JSON.stringify([...list].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())));
    check(P('A→Z with favourites on top'), favs.slice(0, 38).every(Boolean) && az(favWords));
    await page.tap('#vbSortBtn');
    await waitShown(page, '#dlgSort');
    await page.tap('#sortFav');
    check(P('收藏置顶 switch toggles in place'), (await page.$eval('#sortFav', e => e.getAttribute('aria-checked'))) === 'false' && await shown(page, '#dlgSort'));
    order = await cards(page);
    check(P('switch off → pure A→Z, saved'), az(order) && (await prefs(page)).sortType === 'alphabetical-pure');
    await page.tap('#sortList [data-sort="random"]');
    await page.tap('#vbSortBtn');
    await waitShown(page, '#dlgSort');
    check(P('switch disabled for random'), await page.$eval('#sortFav', e => e.disabled));
    await page.tap('#sortList [data-sort="newest"]');
    await page.tap('#vbSortBtn');
    await waitShown(page, '#dlgSort');
    await page.tap('#sortFav');
    await page.tap('#dlgSort .ui-dialog__close');
    check(P('back to newest + 收藏置顶'), (await prefs(page)).sortType === 'newest');
  });

  // ---- 查找：吸顶条里换成搜索框，结果就在下面
  await section(P('search'), async () => {
    const total = (await cards(page)).length;
    await page.evaluate(() => window.scrollTo(0, 2000));
    await page.tap('#vbSearchBtn');
    check(P('search: field focused, tabs make room'), (await activeId(page)) === 'vbPSearch' && !(await shown(page, '#vbCats')));
    const px = await page.$eval('#vbPSearch', e => parseFloat(getComputedStyle(e).fontSize));
    check(P('search field 16px'), px >= 16, px);
    await page.fill('#vbPSearch', 'can');
    const found = await cards(page);
    check(P('search filters'), found.includes('canteen') && found.length < total, found.length);
    await page.fill('#vbPSearch', '食堂');
    check(P('search by meaning'), JSON.stringify(await cards(page)) === JSON.stringify(['canteen']), await cards(page));
    const first = await rect(page, '#vbGrid .vb-card');
    const bar = await rect(page, '.vb-rail-col');
    check(P('results start right under the search bar'), !!first && !!bar && first.y >= bar.b - 1 && first.y <= bar.b + 60, { first, bar });
    await shot(page, 'phone-search');
    await page.tap('#vbPSearchCancel');
    check(P('取消 clears the search'), (await cards(page)).length === total && await shown(page, '#vbCats') && (await page.$eval('#vbPSearch', e => e.value)) === '');
  });

  // ---- 加词面板：单词框回车跳到释义，释义框回车才添加；加完不关，接着加
  await section(P('add sheet'), async () => {
    const before = (await cards(page)).length;
    await page.tap('#vbPAdd');
    await page.waitForTimeout(280);
    check(P('加词 opens the add sheet, word field focused'), await isOpenAdd(page) && (await activeId(page)) === 'vbWord');
    check(P('add sheet is a bottom sheet'), await isBottomSheet(page, '#vbAddForm', vw, vh));
    check(P('add sheet title names the sub'), (await text(page, '#vbAddTitle')) === '加到「不熟悉词汇」');
    const px = await page.$$eval('#vbWord, #vbMeaning', els => els.map(e => parseFloat(getComputedStyle(e).fontSize)));
    check(P('add fields >= 16px'), px.every(s => s >= 16), px);
    check(P('enterkeyhint next / done'), (await page.$eval('#vbWord', e => e.getAttribute('enterkeyhint'))) === 'next' && (await page.$eval('#vbMeaning', e => e.getAttribute('enterkeyhint'))) === 'done');
    await page.type('#vbWord', 'meticulous');
    await page.press('#vbWord', 'Enter');
    await page.waitForTimeout(200);
    check(P('Return in the word field moves to the meaning, adds nothing'), (await activeId(page)) === 'vbMeaning' && (await cards(page)).length === before);
    await page.type('#vbMeaning', 'adj. 一丝不苟的');
    await page.press('#vbMeaning', 'Enter');
    await page.waitForFunction(() => document.getElementById('vbAddHint').textContent.includes('已添加'), null, { timeout: 4000 }).catch(() => {});
    check(P('Return in the meaning adds; sheet stays open for the next word'), await isOpenAdd(page) && (await text(page, '#vbAddHint')).includes('已添加「meticulous」') && (await activeId(page)) === 'vbWord' && (await cards(page)).length === before + 1);
    check(P('no toast over the add sheet'), (await page.$$eval('.ielts-toast', els => els.filter(e => e.textContent.includes('meticulous')).length)) === 0);
    await shot(page, 'phone-add');
    await page.fill('#vbWord', 'canteen');
    check(P('duplicate warning in the sheet'), (await text(page, '#vbAddHint')).includes('已经在这个子分类里了'));
    await page.fill('#vbWord', '');
    check(P('back closes the add sheet'), (await pressBack(page)) && !(await isOpenAdd(page)));
  });

  // ---- 页头 ⋯：导入 / 导出 / 子分类管理；导出、导入都是底部面板，范围分段不比面板宽（原来的 P0）
  await section(P('page ⋯ / export / import'), async () => {
    await page.tap('#vbMoreBtn');
    await waitShown(page, '#dlgActions');
    const items = await page.$$eval('#actList .vb-actitem', els => els.map(e => e.textContent.trim()));
    check(P('page ⋯ holds import / export / sub management'), items.join('|') === '导入 CSV|导出单词|新建子分类|重命名「不熟悉词汇」|删除「不熟悉词汇」', items);
    await shot(page, 'phone-more');
    await page.tap('#actList [data-i="1"]');
    await waitShown(page, '#dlgExport');
    const ex = await page.evaluate(() => {
      const dlg = document.querySelector('#dlgExport .ui-dialog');
      const seg = document.getElementById('expScope').getBoundingClientRect();
      return {
        dRight: dlg.getBoundingClientRect().right, segRight: seg.right, scroll: dlg.scrollWidth - dlg.clientWidth,
        btns: Array.from(document.querySelectorAll('#expScope .ui-seg__btn')).map(b => Math.round(b.getBoundingClientRect().width)),
        checks: Array.from(document.querySelectorAll('#dlgExport .vb-check')).map(e => Math.round(e.getBoundingClientRect().height))
      };
    });
    check(P('export: 范围 segment fits the sheet, equal buttons'), ex.segRight <= ex.dRight && ex.scroll <= 0 && Math.max(...ex.btns) - Math.min(...ex.btns) <= 1, ex);
    check(P('export: checkbox rows >= 40px'), ex.checks.length === 5 && ex.checks.every(h => h >= 40), ex.checks);
    check(P('export is a bottom sheet, no page overflow'), await isBottomSheet(page, '#dlgExport .ui-dialog', vw, vh) && (await overflow(page)) <= 0);
    await shot(page, 'phone-export');
    const [dl] = await Promise.all([page.waitForEvent('download', { timeout: 5000 }), page.tap('#expOk')]);
    check(P('export downloads from the sheet'), dl.suggestedFilename() === 'listening_不熟悉词汇_单词.csv', dl.suggestedFilename());
    await page.tap('#vbMoreBtn');
    await waitShown(page, '#dlgActions');
    await page.tap('#actList [data-i="0"]');
    await waitShown(page, '#dlgImport');
    check(P('import: no drag-and-drop wording'), !(await text(page, '#impDropSub')).includes('拖'), await text(page, '#impDropSub'));
    check(P('import is a bottom sheet'), await isBottomSheet(page, '#dlgImport .ui-dialog', vw, vh));
    await shot(page, 'phone-import');
    await page.tap('#dlgImport .ui-dialog__close');
    await waitHidden(page, '#dlgImport');
  });

  // ---- 单词挑战：设置面板 → 全屏答题（选项在下半屏）→ 返回键先问 → 结果
  await section(P('challenge'), async () => {
    const vocab = (await (await fetch(BASE + '/api/vocabulary', { headers: { Authorization: 'Bearer ' + TOKEN } })).json()).data;
    const words = vocab.categories.listening.subcategories[SUB.unfamiliar].words;
    await page.tap('#vbPChallenge');
    await waitShown(page, '#dlgChallenge');
    await page.waitForTimeout(300);
    const st = await page.evaluate(() => {
      const dlg = document.querySelector('#dlgChallenge .ui-dialog');
      return {
        dRight: dlg.getBoundingClientRect().right, segRight: document.getElementById('chScope').getBoundingClientRect().right, scroll: dlg.scrollWidth - dlg.clientWidth,
        chips: Array.from(document.querySelectorAll('#chCount .ui-chip')).map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)]; })
      };
    });
    check(P('challenge: 范围 segment fits the sheet'), st.segRight <= st.dRight && st.scroll <= 0, st);
    check(P('challenge: 题数 in one row, >= 44px'), new Set(st.chips.map(c => c[0])).size === 1 && st.chips.every(c => c[1] >= 44), st.chips);
    check(P('challenge setup is a bottom sheet'), await isBottomSheet(page, '#dlgChallenge .ui-dialog', vw, vh));
    await shot(page, 'phone-challenge');
    await page.tap('#chCount [data-value="5"]');
    await page.tap('#chOk');
    await waitShown(page, '#dlgQuiz');
    await page.waitForTimeout(400);
    const qz = await page.evaluate(() => {
      const d = document.getElementById('qDialog').getBoundingClientRect();
      const x = document.querySelector('#dlgQuiz .ui-dialog__close').getBoundingClientRect();
      const key = document.querySelector('#qOptions .vb-option__key');
      return {
        d: [d.x, d.y, d.width, d.height], x: [x.width, x.height], key: !!key && key.getClientRects().length > 0, foot: document.getElementById('qFoot').textContent,
        opts: Array.from(document.querySelectorAll('#qOptions .vb-option')).map(e => { const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)]; })
      };
    });
    check(P('quiz fills the screen'), Math.abs(qz.d[0]) <= 1 && Math.abs(qz.d[1]) <= 1 && Math.abs(qz.d[2] - vw) <= 1 && Math.abs(qz.d[3] - vh) <= 1, qz.d);
    check(P('quiz options in the lower half, >= 56px'), qz.opts.length === 4 && qz.opts[0][0] >= vh * 0.45 && qz.opts.every(o => o[1] >= 56), qz.opts);
    check(P('quiz: × 44px, no 1–4 key badges or hint'), qz.x[0] >= 44 && qz.x[1] >= 44 && !qz.key && !qz.foot.includes('键'), qz);
    await shot(page, 'phone-quiz');
    check(P('back during the quiz asks before quitting'), (await pressBack(page)) && await shown(page, '#dlgConfirm') && (await text(page, '#cfTitle')) === '退出这次挑战？');
    await page.tap('#cfCancel');
    check(P('继续答题 keeps the quiz'), await shown(page, '#dlgQuiz') && !(await shown(page, '#dlgConfirm')));
    // 故意全答错，结果里就有 5 行「需要复习」可以检查
    for (let i = 0; i < 5; i++) {
      await page.waitForFunction(n => document.getElementById('qCount').textContent.includes('第 ' + n + ' / 5 题') && !document.querySelector('#qOptions .vb-option:disabled'), i + 1, { timeout: 6000 });
      const q = await page.evaluate(() => ({ word: (document.querySelector('#qQuestion .vb-quiz-word') || {}).textContent || null, mean: (document.querySelector('#qQuestion .vb-quiz-mean') || {}).textContent || null, opts: Array.from(document.querySelectorAll('#qOptions .vb-option__text')).map(e => e.textContent) }));
      const right = q.word ? words.filter(w => w.word === q.word).map(w => w.meaning) : words.filter(w => w.meaning === q.mean).map(w => w.word);
      const pick = Math.max(0, q.opts.findIndex(t => !right.includes(t)));
      await page.locator('#qOptions .vb-option').nth(pick).tap();
      await page.waitForSelector('#qOptions .vb-option.is-right');
      if (i === 0) await shot(page, 'phone-quiz-answered');
    }
    await waitShown(page, '#dlgResult', 6000);
    await page.waitForFunction(() => !document.getElementById('rSummary').textContent.includes('正在'), null, { timeout: 5000 }).catch(() => {});
    const rv = await page.evaluate(() => ({
      words: Array.from(document.querySelectorAll('#rReview .vb-review__word')).map(e => {
        const range = document.createRange();
        range.selectNodeContents(e);
        return { w: e.textContent, lines: new Set(Array.from(range.getClientRects()).map(r => Math.round(r.top))).size };
      }),
      foot: Array.from(document.querySelectorAll('#dlgResult .ui-dialog__foot .ui-btn')).map(b => Math.round(b.getBoundingClientRect().height))
    }));
    check(P('result: review words are not broken mid-word'), rv.words.length >= 1 && rv.words.every(w => w.w.length > 14 || w.lines === 1), rv.words);
    check(P('result is a bottom sheet with 44px buttons'), await isBottomSheet(page, '#dlgResult .ui-dialog', vw, vh) && rv.foot.length === 2 && rv.foot.every(h => h >= 44), rv.foot);
    await shot(page, 'phone-result');
    await page.tap('#rAgain');
    await waitShown(page, '#dlgChallenge');
    await page.tap('#chOk');
    await waitShown(page, '#dlgQuiz');
    await pressBack(page);
    await waitShown(page, '#dlgConfirm');
    await page.tap('#cfOk');
    await page.waitForTimeout(300);
    check(P('quit by back: quiz closed, still on the page'), !(await shown(page, '#dlgQuiz')) && !(await shown(page, '#dlgConfirm')) && (await page.evaluate(() => window.__stay === 1 && location.pathname === '/vocabulary')));
  });

  // ---- 键盘弹出（视口只剩约 470px）：加词、查找、新建子分类的输入框和按钮都还看得见
  await section(P('keyboard-height viewport'), async () => {
    await page.setViewportSize({ width: vw, height: KB_HEIGHT });
    await page.waitForTimeout(200);
    await page.tap('#vbPAdd');
    await page.waitForTimeout(300);
    const box = ids => page.evaluate(list => list.map(id => { const r = document.getElementById(id).getBoundingClientRect(); return [id, Math.round(r.top), Math.round(r.bottom)]; }), ids);
    const a = await box(['vbAddTitle', 'vbWord', 'vbMeaning', 'vbAddBtn']);
    check(P(`keyboard ${KB_HEIGHT}px: add sheet fields and 添加 visible`), a.every(([, t, b]) => t >= 0 && b <= KB_HEIGHT), a);
    await shot(page, 'phone-add-kb');
    await page.tap('#vbAddClose');
    await page.tap('#vbSearchBtn');
    await page.fill('#vbPSearch', 'ab');
    const s = await box(['vbPSearch', 'vbPSearchCancel']);
    const card = await rect(page, '#vbGrid .vb-card');
    const bar = await rect(page, '#vbPbar');
    check(P(`keyboard ${KB_HEIGHT}px: search field, 取消 and a result visible`), s.every(([, t, b]) => t >= 0 && b <= KB_HEIGHT) && !!card && card.b <= bar.y, { s, card, bar: bar && bar.y });
    await shot(page, 'phone-search-kb');
    await page.tap('#vbPSearchCancel');
    await page.tap('#vbMoreBtn');
    await waitShown(page, '#dlgActions');
    await page.tap('#actList [data-i="2"]');
    await waitShown(page, '#dlgSub');
    const n = await box(['dlgSubName', 'dlgSubOk']);
    check(P(`keyboard ${KB_HEIGHT}px: new-sub field and 新建 visible`), n.every(([, t, b]) => t >= 0 && b <= KB_HEIGHT), n);
    await shot(page, 'phone-newsub-kb');
    await page.tap('#dlgSub .ui-dialog__close');
    await page.setViewportSize({ width: vw, height: vh });
  });
}

async function phoneDark(page, P) {
  await section(P('dark'), async () => {
    const bgs = await page.evaluate(() => [document.body, document.querySelector('.vb-rail-col'), document.getElementById('vbPbar'), document.querySelector('#vbGrid .vb-card')].map(e => getComputedStyle(e).backgroundColor));
    check(P('page, sticky bar, bottom bar and cards are dark'), bgs.every(isDark), bgs);
    await shot(page, 'phone-dark-main');
    await page.tap('#vbSubToggle');
    await waitShown(page, '#dlgSubs');
    const sheet = await page.$eval('#dlgSubs .ui-dialog', e => getComputedStyle(e).backgroundColor);
    check(P('sheets are dark'), isDark(sheet), sheet);
    await shot(page, 'phone-dark-subs');
    await page.tap('#dlgSubs .ui-dialog__close');
    await page.tap('#vbPAdd');
    const add = await page.$eval('#vbAddForm', e => getComputedStyle(e).backgroundColor);
    check(P('add sheet is dark'), isDark(add), add);
    await shot(page, 'phone-dark-add');
    await page.tap('#vbAddClose');
    await page.tap('#vbPChallenge');
    await waitShown(page, '#dlgChallenge');
    await page.tap('#chOk');
    await waitShown(page, '#dlgQuiz');
    await page.waitForTimeout(400);
    const quiz = await page.$eval('#qDialog', e => getComputedStyle(e).backgroundColor);
    check(P('quiz is dark'), isDark(quiz), quiz);
    await shot(page, 'phone-dark-quiz');
    await page.tap('#dlgQuiz .ui-dialog__close');
    await waitShown(page, '#dlgConfirm');
    await page.tap('#cfOk');
  });
}

// iOS 只让「在手指点的那一下里 play() 过」的 audio 元素以后自动播放。点「开始挑战」这一下里要先 play() 一次，
// 之后自动读题用同一个 audio 元素。Playwright 的 WebKit 不拦自动播放，只能这样间接查；真机上还要听一下
async function phoneAudioUnlock(browser, dev) {
  resetData();
  const { ctx, page } = await newPage(browser, { width: dev.width, height: dev.height, mobile: true, isMobile: dev.isMobile, prefs: { category: 'listening', subcategory: SUB.unfamiliar, sortType: 'newest', meaningsVisible: true } });
  const P = n => `phone ${dev.width}: ${n}`;
  await open(page);
  await section(P('quiz audio unlock'), async () => {
    await page.evaluate(() => {
      window.__plays = [];
      let inTap = false;
      document.addEventListener('click', () => { inTap = true; setTimeout(() => { inTap = false; }, 0); }, true);
      const seen = [];
      const play = HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play = function () {
        if (!seen.includes(this)) seen.push(this);
        window.__plays.push({ src: String(this.src).slice(0, 40), inTap: inTap, el: seen.indexOf(this) });
        return play.apply(this, arguments);
      };
    });
    // 用看得见的那个「单词挑战」（在 mobile/base 上是页头那个），这样旧版本是「没解锁」而不是「找不到按钮」
    await page.tap((await shown(page, '#vbPChallenge')) ? '#vbPChallenge' : '#vbChallengeBtn');
    await waitShown(page, '#dlgChallenge');
    await page.tap('#chOk');
    await waitShown(page, '#dlgQuiz');
    for (let i = 0; i < 4; i++) {
      await page.waitForFunction(n => document.getElementById('qCount').textContent.includes('第 ' + n + ' / 10 题') && !document.querySelector('#qOptions .vb-option:disabled'), i + 1, { timeout: 6000 });
      await page.waitForTimeout(400);
      await page.locator('#qOptions .vb-option').first().tap();
    }
    await page.waitForTimeout(700);
    const plays = await page.evaluate(() => window.__plays);
    const inTap = plays.filter(p => p.inTap);
    const auto = plays.filter(p => !p.inTap);
    check(P('开始挑战 tap itself calls play() (unlocks audio on iOS)'), inTap.length >= 1, plays);
    check(P('auto-read words reuse that unlocked audio element'), inTap.length >= 1 && auto.length >= 1 && auto.every(p => p.el === inTap[0].el), plays);
    await page.tap('#dlgQuiz .ui-dialog__close');
    await waitShown(page, '#dlgConfirm');
    await page.tap('#cfOk');
  });
  check(P('no page errors (audio unlock)'), page.errors.length === 0, page.errors);
  await ctx.close();
}

// 加载中 / 出错：不显示空的子分类下拉、点不动的底部条和 ⋯
async function phoneLoadingAndError(browser, dev) {
  const { ctx, page } = await newPage(browser, { width: dev.width, height: dev.height, mobile: true, isMobile: dev.isMobile });
  const P = n => `phone ${dev.width}: ${n}`;
  await section(P('loading / error'), async () => {
    let release;
    const gate = new Promise(r => { release = r; });
    await page.route('**/api/vocabulary', async route => { await gate; await route.fulfill({ status: 500, contentType: 'application/json', body: '{"success":false,"error":"测试用的错误"}' }); });
    await page.goto(BASE + '/vocabulary');
    await page.waitForTimeout(500);
    const moreHidden = await page.$eval('#vbMoreBtn', e => getComputedStyle(e).visibility === 'hidden' || e.getClientRects().length === 0);
    check(P('loading: no empty sub picker, bottom bar or ⋯ yet'), await shown(page, '#vbStatus') && !(await shown(page, '#vbSubToggle')) && !(await shown(page, '#vbPbar')) && moreHidden);
    await shot(page, 'phone-loading');
    release();
    await page.waitForFunction(() => document.getElementById('vbStatus').textContent.includes('没加载出来'), null, { timeout: 5000 });
    check(P('error: message + 重新加载, no dead buttons'), await shown(page, '#vbStatus .ui-btn') && !(await shown(page, '#vbPbar')) && !(await shown(page, '#vbSubToggle')));
    await shot(page, 'phone-error');
    await page.unroute('**/api/vocabulary');
    await page.tap('#vbStatus .ui-btn');
    await page.waitForSelector('#vbContent:not([hidden])', { timeout: 5000 });
    check(P('重新加载 brings the bars back'), await shown(page, '#vbPbar') && await shown(page, '#vbSubToggle'));
  });
  await ctx.close();
}

// ============================================================ edit a word: desktop 1280 + phone (WebKit 390×844 / Chromium 360×780)
// 编辑单词：桌面是卡片上的铅笔（和删除一样悬停卡片才出现），手机是单词卡 ⋯ 里的「编辑」（在「删除」上面）。
// 改单词和释义、保存后卡片原地更新（id 不变、位置和滚动不变、排序 / 查找 / 遮释义照旧）、刷新还在；
// 单词清空报错不关面板；取消 / Esc / 返回键什么都不改。拼写改了以后旧 TTS 音频删掉（读的是旧词）。
// 在 main 上跑时铅笔、「编辑」和编辑面板都不存在，每一段都记成 FAIL
const EDIT_PREFS = () => ({ category: 'listening', subcategory: SUB.unfamiliar, sortType: 'newest', meaningsVisible: true });
const cardById = (page, id) => page.locator(`#vbGrid .vb-card[data-id="${id}"]`);
// 一张卡现在的样子：单词、释义、释义遮没遮、在列表里第几张
const cardInfo = (page, id) => page.evaluate(id => {
  const all = Array.from(document.querySelectorAll('#vbGrid .vb-card'));
  const c = all.find(e => e.dataset.id === id);
  if (!c) return { missing: true, count: all.length };
  const m = c.querySelector('.vb-meaning');
  return { word: c.querySelector('.vb-word').textContent.trim(), meaning: m.textContent.trim(), masked: m.classList.contains('is-masked'), index: all.indexOf(c), count: all.length };
}, id);
function storedWord(id) {
  for (const cat of ['listening', 'speaking', 'reading', 'writing']) {
    for (const s of Object.values(readCategory(cat).subcategories)) {
      const w = s.words.find(x => x.id === id);
      if (w) return w;
    }
  }
  return null;
}
const audioFile = id => path.join(SANDBOX, 'vocabulary_book/audio/listening', id + '.mp3');
const isAZ = list => JSON.stringify(list) === JSON.stringify([...list].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())));
const clearToasts = page => page.evaluate(() => document.querySelectorAll('.ielts-toast').forEach(t => t.remove()));
const scrollY = page => page.evaluate(() => window.scrollY);
const boxes = (page, ids) => page.evaluate(list => list.map(id => { const r = document.getElementById(id).getBoundingClientRect(); return [id, Math.round(r.top), Math.round(r.bottom)]; }), ids);
// 记下编辑请求（PUT /api/vocabulary/<id>）的内容
function trackEdits(page) {
  const puts = [];
  page.on('request', r => { if (r.method() === 'PUT' && /^\/api\/vocabulary\/[^/]+$/.test(new URL(r.url()).pathname)) puts.push(JSON.parse(r.postData() || '{}')); });
  return puts;
}
const editorState = page => page.evaluate(() => ({
  title: document.getElementById('edTitle').textContent.trim(), word: document.getElementById('edWord').value, meaning: document.getElementById('edMeaning').value,
  focus: document.activeElement && document.activeElement.id, ok: document.getElementById('edOk').textContent.trim(),
  hint: document.getElementById('edHint').textContent.trim(), warn: document.getElementById('edHint').classList.contains('is-warn')
}));

async function editSuite(browser) {
  await desktopEdit(browser);
  await phoneEdit(browser);
}

async function desktopEdit(browser) {
  resetData();
  let { ctx, page } = await newPage(browser, { prefs: EDIT_PREFS() });
  const puts = trackEdits(page);
  const P = n => 'edit 1280: ' + n;
  await open(page);
  const words0 = readCategory('listening').subcategories[SUB.unfamiliar].words;
  const before = words0.find(w => w.word === 'canteen');
  const id = before.id;
  const card = cardById(page, id);
  const openEditor = async () => {
    await card.scrollIntoViewIfNeeded();
    await card.hover();
    await card.locator('.vb-act--edit').click();
    await waitShown(page, '#dlgEdit');
  };

  await section(P('pencil'), async () => {
    await card.scrollIntoViewIfNeeded();
    await page.mouse.move(5, 5);
    await page.waitForTimeout(250);
    const hiddenOp = await card.locator('.vb-act--edit').evaluate(e => getComputedStyle(e).opacity);
    await card.hover();
    await page.waitForTimeout(250);
    const shownOp = await card.locator('.vb-act--edit').evaluate(e => getComputedStyle(e).opacity);
    check(P('pencil hidden until the card is hovered, like delete'), hiddenOp === '0' && shownOp === '1', { hiddenOp, shownOp });
    const e = await card.locator('.vb-act--edit').boundingBox();
    const d = await card.locator('.vb-act--del').boundingBox();
    check(P('pencil sits left of delete, same size and row'), e.x + e.width <= d.x + 0.5 && Math.abs(e.y - d.y) < 1 && Math.abs(e.width - d.width) < 1 && Math.abs(e.height - d.height) < 1, { e, d });
    check(P('pencil is labelled'), (await card.locator('.vb-act--edit').getAttribute('aria-label')) === '编辑 canteen');
    await shot(page, 'light-1280-edit-hover');
  });

  await section(P('editor'), async () => {
    await openEditor();
    const s = await editorState(page);
    check(P('pencil opens 编辑单词 prefilled, word focused, 保存'), s.title === '编辑单词' && s.word === 'canteen' && s.meaning === 'n. 食堂' && s.focus === 'edWord' && s.ok === '保存' && !s.warn, s);
    const dlg = await rect(page, '#dlgEdit .ui-dialog');
    check(P('desktop editor is a centred dialog'), !!dlg && dlg.w <= 521 && Math.abs((dlg.x + dlg.w / 2) - 640) <= 2 && dlg.b < 900 - 20, dlg);
    await shot(page, 'light-1280-edit');
    await page.fill('#edWord', '');
    await page.click('#edOk');
    await page.waitForTimeout(200);
    let t = await editorState(page);
    check(P('empty word: error under the field, dialog stays, nothing sent'), t.hint === '单词不能为空' && t.warn && await shown(page, '#dlgEdit') && puts.length === 0, t);
    await shot(page, 'light-1280-edit-empty');
    await page.fill('#edWord', 'Biodiversity');
    t = await editorState(page);
    check(P('duplicate in the same sub warned while typing'), t.warn && t.hint.includes('已经在这个子分类里了'), t);
    await page.click('#edOk');
    await page.waitForTimeout(200);
    check(P('duplicate is not saved'), await shown(page, '#dlgEdit') && puts.length === 0);
    await page.fill('#edWord', 'cantina');
    await page.click('#dlgEdit .ui-dialog__foot [data-close]');
    await waitHidden(page, '#dlgEdit');
    check(P('取消 leaves the card unchanged'), (await cardInfo(page, id)).word === 'canteen' && storedWord(id).word === 'canteen' && puts.length === 0);
    await openEditor();
    t = await editorState(page);
    check(P('reopening starts from the stored text, no stale error'), t.word === 'canteen' && t.meaning === 'n. 食堂' && !t.warn, t);
    await page.fill('#edWord', 'cantina');
    await page.keyboard.press('Escape');
    await waitHidden(page, '#dlgEdit');
    check(P('Esc leaves the card unchanged'), (await cardInfo(page, id)).word === 'canteen' && puts.length === 0);
  });

  await section(P('save'), async () => {
    await openEditor();
    const y0 = await scrollY(page);
    const info0 = await cardInfo(page, id);
    await page.fill('#edWord', 'cafeteria');
    await page.fill('#edMeaning', 'n. 自助餐厅');
    await clearToasts(page);
    await page.click('#edOk');
    check(P('save shows a toast'), await toastSeen(page, '已保存「cafeteria」'));
    await waitHidden(page, '#dlgEdit');
    const info1 = await cardInfo(page, id);
    check(P('card updates in place: same card, same position, new text'), info1.word === 'cafeteria' && info1.meaning === 'n. 自助餐厅' && info1.index === info0.index && info1.count === info0.count, { info0, info1 });
    check(P('scroll position kept'), Math.abs((await scrollY(page)) - y0) <= 1, { y0, y1: await scrollY(page) });
    check(P('focus back on that card\'s pencil'), await page.evaluate(id => { const a = document.activeElement; return !!a && a.classList.contains('vb-act--edit') && a.closest('.vb-card').dataset.id === id; }, id));
    const after = storedWord(id);
    check(P('saved on the server: same id, favourite and date kept'), after && after.word === 'cafeteria' && after.meaning === 'n. 自助餐厅' && after.is_favorited === before.is_favorited && after.created_at === before.created_at, after);
    check(P('one request with the new word and meaning'), puts.length === 1 && puts[0].word === 'cafeteria' && puts[0].meaning === 'n. 自助餐厅', puts);
    check(P('new spelling drops the old TTS file'), before.audio_generated === true && after.audio_generated === false && !fs.existsSync(audioFile(id)), after);
    // 有道取不到时不再退回旧音频（读的是 canteen），直接提示
    await page.route('**/dictvoice**', route => route.fulfill({ status: 500, contentType: 'application/json', body: '{"msg":"null audio"}' }));
    page.fallback = [];
    page.youdao = [];
    await card.locator('.vb-word').click();
    check(P('renamed word plays the new spelling, never the old TTS file'), await toastSeen(page, '没取到「cafeteria」的发音') && page.youdao.includes('cafeteria') && page.fallback.length === 0, { youdao: page.youdao, fallback: page.fallback });
    await page.unroute('**/dictvoice**');
  });

  await section(P('meaning only'), async () => {
    const other = words0.find(w => w.audio_generated && w.id !== id);
    await cardById(page, other.id).scrollIntoViewIfNeeded();
    await cardById(page, other.id).hover();
    await cardById(page, other.id).locator('.vb-act--edit').click();
    await waitShown(page, '#dlgEdit');
    await page.fill('#edMeaning', '改过的释义');
    await clearToasts(page);
    await page.press('#edMeaning', 'Enter');
    check(P('Enter saves'), await toastSeen(page, '已保存「' + other.word + '」'));
    const s = storedWord(other.id);
    check(P('meaning-only edit sends only the meaning, keeps word and TTS file'), JSON.stringify(puts[puts.length - 1]) === JSON.stringify({ meaning: '改过的释义' }) && s.word === other.word && s.meaning === '改过的释义' && s.audio_generated === true && fs.existsSync(audioFile(other.id)), { put: puts[puts.length - 1], s });
  });

  await section(P('masked'), async () => {
    await page.click('#vbHide');
    await openEditor();
    check(P('editor shows the meaning while cards are masked'), (await editorState(page)).meaning === 'n. 自助餐厅');
    await page.fill('#edMeaning', 'n. 自助餐厅，食堂');
    await clearToasts(page);
    await page.click('#edOk');
    await toastSeen(page, '已保存「cafeteria」');
    await page.mouse.move(5, 5);
    const i = await cardInfo(page, id);
    check(P('after saving, meanings stay masked'), i.masked && i.meaning === 'n. 自助餐厅，食堂' && await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => e.classList.contains('is-masked'))), i);
    await page.click('#vbHide');
  });

  await section(P('search'), async () => {
    await page.fill('#vbSearch', '自助');
    check(P('search finds the edited meaning'), JSON.stringify(await cards(page)) === JSON.stringify(['cafeteria']), await cards(page));
    await openEditor();
    await page.fill('#edWord', 'cafeterias');
    await clearToasts(page);
    await page.click('#edOk');
    await toastSeen(page, '已保存「cafeterias」');
    check(P('edited word stays in the results, count line consistent'), JSON.stringify(await cards(page)) === JSON.stringify(['cafeterias']) && (await text(page, '#vbCountLine')) === '找到 1 个', { cards: await cards(page), line: await text(page, '#vbCountLine') });
    await openEditor();
    await page.fill('#edMeaning', 'n. 食堂');
    await clearToasts(page);
    await page.click('#edOk');
    await toastSeen(page, '已保存「cafeterias」');
    check(P('an edit that no longer matches leaves the results'), (await cards(page)).length === 0 && (await text(page, '#vbCountLine')).includes('没有包含「自助」'), { cards: await cards(page), line: await text(page, '#vbCountLine') });
    await page.fill('#vbSearch', '');
  });

  await section(P('sort'), async () => {
    await page.selectOption('#vbSort', 'alphabetical');
    await page.click('#vbFavFirst');   // 纯 A→Z
    const order0 = await cards(page);
    const firstId = await page.$eval('#vbGrid .vb-card', e => e.dataset.id);
    const c = cardById(page, firstId);
    await c.hover();
    await c.locator('.vb-act--edit').click();
    await waitShown(page, '#dlgEdit');
    await page.fill('#edWord', 'zygote');
    await clearToasts(page);
    await page.click('#edOk');
    await toastSeen(page, '已保存「zygote」');
    const order1 = await cards(page);
    check(P('A→Z order re-sorted after renaming'), isAZ(order1) && order1[order1.length - 1] === 'zygote' && order1.length === order0.length && !order1.includes(order0[0]), order1.slice(-3));
    await page.selectOption('#vbSort', 'newest');
    await page.click('#vbFavFirst');
  });

  await section(P('reload'), async () => {
    await page.reload();
    await page.waitForSelector('#vbContent:not([hidden])');
    const i = await cardInfo(page, id);
    const list = await cards(page);
    check(P('edits survive a reload'), i.word === 'cafeterias' && i.meaning === 'n. 食堂' && list.includes('zygote') && !list.includes('canteen'), { i, zygote: list.includes('zygote') });
  });
  check(P('no page errors'), page.errors.length === 0, page.errors);
  await ctx.close();

  ({ ctx, page } = await newPage(browser, { theme: 'dark', prefs: EDIT_PREFS() }));
  await open(page);
  await section(P('dark'), async () => {
    const c = page.locator('#vbGrid .vb-card').first();
    await c.hover();
    await c.locator('.vb-act--edit').click();
    await waitShown(page, '#dlgEdit');
    const bgs = await page.evaluate(() => ['#dlgEdit .ui-dialog', '#edWord'].map(s => getComputedStyle(document.querySelector(s)).backgroundColor));
    check(P('dark: editor and fields are dark'), bgs.every(isDark), bgs);
    await shot(page, 'dark-1280-edit');
    await page.keyboard.press('Escape');
  });
  check(P('no page errors (dark)'), page.errors.length === 0, page.errors);
  await ctx.close();
}

async function phoneEdit(browser) {
  const dev = PHONE[engine] || PHONE.webkit;
  const vw = dev.width, vh = dev.height;
  const P = n => `edit phone ${vw}: ${n}`;
  resetData();
  let { ctx, page } = await newPage(browser, { width: vw, height: vh, mobile: true, isMobile: dev.isMobile, prefs: EDIT_PREFS() });
  const puts = trackEdits(page);
  await open(page);
  let id = null, word0 = '', before = null;
  const openEditor = async () => {
    await cardById(page, id).locator('.vb-act--more').tap();
    await waitShown(page, '#dlgActions');
    await page.locator('#actList .vb-actitem', { hasText: /^编辑$/ }).tap();
    await waitShown(page, '#dlgEdit');
  };

  await section(P('menu'), async () => {
    check(P('no pencil on phone cards (it lives in ⋯)'), !(await shown(page, '#vbGrid .vb-act--edit')));
    // 在列表中间编辑，好查滚动位置有没有跳
    await page.evaluate(() => window.scrollTo(0, 1500));
    await page.waitForTimeout(200);
    const pick = await page.evaluate(() => {
      let best = null;
      document.querySelectorAll('#vbGrid .vb-card').forEach(c => {
        const r = c.getBoundingClientRect();
        const d = Math.abs(r.top + r.height / 2 - innerHeight / 2);
        if (!best || d < best.d) best = { d: d, id: c.dataset.id, word: c.querySelector('.vb-word').textContent.trim() };
      });
      return best;
    });
    id = pick.id;
    word0 = pick.word;
    before = storedWord(id);
    await cardById(page, id).locator('.vb-act--more').tap();
    await waitShown(page, '#dlgActions');
    const items = await page.$$eval('#actList .vb-actitem', els => els.map(e => { const r = e.getBoundingClientRect(); return { t: e.textContent.trim(), y: Math.round(r.top), h: Math.round(r.height) }; }));
    const names = items.map(i => i.t);
    const iEdit = names.indexOf('编辑');
    const iDel = names.indexOf('删除这个单词');
    check(P('card ⋯ has 编辑 right above 删除, row >= 44px'), iEdit !== -1 && iDel === iEdit + 1 && items[iEdit].y < items[iDel].y && items[iEdit].h >= 44, items);
    await shot(page, 'phone-edit-menu');
    await page.tap('#dlgActions .ui-dialog__close');
    await waitHidden(page, '#dlgActions');
  });

  await section(P('editor sheet'), async () => {
    const y0 = await scrollY(page);
    await openEditor();
    const s = await editorState(page);
    check(P('编辑 opens 编辑单词 prefilled, word focused, 保存'), s.title === '编辑单词' && s.word === word0 && s.meaning === before.meaning && s.focus === 'edWord' && s.ok === '保存', s);
    check(P('editor is a bottom sheet'), await isBottomSheet(page, '#dlgEdit .ui-dialog', vw, vh));
    const sz = await page.evaluate(() => ({
      fields: ['edWord', 'edMeaning'].map(id => { const e = document.getElementById(id); return [parseFloat(getComputedStyle(e).fontSize), Math.round(e.getBoundingClientRect().height)]; }),
      btns: Array.from(document.querySelectorAll('#dlgEdit .ui-dialog__foot .ui-btn')).map(b => Math.round(b.getBoundingClientRect().height))
    }));
    check(P('fields >= 16px text and >= 44px tall; 取消 / 保存 >= 44px'), sz.fields.every(([f, h]) => f >= 16 && h >= 44) && sz.btns.length === 2 && sz.btns.every(h => h >= 44), sz);
    check(P('no horizontal overflow with the editor open'), (await overflow(page)) <= 0);
    await shot(page, 'phone-edit');
    await page.press('#edWord', 'Enter');
    await page.waitForTimeout(150);
    check(P('Return in the word field moves to the meaning, saves nothing'), (await activeId(page)) === 'edMeaning' && puts.length === 0 && await shown(page, '#dlgEdit'));
    await page.fill('#edWord', word0 + 'x');
    check(P('back closes the editor, card unchanged, page stays'), (await pressBack(page)) && !(await shown(page, '#dlgEdit')) && (await cardInfo(page, id)).word === word0 && puts.length === 0);
    check(P('scroll position kept after back'), Math.abs((await scrollY(page)) - y0) <= 2, { y0, y: await scrollY(page) });
    await openEditor();
    check(P('reopening starts from the stored text'), (await editorState(page)).word === word0);
    await page.fill('#edWord', word0 + 'x');
    await page.tap('#dlgEdit .ui-dialog__foot [data-close]');
    await waitHidden(page, '#dlgEdit');
    check(P('取消 leaves the card unchanged'), (await cardInfo(page, id)).word === word0 && storedWord(id).word === word0 && puts.length === 0);
  });

  await section(P('empty + save'), async () => {
    await openEditor();
    await page.fill('#edWord', '');
    await page.tap('#edOk');
    await page.waitForTimeout(200);
    const t = await editorState(page);
    check(P('empty word: error shown in the sheet, sheet stays open'), t.hint === '单词不能为空' && t.warn && await shown(page, '#dlgEdit') && puts.length === 0, t);
    await shot(page, 'phone-edit-empty');
    await page.fill('#edWord', 'serendipity');
    await page.fill('#edMeaning', 'n. 意外发现好东西的运气');
    const y0 = await scrollY(page);
    const info0 = await cardInfo(page, id);
    await clearToasts(page);
    await page.press('#edMeaning', 'Enter');
    check(P('Return in the meaning saves, toast confirms'), await toastSeen(page, '已保存「serendipity」'));
    await waitHidden(page, '#dlgEdit');
    await page.waitForTimeout(400);
    const info1 = await cardInfo(page, id);
    check(P('card updates in place, same position'), info1.word === 'serendipity' && info1.meaning === 'n. 意外发现好东西的运气' && info1.index === info0.index && info1.count === info0.count, { info0, info1 });
    check(P('scroll position kept after saving'), Math.abs((await scrollY(page)) - y0) <= 2, { y0, y: await scrollY(page) });
    const t2 = await rect(page, '.ielts-toast');
    const bar = await rect(page, '#vbPbar');
    check(P('toast floats above the bottom bar'), !!t2 && !!bar && t2.b <= bar.y, { t2, bar });
    const after = storedWord(id);
    check(P('saved: same id, favourite and date kept'), after && after.word === 'serendipity' && after.meaning === 'n. 意外发现好东西的运气' && after.is_favorited === before.is_favorited && after.created_at === before.created_at, after);
    check(P('no horizontal overflow after saving'), (await overflow(page)) <= 0);
    await shot(page, 'phone-edit-saved');
  });

  await section(P('masked'), async () => {
    await page.tap('#vbPHide');
    await openEditor();
    check(P('editor shows the meaning while 遮释义 is on'), (await editorState(page)).meaning === 'n. 意外发现好东西的运气');
    await page.fill('#edMeaning', 'n. 好运');
    await clearToasts(page);
    await page.tap('#edOk');
    await toastSeen(page, '已保存「serendipity」');
    await waitHidden(page, '#dlgEdit');
    const i = await cardInfo(page, id);
    check(P('after saving, 遮释义 still masks every meaning'), i.masked && i.meaning === 'n. 好运' && await page.$$eval('#vbGrid .vb-meaning', els => els.every(e => e.classList.contains('is-masked'))), i);
    await page.tap('#vbPHide');
  });

  await section(P('keyboard-height viewport'), async () => {
    await page.setViewportSize({ width: vw, height: KB_HEIGHT });
    await page.waitForTimeout(200);
    await clearToasts(page);
    await cardById(page, id).scrollIntoViewIfNeeded();
    await openEditor();
    const b = await boxes(page, ['edTitle', 'edWord', 'edMeaning', 'edOk']);
    check(P(`keyboard ${KB_HEIGHT}px: title, both fields and 保存 visible`), b.every(([, t, bt]) => t >= 0 && bt <= KB_HEIGHT), b);
    await shot(page, 'phone-edit-kb');
    await page.tap('#dlgEdit .ui-dialog__close');
    await waitHidden(page, '#dlgEdit');
    await page.setViewportSize({ width: vw, height: vh });
  });

  await section(P('reload'), async () => {
    // 关面板时页面自己退掉那条历史记录（history.back），等它退完再刷新，不然刷新会被打断
    await page.waitForTimeout(400);
    await page.reload();
    await page.waitForSelector('#vbContent:not([hidden])');
    const i = await cardInfo(page, id);
    check(P('edit survives a reload'), i.word === 'serendipity' && i.meaning === 'n. 好运', i);
  });
  check(P('no page errors'), page.errors.length === 0, page.errors);
  await ctx.close();

  ({ ctx, page } = await newPage(browser, { width: vw, height: vh, mobile: true, isMobile: dev.isMobile, theme: 'dark', prefs: EDIT_PREFS() }));
  await open(page);
  await section(P('dark'), async () => {
    id = await page.$eval('#vbGrid .vb-card', e => e.dataset.id);
    await openEditor();
    const bgs = await page.evaluate(() => ['#dlgEdit .ui-dialog', '#edWord', '#edMeaning'].map(s => getComputedStyle(document.querySelector(s)).backgroundColor));
    check(P('dark: editor sheet and fields are dark'), bgs.every(isDark), bgs);
    await shot(page, 'phone-dark-edit');
    await page.tap('#dlgEdit .ui-dialog__close');
  });
  check(P('no page errors (dark)'), page.errors.length === 0, page.errors);
  await ctx.close();
}

(async () => {
  const engines = process.argv.slice(2).length ? process.argv.slice(2) : ['chromium', 'webkit'];
  resetData();
  await login();
  console.log(`沙盒 ${BASE} · 输出 ${OUT_ROOT}${OFFLINE ? ' · 离线（有道换成提示音）' : ''}`);
  for (const name of engines) {
    engine = name;
    const browser = await pw[name].launch();
    // 每一组单独兜底：一组崩了不影响后面几组
    for (const [key, suite] of [['desktop', desktopSuite], ['prefs', prefsAndThemes], ['missing', missingCategoryFile], ['phone', phoneSuite], ['edit', editSuite]]) {
      if (!SUITES.includes(key)) continue;
      try {
        await suite(browser);
      } catch (e) {
        check(key + ' suite crashed', false, e.stack.split('\n').slice(0, 4).join(' | '));
      }
    }
    await browser.close();
  }
  resetData();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  fs.writeFileSync(path.join(OUT_ROOT, 'e2e-results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
})();

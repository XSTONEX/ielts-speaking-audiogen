// 单词本（/vocabulary）浏览器端到端测试：在沙盒里用编造的数据把每个功能点一遍。
// 用法见同目录 README.md。配置都从环境变量来：
//   VOCAB_E2E_SANDBOX   沙盒目录（必填，make_sandbox.sh 建的那个；测试会把 vocabulary_book 重置成 vocabulary_book.pristine）
//   VOCAB_E2E_BASE      沙盒服务地址，默认 http://localhost:5174
//   VOCAB_E2E_OUT       截图、下载文件放哪，默认系统临时目录下的 vocab-e2e（别放进仓库）
//   VOCAB_E2E_USER / VOCAB_E2E_PASSWORD  沙盒里的假账号，默认 demo / not-a-real-password（make_fake_data.py 写的）
//   VOCAB_E2E_OFFLINE=1 不连有道：有道发音请求换成本地生成的一小段提示音，其余检查照跑
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
  const o = Object.assign({ width: 1280, height: 900, theme: 'light', prefs: null, mobile: false }, opts || {});
  const ctxOpts = { viewport: { width: o.width, height: o.height }, acceptDownloads: true, colorScheme: o.theme };
  if (o.mobile) Object.assign(ctxOpts, { isMobile: true, hasTouch: true });
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

  // phone 390, light + dark
  for (const theme of ['light', 'dark']) {
    resetData();
    ({ ctx, page } = await newPage(browser, { width: 390, height: 844, mobile: true, theme, prefs: { category: 'listening', subcategory: SUB.unfamiliar, sortType: 'newest', meaningsVisible: true } }));
    await open(page);
    check(`phone ${theme}: no horizontal overflow`, (await overflow(page)) <= 0, await overflow(page));
    check(`phone ${theme}: 2-column grid`, (await page.$eval('#vbGrid', e => getComputedStyle(e).gridTemplateColumns.split(' ').length)) === 2);
    check(`phone ${theme}: sub list collapsed`, !(await page.isVisible('#vbSubs')));
    check(`phone ${theme}: trash always visible`, (await page.$eval('.vb-act--del', e => getComputedStyle(e).opacity)) === '1');
    await shot(page, `${theme}-390-main`);
    await shot(page, `${theme}-390-main-full`, true);
    await page.click('#vbSubToggle');
    check(`phone ${theme}: toggle opens subs`, await page.isVisible('#vbSubs') && (await page.$eval('#vbSubToggle', e => e.getAttribute('aria-expanded'))) === 'true');
    await shot(page, `${theme}-390-subs-open`);
    await page.tap(`#vbSubs [data-sub="${SUB.part3}"]`);
    check(`phone ${theme}: picking a sub closes list`, !(await page.isVisible('#vbSubs')) && (await text(page, '#vbSubName')) === 'Part 3 学术场景');
    await page.tap('#vbCats [data-cat="reading"]');
    check(`phone ${theme}: category grid works`, (await text(page, '#vbSubName')) === 'Chapter1 自然地理');
    await page.tap('#vbHide');
    const maskedBefore = await page.$$eval('#vbGrid .vb-meaning.is-masked', els => els.length);
    const firstMeaning = page.locator('#vbGrid .vb-meaning').first();
    page.youdao = [];
    await page.evaluate(() => { window.__clicks = []; document.addEventListener('click', e => window.__clicks.push((e.target.id || e.target.className) + '|' + e.pointerType + '|' + matchMedia('(hover: none)').matches), true); });
    await firstMeaning.tap();
    await page.waitForTimeout(200);
    check(`phone ${theme}: tap masked meaning peeks`, await firstMeaning.evaluate(e => e.classList.contains('is-peek')) && page.youdao.length === 0, { maskedBefore, cls: await firstMeaning.getAttribute('class'), youdao: page.youdao, hidePressed: await page.$eval('#vbHide', e => e.getAttribute('aria-pressed')), clicks: await page.evaluate(() => window.__clicks) });
    page.youdao = [];
    await page.locator('#vbGrid .vb-word').first().tap();
    await page.waitForTimeout(200);
    check(`phone ${theme}: tap word plays`, page.youdao.length >= 1 && new Set(page.youdao).size === 1, page.youdao);
    await shot(page, `${theme}-390-hidden-peek`);
    await page.tap('#vbHide');
    await page.fill('#vbWord', 'thoroughfare');
    await page.fill('#vbMeaning', 'n. 通道');
    await page.tap('#vbAddBtn');
    check(`phone ${theme}: add works`, await toastSeen(page, '已添加「thoroughfare」'));
    await page.tap('#vbChallengeBtn');
    await page.waitForSelector('#dlgChallenge:not([hidden])');
    check(`phone ${theme}: dialog fits`, (await page.$eval('#dlgChallenge .ui-dialog', e => e.getBoundingClientRect().width)) <= 390 - 24 && (await overflow(page)) <= 0);
    await shot(page, `${theme}-390-challenge-setup`);
    await page.tap('#chOk');
    await page.waitForSelector('#dlgQuiz:not([hidden])');
    await page.waitForTimeout(400);
    check(`phone ${theme}: options single column`, (await page.$eval('#qOptions', e => getComputedStyle(e).gridTemplateColumns.split(' ').length)) === 1);
    await shot(page, `${theme}-390-challenge-question`);
    await page.locator('#qOptions .vb-option').first().tap();
    await page.waitForTimeout(300);
    await shot(page, `${theme}-390-challenge-answered`);
    await page.tap('#dlgQuiz .ui-dialog__close');
    await page.tap('#cfOk');
    await page.tap('#vbImportBtn');
    await shot(page, `${theme}-390-import`);
    await page.tap('#dlgImport [data-close]');
    await page.tap('#vbExportBtn');
    check(`phone ${theme}: export dialog no overflow`, (await overflow(page)) <= 0);
    await shot(page, `${theme}-390-export`);
    await page.tap('#dlgExport [data-close]');
    check(`phone ${theme}: no page errors`, page.errors.length === 0, page.errors);
    await ctx.close();
  }
}

(async () => {
  const engines = process.argv.slice(2).length ? process.argv.slice(2) : ['chromium', 'webkit'];
  resetData();
  await login();
  console.log(`沙盒 ${BASE} · 输出 ${OUT_ROOT}${OFFLINE ? ' · 离线（有道换成提示音）' : ''}`);
  for (const name of engines) {
    engine = name;
    const browser = await pw[name].launch();
    try {
      await desktopSuite(browser);
      await prefsAndThemes(browser);
      await missingCategoryFile(browser);
    } catch (e) {
      check('suite crashed', false, e.stack.split('\n').slice(0, 4).join(' | '));
    }
    await browser.close();
  }
  resetData();
  const failed = results.filter(r => !r.ok);
  console.log(`\n${results.length - failed.length}/${results.length} passed`);
  fs.writeFileSync(path.join(OUT_ROOT, 'e2e-results.json'), JSON.stringify(results, null, 2));
  process.exit(failed.length ? 1 : 0);
})();

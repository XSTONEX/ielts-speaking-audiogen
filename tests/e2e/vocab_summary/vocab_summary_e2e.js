// 「词汇汇总」（/vocab_summary）和「登录」（/login）的浏览器测试，Chromium 和 WebKit 各跑一遍。
// 数据是 make_fake_data.py 编的，服务器跑在 sandbox.sh 建的沙盒里（见 README.md）。
//
//   node vocab_summary_e2e.js                 两个页面、两个浏览器
//   node vocab_summary_e2e.js summary webkit  只跑词汇汇总、只用 WebKit
//
// 环境变量：E2E_BASE_URL（默认 http://127.0.0.1:5073）、E2E_TOKEN_FILE（沙盒里的 e2e_token.txt）、
// PLAYWRIGHT_CORE（playwright-core 的路径）、OUT_DIR（截图和下载放哪，默认系统临时目录）
'use strict';
const fs = require('fs');
const os = require('os');
const path = require('path');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const BASE = (process.env.E2E_BASE_URL || 'http://127.0.0.1:5073').replace(/\/$/, '');
const TOKEN_FILE = process.env.E2E_TOKEN_FILE;
if (!TOKEN_FILE) { console.error('先设置 E2E_TOKEN_FILE（沙盒目录里的 e2e_token.txt）'); process.exit(2); }
const SANDBOX = path.dirname(path.resolve(TOKEN_FILE));
const REPO = path.resolve(__dirname, '..', '..', '..');
const PYTHON = process.env.PYTHON || path.join(REPO, '.venv', 'bin', 'python');
let TOKEN = '';

// 每个浏览器开跑前把沙盒数据重置一遍（挑战记录、错词本会被上一轮改掉），凭证也会换新的
function resetData() {
  const r = require('child_process').spawnSync(PYTHON, [path.join(__dirname, 'make_fake_data.py'), SANDBOX], { encoding: 'utf8' });
  if (r.status !== 0) throw new Error('重置沙盒数据失败：' + (r.stderr || r.stdout));
  TOKEN = fs.readFileSync(TOKEN_FILE, 'utf8').trim();
}
const OUT = process.env.OUT_DIR || path.join(os.tmpdir(), 'vocab_summary_e2e');
fs.mkdirSync(OUT, { recursive: true });

// 和 make_fake_data.py 保持一致
const DATA = {
  user: 'reader02',
  password: 'tide pool 7 ',
  LIGHTHOUSE: '20261020090000-The-Lighthouse-Keepers-Log',
  FERRY: '20261019090000-Night-Ferry-Timetable',
  COLD_CHAIN: '20261018090000-The-Cold-Chain',
  RADIO: '20261015090000-Campus-Radio-Interview',
  lighthouseTitle: 'The Lighthouse Keeper’s Log',
};

let passed = 0;
let failed = 0;
function check(name, ok, detail) {
  if (ok) { passed++; return; }
  failed++;
  console.log('FAIL', name, detail === undefined ? '' : String(typeof detail === 'string' ? detail : JSON.stringify(detail)).slice(0, 300));
}
const sleep = ms => new Promise(r => setTimeout(r, ms));
const near = (a, b, tol = 1.5) => Math.abs(a - b) <= tol;

async function openPage(ctx, errors, { token = true } = {}) {
  const p = await ctx.newPage();
  p.on('pageerror', e => errors.push(new URL(p.url()).pathname + ': ' + e.message));
  p.on('dialog', d => d.accept());
  await p.goto(BASE + '/static/plain.css', { waitUntil: 'commit' });
  await p.evaluate(t => { if (t) localStorage.setItem('authToken', t); else localStorage.clear(); }, token ? TOKEN : '');
  return p;
}
async function go(p, url) {
  await p.goto(BASE + url, { waitUntil: 'commit' });
}
const texts = (p, sel) => p.$$eval(sel, els => els.map(e => e.textContent.trim()));
const visible = (p, sel) => p.locator(sel).isVisible();
async function rect(p, sel, i = 0) {
  return p.$$eval(sel, (els, i) => { const r = els[i].getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height, b: r.bottom }; }, i);
}
async function toastSeen(p, text, timeout = 6000) {
  try {
    await p.waitForFunction(t => [...document.querySelectorAll('#toasts .ui-toast')].some(e => e.textContent.includes(t)), text, { timeout });
    return true;
  } catch (e) { return false; }
}
async function download(p, action) {
  const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 8000 }), action()]);
  const file = path.join(OUT, `${Date.now()}-${dl.suggestedFilename()}`);
  await dl.saveAs(file);
  return { name: dl.suggestedFilename(), text: fs.readFileSync(file, 'utf8') };
}
async function api(p, url, init) {
  return p.evaluate(async ([u, i]) => (await fetch(u, i)).json(), [url, init || {}]);
}

// ==================== 词汇汇总 ====================
async function summary(eng, browser) {
  const tag = `[${eng} 词汇汇总]`;
  const errors = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
  const audio = [];
  await ctx.route('https://dict.youdao.com/**', r => { audio.push(r.request().url()); r.abort(); });
  // 记下每个页面一打开时 sessionStorage 里要跳的高亮（精读页加载完会删掉，得在它之前读）
  await ctx.addInitScript(() => { try { window.__jumpAtStart = sessionStorage.getItem('jumpToHighlight'); } catch (e) {} });
  const p = await openPage(ctx, errors);
  let articleFetches = 0;
  p.on('request', r => {
    if (r.url().includes('/vocab_audio/')) audio.push(r.url());
    if (r.url().includes('/intensive_article/')) articleFetches++;
  });

  await go(p, '/vocab_summary');
  await p.waitForSelector('.vs-word', { timeout: 15000 });
  check(`${tag} 标签页标题`, (await p.title()) === '词汇汇总 · IELTS Lab', await p.title());
  check(`${tag} 只有一条全站导航`, (await p.locator('.app-shell-nav').count()) === 1);

  // ---- 左边文章 ----
  const segN = await Promise.all(['Reading', 'Listening', 'Writing'].map(c => p.textContent(`#tab-${c} .vs-seg__n`)));
  check(`${tag} 分类计数只算有词的文章`, segN.join('/') === '3/1/0', segN);
  check(`${tag} 默认在 Reading`, await p.$eval('#tab-Reading', e => e.classList.contains('active')));
  const titles = await texts(p, '#articleList .vs-art__title');
  check(`${tag} 只列出高亮过词的文章，按时间倒序`, titles.join('|') === [DATA.lighthouseTitle, 'Night Ferry Timetable', 'The Cold Chain'].join('|'), titles);
  check(`${tag} 底部说明另有几篇没词`, (await p.textContent('#railNote')).includes('另有 3 篇'), await p.textContent('#railNote'));
  check(`${tag} 第一篇自动选中`, (await texts(p, '#articleList .vs-art.active .vs-art__title'))[0] === DATA.lighthouseTitle);
  check(`${tag} 文章卡片带词数和日期`, (await texts(p, '#articleList .vs-art__meta'))[0] === '9 个词 · 10-20');

  // ---- 右边的词 ----
  check(`${tag} 右边标题`, (await p.textContent('#vocabTitle')) === DATA.lighthouseTitle);
  check(`${tag} 词数`, (await p.textContent('#vocabSubtitle')) === '9 个词');
  check(`${tag} 9 张词卡`, (await p.locator('.vs-word').count()) === 9);
  const words = await texts(p, '.vs-word__en');
  check(`${tag} 按原文顺序排`, words.slice(0, 3).join('|') === 'treacherous|beacon|solitary', words);
  check(`${tag} 单词里的 <i> 原样显示，不当成 HTML`, words.includes('<i>tide</i>') && (await p.locator('.vs-word i, .vs-word b').count()) === 0, words);
  const meanings = await texts(p, '.vs-word__zh');
  check(`${tag} 释义里的 <b> 和双引号原样显示`, meanings.includes('写成 <b>粗体</b> 的 "潮水"'), meanings);
  check(`${tag} 打开原文链接`, (await p.getAttribute('#openArticle', 'href')) === '/intensive#article-' + DATA.LIGHTHOUSE);

  // ---- 对齐：左边分类条和右边标题行同一条线，第一篇文章和第一行词卡同一条线，每行 3 张一样高 ----
  const seg = await rect(p, '.vs-seg');
  const head = await rect(p, '.vs-pane__head');
  const art0 = await rect(p, '#articleList .vs-art');
  const cards = await p.$$eval('.vs-word', els => els.map(e => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, h: r.height }; }));
  check(`${tag} 分类条和标题行顶边对齐`, near(seg.y, head.y) && near(seg.h, head.h), { seg, head });
  check(`${tag} 第一篇文章和第一行词卡顶边对齐`, near(art0.y, cards[0].y), { art0, card: cards[0] });
  check(`${tag} 一行 3 张`, near(cards[0].y, cards[2].y) && !near(cards[0].x, cards[1].x) && near(cards[3].x, cards[0].x) && cards[3].y > cards[0].y, cards.slice(0, 4));
  check(`${tag} 同一行的卡片一样高`, near(cards[0].h, cards[1].h) && near(cards[1].h, cards[2].h), cards.slice(0, 3));
  await p.screenshot({ path: path.join(OUT, `${eng}-summary.png`) });

  // ---- 搜索 ----
  await p.fill('#vocabSearch', '大风');
  check(`${tag} 搜释义`, (await texts(p, '.vs-word__en')).join() === 'gale');
  await p.fill('#vocabSearch', 'zzz');
  check(`${tag} 搜不到有提示`, (await p.textContent('#vocabList')).includes('没找到「zzz」'));
  await p.fill('#vocabSearch', '');
  check(`${tag} 清空搜索回到 9 个`, (await p.locator('.vs-word').count()) === 9);

  // ---- 发音：先放精读划词时生成的，再试有道，都不行才提示；不再请求付费 TTS ----
  audio.length = 0;
  await p.locator('.vs-word', { hasText: 'treacherous' }).click();
  check(`${tag} 两个来源都不行时提示`, await toastSeen(p, '没取到「treacherous」的发音'));
  const sources = [...new Set(audio)];   // WebKit 会对同一个音频地址发好几次分段请求
  check(`${tag} 先取精读里存好的发音`, (sources[0] || '').includes(`/vocab_audio/${DATA.LIGHTHOUSE}/treacherous`), sources);
  check(`${tag} 再取有道的`, sources.length === 2 && sources[1].startsWith('https://dict.youdao.com/dictvoice?audio=treacherous'), sources);
  audio.length = 0;
  await p.locator('.vs-word', { hasText: "one's post" }).locator('.vs-play').click();
  check(`${tag} 带撇号的词也能点发音`, await toastSeen(p, "没取到「one's post」的发音"));
  check(`${tag} 带撇号的词请求的地址对`, decodeURIComponent(audio[0] || '').includes("/one's post"), audio);

  // ---- 连点两篇：只认最后一篇 ----
  await p.route(`**/intensive_article/${DATA.FERRY}`, async r => { await sleep(1200); r.continue(); });
  await p.locator('#articleList .vs-art', { hasText: 'Night Ferry' }).click();
  await p.locator('#articleList .vs-art', { hasText: 'The Cold Chain' }).click();
  await sleep(1800);
  check(`${tag} 连点两篇后标题是后一篇`, (await p.textContent('#vocabTitle')) === 'The Cold Chain');
  check(`${tag} 连点两篇后词也是后一篇的`, (await texts(p, '.vs-word__en'))[0] === 'Perishable' && (await p.locator('.vs-word').count()) === 5, await texts(p, '.vs-word__en'));
  await p.unroute(`**/intensive_article/${DATA.FERRY}`);
  await p.locator('#articleList .vs-art', { hasText: 'Night Ferry' }).click();
  await p.waitForFunction(() => document.querySelectorAll('.vs-word').length === 6);
  check(`${tag} 没写释义的词有说明`, (await texts(p, '.vs-word__zh.is-empty')).join() === '（没写释义）');
  await p.locator('.vs-word', { hasText: 'berth' }).click();   // 这篇没有存好的发音：以前请求一次就会留下一个空文件夹
  check(`${tag} 没存发音的文章也只是提示`, await toastSeen(p, '没取到「berth」的发音'));

  // ---- 分类 ----
  await p.click('#tab-Listening');
  await p.waitForFunction(() => document.querySelectorAll('.vs-word').length === 4);
  check(`${tag} 切到 Listening 自动打开那篇`, (await p.textContent('#vocabTitle')) === 'Campus Radio Interview');
  await p.click('#tab-Writing');
  check(`${tag} 没词的分类给出空状态`, (await p.textContent('#vocabList')).includes('Writing 里还没有划过词的文章'));
  check(`${tag} 空状态能去精读`, (await p.locator('#vocabList a[href="/intensive"]').count()) === 1);
  check(`${tag} 空分类不显示打开原文`, !(await visible(p, '#openArticle')));
  await p.click('#tab-Listening');
  await p.waitForFunction(() => document.querySelectorAll('.vs-word').length === 4);
  await p.reload({ waitUntil: 'commit' });
  await p.waitForSelector('.vs-word');
  check(`${tag} 刷新后记得分类和文章`, (await p.$eval('#tab-Listening', e => e.classList.contains('active'))) && (await p.textContent('#vocabTitle')) === 'Campus Radio Interview');
  await p.click('#tab-Reading');
  await p.waitForFunction(() => document.querySelectorAll('.vs-word').length === 9);

  // ---- 跳到原文：新标签页能拿到要滚到的高亮，这边过一会儿删掉 ----
  const hid = await p.locator('.vs-word', { hasText: 'gale' }).getAttribute('data-hid');
  const [popup] = await Promise.all([ctx.waitForEvent('page'), p.locator('.vs-word', { hasText: 'gale' }).locator('.vs-jump').click()]);
  await popup.waitForLoadState('domcontentloaded').catch(() => {});
  check(`${tag} 新标签页打开这篇`, popup.url().endsWith('/intensive#article-' + DATA.LIGHTHOUSE), popup.url());
  check(`${tag} 新标签页拿到要滚到的高亮`, (await popup.evaluate(() => window.__jumpAtStart)) === hid, hid);
  await popup.close();
  await sleep(1800);
  check(`${tag} 本页的跳转标记已删掉`, (await p.evaluate(() => sessionStorage.getItem('jumpToHighlight'))) === null);

  // ---- 导出 ----
  await p.click('#exportBtn');
  check(`${tag} 导出菜单打开`, await visible(p, '#exportMenu'));
  check(`${tag} 当前文章的说明`, (await p.textContent('#exportCurrentDesc')).includes('9 个词'));
  let file = await download(p, () => p.click('[data-export="current"]'));
  const lines = file.text.replace(/\n$/, '').split('\n');
  check(`${tag} 导出文件名`, file.name === `${DATA.lighthouseTitle}_词汇.csv`, file.name);
  check(`${tag} 导出带 BOM 和表头`, lines[0] === '﻿词汇,释义', lines[0]);
  check(`${tag} 导出 9 行`, lines.length === 10, lines.length);
  check(`${tag} 导出里双引号转义`, lines.includes('"<i>tide</i>","写成 <b>粗体</b> 的 ""潮水"""'), lines);
  check(`${tag} 导出后提示`, await toastSeen(p, '已导出 9 个词'));
  check(`${tag} 点完菜单收起`, !(await visible(p, '#exportMenu')));
  await p.click('#exportBtn');
  file = await download(p, () => p.click('[data-export="category"]'));
  check(`${tag} 导出整个分类（去重后 20 个）`, file.name === 'Reading_分类词汇.csv' && file.text.trim().split('\n').length === 21, [file.name, file.text.trim().split('\n').length]);
  await p.click('#exportBtn');
  await p.keyboard.press('Escape');
  check(`${tag} Esc 收起导出菜单`, !(await visible(p, '#exportMenu')));

  // ---- 开始挑战：选文章 ----
  articleFetches = 0;
  await p.click('#challengeBtn');
  check(`${tag} 打开开始挑战`, await visible(p, '#challengeSetupModal'));
  check(`${tag} 只列出有词的 4 篇`, (await p.locator('#filteredArticles .vs-pick__row').count()) === 4);
  const chips = await texts(p, '#setupFilters .ui-chip');
  check(`${tag} 筛选按钮带篇数`, chips.join('|') === '全部 4|Reading 3|Listening 1|Writing 0', chips);
  check(`${tag} 没文章的分类按钮不能点`, await p.locator('#setupFilters .ui-chip', { hasText: 'Writing' }).isDisabled());
  check(`${tag} 没选文章不能开始`, await p.locator('#startChallengeBtn').isDisabled());
  await p.check('#selectAllArticles');
  check(`${tag} 全选`, (await p.locator('#filteredArticles input:checked').count()) === 4);
  check(`${tag} 已选篇数和词数`, (await p.textContent('#selectedArticlesCount')) === '4' && (await p.textContent('#availableVocabCount')) === '24');
  check(`${tag} 选文章不再整篇下载每篇文章`, articleFetches === 0, articleFetches);
  await p.fill('#challengeWordCount', '5');
  check(`${tag} 题数输入框带动滑块`, (await p.inputValue('#wordCountSlider')) === '5' && (await p.textContent('#questionCount')) === '5');
  await p.$eval('#wordCountSlider', e => { e.value = '30'; e.dispatchEvent(new Event('input', { bubbles: true })); });
  check(`${tag} 滑块带动输入框`, (await p.inputValue('#challengeWordCount')) === '30' && (await p.textContent('#questionCount')) === '24');
  await p.fill('#challengeWordCount', '5');
  await p.locator('#setupFilters .ui-chip', { hasText: 'Listening' }).click();
  check(`${tag} 按分类筛`, (await p.locator('#filteredArticles .vs-pick__row').count()) === 1 && (await p.textContent('#selectAllLabel')) === '全选这 1 篇');
  await p.mouse.click(8, 450);
  check(`${tag} 点弹窗外面关掉`, !(await visible(p, '#challengeSetupModal')));
  await p.click('#challengeBtn');
  check(`${tag} 再打开还记得选过的文章`, (await p.locator('#filteredArticles input:checked').count()) === 4);

  // ---- 答题 ----
  const [resp] = await Promise.all([p.waitForResponse(r => r.url().endsWith('/api/vocab_summary_challenge')), p.click('#startChallengeBtn')]);
  const vocab = (await resp.json()).challenge.vocabulary;
  await p.waitForSelector('#challengeGameModal:not([hidden])');
  check(`${tag} 出了 5 题`, vocab.length === 5, vocab.length);
  check(`${tag} 开始后关掉选文章`, !(await visible(p, '#challengeSetupModal')));
  const question = async () => {
    const hint = await p.textContent('#challengeHint');
    const q = (await p.textContent('#challengeQuestion')).trim();
    const v = hint.includes('这个词的意思') ? vocab.find(x => x.word === q) : vocab.find(x => x.meaning === q);
    return { v, correct: hint.includes('这个词的意思') ? v.meaning : v.word };
  };
  const options = () => p.$$eval('#challengeOptions .vs-opt', els => els.map(e => e.dataset.answer));
  const choose = async answer => { const i = (await options()).indexOf(answer); await p.locator('#challengeOptions .vs-opt').nth(i).click(); };
  const waitQ = n => p.waitForFunction(n => document.getElementById('challengeProgress').textContent.startsWith(`第 ${n} /`), n, { timeout: 6000 });

  check(`${tag} 进度`, (await p.textContent('#challengeProgress')) === '第 1 / 5 题');
  const wrongBefore = Object.keys((await api(p, '/api/vocab_wrong_words')).wrong_words);
  let q = await question();
  const missed = [q.v];
  const wrongPick = (await options()).find(o => o !== q.correct);
  await choose(wrongPick);
  check(`${tag} 答错标出对错`, (await p.locator('.vs-opt.incorrect').count()) === 1 && (await p.locator('.vs-opt.correct').count()) === 1);
  check(`${tag} 答错的提示`, (await p.textContent('#challengeFeedback')).includes('答错了'));
  check(`${tag} 等下一题时不能跳过`, await p.locator('#skipBtn').isDisabled());
  await p.evaluate(() => skipQuestion(false));   // 以前这时点跳过会多记一题、跳掉下一题
  check(`${tag} 等下一题时跳过不生效`, (await p.evaluate(() => game.answers.length)) === 1);
  await waitQ(2);
  check(`${tag} 答错后进入第 2 题`, (await p.textContent('#challengeProgress')) === '第 2 / 5 题');
  q = await question();
  await choose(q.correct);
  check(`${tag} 答对计数`, (await p.textContent('#challengeCorrect')) === '1');
  await waitQ(3);
  missed.push((await question()).v);
  await p.click('#skipBtn');
  check(`${tag} 跳过也标出正确答案`, (await p.locator('.vs-opt.correct').count()) === 1 && (await p.textContent('#challengeFeedback')).includes('跳过了'));
  await waitQ(4);
  q = await question(); await choose(q.correct); await waitQ(5);
  q = await question(); await choose(q.correct);
  await p.waitForSelector('#challengeResultModal:not([hidden])', { timeout: 6000 });

  // ---- 结果 ----
  check(`${tag} 结果副标题有文章名（以前是空的）`, (await p.textContent('#resultSub')).includes(DATA.lighthouseTitle), await p.textContent('#resultSub'));
  const stats = await texts(p, '#resultSummary .vs-stat');
  check(`${tag} 答对 3 / 5`, stats.some(s => s.startsWith('3/ 5') && s.endsWith('答对')), stats);
  check(`${tag} 正确率 60%`, stats.some(s => s.startsWith('60%')), stats);
  check(`${tag} 列出答错和跳过的 2 个`, (await p.locator('#wrongWordsSection .vs-list__row').count()) === 2);
  check(`${tag} 跳过的单独标出`, (await texts(p, '#wrongWordsSection .vs-list__pick.is-skip')).join() === '跳过');
  check(`${tag} 复习按钮带个数`, (await p.textContent('#reviewWrongBtn')) === '复习这 2 个');
  await p.screenshot({ path: path.join(OUT, `${eng}-result.png`) });
  const records = await api(p, '/api/vocab_challenge_records');
  check(`${tag} 存到后端的记录带文章名`, records.records[0].article_titles.length === 4 && records.records[0].article_titles.includes(DATA.lighthouseTitle), records.records[0].article_titles);
  const wrongNow = await api(p, '/api/vocab_wrong_words');
  const wantKeys = new Set(wrongBefore.concat(missed.map(v => `${v.word}::${v.meaning}`)));
  check(`${tag} 答错和跳过的词进了错词本`, Object.keys(wrongNow.wrong_words).length === wantKeys.size && [...wantKeys].every(k => k in wrongNow.wrong_words), Object.keys(wrongNow.wrong_words));

  await p.click('#restartBtn');
  check(`${tag} 再来一次勾回上次的文章`, (await visible(p, '#challengeSetupModal')) && (await p.locator('#filteredArticles input:checked').count()) === 4);
  await p.locator('#challengeSetupModal [data-close]').last().click();

  // ---- 挑战记录 ----
  await p.click('#historyBtn');
  check(`${tag} 打开挑战记录`, await visible(p, '#challengeHistoryModal'));
  check(`${tag} 最近挑战计数`, (await p.textContent('#recentTab .vs-tabs__n')) === '2');
  const recTitles = await texts(p, '.vs-rec__title');
  check(`${tag} 新记录有文章名`, recTitles[0].includes(DATA.lighthouseTitle), recTitles);
  check(`${tag} 旧记录按文章 ID 补回文章名`, recTitles[1] === DATA.lighthouseTitle, recTitles);
  await p.locator('.vs-rec').nth(1).getByRole('button', { name: '详情' }).click();
  check(`${tag} 详情原地展开`, (await p.locator('.vs-rec').nth(1).locator('.vs-rec__detail').textContent()).includes('beacon'));
  await p.locator('.vs-rec').nth(0).getByRole('button', { name: /复习错词/ }).click();
  await p.waitForSelector('#challengeGameModal:not([hidden])');
  check(`${tag} 从记录复习错词`, (await p.textContent('#challengeGameTitle')) === '错词复习' && (await p.textContent('#challengeProgress')) === '第 1 / 2 题');
  check(`${tag} 复习时记录弹窗关掉`, !(await visible(p, '#challengeHistoryModal')));
  await p.keyboard.press('Escape');
  check(`${tag} 答题时 Esc 不关弹窗`, await visible(p, '#challengeGameModal'));
  await p.locator('#challengeOptions .vs-opt').first().click();
  await p.click('#quitBtn');   // 答完一题、等下一题时退出：以前会报错
  check(`${tag} 退出挑战`, !(await visible(p, '#challengeGameModal')));
  await sleep(2600);

  await p.click('#historyBtn');
  await p.click('#wrongTab');
  check(`${tag} 错词本计数`, (await p.textContent('#wrongTab .vs-tabs__n')) === String(Object.keys((await api(p, '/api/vocab_wrong_words')).wrong_words).length));
  const ww = await texts(p, '.vs-ww__word');
  const times = (await texts(p, '.vs-ww__times')).map(t => parseInt(t.replace(/\D/g, ''), 10));
  check(`${tag} 错词按次数排`, times.every((t, i) => !i || times[i - 1] >= t) && ww.includes("one's post"), [ww, times]);
  check(`${tag} 错词里的 HTML 原样显示，不执行`, ww.includes('<img src=x onerror="window.__xss=1">') && (await p.locator('#challengeHistoryModal img').count()) === 0 && (await p.evaluate(() => window.__xss)) === undefined);
  // 编的错词：单词带撇号，释义里撇号、双引号都有（随机出的题也可能答错文章里的 one's post，所以按释义找这一条）
  const quoted = 'it\'s "one\'s" own post';
  await p.locator('.vs-ww', { hasText: quoted }).getByRole('button', { name: '记住了' }).click();
  check(`${tag} 带撇号的词能移出错词本`, (await p.locator('.vs-ww', { hasText: quoted }).count()) === 0 && await toastSeen(p, "已把「one's post」移出错词本"));
  await sleep(500);
  const wrongAfter = await api(p, '/api/vocab_wrong_words');
  check(`${tag} 后端也删掉了`, !Object.values(wrongAfter.wrong_words).some(w => w.meaning === quoted));
  await p.click('#statsTab');
  check(`${tag} 统计四个数`, (await p.locator('#historyContent .vs-stat').count()) === 4);
  check(`${tag} 每天的记录`, (await p.locator('#historyContent .vs-table__row:not(.is-head)').count()) >= 2);
  file = await download(p, () => p.click('#exportHistoryBtn'));
  check(`${tag} 导出记录带文章名`, file.text.startsWith('﻿挑战时间,文章') && file.text.split('\n').filter(l => l.includes(DATA.lighthouseTitle)).length >= 2, file.text.slice(0, 200));
  await p.keyboard.press('Escape');
  check(`${tag} Esc 关掉挑战记录`, !(await visible(p, '#challengeHistoryModal')));

  // ---- 服务器那边：没调 TTS，没留空文件夹 ----
  const log = fs.existsSync(path.join(SANDBOX, 'server.log')) ? fs.readFileSync(path.join(SANDBOX, 'server.log'), 'utf8') : '';
  check(`${tag} 服务器没去生成发音`, !/TTS API error|Generated audio|音频生成/.test(log));
  const audioDirs = fs.readdirSync(path.join(SANDBOX, 'vocab_audio')).sort();
  check(`${tag} 没留下挑战音频文件夹和空文件夹`, audioDirs.join() === DATA.LIGHTHOUSE, audioDirs);

  // ---- 暗色 ----
  await p.emulateMedia({ colorScheme: 'dark' });
  await p.reload({ waitUntil: 'commit' });
  await p.waitForSelector('.vs-word');
  check(`${tag} 暗色词卡底色`, (await p.$eval('.vs-word', e => getComputedStyle(e).backgroundColor)) === 'rgb(30, 30, 30)');
  check(`${tag} 暗色选中文章`, (await p.$eval('.vs-art.active .vs-art__title', e => getComputedStyle(e).color)) === 'rgb(138, 176, 230)');
  await p.screenshot({ path: path.join(OUT, `${eng}-summary-dark.png`) });

  check(`${tag} 没有页面报错`, errors.length === 0, errors);
  await ctx.close();

  // ---- 手机 ----
  const mctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
  await mctx.route('https://dict.youdao.com/**', r => r.abort());
  const merr = [];
  const m = await openPage(mctx, merr);
  await go(m, '/vocab_summary');
  await m.waitForSelector('.vs-word');
  check(`${tag} 手机不横向溢出`, await m.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  const mcards = await m.$$eval('.vs-word', els => els.slice(0, 2).map(e => e.getBoundingClientRect().x));
  check(`${tag} 手机一行一张`, near(mcards[0], mcards[1]), mcards);
  await m.click('#challengeBtn');
  const dlg = await rect(m, '#challengeSetupModal .vs-dlg');
  check(`${tag} 手机弹窗不出屏`, dlg.x >= 0 && dlg.x + dlg.w <= 390, dlg);
  await m.screenshot({ path: path.join(OUT, `${eng}-summary-phone.png`) });
  check(`${tag} 手机没有页面报错`, merr.length === 0, merr);
  await mctx.close();
}

// ==================== 登录 ====================
async function login(eng, browser) {
  const tag = `[${eng} 登录]`;
  const errors = [];
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p = await openPage(ctx, errors, { token: false });
  let loginPosts = 0;
  p.on('request', r => { if (r.url().endsWith('/user_login') && r.method() === 'POST') loginPosts++; });
  const fillIn = async (password) => {
    await p.waitForSelector('#loginForm');
    await p.fill('#username', DATA.user);
    await p.fill('#password', password);
  };
  const logout = () => p.evaluate(() => localStorage.clear());

  await go(p, '/login');
  await p.waitForSelector('#loginForm');
  check(`${tag} 标签页标题`, (await p.title()) === '登录 · IELTS Lab', await p.title());
  await sleep(600);
  check(`${tag} 登录页没有导航栏`, (await p.locator('.app-shell-nav').count()) === 0);
  check(`${tag} 光标在用户名`, await p.evaluate(() => document.activeElement && document.activeElement.id === 'username'));
  await p.screenshot({ path: path.join(OUT, `${eng}-login.png`) });

  await p.click('#loginBtn');
  check(`${tag} 空着提交有提示`, (await p.textContent('#errorMessage')).includes('请输入用户名'));
  await fillIn('wrong-pass');
  await p.click('#loginBtn');
  await p.waitForSelector('#errorMessage:not([hidden])');
  await p.waitForFunction(() => document.getElementById('errorMessage').textContent.includes('不对'));
  check(`${tag} 密码错的提示`, (await p.textContent('#errorMessage')) === '用户名或密码不对，再试一次。');
  check(`${tag} 失败后按钮恢复`, !(await p.locator('#loginBtn').isDisabled()) && (await p.textContent('#loginBtnText')) === '登录');

  await p.click('#togglePassword');
  check(`${tag} 显示密码`, (await p.getAttribute('#password', 'type')) === 'text' && (await p.getAttribute('#togglePassword', 'aria-label')) === '隐藏密码');
  await p.click('#togglePassword');
  check(`${tag} 再点隐藏密码`, (await p.getAttribute('#password', 'type')) === 'password');

  // 密码末尾的空格是密码的一部分（以前会被删掉，这样的密码登不上）；回车提交只发一次
  loginPosts = 0;
  await fillIn(DATA.password);
  await p.press('#password', 'Enter');
  await p.waitForURL(u => new URL(u).pathname === '/', { timeout: 8000 }).catch(() => {});
  check(`${tag} 末尾带空格的密码能登录，直接打开登录页时回首页`, new URL(p.url()).pathname === '/', p.url());
  check(`${tag} 回车只提交一次`, loginPosts === 1, loginPosts);
  check(`${tag} 存了凭证`, !!(await p.evaluate(() => localStorage.getItem('authToken'))));

  // 被要求登录后，登完回到原来那页
  await logout();
  await go(p, '/vocab_summary');
  await p.waitForURL('**/login', { timeout: 8000 }).catch(() => {});
  check(`${tag} 没登录打开词汇汇总会跳登录页`, new URL(p.url()).pathname === '/login', p.url());
  await fillIn(DATA.password);
  await p.click('#loginBtn');
  await p.waitForURL('**/vocab_summary', { timeout: 8000 }).catch(() => {});
  check(`${tag} 登录后回到词汇汇总`, new URL(p.url()).pathname === '/vocab_summary', p.url());

  for (const [next, want] of [['/intensive', '/intensive'], ['//example.com/x', '/'], ['https://example.com/x', '/'], ['/login', '/']]) {
    await logout();
    await go(p, '/login?next=' + encodeURIComponent(next));
    await fillIn(DATA.password);
    await p.click('#loginBtn');
    await p.waitForURL(u => new URL(u).pathname !== '/login', { timeout: 8000 }).catch(() => {});
    const u = new URL(p.url());
    check(`${tag} ?next=${next} 登录后到 ${want}`, u.origin === new URL(BASE).origin && u.pathname === want, p.url());
    // 等落地页加载完再走：页面还在加载时离开，WebKit 会把被打断的请求报成 "Load failed"
    await p.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  }

  // 已经登录的人打开登录页：直接放行
  await go(p, '/login?next=' + encodeURIComponent('/vocabulary'));
  await p.waitForURL('**/vocabulary', { timeout: 8000 }).catch(() => {});
  check(`${tag} 已登录打开登录页直接放行`, new URL(p.url()).pathname === '/vocabulary', p.url());

  // 暗色、矮屏幕
  await logout();
  await p.emulateMedia({ colorScheme: 'dark' });
  await go(p, '/login');
  await p.waitForSelector('#loginForm');
  check(`${tag} 暗色卡片底色`, (await p.$eval('.lg-card', e => getComputedStyle(e).backgroundColor)) === 'rgb(30, 30, 30)');
  await p.screenshot({ path: path.join(OUT, `${eng}-login-dark.png`) });
  await p.setViewportSize({ width: 360, height: 420 });
  await p.emulateMedia({ colorScheme: 'light' });
  await go(p, '/login');
  await p.waitForSelector('#loginForm');
  check(`${tag} 矮屏幕不横向溢出`, await p.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
  await p.locator('.lg-foot').scrollIntoViewIfNeeded();
  const foot = await rect(p, '.lg-foot');
  check(`${tag} 矮屏幕能滚到底部`, foot.b <= 420 + 1 && foot.y >= 0, foot);
  await p.screenshot({ path: path.join(OUT, `${eng}-login-short.png`) });

  check(`${tag} 没有页面报错`, errors.length === 0, errors);
  await ctx.close();
}

(async () => {
  const args = process.argv.slice(2);
  const suites = ['summary', 'login'].filter(s => !args.some(a => ['summary', 'login'].includes(a)) || args.includes(s));
  const engines = ['chromium', 'webkit'].filter(e => !args.some(a => ['chromium', 'webkit'].includes(a)) || args.includes(e));
  for (const eng of engines) {
    resetData();
    const browser = await pw[eng].launch();
    const before = { passed, failed };
    for (const s of suites) {
      try {
        await (s === 'summary' ? summary : login)(eng, browser);
      } catch (e) {
        failed++;
        console.log('FAIL', `[${eng} ${s}] 出错中断：`, e && e.stack ? e.stack.split('\n').slice(0, 4).join(' | ') : e);
      }
    }
    console.log(`${eng}: ${passed - before.passed} 项通过，${failed - before.failed} 项失败`);
    await browser.close();
  }
  console.log(`共 ${passed} 项通过，${failed} 项失败。截图和下载在 ${OUT}`);
  process.exit(failed ? 1 : 0);
})();

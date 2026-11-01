// 口语音频库（/speaking）和合集页（/combined）的手机端浏览器检查。配置全走环境变量，见 README.md。
//   SP_BASE_URL   沙盒服务地址，默认 http://127.0.0.1:5111
//   SP_SANDBOX    沙盒目录（读 e2e_token.txt）
//   SP_SHOTS      截图输出目录，不设就不截
//   PLAYWRIGHT_CORE  playwright-core 的路径
// 用法：node phone_e2e.js [webkit|chromium|all]   默认 all
// 数据是 make_fake_data.py 编的；脚本只会让「生成音频」失败一次（沙盒没有 API key），不删任何东西。
const fs = require('fs');
const path = require('path');
const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const BASE = (process.env.SP_BASE_URL || 'http://127.0.0.1:5111').replace(/\/$/, '');
const SANDBOX = process.env.SP_SANDBOX;
if (!SANDBOX) { console.log('CRASH 请设置 SP_SANDBOX=<沙盒目录>'); process.exit(1); }
const TOKEN = fs.readFileSync(path.join(SANDBOX, 'e2e_token.txt'), 'utf8').trim();
const SHOTS = process.env.SP_SHOTS || '';
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });

const HOMETOWN = 'P1 - Hometown';
const NEIGHBOUR = 'P2 - 一位乐于助人的邻居';
const READING = '朗读材料';
const APOSTROPHE = "P1 - Children's games";
const topicUrl = folder => '/speaking#folder=' + encodeURIComponent(folder);

let pass = 0, fail = 0;
let engine = '';
function ok(cond, name, detail) {
  if (cond) pass++; else fail++;
  console.log((cond ? 'PASS ' : 'FAIL ') + `[${engine}] ${name}` + (cond || detail === undefined ? '' : '  → ' + JSON.stringify(detail)));
  return !!cond;
}

const PROFILES = {
  webkit: { viewport: { width: 390, height: 844 }, hasTouch: true },
  chromium: { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true }
};

async function newPage(browser, opts = {}) {
  const ctxOpts = Object.assign({ deviceScaleFactor: 2, colorScheme: opts.dark ? 'dark' : 'light' }, PROFILES[engine]);
  if (opts.viewport) ctxOpts.viewport = opts.viewport;
  if (opts.desktop) { delete ctxOpts.isMobile; }
  const ctx = await browser.newContext(ctxOpts);
  await ctx.addInitScript(([t, dark]) => {
    if (location.protocol === 'about:') return;
    localStorage.setItem('authToken', t);
    localStorage.setItem('ui-theme', dark ? 'dark' : 'light');
  }, [TOKEN, !!opts.dark]);
  // 只放行沙盒自己的请求（谷歌字体等外部资源一律拦掉，测试完全离线）
  const origin = new URL(BASE).origin;
  await ctx.route('**/*', r => (new URL(r.request().url()).origin === origin ? r.continue() : r.abort()));
  const page = await ctx.newPage();
  page.setDefaultTimeout(10000);   // 找不到元素时早点失败（对着旧版跑时很多元素本来就不存在）
  page.errors = [];
  page.on('pageerror', e => page.errors.push(e.message));
  return { ctx, page };
}

async function open(page, url) {
  await page.goto(BASE + url);
  await page.waitForFunction(() => document.querySelector('#topicList .sp-tcard, #topicList .sp-state, #topicList .sp-list__row, .sp-clip, .folder-card'), null, { timeout: 15000 }).catch(() => {});
  await page.waitForTimeout(500);
}
async function shot(page, name) {
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `${engine}-${name}.png`) });
}
const rect = (page, sel) => page.evaluate(s => {
  const el = document.querySelector(s);
  if (!el) return null;
  const r = el.getBoundingClientRect();
  const cs = getComputedStyle(el);
  return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height, visible: r.width > 0 && cs.visibility !== 'hidden' && cs.display !== 'none' };
}, sel);
const noOverflow = page => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1);
async function tapTargets(page, selectors, min) {
  return page.evaluate(([sels, m]) => {
    const bad = [];
    sels.forEach(s => document.querySelectorAll(s).forEach(el => {
      const r = el.getBoundingClientRect();
      if (!r.width) return;
      if (r.width < m || r.height < m) bad.push(s + ' ' + Math.round(r.width) + '×' + Math.round(r.height));
    }));
    return bad;
  }, [selectors, min]);
}
// 屏幕上看得到的文字里最小的字号
const minFont = page => page.evaluate(() => {
  let min = 99, where = '';
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let n;
  while ((n = walker.nextNode())) {
    if (!n.textContent.trim()) continue;
    const el = n.parentElement;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === 'hidden' || el.closest('[hidden], .sp-sr, [aria-hidden="true"]')) continue;
    const size = parseFloat(cs.fontSize);
    if (size < min) { min = size; where = el.className + ' ' + n.textContent.trim().slice(0, 20); }
  }
  return { min, where };
});
const visibleToasts = page => page.evaluate(() => [...document.querySelectorAll('.ielts-toast')].map(t => {
  const r = t.getBoundingClientRect();
  return { text: t.textContent, top: r.top, bottom: r.bottom, left: r.left, right: r.right };
}));
async function waitToastsGone(page) {
  await page.waitForFunction(() => !document.querySelector('.ielts-toast'), null, { timeout: 6000 }).catch(() => {});
}

// ==================== 音频库 ====================
async function library(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, '/speaking');
  const vh = page.viewportSize().height;
  ok(await noOverflow(page), '音频库：不横向溢出');
  const first = await rect(page, '#topicList > .sp-tcard');
  ok(first && first.top < vh - 120, '音频库：第一屏就能看到话题列表（第一张卡片在首屏）', first);
  const two = await page.evaluate(() => [...document.querySelectorAll('#topicList > .sp-tcard')].slice(0, 2).map(c => c.getBoundingClientRect()).map(r => [Math.round(r.top), Math.round(r.left)]));
  ok(two.length === 2 && two[0][0] === two[1][0] && two[0][1] !== two[1][1], '音频库：话题一行两张卡片', two);
  const recent = await page.evaluate(() => [...document.querySelectorAll('#recentGrid .sp-rchip')].map(c => Math.round(c.getBoundingClientRect().height)));
  ok(recent.length === 4 && Math.max(...recent) <= 80, '音频库：「最近使用」是两列小卡片（4 个，每个不高于 80px）', recent);
  ok((await page.textContent('#recentSection .sp-label')).trim() === '最近使用', '音频库：「最近使用」标签不变');
  const small = await tapTargets(page, ['#chipTrack .sp-chip', '#sortSelect', '.sp-search', '[data-action=lib-more]'], 40);
  ok(!small.length, '音频库：Part 筛选、排序、搜索框、⋯ 都不小于 40px', small);
  const small44 = await tapTargets(page, ['.sp-tcard__play', '.sp-rchip__play', '#composerFab', '[data-action=lib-more]'], 44);
  ok(!small44.length, '音频库：连播按钮、新建按钮、⋯ 不小于 44px', small44);
  const font = await minFont(page);
  ok(font.min >= 12, '音频库：屏幕上没有小于 12px 的字', font);
  ok(await page.evaluate(() => parseFloat(getComputedStyle(document.getElementById('searchInput')).fontSize) >= 16), '音频库：搜索框 16px');
  ok(await page.evaluate(() => !document.querySelector('#topicList button button, #recentGrid button button, #topicList [role=button] button')), '音频库：卡片里没有嵌套的按钮（读屏能分开读）');
  await shot(page, '01-library');

  // 吸顶的搜索 + Part
  await page.evaluate(() => window.scrollTo(0, 700));
  await page.waitForTimeout(300);
  const search = await rect(page, '.sp-search');
  ok(search && search.top >= 40 && search.top < 140, '音频库：往下翻时搜索框吸在导航下面', search);
  const chips = await rect(page, '#partChips');
  ok(chips && chips.top < 200, '音频库：往下翻时 Part 筛选也吸在顶上', chips);
  ok(await page.evaluate(() => document.body.classList.contains('sp-scrolled')), '音频库：翻下去后「新建音频」缩成圆按钮');

  // 最后一张卡片不被浮动按钮盖住
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(400);
  const last = await page.evaluate(() => { const c = [...document.querySelectorAll('#topicList > .sp-tcard')].pop(); return c.getBoundingClientRect().bottom; });
  const fab = await rect(page, '#composerFab');
  ok(fab && last <= fab.top + 1, '音频库：翻到底时最后一行在「新建音频」按钮上面', { last, fabTop: fab && fab.top });
  await shot(page, '02-library-bottom');

  // Part 筛选：标签跟着变，最近使用收起，只剩这个 Part
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.tap('#chipTrack [data-part=Part2]');
  await page.waitForTimeout(300);
  ok((await page.textContent('#topicsLabel')).trim() === 'Part 2 话题', '筛选：列表标题变成「Part 2 话题」');
  ok(await page.evaluate(() => document.getElementById('recentSection').hidden), '筛选：选了 Part 后「最近使用」收起，列表上移');
  ok(await page.evaluate(() => [...document.querySelectorAll('#topicList .sp-tcard .sp-badge')].every(b => b.textContent === 'P2')), '筛选：只剩 Part 2 的话题');
  await page.tap('#chipTrack [data-part=all]');

  // ⋯ 菜单：管理和合集都在；返回手势先关菜单
  await page.tap('[data-action=lib-more]');
  await page.waitForTimeout(300);
  const sheetText = await page.textContent('#moreSheet');
  ok(/管理音频/.test(sheetText) && /合集播放页/.test(sheetText), '⋯ 菜单：有「管理音频」和「合集播放页」', sheetText);
  ok(await page.evaluate(() => document.documentElement.classList.contains('sp-lock')), '⋯ 菜单：打开时背景不滚');
  await shot(page, '03-library-menu');
  await page.goBack();
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => document.getElementById('moreSheet').hidden && location.pathname === '/speaking'), '⋯ 菜单：返回手势关掉菜单，还在音频库');
  ok(!(await page.evaluate(() => document.documentElement.classList.contains('sp-lock'))), '⋯ 菜单：关掉后背景能滚');

  // 管理模式（放进 ⋯ 里）→ 进话题后能删
  await page.tap('[data-action=lib-more]');
  await page.waitForTimeout(250);
  await page.tap('#moreSheet .sp-sheet__item >> text=管理音频');
  await page.waitForTimeout(500);
  ok((await visibleToasts(page)).some(t => /管理模式已开/.test(t.text)), '管理：从 ⋯ 打开管理模式有提示');
  await page.tap(`.sp-tcard__open[data-folder="${HOMETOWN}"]`);
  await page.waitForTimeout(500);
  ok(await page.evaluate(() => !!document.querySelector('.sp-managebar') && document.querySelectorAll('.sp-clip [data-action=delete-clip]').length > 0), '管理：进话题后每条都有删除按钮，顶上有「管理中」条');
  ok(/删除整个话题/.test(await page.textContent('#topicActions')), '管理：底部操作条变成「删除整个话题 + 完成」');
  await shot(page, '04-topic-manage');
  await page.tap('.sp-managebar [data-action=toggle-manage]');
  await waitToastsGone(page);

  ok(!page.errors.length, '音频库：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 返回时回到原来的位置 ====================
async function scrollRestore(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, '/speaking');
  // 翻到下面一点，点一张此时在屏幕中间的卡片
  await page.evaluate(() => window.scrollTo(0, 600));
  await page.waitForTimeout(300);
  const y0 = await page.evaluate(() => window.scrollY);
  const folder = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('#topicList .sp-tcard__open')];
    const c = cards.find(el => { const r = el.getBoundingClientRect(); return r.top > 250 && r.bottom < innerHeight - 120; });
    return c && c.dataset.folder;
  });
  await page.tap(`.sp-tcard__open[data-folder="${folder}"]`);
  await page.waitForTimeout(500);
  ok(await page.evaluate(() => !document.getElementById('viewTopic').hidden), '返回：点卡片进到话题页', folder);
  await page.goBack();
  await page.waitForTimeout(600);
  const y1 = await page.evaluate(() => window.scrollY);
  ok(Math.abs(y1 - y0) <= 4, '返回：侧滑 / 返回键回到音频库时停在原来的位置', { y0, y1 });
  // 用页面上的「‹ 音频库」也一样
  await page.tap(`.sp-tcard__open[data-folder="${folder}"]`);
  await page.waitForTimeout(500);
  await page.tap('#topicBar [data-action=back]');
  await page.waitForTimeout(600);
  const y2 = await page.evaluate(() => window.scrollY);
  ok(Math.abs(y2 - y0) <= 4, '返回：点「‹ 音频库」回来也停在原来的位置', { y0, y2 });
  // 话题跳话题（完整播放器的「打开话题」）以后，「‹ 音频库」还是回音频库，不是回上一个话题
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.tap(`.sp-tcard__open[data-folder="${HOMETOWN}"]`);
  await page.waitForTimeout(400);
  await page.tap('.sp-clip .sp-play');
  await page.waitForTimeout(500);
  await page.goBack();
  await page.waitForTimeout(400);
  await page.tap('.sp-tcard__open[data-folder="P1 - Weather"]');
  await page.waitForTimeout(400);
  await page.tap('#playerTitle');
  await page.waitForTimeout(400);
  await page.tap('#fullPlayer [data-action=fp-open-topic]');
  await page.waitForTimeout(800);
  ok(await page.evaluate(() => /Hometown/.test(document.getElementById('topbarTitle').textContent)), '完整播放器：「打开话题」去到正在放的话题');
  await page.tap('#topicBar [data-action=back]');
  await page.waitForTimeout(500);
  ok(await page.evaluate(() => !document.getElementById('viewLibrary').hidden), '返回：话题跳话题以后「‹ 音频库」仍然回音频库');
  await page.tap('#playerBar #toggleBtn');
  // 不认识的话题只提示一次
  await page.evaluate(() => { location.hash = '#folder=' + encodeURIComponent('不存在的话题'); });
  await page.waitForTimeout(800);
  const toasts = (await visibleToasts(page)).filter(t => /找不到话题/.test(t.text));
  ok(toasts.length === 1, '不存在的话题：只提示一次', toasts);
  ok(!page.errors.length, '返回：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 搜索 ====================
async function search(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, '/speaking');
  await page.tap('#searchInput');
  ok(await page.evaluate(() => getComputedStyle(document.getElementById('composerFab')).display === 'none'), '搜索：输入时「新建音频」按钮让开');
  await page.fill('#searchInput', 'lantern');
  await page.waitForSelector('#hitsList .sp-hit', { timeout: 5000 }).catch(() => {});
  const hit = await page.evaluate(() => {
    const h = document.querySelector('#hitsList .sp-hit');
    return h && { mark: (h.querySelector('mark') || {}).textContent, title: h.querySelector('.sp-hit__title').textContent, q: (h.querySelector('.sp-hit__q') || {}).textContent, playH: h.querySelector('.sp-hit__play').getBoundingClientRect().height };
  });
  ok(hit && /lantern/i.test(hit.mark || ''), '搜索：命中的词高亮', hit);
  ok(hit && !/^P1 -/.test(hit.title.replace(/^P1/, '').trim()) && /Hometown/.test(hit.title), '搜索：结果写话题名（不带「P1 -」前缀）', hit);
  ok(hit && /culture/.test(hit.q || ''), '搜索：结果带这一条的问题', hit);
  ok(hit && hit.playH >= 44, '搜索：结果右边有 44px 的播放按钮', hit);
  ok(await page.evaluate(() => document.getElementById('topicList').parentNode.hidden), '搜索：话题名一个没命中时，空的话题区收起');
  await page.setViewportSize({ width: PROFILES[engine].viewport.width, height: 470 });
  await page.waitForTimeout(300);
  const input = await rect(page, '#searchInput');
  ok(input && input.top >= 0 && input.bottom <= 470, '搜索：键盘弹起（可视高度 470）时搜索框还在屏幕里', input);
  await page.setViewportSize(PROFILES[engine].viewport);
  await shot(page, '05-search');
  await page.tap('#hitsList .sp-hit__open');
  await page.waitForTimeout(1200);
  const opened = await page.evaluate(() => {
    const c = document.querySelector('.sp-clip.is-open');
    if (!c) return null;
    const t = c.querySelector('.sp-clip__text');
    const r = c.getBoundingClientRect();
    return { text: t && t.textContent, top: r.top, bottom: r.bottom, bar: document.getElementById('topicBar').getBoundingClientRect().bottom };
  });
  ok(opened && /lanterns/.test(opened.text), '搜索：点结果进话题，那一条直接展开（能看到搜的那句）', opened);
  ok(opened && opened.top >= opened.bar - 2 && opened.top < page.viewportSize().height - 100, '搜索：展开的那条滚到顶栏下面', opened);
  await shot(page, '06-search-hit-open');
  ok(!page.errors.length, '搜索：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 话题页 + 播放器 ====================
async function topic(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, topicUrl(HOMETOWN));
  ok(await noOverflow(page), '话题：不横向溢出');
  const small = await tapTargets(page, ['#topicBar [data-action=back]', '#topicBar [data-action=topic-more]', '.sp-clip .sp-play', '.sp-clip__main', '#topicActions .sp-btn'], 44);
  ok(!small.length, '话题：返回、⋯、播放、每一条、底部按钮都不小于 44px', small);
  const font = await minFont(page);
  ok(font.min >= 12, '话题：屏幕上没有小于 12px 的字', font);
  ok(/连续播放 6 条/.test(await page.textContent('#topicActions')) && /添加/.test(await page.textContent('#topicActions')), '话题：底部操作条是「连续播放 + 添加」（拇指够得着）');
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(300);
  const lastClip = await page.evaluate(() => [...document.querySelectorAll('.sp-clip')].pop().getBoundingClientRect().bottom);
  const bar = await rect(page, '#topicActions');
  ok(lastClip <= bar.top + 1, '话题：翻到底时最后一条在底部操作条上面', { lastClip, barTop: bar.top });
  ok(await page.evaluate(() => document.getElementById('topicBar').classList.contains('is-stuck')), '话题：翻下去后顶栏显示话题名');
  await page.evaluate(() => window.scrollTo(0, 0));

  // 点一条就地展开，可以同时展开两条
  const mains = await page.$$('.sp-clip__main');
  await mains[0].tap();
  await page.waitForTimeout(500);
  await (await page.$$('.sp-clip__main'))[1].tap();
  await page.waitForTimeout(500);
  const open2 = await page.evaluate(() => [...document.querySelectorAll('.sp-clip.is-open .sp-clip__text')].map(t => t.textContent));
  ok(open2.length === 2 && open2.every(t => t.length > 10 && !/加载中/.test(t)), '话题：点一条展开全文，可以同时展开两条', open2);
  ok(open2.length && !/^Where is your hometown\?/.test(open2[0]), '话题：展开的全文不再重复问题（问题已经在上面）', open2[0]);
  await shot(page, '07-topic-expanded');

  // 底部「连续播放」→ 迷你播放条
  await page.tap('#topicActions [data-action=play-topic]');
  await page.waitForFunction(() => document.getElementById('audioEl').currentTime > 0.3, null, { timeout: 8000 }).catch(() => {});
  const player = await rect(page, '#playerBar');
  ok(player && player.visible && player.height >= 60 && player.height <= 100, '播放：迷你播放条 64px 左右', player);
  ok(await page.evaluate(() => document.getElementById('topicActions').hidden), '播放：放音频时底部操作条让给迷你播放条');
  ok((await page.textContent('#playerTitle')).trim() === 'Where is your hometown?', '播放：迷你播放条写的是这一条的问题', await page.textContent('#playerTitle'));
  ok(/Hometown · 1\/6/.test(await page.textContent('#playerSub')), '播放：下面一行是「话题 · 第几条」', await page.textContent('#playerSub'));
  const ms = await page.evaluate(() => navigator.mediaSession && navigator.mediaSession.metadata
    ? { title: navigator.mediaSession.metadata.title, artist: navigator.mediaSession.metadata.artist, album: navigator.mediaSession.metadata.album, state: navigator.mediaSession.playbackState } : null);
  ok(ms && ms.title === 'Where is your hometown?' && /Hometown/.test(ms.artist) && ms.album === '口语音频库', '锁屏：Media Session 有标题、话题名', ms);
  ok(ms && ms.state === 'playing', '锁屏：播放状态同步给系统', ms);
  ok(await page.evaluate(() => document.querySelector('.sp-clip.is-current') === document.querySelector('.sp-clip')), '播放：正在放的那条高亮');
  const smallP = await tapTargets(page, ['#toggleBtn', '#nextBtn'], 44);
  ok(!smallP.length, '播放：迷你播放条按钮不小于 44px', smallP);

  // 提示条浮在播放条上面
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.tap('.sp-clip.is-open [data-action=copy-text]');
  await page.waitForTimeout(400);
  const toasts = await visibleToasts(page);
  const pbar = await rect(page, '#playerBar');
  ok(toasts.length && toasts.every(t => t.bottom <= pbar.top + 1 && t.right <= page.viewportSize().width), '提示条：浮在迷你播放条上面，不出屏', { toasts, playerTop: pbar.top });
  await shot(page, '08-topic-playing');

  // 完整播放器：点迷你条中间打开，倍速、下一条，返回手势收起
  await page.tap('#playerTitle');
  await page.waitForTimeout(500);
  const fp = await rect(page, '#fullPlayer');
  ok(fp && fp.visible && fp.height > page.viewportSize().height * 0.8, '完整播放器：从底部升起，约 92% 屏高', fp);
  ok(/Where is your hometown\?/.test(await page.textContent('#fpBody')) && /mid-sized city/.test(await page.textContent('#fpBody')), '完整播放器：显示这一条的问题和全文');
  const smallF = await tapTargets(page, ['#fullPlayer .sp-fp__transport button', '#fpSeek', '#fpRate button', '#fullPlayer [data-action=close-fullplayer]'], 40);
  ok(!smallF.length, '完整播放器：按钮、进度条、倍速都够大', smallF);
  await page.tap('#fpRate [data-rate="1.25"]');
  ok(await page.evaluate(() => document.getElementById('audioEl').playbackRate === 1.25), '完整播放器：倍速一点就换（0.75 / 1.0 / 1.25 / 1.5）');
  await page.tap('#fullPlayer [data-action=next]');
  await page.waitForTimeout(500);
  ok(/第 2 \/ 6 条/.test(await page.textContent('#fpIndex')) && /Do you like living there/.test(await page.textContent('#fpBody')), '完整播放器：下一条', await page.textContent('#fpIndex'));
  ok(await page.evaluate(() => navigator.mediaSession && navigator.mediaSession.metadata && navigator.mediaSession.metadata.title === 'Do you like living there?'), '锁屏：换到下一条时标题跟着换');
  await shot(page, '09-full-player');
  await page.goBack();
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => document.getElementById('fullPlayer').hidden && !document.getElementById('viewTopic').hidden), '完整播放器：返回手势收起播放器，还在话题页');

  // 拖进度条时被浏览器取消（pointercancel）后进度照常走（以前会冻住）
  await page.tap('#playerTitle');
  await page.waitForTimeout(400);
  await page.evaluate(() => { const a = document.getElementById('audioEl'); a.currentTime = 0; if (a.paused) a.play(); });
  const seek = await rect(page, '#fpSeek');
  await page.evaluate(([x, y]) => {
    const bar = document.getElementById('fpSeek');
    const opts = { pointerId: 7, pointerType: 'touch', isPrimary: true, bubbles: true, clientX: x, clientY: y };
    bar.dispatchEvent(new PointerEvent('pointerdown', opts));
    bar.dispatchEvent(new PointerEvent('pointermove', Object.assign({}, opts, { clientX: x + 10 })));
    bar.dispatchEvent(new PointerEvent('pointercancel', opts));
  }, [seek.left + seek.width * 0.1, seek.top + seek.height / 2]);
  const t0 = await page.textContent('#fpCur');
  await page.waitForTimeout(2200);
  const t1 = await page.textContent('#fpCur');
  ok(t0 !== t1, '进度条：拖动被取消后时间还在走', { t0, t1 });
  if (engine === 'chromium') {
    // 真的手指拖一下（CDP 触摸事件），松手后进度条和时间都跟着音频走
    const cdp = await ctx.newCDPSession(page);
    const pt = (x, y) => [{ x, y, radiusX: 6, radiusY: 6, force: 1, id: 1 }];
    const y = seek.top + seek.height / 2;
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: pt(seek.left + 20, y) });
    for (let i = 1; i <= 6; i++) {
      await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: pt(seek.left + 20 + i * 15, y + i * 2) });
      await page.waitForTimeout(30);
    }
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
    await page.waitForTimeout(300);
    const a = await page.evaluate(() => ({ label: document.getElementById('fpCur').textContent, fill: document.querySelector('#fpSeek .sp-seek__fill').style.width }));
    await page.waitForTimeout(2200);
    const b = await page.evaluate(() => ({ label: document.getElementById('fpCur').textContent, fill: document.querySelector('#fpSeek .sp-seek__fill').style.width }));
    ok(a.label !== b.label && a.fill !== b.fill, '进度条：手指拖完以后时间和进度条继续走', { a, b });
  }
  await page.goBack();
  await page.waitForTimeout(300);

  // 连播：一条放完自动下一条，下一条自动展开
  const before = await page.evaluate(() => { const a = document.getElementById('audioEl'); if (a.paused) a.play(); a.currentTime = Math.max(0, a.duration - 0.3); return Number(/(\d+)\/6/.exec(document.getElementById('playerSub').textContent)[1]); });
  await page.waitForFunction(n => new RegExp((n + 1) + '/6').test(document.getElementById('playerSub').textContent), before, { timeout: 6000 }).catch(() => {});
  await page.waitForTimeout(800);
  const cur = await page.evaluate(() => { const c = document.querySelector('.sp-clip.is-current'); return c && { open: c.classList.contains('is-open'), sub: document.getElementById('playerSub').textContent }; });
  ok(cur && new RegExp((before + 1) + '/6').test(cur.sub) && cur.open, '连播：放完自动下一条，下一条自动展开', { before, cur });

  // ⋯ → 全部展开
  await page.tap('#topicBar [data-action=topic-more]');
  await page.waitForTimeout(300);
  await page.tap('#moreSheet .sp-sheet__item >> text=全部展开');
  await page.waitForTimeout(800);
  ok(await page.evaluate(() => document.querySelectorAll('.sp-clip.is-open').length === 6), '⋯ 菜单：全部展开');

  // 删除确认：底部升起，说的是这一条讲什么而不是文件名；返回手势取消
  await page.tap('#topicBar [data-action=topic-more]');
  await page.waitForTimeout(300);
  await page.tap('#moreSheet .sp-sheet__item >> text=管理（删除音频）');
  await page.waitForTimeout(400);
  await page.tap('.sp-clip [data-action=delete-clip]');
  await page.waitForTimeout(400);
  const dlg = await page.evaluate(() => { const d = document.getElementById('dialog'); const r = d.getBoundingClientRect(); return { text: d.textContent, bottom: r.bottom, left: r.left, width: r.width }; });
  ok(/Where is your hometown\?/.test(dlg.text) && !/\.mp3/.test(dlg.text), '删除确认：写的是这一条的问题，不是文件名', dlg.text);
  ok(Math.abs(dlg.bottom - page.viewportSize().height) <= 1 && dlg.left === 0, '删除确认：从底部升起（拇指够得着删除键）', dlg);
  await shot(page, '10-delete-confirm');
  await page.goBack();
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => document.getElementById('dialog').hidden && !document.getElementById('viewTopic').hidden), '删除确认：返回手势取消，不离开话题');
  ok(!page.errors.length, '话题：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== Part 2 题卡、长文 ====================
async function cueAndReader(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, topicUrl(NEIGHBOUR));
  const cue = await page.evaluate(() => { const p = document.querySelector('.sp-cue .sp-question__text'); return { h: p.getBoundingClientRect().height, full: p.scrollHeight }; });
  ok(cue.h < cue.full && cue.h <= 3 * 16 * 1.6 + 2, 'Part 2：题卡默认只显示三行', cue);
  const firstClip = await rect(page, '.sp-clip');
  ok(firstClip && firstClip.top < page.viewportSize().height * 0.75, 'Part 2：第一条音频在首屏', firstClip);
  await page.tap('[data-action=toggle-cue]');
  const cue2 = await page.evaluate(() => { const p = document.querySelector('.sp-cue .sp-question__text'); return p.getBoundingClientRect().height >= p.scrollHeight - 1; });
  ok(cue2, 'Part 2：点「展开全部」看到整张题卡');
  await shot(page, '11-topic-p2');

  await open(page, topicUrl(READING));
  await page.tap('.sp-clip__main');
  await page.waitForTimeout(900);
  const reader = await page.evaluate(() => { const r = document.getElementById('reader'); const b = r.getBoundingClientRect(); return { hidden: r.hidden, top: b.top, h: b.height, text: document.getElementById('readerText').textContent.length, size: getComputedStyle(document.getElementById('readerText')).fontSize }; });
  ok(!reader.hidden && reader.top === 0 && reader.h >= page.viewportSize().height - 1 && reader.text > 2000, '长文：超过 600 字的原文用全屏阅读页打开', reader);
  ok(parseFloat(reader.size) >= 17, '长文：阅读页正文 17px', reader.size);
  const smallR = await tapTargets(page, ['#reader [data-action=close-reader]', '#readerFoot .sp-btn'], 44);
  ok(!smallR.length, '长文：阅读页按钮不小于 44px', smallR);
  await shot(page, '12-reader');
  await page.goBack();
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => document.getElementById('reader').hidden && !document.getElementById('viewTopic').hidden), '长文：返回手势关掉阅读页，回到话题');
  ok(!page.errors.length, '题卡 / 长文：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 新建音频面板 ====================
async function composer(browser) {
  const { ctx, page } = await newPage(browser);
  await open(page, '/speaking');
  await page.tap('#composerFab');
  await page.waitForTimeout(500);
  const vh = page.viewportSize().height;
  const gen = await rect(page, '#generateBtn');
  ok(gen && gen.bottom <= vh && gen.height >= 48, '新建：「生成音频」钉在面板底部、在屏幕里', gen);
  ok(await page.evaluate(() => document.documentElement.classList.contains('sp-lock')), '新建：打开时背景不滚');
  await page.tap('#partSeg [data-part=P2]');
  await page.fill('#topicInput', 'A windy morning');
  await page.waitForTimeout(400);
  const sugg = await page.evaluate(() => { const b = document.getElementById('topicSuggest'); return b.hidden ? null : { pos: getComputedStyle(b).position, h: [...b.querySelectorAll('button')].map(x => x.getBoundingClientRect().height) }; });
  ok(sugg && sugg.pos === 'static' && sugg.h.every(h => h >= 44), '新建：话题联想就排在输入框下面，每行 44px', sugg);
  await page.tap('.sp-suggest__new');
  await page.waitForTimeout(600);
  const order = await page.evaluate(() => {
    const y = id => document.getElementById(id).getBoundingClientRect().top;
    return { cue: y('part2Question'), text: y('textInput'), gen: y('generateBtn'), cueVisible: !document.getElementById('part2Wrap').hidden };
  });
  ok(order.cueVisible && order.cue < order.text && order.text < order.gen, '新建：Part 2 题卡（必填）排在英文和「生成」上面', order);
  const ta = await page.evaluate(() => { const t = document.getElementById('textInput'); return { h: t.getBoundingClientRect().height, fs: parseFloat(getComputedStyle(t).fontSize) }; });
  ok(ta.h >= 170 && ta.fs >= 16, '新建：英文框至少 6 行、16px', ta);
  const inputs = await page.evaluate(() => ['topicInput', 'part2Question', 'textInput'].map(id => parseFloat(getComputedStyle(document.getElementById(id)).fontSize)));
  ok(inputs.every(s => s >= 16), '新建：所有输入框 16px', inputs);
  const sw = await rect(page, '.sp-check');
  ok(sw && sw.height >= 44, '新建：「生成后留在这个话题」是一整行开关（≥44px）', sw);
  ok(await page.evaluate(() => document.getElementById('composer').scrollWidth <= document.getElementById('composer').clientWidth + 1), '新建：面板里没有横向溢出');
  await shot(page, '13-composer-p2');

  // 生成失败：一句人话 + 重试，不显示原始异常
  await page.fill('#part2Question', 'Describe a windy morning you remember.');
  await page.fill('#textInput', 'I remember a windy morning when the whole street was covered in leaves and everyone was laughing.');
  await page.tap('#generateBtn');
  await page.waitForSelector('.sp-queue__row--error', { timeout: 15000 }).catch(() => {});
  const err = await page.evaluate(() => { const r = document.querySelector('.sp-queue__row--error'); return r && { why: r.querySelector('.sp-queue__why').textContent, retry: !!r.querySelector('[data-action=retry-generate]'), all: r.textContent }; });
  ok(err && /语音服务暂时不可用/.test(err.why) && err.retry, '新建：失败时说清楚原因，并有「重试」', err);
  ok(err && !/HTTPSConnectionPool|Traceback|api\.deerapi/.test(err.all), '新建：不把原始异常给人看', err);
  const t = await visibleToasts(page);
  ok(!t.length, '新建：失败那一行就是提示，不再叠一条提示条把它盖住', t);
  ok(await page.evaluate(() => !!document.querySelector('#generateBtn svg') && document.getElementById('generateBtn').textContent.trim() === '生成音频'), '新建：生成过一次后按钮的「＋」图标还在');
  const retryRect = await rect(page, '.sp-queue__row--error [data-action=retry-generate]');
  ok(retryRect && retryRect.bottom <= gen.top && retryRect.top >= 0, '新建：失败那一行自动滚进视野', retryRect);
  await shot(page, '14-composer-error');
  await waitToastsGone(page);
  await page.tap('.sp-queue__row--error [data-action=retry-generate]');
  await page.waitForTimeout(300);
  await page.waitForSelector('.sp-queue__row--error', { timeout: 15000 }).catch(() => {});
  ok(await page.evaluate(() => document.querySelectorAll('#queueBox .sp-queue__row').length === 1 && !!document.querySelector('.sp-queue__row--error')), '新建：点「重试」原样再发一次（不多出一行）');
  ok(await page.evaluate(() => /windy morning/.test(document.getElementById('textInput').value)), '新建：失败后英文还在框里');
  await page.goBack();
  await page.waitForTimeout(500);
  ok(await page.evaluate(() => !document.getElementById('composer').classList.contains('is-open') && location.pathname === '/speaking'), '新建：返回手势关掉面板，还在音频库');
  ok(await page.evaluate(() => document.getElementById('composer').inert), '新建：关掉后面板里的输入框不能被 Tab / 读屏碰到');

  // 从话题页打开：存到哪已经定了，只显示一行摘要
  await open(page, topicUrl(HOMETOWN));
  await page.tap('#topicActions [data-action=add-here]');
  await page.waitForTimeout(500);
  const dest = await page.evaluate(() => ({ chip: !document.getElementById('composerDest').hidden && document.getElementById('composerDestName').textContent, seg: getComputedStyle(document.getElementById('partSeg')).display }));
  ok(dest.chip === HOMETOWN && dest.seg === 'none', '新建：从话题页打开时只显示「存入 P1 - Hometown · 更改」', dest);
  await page.tap('[data-action=dest-change]');
  ok(await page.evaluate(() => getComputedStyle(document.getElementById('partSeg')).display !== 'none'), '新建：点「更改」才出现 Part 和话题名');
  await shot(page, '15-composer-from-topic');
  ok(!page.errors.length, '新建：没有脚本报错', page.errors);
  await ctx.close();

  // 键盘弹起时可视区域只剩 ~470px：输入框和「生成音频」都还在屏幕里
  const kb = await newPage(browser, { viewport: { width: PROFILES[engine].viewport.width, height: 470 } });
  await open(kb.page, '/speaking');
  await kb.page.tap('#composerFab');
  await kb.page.waitForTimeout(500);
  await kb.page.focus('#textInput');
  await kb.page.waitForTimeout(300);
  const g = await rect(kb.page, '#generateBtn');
  const ti = await rect(kb.page, '#textInput');
  ok(g && g.bottom <= 470 && g.top > 300, '键盘：「生成音频」在键盘上方', g);
  ok(ti && ti.top < g.top && ti.top >= 0, '键盘：英文框在屏幕里', ti);
  await shot(kb.page, '16-composer-keyboard');
  await kb.page.goBack();
  await open(kb.page, topicUrl(NEIGHBOUR));
  await kb.page.tap('#topicBar [data-action=topic-more]');
  await kb.page.waitForTimeout(300);
  await kb.page.tap('#moreSheet .sp-sheet__item >> text=编辑题卡问题');
  await kb.page.waitForTimeout(500);
  const q = await rect(kb.page, '#dialogQuestion');
  const save = await rect(kb.page, '#dialog [data-dialog=ok]');
  ok(q && save && q.top >= 0 && save.bottom <= 470, '键盘：编辑题卡问题时文本框和「保存」都在屏幕里', { q, save });
  await kb.ctx.close();
}

// ==================== 读取中 / 空 / 出错 ====================
async function states(browser) {
  const { ctx, page } = await newPage(browser);
  await page.route('**/list_audio', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{"Part1":[],"Part2":[],"Part3":[],"其他":[]}' }));
  await open(page, '/speaking');
  ok(/还没有音频/.test(await page.textContent('#topicList')) && !!(await page.$('#topicList [data-action=new-first]')), '空库：有「新建第一条」按钮');
  await page.tap('#topicList [data-action=new-first]');
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => document.getElementById('composer').classList.contains('is-open')), '空库：点「新建第一条」打开面板');
  await shot(page, '17-empty');
  await ctx.close();

  const e = await newPage(browser);
  let fails = 1;
  await e.page.route('**/list_audio', r => (fails-- > 0 ? r.fulfill({ status: 500, body: 'boom' }) : r.continue()));
  await open(e.page, '/speaking');
  ok(/列表没加载出来/.test(await e.page.textContent('#topicList')), '出错：列表没加载出来时有说明和「重试」');
  await e.page.tap('#topicList [data-action=reload-list]');
  await e.page.waitForSelector('#topicList .sp-tcard', { timeout: 5000 }).catch(() => {});
  ok(await e.page.evaluate(() => document.querySelectorAll('#topicList .sp-tcard').length > 5), '出错：点「重试」后列表出来了');
  await e.ctx.close();

  // 提示条里很长、没有断行点的英文（以前是后端原始异常）也要换行，不能伸出屏幕
  const t = await newPage(browser);
  await open(t.page, '/speaking');
  await t.page.evaluate(() => window.IELTSUI.toast('HTTPSConnectionPool(host=api.example.com,port=443):Max_retries_exceeded_with_url:/v1/audio/speech_' + 'x'.repeat(80), 'error'));
  await t.page.waitForTimeout(300);
  const long = await visibleToasts(t.page);
  ok(long.length && long.every(x => x.right <= t.page.viewportSize().width && x.left >= 0), '提示条：很长的英文也会换行，不伸出屏幕', long);
  await t.ctx.close();

  const l = await newPage(browser);
  await l.page.route('**/list_audio', async r => { await new Promise(res => setTimeout(res, 1500)); await r.continue(); });
  await l.page.goto(BASE + '/speaking');
  await l.page.waitForTimeout(600);
  ok(await l.page.evaluate(() => [...document.querySelectorAll('#topicList .sp-skel')].filter(s => s.getBoundingClientRect().height > 0).length >= 4), '读取中：先显示几张灰色占位卡片');
  await l.ctx.close();
}

// ==================== 深色 ====================
async function dark(browser) {
  const { ctx, page } = await newPage(browser, { dark: true });
  await open(page, '/speaking');
  ok(await noOverflow(page), '深色：音频库不横向溢出');
  const sort = await page.evaluate(() => { const s = getComputedStyle(document.getElementById('sortSelect')); return { color: s.color, repeat: s.backgroundRepeat }; });
  ok(sort.color === 'rgba(0, 0, 0, 0)' && /no-repeat/.test(sort.repeat), '深色：排序按钮只有图标（不露字、不平铺）', sort);
  await shot(page, '18-dark-library');
  await open(page, topicUrl(HOMETOWN));
  await page.tap('.sp-clip .sp-play');
  await page.waitForTimeout(800);
  const bg = await page.evaluate(() => [getComputedStyle(document.getElementById('playerBar')).backgroundColor, getComputedStyle(document.getElementById('clipList')).backgroundColor]);
  ok(bg[0] === bg[1], '深色：迷你播放条和卡片同一个底色（不是 theme.css 的蓝灰）', bg);
  await shot(page, '19-dark-topic');
  await page.tap('#composerFab').catch(() => {});
  ok(!page.errors.length, '深色：没有脚本报错', page.errors);
  await ctx.close();
}

// ==================== 合集页 ====================
async function combined(browser) {
  const { ctx, page } = await newPage(browser);
  // 合集页请求的地址是 /combined_audio/<话题>.mp3，以前服务器找的是 <话题>.mp3.mp3，永远 404
  const res = await ctx.request.get(BASE + '/combined_audio/' + encodeURIComponent(HOMETOWN) + '.mp3', { headers: { Authorization: 'Bearer ' + TOKEN } });
  ok(res.status() === 200, '合集：页面请求的合集音频地址能拿到文件（不再 404）', res.status());
  await open(page, '/combined');
  await page.waitForTimeout(800);
  ok(await noOverflow(page), '合集：不横向溢出');
  const back = await page.evaluate(() => { const b = document.getElementById('backBtn'); const r = b.getBoundingClientRect(); return { text: b.textContent.trim(), h: r.height }; });
  ok(/口语音频库/.test(back.text) && back.h >= 44, '合集：返回按钮是「‹ 口语音频库」、44px', back);
  const small = await tapTargets(page, ['.category-btn', '.folder-card .folder-btn'], 40);
  ok(!small.length, '合集：分类和按钮都不小于 40px', small);
  const card = await rect(page, '.folder-card');
  ok(card && card.height <= 110, '合集：每个话题一行（不再是两个大按钮叠起来）', card);
  await shot(page, '20-combined');
  // 名字带单引号的话题也能播；播放器从底部升起，列表不动；音频真的能加载（以前请求 .mp3.mp3 永远 404）
  await page.evaluate(() => window.scrollTo(0, 300));
  await page.waitForTimeout(200);
  const y0 = await page.evaluate(() => window.scrollY);
  await page.tap(`.folder-card[data-folder="${APOSTROPHE}"] [data-role=play]`);
  await page.waitForFunction(() => document.getElementById('audioPlayer').duration > 0, null, { timeout: 8000 }).catch(() => {});
  await page.waitForTimeout(500);   // 等升起的动画走完
  const st = await page.evaluate(() => { const s = document.getElementById('playerSection'); const r = s.getBoundingClientRect(); const a = document.getElementById('audioPlayer'); return { pos: getComputedStyle(s).position, bottom: r.bottom, dur: a.duration, err: a.error && a.error.code, y: scrollY, title: document.getElementById('playerTitle').textContent, answer: parseFloat(getComputedStyle(document.querySelector('.subtitle-answer') || document.body).fontSize) }; });
  ok(st.dur > 5 && !st.err, '合集：「播放合集」的音频能加载（不再 404）', st);
  ok(st.pos === 'fixed' && Math.abs(st.bottom - page.viewportSize().height) <= 1 && st.y === y0, '合集：播放器从底部升起，列表停在原处', st);
  ok(/Children's games/.test(st.title), '合集：名字带单引号的话题按钮正常', st.title);
  ok(st.answer >= 16, '合集：字幕 16px 以上', st.answer);
  await shot(page, '21-combined-player');
  await page.goBack();
  await page.waitForTimeout(400);
  ok(await page.evaluate(() => !document.getElementById('playerSection').classList.contains('active') && location.pathname === '/combined'), '合集：返回手势收起播放器，还在合集页');
  ok(!page.errors.length, '合集：没有脚本报错', page.errors);
  await ctx.close();

  // 从话题页的 ⋯ →「合集播放页」过来（带 #folder=）：直接打开那个话题的播放器；返回按钮回到那个话题
  const d = await newPage(browser);
  await open(d.page, topicUrl(HOMETOWN));
  await d.page.tap('#topicBar [data-action=topic-more]');
  await d.page.waitForTimeout(300);
  await d.page.tap('#moreSheet .sp-sheet__item >> text=合集播放页');
  await d.page.waitForURL(/\/combined/, { timeout: 5000 }).catch(() => {});
  ok(decodeURIComponent(d.page.url()).endsWith('/combined#folder=' + HOMETOWN), '合集：话题页的「合集播放页」带着这个话题', d.page.url());
  await d.page.waitForFunction(() => document.getElementById('playerSection').classList.contains('active'), null, { timeout: 8000 }).catch(() => {});
  ok(await d.page.evaluate(() => document.getElementById('playerSection').classList.contains('active') && /Hometown/.test(document.getElementById('playerTitle').textContent)), '合集：从话题过来直接打开那个话题的播放器');
  await d.page.goBack();
  await d.page.waitForTimeout(300);
  ok(await d.page.evaluate(() => location.pathname === '/combined' && !document.getElementById('playerSection').classList.contains('active')), '合集：返回手势先收起播放器');
  await d.page.tap('#backBtn');
  await d.page.waitForURL(/\/speaking/, { timeout: 5000 }).catch(() => {});
  await d.page.waitForTimeout(800);
  ok(decodeURIComponent(d.page.url()).endsWith('/speaking#folder=' + HOMETOWN) && await d.page.evaluate(() => !document.getElementById('viewTopic').hidden), '合集：「‹ 口语音频库」回到原来那个话题', d.page.url());
  ok(!d.page.errors.length, '合集（深链）：没有脚本报错', d.page.errors);
  await d.ctx.close();
}

// ==================== 桌面宽度：触屏拖进度条（老 bug，桌面也有） ====================
async function desktopTouchSeek(browser) {
  const { ctx, page } = await newPage(browser, { viewport: { width: 1024, height: 700 }, desktop: true });
  await open(page, topicUrl(HOMETOWN));
  await page.click('.sp-clip [data-action=play-clip]');
  await page.waitForFunction(() => document.getElementById('audioEl').currentTime > 0.2, null, { timeout: 8000 }).catch(() => {});
  ok(await page.evaluate(() => getComputedStyle(document.getElementById('seekBar')).touchAction === 'none'), '桌面播放条：进度条不让浏览器拿去滚动（touch-action: none）');
  const seek = await rect(page, '#seekBar');
  await page.evaluate(([x, y]) => {
    const bar = document.getElementById('seekBar');
    const opts = { pointerId: 9, pointerType: 'touch', isPrimary: true, bubbles: true, clientX: x, clientY: y };
    bar.dispatchEvent(new PointerEvent('pointerdown', opts));
    bar.dispatchEvent(new PointerEvent('pointercancel', opts));
  }, [seek.left + 5, seek.top + seek.height / 2]);
  const a = await page.textContent('#curTime');
  await page.waitForTimeout(2200);
  const b = await page.textContent('#curTime');
  ok(a !== b, '桌面播放条：拖动被取消后时间还在走（以前冻住）', { a, b });
  await ctx.close();
}

(async () => {
  const which = process.argv[2] || 'all';
  const engines = which === 'all' ? ['webkit', 'chromium'] : [which];
  for (const name of engines) {
    engine = name;
    const browser = await pw[name].launch();
    for (const suite of [library, scrollRestore, search, topic, cueAndReader, composer, states, dark, combined, desktopTouchSeek]) {
      try { await suite(browser); } catch (e) { ok(false, suite.name + ' 跑崩了', e.message.split('\n')[0]); }
    }
    await browser.close();
  }
  console.log(`通过 ${pass} 项，失败 ${fail} 项`);
  process.exit(fail ? 1 : 0);
})();

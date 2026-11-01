// 手机：ENGINE=webkit 用 390×844（iPhone），chromium 用 360×780 + isMobile（安卓），都开触屏；亮色和暗色。
// 查：不横向溢出；顺序 等你完成 → 最近的挑战（一行，点开是排名）→ 发帖框 → 帖子；四个附件按钮一行；
// 整屏发帖面板（发布在顶栏、键盘弹出时还在）；选录音 / 选文章 / 发起挑战是底部面板、不框里套框；贴底的回复条；
// 删帖、删评论走 ⋯ 面板再确认；看大图左右滑、44px 关闭；答题整屏、选项在下半屏；返回键先关最上面一层；
// 提示条不盖住按钮。脚本自己用接口建一个带两张图和一个挑战的帖子，不依赖前面脚本留下的数据。
const fs = require('fs');
const path = require('path');
const { ok, offline, shot, run, BASE, ENGINE, FX, toks } = require('./lib');

const DEVICE = ENGINE === 'webkit'
  ? { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 }
  : { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 };
const W = DEVICE.viewport.width, H = DEVICE.viewport.height, KB_H = 470;
const PAGE = BASE + '/message_board';

async function phone(browser, who, dark) {
  const ctx = await browser.newContext(Object.assign({ colorScheme: dark ? 'dark' : 'light' }, DEVICE));
  await offline(ctx);
  await ctx.addInitScript(([t, u, theme]) => {
    if (location.protocol === 'about:') return;   // about:blank 上碰 localStorage 会报错
    localStorage.setItem('authToken', t);
    localStorage.setItem('currentUser', JSON.stringify(u));
    localStorage.setItem('ui-theme', theme);
  }, [toks[who].token, toks[who].user, dark ? 'dark' : 'light']);
  const page = await ctx.newPage();
  page._errors = [];
  page.on('pageerror', e => page._errors.push(e.message));
  page.on('dialog', async d => { page._errors.push('native dialog ' + d.message()); await d.dismiss(); });
  return { ctx, page };
}
// 一段流程出错（比如旧版页面上没有这个按钮）只记一条 FAIL，接着跑下一段
async function step(name, fn) {
  try { await fn(); } catch (e) { ok(false, `${name} (step crashed: ${String(e.message || e).split('\n')[0]})`); }
}
const wait = (page, ms) => page.waitForTimeout(ms || 400);
// 模拟返回键 / 右滑返回。推迟一拍再退：退出页面时 evaluate 本身别跟着报「上下文没了」
const back = async (page) => { await page.evaluate(() => { setTimeout(() => history.back(), 0); }); await wait(page, 600); };
async function openBoard(page) {
  await page.goto('about:blank');
  await page.goto(PAGE);
  await page.waitForSelector('.mb-post', { timeout: 8000 });
  await wait(page, 1500);
}
const box = (page, sel) => page.evaluate(s => {
  const el = typeof s === 'string' ? document.querySelector(s) : null;
  if (!el) return null;
  const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
  return { top: r.top, bottom: r.bottom, left: r.left, right: r.right, width: r.width, height: r.height, visible: r.width > 0 && r.height > 0 && cs.display !== 'none' && cs.visibility !== 'hidden' };
}, sel);
const seen = async (page, sel) => { const b = await box(page, sel); return !!(b && b.visible); };
async function noOverflow(page, what) {
  const r = await page.evaluate(() => {
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
      if (!scroller && (b.right > vw + 1 || b.left < -1)) bad.push(el.tagName.toLowerCase() + '.' + [...el.classList].join('.'));
    });
    return { sw: document.documentElement.scrollWidth, vw, bad: bad.slice(0, 4) };
  });
  ok(r.sw <= r.vw && !r.bad.length, `${what}: no horizontal overflow (${r.sw}/${r.vw} ${r.bad.join(' ')})`);
}
// 提示条和某组元素有没有叠在一起
const toastCovers = (page, sel) => page.evaluate(s => {
  const R = r => [Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)];
  const ts = [...document.querySelectorAll('.ielts-toast')].map(t => ({ r: t.getBoundingClientRect(), text: t.textContent })).filter(t => t.r.width > 0);
  const els = [...document.querySelectorAll(s)].map(e => e.getBoundingClientRect()).filter(r => r.width > 0);
  const hits = [];
  ts.forEach(t => els.forEach(e => { if (t.r.left < e.right && t.r.right > e.left && t.r.top < e.bottom && t.r.bottom > e.top) hits.push({ toast: t.text, at: R(t.r), el: R(e) }); }));
  return { toasts: ts.length, hit: hits.length > 0, hits: hits.slice(0, 3) };
}, sel);
// 合成一次横向滑动（Playwright 没有滑动手势），页面的 touchstart / touchend 处理照常收到
const swipe = (page, sel, dx) => page.evaluate(([s, d]) => {
  const el = document.querySelector(s);
  const r = el.getBoundingClientRect();
  const x = r.left + r.width / 2, y = r.top + r.height / 2;
  const fire = (type, cx) => {
    const ev = new Event(type, { bubbles: true, cancelable: true });
    const t = [{ clientX: cx, clientY: y, identifier: 1, target: el }];
    Object.defineProperty(ev, 'touches', { value: type === 'touchend' ? [] : t });
    Object.defineProperty(ev, 'changedTouches', { value: t });
    el.dispatchEvent(ev);
  };
  fire('touchstart', x);
  fire('touchend', x + d);
}, [sel, dx]);

// 用接口给林夏建一个带两张图 + 一个挑战（@ 周屿、陈默）的帖子
async function seed(page) {
  const img = n => fs.readFileSync(path.join(FX, n)).toString('base64');
  return page.evaluate(async ([a, b]) => {
    const tk = localStorage.getItem('authToken');
    const h = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + tk };
    const up = async (b64, name) => {
      const bin = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      const fd = new FormData();
      fd.append('image', new Blob([bin], { type: 'image/png' }), name);
      fd.append('user_id', 'linxia');
      return (await (await fetch('/api/upload_message_image', { method: 'POST', headers: { Authorization: 'Bearer ' + tk }, body: fd })).json()).filename;
    };
    const f1 = await up(a, 'a.png'), f2 = await up(b, 'b.png');
    const arts = await (await fetch('/api/get_articles_list', { headers: h })).json();
    const ids = Object.values(arts.categories).flat().map(x => x.id).slice(0, 2);
    const c = await (await fetch('/api/create_challenge', { method: 'POST', headers: h, body: JSON.stringify({ title: '手机测试挑战', description: '五个词', article_ids: ids, word_count: 5, mentioned_users: ['zhouyu', 'chenmo'] }) })).json();
    const m = await (await fetch('/api/messages', { method: 'POST', headers: h, body: JSON.stringify({ type: 'mixed_content', token: tk, content: { text: '手机测试帖：两张图和一个挑战', audios: [], articles: [], images: [{ filename: f1, caption: '' }, { filename: f2, caption: '' }], challenge: { id: c.challenge_id, title: '手机测试挑战', description: '五个词', vocabulary_count: c.vocabulary_count, mentioned_users: ['zhouyu', 'chenmo'] } } }) })).json();
    return { postId: m.message && m.message.id, challengeId: c.challenge_id };
  }, [img('a.png'), img('b.png')]);
}

run(async browser => {
  let seeded = null;
  const { ctx, page } = await phone(browser, 'linxia', false);
  await openBoard(page);
  await step('seed', async () => { seeded = await seed(page); ok(!!(seeded && seeded.postId && seeded.challengeId), 'seeded a phone test post with images + challenge'); });
  const post = () => `.mb-post[data-post-id="${seeded.postId}"]`;

  await step('main', async () => {
    await openBoard(page);
    await shot(page, '40-phone-main');
    await noOverflow(page, 'main');
    const tops = await page.evaluate(() => ['#pendingCard', '#recentCard', '#composer', '#postsList', '#howtoCard'].map(s => { const n = document.querySelector(s); return n && !n.hidden && getComputedStyle(n).display !== 'none' ? Math.round(n.getBoundingClientRect().top) : null; }));
    ok(tops[1] !== null && tops[2] !== null && (tops[0] === null || tops[0] < tops[1]) && tops[1] < tops[2] && tops[2] < tops[3], `order 等你完成 → 最近的挑战 → 发帖框 → 帖子 (${JSON.stringify(tops)})`);
    ok(tops[4] === null, '算分说明 card not in the phone feed (moved into the ranking sheet)');
    const strip = await box(page, '#recentCard .mb-recent-strip');
    ok(strip && strip.visible && strip.height >= 44 && strip.height <= 76, `最近的挑战 is one tappable row (${strip && Math.round(strip.height)}px)`);
    const tools = await page.$$eval('.mb-composer__row .ui-btn', els => els.map(e => { const r = e.getBoundingClientRect(); return { t: e.textContent.trim(), top: Math.round(r.top), h: r.height }; }));
    ok(tools.length === 4 && tools.every(t => t.top === tools[0].top && t.h >= 44), `录音 / 文章 / 图片 / 挑战 on one row, ≥44px (${JSON.stringify(tools)})`);
    const lede = await seen(page, '.mb-head__lede');
    ok(!lede, 'header lede hidden on phones');
  });

  await step('composer', async () => {
    await page.tap('.mb-composer__fake');
    await wait(page);
    const c = await box(page, '#composer');
    ok(c && c.top <= 0.5 && c.height >= H - 1, `composer opens full screen (${c && Math.round(c.top)} / ${c && Math.round(c.height)})`);
    const pub = await box(page, '#composer .mb-composer__send .ui-btn--primary');
    ok(pub && pub.top < 80 && pub.height >= 40, `发布 in the top bar (${pub && Math.round(pub.top)})`);
    const fsz = await page.$eval('#composer textarea', e => parseFloat(getComputedStyle(e).fontSize));
    ok(fsz >= 16, `composer text ≥ 16px (${fsz})`);
    await shot(page, '41-phone-composer');
    await page.keyboard.type('手机上写了一半');
    await page.setViewportSize({ width: W, height: KB_H });
    await wait(page);
    const pub2 = await box(page, '#composer .mb-composer__send .ui-btn--primary');
    const tb = await box(page, '#composer .mb-composer__body .mb-tools');
    const ta = await box(page, '#composer textarea');
    ok(pub2 && pub2.top >= 0 && pub2.bottom <= KB_H && tb && tb.bottom <= KB_H + 1 && ta && ta.top < KB_H, 'keyboard open: 发布, the text box and the tool row are all on screen');
    await shot(page, '42-phone-composer-keyboard');
    await page.setViewportSize(DEVICE.viewport);
    await wait(page);
    await back(page);
    ok(await seen(page, '.ui-dialog[role=alertdialog]') && await seen(page, '#composer.is-open'), 'back on a draft asks 放弃这篇草稿？ first');
    await back(page);
    ok(!(await seen(page, '.ui-dialog[role=alertdialog]')) && await seen(page, '#composer.is-open'), 'back again closes the question, draft kept');
    await page.tap('#composer .mb-composer__send .ui-btn:not(.ui-btn--primary)');
    await wait(page);
    await page.tap('.ui-dialog[role=alertdialog] button:has-text("放弃")');
    await wait(page, 700);
    ok(!(await seen(page, '#composer.is-open')), '取消 → 放弃 closes the composer');
    await back(page);
    ok(!page.url().includes('/message_board'), 'no history left behind by the composer layers');
    await openBoard(page);
  });

  await step('pickers', async () => {
    await page.tap('.mb-composer__row .ui-btn:has-text("录音")');
    await page.waitForSelector('.ui-dialog .mb-topic');
    await wait(page);
    await noOverflow(page, 'audio picker');
    await shot(page, '43-phone-audio-picker');
    const cats = await page.$$eval('.ui-dialog .mb-picker__rail .ui-rail__item', els => els.map(e => { const r = e.getBoundingClientRect(); return { top: Math.round(r.top), h: r.height }; }));
    ok(cats.length === 4 && cats.every(c => c.top === cats[0].top && c.h >= 40), 'audio categories in one row, ≥ 40px');
    await page.locator('.ui-dialog .mb-pick button:has-text("加入")').first().tap();
    const done = await box(page, '.ui-dialog .ui-dialog__foot .ui-btn--primary');
    ok(done && done.height >= 44 && done.width >= W - 40, '完成 is a full-width 44px button');
    await page.tap('.ui-dialog button:has-text("完成")');
    await wait(page, 600);
    ok(await page.locator('#composer .mb-composer__atts .mb-att').count() === 1 && await seen(page, '#composer.is-open'), 'picked recording shows in the full-screen composer');
    await page.tap('#composer .mb-composer__body .mb-tools .ui-btn:has-text("文章")');
    await page.waitForSelector('.ui-dialog .mb-pick');
    await wait(page);
    const names = await page.$$eval('.ui-dialog .mb-picker__rail .ui-rail__name', els => els.map(e => e.textContent));
    ok(JSON.stringify(names) === '["阅读","听力","写作"]', `article categories in Chinese (${names})`);
    await back(page);
    ok(!(await seen(page, '.ui-dialog')) && await seen(page, '#composer.is-open'), 'back closes the picker, composer stays');
  });

  await step('challenge', async () => {
    await page.tap('#composer .mb-composer__body .mb-tools .ui-btn:has-text("挑战")');
    await page.waitForSelector('.ui-dialog .mb-check');
    await wait(page);
    await noOverflow(page, 'challenge sheet');
    await shot(page, '44-phone-challenge');
    const list = await page.$eval('.ui-dialog .mb-checklist', e => ({ sh: e.scrollHeight, ch: e.clientHeight }));
    ok(list.sh <= list.ch + 1, `article list does not scroll inside the sheet (${list.sh}/${list.ch})`);
    const people = await box(page, '.ui-dialog .mb-people');
    const arts = await box(page, '.ui-dialog .mb-checklist');
    ok(people && arts && people.top < arts.top, '@ 邀请同伴 comes before the long article list');
    const rows = await page.$$eval('.ui-dialog .mb-check', els => els.map(e => e.getBoundingClientRect().height));
    ok(rows.length && rows.every(h => h >= 44), 'article rows ≥ 44px');
    const chips = await page.$$eval('.ui-dialog .mb-people .ui-chip', els => els.map(e => e.getBoundingClientRect().height));
    ok(chips.length && chips.every(h => h >= 44), 'invite chips ≥ 44px');
    const create = await box(page, '.ui-dialog .ui-dialog__foot .ui-btn--primary');
    ok(create && create.bottom <= H && create.height >= 44, '创建挑战 visible at the bottom');
    await page.setViewportSize({ width: W, height: KB_H });
    await page.tap('.ui-dialog .mb-f-title input');
    await wait(page);
    const create2 = await box(page, '.ui-dialog .ui-dialog__foot .ui-btn--primary');
    const input = await box(page, '.ui-dialog .mb-f-title input');
    ok(create2 && create2.bottom <= KB_H && input && input.top >= 0 && input.bottom <= create2.top, 'keyboard open: name field and 创建挑战 on screen');
    await page.setViewportSize(DEVICE.viewport);
    await back(page);
    ok(!(await seen(page, '.ui-dialog')) && await seen(page, '#composer.is-open'), 'back closes the challenge sheet, composer stays');
    // 真建一个：提示条「挑战已创建」浮在发帖面板的工具条上面，不挡发布
    await page.tap('#composer .mb-composer__body .mb-tools .ui-btn:has-text("挑战")');
    await page.waitForSelector('.ui-dialog .mb-check');
    await page.fill('.ui-dialog .mb-f-title input', '手机上建的挑战');
    await page.locator('.ui-dialog .mb-check').first().tap();
    await page.tap('.ui-dialog .ui-dialog__foot .ui-btn--primary');
    await page.waitForSelector('#composer .mb-composer__atts .mb-ch');
    await wait(page, 300);
    const t = await toastCovers(page, '#composer .mb-composer__body .mb-tools .ui-btn, #composer .mb-composer__send .ui-btn');
    ok(t.toasts > 0 && !t.hit, 'toast floats above the composer tool row, 发布 not covered');
    await shot(page, '44b-phone-composer-challenge');
  });

  await step('publish', async () => {
    await page.fill('#composer textarea', '手机上发的一条测试帖');
    await page.tap('#composer .mb-composer__send .ui-btn--primary');
    await page.waitForFunction(() => document.querySelector('#postsList .mb-post .mb-post__text')?.textContent.includes('手机上发的'));
    await wait(page, 300);
    ok(!(await seen(page, '#composer.is-open')), 'published from the top bar, composer closed');
    const t = await toastCovers(page, '.mb-composer__row .ui-btn, .mb-composer__fake');
    ok(t.toasts > 0 && !t.hit, 'toast does not cover the composer');
  });

  await step('reply', async () => {
    const p = page.locator(post());
    await p.scrollIntoViewIfNeeded();
    await p.locator('.mb-post__foot .ui-btn').tap();
    await wait(page, 500);
    const bar = await box(page, `${post()} .mb-reply`);
    ok(bar && Math.abs(bar.bottom - H) <= 1 && bar.left <= 0 && bar.right >= W - 1, 'reply bar pinned to the bottom');
    const send = await box(page, `${post()} .mb-reply .ui-btn--primary`);
    ok(send && send.height >= 44, '发表 ≥ 44px');
    const tools = await page.$$eval(`${post()} .mb-reply .mb-tools .ui-btn`, els => els.map(e => { const r = e.getBoundingClientRect(); return [r.width, r.height]; }));
    ok(tools.length === 4 && tools.every(([w, h]) => w >= 44 && h >= 44), 'reply attachment icons ≥ 44×44');
    ok((await page.textContent(`${post()} .mb-reply__head`)).includes('回复 林夏'), 'reply bar says who you reply to');
    const foot = await box(page, `${post()} .mb-post__foot`);
    ok(foot && foot.bottom <= bar.top, 'the post being replied to stays visible above the bar');
    await shot(page, '45-phone-reply');
    await page.setViewportSize({ width: W, height: KB_H });
    await page.tap(`${post()} .mb-reply textarea`);
    await page.keyboard.type('手机上的评论');
    await wait(page);
    const send2 = await box(page, `${post()} .mb-reply .ui-btn--primary`);
    const ta = await box(page, `${post()} .mb-reply textarea`);
    ok(send2 && send2.bottom <= KB_H && ta && ta.top >= 0, 'keyboard open: the reply box and 发表 on screen');
    await shot(page, '46-phone-reply-keyboard');
    await page.setViewportSize(DEVICE.viewport);
    await page.tap(`${post()} .mb-reply .ui-btn--primary`);
    await page.waitForFunction(s => document.querySelector(s + ' .mb-comment .mb-comment__text')?.textContent === '手机上的评论', post());
    await wait(page, 300);
    ok(!(await seen(page, `${post()} .mb-reply`)), 'comment sent, reply bar closed');
    // 以前提示条正好盖在刚发的评论的删除 × 上；现在只留最新一条提示，也不盖刚发的评论的 ⋯
    const visibleToasts = await page.$$eval('.ielts-toast', els => els.filter(e => e.getBoundingClientRect().width > 0).length);
    ok(visibleToasts === 1, `only the newest toast is shown (${visibleToasts})`);
    const t = await toastCovers(page, `${post()} .mb-comment .mb-more`);
    ok(t.toasts > 0 && !t.hit, `toast does not cover the new comment's ⋯ ${JSON.stringify(t)}`);
    // 返回键收起回复条（空的直接收）
    await p.locator('.mb-post__foot .ui-btn').tap();
    await wait(page);
    await back(page);
    ok(!(await seen(page, `${post()} .mb-reply`)) && page.url().includes('/message_board'), 'back closes an empty reply bar, page stays');
  });

  await step('delete comment', async () => {
    const c = page.locator(`${post()} .mb-comment`).first();
    ok(!(await c.locator('.mb-comment__del').isVisible()), 'no bare × on comments');
    const more = await c.locator('.mb-more').boundingBox();
    ok(more && more.width >= 44 && more.height >= 44, 'comment ⋯ ≥ 44×44');
    await c.locator('.mb-more').tap();
    await wait(page);
    await shot(page, '47-phone-comment-menu');
    await page.tap('.ui-dialog .mb-acts__btn:has-text("删除评论")');
    await wait(page, 600);
    ok(await seen(page, '.ui-dialog[role=alertdialog]'), '删除评论 asks for confirmation');
    await page.tap('.ui-dialog[role=alertdialog] button:has-text("删除")');
    await page.waitForFunction(s => !document.querySelector(s + ' .mb-comment'), post());
    ok(true, 'comment deleted through ⋯ → 删除评论 → 删除');
  });

  await step('lightbox', async () => {
    await page.locator(`${post()} .mb-images__btn`).first().tap();
    await page.waitForSelector('.mb-lightbox');
    await wait(page);
    const close = await box(page, '.mb-lightbox__close');
    ok(close && close.width >= 44 && close.height >= 44 && close.top < 80, 'lightbox close ≥ 44px, top-right');
    const cnt = await page.textContent('.mb-lightbox__count');
    ok(cnt.startsWith('1 / 2') && !/Esc|←/.test(cnt), `counter without keyboard hints (${cnt})`);
    await shot(page, '48-phone-lightbox');
    await swipe(page, '.mb-lightbox__img', -120);
    await wait(page, 200);
    ok((await page.textContent('.mb-lightbox__count')).startsWith('2 / 2'), 'swipe left → next image');
    await swipe(page, '.mb-lightbox__img', 120);
    await wait(page, 200);
    ok((await page.textContent('.mb-lightbox__count')).startsWith('1 / 2'), 'swipe right → previous image');
    await back(page);
    ok(await page.locator('.mb-lightbox').count() === 0 && page.url().includes('/message_board'), 'back closes the lightbox, page stays');
  });

  await step('ranking', async () => {
    await page.evaluate(() => window.scrollTo(0, 0));
    await wait(page);
    await page.tap('#recentCard .mb-recent-strip');
    await page.waitForSelector('.ui-dialog .mb-ranklist');
    await wait(page, 500);
    const chTitle = (await page.textContent('.ui-dialog .mb-rank-info__title')).trim();
    await shot(page, '49-phone-ranking');
    const foot = await page.textContent('.ui-dialog .mb-howto');
    ok(foot.includes('满分 70') && foot.includes('题目从精读'), 'scoring rules are a footnote in the ranking sheet');
    const btns = await page.$$eval('.ui-dialog .ui-dialog__foot .ui-btn', els => els.map(e => ({ t: e.textContent.trim(), h: e.getBoundingClientRect().height })));
    ok(btns.map(b => b.t).join('|') === '去帖子|关闭' && btns.every(b => b.h >= 44), `ranking sheet has 去帖子 / 关闭 (${JSON.stringify(btns)})`);
    await page.tap('.ui-dialog .ui-dialog__foot .ui-btn:has-text("去帖子")');
    await wait(page, 1200);
    // 最近的挑战是最新挂出来的那个（可能是上面「发布」一步新建的），找标题对得上的挑战块
    const ch = await page.evaluate(t => {
      const b = [...document.querySelectorAll('.mb-post > .mb-post__atts .mb-ch')].find(n => n.querySelector('.mb-ch__title')?.textContent === t);
      if (!b) return null;
      const r = b.getBoundingClientRect();
      return { top: r.top, bottom: r.bottom };
    }, chTitle);
    ok(!(await seen(page, '.ui-dialog')) && ch && ch.top >= 0 && ch.top < H, `去帖子 closes the sheet and scrolls to that challenge (${chTitle} ${JSON.stringify(ch)})`);
  });

  await step('post menu', async () => {
    const p = page.locator(post());
    ok(!(await p.locator('.mb-post__head .mb-iconbtn--danger').isVisible()), 'trash icon replaced by ⋯ on phones');
    await p.locator('.mb-post__head .mb-more').tap();
    await wait(page);
    await page.tap('.ui-dialog .mb-acts__btn:has-text("删除帖子")');
    await wait(page, 600);
    ok(await seen(page, '.ui-dialog[role=alertdialog]'), '⋯ → 删除帖子 asks for confirmation');
    await shot(page, '50-phone-delete-confirm');
    await back(page);
    ok(!(await seen(page, '.ui-dialog')) && await p.count() === 1, 'back cancels, post kept');
  });

  await step('cue card', async () => {
    const att = page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-att').nth(1);
    if (!(await att.count())) { console.log('SKIP msg_fake_0001 not here'); return; }
    const d = await att.locator('.mb-att__desc').evaluate(e => ({ h: e.getBoundingClientRect().height, lh: parseFloat(getComputedStyle(e).lineHeight) }));
    ok(d.h <= d.lh * 3 + 2, `long cue card clamped to 3 lines (${Math.round(d.h)}px)`);
    await att.locator('.mb-desc-toggle').tap();
    const d2 = await att.locator('.mb-att__desc').evaluate(e => e.getBoundingClientRect().height);
    ok(d2 > d.h + 20, '展开题目 shows the whole cue card');
    const play = await att.locator('.mb-play').boundingBox();
    ok(play && play.width >= 44 && play.height >= 44, 'play button ≥ 44×44');
  });
  ok(!page._errors.length, `no page errors as 林夏 ${JSON.stringify(page._errors)}`);
  await ctx.close();

  // ---------- 周屿：被 @ 的人做题 ----------
  const z = await phone(browser, 'zhouyu', false);
  await step('quiz', async () => {
    await openBoard(z.page);
    const pg = z.page;
    const pend = await box(pg, '#pendingCard .mb-pending');
    const start = await box(pg, '#pendingCard .mb-pending .ui-btn');
    ok(pend && pend.top < 260 && pend.height >= 56 && start && start.height >= 44, 'pending challenge row near the top, 开始 ≥ 44px');
    await pg.tap('#pendingCard .mb-pending .ui-btn');
    await pg.waitForSelector('.mb-quiz .mb-opt');
    await wait(pg, 500);
    const q = await box(pg, '.ui-dialog.mb-quiz');
    ok(q && q.top <= 0.5 && q.height >= H - 1, 'quiz is full screen');
    const opts = await pg.$$eval('.mb-quiz .mb-opt', els => els.map(e => { const r = e.getBoundingClientRect(); return { top: r.top, h: r.height }; }));
    ok(opts.length >= 2 && opts.every(o => o.h >= 56 && o.top > H * 0.4), `options ≥ 56px in the lower half (${JSON.stringify(opts.map(o => Math.round(o.top)))})`);
    ok(!(await seen(pg, '.mb-opt__key')) && !(await pg.textContent('.mb-quiz__note')).includes('数字键'), 'no number-key badges or hints on phones');
    const quit = await box(pg, '.mb-quiz__head .ui-btn');
    ok(quit && quit.height >= 44, '退出 ≥ 44px');
    await shot(pg, '51-phone-quiz');
    await back(pg);
    ok(await seen(pg, '.ui-dialog[role=alertdialog]') && await seen(pg, '.mb-quiz'), 'back during the quiz asks 退出这次挑战？');
    await back(pg);
    ok(!(await seen(pg, '.ui-dialog[role=alertdialog]')) && await seen(pg, '.mb-quiz'), 'back again → 接着答');
    await pg.tap('.mb-quiz__head .ui-btn');
    await wait(pg);
    await pg.tap('.ui-dialog[role=alertdialog] button:has-text("退出")');
    await wait(pg, 600);
    ok(await pg.locator('.mb-quiz').count() === 0, '退出 → 退出 leaves the quiz');
    await back(pg);
    ok(!pg.url().includes('/message_board'), 'no history left behind by the quiz layers');
  });
  ok(!z.page._errors.length, `no page errors as 周屿 ${JSON.stringify(z.page._errors)}`);
  await z.ctx.close();

  // ---------- 暗色 ----------
  const d = await phone(browser, 'chenmo', true);
  await step('dark', async () => {
    await openBoard(d.page);
    ok((await d.page.evaluate(() => document.documentElement.dataset.theme)) === 'dark', 'dark theme applied');
    await noOverflow(d.page, 'dark main');
    await shot(d.page, '52-phone-dark');
    await d.page.tap('.mb-composer__fake');
    await wait(d.page);
    await noOverflow(d.page, 'dark composer');
    const bg = await d.page.$eval('#composer', e => getComputedStyle(e).backgroundColor);
    ok(bg !== 'rgb(255, 255, 255)', `dark composer surface (${bg})`);
    await shot(d.page, '53-phone-dark-composer');
  });
  ok(!d.page._errors.length, `no page errors in dark ${JSON.stringify(d.page._errors)}`);
  await d.ctx.close();
});

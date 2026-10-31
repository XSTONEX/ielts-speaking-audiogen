// 首页浏览器测试：Chromium + WebKit，亮/暗，四种宽度；有数据和新账号两个沙盒。
// 查：所有框的边线对齐、不横向溢出、控制台没报错、入口齐全且不放合集/Reading、
// 主题按钮、点待复习/继续上次/卡片能到对应页、换时区「几天前」照样对、没登录跳登录页。
// 环境变量见同目录 README.md。
const fs = require('fs');
const path = require('path');
const { chromium, webkit } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const FULL_URL = process.env.FULL_URL || 'http://localhost:5062';
const EMPTY_URL = process.env.EMPTY_URL || '';
const read = (file) => fs.readFileSync(file, 'utf8').trim();
const FULL_TOKEN = read(process.env.FULL_TOKEN_FILE || 'e2e_token.txt');
const EMPTY_TOKEN = EMPTY_URL ? read(process.env.EMPTY_TOKEN_FILE) : '';
const OUT_DIR = process.env.OUT_DIR || '';
const ENTRIES = ['/speaking', '/intensive', '/writing_practice', '/listening_review', '/vocabulary', '/study_techniques', '/message_board'];

let passed = 0;
const failures = [];
function check(label, ok, detail) {
  if (ok) passed++;
  else failures.push(label + (detail ? ' — ' + detail : ''));
}

async function openHome(browser, base, token, opts) {
  const ctx = await browser.newContext({ viewport: { width: opts.width || 1280, height: 900 }, colorScheme: opts.scheme || 'light', timezoneId: opts.tz });
  await ctx.addInitScript((t) => { localStorage.setItem('authToken', t); localStorage.setItem('ui-theme', 'system'); }, token);
  const page = await ctx.newPage();
  const errors = [];
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(base + '/');
  await page.waitForFunction(() => document.querySelector('.app-shell-nav') &&
    document.querySelector('[data-foot="speaking"]').textContent.trim().length > 1, null, { timeout: 10000 });
  await page.waitForTimeout(300); // 等主题过渡（0.2s）走完再量颜色
  return { ctx, page, errors };
}

// 量每个框的边线：宽屏三列时，同一列左右边、同一排上下边、同一排卡片底部细线都要在同一条线上
function measure(wide) {
  const q = (s) => document.querySelector(s);
  const boxes = {
    speaking: '.home-at-speaking', intensive: '.home-at-intensive', writing: '.home-at-writing', listening: '.home-at-listening',
    review: '.home-review', vocab: '.home-grid--more > a:nth-of-type(1)', tips: '.home-grid--more > a:nth-of-type(2)',
    board: '.home-grid--more > a:nth-of-type(3)', resume: '#homeResume',
  };
  const R = {}; const foot = {};
  for (const k in boxes) {
    const e = q(boxes[k]); const r = e && e.getBoundingClientRect();
    R[k] = r && r.height ? r : null;
    const f = e && e.querySelector('.home-foot:not([hidden])');
    if (f) foot[k] = f.getBoundingClientRect().top;
  }
  const bad = [];
  const same = (label, vals) => {
    vals = vals.filter((v) => v != null);
    if (vals.length < 2) return;
    const d = Math.max(...vals) - Math.min(...vals);
    if (d > 0.5) bad.push(label + ' 差 ' + d.toFixed(1) + 'px');
  };
  const g = (k, side) => (R[k] ? R[k][side] : null);
  if (wide) {
    same('第一列左边', ['resume', 'speaking', 'writing', 'vocab'].map((k) => g(k, 'left')));
    same('第一列右边', ['speaking', 'writing', 'vocab'].map((k) => g(k, 'right')));
    same('第二列左边', ['intensive', 'listening', 'tips'].map((k) => g(k, 'left')));
    same('第二列右边', ['intensive', 'listening', 'tips'].map((k) => g(k, 'right')));
    same('第三列左边', ['review', 'board'].map((k) => g(k, 'left')));
    same('第三列右边', ['resume', 'review', 'board'].map((k) => g(k, 'right')));
    same('第一排上边', ['speaking', 'intensive', 'review'].map((k) => g(k, 'top')));
    same('第一排下边', ['speaking', 'intensive'].map((k) => g(k, 'bottom')));
    same('第二排上边', ['writing', 'listening'].map((k) => g(k, 'top')));
    same('第二排下边', ['writing', 'listening', 'review'].map((k) => g(k, 'bottom')));
    same('第三排上下边', ['vocab', 'tips', 'board'].map((k) => g(k, 'top')));
    same('第三排下边', ['vocab', 'tips', 'board'].map((k) => g(k, 'bottom')));
    same('第一排细线', [foot.speaking, foot.intensive]);
    same('第二排细线', [foot.writing, foot.listening, foot.review]);
    same('第三排细线', [foot.vocab, foot.tips, foot.board]);
  }
  return {
    bad,
    overflowX: document.documentElement.scrollWidth > innerWidth + 1,
    feet: [...document.querySelectorAll('[data-foot]')].map((e) => e.textContent.trim()),
    week: q('#homeWeek').textContent.trim(),
    resume: !q('#homeResume').hidden,
    reviewRows: document.querySelectorAll('.home-review__row').length,
    reviewEmpty: !q('#reviewEmpty').hidden,
    themeBtn: !!q('.app-shell-theme'),
    entries: [...document.querySelectorAll('.home a[href]')].map((a) => a.getAttribute('href')),
    retired: !!q('a[href="/combined"], a[href="/reading"]'),
  };
}

async function layoutChecks(eng, browser) {
  const runs = [{ name: '有数据', base: FULL_URL, token: FULL_TOKEN, full: true }];
  if (EMPTY_URL) runs.push({ name: '新账号', base: EMPTY_URL, token: EMPTY_TOKEN, full: false });
  for (const run of runs) {
    for (const scheme of ['light', 'dark']) {
      for (const width of [1280, 1440, 900, 375]) {
        const tag = `${eng} ${run.name} ${scheme} ${width}`;
        const { ctx, page, errors } = await openHome(browser, run.base, run.token, { width, scheme });
        const r = await page.evaluate(measure, width > 1000);
        check(tag + ' 边线对齐', r.bad.length === 0, r.bad.join('；'));
        check(tag + ' 不横向溢出', !r.overflowX);
        check(tag + ' 控制台没报错', errors.length === 0, errors.join(' | ').slice(0, 300));
        check(tag + ' 有主题按钮', r.themeBtn);
        check(tag + ' 不放合集和 Reading 入口', !r.retired);
        check(tag + ' 七个模块入口都在', ENTRIES.every((h) => r.entries.includes(h)), r.entries.join(','));
        check(tag + ' 数据行都填上了', r.feet.every((t) => t && t !== '—'), r.feet.join(' / '));
        if (run.full) {
          check(tag + ' 有「继续上次」', r.resume);
          check(tag + ' 待复习列出 6 行', r.reviewRows === 6, String(r.reviewRows));
          check(tag + ' 本周一行有数字', /\d/.test(r.week), r.week);
        } else {
          check(tag + ' 新账号不显示「继续上次」', !r.resume);
          check(tag + ' 新账号待复习是空状态', r.reviewEmpty && r.reviewRows === 0);
        }
        if (OUT_DIR && (eng === 'chromium' || width === 1280)) {
          await page.screenshot({ path: path.join(OUT_DIR, `${eng}_${run.full ? 'full' : 'empty'}_${scheme}_${width}.png`), fullPage: true });
        }
        await ctx.close();
      }
    }
  }
}

async function clickChecks(eng, browser) {
  const { ctx, page } = await openHome(browser, FULL_URL, FULL_TOKEN, {});
  const bg = () => page.evaluate(() => [document.documentElement.dataset.theme, getComputedStyle(document.body).backgroundColor]);
  await page.click('.app-shell-theme');
  await page.waitForTimeout(400);
  const dark = await bg();
  check(eng + ' 主题按钮切到暗色', dark[0] === 'dark' && dark[1] === 'rgb(22, 22, 22)', dark.join(' '));
  await page.click('.app-shell-theme');
  await page.waitForTimeout(400);
  const light = await bg();
  check(eng + ' 再点切到亮色', light[0] === 'light' && light[1] === 'rgb(247, 247, 245)', light.join(' '));

  const rows = await page.$$eval('.home-review__row', (as) => as.map((a) => a.getAttribute('href')));
  check(eng + ' 单词行去词汇汇总', rows.includes('/vocab_summary'), rows.join(','));
  check(eng + ' 写作行去写作页', rows.includes('/writing_practice'), rows.join(','));
  const listen = rows.find((h) => h.startsWith('/listening_review?project='));
  check(eng + ' 听力行直接打开那一项', !!listen, rows.join(','));

  // 只看跳到了哪个网址：目标页 <head> 里有同步加载的 CDN 脚本，断网时等不到页面加载完
  const goes = async (selector, pathname) => {
    await Promise.all([
      page.waitForURL((u) => u.pathname === pathname, { waitUntil: 'commit', timeout: 10000 }).catch(() => {}),
      page.click(selector),
    ]);
    return new URL(page.url()).pathname === pathname;
  };
  check(eng + ' 「接着练」去写作页', await goes('#resumeGo', '/writing_practice'), page.url());
  await page.goto(FULL_URL + '/');
  await page.waitForSelector('#homeResume:not([hidden])');
  check(eng + ' 精读卡片去精读页', await goes('.home-at-intensive', '/intensive'), page.url());
  await ctx.close();

  // 浏览器在哪个时区，「继续上次」的时间都按它自己的钟显示，指的是同一个时刻
  for (const tz of ['Asia/Shanghai', 'America/Los_Angeles']) {
    const o = await openHome(browser, FULL_URL, FULL_TOKEN, { tz });
    const r = await o.page.evaluate(async () => {
      const data = await (await fetch('/api/home')).json();
      const at = new Date(data.resume.at.replace(/(\.\d{3})\d+/, '$1'));
      const d = at;
      const hm = String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      return { zoned: /[+-]\d\d:\d\d$/.test(data.resume.at), hm, shown: document.getElementById('resumeDetail').textContent };
    });
    check(`${eng} ${tz} 时间带时区`, r.zoned);
    check(`${eng} ${tz} 按本地钟显示`, r.shown.includes(r.hm) || /分钟前|刚刚|天前/.test(r.shown), r.shown + ' / ' + r.hm);
    await o.ctx.close();
  }

  const anon = await browser.newContext();
  const p = await anon.newPage();
  // 登录页 <head> 里有 Google 字体，断网时等不到 load，只等网址
  await p.goto(FULL_URL + '/', { waitUntil: 'commit' });
  await p.waitForURL('**/login', { waitUntil: 'commit', timeout: 10000 }).catch(() => {});
  check(eng + ' 没登录跳登录页', new URL(p.url()).pathname === '/login', p.url());
  await anon.close();
}

(async () => {
  if (OUT_DIR) fs.mkdirSync(OUT_DIR, { recursive: true });
  for (const [eng, engine] of [['chromium', chromium], ['webkit', webkit]]) {
    const browser = await engine.launch();
    await layoutChecks(eng, browser);
    await clickChecks(eng, browser);
    await browser.close();
  }
  console.log(`通过 ${passed} 项，失败 ${failures.length} 项`);
  failures.forEach((f) => console.log('  ✗ ' + f));
  process.exit(failures.length ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });

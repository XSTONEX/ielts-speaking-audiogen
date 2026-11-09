// 「错题标注」的浏览器检查（沙盒、编造数据）：
// 导入三份 JSON（填空 + 单选；地图 + 多选；版式里选字母的配对 + 填空）→ 页头三档（错题标注 | 显示答案 | 重做），打开就是错题标注 →
// 卷子 / 原文显示两种排法，不漏答案（正确答案、你填的、对错颜色、解析、出处、划线、字幕上的 Q 标签）→ 错的（含没答）框红、答对的不标 →
// 点框起来的题 / 红题号：音频跳到那题的出处句子开始放，原文不露出来 → 错题卡（错几题、那次答对、题号总览、做题记录、打卡 / 标熟）→
// 换一次记录就按那一次标 → 刷新、换篇回来还是错题标注；从笔记跳到某一句的开在显示答案 → 切回显示答案 / 重做都正常 →
// 抽屉宽度、暗色、390 手机。
// 用法见 README；每跑一次前先重灌 seed.py 和 jiufen_data.py。
const path = require('path');
const fs = require('fs');
const os = require('os');
const { execFileSync } = require('child_process');
const pw = require(process.env.PLAYWRIGHT_CORE);
const engine = process.argv[2] || 'chromium';
const sb = process.env.LR_SANDBOX;
const fake = path.join(__dirname, 'jiufen_fake_translate.py');
const BASE = (process.env.LR_BASE_URL || 'http://localhost:5073').replace(/\/$/, '');
const OUT = process.env.LR_OUT_DIR || path.join(os.tmpdir(), 'listening-e2e');
fs.mkdirSync(OUT, { recursive: true });
const token = JSON.parse(fs.readFileSync(`${sb}/e2e_tokens.json`, 'utf8')).demo;
let pass = 0, fail = 0;
const check = (name, ok, got) => { ok ? pass++ : fail++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + JSON.stringify(got)}`); };
const shot = async (page, name) => { await page.waitForTimeout(300); await page.screenshot({ path: path.join(OUT, `flag-${engine}-${name}.png`), fullPage: true }); };
// 一段出错只记一项失败，接着跑下一段
async function section(name, fn) {
  try { await fn(); } catch (e) { check(`${name} (section crashed)`, false, String(e && e.message || e).split('\n')[0]); }
}

async function login(ctx) {
  await ctx.addInitScript(t => { if (location.protocol === 'about:') return; localStorage.setItem('authToken', t); }, token);
}

async function openByTitle(page, re) {
  await page.evaluate(async (src) => {
    if (state.view === 'detail') backToList();
    await loadProjects();
    const p = state.projects.find(p => new RegExp(src).test(p.title));
    await openProject(p.id);
  }, re.source);
  await page.waitForFunction(() => state.view === 'detail' && !!state.exam);
}

// 页面上任何地方露出答案的东西
const LEAKS = '.lr-qtag, .lr-ans, .lr-evi, .lr-hl, .lr-qx, .is-review, .lq-gap.is-ok, .lq-gap.is-err, .lq-gap.is-none, .lq-gap__val, .lq-gap__you, .lq-gap__right, .lq-opt.is-right, .lq-opt.is-wrong, .lq-opt.is-miss, .lq-opt.is-on, .lq-cell.is-right, .lq-cell.is-wrong, .lq-cell.is-on, .lq-slot.is-ok, .lq-slot.is-err, .lq-slot.is-none, .lq-slot__k, .lq-tray, .lq-n.is-ok, .lq-n.is-err, .lr-qnum.is-err, .lr-qnum.is-blank, #questionsPane input, #paperQs input, [data-act="q-play"]';

// 点了一道错题以后：音频到哪了、这题的出处从几秒开始、原文露没露出来
function listenInfo(num) {
  const it = examQuestions().find(x => x.q.num === num);
  const segs = it ? evidenceSegs(it.q) : [];
  const el = document.querySelector(`[data-listen="${num}"].is-on`);
  return {
    t: Math.round(audioEl.currentTime * 100) / 100, want: segs.length ? Math.min(...segs.map(s => s.start)) : null, paused: audioEl.paused,
    on: state.flagOn, ring: !!el && getComputedStyle(el.matches('tr') ? el.querySelector('td') : el).boxShadow !== 'none',
    mode: state.mode, showScript: state.showScript, lyricsHidden: document.getElementById('lyricsContainer').hidden,
    paper: !document.getElementById('paperPane').hidden, qx: document.querySelectorAll('.lr-qx').length, selQ: state.selQ, ptab: state.ptab,
  };
}
const jumped = l => l.want !== null && l.t >= l.want - 0.05 && l.t < l.want + 2.5;
// 停下来、拨到一个不是任何出处的地方，好看下一次点有没有跳
async function parkAudio(page) {
  await page.evaluate(() => { audioEl.pause(); audioEl.currentTime = 1; });
  await page.waitForTimeout(150);
}

// 卷子 / 右栏里看得到的：哪些题框红、哪些没框
function readFlags([hostSel, LEAKS]) {
  const host = document.querySelector(hostSel);
  const nums = el => el.dataset.nums;
  return {
    gaps: [...host.querySelectorAll('.lq-gap')].map(g => nums(g) + (g.classList.contains('is-flag') ? '!' : '')).join(' '),
    qs: [...host.querySelectorAll('.lq-q')].map(q => nums(q) + (q.classList.contains('is-flag') ? '!' : '')).join(' '),
    rows: [...host.querySelectorAll('.lq-grid tr[data-nums]')].map(r => nums(r) + (r.classList.contains('is-flag') ? '!' : '')).join(' '),
    slots: [...host.querySelectorAll('.lq-slot')].map(s => nums(s) + (s.classList.contains('is-flag') ? '!' : '')).join(' '),
    redChips: [...host.querySelectorAll('.lq-n.is-flag')].map(n => n.textContent).join(','),
    leaks: document.querySelectorAll(LEAKS).length,
    leakList: [...document.querySelectorAll(LEAKS)].slice(0, 5).map(e => e.className || e.tagName),
    text: host.innerText,
    explain: /解析|干扰|出处|正确答案|你的答案|你选|没答/.test((host.querySelector('.lr-qs') || host).innerText),
  };
}

(async () => {
  const browser = await pw[engine].launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await login(ctx);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/listening_review`);
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  await page.evaluate(() => { localStorage.removeItem('listening-redo-script'); localStorage.setItem('ui-theme', 'light'); });

  // ---------- 导入三份 JSON，补上编的译文 ----------
  for (const file of ['e2e_single.json', 'e2e_map.json', 'e2e_mixed.json']) {
    await page.evaluate(async (file) => {
      openUploadModal(); switchTab('json');
      const text = await (await fetch('/static/e2e/' + file)).text();
      const dt = new DataTransfer(); dt.setData('text/plain', text);
      document.getElementById('jsonPaste').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
    }, file);
    await page.waitForFunction(() => !document.getElementById('uploadJsonBtn').disabled, null, { timeout: 5000 });
    await page.click('#uploadJsonBtn');
    await page.waitForFunction(() => document.getElementById('uploadModal').hidden, null, { timeout: 5000 });
  }
  await page.waitForFunction(() => state.projects.filter(p => p.source_type === 'jiufen' && p.status === 'error' && p.error_phase === 'polish').length === 4, null, { timeout: 30000 });
  execFileSync('python3', [fake, sb]);

  // ---------- 1. 填空 + 单选（九分那次：3 错、4 没答）：原文隐藏的卷子 ----------
  await section('paper', async () => {
    await openByTitle(page, /Riverside Bike Hire/);
    const seg = await page.evaluate(() => [...document.querySelectorAll('#modeSeg .mode-btn')].map(b => b.dataset.mode + ':' + b.textContent.trim()).join(' '));
    check('header switch: 错题标注 first, left of 显示答案', seg === 'flag:错题标注 answers:显示答案 redo:重做', seg);
    // 不点任何按钮：打开就是这一档
    const p0 = await page.evaluate(() => ({
      on: document.querySelector('.mode-btn.is-on').dataset.mode,
      pressed: document.querySelector('.mode-btn[data-mode="flag"]').getAttribute('aria-pressed'),
      lyrics: document.getElementById('lyricsContainer').hidden,
      paper: !document.getElementById('paperPane').hidden,
      flagCard: !document.getElementById('flagCard').hidden,
      info: document.getElementById('sideInfoCard').hidden,
      redoCard: document.getElementById('redoCard').hidden,
      main: document.getElementById('sideMainCard').hidden,
      trans: document.getElementById('toggleTransBtn').hidden,
      script: !document.getElementById('scriptBtn').hidden && document.getElementById('scriptBtn').getAttribute('aria-pressed') === 'false',
      grid: document.getElementById('detailGrid').className,
    }));
    check('opens on 错题标注: transcript hidden, paper on the left, 错题标注 card on the right', p0.on === 'flag' && p0.pressed === 'true' && p0.lyrics && p0.paper && p0.flagCard && p0.info && p0.redoCard && p0.main && p0.trans && p0.script && /is-flag/.test(p0.grid) && /is-paper/.test(p0.grid) && !/is-redo/.test(p0.grid), p0);
    const f = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    check('no answers, your answers, colours or explanations anywhere', f.leaks === 0 && !f.explain, { leaks: f.leakList, explain: f.explain });
    check('answer words and your old answers are not on the paper', !/\b(twelve|passport|mill|hill|seven)\b/i.test(f.text) && !/\b12\b/.test(f.text.replace(/Questions? \d+[–-]\d+/g, '')), f.text.slice(0, 300));
    check('wrong (3) and blank (4) blanks framed red, 1 and 2 plain', f.gaps === '1 2 3! 4!' && f.redChips === '3,4', f);
    check('the right choice question (5) is not framed, its options are plain cards', f.qs === '5' && await page.evaluate(() => document.querySelectorAll('#paperQs .lq-opts.is-look .lq-opt').length === 3 && !document.querySelector('#paperQs button.lq-opt')), f.qs);
    const st = await page.evaluate(() => {
      const g = document.querySelector('#paperQs .lq-gap.is-flag'), n = g.querySelector('.lq-n'), plain = document.querySelector('#paperQs .lq-gap:not(.is-flag) .lq-n');
      const cs = getComputedStyle(g);
      return { bw: cs.borderTopWidth, bc: cs.borderTopColor, red: getComputedStyle(n).backgroundColor, plain: getComputedStyle(plain).backgroundColor, bg: cs.backgroundColor, sr: g.querySelector('.lr-sr') && g.querySelector('.lr-sr').textContent, empty: g.querySelector('.lq-gap__sp').textContent === '' };
    });
    // 1.5px 的框在 1 倍屏上 Chrome 画成 1px，视网膜屏上是 1.5px
    check('framed blank: red border, red number chip, empty line, screen-reader note', parseFloat(st.bw) >= 1 && st.bc === st.red && st.red !== st.plain && st.bg !== 'rgba(0, 0, 0, 0)' && st.sr === '（上次错了，按一下从原文这里开始听）' && st.empty, st);
    const la = await page.evaluate(() => {
      const g = document.querySelector('#paperQs .lq-gap.is-flag'), plain = document.querySelector('#paperQs .lq-gap:not(.is-flag)');
      const note = document.getElementById('flagNote');
      return { listen: g.dataset.listen, role: g.getAttribute('role'), tab: g.tabIndex, icon: !!g.querySelector('.lq-listen'), cursor: getComputedStyle(g).cursor,
        plain: plain.hasAttribute('data-listen') || !!plain.querySelector('.lq-listen'), plainCursor: getComputedStyle(plain).cursor, note: !note.hidden && note.textContent };
    });
    check('framed blanks have a play mark, pointer and keyboard focus; plain ones are not clickable', la.listen === '3' && la.role === 'button' && la.tab === 0 && la.icon && la.cursor === 'pointer' && !la.plain && la.plainCursor === 'default', la);
    check('card note: tap a framed question or red number to hear it, transcript stays hidden', /点红框里的题或红题号/.test(la.note || '') && /原文还是藏着/.test(la.note || ''), la.note);
    const c0 = await page.evaluate(() => ({
      nth: document.getElementById('flagNth').textContent,
      count: document.getElementById('flagCount').textContent,
      countRed: document.getElementById('flagCount').classList.contains('is-err'),
      score: document.getElementById('flagScore').textContent,
      map: [...document.querySelectorAll('#flagMap .lr-qnum')].map(b => b.textContent + (b.classList.contains('is-flag') ? '!' : '')).join(' '),
      mapShown: !document.getElementById('flagMap').hidden,
      btns: !!document.querySelector('#flagCard #checkinBtn') && !!document.querySelector('#flagCard #masteredBtn'),
      bar: document.getElementById('paperFlag').innerText,
      jump: getComputedStyle(document.getElementById('paperJump')).display,
      redoBits: ['.lr-paper__msg', '#paperProg', '.lr-paper__submit'].map(s => getComputedStyle(document.querySelector(s)).display).join(','),
    }));
    check('card: 按第 1 次, 2 wrong (red), that attempt 3/5, map marks 3 and 4', c0.nth === '按第 1 次' && c0.count === '2' && c0.countRed && c0.score === '3/5' && c0.map === '1 2 3! 4! 5' && c0.mapShown, c0);
    check('打卡 / 标熟 moved into the card', c0.btns, c0);
    check('paper bar says which attempt and how many, and that a tap plays it; no submit / progress', /原文已隐藏/.test(c0.bar) && /红框是第 1 次/.test(c0.bar) && /错的 2 题/.test(c0.bar) && /点一下从原文那里听/.test(c0.bar) && c0.redoBits === 'none,none,none' && c0.jump === 'none', c0);
    // 点框红的 3：音频跳到 3 的出处开始放，原文还藏着，什么解析都不展开
    await parkAudio(page);
    await page.click('#paperQs .lq-gap.is-flag[data-nums="3"]');
    await page.waitForTimeout(500);
    const l3 = await page.evaluate(listenInfo, '3');
    check('tapping framed 3: audio jumps to its source sentence and plays', jumped(l3) && !l3.paused, l3);
    check('…the transcript stays hidden and nothing opens', l3.mode === 'flag' && !l3.showScript && l3.lyricsHidden && l3.paper && l3.qx === 0 && l3.selQ === null, l3);
    check('…and that question gets the darker ring', l3.on === '3' && l3.ring, l3);
    await shot(page, 'listen');
    // 点那一行的字（不是空格本身）也算点了这题
    await parkAudio(page);
    await page.click('#paperQs .lr-qs__content li:has(.lq-gap[data-nums="4"])', { position: { x: 30, y: 12 } });
    await page.waitForTimeout(400);
    const l4 = await page.evaluate(listenInfo, '4');
    check('tapping the words next to blank 4 plays 4 from its source', jumped(l4) && l4.on === '4' && l3.want !== l4.want, l4);
    // 答对的 5 点了不跳
    await parkAudio(page);
    await page.click('#paperQs .lq-q__stem');
    await page.waitForTimeout(300);
    const l5 = await page.evaluate(listenInfo, '5');
    check('tapping a question you got right does nothing', l5.t === 1 && l5.paused && l5.on === '4' && l5.qx === 0 && l5.selQ === null, l5);
    // 键盘：Tab 到框红的空格按回车
    await parkAudio(page);
    await page.focus('#paperQs .lq-gap.is-flag[data-nums="3"]');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(400);
    const k3 = await page.evaluate(listenInfo, '3');
    check('keyboard: Enter on a framed blank plays it', jumped(k3) && k3.on === '3' && !k3.paused, k3);
    // 焦点还停在这道题上（鼠标点过也一样），空格要照样是暂停，不是又跳回这题开头
    await page.waitForTimeout(600);
    const before = await page.evaluate(() => audioEl.currentTime);
    await page.keyboard.press('Space');
    await page.waitForTimeout(300);
    const sp = await page.evaluate(() => ({ paused: audioEl.paused, t: audioEl.currentTime, focus: document.activeElement.dataset.listen }));
    check('Space with the focus on a framed question still pauses, no jump back', sp.focus === '3' && sp.paused && sp.t >= before - 0.05, { before, sp });
    // 卡上点红题号：跳到那题、闪一下，也从原文那里听；点不红的只跳
    await parkAudio(page);
    await page.click('#flagMap .lr-qnum[data-q="4"]');
    await page.waitForTimeout(400);
    const j0 = await page.evaluate(() => (document.querySelector('#paperQs .is-jump') || {}).dataset);
    const m4 = await page.evaluate(listenInfo, '4');
    check('red number in the card: jumps to that question and plays its source', j0 && j0.nums === '4' && jumped(m4) && m4.lyricsHidden, { j0, m4 });
    await parkAudio(page);
    await page.click('#flagMap .lr-qnum[data-q="1"]');
    await page.waitForTimeout(300);
    const m1 = await page.evaluate(listenInfo, '1');
    check('plain number in the card only scrolls, no audio jump', m1.t === 1 && m1.paused, m1);
    await shot(page, 'paper');
  });

  // ---------- 2. 换到显示答案、刷新、换篇回来还是错题标注；笔记跳过来的开在显示答案；显示原文 ----------
  await section('default + transcript', async () => {
    await page.click('.mode-btn[data-mode="answers"]');
    await page.reload();
    await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
    await openByTitle(page, /Riverside Bike Hire/);
    const r0 = await page.evaluate(() => ({ mode: state.mode, paper: !document.getElementById('paperPane').hidden, on: document.querySelector('.mode-btn.is-on').dataset.mode }));
    check('after using 显示答案 and reloading, the article opens on 错题标注 again', r0.mode === 'flag' && r0.paper && r0.on === 'flag', r0);
    // 从笔记本 / 生词本点「原句」过来（?project=…&seg=…）：要看那一句，开在显示答案
    const pid = await page.evaluate(() => state.currentProject.id);
    await page.goto(`${BASE}/listening_review?project=${encodeURIComponent(pid)}&seg=3`);
    await page.waitForFunction(() => typeof state !== 'undefined' && state.view === 'detail' && !!state.exam);
    await page.waitForTimeout(300);
    const dl = await page.evaluate(() => ({ mode: state.mode, active: (document.querySelector('#lyricsContainer .lr-line.is-active') || {}).dataset, shown: !document.getElementById('lyricsContainer').hidden }));
    check('a deep link to one sentence (from the notebook) opens on 显示答案 with that line', dl.mode === 'answers' && dl.shown && dl.active && dl.active.segId === '3', dl);
    await page.goto(`${BASE}/listening_review`);
    await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
    await openByTitle(page, /Riverside Bike Hire/);
    await page.click('#scriptBtn');
    const s0 = await page.evaluate(() => ({
      lyrics: !document.getElementById('lyricsContainer').hidden,
      lines: document.querySelectorAll('#lyricsContainer .lr-line').length,
      end: document.querySelectorAll('#lyricsContainer .lr-endcard').length,
      paper: document.getElementById('paperPane').hidden,
      main: !document.getElementById('sideMainCard').hidden,
      trans: !document.getElementById('toggleTransBtn').hidden,
      mapHidden: document.getElementById('flagMap').hidden,
      pane: [...document.querySelectorAll('#questionsPane .lr-qmap .lr-qnum')].map(b => b.textContent + (b.classList.contains('is-flag') ? '!' : '')).join(' '),
      legend: (document.querySelector('#questionsPane .lr-qs__legend') || {}).innerText,
    }));
    const f = await page.evaluate(readFlags, ['#questionsPane', LEAKS]);
    check('show transcript: lines back, clean, questions move to the side', s0.lyrics && s0.lines === 10 && s0.end === 1 && s0.paper && s0.main && s0.trans && s0.mapHidden, s0);
    check('side questions: map + legend + the same red frames, still no leaks', s0.pane === '1 2 3! 4! 5' && /第 1 次错的题（没答的也算），点一下从原文那里听/.test(s0.legend || '') && f.gaps === '1 2 3! 4!' && f.leaks === 0 && !f.explain, { s0, f: { gaps: f.gaps, leaks: f.leakList } });
    await parkAudio(page);
    await page.click('#questionsPane .lr-qmap .lr-qnum[data-q="3"]');
    await page.waitForTimeout(400);
    const j = await page.evaluate(() => (document.querySelector('#questionsPane .is-jump') || {}).dataset);
    const sl = await page.evaluate(listenInfo, '3');
    check('clicking a red number in the side list jumps there and plays its source', j && j.nums === '3' && jumped(sl), { j, sl });
    await parkAudio(page);
    await page.click('#questionsPane .lq-gap.is-flag[data-nums="4"]');
    await page.waitForTimeout(400);
    const s4 = await page.evaluate(listenInfo, '4');
    check('framed blank in the side list plays too', jumped(s4) && s4.on === '4', s4);
    await page.evaluate(() => audioEl.pause());
    await shot(page, 'shown');
    await page.click('#scriptBtn');   // 关回卷子，后面都看卷子
  });

  // ---------- 3. 切回显示答案 / 重做都正常，再回来 ----------
  await section('switching', async () => {
    await page.click('.mode-btn[data-mode="answers"]');
    const a = await page.evaluate(() => ({
      tags: document.querySelectorAll('.lr-qtag').length,
      info: !document.getElementById('sideInfoCard').hidden, flag: document.getElementById('flagCard').hidden,
      btnsHome: !!document.querySelector('#sideInfoCard #checkinBtn'),
      listen: document.querySelectorAll('[data-listen]').length,
      gaps: [...document.querySelectorAll('#questionsPane .lq-gap')].map(g => g.className.replace('lq-gap', '').trim()).join(','),
    }));
    check('back to 显示答案: tags, 本篇 card and its buttons back, nothing tap-to-listen left', a.tags === 5 && a.info && a.flag && a.btnsHome && a.listen === 0 && a.gaps === 'is-ok,is-ok,is-err,is-none', a);
    await page.click('.mode-btn[data-mode="flag"]');
    await page.click('.mode-btn[data-mode="redo"]');
    const r = await page.evaluate(() => ({ card: !document.getElementById('redoCard').hidden, flag: document.getElementById('flagCard').hidden, inputs: document.querySelectorAll('#paperQs .lq-gap__in').length, look: document.querySelectorAll('.is-look, [data-listen]').length, flagOn: state.flagOn }));
    check('flag → 重做: answer card and writing lines, nothing left over from flag', r.card && r.flag && r.inputs === 4 && r.look === 0 && r.flagOn === null, r);
  });

  // ---------- 4. 做第二次（本站），按哪次标跟着换 ----------
  await section('attempts', async () => {
    // 重做里填好（5 选错）交卷：第 2 次只错第 5 题
    await page.evaluate(async () => {
      state.redo = { answers: { 1: '12', 2: 'passport', 3: 'mill', 4: 'seven', 5: 'A' }, elapsed: 30 };
      await confirmSubmit();
    });
    await page.waitForFunction(() => state.mode === 'answers' && state.exam.attempts.length === 2, null, { timeout: 5000 });
    await page.click('.mode-btn[data-mode="flag"]');
    const f = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    const c = await page.evaluate(() => ({
      nth: document.getElementById('flagNth').textContent, count: document.getElementById('flagCount').textContent, score: document.getElementById('flagScore').textContent,
      box: !document.getElementById('attemptBox').hidden && !!document.getElementById('attemptBox').closest('#flagCard'),
      bar: document.getElementById('paperFlag').innerText,
    }));
    check('newest attempt by default: only 5 framed (whole choice question)', f.gaps === '1 2 3 4' && f.qs === '5!' && f.redChips === '5' && f.leaks === 0, f);
    check('card follows: 按第 2 次, 1 wrong, 4/5, attempt switch inside the card', c.nth === '按第 2 次' && c.count === '1' && c.score === '4/5' && c.box && /第 2 次/.test(c.bar) && /错的 1 题/.test(c.bar), c);
    const st = await page.evaluate(() => { const q = document.querySelector('#paperQs .lq-q.is-flag'); const cs = getComputedStyle(q); return { bw: cs.borderTopWidth, bg: cs.backgroundColor, radius: cs.borderTopLeftRadius, listen: q.dataset.listen, tag: (q.querySelector('.lq-listen-tag') || {}).textContent, opts: [...q.querySelectorAll('.lq-opt')].map(o => getComputedStyle(o).cursor).join(',') }; });
    check('framed question: border, tinted background, 「听原文」 tag, the whole question is the button', parseFloat(st.bw) >= 1 && st.bg !== 'rgba(0, 0, 0, 0)' && st.radius === '10px' && st.listen === '5' && st.tag === '听原文' && st.opts === 'pointer,pointer,pointer', st);
    // 点选项卡片：不会选上，只是从 5 的原文那里听
    await parkAudio(page);
    await page.click('#paperQs .lq-q.is-flag .lq-opt');
    await page.waitForTimeout(400);
    const q5 = await page.evaluate(listenInfo, '5');
    const picked = await page.evaluate(() => document.querySelectorAll('.lq-opt.is-on, .lq-opt.is-right, .lq-opt.is-wrong').length);
    check('tapping an option of framed 5 plays 5 and selects nothing', jumped(q5) && q5.on === '5' && picked === 0, { q5, picked });
    await page.evaluate(() => audioEl.pause());
    await page.click('#attemptBtn');
    const hint = await page.evaluate(() => document.getElementById('attemptHint').textContent);
    check('attempt hint explains the switch in this tab', /就按那一次标注错题/.test(hint), hint);
    await page.click('#attemptMenu .lr-att__opt[data-i="0"]');
    const g = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    const c2 = await page.evaluate(() => document.getElementById('flagNth').textContent + ' ' + document.getElementById('flagCount').textContent);
    check('picking the first attempt re-marks 3 and 4', g.gaps === '1 2 3! 4!' && g.qs === '5' && c2 === '按第 1 次 2', { gaps: g.gaps, qs: g.qs, c2 });
    await shot(page, 'attempts');
  });

  // ---------- 5. 地图 + 多选（2 错、3 没答、5 错）----------
  await section('map + multi', async () => {
    await openByTitle(page, /Greenfield Library Tour/);
    const f = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    const m = await page.evaluate(() => ({
      mode: state.mode,
      rowListen: [...document.querySelectorAll('#paperQs .lq-grid tr[data-listen]')].map(r => r.dataset.listen).join(','),
      img: !!document.querySelector('#paperQs .lq-map img'),
      cells: [...document.querySelectorAll('#paperQs .lq-grid .lq-cell')].map(c => c.textContent).join(''),
      cellCount: document.querySelectorAll('#paperQs .lq-grid .lq-cell').length,
      multi: document.querySelectorAll('#paperQs .lq-opts--multi .lq-opt').length,
      chips: [...document.querySelectorAll('#paperQs .lq-q .lq-nums .lq-n')].map(n => n.textContent + (n.classList.contains('is-flag') ? '!' : '')).join(' '),
      rowBg: getComputedStyle(document.querySelector('#paperQs .lq-grid tr.is-flag td')).backgroundColor,
      plainBg: getComputedStyle(document.querySelector('#paperQs .lq-grid tr:not(.is-flag) td')).backgroundColor,
    }));
    check('map: plan + empty answer grid, rows 2 and 3 tinted and tappable', m.mode === 'flag' && m.img && m.cellCount === 15 && m.cells === '' && f.rows === '1 2! 3!' && m.rowBg !== m.plainBg && m.rowListen === '2,3', { m, rows: f.rows });
    check('multi: whole pair framed, only 5 red; right choice 6 plain', f.qs === '4 5! 6' && m.chips === '4 5!' && m.multi === 5, { qs: f.qs, chips: m.chips });
    check('no leaks on the map / multi paper', f.leaks === 0 && !f.explain, f.leakList);
    // 点地图表格里第 3 行的空格子：不填字母，从 3 的原文那里听
    await parkAudio(page);
    await page.click('#paperQs .lq-grid tr[data-listen="3"] td:nth-child(3)');
    await page.waitForTimeout(400);
    const r3 = await page.evaluate(listenInfo, '3');
    const filled = await page.evaluate(() => [...document.querySelectorAll('#paperQs .lq-cell')].map(c => c.textContent).join(''));
    check('tapping a cell in framed row 3 plays 3, fills nothing', jumped(r3) && r3.on === '3' && r3.ring && filled === '', { r3, filled });
    await parkAudio(page);
    await page.click('#paperQs .lq-q.is-flag .lq-q__stem');
    await page.waitForTimeout(400);
    const r5 = await page.evaluate(listenInfo, '5');
    check('multi pair: tapping it plays the wrong one (5)', jumped(r5) && r5.on === '5', r5);
    await page.evaluate(() => audioEl.pause());
    await shot(page, 'map');
  });

  // ---------- 6. 版式里选字母的配对 + 填空（11 错、13 错；32 错）----------
  await section('layout slots', async () => {
    await openByTitle(page, /^Part 2$/);
    const f = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    const s = await page.evaluate(() => ({ nonum: [...document.querySelectorAll('#paperQs .lq-slot')].every(x => x.classList.contains('lq-slot--nonum')), text: [...document.querySelectorAll('#paperQs .lq-slot')].map(x => x.innerText.trim()).join('|'), bank: document.querySelectorAll('#paperQs .lq-bank__item').length, used: document.querySelectorAll('#paperQs .lq-bank__item.is-used').length }));
    check('letter slots in the layout are empty, only 13 framed', f.slots === '12 13! 14' && s.nonum && s.text.replace(/（上次错了[^）]*）/g, '') === '||' && s.bank > 0 && s.used === 0, { slots: f.slots, s });
    await parkAudio(page);
    await page.click('#paperQs .lq-slot.is-flag');
    await page.waitForTimeout(400);
    const s13 = await page.evaluate(listenInfo, '13');
    const menu = await page.evaluate(() => !!document.querySelector('.lq-menu'));
    check('tapping framed slot 13 plays 13, no letter menu', jumped(s13) && s13.on === '13' && !menu, { s13, menu });
    await page.evaluate(() => audioEl.pause());
    check('choice 11 (wrong) framed', /11!/.test(f.qs), f.qs);
    check('no leaks on the matching paper', f.leaks === 0 && !f.explain, f.leakList);
    const other = await page.evaluate(async () => { await loadProjects(); return state.projects.filter(p => p.source_type === 'jiufen').map(p => p.title); });
    const p4 = other.find(t => !/Riverside|Greenfield|^Part 2$/.test(t));
    await openByTitle(page, new RegExp('^' + p4.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '$'));
    const g = await page.evaluate(readFlags, ['#paperQs', LEAKS]);
    check('Part 4 notes: 32 framed, 31 plain, no answer words', /32!/.test(g.gaps) && !/31!/.test(g.gaps) && !/\b(calm|happy|rooftops)\b/i.test(g.text) && g.leaks === 0, { gaps: g.gaps, leaks: g.leakList });
    // 音频和字幕对不上（改成重新转录）时没有出处：框照样框，但不能点、不提「点一下听」
    const na = await page.evaluate(() => {
      state.exam.aligned = false; renderQuestions();
      const r = { listen: document.querySelectorAll('[data-listen]').length, icons: document.querySelectorAll('.lq-listen').length, framed: document.querySelectorAll('#paperQs .is-flag').length, bar: document.getElementById('paperFlag').innerText, note: document.getElementById('flagNote').hidden };
      state.exam.aligned = true; renderQuestions();
      return r;
    });
    check('no source sentences (re-transcribed audio): still framed, but no tap-to-listen and no hint', na.listen === 0 && na.icons === 0 && na.framed > 0 && !/点一下/.test(na.bar) && na.note, na);
    await shot(page, 'layout');
  });

  // ---------- 7. 抽屉宽度：红题号在卷子顶上 ----------
  await section('drawer width', async () => {
    await page.setViewportSize({ width: 1000, height: 800 });
    await openByTitle(page, /Riverside Bike Hire/);
    await page.evaluate(() => { setMode('flag'); toggleSide(false); });   // 前面重做过、交过卷，保险起见
    const d = await page.evaluate(() => ({ jump: getComputedStyle(document.getElementById('paperJump')).display, n: [...document.querySelectorAll('#paperJump .lr-qnum')].map(b => b.textContent).join(','), overflow: document.documentElement.scrollWidth - window.innerWidth }));
    check('drawer width: red numbers in the paper bar (card is in the drawer)', d.jump !== 'none' && d.n === '5' && d.overflow <= 0, d);
    await parkAudio(page);
    await page.click('#paperJump .lr-qnum[data-q="5"]');
    await page.waitForTimeout(400);
    const j = await page.evaluate(() => (document.querySelector('#paperQs .is-jump') || {}).dataset);
    const b5 = await page.evaluate(listenInfo, '5');
    check('bar number jumps to the question and plays its source', j && j.nums === '5' && jumped(b5) && b5.lyricsHidden, { j, b5 });
    await page.evaluate(() => audioEl.pause());
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  // ---------- 8. 暗色 ----------
  await section('dark', async () => {
    await page.evaluate(() => localStorage.setItem('ui-theme', 'dark'));
    await page.reload();
    await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
    await openByTitle(page, /Greenfield Library Tour/);
    const d = await page.evaluate(() => ({ mode: state.mode, bg: getComputedStyle(document.querySelector('#paperQs .lq-q.is-flag')).backgroundColor, body: getComputedStyle(document.body).backgroundColor }));
    check('dark theme: frame is a dark tint, not the light pink', d.mode === 'flag' && d.bg !== 'rgb(251, 239, 238)' && d.body !== 'rgb(247, 247, 245)', d);
    await shot(page, 'map-dark');
    await page.evaluate(() => localStorage.setItem('ui-theme', 'light'));
  });
  check('no page errors (desktop)', errors.length === 0, errors);

  // ---------- 9. 手机 390 ----------
  await section('phone', async () => {
    const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
    await login(phone);
    const pp = await phone.newPage();
    pp.on('pageerror', e => errors.push('phone: ' + e.message));
    await pp.goto(`${BASE}/listening_review`);
    await pp.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
    await pp.evaluate(() => { localStorage.setItem('listening-redo-script', '0'); localStorage.setItem('ui-theme', 'light'); });
    await openByTitle(pp, /Riverside Bike Hire/);
    await pp.waitForTimeout(300);
    const p = await pp.evaluate(() => {
      const seg = document.getElementById('modeSeg');
      const btns = [...seg.querySelectorAll('.mode-btn')].map(b => b.getBoundingClientRect());
      const jump = [...document.querySelectorAll('#paperJump .lr-qnum')].map(b => b.getBoundingClientRect());
      const vis = s => { const e = document.querySelector(s); return !!e && getComputedStyle(e).display !== 'none' && e.getBoundingClientRect().width > 0; };
      return {
        ptab: state.ptab, mode: state.mode, first: seg.querySelector('.mode-btn').dataset.mode, inQ: !!seg.closest('#pQHead'), three: btns.length === 3, fits: btns.every(r => r.left >= 0 && r.right <= window.innerWidth && r.height >= 44),
        att: !!document.getElementById('attemptBox').closest('#pQHead') && !document.getElementById('attemptBox').hidden,
        short: vis('.lr-paper__fp'), wide: vis('.lr-paper__fw'), shortText: document.querySelector('.lr-paper__fp').innerText,
        jump: jump.length, jumpBig: jump.every(r => r.height >= 40 && r.width >= 40),
        card: vis('#flagCard'), overflow: document.documentElement.scrollWidth - window.innerWidth,
      };
    });
    check('phone: opens on 错题标注 in 题目; three tabs on one row, 错题标注 first, each 44px tall', p.mode === 'flag' && p.first === 'flag' && p.ptab === 'questions' && p.inQ && p.three && p.fits, p);
    check('phone: attempt switch stays under the tabs (two attempts now)', p.att, p);
    check('phone: short bar 「红框 = 错的 1 题，点了听」 + 40px red numbers, no sideways scroll', p.short && !p.wide && /红框\s*= 错的 1 题，点了听/.test(p.shortText) && p.jump === 1 && p.jumpBig && !p.card && p.overflow <= 0, p);
    // 换回第 1 次（3 错、4 没答），看表格里的空也框红
    await pp.evaluate(() => { state.attemptIdx = 0; renderExamSide(); });
    const p2 = await pp.evaluate(() => ({ n: [...document.querySelectorAll('#paperJump .lr-qnum')].map(b => b.textContent).join(','), gaps: [...document.querySelectorAll('#paperQs .lq-gap.is-flag')].map(g => g.dataset.nums).join(',') }));
    check('phone: switching attempt re-marks the paper', p2.n === '3,4' && p2.gaps === '3,4', p2);
    await shot(pp, 'phone');
    await parkAudio(pp);
    await pp.tap('#paperJump .lr-qnum[data-q="4"]');
    await pp.waitForTimeout(400);
    const j = await pp.evaluate(() => (document.querySelector('#paperQs .is-jump') || {}).dataset);
    const pj = await pp.evaluate(listenInfo, '4');
    check('phone: tapping a red number jumps to it and plays its source', j && j.nums === '4' && jumped(pj), { j, pj });
    await parkAudio(pp);
    await pp.tap('#paperQs .lq-gap.is-flag[data-nums="3"]');
    await pp.waitForTimeout(400);
    const pt = await pp.evaluate(listenInfo, '3');
    check('phone: tapping framed 3 plays it, stays on 题目, transcript still hidden', jumped(pt) && pt.ptab === 'questions' && pt.lyricsHidden && !pt.showScript && pt.on === '3', pt);
    await pp.evaluate(() => audioEl.pause());
    await pp.tap('.ptab-btn[data-ptab="side"]');
    const s = await pp.evaluate(() => ({ name: document.getElementById('ptabSideName').textContent, card: !document.getElementById('flagCard').hidden && getComputedStyle(document.getElementById('flagCard')).display !== 'none', btns: !!document.querySelector('#flagCard #checkinBtn') }));
    check('phone: 本篇 tab shows the 错题标注 card with 打卡 / 标熟', s.name === '本篇' && s.card && s.btns, s);
    await pp.tap('.ptab-btn[data-ptab="script"]');
    const o = await pp.evaluate(() => ({ off: !document.getElementById('scriptHidden').hidden, tags: document.querySelectorAll('.lr-qtag').length }));
    check('phone: 原文 tab says the transcript is hidden', o.off && o.tags === 0, o);
    await pp.evaluate(() => openMoreSheet());
    const more = await pp.evaluate(() => !document.getElementById('moreScript').hidden);
    check('phone: 显示原文 switch is in ⋯ for this tab too', more, more);
    await phone.close();
  });
  check('no page errors (phone)', errors.length === 0, errors);

  console.log(`${engine}: ${pass}/${pass + fail} passed`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });

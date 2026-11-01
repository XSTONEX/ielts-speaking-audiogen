// 「显示答案 / 重做」的浏览器检查（沙盒、编造数据）：
// 导入三份 JSON（填空 + 单选；地图 + 多选；版式里选字母的配对）→ 切到重做 → 各题型作答（横线、选项卡片、
// 答题纸表格、字母槽 + 菜单、按字母键）→ 刷新后接着做 → 显示 / 隐藏原文 → 交卷判分 → 显示答案的新样式 →
// 做题记录（本站 / 九分、删本站的）→ 暗色、390 宽（字母菜单从底部弹出）。
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
const shot = async (page, name) => { await page.waitForTimeout(300); await page.screenshot({ path: path.join(OUT, `redo-${engine}-${name}.png`) }); };

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

(async () => {
  const browser = await pw[engine].launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await login(ctx);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/listening_review`);
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);

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

  // ---------- 1. 填空 + 单选：默认显示答案，切到重做 ----------
  await openByTitle(page, /Riverside Bike Hire/);
  const a0 = await page.evaluate(() => ({
    seg: !document.getElementById('modeSeg').hidden,
    on: document.querySelector('.mode-btn.is-on').dataset.mode,
    script: document.getElementById('scriptBtn').hidden,
    qtags: document.querySelectorAll('.lr-qtag').length,
  }));
  check('switch shown on imported article, answers by default', a0.seg && a0.on === 'answers' && a0.script && a0.qtags === 5, a0);
  await page.click('.mode-btn[data-mode="redo"]');
  const r0 = await page.evaluate(() => ({
    lyrics: document.getElementById('lyricsContainer').hidden,
    paper: !document.getElementById('paperPane').hidden,
    card: !document.getElementById('redoCard').hidden,
    info: document.getElementById('sideInfoCard').hidden,
    main: document.getElementById('sideMainCard').hidden,
    trans: document.getElementById('toggleTransBtn').hidden,
    scriptPressed: document.getElementById('scriptBtn').getAttribute('aria-pressed'),
    leaks: document.querySelectorAll('.lr-qtag, .lr-ans, .lr-evi, .lr-hl, .lr-qx, .lr-qs__legend, .is-review, .lq-gap.is-ok, .lq-gap.is-err, .lq-gap.is-none, .lq-opt.is-right, .lq-opt.is-wrong').length,
    inputs: [...document.querySelectorAll('#paperQs .lq-gap__in')].map(i => i.dataset.q + '=' + i.value).join(','),
    spell: [...document.querySelectorAll('#paperQs .lq-gap__in')].every(i => i.getAttribute('spellcheck') === 'false' && i.getAttribute('autocorrect') === 'off'),
    chips: [...document.querySelectorAll('#paperQs .lq-gap .lq-n')].map(n => n.textContent).join(','),
    picks: document.querySelectorAll('#paperQs .lq-opt').length,
    picked: document.querySelectorAll('#paperQs .lq-opt.is-on').length,
    card: (() => { const o = document.querySelector('#paperQs .lq-opt'); const cs = getComputedStyle(o); return { border: cs.borderTopStyle + ' ' + cs.borderTopWidth, w: Math.round(o.getBoundingClientRect().width) }; })(),
    nth: document.getElementById('redoNth').textContent,
    last: document.getElementById('redoLast').textContent,
    map: [...document.querySelectorAll('#redoMap .lr-qnum')].map(b => b.className.includes('is-todo') ? 'o' : 'x').join(''),
  }));
  check('redo hides the transcript and shows the paper + answer card', r0.lyrics && r0.paper && r0.card && r0.info && r0.main && r0.trans && r0.scriptPressed === 'false', r0);
  check('no answers leak in redo (tags, underline, highlights, chips, legend)', r0.leaks === 0, r0.leaks);
  check('blanks are empty writing lines with the number inside, spellcheck off', r0.inputs === '1=,2=,3=,4=' && r0.spell && r0.chips === '1,2,3,4', r0);
  check('choice options are bordered cards, capped at 620px, unselected', r0.picks === 3 && r0.picked === 0 && r0.card.border === 'solid 1px' && r0.card.w <= 620, r0);
  check('answer card numbers', r0.nth === '第 2 次' && r0.last === '3/5' && r0.map === 'ooooo', r0);

  await page.click('#paperQs .lq-gap__in[data-q="1"]');
  await page.keyboard.type('Twelve');
  await page.keyboard.press('Enter');
  const focus2 = await page.evaluate(() => document.activeElement.dataset.q);
  await page.keyboard.type('passport');
  await page.keyboard.press('Enter');
  await page.keyboard.type('mill');
  await page.keyboard.press('Enter');
  await page.keyboard.type(' ');   // 空格在输入框里只是空格，不会开始播放
  const space = await page.evaluate(() => ({ paused: audioEl.paused, v: document.querySelector('#paperQs .lq-gap__in[data-q="4"]').value }));
  await page.keyboard.press('Backspace');
  check('Enter jumps to the next blank', focus2 === '2', focus2);
  check('space typed in a blank does not play audio', space.paused && space.v === ' ', space);
  await page.click('#paperQs .lq-opt[data-k="A"]');
  await page.keyboard.press('c');   // 选项上按字母键直接改选
  const byKey = await page.evaluate(() => [...document.querySelectorAll('#paperQs .lq-opt.is-on')].map(b => b.dataset.k).join(''));
  await page.keyboard.press('b');
  await page.keyboard.press(' ');   // 选项上按空格：点这个选项（已选的就取消），不开始播放
  const spaceOpt = await page.evaluate(() => ({ paused: audioEl.paused, on: [...document.querySelectorAll('#paperQs .lq-opt.is-on')].map(b => b.dataset.k).join('') }));
  await page.keyboard.press('b');
  check('letter keys on a choice pick that option', byKey === 'C', byKey);
  check('space on an option toggles it, audio stays paused', spaceOpt.paused && spaceOpt.on === '', spaceOpt);
  await page.waitForTimeout(2300);
  const r1 = await page.evaluate(() => ({
    done: document.getElementById('redoDone').textContent,
    prog: document.getElementById('paperProg').textContent,
    map: [...document.querySelectorAll('#redoMap .lr-qnum')].map(b => b.className.includes('is-done') ? 'x' : 'o').join(''),
    time: document.getElementById('redoTime').textContent,
    picked: [...document.querySelectorAll('#paperQs .lq-opt.is-on')].map(b => b.dataset.k).join(''),
    filled: document.querySelectorAll('#paperQs .lq-gap.is-filled').length,
  }));
  check('progress counts answered questions', r1.done === '4' && /^已答 4\/5 · 00:0\d$/.test(r1.prog) && r1.map === 'xxxox' && r1.filled === 3, r1);
  check('clock runs', r1.time !== '00:00', r1.time);
  check('choice picked', r1.picked === 'B', r1.picked);
  await shot(page, 'paper');

  // 刷新页面后回来，还是重做、答案都在
  await page.waitForTimeout(500);
  await page.reload();
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  await openByTitle(page, /Riverside Bike Hire/);
  const r2 = await page.evaluate(() => ({
    mode: state.mode,
    v1: (document.querySelector('#paperQs .lq-gap__in[data-q="1"]') || {}).value,
    picked: [...document.querySelectorAll('#paperQs .lq-opt.is-on')].map(b => b.dataset.k).join(''),
    time: document.getElementById('redoTime').textContent,
  }));
  check('draft survives a reload', r2.mode === 'redo' && r2.v1 === 'Twelve' && r2.picked === 'B' && r2.time !== '00:00', r2);

  // 显示原文：字幕回来但没有答案标记，题目回到右栏
  await page.click('#scriptBtn');
  const r3 = await page.evaluate(() => ({
    lyrics: !document.getElementById('lyricsContainer').hidden,
    paper: document.getElementById('paperPane').hidden,
    lines: document.querySelectorAll('#lyricsContainer .lr-line').length,
    leaks: document.querySelectorAll('.lr-qtag, .lr-ans, .lr-evi').length,
    paneInputs: [...document.querySelectorAll('#questionsPane .lq-gap__in')].map(i => i.value).join('|'),
    paneMap: document.querySelectorAll('#questionsPane .lr-qmap .lr-qnum').length,
    trans: !document.getElementById('toggleTransBtn').hidden,
    saved: localStorage.getItem('listening-redo-script'),
    redoMap: document.getElementById('redoMap').hidden,
  }));
  check('show transcript: lines back, still no answer marks', r3.lyrics && r3.paper && r3.lines === 10 && r3.leaks === 0 && r3.trans, r3);
  check('questions move to the side with the same answers', r3.paneInputs === 'Twelve|passport|mill|' && r3.paneMap === 5 && r3.redoMap, r3);
  check('transcript choice remembered', r3.saved === '1', r3.saved);
  await shot(page, 'shown');

  // 切回显示答案再回来，答卷还在
  await page.click('.mode-btn[data-mode="answers"]');
  const r4 = await page.evaluate(() => ({ tags: document.querySelectorAll('.lr-qtag').length, info: !document.getElementById('sideInfoCard').hidden, card: document.getElementById('redoCard').hidden }));
  await page.click('.mode-btn[data-mode="redo"]');
  const r5 = await page.evaluate(() => [...document.querySelectorAll('#questionsPane .lq-gap__in')].map(i => i.value).join('|'));
  check('answers mode is back to normal', r4.tags === 5 && r4.info && r4.card, r4);
  check('switching back keeps the unfinished paper', r5 === 'Twelve|passport|mill|', r5);

  // 交卷
  await page.click('#redoCard .ui-btn--primary');
  const s0 = await page.evaluate(() => ({ open: !document.getElementById('submitModal').hidden, text: document.getElementById('submitText').textContent, nth: document.getElementById('submitNth').textContent, done: document.getElementById('submitDone').textContent }));
  check('submit dialog lists the blank question', s0.open && /还有 1 题没答：第 4 题/.test(s0.text) && s0.nth === '第 2 次' && s0.done === '4 / 5', s0);
  await page.click('#submitConfirmBtn');
  await page.waitForFunction(() => document.getElementById('submitModal').hidden && state.mode === 'answers', null, { timeout: 5000 });
  const s1 = await page.evaluate(() => ({
    attempts: state.exam.attempts.map(a => (a.source || 'jiufen') + ':' + a.correct + '/' + a.total).join(' '),
    src: document.getElementById('sideSrc').textContent,
    score: document.getElementById('sideScoreNum').textContent,
    btn: document.getElementById('attemptBtnText').textContent,
    tags: [...document.querySelectorAll('.lr-qtag')].map(t => t.textContent + (t.classList.contains('is-err') ? '!' : t.classList.contains('is-blank') ? '-' : '')).join(' '),
    meta: document.getElementById('detailMeta').textContent,
    toast: [...document.querySelectorAll('.ielts-toast')].map(t => t.textContent).join(' | '),
    draft: localStorage.getItem('listening-redo:' + state.currentProject.id),
    card: (state.projects.find(p => p.id === state.currentProject.id) || {}).score,
  }));
  check('submitted attempt saved after the imported one', s1.attempts === 'jiufen:3/5 self:4/5', s1.attempts);
  check('shows the new attempt', /^本站重做 · .+交卷 · 用时 00:0\d$|^本站重做 · .+交卷 · 用时 0:0\d$/.test(s1.src) && s1.score === '4/5' && /第 2 次/.test(s1.btn) && /本站/.test(s1.btn), s1);
  check('transcript tags follow the new attempt', s1.tags === 'Q1 Q2 Q3 Q4- Q5', s1.tags);
  check('meta + toast + list score', /做过 2 次/.test(s1.meta) && /第 2 次交卷：答对 4\/5，比上次多对 1 题/.test(s1.toast) && s1.card && s1.card.correct === 4, s1);
  check('draft cleared after submit', s1.draft === null, s1.draft);
  const v0 = await page.evaluate(() => ({
    gaps: [...document.querySelectorAll('#questionsPane .lq-gap')].map(b => b.dataset.q + (b.classList.contains('is-ok') ? 'ok' : b.classList.contains('is-err') ? 'err' : b.classList.contains('is-none') ? 'none' : '?')).join(' '),
    none: (document.querySelector('#questionsPane .lq-gap.is-none') || {}).innerText,
    opts: [...document.querySelectorAll('#questionsPane .lq-opts.is-review .lq-opt')].map(o => o.className.replace(/lq-opt\s?/, '') + ':' + o.querySelector('.lq-opt__tag').textContent).join(' | '),
  }));
  check('answers view: blanks as green / dashed lines', v0.gaps === '1ok 2ok 3ok 4none' && /没答\s*seven/.test(v0.none || ''), v0);
  check('answers view: choice cards in the same shape', v0.opts === ': | is-right:你选 · 对 | :', v0.opts);
  const saved = await page.evaluate(async () => (await API.get('/api/listening_review/project/' + state.currentProject.id)).exam.attempts.length);
  check('server kept both attempts', saved === 2, saved);
  await shot(page, 'after-submit');

  // 做题记录：本站的可以删，九分的不能
  await page.click('#attemptBtn');
  const m0 = await page.evaluate(() => ({ items: [...document.querySelectorAll('#attemptMenu .lr-att__opt')].map(b => b.innerText.replace(/\s+/g, ' ')), dels: document.querySelectorAll('#attemptMenu .lr-att__del').length }));
  check('attempt menu tags 九分 / 本站, delete only on 本站', m0.items.length === 2 && /九分/.test(m0.items[0]) && /本站/.test(m0.items[1]) && m0.dels === 1, m0);
  await page.click('#attemptMenu .lr-att__del');
  const c0 = await page.evaluate(() => ({ open: !document.getElementById('confirmModal').hidden, title: document.getElementById('confirmTitle').textContent }));
  check('delete asks first', c0.open && c0.title === '删除第 2 次记录？', c0);
  await page.click('#confirmOkBtn');
  await page.waitForFunction(() => state.exam.attempts.length === 1, null, { timeout: 5000 });
  const d0 = await page.evaluate(() => ({ box: document.getElementById('attemptBox').hidden, score: document.getElementById('sideScoreNum').textContent, src: document.getElementById('sideSrc').textContent }));
  check('deleted: back to the imported attempt', d0.box && d0.score === '3/5' && /^九分学长/.test(d0.src), d0);

  // ---------- 2. 地图 + 多选 ----------
  await openByTitle(page, /Greenfield Library Tour/);
  const g0 = await page.evaluate(() => ({
    kinds: state.exam.groups.map(g => g.kind).join(','),
    img: !!document.querySelector('#questionsPane .lq-map .lr-qs__imglink img'),
    cols: [...document.querySelectorAll('#questionsPane .lq-grid th')].map(t => t.textContent).join(''),
    rows: [...document.querySelectorAll('#questionsPane .lq-grid tr[data-q]')].map(r => r.dataset.q + ':' + [...r.querySelectorAll('.lq-cell')].map(c => c.classList.contains('is-right') ? c.textContent + '+' : c.classList.contains('is-wrong') ? c.textContent + 'x' : c.classList.contains('is-miss') ? c.textContent + '?' : '').join('')).join(' '),
    emptyOpts: [...document.querySelectorAll('#questionsPane .lq-opt')].filter(o => !o.querySelector('.lq-opt__t').textContent.trim()).length,
    nums: [...document.querySelectorAll('#questionsPane .lq-nums .lq-n')].map(n => n.textContent + (n.classList.contains('is-err') ? '!' : '')).join(' '),
    marks: [...document.querySelectorAll('#questionsPane .lq-opts--multi .lq-opt')].map(o => o.querySelector('.lq-opt__tag').textContent).filter(Boolean).join(','),
    tray: (document.querySelector('#questionsPane .lq-tray') || {}).innerText,
  }));
  check('map + multi recognised', g0.kinds === 'map,multi,choice', g0.kinds);
  check('map: plan + answer-sheet grid, one row per question', g0.img && g0.emptyOpts === 0 && g0.cols.startsWith('位置ABCDE') && g0.rows === '1:C+ 2:BxE+ 3:A?', g0);
  check('multi: both numbers, tray, shared options with 漏选', g0.nums === '4 5!' && g0.marks === '你选 · 对,你选,漏选' && /对 1 题/.test(g0.tray || '') && /5\s*C\s*D/.test(g0.tray || ''), g0);
  await page.click('#questionsPane .lq-grid tr[data-q="2"]');
  const gq = await page.evaluate(() => ({ sel: !!document.querySelector('#questionsPane .lq-grid tr.is-sel[data-q="2"]'), qx: (document.querySelector('#questionsPane .lq-grid__qx .lr-qx') || {}).innerText || '' }));
  check('clicking a grid row opens its explanation under the row', gq.sel && /你的答案\s*B/.test(gq.qx), gq);
  await page.click('#questionsPane .lq-q__stem[data-q="4"]');
  const qx = await page.evaluate(() => (document.querySelector('#questionsPane .lr-qx') || {}).innerText || '');
  check('multi explanation lists both letters', /你选\s*B、C/.test(qx) && /正确答案\s*B、D（不分先后）/.test(qx), qx);

  await page.click('.mode-btn[data-mode="redo"]');
  await page.click('#scriptBtn');   // 上一篇选了显示原文，这里关掉，看卷子
  const g1 = await page.evaluate(() => ({
    paper: !document.getElementById('paperPane').hidden,
    rows: document.querySelectorAll('#paperQs .lq-grid tr[data-nums]').length,
    letters: [...document.querySelectorAll('#paperQs .lq-grid tr[data-nums]')].map(r => r.querySelectorAll('.lq-cell').length).join(','),
    side: getComputedStyle(document.querySelector('#paperQs .lq-map')).gridTemplateColumns.split(' ').length,
    multi: document.querySelectorAll('#paperQs .lq-opts--multi .lq-opt').length,
    tray: (document.querySelector('#paperQs .lq-tray') || {}).innerText,
  }));
  check('redo: map is an answer-sheet grid beside the plan, multi is checkbox cards', g1.paper && g1.rows === 3 && g1.letters === '5,5,5' && g1.side === 2 && g1.multi === 5 && /选 2 个 · 已选 0/.test(g1.tray || ''), g1);
  const cell = (q, k) => page.click(`#paperQs .lq-cell[data-q="${q}"][data-k="${k}"]`);
  await cell('1', 'C'); await cell('2', 'E'); await cell('2', 'E'); await cell('2', 'A');
  await page.keyboard.press('ArrowRight');   // 方向键在圈之间挪，按字母键选
  await page.keyboard.press('b');
  const gk = await page.evaluate(() => ({ focus: document.activeElement.dataset.q + document.activeElement.dataset.k, paused: audioEl.paused }));
  check('grid: arrow keys move between circles, letter key picks, audio not touched', gk.focus === '2B' && gk.paused, gk);
  const multiOpt = (k, force) => page.click(`#paperQs .lq-opts--multi .lq-opt[data-k="${k}"]`, { force: !!force });
  await multiOpt('B'); await multiOpt('D'); await multiOpt('E', true);   // 选够了，第三个点了也没用
  const g2 = await page.evaluate(() => ({
    on: [...document.querySelectorAll('#paperQs .lq-opts--multi .lq-opt.is-on')].map(b => b.dataset.k + b.querySelector('.lq-opt__tag').textContent).join(','),
    dimE: document.querySelector('#paperQs .lq-opts--multi .lq-opt[data-k="E"]').getAttribute('aria-disabled'),
    tray: document.querySelector('#paperQs .lq-tray').innerText.replace(/\s+/g, ' '),
    hint: (document.querySelector('#paperQs .lr-unit[data-unit="4"] .lq-hint') || {}).textContent,
    cells: [...document.querySelectorAll('#paperQs .lq-cell.is-on')].map(b => b.dataset.q + b.dataset.k).join(','),
    nums: [...document.querySelectorAll('#paperQs .lr-unit[data-unit="4"] [data-numtag]')].map(n => n.className.includes('is-done') ? 'x' : 'o').join(''),
  }));
  check('multi stops at two, tray shows 4 B / 5 D, rest dashed', g2.on === 'B4,D5' && g2.dimE === 'true' && /已选 2 4 B 5 D/.test(g2.tray) && /选够了/.test(g2.hint || '') && g2.nums === 'xx', g2);
  check('grid circles toggle', g2.cells === '1C,2B', g2.cells);
  await multiOpt('D'); await multiOpt('E'); await multiOpt('E'); await multiOpt('D');
  await page.click('#paperQs .lq-opts:not(.lq-opts--multi) .lq-opt[data-k="B"]');
  await page.click('#redoMap .lr-qnum[data-q="3"]');
  await page.waitForTimeout(400);
  const g3 = await page.evaluate(() => ({ focus: document.activeElement.closest('[data-nums]') && document.activeElement.closest('[data-nums]').dataset.nums, done: document.getElementById('redoDone').textContent }));
  check('question map jumps to that question', g3.focus === '3' && g3.done === '5', g3);
  await shot(page, 'map-paper');
  await page.click('#redoCard .ui-btn--primary');
  await page.click('#submitConfirmBtn');
  await page.waitForFunction(() => state.mode === 'answers', null, { timeout: 5000 });
  const g4 = await page.evaluate(() => {
    const a = state.exam.attempts[state.attemptIdx];
    return { score: `${a.correct}/${a.total}`, ans: Object.entries(a.answers).map(([n, x]) => `${n}${x.user || '-'}${x.state[0]}`).join(' '),
      row2: [...document.querySelectorAll('#questionsPane .lq-grid tr[data-q="2"] .lq-cell')].map(c => c.textContent + (c.classList.contains('is-right') ? '+' : c.classList.contains('is-wrong') ? 'x' : '')).join('') };
  });
  check('map + multi graded (multi in either order)', g4.score === '4/6' && g4.ans === '1Cr 2Bw 3-b 4Br 5Dr 6Br', g4);
  check('map row shows your wrong letter and the right one', g4.row2 === 'ABxCDE+', g4.row2);

  // ---------- 3. 版式里选字母的配对（字母槽 + 菜单） ----------
  await openByTitle(page, /^Part 2$/);
  await page.click('.mode-btn[data-mode="redo"]');
  const x0 = await page.evaluate(() => ({
    slots: [...document.querySelectorAll('#paperQs .lq-slot')].map(s => s.dataset.slot).join(','),
    ph: document.querySelector('#paperQs .lq-slot').innerText.trim(),
    nonum: [...document.querySelectorAll('#paperQs .lq-slot')].every(s => s.classList.contains('lq-slot--nonum') && !s.querySelector('.lq-n')),
    selects: document.querySelectorAll('#paperQs select').length,
    bank: document.querySelectorAll('#paperQs .lq-bank .lq-bank__item').length,
  }));
  check('blanks in a matching layout become letter slots (no native dropdown)', x0.slots === '12,13,14' && x0.ph === '选字母' && x0.selects === 0 && x0.bank > 0, x0);
  check('layout already says "12." so the slot does not repeat the number', x0.nonum, x0);
  await page.click('#paperQs .lq-slot[data-slot="12"]');
  const mn = await page.evaluate(() => { const m = document.querySelector('.lq-menu'); return m && { opts: m.querySelectorAll('.lq-menu__opt').length, focus: document.activeElement.classList.contains('lq-menu__opt'), expanded: document.querySelector('#paperQs .lq-slot[data-slot="12"]').getAttribute('aria-expanded'), sheet: m.classList.contains('is-sheet') }; });
  check('clicking a slot opens the option menu under it', mn && mn.opts > 2 && mn.focus && mn.expanded === 'true' && !mn.sheet, mn);
  await page.click('.lq-menu .lq-menu__opt[data-k="A"]');
  const s12 = await page.evaluate(() => ({ menu: !!document.querySelector('.lq-menu'), text: document.querySelector('#paperQs .lq-slot[data-slot="12"]').innerText.replace(/\s+/g, ' ').trim(), focus: document.activeElement.dataset.slot, used: [...document.querySelectorAll('#paperQs .lq-bank__item.is-used')].map(i => i.innerText.replace(/\s+/g, ' ')).join(' | ') }));
  check('picking from the menu fills letter + option text, focus stays on the slot', !s12.menu && /^A \S/.test(s12.text) && s12.focus === '12', s12);
  check('the box marks which question used a letter', /^A .* 12$/.test(s12.used), s12.used);
  await page.click('#paperQs .lq-slot[data-slot="13"]');
  const used = await page.evaluate(() => (document.querySelector('.lq-menu .lq-menu__opt[data-k="A"]') || {}).innerText);
  check('a letter used elsewhere says where', /已填在 12/.test(used || ''), used);
  await page.keyboard.press('Escape');
  const esc = await page.evaluate(() => ({ menu: !!document.querySelector('.lq-menu'), focus: document.activeElement.dataset.slot }));
  check('Escape closes the menu back to the slot', !esc.menu && esc.focus === '13', esc);
  await page.keyboard.press('b');   // 槽上直接按字母键
  await page.focus('#paperQs .lq-slot[data-slot="14"]');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('c');
  const kb = await page.evaluate(() => ({ v13: state.redo.answers['13'], v14: state.redo.answers['14'], menu: !!document.querySelector('.lq-menu'), paused: audioEl.paused }));
  check('letter keys fill a slot; ArrowDown opens the menu, letter picks', kb.v13 === 'B' && kb.v14 === 'C' && !kb.menu && kb.paused, kb);
  await page.click('#paperQs .lq-opt[data-k="C"]');
  await page.click('#redoCard .ui-btn--primary');
  const x1 = await page.evaluate(() => document.getElementById('submitText').textContent);
  check('all answered message', x1 === '都答完了，交卷后马上判分。', x1);
  await page.click('#submitConfirmBtn');
  await page.waitForFunction(() => state.mode === 'answers', null, { timeout: 5000 });
  const x2 = await page.evaluate(() => { const a = state.exam.attempts[state.attemptIdx]; return { score: `${a.correct}/${a.total}`, slots: [...document.querySelectorAll('#questionsPane .lq-slot.is-ok')].map(s => s.innerText.replace(/\s+/g, ' ').trim()).join(' | ') }; });
  check('matching graded, answers view shows green letter slots', x2.score === '4/4' && /^A \S.* \| B \S.* \| C \S/.test(x2.slots), x2);

  // ---------- 暗色 + 手机 ----------
  await page.evaluate(() => localStorage.setItem('ui-theme', 'dark'));
  await page.reload();
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  await openByTitle(page, /Greenfield Library Tour/);
  await page.click('.mode-btn[data-mode="redo"]');
  await page.click('#paperQs .lq-cell[data-q="1"][data-k="C"]');
  await page.click('#paperQs .lq-opts--multi .lq-opt[data-k="B"]');
  await page.waitForTimeout(400);   // 等按钮颜色的过渡动画走完再截图
  await shot(page, 'map-paper-dark');
  const dark = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  check('dark theme applies to the paper', dark !== 'rgb(247, 247, 245)' && dark !== 'rgb(255, 255, 255)', dark);
  await page.evaluate(() => localStorage.setItem('ui-theme', 'light'));
  check('no page errors (desktop)', errors.length === 0, errors);

  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true });
  await login(phone);
  const pp = await phone.newPage();
  pp.on('pageerror', e => errors.push('phone: ' + e.message));
  await pp.goto(`${BASE}/listening_review`);
  await pp.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  await pp.evaluate(() => localStorage.setItem('listening-redo-script', '0'));
  await openByTitle(pp, /Riverside Bike Hire/);
  await pp.evaluate(() => setMode('redo'));
  const ph = await pp.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - window.innerWidth,
    submit: getComputedStyle(document.querySelector('.lr-paper__submit')).display,
    prog: getComputedStyle(document.getElementById('paperProg')).display,
    drawer: state.sideOpen,
  }));
  check('phone: paper fits, submit + progress in the bar', ph.overflow <= 0 && ph.submit !== 'none' && ph.prog !== 'none' && !ph.drawer, ph);
  const tools = await pp.evaluate(() => { const seg = document.getElementById('modeSeg').getBoundingClientRect(), b = document.getElementById('scriptBtn').getBoundingClientRect(); return { segRight: Math.round(seg.right), segBottom: Math.round(seg.bottom), btnTop: Math.round(b.top), w: window.innerWidth }; });
  check('phone: switch on its own row, nothing overlaps', tools.segRight <= tools.w && tools.btnTop >= tools.segBottom, tools);
  await shot(pp, 'phone');
  await pp.click('.lr-paper__submit');
  const ph2 = await pp.evaluate(() => !document.getElementById('submitModal').hidden);
  check('phone: submit opens the dialog', ph2, ph2);
  await pp.evaluate(() => closeSubmitDialog());
  await openByTitle(pp, /^Part 2$/);
  await pp.evaluate(() => setMode('redo'));
  await pp.click('#paperQs .lq-slot[data-slot="12"]');
  const sh = await pp.evaluate(() => { const m = document.querySelector('.lq-menu'); const r = m && m.getBoundingClientRect(); return m && { sheet: m.classList.contains('is-sheet'), bottom: Math.round(r.bottom), h: window.innerHeight, w: Math.round(r.width), scrim: !!document.querySelector('.lq-scrim') }; });
  check('phone: letter menu slides up from the bottom with a scrim', sh && sh.sheet && Math.abs(sh.bottom - sh.h) <= 1 && sh.w >= 380 && sh.scrim, sh);
  await shot(pp, 'phone-sheet');
  await pp.click('.lq-menu .lq-menu__opt[data-k="B"]');
  const sh2 = await pp.evaluate(() => ({ menu: !!document.querySelector('.lq-menu'), scrim: !!document.querySelector('.lq-scrim'), v: state.redo.answers['12'], overflow: document.documentElement.scrollWidth - window.innerWidth }));
  check('phone: picking closes the sheet, page still fits', !sh2.menu && !sh2.scrim && sh2.v === 'B' && sh2.overflow <= 0, sh2);
  check('no page errors (phone)', errors.length === 0, errors);

  console.log(`${engine}: ${pass}/${pass + fail} passed`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });

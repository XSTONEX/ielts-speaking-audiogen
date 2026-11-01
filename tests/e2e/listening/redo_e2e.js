// 「显示答案 / 重做」的浏览器检查（沙盒、编造数据）：
// 导入三份 JSON（填空 + 单选；地图 + 多选；版式里选字母的配对）→ 切到重做 → 各题型作答 → 刷新后接着做 →
// 显示 / 隐藏原文 → 交卷判分 → 做题记录（本站 / 九分、删本站的）→ 暗色、390 宽截图。
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
    leaks: document.querySelectorAll('.lr-qtag, .lr-ans, .lr-evi, .lr-hl, .lr-qx, .lr-blank, .lr-qs__legend').length,
    inputs: [...document.querySelectorAll('#paperQs .lr-inp__box')].map(i => i.dataset.q + '=' + i.value).join(','),
    spell: [...document.querySelectorAll('#paperQs .lr-inp__box')].every(i => i.getAttribute('spellcheck') === 'false' && i.getAttribute('autocorrect') === 'off'),
    picks: document.querySelectorAll('#paperQs .lr-pick__opt').length,
    picked: document.querySelectorAll('#paperQs .lr-pick__opt.is-on').length,
    nth: document.getElementById('redoNth').textContent,
    last: document.getElementById('redoLast').textContent,
    map: [...document.querySelectorAll('#redoMap .lr-qnum')].map(b => b.className.includes('is-todo') ? 'o' : 'x').join(''),
  }));
  check('redo hides the transcript and shows the paper + answer card', r0.lyrics && r0.paper && r0.card && r0.info && r0.main && r0.trans && r0.scriptPressed === 'false', r0);
  check('no answers leak in redo (tags, underline, highlights, chips, legend)', r0.leaks === 0, r0.leaks);
  check('blanks are empty inputs, spellcheck off', r0.inputs === '1=,2=,3=,4=' && r0.spell, r0);
  check('choice options unselected', r0.picks === 3 && r0.picked === 0, r0);
  check('answer card numbers', r0.nth === '第 2 次' && r0.last === '3/5' && r0.map === 'ooooo', r0);

  await page.click('#paperQs .lr-inp__box[data-q="1"]');
  await page.keyboard.type('Twelve');
  await page.keyboard.press('Enter');
  const focus2 = await page.evaluate(() => document.activeElement.dataset.q);
  await page.keyboard.type('passport');
  await page.keyboard.press('Enter');
  await page.keyboard.type('mill');
  await page.keyboard.press('Enter');
  await page.keyboard.type(' ');   // 空格在输入框里只是空格，不会开始播放
  const space = await page.evaluate(() => ({ paused: audioEl.paused, v: document.querySelector('#paperQs .lr-inp__box[data-q="4"]').value }));
  await page.keyboard.press('Backspace');
  check('Enter jumps to the next blank', focus2 === '2', focus2);
  check('space typed in a blank does not play audio', space.paused && space.v === ' ', space);
  await page.click('#paperQs .lr-pick__opt[data-k="B"]');
  await page.waitForTimeout(2300);
  const r1 = await page.evaluate(() => ({
    done: document.getElementById('redoDone').textContent,
    prog: document.getElementById('paperProg').textContent,
    map: [...document.querySelectorAll('#redoMap .lr-qnum')].map(b => b.className.includes('is-done') ? 'x' : 'o').join(''),
    time: document.getElementById('redoTime').textContent,
    picked: [...document.querySelectorAll('#paperQs .lr-pick__opt.is-on')].map(b => b.dataset.k).join(''),
    filled: document.querySelectorAll('#paperQs .lr-inp.is-filled').length,
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
    v1: (document.querySelector('#paperQs .lr-inp__box[data-q="1"]') || {}).value,
    picked: [...document.querySelectorAll('#paperQs .lr-pick__opt.is-on')].map(b => b.dataset.k).join(''),
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
    paneInputs: [...document.querySelectorAll('#questionsPane .lr-inp__box')].map(i => i.value).join('|'),
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
  const r5 = await page.evaluate(() => [...document.querySelectorAll('#questionsPane .lr-inp__box')].map(i => i.value).join('|'));
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
    img: !!document.querySelector('#questionsPane .lr-qs__imglink img'),
    rows: [...document.querySelectorAll('#questionsPane .lr-qs__match')].map(r => r.innerText.replace(/\s+/g, ' ')).join(' | '),
    emptyOpts: [...document.querySelectorAll('#questionsPane .lr-opt')].filter(o => !o.children[1].textContent.trim()).length,
    nums: [...document.querySelectorAll('#questionsPane .lr-qnums .lr-qnum')].map(n => n.textContent + (n.classList.contains('is-err') ? '!' : '')).join(' '),
    marks: [...document.querySelectorAll('#questionsPane .lr-opt')].map(o => o.querySelector('.lr-opt__mark').textContent).filter(Boolean).join(','),
  }));
  check('map + multi recognised', g0.kinds === 'map,multi,choice', g0.kinds);
  check('map shows the plan and one row per question (no blank options)', g0.img && g0.emptyOpts === 0 && /Children's corner 1 ?C/.test(g0.rows) && /Study rooms 2 ?B ?E/.test(g0.rows), g0);
  check('multi shows both numbers and shared options', g0.nums === '4 5!' && g0.marks.startsWith('你选 · 对,你选,答案'), g0);
  await page.click('#questionsPane .lr-qs__stem[data-q="4"]');
  const qx = await page.evaluate(() => (document.querySelector('#questionsPane .lr-qx') || {}).innerText || '');
  check('multi explanation lists both letters', /你选\s*B、C/.test(qx) && /正确答案\s*B、D（不分先后）/.test(qx), qx);

  await page.click('.mode-btn[data-mode="redo"]');
  await page.click('#scriptBtn');   // 上一篇选了显示原文，这里关掉，看卷子
  const g1 = await page.evaluate(() => ({
    paper: !document.getElementById('paperPane').hidden,
    rows: document.querySelectorAll('#paperQs .lr-letrow').length,
    letters: [...document.querySelectorAll('#paperQs .lr-letrow')].map(r => r.querySelectorAll('.lr-letter').length).join(','),
    multi: document.querySelectorAll('#paperQs .lr-pick--multi .lr-pick__opt').length,
    hint: (document.querySelector('#paperQs .lr-pick__hint') || {}).textContent,
  }));
  check('redo: map letters per question, multi is checkboxes', g1.paper && g1.rows === 3 && g1.letters === '5,5,5' && g1.multi === 5 && g1.hint === '选 2 个 · 已选 0', g1);
  const letter = (q, k) => page.click(`#paperQs .lr-letter[data-q="${q}"][data-k="${k}"]`);
  await letter('1', 'C'); await letter('2', 'E'); await letter('2', 'E'); await letter('2', 'B');
  const multiOpt = (k, force) => page.click(`#paperQs .lr-pick--multi .lr-pick__opt[data-k="${k}"]`, { force: !!force });
  await multiOpt('B'); await multiOpt('D'); await multiOpt('E', true);   // 选够了，第三个点了也没用
  const g2 = await page.evaluate(() => ({
    on: [...document.querySelectorAll('#paperQs .lr-pick--multi .lr-pick__opt.is-on')].map(b => b.dataset.k).join(''),
    dimE: document.querySelector('#paperQs .lr-pick--multi .lr-pick__opt[data-k="E"]').getAttribute('aria-disabled'),
    hint: document.querySelector('#paperQs .lr-pick__hint').textContent,
    letters: [...document.querySelectorAll('#paperQs .lr-letter.is-on')].map(b => b.dataset.q + b.dataset.k).join(','),
    nums: [...document.querySelectorAll('#paperQs .lr-unit[data-unit="4"] .lr-qnum')].map(n => n.className.includes('is-done') ? 'x' : 'o').join(''),
  }));
  check('multi stops at two letters and greys the rest', g2.on === 'BD' && g2.dimE === 'true' && /已选 2，选够了/.test(g2.hint) && g2.nums === 'xx', g2);
  check('letter buttons toggle', g2.letters === '1C,2B', g2.letters);
  await multiOpt('D'); await multiOpt('E'); await multiOpt('E'); await multiOpt('D');
  await page.click('#paperQs .lr-pick:not(.lr-pick--multi) .lr-pick__opt[data-k="B"]');
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
      row2: [...document.querySelectorAll('#questionsPane .lr-qs__match')][1].innerText.replace(/\s+/g, ' ') };
  });
  check('map + multi graded (multi in either order)', g4.score === '4/6' && g4.ans === '1Cr 2Bw 3-b 4Br 5Dr 6Br', g4);
  check('map row shows your wrong letter and the right one', /2 ?B ?E/.test(g4.row2), g4.row2);

  // ---------- 3. 版式里选字母的配对（小下拉） ----------
  await openByTitle(page, /^Part 2$/);
  await page.click('.mode-btn[data-mode="redo"]');
  const x0 = await page.evaluate(() => ({ sels: [...document.querySelectorAll('#paperQs .lr-pickchip__sel')].map(s => s.dataset.q).join(','), first: document.querySelector('#paperQs .lr-pickchip__sel').options[0].textContent }));
  check('blanks in a matching layout become dropdowns', x0.sels === '12,13,14' && x0.first === '选', x0);
  await page.selectOption('#paperQs .lr-pickchip__sel[data-q="12"]', 'A');
  const used = await page.evaluate(() => [...document.querySelector('#paperQs .lr-pickchip__sel[data-q="13"]').options].map(o => o.textContent).join(' | '));
  check('a letter used elsewhere says where', /A.*（已填在 12）/.test(used), used);
  await page.selectOption('#paperQs .lr-pickchip__sel[data-q="13"]', 'B');
  await page.selectOption('#paperQs .lr-pickchip__sel[data-q="14"]', 'C');
  await page.click('#paperQs .lr-pick__opt[data-k="C"]');
  await page.click('#redoCard .ui-btn--primary');
  const x1 = await page.evaluate(() => document.getElementById('submitText').textContent);
  check('all answered message', x1 === '都答完了，交卷后马上判分。', x1);
  await page.click('#submitConfirmBtn');
  await page.waitForFunction(() => state.mode === 'answers', null, { timeout: 5000 });
  const x2 = await page.evaluate(() => { const a = state.exam.attempts[state.attemptIdx]; return `${a.correct}/${a.total}`; });
  check('matching graded', x2 === '4/4', x2);

  // ---------- 暗色 + 手机 ----------
  await page.evaluate(() => localStorage.setItem('ui-theme', 'dark'));
  await page.reload();
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  await openByTitle(page, /Greenfield Library Tour/);
  await page.click('.mode-btn[data-mode="redo"]');
  await page.click('#paperQs .lr-letter[data-q="1"][data-k="C"]');
  await page.click('#paperQs .lr-pick--multi .lr-pick__opt[data-k="B"]');
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
  check('no page errors (phone)', errors.length === 0, errors);

  console.log(`${engine}: ${pass}/${pass + fail} passed`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });

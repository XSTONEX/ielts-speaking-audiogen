// 九分学长 JSON 导入的浏览器检查（沙盒、编造数据）：
// 粘贴 → 预解析 → 导入（真的从沙盒下载音频、不转录）→ 翻译因为没有 key 停下 → 补上编的译文 →
// 字幕上的题号 / 答案下划线 / 看题静音 → 题目栏的划线、出处、解析 → 再导入第二次做题 → 切换做题记录。
// 用法见 README；每跑一次前先重灌 seed.py 和 jiufen_data.py。
const path = require('path');
const { execFileSync } = require('child_process');
const pw = require(process.env.PLAYWRIGHT_CORE);
const engine = process.argv[2] || 'chromium';
const sb = process.env.LR_SANDBOX;
const fake = path.join(__dirname, 'jiufen_fake_translate.py');
const BASE = (process.env.LR_BASE_URL || 'http://localhost:5073').replace(/\/$/, '');
const token = JSON.parse(require('fs').readFileSync(`${sb}/e2e_tokens.json`, 'utf8')).demo;
let pass = 0, fail = 0;
const check = (name, ok, got) => { ok ? pass++ : fail++; console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${ok ? '' : '  -> ' + JSON.stringify(got)}`); };
(async () => {
  const browser = await pw[engine].launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(`${BASE}/login`);
  await page.evaluate(t => localStorage.setItem('authToken', t), token);
  await page.goto(`${BASE}/listening_review`);
  await page.waitForFunction(() => typeof state !== 'undefined' && state.projects.length > 0);
  const pasteJson = async (file) => page.evaluate(async (file) => {
    openUploadModal(); switchTab('json');
    const text = await (await fetch('/static/e2e/' + file)).text();
    const dt = new DataTransfer(); dt.setData('text/plain', text);
    document.getElementById('jsonPaste').dispatchEvent(new ClipboardEvent('paste', { clipboardData: dt, bubbles: true, cancelable: true }));
  }, file);
  await pasteJson('e2e_single.json');
  await page.waitForFunction(() => !document.getElementById('uploadJsonBtn').disabled, null, { timeout: 5000 }).catch(() => {});
  const pv = await page.evaluate(() => ({ paste: document.getElementById('jsonPaste').value.length, bar: document.getElementById('jsonFileName').textContent, text: document.getElementById('jsonPreview').innerText, btn: document.getElementById('uploadJsonBtn').textContent }));
  check('paste not shown in box', pv.paste === 0, pv.paste);
  check('preview summary', /单篇练习/.test(pv.text) && /9 月 24 日交卷/.test(pv.text) && /用时 5:03/.test(pv.text), pv.text);
  check('preview stats', /答对 3 \/ 5/.test(pv.text) && /错 Q3/.test(pv.text) && /没答 Q4/.test(pv.text) && /划线 5 处/.test(pv.text), pv.text);
  check('import button', pv.btn === '导入 1 个 Part', pv.btn);
  await page.click('#uploadJsonBtn');
  await page.waitForFunction(() => document.getElementById('uploadModal').hidden, null, { timeout: 5000 });
  await page.waitForFunction(() => state.projects.some(p => p.source_type === 'jiufen' && p.status === 'error'), null, { timeout: 15000 });
  const card = await page.evaluate(() => { const p = state.projects.find(p => p.source_type === 'jiufen'); return { title: p.title, phase: p.error_phase, err: p.error }; });
  check('downloaded, skipped ASR, stopped at translation (no key)', card.phase === 'polish' && /WILDAPI_API_KEY/.test(card.err), card);
  execFileSync('python3', [fake, sb]);
  await page.evaluate(async () => { await loadProjects(); const p = state.projects.find(p => p.source_type === 'jiufen'); await openProject(p.id); });
  await page.waitForSelector('#questionsPane .lr-blank');
  const d = await page.evaluate(() => ({
    meta: document.getElementById('detailMeta').textContent,
    score: document.getElementById('sideScoreNum').textContent,
    src: document.getElementById('sideSrc').textContent,
    qtags: [...document.querySelectorAll('.lr-qtag')].map(e => e.textContent + '@' + e.closest('.lr-line').dataset.segId).join(' '),
    ans: [...document.querySelectorAll('.lr-ans')].map(e => e.textContent).join(','),
    hl: [...document.querySelectorAll('#questionsPane .lr-hl')].map(e => e.textContent).join(','),
    gap: document.querySelector('.lr-gap') && document.querySelector('.lr-gap').textContent,
  }));
  check('header meta', /九分学长/.test(d.meta), d.meta);
  check('side score + source', d.score === '3/5' && d.src === '九分学长 · 9 月 24 日交卷 · 用时 5:03', d);
  check('Q tags on answer sentences', d.qtags === 'Q1@5 Q2@6 Q3@7 Q4@8 Q5@9', d.qtags);
  check('answer underlines', d.ans === 'twelve,passport,mill,seven', d.ans);
  check('highlights in layout and choice', d.hl === 'Half-day,old,under,electric,steep', d.hl);
  check('silence divider', /^看题时间 0:07–0:33，没有声音$/.test(d.gap || ''), d.gap);
  await page.click('#questionsPane .lr-blank[data-q="3"]');
  const s = await page.evaluate(() => ({ evi: document.querySelector('.lr-evi .lr-evi__head') && document.querySelector('.lr-evi .lr-evi__head').innerText, inBand: [...document.querySelectorAll('.lr-evi .lr-line')].map(e => e.dataset.segId).join(','), qx: document.querySelector('#questionsPane .lr-qx') && document.querySelector('#questionsPane .lr-qx').innerText }));
  check('evidence band', /Q3 出处 · 0:48–0:50/.test(s.evi || '') && s.inBand === '7', s);
  check('explanation', /你的答案\s*hill/.test(s.qx || '') && /正确答案\s*mill/.test(s.qx || '') && /干扰/.test(s.qx || ''), s.qx);
  await page.click('#questionsPane [data-act="q-close"]');
  check('collapse', await page.evaluate(() => !document.querySelector('.lr-evi') && !document.querySelector('.lr-qx')), null);
  // 第二次做题
  await page.evaluate(() => backToList());
  await pasteJson('e2e_single_again.json');
  await page.waitForFunction(() => !document.getElementById('uploadJsonBtn').disabled, null, { timeout: 5000 }).catch(() => {});
  const again = await page.evaluate(() => document.getElementById('jsonPreview').innerText);
  check('re-import offers update', /导入过/.test(again) && /更新那一篇/.test(again) && /第 2 次做/.test(again) && /上次 3 \/ 5/.test(again), again);
  await page.click('#uploadJsonBtn');
  await page.waitForFunction(() => document.getElementById('uploadModal').hidden, null, { timeout: 5000 });
  await page.evaluate(async () => { await loadProjects(); const p = state.projects.find(p => p.source_type === 'jiufen'); await openProject(p.id); });
  await page.waitForSelector('#attemptBox:not([hidden])');
  await page.click('#attemptBtn');
  await page.click('#attemptMenu [data-i="0"]');
  const sw = await page.evaluate(() => ({ btn: document.getElementById('attemptBtnText').textContent, score: document.getElementById('sideScoreNum').textContent, hl: document.querySelectorAll('#questionsPane .lr-hl').length }));
  check('attempt switch', sw.btn === '第 1 次 · 9 月 24 日交卷' && sw.score === '3/5' && sw.hl === 5, sw);

  // 多列表格（编的 4 列表格题，形状照线上一篇 Part 1）：表头不能被挤成一个字母一行，解析放在表格下面
  await page.evaluate(() => {
    localStorage.removeItem('listening-side-width');
    applySideWidth();
    const q = (num, answer) => ({ num, text: '', options: [], answer, evidence: null, analysis: { explain: '编的解析', trap: '', extra: [] } });
    state.exam.groups.push({
      id: 'g-table', range: 'Questions 6–8', kind: 'blank', instruction_html: 'Complete the table below.', image: '', title: '', options: [],
      content_html: '<table><tr><th></th><th>Mia (daughter)</th><th>Leo (son)</th><th>Ava (daughter)</th></tr>'
        + '<tr><th>Foods they cannot eat</th><td>none</td><td><span class="ir-blank" data-q="6">6</span></td><td><span class="ir-blank" data-q="7">7</span></td></tr>'
        + '<tr><th>Classes they want to join</th><td><span class="ir-blank" data-q="8">8</span></td><td>(the same)</td><td>judo</td></tr></table>',
      questions: [q('6', 'eggs'), q('7', 'nuts'), q('8', 'ballet')],
    });
    selectQuestion('7');
  });
  const tb = await page.evaluate(() => {
    const wrap = document.querySelector('#questionsPane .lr-tblwrap');
    const table = wrap && wrap.querySelector('table');
    const qx = document.querySelector('#questionsPane .lr-qx');
    const side = document.getElementById('notesSide');
    return {
      side: Math.round(side.getBoundingClientRect().width),
      headCol: table && Math.round(table.rows[1].cells[0].getBoundingClientRect().width),
      fits: wrap && wrap.scrollWidth <= wrap.clientWidth + 1,
      sideScrollsSideways: side.scrollWidth > side.clientWidth + 1,
      selCell: (document.querySelector('.lr-tbl .is-sel') || {}).textContent,
      head: qx && (qx.querySelector('.lr-qx__head') || {}).textContent,
      afterTable: qx && qx.previousElementSibling && qx.previousElementSibling.className,
      font: qx && getComputedStyle(qx.querySelector('.lr-qx__text')).fontSize,
    };
  });
  check('imported article panel defaults to 440', tb.side === 440, tb);
  check('table fits without squeezing headers', tb.fits && tb.headCol >= 80 && !tb.sideScrollsSideways, tb);
  check('explanation under the table, names the cell', /lr-tbl(hint|wrap)/.test(tb.afterTable || '') && tb.head === '第 7 题 · Ava (daughter) · Foods they cannot eat' && tb.font === '15px', tb);

  // 拖分隔条：往左拖 120，右栏变宽并记住；重新打开还是这个宽；双击恢复 440
  const grip = await page.evaluate(() => { const r = document.querySelector('.lr-split__grip').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.move(grip.x, grip.y);
  await page.mouse.down();
  await page.mouse.move(grip.x - 60, grip.y, { steps: 3 });
  const badge = await page.evaluate(() => document.getElementById('sideSplitBadge').textContent);
  await page.mouse.move(grip.x - 120, grip.y, { steps: 3 });
  await page.mouse.up();
  const dragged = await page.evaluate(() => ({ side: Math.round(document.getElementById('notesSide').getBoundingClientRect().width), saved: localStorage.getItem('listening-side-width') }));
  check('drag widens panel and remembers it', dragged.side === 560 && dragged.saved === '560' && /右栏 500 px · 双击恢复 440/.test(badge), { dragged, badge });
  await page.evaluate(async () => { backToList(); await loadProjects(); const p = state.projects.find(p => p.source_type === 'jiufen'); await openProject(p.id); });
  check('width kept after reopening', await page.evaluate(() => Math.round(document.getElementById('notesSide').getBoundingClientRect().width)) === 560, null);
  const grip2 = await page.evaluate(() => { const r = document.querySelector('.lr-split__grip').getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
  await page.mouse.dblclick(grip2.x, grip2.y);
  const reset = await page.evaluate(() => ({ side: Math.round(document.getElementById('notesSide').getBoundingClientRect().width), saved: localStorage.getItem('listening-side-width') }));
  check('double-click restores 440', reset.side === 440 && reset.saved === null, reset);
  check('no page errors', errors.length === 0, errors);
  console.log(`${engine}: ${pass}/${pass + fail} passed`);
  await browser.close();
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });

// 题目栏划词、原文和题目栏之间的分割条、单词发音（有道词典，点的时候实时取）。
// 文章是现导入的：tests/fixtures/jiufen_reading_attempt.json（编的「The Glass Bridge」）再补两组编的题——
// 一组选择题（题干 + 选项）、一组配对题（题组公共选项），加上原来那组填空的「原题版式」，题目栏里能划词的几种文字都有。
// 标题以「（chromium）」「（webkit）」结尾，套件前后由 lib.cleanup 删掉（高亮跟着文章一起没）。
const fs = require('fs');
const path = require('path');

const FIXTURE = path.join(__dirname, '..', '..', 'fixtures', 'jiufen_reading_attempt.json');

function examJson() {
  const raw = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  const groups = raw.data.attempt.parts[0].groups;
  groups.push({
    id: '920', displayOrder: 3, qRange: 'Questions 6-7', type: 'single-choice', contentHtml: null, options: [],
    description: 'Choose the correct letter, <strong>A, B, C or D</strong>.',
    questions: [
      { id: '961', qNumber: '6', question: 'Why did the town council relocate the lanterns?', rightAnswer: 'B', userAnswer: 'A', state: '2', sentenceIndex: '1-1', analyses: [], displayOrder: 1,
        options: [{ displayOrder: 1, optionNum: 'A', option: 'to attract night-time tourists' }, { displayOrder: 2, optionNum: 'B', option: 'to reduce glare for passing sailors' }] },
      { id: '962', qNumber: '7', question: 'What does the writer say about the handrails?', rightAnswer: 'A', userAnswer: 'A', state: '1', sentenceIndex: '2-2', analyses: [], displayOrder: 2,
        options: [{ displayOrder: 1, optionNum: 'A', option: 'they were added after complaints' }, { displayOrder: 2, optionNum: 'B', option: 'they were part of the first design' }] },
    ],
  });
  groups.push({
    id: '930', displayOrder: 4, qRange: 'Questions 8', type: 'matching', contentHtml: null,
    options: [{ displayOrder: 1, optionNum: 'A', option: 'a reluctant volunteer' }, { displayOrder: 2, optionNum: 'B', option: 'a former lighthouse keeper' }],
    description: 'Match the statement with the correct person, <strong>A or B</strong>.',
    questions: [{ id: '981', qNumber: '8', question: 'suggested painting the railings blue', rightAnswer: 'B', userAnswer: 'B', state: '1', analyses: [], displayOrder: 1, options: [] }],
  });
  return JSON.stringify(raw);
}

module.exports = async function suiteQuestion({ cfg, browser, engine, t, lib }) {
  const BASE = cfg.baseUrl;
  const TITLE = `Harbour Questions（${engine}）`;
  const ok = (c, w) => t.ok(c, w);
  const shotDir = path.join(cfg.out, 'question');
  fs.mkdirSync(shotDir, { recursive: true });

  // ---- 导入文章（不翻译） ----
  const api = await lib.apiContext(cfg);
  let id;
  try {
    const r = await api.post('/intensive_import', { data: { raw: examJson(), translate: false, titles: [TITLE], category: 'Reading' } });
    const d = await r.json();
    if (!d.success) throw new Error('导入失败 ' + JSON.stringify(d));
    id = d.ids[0];
  } finally {
    await api.dispose();
  }
  const serverHighlights = async () => {
    const a = await lib.apiContext(cfg);
    try { return (await (await a.get('/intensive_article/' + encodeURIComponent(id))).json()).article.highlights || []; } finally { await a.dispose(); }
  };

  // 有道的发音请求：记下来、拦掉（测试不连外网），页面应该接着去取以前存过的 /vocab_audio
  async function watchAudio(ctx) {
    const youdao = [], stored = [], paid = [];
    await ctx.route(/dict\.youdao\.com/, route => { youdao.push(new URL(route.request().url()).searchParams.get('audio') || ''); route.fulfill({ status: 404, contentType: 'text/plain', body: '' }); });
    ctx.on('request', r => {
      const u = r.url();
      if (/\/vocab_audio\/(?!articles\/)/.test(u)) stored.push(decodeURIComponent(u.split('/').pop()));
      if (/\/(generate_article_audio|prepare_article_audio|generate_audio_segment|combine_audio_segments)/.test(u)) paid.push(u);
    });
    return { youdao, stored, paid };
  }
  function watchErrors(p) {
    const errs = [];
    const expected = s => /status of 404/.test(s) || /NotSupportedError|发音/.test(s);
    p.on('pageerror', e => errs.push(String(e)));
    p.on('console', m => { if (m.type() === 'error' && !expected(m.text())) errs.push('console ' + m.text()); });
    return errs;
  }
  // 题目栏里某段文字（data-hk 前缀 + 包含的词）里一个词的位置
  const wordBox = (p, hkRe, word, noScroll) => p.evaluate(([hkRe, word, noScroll]) => {
    const b = [...document.querySelectorAll('#examPane [data-hk]')].find(x => new RegExp(hkRe).test(x.dataset.hk) && x.textContent.includes(word));
    if (!b) return null;
    const d = b.closest('details'); if (d) d.open = true;
    if (!noScroll) b.scrollIntoView({ block: 'center' });
    const nodes = []; const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) nodes.push(n);
    const node = nodes.find(n => n.nodeValue.includes(word)); const i = node.nodeValue.indexOf(word);
    const r = document.createRange(); r.setStart(node, i); r.setEnd(node, i + word.length); const rc = r.getBoundingClientRect();
    return { hk: b.dataset.hk, x: rc.left + rc.width / 2, y: rc.top + rc.height / 2, x0: rc.left, x1: rc.right };
  }, [hkRe.source, word, !!noScroll]);
  const state = p => p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, meaning: document.getElementById('meaningBox').style.display, text: selectionRange && selectionRange.text, qk: selectionRange && selectionRange.qk, btn: document.querySelector('#floatBox .ir-pop-main').textContent, disabled: document.querySelector('#floatBox .ir-pop-main').disabled }));

  // ==================== 桌面 ====================
  {
    const ctx = await lib.newContext(cfg, browser, { viewport: { width: 1440, height: 900 } });
    const audio = await watchAudio(ctx);
    const p = await lib.newPage(ctx, 10000);
    const errs = watchErrors(p);
    let acceptNext = false; const dialogs = [];
    p.on('dialog', d => { dialogs.push(d.message()); if (acceptNext) { acceptNext = false; d.accept(); } else d.dismiss(); });
    const sleep = ms => p.waitForTimeout(ms);
    try {
      await lib.openList(p, cfg);
      await p.evaluate(() => { try { localStorage.removeItem('intensiveExamWidth'); localStorage.removeItem('intensiveHideAnswers'); } catch (e) {} });
      await lib.openArticle(p, id);
      await p.waitForSelector('#examPane .ir-q');

      // ---- 能划词的题目文字都带上了块名 ----
      const hks = await p.evaluate(() => [...document.querySelectorAll('#examPane [data-hk]')].map(b => b.dataset.hk));
      ok(['g0.q1', 'g1.layout', 'g1.q4', 'g2.q6', 'g2.q6.A', 'g2.q6.B', 'g3.oA', 'g3.oB', 'g3.q8'].every(k => hks.includes(k)), `question text blocks carry data-hk ${JSON.stringify(hks)}`);

      // ---- 题干：双击选词 → 浮层 → 写释义 → 保存 ----
      async function highlightIn(hkRe, word, meaning) {
        await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
        await p.mouse.click(5, 450);
        const w = await wordBox(p, hkRe, word);
        if (!w) { ok(false, `no block for ${word}`); return null; }
        await p.mouse.dblclick(w.x, w.y); await sleep(150);
        const st = await state(p);
        ok(st.float === 'block' && st.text === word && st.qk === w.hk && st.btn === '高亮' && !st.disabled, `double-click "${word}" in ${w.hk} → highlight popover ${JSON.stringify(st)}`);
        await p.click('#floatBox .ir-pop-main');
        await p.fill('#meaningInput', meaning);
        await p.press('#meaningInput', 'Enter');
        await p.waitForFunction(m => (highlights || []).some(h => h.meaning === m), meaning);
        await sleep(150);
        return w.hk;
      }
      const before = Number(await p.textContent('#vocabCount') || 0);
      const k1 = await highlightIn(/^g2\.q6$/, 'relocate', 'e2e 搬迁');
      const k2 = await highlightIn(/^g2\.q6\.B$/, 'glare', 'e2e 强光');
      const k3 = await highlightIn(/^g3\.oA$/, 'reluctant', 'e2e 不情愿的');
      const k4 = await highlightIn(/^g1\.layout$/, 'engineers', 'e2e 工程师');
      const marks = () => p.evaluate(() => [...document.querySelectorAll('#examPane mark.hl')].map(m => ({ hk: m.closest('[data-hk]').dataset.hk, text: m.firstChild.nodeValue, tip: (m.querySelector('.tooltip') || {}).textContent })));
      const m1 = await marks();
      ok(JSON.stringify(m1.map(m => m.text).sort()) === JSON.stringify(['engineers', 'glare', 'relocate', 'reluctant']) && m1.every(m => /^e2e /.test(m.tip)), `four marks drawn in the questions ${JSON.stringify(m1)}`);
      ok(Number(await p.textContent('#vocabCount')) === before + 4, 'vocab count +4');
      const sh = await serverHighlights();
      ok(JSON.stringify(sh.filter(h => h.qk).map(h => [h.qk, h.text]).sort()) === JSON.stringify([[k4, 'engineers'], [k3, 'reluctant'], [k1, 'relocate'], [k2, 'glare']].sort()), `saved with qk ${JSON.stringify(sh.map(h => [h.qk, h.text]))}`);
      ok(await p.evaluate(() => document.querySelectorAll('#vContent mark.hl').length === 0), 'question highlights are not painted into the passage');

      // ---- 题目里的词就算在原文里出现，也算「已划过」；反过来也一样 ----
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      const eng = await p.evaluate(() => { const pp = [...document.querySelectorAll('#vContent p.en')].find(p => /Engineers/.test(p.textContent)); pp.scrollIntoView({ block: 'center' }); const tn = [...pp.childNodes].find(n => n.nodeType === 3 && n.nodeValue.includes('Engineers')); const i = tn.nodeValue.indexOf('Engineers'); const r = document.createRange(); r.setStart(tn, i); r.setEnd(tn, i + 9); const rc = r.getBoundingClientRect(); return { x: rc.left + rc.width / 2, y: rc.top + rc.height / 2 }; });
      await p.mouse.dblclick(eng.x, eng.y); await sleep(150);
      const dup = await state(p);
      ok(dup.float === 'block' && dup.disabled && dup.btn === '已划过', `"Engineers" in the passage counts as already highlighted ${JSON.stringify(dup)}`);

      // ---- 跨两段题目文字的选区只提示 ----
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      const a = await wordBox(p, /^g2\.q7$/, 'handrails'), b2 = await wordBox(p, /^g2\.q7\.A$/, 'added', true);
      await p.mouse.move(a.x0 + 2, a.y); await p.mouse.down(); await p.mouse.move(b2.x1 - 1, b2.y, { steps: 8 }); await p.mouse.up(); await sleep(150);
      const cross = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, tip: [...document.querySelectorAll('.temp-tooltip')].map(t => t.textContent).join() }));
      ok(cross.float === 'none' && /同一句题目/.test(cross.tip), `selection across stem + option is refused ${JSON.stringify(cross)}`);

      // ---- 悬停看释义；点一下读出来：先有道，没有再退回以前存过的 ----
      const rel = await p.$('#examPane mark.hl[data-hid]');
      const relBox = await wordBox(p, /^g2\.q6$/, 'relocate');
      await p.mouse.move(relBox.x, relBox.y); await sleep(150);
      const tipShown = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl')].find(m => m.firstChild.nodeValue === 'relocate'); return getComputedStyle(m.querySelector('.tooltip')).display; });
      ok(tipShown === 'block', `hover shows the meaning bubble (${tipShown})`);
      audio.youdao.length = 0; audio.stored.length = 0;
      await p.mouse.click(relBox.x, relBox.y); await sleep(500);
      ok(audio.youdao[0] === 'relocate' && audio.stored[0] === 'relocate', `click → Youdao first, then the old stored file ${JSON.stringify(audio)}`);
      ok(rel !== null, 'mark element exists');
      // 原文里的高亮也一样走有道
      const lh = await p.evaluate(() => fetch('/intensive_add_highlight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: currentArticle.id, start: currentArticle.content_text.indexOf('bridge'), end: currentArticle.content_text.indexOf('bridge') + 6, meaning: 'e2e 桥', text: 'bridge' }) }).then(r => r.json()));
      ok(lh.success && !('qk' in lh.highlight), 'passage highlight via API has no qk');

      // ---- 刷新：原文和题目里的高亮都画回来；词汇面板列出来，题目里的带「第几题」排在后面 ----
      await lib.settle(p); await p.reload();
      await p.waitForFunction(() => currentArticle && document.querySelectorAll('#examPane mark.hl').length >= 4); await sleep(300);
      const m2 = await marks();
      ok(m2.length === 4 && await p.evaluate(() => document.querySelectorAll('#vContent mark.hl').length === 1), `after reload: 4 question marks + 1 passage mark ${JSON.stringify(m2.map(m => m.text))}`);
      await p.click('#vocabToggle'); await sleep(300);
      const rows = await p.evaluate(() => [...document.querySelectorAll('#hpBody .ir-vi')].map(r => r.querySelector('.ir-vi-word').textContent));
      ok(JSON.stringify(rows) === JSON.stringify(['bridge', 'engineers题目', 'relocate第 6 题', 'glare第 6 题', 'reluctant题目']), `vocab panel order + tags ${JSON.stringify(rows)}`);
      audio.youdao.length = 0;
      await p.click('#hpBody .ir-vi:nth-child(3) .ir-vi-text'); await sleep(300);
      ok(audio.youdao[0] === 'relocate', `vocab row click plays via Youdao ${JSON.stringify(audio.youdao)}`);
      // 跳到题目里的词：题目栏滚过去、闪一下
      await p.evaluate(() => { document.getElementById('examPane').scrollTop = 0; });
      await p.click('#hpBody .ir-vi:nth-child(5) [title="跳到原文"]'); await sleep(250);
      const jump = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl')].find(m => m.firstChild.nodeValue === 'reluctant'); const r = m.getBoundingClientRect(), pr = document.getElementById('examPane').getBoundingClientRect(); return { active: m.classList.contains('active'), inView: r.top > pr.top && r.bottom < pr.bottom, scrolled: document.getElementById('examPane').scrollTop > 0 }; });
      ok(jump.active && jump.inView && jump.scrolled, `jump from the vocab panel scrolls the questions to the word ${JSON.stringify(jump)}`);
      await p.click('#highlightsPanel .ir-panel-head .ir-icon-btn'); await sleep(250);

      // ---- 右键删除：只拿掉这一个，题目栏不跳回顶上 ----
      const gl = await wordBox(p, /^g2\.q6\.B$/, 'glare');
      const st0 = await p.evaluate(() => document.getElementById('examPane').scrollTop);
      acceptNext = true;
      await p.mouse.click(gl.x, gl.y, { button: 'right' }); await sleep(600);
      const del = await p.evaluate(() => ({ marks: [...document.querySelectorAll('#examPane mark.hl')].map(m => m.firstChild.nodeValue).sort(), scroll: document.getElementById('examPane').scrollTop, count: document.getElementById('vocabCount').textContent, text: document.querySelector('#examPane [data-hk="g2.q6.B"]').textContent }));
      ok(JSON.stringify(del.marks) === JSON.stringify(['engineers', 'relocate', 'reluctant']) && Math.abs(del.scroll - st0) < 2 && del.text === 'to reduce glare for passing sailors', `right-click delete removes one mark, keeps scroll ${JSON.stringify({ ...del, st0 })}`);
      ok(!(await serverHighlights()).some(h => h.text === 'glare'), 'deleted on the server');

      // ---- 写释义时点别处，「保存」照样存得上（以前点正文会把选区清掉） ----
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      const sail = await wordBox(p, /^g2\.q6\.B$/, 'sailors');
      await p.mouse.dblclick(sail.x, sail.y); await sleep(150);
      await p.click('#floatBox .ir-pop-main');
      await p.mouse.click(200, 450); await sleep(100);   // 点一下左边的原文
      await p.fill('#meaningInput', 'e2e 水手'); await p.click('#meaningBox .ir-pop-main');
      await p.waitForFunction(() => (highlights || []).some(h => h.meaning === 'e2e 水手'), null, { timeout: 3000 }).catch(() => {});
      ok(await p.evaluate(() => (highlights || []).some(h => h.text === 'sailors' && h.qk === 'g2.q6.B')), 'clicking elsewhere while writing the meaning does not lose the selection');

      // ---- 多行释义：贴进来的换行留着，Shift+回车再加一行，回车保存；气泡里一行一行显示 ----
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      await p.mouse.click(5, 450);
      const hr = await wordBox(p, /^g2\.q7\.A$/, 'complaints');
      await p.mouse.dblclick(hr.x, hr.y); await sleep(150);
      await p.click('#floatBox .ir-pop-main');
      const h1 = await p.evaluate(() => document.getElementById('meaningInput').offsetHeight);
      await p.fill('#meaningInput', 'n. e2e 扶手\n  v. e2e 装栏杆  ');
      await p.press('#meaningInput', 'Meta+ArrowDown'); await p.press('#meaningInput', 'Shift+Enter'); await p.keyboard.type('adj. e2e 第三行');
      const typed = await p.evaluate(() => { const el = document.getElementById('meaningInput'); return { v: el.value, h: el.offsetHeight, open: document.getElementById('meaningBox').style.display }; });
      ok(typed.open === 'block' && typed.v.split('\n').length === 3 && typed.h > h1 * 1.8, `meaning box keeps line breaks and grows ${JSON.stringify({ ...typed, h1 })}`);
      await p.press('#meaningInput', 'Enter');
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'complaints'), null, { timeout: 3000 }).catch(() => {});
      const mlSaved = (await serverHighlights()).find(h => h.text === 'complaints');
      ok(mlSaved && mlSaved.meaning === 'n. e2e 扶手\nv. e2e 装栏杆\nadj. e2e 第三行', `multi-line meaning saved, lines trimmed ${JSON.stringify(mlSaved && mlSaved.meaning)}`);
      const hrBox = await wordBox(p, /^g2\.q7\.A$/, 'complaints');
      await p.mouse.move(hrBox.x, hrBox.y); await sleep(150);
      const mlTip = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl')].find(m => m.firstChild.nodeValue === 'complaints'); const t = m.querySelector('.tooltip'); const cs = getComputedStyle(t); return { display: cs.display, ws: cs.whiteSpace, lines: Math.round((t.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)) / parseFloat(cs.lineHeight)) }; });
      ok(mlTip.display === 'block' && mlTip.ws === 'pre-line' && mlTip.lines === 3, `tooltip shows the meaning on 3 lines ${JSON.stringify(mlTip)}`);
      await p.click('#vocabToggle'); await sleep(300);
      const mlRow = await p.evaluate(() => { const r = [...document.querySelectorAll('#hpBody .ir-vi')].find(r => /complaints/.test(r.textContent)); const m = r && r.querySelector('.ir-vi-mean'); return m ? { ws: getComputedStyle(m).whiteSpace, lines: Math.round(m.clientHeight / parseFloat(getComputedStyle(m).lineHeight)) } : null; });
      ok(mlRow && mlRow.ws === 'pre-line' && mlRow.lines === 3, `vocab panel row shows 3 lines ${JSON.stringify(mlRow)}`);
      await p.click('#highlightsPanel .ir-panel-head .ir-icon-btn'); await sleep(250);

      // ==================== 分割条 ====================
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      const geo = () => p.evaluate(() => { const s = document.getElementById('examSplit').getBoundingClientRect(), e = document.getElementById('examPane').getBoundingClientRect(), c = document.getElementById('vContent').getBoundingClientRect(), b = document.querySelector('#viewer .ir-body').getBoundingClientRect(); return { split: s.left, exam: Math.round(e.width), examLeft: e.left, content: Math.round(c.width), body: Math.round(b.width), grip: getComputedStyle(document.querySelector('.ir-split-grip')).display, stored: localStorage.getItem('intensiveExamWidth') }; });
      const g0 = await geo();
      ok(g0.grip !== 'none' && Math.abs(g0.split - g0.examLeft) < 1 && g0.exam === Math.round(Math.min(g0.body * 0.46, 540)) && g0.stored === null, `splitter sits on the questions' left edge, default width ${JSON.stringify(g0)}`);
      const sy = 450;
      // 指上去：线和把手变成主题色
      await p.mouse.move(g0.split, sy); await sleep(200);
      const hov = await p.evaluate(() => ({ line: getComputedStyle(document.getElementById('examSplit'), '::after').backgroundColor, cursor: getComputedStyle(document.getElementById('examSplit'), '::before').cursor, grip: getComputedStyle(document.querySelector('.ir-split-grip')).borderColor }));
      ok(hov.line !== 'rgba(0, 0, 0, 0)' && hov.cursor === 'col-resize', `hover highlights the splitter ${JSON.stringify(hov)}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-split-hover.png`) });
      // 往左拖 200px：题目栏宽 200，原文窄 200，拖的过程中不选中文字
      await p.mouse.down(); await p.mouse.move(g0.split - 100, sy, { steps: 5 });
      const mid = await p.evaluate(() => ({ dragging: document.getElementById('examSplit').classList.contains('is-dragging'), sel: String(getSelection()) }));
      await p.mouse.move(g0.split - 200, sy, { steps: 5 }); await p.mouse.up(); await sleep(150);
      const g1 = await geo();
      ok(mid.dragging && mid.sel === '' && Math.abs(g1.exam - (g0.exam + 200)) <= 2 && Math.abs(g1.content - (g0.content - 200)) <= 2 && Number(g1.stored) === g1.exam, `drag left 200px widens the questions ${JSON.stringify({ mid, g1 })}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-split-wide.png`) });
      // 题目里的高亮跟着换行，位置还对
      ok(JSON.stringify((await marks()).map(m => m.text).sort()) === JSON.stringify(['complaints', 'engineers', 'relocate', 'reluctant', 'sailors']), 'marks survive the resize');
      // 刷新后还记得
      await lib.settle(p); await p.reload(); await p.waitForFunction(() => currentArticle && document.querySelector('#examPane .ir-q')); await sleep(300);
      const g2 = await geo();
      ok(Math.abs(g2.exam - g1.exam) <= 1, `width remembered after reload ${g2.exam} vs ${g1.exam}`);
      // 拖到最左 / 最右：原文至少 400，题目栏至少 320
      await p.mouse.move(g2.split, sy); await p.mouse.down(); await p.mouse.move(20, sy, { steps: 6 }); await p.mouse.up(); await sleep(150);
      const g3 = await geo();
      await p.mouse.move(g3.split, sy); await p.mouse.down(); await p.mouse.move(1430, sy, { steps: 6 }); await p.mouse.up(); await sleep(150);
      const g4 = await geo();
      ok(g3.content === 400 && g4.exam === 320, `clamped: passage ≥ 400, questions ≥ 320 ${JSON.stringify({ c: g3.content, e: g4.exam })}`);
      // 键盘：聚焦后 ← 加宽 24
      await p.focus('#examSplit'); await p.keyboard.press('ArrowLeft'); await sleep(100);
      const g5 = await geo();
      ok(g5.exam === 344, `ArrowLeft widens by 24 (${g4.exam} → ${g5.exam})`);
      // 双击恢复默认，本机记录也删掉
      await p.mouse.dblclick(g5.split, sy); await sleep(150);
      const g6 = await geo();
      ok(g6.exam === g0.exam && g6.stored === null, `double-click resets ${JSON.stringify(g6)}`);
      // 窗口变窄时跟着收：先拖到很宽，再把窗口缩到 1000
      await p.mouse.move(g6.split, sy); await p.mouse.down(); await p.mouse.move(500, sy, { steps: 6 }); await p.mouse.up(); await sleep(150);
      await p.setViewportSize({ width: 1000, height: 900 }); await sleep(300);
      const g7 = await geo();
      ok(g7.content >= 400 && g7.exam >= 320, `narrower window keeps ≥ 400px of passage ${JSON.stringify(g7)}`);
      // 821–900：原文 / 题目切换，没有分割条；切到「题目」照样能划词
      await p.setViewportSize({ width: 860, height: 900 }); await sleep(300);
      const narrow = await p.evaluate(() => ({ split: getComputedStyle(document.getElementById('examSplit')).display, tabs: getComputedStyle(document.getElementById('examTabs')).display }));
      ok(narrow.split === 'none' && narrow.tabs !== 'none', `821–900px: tabs, no splitter ${JSON.stringify(narrow)}`);
      await p.click('#examTabQ'); await sleep(200);
      const hw = await wordBox(p, /^g2\.q7$/, 'handrails');
      await p.mouse.dblclick(hw.x, hw.y); await sleep(150);
      const ns = await state(p);
      ok(ns.float === 'block' && ns.text === 'handrails' && ns.qk === 'g2.q7', `821–900px: selecting in the 题目 tab works ${JSON.stringify(ns)}`);
      await p.evaluate(() => cancelFloat());
      await p.setViewportSize({ width: 1440, height: 900 }); await sleep(200);
      await p.evaluate(() => { try { localStorage.removeItem('intensiveExamWidth'); } catch (e) {} });

      ok(audio.paid.length === 0, `no paid audio endpoints called ${JSON.stringify(audio.paid)}`);
      ok(errs.length === 0, `no page errors ${JSON.stringify(errs.slice(0, 5))}`);
    } catch (e) {
      await p.screenshot({ path: path.join(shotDir, `${engine}-desktop-crash.png`) }).catch(() => {});
      throw e;
    } finally {
      await ctx.close();
    }
  }

  // ==================== 手机 ====================
  {
    const device = engine === 'webkit'
      ? { viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 }
      : { viewport: { width: 360, height: 780 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 };
    const ctx = await lib.newContext(cfg, browser, device);
    const audio = await watchAudio(ctx);
    const p = await lib.newPage(ctx, 10000);
    const errs = watchErrors(p);
    p.on('dialog', d => d.dismiss());
    const sleep = ms => p.waitForTimeout(ms);
    // 桌面那段存下的高亮先清掉，手机这段从零开始
    {
      const a = await lib.apiContext(cfg);
      try { for (const h of await serverHighlights()) await a.post('/intensive_delete_highlight', { data: { id, highlight_id: h.id } }); } finally { await a.dispose(); }
    }
    try {
      await lib.openList(p, cfg);
      await lib.openArticle(p, id);
      ok(await p.evaluate(() => getComputedStyle(document.getElementById('examSplit')).display === 'none'), 'phone: no splitter');
      await p.tap('#examSheetBtn'); await sleep(400);
      // 翻到第 7 题
      for (let i = 0; i < 6; i++) { await p.tap('.ir-qs-nav [data-act="qs-next"]'); await sleep(120); }
      ok(await p.evaluate(() => document.querySelector('#examPane .ir-q.is-cur').dataset.num) === '7', 'phone: at question 7');
      // 长按选词（真点一下，再设选区）
      const w = await wordBox(p, /^g2\.q7$/, 'writer');
      await p.touchscreen.tap(w.x, w.y); await sleep(80);
      await p.evaluate(() => { const b = document.querySelector('#examPane [data-hk="g2.q7"]'); const n = b.firstChild; const i = n.nodeValue.indexOf('writer'); const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + 6); getSelection().removeAllRanges(); getSelection().addRange(r); });
      await sleep(600);
      const fb = await p.evaluate(() => { const f = document.getElementById('floatBox').getBoundingClientRect(), pane = document.getElementById('examPane').getBoundingClientRect(); return { shown: document.getElementById('floatBox').style.display, word: document.getElementById('popWord').textContent, btn: document.querySelector('#floatBox .ir-pop-main').textContent, bottom: Math.round(f.bottom), paneTop: Math.round(pane.top), qk: selectionRange && selectionRange.qk }; });
      ok(fb.shown === 'block' && fb.word === 'writer' && fb.btn === '划线并写释义' && fb.qk === 'g2.q7' && Math.abs(fb.bottom - fb.paneTop) <= 2, `phone: long-press in the question → action bar on top of the sheet ${JSON.stringify(fb)}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-phone-select.png`) });
      await p.tap('#floatBox .ir-pop-main'); await sleep(250);
      await p.fill('#meaningInput', 'e2e 作者');
      await p.tap('#meaningBox .ir-pop-main');
      await p.waitForFunction(() => (highlights || []).some(h => h.meaning === 'e2e 作者')); await sleep(300);
      const pm = await p.evaluate(() => { const m = document.querySelector('#examPane mark.hl'); return { text: m && m.firstChild.nodeValue, open: document.getElementById('examPane').classList.contains('is-open') }; });
      ok(pm.text === 'writer' && pm.open, `phone: saved, mark in the sheet, sheet still open ${JSON.stringify(pm)}`);
      // 点高亮：单词卡 + 有道
      audio.youdao.length = 0;
      const mw = await wordBox(p, /^g2\.q7$/, 'writer');
      await p.touchscreen.tap(mw.x, mw.y); await sleep(400);
      const card = await p.evaluate(() => ({ hidden: document.getElementById('wordCard').hidden, word: document.getElementById('wcWord').textContent, mean: document.getElementById('wcMean').textContent }));
      ok(!card.hidden && card.word === 'writer' && card.mean === 'e2e 作者' && audio.youdao[0] === 'writer', `phone: tap the mark → word card + Youdao ${JSON.stringify({ card, y: audio.youdao })}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-phone-card.png`) });
      await p.evaluate(() => history.back()); await sleep(400);
      await p.evaluate(() => history.back()); await sleep(400);
      // 词汇面板里跳过去：面板关掉，题目面板升起停在第 6 题，词在面板里看得见
      await p.evaluate(() => fetch('/intensive_add_highlight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: currentArticle.id, qk: 'g2.q6', start: 'Why did the town council '.length, end: 'Why did the town council '.length + 8, meaning: 'e2e 搬迁', text: 'relocate' }) }));
      await lib.settle(p); await p.reload(); await p.waitForFunction(() => currentArticle && document.querySelectorAll('#examPane mark.hl').length === 2); await sleep(300);
      await p.tap('#vocabToggle'); await sleep(400);
      const row = await p.evaluate(() => [...document.querySelectorAll('#hpBody .ir-vi')].findIndex(r => r.querySelector('.ir-vi-word').textContent.startsWith('relocate')));
      await p.tap(`#hpBody .ir-vi:nth-child(${row + 1}) [title="跳到原文"]`); await sleep(900);
      const j = await p.evaluate(() => { const pane = document.getElementById('examPane'); const m = [...pane.querySelectorAll('mark.hl')].find(m => m.firstChild.nodeValue === 'relocate'); const r = m.getBoundingClientRect(), pr = pane.getBoundingClientRect(); return { panel: document.getElementById('highlightsPanel').classList.contains('active'), open: pane.classList.contains('is-open'), cur: pane.querySelector('.ir-q.is-cur').dataset.num, inView: r.top >= pr.top && r.bottom <= pr.bottom && r.height > 0 }; });
      ok(!j.panel && j.open && j.cur === '6' && j.inView, `phone: jump from the vocab panel opens the sheet at question 6 ${JSON.stringify(j)}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-phone-jump.png`) });
      ok(audio.paid.length === 0, 'phone: no paid audio endpoints');
      ok(errs.length === 0, `phone: no page errors ${JSON.stringify(errs.slice(0, 5))}`);
    } catch (e) {
      await p.screenshot({ path: path.join(shotDir, `${engine}-phone-crash.png`) }).catch(() => {});
      throw e;
    } finally {
      await ctx.close();
    }
  }
};

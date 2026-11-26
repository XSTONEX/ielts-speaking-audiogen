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
  // 选两项：九分学长只在第一题带选项，第二题只有题干和答案
  const stem = 'Which TWO features of the bridge does the writer mention?';
  groups.push({
    id: '940', displayOrder: 5, qRange: 'Questions 9-10', type: 'multiple-choice', contentHtml: null, options: [],
    description: 'Choose <strong>TWO</strong> letters, <strong>A-E</strong>.',
    questions: [
      { id: '991', qNumber: '9', question: stem, rightAnswer: 'A', userAnswer: 'E', state: '2', analyses: [], displayOrder: 1,
        options: ['a curved deck', 'a toll booth', 'stone towers', 'night lighting', 'a viewing platform'].map((t, i) => ({ displayOrder: i + 1, optionNum: 'ABCDE'[i], option: t })) },
      { id: '992', qNumber: '10', question: stem, rightAnswer: 'D', userAnswer: 'D', state: '1', analyses: [], displayOrder: 2, options: [] },
    ],
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
    const expected = s => /status of (404|502)/.test(s) || /NotSupportedError|发音/.test(s);   // 502：三击查词里故意让 AI 出错的那一次
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
  const state = p => p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, meaning: document.getElementById('meaningBox').style.display, text: selectionRange && selectionRange.text, qk: selectionRange && selectionRange.qk, btn: document.querySelector('#floatBox .ir-pop-main').textContent, disabled: document.querySelector('#floatBox .ir-pop-main').disabled, existing: selectionRange && selectionRange.existingHighlight }));

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

      // ---- 选两项：第 10 题也画出整套选项，各题只标自己的对错 ----
      const multi = await p.evaluate(() => ['9', '10'].map(n => { const q = document.querySelector(`#examPane .ir-q[data-num="${n}"]`); return { opts: [...q.querySelectorAll('.ir-opt')].map(o => o.querySelector('b').textContent + (o.classList.contains('is-answer') ? '+' : '') + (o.classList.contains('is-mine') ? '*' : '')), hk: [...q.querySelectorAll('.ir-opt [data-hk]')].map(b => b.dataset.hk), ans: !!q.querySelector('.ir-ans') }; }));
      ok(JSON.stringify(multi[0].opts) === JSON.stringify(['A+', 'B', 'C', 'D', 'E*']), `choose-two Q9: A green, E struck red ${JSON.stringify(multi[0])}`);
      ok(JSON.stringify(multi[1].opts) === JSON.stringify(['A', 'B', 'C', 'D+*', 'E']) && !multi[1].ans, `choose-two Q10 repeats all five options, D green ${JSON.stringify(multi[1])}`);
      ok(JSON.stringify(multi[1].hk) === JSON.stringify(['g4.q10.A', 'g4.q10.B', 'g4.q10.C', 'g4.q10.D', 'g4.q10.E']), `choose-two Q10 options can be highlighted ${JSON.stringify(multi[1].hk)}`);

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
      const marks = () => p.evaluate(() => [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].map(m => ({ hk: m.closest('[data-hk]').dataset.hk, text: m.firstChild.nodeValue, tip: (m.querySelector('.tooltip') || {}).textContent })));
      const m1 = await marks();
      ok(JSON.stringify(m1.map(m => m.text).sort()) === JSON.stringify(['engineers', 'glare', 'relocate', 'reluctant']) && m1.every(m => /^e2e /.test(m.tip)), `four marks drawn in the questions ${JSON.stringify(m1)}`);
      ok(Number(await p.textContent('#vocabCount')) === before + 4, 'vocab count +4');
      const sh = await serverHighlights();
      ok(JSON.stringify(sh.filter(h => h.qk).map(h => [h.qk, h.text]).sort()) === JSON.stringify([[k4, 'engineers'], [k3, 'reluctant'], [k1, 'relocate'], [k2, 'glare']].sort()), `saved with qk ${JSON.stringify(sh.map(h => [h.qk, h.text]))}`);
      ok(await p.evaluate(() => document.querySelectorAll('#vContent mark.hl:not(.hl-echo)').length === 0), 'question highlights are not painted into the passage');

      // ---- 题目里划过的词，原文里出现的地方自动标上（同一条高亮、同一条释义，不存新的）；选到它只给「删除高亮」 ----
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      const echo = await p.evaluate(() => { const h = highlights.find(h => h.text === 'engineers'); const ms = [...document.querySelectorAll('#vContent mark.hl.hl-echo')].filter(m => m.firstChild.nodeValue === 'Engineers'); const m = ms[0]; if (m) m.scrollIntoView({ block: 'center' }); const r = m && m.getBoundingClientRect(); return { n: ms.length, hid: m && m.dataset.hid, want: h && h.id, tip: m && (m.querySelector('.tooltip') || {}).textContent, x: r && r.left + r.width / 2, y: r && r.top + r.height / 2, stored: highlights.filter(h => /^engineers$/i.test(h.text)).length }; });
      ok(echo.n === 1 && echo.hid === echo.want && echo.tip === 'e2e 工程师' && echo.stored === 1, `"Engineers" in the passage is auto-marked with the question's meaning ${JSON.stringify(echo)}`);
      await p.mouse.dblclick(echo.x, echo.y); await sleep(150);
      const dup = await state(p);
      ok(dup.float === 'block' && dup.existing === echo.want, `selecting an auto-marked word offers only 删除高亮 ${JSON.stringify(dup)}`);

      // ---- 跨两段题目文字的选区只提示 ----
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      const a = await wordBox(p, /^g2\.q7$/, 'handrails'), b2 = await wordBox(p, /^g2\.q7\.A$/, 'added', true);
      await p.mouse.move(a.x0 + 2, a.y); await p.mouse.down(); await p.mouse.move(b2.x1 - 1, b2.y, { steps: 8 }); await p.mouse.up(); await sleep(150);
      const cross = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, tip: [...document.querySelectorAll('.temp-tooltip')].map(t => t.textContent).join() }));
      ok(cross.float === 'none' && /同一句题目/.test(cross.tip), `selection across stem + option is refused ${JSON.stringify(cross)}`);

      // ---- 悬停看释义；点一下读出来：先有道，没有再退回以前存过的 ----
      const rel = await p.$('#examPane mark.hl:not(.hl-echo)[data-hid]');
      const relBox = await wordBox(p, /^g2\.q6$/, 'relocate');
      await p.mouse.move(relBox.x, relBox.y); await sleep(150);
      const tipShown = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].find(m => m.firstChild.nodeValue === 'relocate'); return getComputedStyle(m.querySelector('.tooltip')).display; });
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
      await p.waitForFunction(() => currentArticle && document.querySelectorAll('#examPane mark.hl:not(.hl-echo)').length >= 4); await sleep(300);
      const m2 = await marks();
      ok(m2.length === 4 && await p.evaluate(() => document.querySelectorAll('#vContent mark.hl:not(.hl-echo)').length === 1), `after reload: 4 question marks + 1 passage mark ${JSON.stringify(m2.map(m => m.text))}`);
      await p.click('#vocabToggle'); await sleep(300);
      const rows = await p.evaluate(() => [...document.querySelectorAll('#hpBody .ir-vi')].map(r => r.querySelector('.ir-vi-word').textContent));
      ok(JSON.stringify(rows) === JSON.stringify(['bridge', 'engineers题目', 'relocate第 6 题', 'glare第 6 题', 'reluctant题目']), `vocab panel order + tags ${JSON.stringify(rows)}`);
      audio.youdao.length = 0;
      await p.click('#hpBody .ir-vi:nth-child(3) .ir-vi-text'); await sleep(300);
      ok(audio.youdao[0] === 'relocate', `vocab row click plays via Youdao ${JSON.stringify(audio.youdao)}`);
      // 跳到题目里的词：题目栏滚过去、闪一下
      await p.evaluate(() => { document.getElementById('examPane').scrollTop = 0; });
      await p.click('#hpBody .ir-vi:nth-child(5) [title="跳到原文"]'); await sleep(250);
      const jump = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].find(m => m.firstChild.nodeValue === 'reluctant'); const r = m.getBoundingClientRect(), pr = document.getElementById('examPane').getBoundingClientRect(); return { active: m.classList.contains('active'), inView: r.top > pr.top && r.bottom < pr.bottom, scrolled: document.getElementById('examPane').scrollTop > 0 }; });
      ok(jump.active && jump.inView && jump.scrolled, `jump from the vocab panel scrolls the questions to the word ${JSON.stringify(jump)}`);
      await p.click('#highlightsPanel .ir-panel-head .ir-icon-btn'); await sleep(250);

      // ---- 右键删除：只拿掉这一个，题目栏不跳回顶上 ----
      const gl = await wordBox(p, /^g2\.q6\.B$/, 'glare');
      const st0 = await p.evaluate(() => document.getElementById('examPane').scrollTop);
      acceptNext = true;
      await p.mouse.click(gl.x, gl.y, { button: 'right' }); await sleep(600);
      const del = await p.evaluate(() => ({ marks: [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].map(m => m.firstChild.nodeValue).sort(), scroll: document.getElementById('examPane').scrollTop, count: document.getElementById('vocabCount').textContent, text: document.querySelector('#examPane [data-hk="g2.q6.B"]').textContent }));
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
      const mlTip = await p.evaluate(() => { const m = [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].find(m => m.firstChild.nodeValue === 'complaints'); const t = m.querySelector('.tooltip'); const cs = getComputedStyle(t); return { display: cs.display, ws: cs.whiteSpace, lines: Math.round((t.clientHeight - parseFloat(cs.paddingTop) - parseFloat(cs.paddingBottom)) / parseFloat(cs.lineHeight)) }; });
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

      // ==================== 三击查词 / AI 释义 ====================
      // /intensive_lookup 在浏览器里拦下（沙盒没有模型 key），按词回一条编的释义；catches 模拟模型出错
      const lookups = [];
      await p.route('**/intensive_lookup', async route => {
        const b = route.request().postDataJSON(); lookups.push(b);
        await sleep(300);
        if (b.text === 'catches') return route.fulfill({ status: 502, contentType: 'application/json', body: JSON.stringify({ error: 'AI 释义暂时取不到，请自己写一下' }) });
        route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, meaning: `e2e ai ${b.text}` }) });
      });
      const passBox = word => p.evaluate(word => { const pp = [...document.querySelectorAll('#vContent p.en')].find(p => p.textContent.includes(word)); pp.scrollIntoView({ block: 'center' }); const tw = document.createTreeWalker(pp, NodeFilter.SHOW_TEXT); let tn; while ((tn = tw.nextNode()) && !tn.nodeValue.includes(word)); const i = tn.nodeValue.indexOf(word); const r = document.createRange(); r.setStart(tn, i + 1); r.setEnd(tn, i + word.length - 1); const rc = r.getBoundingClientRect(); return { x: rc.left + rc.width / 2, y: rc.top + rc.height / 2 }; }, word);
      async function tripleClick(x, y) { await p.mouse.move(x, y); for (const n of [1, 2, 3]) { await p.mouse.down({ clickCount: n }); await p.mouse.up({ clickCount: n }); } }
      const saved = async word => (await serverHighlights()).find(h => h.text === word);
      // 原文：三击 fishermen → 念一遍；不弹释义框，词上扫光 + 「AI 释义」气泡 → 存成高亮，亮一下、露出释义
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      const said0 = audio.youdao.length;
      let w3 = await passBox('fishermen');
      await tripleClick(w3.x, w3.y); await sleep(80);
      const busy = await p.evaluate(() => { const w = document.querySelector('#vContent .ir-ai-wait'); const b = document.querySelector('#vContent .ir-ai-badge'); return { box: document.getElementById('meaningBox').style.display, float: document.getElementById('floatBox').style.display, wait: !!w, badge: b && b.textContent, anim: w && getComputedStyle(w).animationName, sel: String(getSelection()) }; });
      ok(busy.box === 'none' && busy.float === 'none' && busy.wait && /AI 释义/.test(busy.badge || '') && /ir-ai-sweep/.test(busy.anim || '') && busy.sel === '', `triple-click: no box, the word shimmers with an AI badge ${JSON.stringify(busy)}`);
      ok(audio.youdao.slice(said0).includes('fishermen'), `triple-click pronounces the word ${JSON.stringify(audio.youdao.slice(said0))}`);
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'fishermen'), null, { timeout: 5000 }).catch(() => {});
      await sleep(150);
      const f1 = await saved('fishermen');
      const f1Page = await p.evaluate(() => { const ms = [...document.querySelectorAll('#vContent mark.hl:not(.hl-echo)')].filter(m => m.firstChild.nodeValue === 'fishermen'); const tip = ms[0] && ms[0].querySelector('.tooltip'); return { marks: ms.length, pop: ms.some(m => m.classList.contains('ir-hl-new')), tip: tip && getComputedStyle(tip).display, tipText: tip && tip.textContent, left: document.querySelectorAll('.ir-ai-wait, .ir-ai-badge').length }; });
      ok(f1 && f1.meaning === 'e2e ai fishermen' && !f1.qk && f1Page.marks === 1 && f1Page.pop && f1Page.tip === 'block' && f1Page.tipText === 'e2e ai fishermen' && f1Page.left === 0, `triple-click in the passage saves the AI meaning and shows it ${JSON.stringify({ f1, f1Page })}`);
      await sleep(2700);
      ok(await p.evaluate(() => { const m = [...document.querySelectorAll('#vContent mark.hl:not(.hl-echo)')].find(m => m.firstChild.nodeValue === 'fishermen'); return !m.classList.contains('tip-on') && !m.classList.contains('ir-hl-new'); }), 'the meaning bubble goes away by itself');
      ok(lookups[0] && lookups[0].text === 'fishermen' && !lookups[0].qk && lookups[0].end - lookups[0].start === 9, `lookup sends the word and its range ${JSON.stringify(lookups[0])}`);
      // 已经划过的词再三击：不再查
      await p.mouse.click(5, 450);
      w3 = await passBox('fishermen');
      await tripleClick(w3.x, w3.y); await sleep(200);
      ok(lookups.length === 1 && !(await p.evaluate(() => document.querySelector('.ir-ai-wait'))), 'triple-click on an existing highlight does not look it up again');
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      // 题目栏：三击题干里的 handrails → 带 qk 存
      await p.mouse.click(5, 450);
      const hq = await wordBox(p, /^g2\.q7$/, 'handrails');
      await tripleClick(hq.x, hq.y);
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'handrails'), null, { timeout: 5000 }).catch(() => {});
      await sleep(150);
      const f2 = await saved('handrails');
      ok(f2 && f2.qk === 'g2.q7' && f2.meaning === 'e2e ai handrails' && await p.evaluate(() => [...document.querySelectorAll('#examPane mark.hl:not(.hl-echo)')].some(m => m.firstChild.nodeValue === 'handrails')), `triple-click in a question saves with qk ${JSON.stringify(f2)}`);
      // 释义框里的「AI」：只填进框里，回车才存
      await p.evaluate(() => { try { cancelFloat(); cancelMeaning(); } catch (e) {} });
      await p.mouse.click(5, 450);
      const sw = await passBox('shadows');
      await p.mouse.dblclick(sw.x, sw.y); await sleep(150);
      await p.click('#floatBox .ir-pop-main');
      await p.click('#meaningBox .ir-pop-ai');
      await p.waitForFunction(() => document.getElementById('meaningInput').value === 'e2e ai shadows', null, { timeout: 5000 }).catch(() => {});
      const filled = await p.evaluate(() => ({ v: document.getElementById('meaningInput').value, focus: document.activeElement && document.activeElement.id, box: document.getElementById('meaningBox').style.display }));
      ok(filled.v === 'e2e ai shadows' && filled.focus === 'meaningInput' && filled.box === 'block' && !(await saved('shadows')), `AI button fills the box without saving ${JSON.stringify(filled)}`);
      await p.press('#meaningInput', 'Enter');
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'shadows'), null, { timeout: 5000 }).catch(() => {});
      ok(((await saved('shadows')) || {}).meaning === 'e2e ai shadows', 'Enter saves the AI meaning');
      // 模型出错：扫光变红收掉，提示双击自己写；不弹框、不存
      await p.mouse.click(5, 450);
      const cw = await passBox('catches');
      await tripleClick(cw.x, cw.y);
      await p.waitForFunction(() => document.querySelector('.ir-ai-wait.is-fail'), null, { timeout: 5000 }).catch(() => {});
      const fail = await p.evaluate(() => ({ box: document.getElementById('meaningBox').style.display, red: !!document.querySelector('.ir-ai-wait.is-fail'), toast: [...document.querySelectorAll('.ir-toast')].map(t => t.textContent).join('|') }));
      await sleep(1000);
      const gone = await p.evaluate(() => document.querySelectorAll('.ir-ai-wait, .ir-ai-badge').length);
      ok(fail.box === 'none' && fail.red && /自己写/.test(fail.toast) && gone === 0 && !(await saved('catches')), `AI failure: shimmer turns red and clears, hint to write by hand ${JSON.stringify({ fail, gone })}`);
      // 划词浮层上的「AI 释义」：三击选不全的短语，拖选后点它 → 和三击一样扫光、直接存
      await p.mouse.click(5, 450);
      const ph = await p.evaluate(phrase => { const pp = [...document.querySelectorAll('#vContent p.en')].find(p => p.textContent.includes(phrase)); pp.scrollIntoView({ block: 'center' }); const tw = document.createTreeWalker(pp, NodeFilter.SHOW_TEXT); let tn; while ((tn = tw.nextNode()) && !tn.nodeValue.includes(phrase)); const i = tn.nodeValue.indexOf(phrase); const ch = k => { const r = document.createRange(); r.setStart(tn, k); r.setEnd(tn, k + 1); return r.getBoundingClientRect(); }; const a = ch(i), b = ch(i + phrase.length - 1); return { x1: a.left + 1, x2: b.right - 1, y: a.top + a.height / 2 }; }, 'scare the fish');
      await p.mouse.move(ph.x1, ph.y); await p.mouse.down(); await p.mouse.move(ph.x2, ph.y, { steps: 6 }); await p.mouse.up(); await sleep(150);
      const pop = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, text: selectionRange && selectionRange.text, ai: getComputedStyle(document.querySelector('#floatBox .ir-fb-ai')).display, label: document.querySelector('#floatBox .ir-fb-ai').innerText.trim() }));
      ok(pop.float === 'block' && pop.text === 'scare the fish' && pop.ai !== 'none' && pop.label === 'AI 释义', `selection popover offers AI 释义 for a phrase ${JSON.stringify(pop)}`);
      await p.click('#floatBox .ir-fb-ai'); await sleep(80);
      const phBusy = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, box: document.getElementById('meaningBox').style.display, wait: document.querySelectorAll('#vContent .ir-ai-wait').length, badge: !!document.querySelector('#vContent .ir-ai-badge') }));
      ok(phBusy.float === 'none' && phBusy.box === 'none' && phBusy.wait >= 1 && phBusy.badge, `popover AI: popover closes, the phrase shimmers ${JSON.stringify(phBusy)}`);
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'scare the fish'), null, { timeout: 5000 }).catch(() => {});
      await sleep(150);
      const f3 = await saved('scare the fish');
      const f3Look = lookups[lookups.length - 1];
      ok(f3 && f3.meaning === 'e2e ai scare the fish' && f3Look.text === 'scare the fish' && f3Look.end - f3Look.start === 14 && await p.evaluate(() => [...document.querySelectorAll('#vContent mark.hl:not(.hl-echo)')].some(m => m.firstChild.nodeValue === 'scare the fish')) && !(await p.evaluate(() => document.querySelector('.ir-ai-wait, .ir-ai-badge'))), `popover AI saves the phrase with its meaning ${JSON.stringify({ f3, f3Look })}`);
      // 选到已有高亮：浮层只有「删除高亮」，没有 AI
      await sleep(2700); await p.mouse.click(5, 450);
      const fm = await passBox('fishermen');
      await p.mouse.dblclick(fm.x, fm.y); await sleep(150);
      const exist = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, ai: getComputedStyle(document.querySelector('#floatBox .ir-fb-ai')).display, del: getComputedStyle(document.querySelector('#floatBox .ir-pop-danger')).display }));
      ok(exist.float === 'block' && exist.ai === 'none' && exist.del !== 'none', `no AI button on an existing highlight ${JSON.stringify(exist)}`);
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      // 同一个词本文里出现的地方都自动标上：三击 chose glass 里的 glass → 原文另外两处 + 题目里的 glass 都画上同一条
      await p.mouse.click(5, 450);
      const gw = await passBox('chose glass');
      const gx = await p.evaluate(() => { const pp = [...document.querySelectorAll('#vContent p.en')].find(p => p.textContent.includes('chose glass')); const tw = document.createTreeWalker(pp, NodeFilter.SHOW_TEXT); let tn; while ((tn = tw.nextNode()) && !tn.nodeValue.includes('chose glass')); const i = tn.nodeValue.indexOf('chose glass') + 6; const r = document.createRange(); r.setStart(tn, i + 1); r.setEnd(tn, i + 4); const rc = r.getBoundingClientRect(); return { x: rc.left + rc.width / 2, y: rc.top + rc.height / 2 }; });
      await tripleClick(gx.x, gx.y);
      await p.waitForFunction(() => (highlights || []).some(h => h.text === 'glass'), null, { timeout: 5000 }).catch(() => {});
      await sleep(200);
      const glx = await p.evaluate(() => { const h = highlights.find(h => h.text === 'glass'); const all = [...document.querySelectorAll(`mark.hl[data-hid="${h.id}"]`)]; return { stored: highlights.filter(x => /^glass$/i.test(x.text)).length, real: all.filter(m => !m.classList.contains('hl-echo')).length, passEcho: all.filter(m => m.classList.contains('hl-echo') && m.closest('#vContent')).map(m => m.firstChild.nodeValue), examEcho: all.filter(m => m.closest('#examPane')).length, tips: all.every(m => m.querySelector('.tooltip') && m.querySelector('.tooltip').textContent === 'e2e ai glass'), inBridge: !!document.querySelector('mark.hl:not(.hl-echo) mark.hl') }; });
      ok(glx.stored === 1 && glx.real === 1 && glx.passEcho.length >= 1 && glx.examEcho >= 1 && glx.tips && !glx.inBridge, `every other "glass" in the article is auto-marked with the same meaning ${JSON.stringify(glx)}`);
      ok(await p.evaluate(() => Number(document.getElementById('vocabCount').textContent) === new Set(highlights.map(h => (h.text || '').trim().toLowerCase())).size), 'vocab count counts each word once');
      // 选一段带着自动标出的词的短语（the glass is lit）：照常能划，不当成「删除高亮」
      await p.mouse.click(5, 450);
      const lit = await p.evaluate(phrase => { const own = p => { const c = p.cloneNode(true); c.querySelectorAll('.tooltip').forEach(t => t.remove()); return c.textContent; }; const pp = [...document.querySelectorAll('#vContent p.en')].find(p => own(p).includes(phrase)); pp.scrollIntoView({ block: 'center' }); const r = document.createRange(); const nodes = []; const tw = document.createTreeWalker(pp, NodeFilter.SHOW_TEXT, { acceptNode: n => n.parentNode.closest('.tooltip') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT }); let tn; while ((tn = tw.nextNode())) nodes.push(tn); let o = 0; const full = nodes.map(n => n.nodeValue).join(''); const a = full.indexOf(phrase), b = a + phrase.length; const at = k => { let acc = 0; for (const n of nodes) { if (k <= acc + n.length) return [n, k - acc]; acc += n.length; } }; r.setStart(...at(a)); r.setEnd(...at(b)); getSelection().removeAllRanges(); getSelection().addRange(r); handleReaderSelection(document.getElementById('vContent')); return { text: selectionRange && selectionRange.text, existing: selectionRange && selectionRange.existingHighlight, float: document.getElementById('floatBox').style.display, main: getComputedStyle(document.querySelector('#floatBox .ir-pop-main')).display }; }, 'the glass is lit');
      ok(lit.text === 'the glass is lit' && !lit.existing && lit.float === 'block' && lit.main !== 'none', `a phrase containing an auto-marked word can still be highlighted ${JSON.stringify(lit)}`);
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      // 在自动标出的地方右键删除：提示会一起取消，删的是那一条，所有地方一起消失
      const ge = await p.evaluate(() => { const m = document.querySelector('#vContent mark.hl.hl-echo'); const h = highlights.find(h => h.id === m.dataset.hid); m.scrollIntoView({ block: 'center' }); const r = m.getBoundingClientRect(); return { x: r.left + 3, y: r.top + r.height / 2, hid: h.id, text: h.text }; });
      dialogs.length = 0; acceptNext = true;
      await p.mouse.click(ge.x, ge.y, { button: 'right' });
      await p.waitForFunction(hid => !(highlights || []).some(h => h.id === hid), ge.hid, { timeout: 5000 }).catch(() => {});
      await sleep(150);
      const gone2 = await p.evaluate(hid => document.querySelectorAll(`mark.hl[data-hid="${hid}"]`).length, ge.hid);
      ok(/一起取消/.test(dialogs[0] || '') && gone2 === 0 && !(await serverHighlights()).some(h => h.id === ge.hid), `deleting from an auto-marked spot removes the word everywhere ${JSON.stringify({ dialogs, gone2, text: ge.text })}`);
      await p.unroute('**/intensive_lookup');

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
      const pm = await p.evaluate(() => { const m = document.querySelector('#examPane mark.hl:not(.hl-echo)'); return { text: m && m.firstChild.nodeValue, open: document.getElementById('examPane').classList.contains('is-open') }; });
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
      await lib.settle(p); await p.reload(); await p.waitForFunction(() => currentArticle && document.querySelectorAll('#examPane mark.hl:not(.hl-echo)').length === 2); await sleep(300);
      await p.tap('#vocabToggle'); await sleep(400);
      const row = await p.evaluate(() => [...document.querySelectorAll('#hpBody .ir-vi')].findIndex(r => r.querySelector('.ir-vi-word').textContent.startsWith('relocate')));
      await p.tap(`#hpBody .ir-vi:nth-child(${row + 1}) [title="跳到原文"]`); await sleep(900);
      const j = await p.evaluate(() => { const pane = document.getElementById('examPane'); const m = [...pane.querySelectorAll('mark.hl:not(.hl-echo)')].find(m => m.firstChild.nodeValue === 'relocate'); const r = m.getBoundingClientRect(), pr = pane.getBoundingClientRect(); return { panel: document.getElementById('highlightsPanel').classList.contains('active'), open: pane.classList.contains('is-open'), cur: pane.querySelector('.ir-q.is-cur').dataset.num, inView: r.top >= pr.top && r.bottom <= pr.bottom && r.height > 0 }; });
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

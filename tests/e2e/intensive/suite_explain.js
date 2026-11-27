// AI 讲解：题目栏顶上的页签（题目 / AI 讲解 / 同替 / 词汇 / 段落）。
// 文章现导入（tests/fixtures/jiufen_reading_attempt.json，编的「The Glass Bridge」），讲解数据是这里编的：
// /intensive_explain 两个接口和文章接口里的 explain 字段都在浏览器里拦下来给，不调模型、不碰付费接口。
// 讲解的生成和校验本身由 tests/test_reading_explain.py、tests/test_intensive_explain.py 管。
const fs = require('fs');
const path = require('path');

const FIXTURE = path.join(__dirname, '..', '..', 'fixtures', 'jiufen_reading_attempt.json');

const mark = (where, text, role, p, s, rel, zh) => ({ in: where, key: null, text, role, p, s, rel, zh });
const q = (num, extra) => Object.assign({ num, marks: [], evidence: [], eye_type: null, predict: null, answer_text: null, verdict: null, steps: [], rule: null, trap: null, wrong_options: [], slip: null, vocab_gate: null, doubt: null, pairs: 0, issues: [], jiufen: null }, extra);
const JUDGE = { type: 'judge', questions: {
  1: q('1', { verdict: 'NG', eye_type: '极端', evidence: [0], pairs: 1, rule: '题眼找不到同义也找不到反义 → NG',
    marks: [mark('stem', 'Marlow', '定位词', 'Marlow', 0, '原词', '地名原词'), mark('stem', 'the first of its kind', '题眼', null, null, '无对应', '没说是不是全国第一座')],
    steps: ['定位：Marlow 在 [0]。', '证据：[0] 只说这是镇上第一座玻璃桥。', '结论：全国第一找不到，NOT GIVEN。'] }),
  2: q('2', { verdict: 'F1', eye_type: '谓语', evidence: [2, 3], pairs: 3, slip: '你选了 TRUE：没看到 worried 是 supported 的反面。',
    marks: [mark('stem', 'Fishermen', '定位词', 'Local fishermen', 2, '原词', '渔民'), mark('stem', 'supported', '题眼', 'were worried', 2, '反向', '支持 ↔ 担心'), mark('stem', 'from the beginning', '辅助', 'at first', 2, '同替', '一开始')],
    steps: ['定位：fishermen 在 [2]。', '证据：[2] 一开始很担心，[3] 还说影子会吓跑鱼。', '结论：supported 对上 worried，方向相反，FALSE。'] }),
  3: q('3', { verdict: 'T', eye_type: '比较', evidence: [6], pairs: 2,
    marks: [mark('stem', 'more', '题眼', 'mainly', 6, '同替', '更多 = 主要'), mark('stem', 'at night', '定位词', 'in the evening', 6, '同替', '夜里 = 傍晚')],
    steps: ['定位：night 对上 [6] 的 evening。', '证据：[6] 游客主要傍晚来。', '结论：同向，TRUE。'] }),
} };
const BLANK = { type: 'blank', questions: {
  4: q('4', { eye_type: '空格左右', predict: 'n. 单数，一个地方', evidence: [1], answer_text: 'river', pairs: 2, slip: '你填了 water：原文是 river，要照抄。',
    marks: [mark('stem', 'engineers', '定位词', 'Engineers', 1, '原词', '工程师'), mark('stem', 'let light reach', '题眼', 'let light reach', 1, '原词', '让光照到')],
    steps: ['定位：engineers 在 [1]。', '证据：[1] let light reach the river below。', '结论：照抄 river。'] }),
  5: q('5', { eye_type: '疑问词', predict: 'n. 地点', evidence: [7], answer_text: 'north bank', pairs: 1,
    marks: [mark('stem', 'museum', '定位词', 'museum', 7, '原词', '博物馆')], steps: ['定位：museum 在 [7]。', '证据：[7] on the north bank。', '结论：填 north bank。'] }),
} };
const OVERVIEW = {
  paragraphs: [{ label: 'A', gist: '1998 年建了玻璃桥', repeat: '桥：glass bridge / glass' }, { label: 'B', gist: '渔民先担心后受益', repeat: null }, { label: 'C', gist: '现在是景点', repeat: null }],
  pairs: [{ q: 'supported', p: 'were worried', q_zh: '支持', p_zh: '担心', note: '反义陷阱' }, { q: 'at night', p: 'in the evening', q_zh: '夜里', p_zh: '傍晚', note: null }],
  vocab: [{ word: 'attraction', lemma: 'attraction', meaning: 'n. 景点（e2e）', tier: '必背', why: '高频学术词', s: 5, family: 'attract → attraction / attractive' },
          { word: 'argued', lemma: 'argue', meaning: 'v. 主张（e2e）', tier: '眼熟', why: '本篇专属', s: 3, family: null }],
  hard: [{ s: 6, core: 'Visitors come mainly in the evening', note: 'when 引导的从句补充说明时间' }], issues: [],
};
const explain = (status, done, groups, overview) => ({ status, model: 'e2e-model', done, total: 3, groups, overview: overview || null, errors: [] });

module.exports = async function suiteExplain({ cfg, browser, engine, t, lib }) {
  const BASE = cfg.baseUrl;
  const TITLE = `AI Bridge（${engine}）`;
  const ok = (c, w) => t.ok(c, w);
  const shotDir = path.join(cfg.out, 'explain');
  fs.mkdirSync(shotDir, { recursive: true });

  const api = await lib.apiContext(cfg);
  let id;
  try {
    const r = await api.post('/intensive_import', { data: { raw: fs.readFileSync(FIXTURE, 'utf8'), translate: false, titles: [TITLE], category: 'Reading' } });
    const d = await r.json();
    if (!d.success) throw new Error('导入失败 ' + JSON.stringify(d));
    id = d.ids[0];
  } finally {
    await api.dispose();
  }

  // 这篇的讲解存在这里：null → 生成中 → 讲完一组 → 全部讲完
  let state = null, polls = 0, posts = 0;
  async function wire(ctx) {
    await ctx.route(url => url.pathname === '/intensive_article/' + encodeURIComponent(id) || url.pathname === '/intensive_article/' + id, async route => {
      const resp = await route.fetch(); const d = await resp.json();
      if (d.article) d.article.explain = state;
      await route.fulfill({ response: resp, json: d });
    });
    await ctx.route(url => url.pathname === '/intensive_explain', route => { posts++; polls = 0; state = explain('running', 0, {}); return route.fulfill({ json: { success: true, explain: state } }); });
    await ctx.route(url => url.pathname.startsWith('/intensive_explain/'), route => {
      polls++;
      state = polls === 1 ? explain('running', 1, { 0: JUDGE }) : explain('done', 3, { 0: JUDGE, 1: BLANK }, OVERVIEW);
      return route.fulfill({ json: { success: true, explain: state } });
    });
  }
  const X = p => p.evaluate(() => document.getElementById('examPane').dataset.x);
  const hl = p => p.evaluate(() => Object.fromEntries([...CSS.highlights.keys()].filter(k => k.startsWith('xp-')).map(k => [k, CSS.highlights.get(k).size])));
  const supportsHighlights = p => p.evaluate(() => !!(window.CSS && CSS.highlights && typeof Highlight !== 'undefined'));

  // ==================== 桌面 ====================
  {
    const ctx = await lib.newContext(cfg, browser, { viewport: { width: 1440, height: 900 } });
    await wire(ctx);
    const p = await lib.newPage(ctx, 10000);
    const errors = []; p.on('pageerror', e => errors.push(e.message));
    p.on('dialog', d => d.accept());
    try {
      await lib.openList(p, cfg);
      await p.evaluate(() => { try { localStorage.removeItem('intensiveExamWidth'); localStorage.removeItem('intensiveHideAnswers'); } catch (e) {} });
      await lib.openArticle(p, id);
      await p.waitForSelector('#examPane .ir-q');
      const can = await supportsHighlights(p);
      ok((await p.evaluate(() => [...document.querySelectorAll('#examXtabs button')].map(b => b.textContent + (b.classList.contains('is-on') ? '*' : '')).join())) === '题目*,AI 讲解,同替,词汇,段落', 'tabs: 题目 is the default');
      ok(await p.evaluate(() => getComputedStyle(document.getElementById('xpStatus')).display === 'none' && !document.getElementById('viewer').classList.contains('xp-on')), '题目 tab shows nothing of the AI layer');

      // ---- 还没有讲解 → 生成 → 讲完一组显示一组 ----
      await p.click('#examXtabs [data-x="ai"]');
      ok((await X(p)) === 'ai' && /还没有 AI 讲解/.test(await p.textContent('#xpStatus')), 'AI 讲解 tab with nothing generated offers to generate');
      await p.click('#xpStatus [data-act="xp-gen"]'); await p.waitForTimeout(300);
      ok(posts === 1 && /正在生成/.test(await p.textContent('#xpStatus')), 'generate → shows progress');
      await p.waitForFunction(() => document.querySelector('#examPane .ir-q[data-num="2"] .ir-xp-chips'), null, { timeout: 8000 });
      ok(await p.evaluate(() => !document.querySelector('#examPane .ir-q[data-num="4"] .ir-xp-chips') && /讲完 1 \/ 3/.test(document.getElementById('xpStatus').textContent)), 'first poll: the judge group is explained, the blanks are not yet');
      await p.waitForFunction(() => document.querySelector('#examPane .ir-q[data-num="4"] .ir-xp-chips'), null, { timeout: 8000 });
      ok(await p.evaluate(() => !/正在生成/.test(document.getElementById('xpStatus').textContent) && !!document.querySelector('#xpStatus .ir-xp-legend')), 'second poll: done, the legend replaces the progress');
      const before = polls; await p.waitForTimeout(4600);
      ok(polls === before, 'polling stops once it is done');

      // ---- 题目上的划词、原文的句号和题号 ----
      const marks = await hl(p);
      if (can) ok(marks['xp-loc'] === 5 && marks['xp-eye'] === 3 && marks['xp-aux'] === 1 && marks['xp-miss'] === 1 && !marks['xp-ans'], `every question's words are marked, nothing in the passage until one is opened ${JSON.stringify(marks)}`);
      const gutter = await p.evaluate(() => ({ on: document.getElementById('viewer').classList.contains('xp-on'), num: getComputedStyle(document.querySelector('#vContent p[data-s="6"]'), '::before').content, xq: [...document.querySelectorAll('#vContent p[data-xq]')].map(e => e.dataset.s + ':' + e.dataset.xq).join() }));
      ok(gutter.on && gutter.num === '"6"' && gutter.xq === '0:1,1:4,2:2,6:3,7:5', `sentence numbers show; evidence sentences carry their question ${JSON.stringify(gutter)}`);
      ok(await p.evaluate(() => getComputedStyle(document.querySelector('#examPane .ir-q[data-num="2"] .ir-xp-body')).display === 'none' && getComputedStyle(document.querySelector('#examPane .ir-q[data-num="2"] .ir-q-actions')).display === 'none'), 'collapsed questions show only the chips');

      // ---- 点一道题：展开讲解，原文亮出证据句和对应的词 ----
      await p.click('#examPane .ir-q[data-num="2"] .ir-q-text'); await p.waitForTimeout(800);
      const open = await p.evaluate(() => { const qEl = document.querySelector('#examPane .ir-q[data-num="2"]'); const ev = [...document.querySelectorAll('#vContent p.ir-ev')]; const r = ev[0] && ev[0].getBoundingClientRect();
        return { active: qEl.classList.contains('is-active'), body: getComputedStyle(qEl.querySelector('.ir-xp-body')).display, ev: ev.map(e => e.dataset.s).join(), inView: !!r && r.top > 50 && r.bottom < innerHeight,
          pairs: qEl.querySelectorAll('.ir-xp-pair').length, text: qEl.querySelector('.ir-xp').textContent, refs: qEl.querySelectorAll('.ir-xp-ref').length, passage: xpHits.filter(h => h.side === 'p').length }; });
      ok(open.active && open.body === 'block' && open.ev === '2,3' && open.inView, `opening Q2 lights its evidence sentences ${JSON.stringify({ a: open.active, b: open.body, ev: open.ev, v: open.inView })}`);
      ok(open.pairs === 3 && /F1 · 方向相反/.test(open.text) && /你偏在哪/.test(open.text) && /supported⇄wereworried/.test(open.text.replace(/\s/g, '')) && open.refs >= 4, `the card has the verdict, the pairs, the steps and where you slipped (refs ${open.refs})`);
      if (can) ok(open.passage === 3, `the matching words in the passage are marked (${open.passage})`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-desktop-q2.png`) });

      // ---- 悬停：弹出这组对应，两边一起加深 ----
      if (can) {
        const at = await p.evaluate(() => { const h = xpHits.find(h => h.side === 'p' && h.num === '2' && h.k === 1); const r = h.range.getClientRects()[0]; return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
        await p.mouse.move(at.x, at.y); await p.waitForTimeout(250);
        const tip = await p.evaluate(() => ({ hidden: document.getElementById('xpTip').hidden, text: document.getElementById('xpTip').textContent, hot: CSS.highlights.has('xp-hot') ? CSS.highlights.get('xp-hot').size : 0 }));
        ok(!tip.hidden && /题眼/.test(tip.text) && /supported/.test(tip.text) && /were worried/.test(tip.text) && /支持 ↔ 担心/.test(tip.text) && tip.hot === 2, `hovering a marked word shows the pair and lights both sides ${JSON.stringify(tip)}`);
        await p.mouse.move(5, 400); await p.waitForTimeout(250);
        ok(await p.evaluate(() => document.getElementById('xpTip').hidden && !CSS.highlights.has('xp-hot')), 'moving away hides it');
      }

      // ---- 填空题：答案在原文里标出来；讲解里的句号能点 ----
      await p.click('#examPane .ir-q[data-num="4"] .ir-q-text'); await p.waitForTimeout(700);
      const q4 = await p.evaluate(() => ({ ev: [...document.querySelectorAll('#vContent p.ir-ev')].map(e => e.dataset.s).join(), ans: xpHits.filter(h => h.k === -1).map(h => h.range.toString()).join(), q2: getComputedStyle(document.querySelector('#examPane .ir-q[data-num="2"] .ir-xp-body')).display, chips: document.querySelector('#examPane .ir-q[data-num="4"] .ir-xp-chips').textContent }));
      ok(q4.ev === '1' && q4.q2 === 'none' && /预测 · n\. 单数/.test(q4.chips) && (!can || q4.ans === 'river'), `opening Q4 closes Q2 and marks the answer in the passage ${JSON.stringify(q4)}`);
      await p.click('#examPane .ir-q[data-num="2"] .ir-q-text'); await p.waitForTimeout(500);
      await p.click('#examPane .ir-q[data-num="2"] .ir-xp-steps .ir-xp-ref[data-s="3"]'); await p.waitForTimeout(300);
      ok(await p.evaluate(() => document.querySelector('#vContent p[data-s="3"]').classList.contains('xp-flash') && document.querySelector('#examPane .ir-q[data-num="2"]').classList.contains('is-active')), 'a sentence number in the steps flashes that sentence');

      // ---- 自己划的词照样能划，AI 的划词还在 ----
      const word = await p.evaluate(() => { const b = document.querySelector('#examPane .ir-q[data-num="3"] .ir-q-text'); b.scrollIntoView({ block: 'center' }); const i = hkText(b).indexOf('attracts'); const r = hkDomRange(b, i, i + 8).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; });
      await p.mouse.dblclick(word.x, word.y); await p.waitForTimeout(450);
      const dbl = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, sel: String(window.getSelection()), active: xpActive }));
      ok(dbl.float !== 'none' && dbl.sel.trim() === 'attracts' && dbl.active === '2',`double-clicking a word in a question still offers 高亮 and does not open that question ${JSON.stringify(dbl)}`);
      await p.evaluate(() => cancelFloat());

      // ---- 同替 / 词汇 / 段落 ----
      await p.click('#examXtabs [data-x="pairs"]');
      const pairs = await p.evaluate(() => ({ rows: document.querySelectorAll('#xpPanel .ir-xp-row').length, text: document.getElementById('xpPanel').textContent, groups: [...document.querySelectorAll('#examPane .ir-group')].filter(g => g.offsetParent).length, hl: [...CSS.highlights.keys()].filter(k => k.startsWith('xp-')).length, ev: document.querySelectorAll('#vContent p.ir-ev').length, on: document.getElementById('viewer').classList.contains('xp-on') }));
      ok(pairs.rows === 2 && /反义陷阱/.test(pairs.text) && pairs.groups === 0 && pairs.hl === 0 && pairs.ev === 0 && !pairs.on, `同替: a table instead of the questions, the marks are gone ${JSON.stringify(pairs)}`);
      await p.click('#examXtabs [data-x="vocab"]');
      ok(await p.evaluate(() => document.querySelectorAll('#xpPanel .ir-xp-row.is-word').length === 2 && /必背 1 · 眼熟 1/.test(document.getElementById('xpPanel').textContent)), '词汇: tiered list');
      const n0 = await p.evaluate(() => highlights.length);
      await p.click('#xpPanel .ir-xp-row[data-jump="5"] [data-act="xp-add"]'); await p.waitForTimeout(600);
      const added = await p.evaluate(() => ({ n: highlights.length, mark: [...document.querySelectorAll('#vContent p[data-s="5"] mark.hl')].map(m => m.firstChild.nodeValue).join(), btn: document.querySelector('#xpPanel .ir-xp-row[data-jump="5"] [data-act="xp-add"]').textContent, off: document.querySelector('#xpPanel .ir-xp-row[data-jump="5"] [data-act="xp-add"]').disabled }));
      ok(added.n === n0 + 1 && added.mark === 'attraction' && added.btn === '已在生词本' && added.off, `加入生词本 highlights the word in the passage with the AI meaning ${JSON.stringify(added)}`);
      await p.click('#xpPanel .ir-xp-row[data-jump="3"] .en'); await p.waitForTimeout(300);
      ok(await p.evaluate(() => document.querySelector('#vContent p[data-s="3"]').classList.contains('xp-flash')), 'clicking a word jumps to its sentence');
      await p.click('#examXtabs [data-x="para"]');
      ok(await p.evaluate(() => document.querySelectorAll('#xpPanel .ir-xp-row.is-para').length === 3 && /长难句/.test(document.getElementById('xpPanel').textContent)), '段落: one gist per paragraph, then the hard sentences');

      // ---- 讲解里的英文和原文、题目里的一样：划过的词自动标上，能双击划词、三击查词 ----
      ok(await p.evaluate(() => { document.querySelector('#examXtabs [data-x="vocab"]').click(); const m = document.querySelector('#xpPanel .ir-xp-row[data-jump="5"] .en mark.hl.hl-echo'); return !!m && m.firstChild.nodeValue === 'attraction' && m.getAttribute('data-hid') === highlights.find(h => h.text === 'attraction').id; }), 'a word already in the 生词本 is marked in the vocab table too (same highlight)');
      const wordAt = (sel, word) => p.evaluate(([sel, word]) => { const root = document.querySelector(sel); root.scrollIntoView({ block: 'center' }); const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT); let n; while ((n = w.nextNode())) { if (n.parentNode.closest('.tooltip')) continue; const i = n.nodeValue.indexOf(word); if (i >= 0) { const r = document.createRange(); r.setStart(n, i); r.setEnd(n, i + word.length); const b = r.getBoundingClientRect(); return { x: b.left + b.width / 2, y: b.top + b.height / 2 }; } } return null; }, [sel, word]);
      // 讲解里没有、原文和题目里也没有的词（词族里的 attractive）：存不了，给个说明
      let at = await wordAt('#xpPanel .ir-xp-row[data-jump="5"]', 'attractive');
      await p.mouse.dblclick(at.x, at.y); await p.waitForTimeout(400);
      ok(await p.evaluate(() => document.getElementById('floatBox').style.display === 'none' && /不在原文和题目里/.test(document.body.textContent)), 'a word that is nowhere in the passage or the questions cannot be saved, and says so');
      await p.click('#examXtabs [data-x="ai"]'); await p.click('#examPane .ir-q[data-num="2"] .ir-q-text'); await p.waitForTimeout(600);
      // 双击讲解里的 worried → 存到原文第 2 句的 worried 上，讲解里出现的地方都自动标上
      at = await wordAt('#examPane .ir-q[data-num="2"] .ir-xp-pair[data-k="1"]', 'worried');
      await p.mouse.dblclick(at.x, at.y); await p.waitForTimeout(400);
      const picked = await p.evaluate(() => ({ float: document.getElementById('floatBox').style.display, text: selectionRange && selectionRange.text, qk: selectionRange && selectionRange.qk, inS2: selectionRange && selectionRange.start >= examSentenceAt[2] && selectionRange.end <= examSentenceAt[2] + 60 }));
      ok(picked.float !== 'none' && picked.text === 'worried' && !picked.qk && picked.inS2, `double-clicking a word in the explanation offers 高亮, anchored to the passage ${JSON.stringify(picked)}`);
      await p.click('#floatBox .ir-pop-main'); await p.fill('#meaningInput', 'adj. e2e 担心的'); await p.press('#meaningInput', 'Enter'); await p.waitForTimeout(600);
      const saved = await p.evaluate(() => { const h = highlights.find(h => h.text === 'worried'); const xp = [...document.querySelectorAll('#examPane .ir-q[data-num="2"] .ir-xp mark.hl')]; const real = document.querySelector('#vContent p[data-s="2"] mark.hl:not(.hl-echo)');
        return { h: !!h && !h.qk, real: real && real.firstChild.nodeValue, echoes: xp.length, allEcho: xp.every(m => m.classList.contains('hl-echo') && m.getAttribute('data-hid') === (h && h.id)), tip: xp[0] && xp[0].closest('.ir-xp').querySelector('mark.hl .tooltip').textContent, font: xp[0] && getComputedStyle(xp[0]).backgroundColor === getComputedStyle(real).backgroundColor }; });
      ok(saved.h && saved.real === 'worried' && saved.echoes >= 2 && saved.allEcho && /e2e 担心/.test(saved.tip) && saved.font, `saved on the passage word; every "worried" in the explanation is marked with the same meaning and colour ${JSON.stringify(saved)}`);
      // 三击讲解里的 supported（原文里没有，在题干里）→ AI 释义存到题干那个词上
      await p.route('**/intensive_lookup', route => route.fulfill({ json: { success: true, meaning: 'v. e2e 支持' } }));
      at = await wordAt('#examPane .ir-q[data-num="2"] .ir-xp-note.is-slip', 'supported');
      await p.mouse.move(at.x, at.y); for (const n of [1, 2, 3]) { await p.mouse.down({ clickCount: n }); await p.mouse.up({ clickCount: n }); }
      await p.waitForTimeout(900);
      const looked = await p.evaluate(() => { const h = highlights.find(h => h.text === 'supported'); return { qk: h && h.qk, meaning: h && h.meaning, stem: [...document.querySelectorAll('#examPane .ir-q[data-num="2"] .ir-q-text mark.hl:not(.hl-echo)')].map(m => m.firstChild.nodeValue).join(), echoes: document.querySelectorAll('#examPane .ir-q[data-num="2"] .ir-xp mark.hl-echo[data-hid="' + (h && h.id) + '"]').length, box: document.getElementById('meaningBox').style.display }; });
      ok(looked.qk === 'g0.q2' && looked.meaning === 'v. e2e 支持' && looked.stem === 'supported' && looked.echoes >= 2 && looked.box === 'none', `triple-clicking a word in the explanation looks it up and saves it where it is in the question ${JSON.stringify(looked)}`);
      // 切走再回来、换一道题再回来，讲解里标上的词都还在
      await p.click('#examXtabs [data-x="pairs"]'); await p.waitForTimeout(150);
      ok(await p.evaluate(() => [...document.querySelectorAll('#xpPanel mark.hl-echo')].map(m => m.firstChild.nodeValue).sort().join() === 'supported,worried'), 'the 同替 table marks them too');
      await p.click('#examXtabs [data-x="ai"]'); await p.waitForTimeout(150);
      ok(await p.evaluate(() => document.querySelectorAll('#examPane .ir-q[data-num="2"] .ir-xp mark.hl-echo').length >= 4), 'coming back to AI 讲解 they are still marked');
      await p.unroute('**/intensive_lookup');
      await p.click('#examXtabs [data-x="para"]');

      // ---- 回到 AI 讲解：划词重新画上；隐藏答案回到「题目」 ----
      await p.click('#examXtabs [data-x="ai"]'); await p.waitForTimeout(200);
      if (can) ok((await hl(p))['xp-eye'] === 3, 'back on AI 讲解 the marks are painted again (after a highlight changed the passage)');
      await p.click('[data-act="answers"]'); await p.waitForTimeout(200);
      ok((await X(p)) === 'q' && await p.evaluate(() => [...document.querySelectorAll('#examPane .ir-xp')].every(e => getComputedStyle(e).display === 'none') && [...CSS.highlights.keys()].filter(k => k.startsWith('xp-')).length === 0), 'hiding the answers leaves the AI layer');
      await p.click('#examXtabs [data-x="ai"]'); await p.waitForTimeout(200);
      ok((await X(p)) === 'ai' && await p.evaluate(() => !document.getElementById('examPane').classList.contains('hide-ans')), 'opening AI 讲解 shows the answers again');

      // ---- 「题目」页签下的「解析」「定位原文」 ----
      await p.click('#examXtabs [data-x="q"]');
      await p.click('#examPane .ir-q[data-num="3"] [data-act="locate"]'); await p.waitForTimeout(500);
      ok((await p.evaluate(() => [...document.querySelectorAll('#vContent p.ir-ev')].map(e => e.dataset.s).join())) === '6', '定位原文 uses the AI evidence sentence');
      await p.click('#examPane .ir-q[data-num="3"] [data-act="analysis"]'); await p.waitForTimeout(500);
      ok((await X(p)) === 'ai' && await p.evaluate(() => document.querySelector('#examPane .ir-q[data-num="3"]').classList.contains('is-active') && getComputedStyle(document.querySelector('#examPane .ir-q[data-num="3"] .ir-xp-body')).display === 'block'), '解析 opens that question on the AI 讲解 tab');

      // ---- 刷新：讲解跟着文章一起回来，不用再生成 ----
      await p.reload(); await p.waitForFunction(id => typeof currentArticle !== 'undefined' && currentArticle && currentArticle.id === id && document.querySelector('#examPane .ir-q'), id);
      await p.click('#examXtabs [data-x="ai"]'); await p.waitForTimeout(300);
      ok(posts === 1 && await p.evaluate(() => !!document.querySelector('#examPane .ir-q[data-num="5"] .ir-xp-chips') && !!document.querySelector('#xpStatus .ir-xp-legend')), 'after a reload the explanation is there without generating again');
      ok(errors.length === 0, `no page errors ${errors.join(' | ')}`);
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
    await wire(ctx);
    const p = await lib.newPage(ctx, 10000);
    const errors = []; p.on('pageerror', e => errors.push(e.message));
    p.on('dialog', d => d.accept());
    const sleep = ms => p.waitForTimeout(ms);
    try {
      await lib.openList(p, cfg);
      await lib.openArticle(p, id);
      await p.waitForSelector('#examPane .ir-q', { state: 'attached' });
      await p.tap('#examSheetBtn'); await sleep(400);
      await p.tap('.ir-qs-nav [data-act="qs-next"]'); await sleep(200);
      await p.tap('.ir-qs-nav [data-act="qs-analysis"]'); await sleep(400);
      const peek = await p.evaluate(() => { const cur = document.querySelector('#examPane .ir-q.is-cur'); return { x: document.getElementById('examPane').dataset.x, num: cur.dataset.num, active: cur.classList.contains('is-active'), body: getComputedStyle(cur.querySelector('.ir-xp-body')).display, tabs: getComputedStyle(document.getElementById('examXtabs')).display, on: document.querySelector('.ir-qs-nav [data-act="qs-analysis"]').classList.contains('is-on'), ev: [...document.querySelectorAll('#vContent p.ir-ev')].map(e => e.dataset.s).join(), w: document.documentElement.scrollWidth <= innerWidth }; });
      ok(peek.x === 'ai' && peek.num === '2' && peek.active && peek.body === 'block' && peek.tabs === 'none' && peek.on && peek.ev === '2,3' && peek.w, `解析 in the peek: the current question's explanation opens, its evidence is lit ${JSON.stringify(peek)}`);
      await p.tap('.ir-qs-nav [data-act="qs-next"]'); await sleep(300);
      ok((await p.evaluate(() => [...document.querySelectorAll('#vContent p.ir-ev')].map(e => e.dataset.s).join())) === '6', 'next question → the passage follows');
      await p.tap('.ir-qs-nav [data-act="qs-locate"]'); await sleep(1200);
      const loc = await p.evaluate(() => { const r = document.querySelector('#vContent p[data-s="6"]').getBoundingClientRect(); const pane = document.getElementById('examPane').getBoundingClientRect(); return { top: r.top, bottom: r.bottom, pane: pane.top, bar: document.querySelector('#viewer .ir-bar').getBoundingClientRect().bottom }; });
      ok(loc.top >= loc.bar - 1 && loc.bottom <= loc.pane + 1, `定位 puts the evidence between the top bar and the sheet ${JSON.stringify(loc)}`);
      await p.screenshot({ path: path.join(shotDir, `${engine}-phone-peek.png`) });
      // 展开整张列表：页签露出来，能切到词汇
      await p.tap('#examPane .ir-qs-more'); await sleep(400);
      ok(await p.evaluate(() => getComputedStyle(document.getElementById('examXtabs')).display !== 'none' && document.getElementById('examXtabs').getBoundingClientRect().width <= innerWidth), 'the full list shows the tabs');
      await p.tap('#examXtabs [data-x="vocab"]'); await sleep(300);
      ok(await p.evaluate(() => document.querySelectorAll('#xpPanel .ir-xp-row.is-word').length === 2 && [...document.querySelectorAll('#xpPanel [data-act="xp-add"]')].every(b => b.getBoundingClientRect().height >= 38)), '词汇 on the phone: rows with finger-sized buttons');
      await p.tap('.ir-qs-nav [data-act="qs-analysis"]').catch(() => {});
      ok(errors.length === 0, `no page errors ${errors.join(' | ')}`);
    } finally {
      await ctx.close();
    }
  }
};

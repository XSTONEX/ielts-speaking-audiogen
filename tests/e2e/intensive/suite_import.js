// /intensive/new 导入九分学长 JSON → 文章页：原文、题目栏（对错、解析、定位原文）、成绩、做题时的划线；
// 再看一篇带译文的导入文章、一篇普通旧文章，以及粘贴文本模式和手机上的「原文 / 题目」切换。
// 导入用的是 tests/fixtures/jiufen_reading_attempt.json（编的「The Glass Bridge」，3 段 8 句 5 题，对 2/5，用时 10:00）。
const fs = require('fs');
const path = require('path');

const FIXTURE = path.join(__dirname, '..', '..', 'fixtures', 'jiufen_reading_attempt.json');

module.exports = async function suiteImport({ cfg, browser, engine, t, lib }) {
  const { IDS } = lib;
  const BASE = cfg.baseUrl;
  // 粘贴时前后多带了几个引号也要认得出来
  const RAW = '“”“\n' + fs.readFileSync(FIXTURE, 'utf8') + '\n”“”';
  const TITLE = `The Glass Bridge（${engine}）`;
  const ok = (c, w) => t.ok(c, w);
  const errs = [];
  // 预期内的：故意贴乱码时预览返回 400、翻译失败返回 502；WebKit 在跳页时会把没回来的 fetch 记成 Load failed
  const expected = s => /status of (400|502)/.test(s) || /Load failed/.test(s);

  const ctx = await lib.newContext(cfg, browser, { viewport: { width: 1440, height: 900 } });
  const p = await lib.newPage(ctx, 10000);
  p.on('pageerror', e => { if (!expected(String(e))) errs.push(String(e)); });
  p.on('console', m => { if (m.type() === 'error' && !expected(m.text())) errs.push('console ' + m.text()); });
  let pc = null;
  try {
    // ---- 添加页：先预览 ----
    await lib.settle(p); await p.goto(BASE + '/intensive/new');
    await p.evaluate(() => { try { localStorage.removeItem('intensiveNewMode'); } catch (e) {} });
    await lib.settle(p); await p.reload();
    ok(await p.isVisible('#pane-json') && !(await p.isVisible('#pane-text')), 'json mode by default');
    await p.fill('#raw', 'hello there');
    await p.waitForSelector('#preview .ir-error');
    ok((await p.textContent('#preview .ir-error')).includes('没找到 JSON') && await p.isDisabled('#importBtn'), 'garbage → explained, import disabled');
    await p.fill('#raw', RAW);
    await p.waitForSelector('#preview .ir-part');
    const pv = await p.evaluate(() => ({ title: document.querySelector('#preview .ir-input').value, facts: document.querySelector('#preview .ir-facts').textContent, chips: [...document.querySelectorAll('#preview .ir-chip')].map(c => c.textContent), enabled: !document.getElementById('importBtn').disabled }));
    ok(pv.title === 'The Glass Bridge' && /3 段（A–C）/.test(pv.facts) && /8 句/.test(pv.facts) && /5 题/.test(pv.facts) && /划线 5 处/.test(pv.facts) && /2\/5/.test(pv.facts) && /10:00/.test(pv.facts) && pv.enabled, `preview ${JSON.stringify(pv)}`);
    ok(JSON.stringify(pv.chips) === JSON.stringify(['判断 1–3', '填空 4–5']), `group chips ${JSON.stringify(pv.chips)}`);
    await p.fill('#preview .ir-input', TITLE);

    // ---- 带翻译导入：沙盒没有 API key → 说明失败原因，给「不翻译，直接导入」 ----
    await p.click('#importBtn');
    await p.waitForSelector('#importNoZhBtn', { state: 'visible' });
    const failMsg = await p.textContent('#importMsg');
    ok(/翻译没成功/.test(failMsg) && !(await p.isDisabled('#importBtn')), `translate failure explained: ${failMsg}`);
    const count = () => p.evaluate(() => fetch('/intensive_list').then(r => r.json()).then(d => d.items.length));
    const before = await count();
    await p.click('#importNoZhBtn');
    await p.waitForURL(/\/intensive#article-/);
    await p.waitForFunction(() => document.querySelectorAll('#examPane .ir-q').length && currentArticle);
    await p.waitForTimeout(400);
    const after = await count();
    const v = await p.evaluate(() => ({ title: document.getElementById('vTitle').textContent, qs: document.querySelectorAll('#examPane .ir-q').length, right: document.querySelectorAll('#examPane .ir-q.is-right').length, wrong: document.querySelectorAll('#examPane .ir-q.is-wrong').length, blank: document.querySelectorAll('#examPane .ir-q.is-blank').length, zh: document.querySelectorAll('#vContent .reader p.zh').length, en: document.querySelectorAll('#vContent .reader p.en').length, hd: [...document.querySelectorAll('#vContent .reader p.hd')].map(p => p.textContent).join(''), score: document.querySelector('.ir-exam-score').textContent, marks: (window.CSS && CSS.highlights && CSS.highlights.get('jiufen')) ? CSS.highlights.get('jiufen').size : -1, ptitle: document.querySelector('.ir-ptitle').textContent }));
    ok(after === before + 1, `one article created (${before}→${after})`);
    ok(v.title === TITLE && v.qs === 5 && v.right === 2 && v.wrong === 2 && v.blank === 1 && v.zh === 0 && v.en === 8 && v.hd === 'ABC' && /对 2 \/ 5/.test(v.score) && /用时 10:00/.test(v.score) && v.ptitle === 'The Glass Bridge', `exam view ${JSON.stringify(v)}`);
    ok(v.marks === 5, `exam-time underlines painted: ${v.marks}`);

    // ---- 原文照样能划词（行首的词、穿过划线层；第 6 句开头的 Visitors 本身就有划线） ----
    for (const s of [0, 2, 5, 6]) {
      await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
      await p.mouse.click(5, 450);
      const w = await p.evaluate(s => { const pp = document.querySelector(`#vContent p[data-s="${s}"]`); pp.scrollIntoView({ block: 'center' }); const t = pp.firstChild; const m = /^[A-Za-z’']+/.exec(t.nodeValue); const r = document.createRange(); r.setStart(t, 0); r.setEnd(t, m[0].length); const rc = r.getBoundingClientRect(); return { word: m[0], x: rc.left + rc.width / 2, y: rc.top + rc.height / 2 }; }, s);
      await p.mouse.dblclick(w.x, w.y); await p.waitForTimeout(120);
      const st = await p.evaluate(() => ({ f: document.getElementById('floatBox').style.display, t: selectionRange && selectionRange.text }));
      ok(st.f === 'block' && st.t === w.word, `line-initial "${w.word}" (sentence ${s}) → ${JSON.stringify(st)}`);
    }
    // 自己的高亮盖住一条划线（"first glass bridge" 包含划线 "glass bridge"）：两样都要还在
    await p.evaluate(() => { try { cancelFloat(); } catch (e) {} });
    const sel = await p.evaluate(() => { const pp = document.querySelector('#vContent p[data-s="0"]'); pp.scrollIntoView({ block: 'center' }); const t = pp.firstChild; const i = t.nodeValue.indexOf('first glass bridge'); const r = document.createRange(); r.setStart(t, i); r.setEnd(t, i + 'first glass bridge'.length); getSelection().removeAllRanges(); getSelection().addRange(r); document.getElementById('vContent').dispatchEvent(new MouseEvent('mouseup', { bubbles: true })); return selectionRange && selectionRange.text; });
    await p.evaluate(() => confirmHighlight()); await p.fill('#meaningInput', '第一座玻璃桥'); await p.click('#meaningBox .ir-pop-main');
    await p.waitForFunction(() => (highlights || []).some(h => h.meaning === '第一座玻璃桥'));
    await p.waitForTimeout(200);
    const hm = await p.evaluate(() => ({ mark: document.querySelector('#vContent mark.hl') && document.querySelector('#vContent mark.hl').firstChild.nodeValue, marks: CSS.highlights.get('jiufen').size, under: [...CSS.highlights.get('jiufen')].some(r => r.toString() === 'glass bridge') }));
    ok(sel === 'first glass bridge' && hm.mark === 'first glass bridge' && hm.marks === 5 && hm.under, `own highlight over an underline ${JSON.stringify({ sel, ...hm })}`);

    // ---- 题目栏 ----
    const evS = () => p.evaluate(() => [...document.querySelectorAll('#vContent p.ir-ev')].map(p => p.dataset.s).join());
    await p.click('#examPane .ir-q[data-num="4"] [data-act="locate"]'); await p.waitForTimeout(700);
    const loc = await p.evaluate(() => { const ev = [...document.querySelectorAll('#vContent p.ir-ev')]; const r = ev[0] && ev[0].getBoundingClientRect(); return { s: ev.map(p => p.dataset.s), inView: !!r && r.top > 56 && r.bottom < innerHeight, active: document.querySelector('#examPane .ir-q.is-active').dataset.num }; });
    ok(JSON.stringify(loc.s) === '["1"]' && loc.inView && loc.active === '4', `locate Q4 → sentence 1 ${JSON.stringify(loc)}`);
    await p.click('#examPane .ir-q[data-num="2"] [data-act="locate"]'); await p.waitForTimeout(500);
    ok((await evS()) === '2,3', 'locate Q2 → sentences 2–3, previous cleared');
    await p.click('#examPane .ir-q[data-num="2"] [data-act="analysis"]');
    ok(await p.isVisible('#examPane .ir-q[data-num="2"] .ir-analysis') && /worried at first/.test(await p.textContent('#examPane .ir-q[data-num="2"] .ir-analysis')), 'analysis opens');
    // 填空：答错的写出你的和正确答案；没作答的写「（空）」
    const ans4 = await p.textContent('#examPane .ir-q[data-num="4"] .ir-ans');
    ok(/你的答案\s*water/.test(ans4) && /正确答案\s*river \/ river below/.test(ans4), `Q4 answers ${ans4}`);
    const ans5 = await p.textContent('#examPane .ir-q[data-num="5"] .ir-ans');
    ok(/（空）/.test(ans5) && /正确答案\s*north bank/.test(ans5), `Q5 unanswered ${ans5}`);
    // 判断题：答对的只标一个选项（又是你选的又是正确答案），答错的你选的和正确的分开标
    const opts = await p.evaluate(() => Object.fromEntries(['1', '2'].map(n => [n, [...document.querySelectorAll(`#examPane .ir-q[data-num="${n}"] .ir-opt`)].map(o => o.textContent + (o.classList.contains('is-answer') ? '+ans' : '') + (o.classList.contains('is-mine') ? '+mine' : ''))])));
    const hasAns1 = await p.evaluate(() => !!document.querySelector('#examPane .ir-q[data-num="1"] .ir-ans'));
    ok(JSON.stringify(opts['1']) === '["TRUE","FALSE","NOT GIVEN+ans+mine"]' && !hasAns1, `right judge Q1 marks only your answer ${JSON.stringify(opts['1'])} ans=${hasAns1}`);
    ok(JSON.stringify(opts['2']) === '["TRUE+mine","FALSE+ans","NOT GIVEN"]', `wrong judge Q2 marks yours and the right one ${JSON.stringify(opts['2'])}`);
    ok(/只看错题 3/.test(await p.textContent('[data-act="only-wrong"]')), 'only-wrong button counts wrong + unanswered');
    await p.click('[data-act="only-wrong"]');
    ok((await p.evaluate(() => [...document.querySelectorAll('#examPane .ir-q')].filter(q => getComputedStyle(q).display !== 'none').map(q => q.dataset.num).join())) === '2,4,5', 'only wrong: 2,4,5');
    await p.click('[data-act="only-wrong"]');
    ok((await p.evaluate(() => [...document.querySelectorAll('#examPane .ir-q')].filter(q => getComputedStyle(q).display !== 'none').length)) === 5, 'only wrong off: all 5 back');
    // 隐藏答案：对错、解析、定位都藏起来，正确选项也不再标颜色
    const optColors = () => p.evaluate(() => { const os = [...document.querySelectorAll('#examPane .ir-q[data-num="2"] .ir-opt')]; return os.map(o => getComputedStyle(o).color); });
    const shownColors = await optColors();
    await p.click('[data-act="answers"]');
    const hidden = await p.evaluate(() => ({ ans: [...document.querySelectorAll('#examPane .ir-ans')].every(a => getComputedStyle(a).display === 'none'), acts: [...document.querySelectorAll('#examPane .ir-q-actions')].every(a => getComputedStyle(a).display === 'none') }));
    const hiddenColors = await optColors();
    ok(hidden.ans && hidden.acts && new Set(hiddenColors).size === 1 && new Set(shownColors).size > 1, `answers hidden ${JSON.stringify({ ...hidden, shownColors, hiddenColors })}`);
    await lib.settle(p); await p.reload(); await p.waitForFunction(() => document.querySelectorAll('#examPane .ir-q').length && currentArticle); await p.waitForTimeout(300);
    ok(await p.evaluate(() => document.getElementById('examPane').classList.contains('hide-ans')), 'hidden answers survive reload');
    await p.click('[data-act="answers"]');
    ok(!(await p.evaluate(() => document.getElementById('examPane').classList.contains('hide-ans'))), 'answers back');
    // 原题版式里的空格编号 → 跳到那道题
    await p.click('#examPane .ir-layout summary');
    await p.click('#examPane .ir-blank[data-q="5"]'); await p.waitForTimeout(500);
    ok((await p.evaluate(() => document.querySelector('#examPane .ir-q.is-active').dataset.num)) === '5', 'blank chip → question 5');
    // ⋯ 菜单里的「做题时的划线」开关
    const jiufenSize = () => p.evaluate(() => CSS.highlights.get('jiufen') ? CSS.highlights.get('jiufen').size : 0);
    await p.click('#moreBtn'); await p.click('#jiufenMarksBtn');
    const off = await jiufenSize();
    await p.click('#moreBtn'); await p.click('#jiufenMarksBtn');
    const on = await jiufenSize();
    ok(off === 0 && on === 5, `underline toggle ${off} → ${on}`);
    await p.keyboard.press('Escape');

    // ---- 带译文的导入文章：原文和题目下面都有中文，「译文」开关两边一起藏 ----
    await lib.openArticle(p, IDS.glassBridge);
    await p.waitForFunction(() => document.querySelector('#examPane .ir-q'));
    const tz = await p.evaluate(() => ({ zh: document.querySelectorAll('#vContent .reader p.zh').length, qzh: document.querySelectorAll('#examPane .ir-q > .ir-q-zh').length, first: document.querySelector('#vContent p[data-s="0"] + p').textContent }));
    ok(tz.zh === 8 && tz.qzh === 5 && tz.first === '马洛镇在 1998 年建了第一座玻璃桥。', `translated article ${JSON.stringify(tz)}`);
    await p.click('#zhToggle');
    const hz = await p.evaluate(() => ({ p: [...document.querySelectorAll('#vContent .reader p.zh')].every(x => getComputedStyle(x).display === 'none'), q: [...document.querySelectorAll('#examPane .ir-q-zh')].every(x => getComputedStyle(x).display === 'none'), en: getComputedStyle(document.querySelector('#vContent .reader p.en')).display !== 'none' }));
    await p.click('#zhToggle');
    ok(hz.p && hz.q && hz.en, `译文 toggle hides passage + question Chinese ${JSON.stringify(hz)}`);

    // ---- 普通旧文章没有题目栏、没有划线，自己的高亮照常 ----
    await lib.openArticle(p, IDS.lighthouse);
    const old = await p.evaluate(() => ({ exam: document.querySelector('#viewer .ir-body').classList.contains('has-exam'), pane: getComputedStyle(document.getElementById('examPane')).display, tabs: getComputedStyle(document.getElementById('examTabs')).display, marks: CSS.highlights.get('jiufen') ? CSS.highlights.get('jiufen').size : 0, hl: document.querySelectorAll('#vContent mark.hl').length, menu: document.getElementById('jiufenMarksBtn').style.display }));
    ok(!old.exam && old.pane === 'none' && old.tabs === 'none' && old.marks === 0 && old.hl === 8 && old.menu === 'none', `old article unchanged ${JSON.stringify(old)}`);

    // ---- 列表卡片显示成绩；粘贴文本模式照样能建、能打开 ----
    await p.evaluate(() => closeViewer()); await p.evaluate(() => loadList()); await p.waitForTimeout(400);
    const cardText = await p.evaluate(title => { const c = [...document.querySelectorAll('.ir-card')].find(c => c.querySelector('h3').textContent === title); return c ? c.textContent : null; }, TITLE);
    ok(/对 2\/5/.test(cardText || ''), `list card shows 对 2/5: ${cardText}`);
    await lib.settle(p); await p.goto(BASE + '/intensive/new'); await p.click('#tab-text');
    await p.fill('#title', `Plain ${engine}`); await p.fill('#content', 'First line in English.\n第一行中文。\nSecond line.');
    await p.click('#createBtn'); await p.waitForURL(/\/intensive#article-/); await p.waitForFunction(() => currentArticle && document.querySelector('#vContent .reader p'));
    const plain = await p.evaluate(() => ({ t: document.getElementById('vTitle').textContent, ps: [...document.querySelectorAll('#vContent .reader p')].map(p => p.className), exam: document.querySelector('#viewer .ir-body').classList.contains('has-exam') }));
    ok(plain.t === `Plain ${engine}` && JSON.stringify(plain.ps) === '["en","zh","en"]' && !plain.exam, `plain article ${JSON.stringify(plain)}`);
    await lib.settle(p); await p.goto(BASE + '/intensive/new');
    ok(await p.isVisible('#pane-text') && !(await p.isVisible('#pane-json')), 'remembers last mode');
    await p.click('#tab-json');

    // ---- 手机：原文 / 题目两个标签；定位原文切到原文，切回题目还在原来的位置 ----
    pc = await lib.newContext(cfg, browser, { viewport: { width: 390, height: 844 }, hasTouch: true });
    const m = await lib.newPage(pc, 10000); m.on('pageerror', e => errs.push('phone ' + e));
    await m.goto(BASE + '/intensive#article-' + encodeURIComponent(IDS.glassBridge));
    await m.waitForFunction(() => currentArticle && document.querySelector('#examPane .ir-q')); await m.waitForTimeout(400);
    const t0 = await m.evaluate(() => ({ tabs: getComputedStyle(document.getElementById('examTabs')).display, pane: getComputedStyle(document.getElementById('examPane')).display, label: document.getElementById('examTabQ').textContent }));
    ok(t0.tabs === 'flex' && t0.pane === 'none' && t0.label === '题目 · 对 2/5', `phone opens on passage ${JSON.stringify(t0)}`);
    await m.tap('#examTabQ'); await m.waitForTimeout(200);
    await m.evaluate(() => document.querySelector('#examPane .ir-q[data-num="5"]').scrollIntoView({ block: 'center' }));
    const sc = await m.evaluate(() => document.getElementById('examPane').scrollTop);
    await m.tap('#examPane .ir-q[data-num="5"] [data-act="locate"]'); await m.waitForTimeout(700);
    const ph = await m.evaluate(() => { const ev = [...document.querySelectorAll('#vContent p.ir-ev')]; const r = ev[0].getBoundingClientRect(); return { onText: !document.querySelector('#viewer .ir-body').classList.contains('show-q'), s: ev.map(p => p.dataset.s).join(), inView: r.top > 90 && r.bottom < innerHeight }; });
    ok(ph.onText && ph.s === '7' && ph.inView, `phone locate → passage tab, sentence 7 ${JSON.stringify(ph)}`);
    await m.tap('#examTabQ'); await m.waitForTimeout(200);
    const sc2 = await m.evaluate(() => document.getElementById('examPane').scrollTop);
    ok(sc > 200 && Math.abs(sc2 - sc) < 2, `back to questions keeps position ${sc} → ${sc2}`);

    ok(errs.length === 0, `page errors ${errs.join(' | ')}`);
  } catch (e) {
    await p.screenshot({ path: `${cfg.out}/import-crash-${engine}.png` }).catch(() => {});
    throw e;
  } finally {
    if (pc) await pc.close();
    await ctx.close();
  }
};

// 桌面划词：已有高亮原样画回来；行首的词用各种手势都能选中并弹出「高亮」浮层；存一条释义刷新后还在。
// 每篇编造文章各管一种容易算错下标的格式（见 make_fake_data.py）。
const LINES_PER_ARTICLE = 6;

const GESTURES = {
  'drag L→R from left margin': async (page, r) => { await page.mouse.move(r.x0 - 12, r.y); await page.mouse.down(); await page.mouse.move(r.x1 - 1, r.y, { steps: 8 }); await page.mouse.up(); },
  'drag R→L into left margin': async (page, r) => { await page.mouse.move(r.x1 - 1, r.y); await page.mouse.down(); await page.mouse.move(r.x0 - 14, r.y, { steps: 8 }); await page.mouse.up(); },
  'drag R→L ending a bit above': async (page, r) => { await page.mouse.move(r.x1 - 1, r.y); await page.mouse.down(); await page.mouse.move(r.x0 - 6, r.y - r.h * 0.75, { steps: 8 }); await page.mouse.up(); },
  'drag from gap above-left': async (page, r) => { await page.mouse.move(r.x0 - 4, r.y - r.h * 0.9); await page.mouse.down(); await page.mouse.move(r.x1 - 1, r.y, { steps: 8 }); await page.mouse.up(); },
  'double-click word': async (page, r) => { await page.mouse.dblclick((r.x0 + r.x1) / 2, r.y); },
};
// 端点落在元素上 / 上一行末尾的选区：WebKit、三击、键盘选择会产生这种选区
const SYNTHETIC = {
  'start=(p,0)': (idx, len) => { const p = document.querySelectorAll('#vContent .reader p')[idx]; const r = document.createRange(); r.setStart(p, 0); r.setEnd(p.firstChild, len); return r; },
  'start=end of previous line': (idx, len) => { const ps = document.querySelectorAll('#vContent .reader p'); const prev = ps[idx - 1]; let last = prev.lastChild; while (last && last.nodeType !== 3) last = last.previousSibling || null; const r = document.createRange(); if (last) r.setStart(last, last.length); else r.setStart(prev, prev.childNodes.length); r.setEnd(ps[idx].firstChild, len); return r; },
  'start=(reader, idx)': (idx, len) => { const ps = document.querySelectorAll('#vContent .reader p'); const reader = ps[idx].parentNode; const r = document.createRange(); r.setStart(reader, [...reader.childNodes].indexOf(ps[idx])); r.setEnd(ps[idx].firstChild, len); return r; },
};

async function state(page) {
  return page.evaluate(() => ({
    float: document.getElementById('floatBox').style.display,
    sel: selectionRange ? JSON.parse(JSON.stringify(selectionRange)) : null,
    tips: [...document.querySelectorAll('.temp-tooltip')].map(t => t.textContent),
  }));
}
async function reset(page) {
  await page.evaluate(() => { try { cancelFloat(); } catch (e) {} document.querySelectorAll('.temp-tooltip').forEach(t => t.remove()); getSelection().removeAllRanges(); });
  await page.mouse.click(5, 5); // 点正文外面
  await page.evaluate(() => { try { cancelFloat(); } catch (e) {} });
}

// 行首的英文词（不在已有高亮里），连同它在屏幕上的位置
async function lineInitialWords(page, n) {
  return page.evaluate(n => {
    const out = [];
    const ps = [...document.querySelectorAll('#vContent .reader p')];
    for (let i = 1; i < ps.length && out.length < n; i++) {
      const t = ps[i].firstChild;
      if (!t || t.nodeType !== 3) continue;           // 以 <mark> 开头 → 跳过
      const m = /^[A-Za-z][A-Za-z'’-]+/.exec(t.nodeValue);
      if (!m || m[0].length < 3) continue;
      out.push({ idx: i, word: m[0] });
    }
    return out;
  }, n);
}
async function rectOf(page, idx) {
  return page.evaluate(idx => {
    const p = document.querySelectorAll('#vContent .reader p')[idx];
    p.scrollIntoView({ block: 'center' });
    const t = p.firstChild; const m = /^[A-Za-z][A-Za-z'’-]+/.exec(t.nodeValue);
    const r = document.createRange(); r.setStart(t, 0); r.setEnd(t, m[0].length);
    const rc = r.getBoundingClientRect();
    return { x0: rc.left, x1: rc.right, y: rc.top + rc.height / 2, h: rc.height };
  }, idx);
}

module.exports = async function suiteSelect({ cfg, browser, t, lib }) {
  const { IDS } = lib;
  const ARTICLES = [IDS.lighthouse, IDS.ferry, IDS.coldChain, IDS.emoji, IDS.ropeBridge];
  const ctx = await lib.newContext(cfg, browser, { viewport: { width: 1200, height: 800 } });
  const page = await lib.newPage(ctx);
  const errors = [];
  page.on('pageerror', e => errors.push(String(e)));
  try {
    await lib.openList(page, cfg);

    for (const id of ARTICLES) {
      await lib.openArticle(page, id);
      // 1) 已有高亮一个不少、文字一字不差地画回来（同一范围存了两次的只画一个）
      const hl = await page.evaluate(() => {
        const uniq = []; (currentArticle.highlights || []).forEach(h => { if (!uniq.some(x => x.start === h.start && x.end === h.end)) uniq.push(h); });
        const marks = [...document.querySelectorAll('#vContent mark.hl')];
        const bad = [];
        marks.forEach(m => { const h = uniq.find(x => x.id === m.getAttribute('data-hid')); const own = [...m.childNodes].filter(n => !(n.classList && n.classList.contains('tooltip'))).map(n => n.textContent).join(''); if (!h || own.trim() !== (h.text || '').trim()) bad.push([own, h && h.text]); });
        return { stored: (currentArticle.highlights || []).length, expected: uniq.length, marks: marks.length, bad };
      });
      t.ok(hl.expected > 0 && hl.marks === hl.expected && hl.bad.length === 0, `${id}: highlights restored ${hl.marks}/${hl.expected} (stored ${hl.stored}) bad=${JSON.stringify(hl.bad.slice(0, 3))}`);
      if (id === IDS.lighthouse) t.ok(hl.stored === 9 && hl.marks === 8, `${id}: duplicate highlight drawn once (${hl.stored} stored → ${hl.marks} marks)`);

      // 2) 真实鼠标手势选行首的词
      const words = await lineInitialWords(page, LINES_PER_ARTICLE);
      t.ok(words.length >= 4, `${id}: found ${words.length} line-initial words to try`);
      for (const w of words) {
        for (const [g, fn] of Object.entries(GESTURES)) {
          await reset(page);
          const r = await rectOf(page, w.idx);
          await fn(page, r);
          await page.waitForTimeout(60);
          const s = await state(page);
          // 拖过头可能多带一个空格或字符；只要求从这个词开始
          const got = s.sel && s.sel.text;
          const good = s.float === 'block' && got && got.startsWith(w.word) && !s.tips.length && (g !== 'double-click word' || got === w.word);
          t.ok(good, `${id} [${g}] "${w.word}" → float=${s.float} text=${JSON.stringify(got)} tips=${s.tips}`);
        }
        for (const [g, make] of Object.entries(SYNTHETIC)) {
          await reset(page);
          const s = await page.evaluate(([src, idx, len]) => {
            const make = eval('(' + src + ')');
            const r = make(idx, len); const sel = getSelection(); sel.removeAllRanges(); sel.addRange(r);
            document.getElementById('vContent').dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
            return { float: document.getElementById('floatBox').style.display, sel: selectionRange && selectionRange.text, tips: [...document.querySelectorAll('.temp-tooltip')].map(t => t.textContent) };
          }, [make.toString(), w.idx, w.word.length]);
          t.ok(s.float === 'block' && s.sel === w.word && !s.tips.length, `${id} [${g}] "${w.word}" → float=${s.float} text=${JSON.stringify(s.sel)} tips=${s.tips}`);
        }
      }
    }

    // 3) 给行首的词存一条释义，刷新后原样回来，然后删掉
    try {
      await lib.openArticle(page, ARTICLES[0]);
      await reset(page);
      const w = (await lineInitialWords(page, 3)).pop();
      const r = await rectOf(page, w.idx);
      await GESTURES['double-click word'](page, r);
      await page.waitForTimeout(60);
      await page.evaluate(() => confirmHighlight());
      await page.fill('#meaningInput', 'e2e-测试');
      await page.click('#meaningBox button:has-text("保存")');
      await page.waitForFunction(() => (highlights || []).some(h => h.meaning === 'e2e-测试'));
      const saved = await page.evaluate(() => highlights.find(h => h.meaning === 'e2e-测试'));
      await lib.settle(page); await page.reload();
      await page.waitForFunction(() => typeof openArticle === 'function' && typeof currentArticle !== 'undefined' && currentArticle && document.querySelector('#vContent .reader p'), null, { timeout: 15000 });
      await page.waitForTimeout(300);
      const back = await page.evaluate(id => { const m = document.querySelector(`#vContent mark.hl[data-hid="${id}"]`); return m ? m.firstChild.nodeValue : null; }, saved.id);
      t.ok(saved.text === w.word && back === w.word, `save+reload line-initial "${w.word}": saved=${JSON.stringify(saved.text)} restored=${JSON.stringify(back)}`);
      await page.evaluate(id => fetch('/intensive_delete_highlight', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ id: currentArticle.id, highlight_id: id }) }), saved.id);
    } catch (e) {
      t.ok(false, `[save+reload] crashed: ${e.message.split('\n')[0]}`);
    }
    t.ok(errors.length === 0, `page errors: ${errors.join(' | ')}`);
  } catch (e) {
    await page.screenshot({ path: `${cfg.out}/select-crash-${t.engine}.png` }).catch(() => {});
    throw e;
  } finally {
    await ctx.close();
  }
};

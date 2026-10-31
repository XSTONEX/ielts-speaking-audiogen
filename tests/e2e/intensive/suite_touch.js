// 手机上的划词流程，用真实的触摸点击（Chromium 手机模式 + WebKit 触摸）。
// 长按选词没法合成：先真实点一下那个词（pointerType=touch），再用 Range 设出长按会得到的选区，
// 这会照常触发 selectionchange，和真长按走同一条路。
const W = 390, H = 844;

module.exports = async function suiteTouch({ cfg, browser, engine, t, lib }) {
  const opts = { viewport: { width: W, height: H }, hasTouch: true, deviceScaleFactor: 2 };
  if (engine === 'chromium') opts.isMobile = true;   // WebKit 不认 isMobile
  const ctx = await lib.newContext(cfg, browser, opts);
  const p = await lib.newPage(ctx);
  const errs = []; const dialogs = [];
  p.on('pageerror', e => errs.push(String(e)));
  p.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
  const ok = (c, what) => t.ok(c, what);

  const st = () => p.evaluate(() => { const f = document.getElementById('floatBox'), m = document.getElementById('meaningBox'); const fr = f.getBoundingClientRect(); return { float: f.style.display, meaning: m.style.display, sel: selectionRange && selectionRange.text, fTop: fr.top, fBottom: fr.bottom, fLeft: fr.left, fRight: fr.right, focus: document.activeElement && document.activeElement.id, btn: [...f.querySelectorAll('button')].filter(x => x.style.display !== 'none').map(x => x.textContent), browserSel: getSelection().toString(), toast: [...document.querySelectorAll('.temp-tooltip')].map(t => t.textContent) }; });
  // 第 pi 行里第一个匹配 re 的词，滚到屏幕中间，返回它的位置
  const wordAt = (pi, re) => p.evaluate(([pi, re]) => { const ps = document.querySelectorAll('#vContent .reader p'); const pp = ps[pi]; pp.scrollIntoView({ block: 'center' }); const t = [...pp.childNodes].find(n => n.nodeType === 3); const m = new RegExp(re).exec(t.nodeValue); const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length); const rc = r.getBoundingClientRect(); return { pi, s: m.index, e: m.index + m[0].length, word: m[0], x: rc.left + rc.width / 2, y: rc.top + rc.height / 2, bottom: rc.bottom }; }, [pi, re]);
  // 点一下这个词，再把选区设成这个词（长按的效果），等页面的 selectionchange 防抖跑完
  async function longPress(w) {
    await p.touchscreen.tap(w.x, w.y); await p.waitForTimeout(80);
    await p.evaluate(([pi, s, e]) => { const ps = document.querySelectorAll('#vContent .reader p'); const t = [...ps[pi].childNodes].find(n => n.nodeType === 3); const r = document.createRange(); r.setStart(t, s); r.setEnd(t, e); getSelection().removeAllRanges(); getSelection().addRange(r); }, [w.pi, w.s, w.e]);
    await p.waitForTimeout(600);
  }

  try {
    await lib.openList(p, cfg);
    // 先把列表往下翻，再点卡片打开（旧页面在这种情况下会把浮层放到屏幕外）
    await p.evaluate(() => window.scrollTo(0, 600));
    await p.waitForTimeout(150);
    const card = await p.evaluate(() => { const c = [...document.querySelectorAll('.ir-card')].find(c => c.querySelector('h3').textContent === 'The Rope Bridge Builders'); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { x: r.left + 40, y: r.top + 20, sy: window.scrollY }; });
    await p.touchscreen.tap(card.x, card.y);
    await p.waitForFunction(() => document.querySelector('#vContent .reader p') && currentArticle);
    await p.waitForTimeout(400);
    ok(card.sy > 0, `list was scrolled (${card.sy}) before opening`);
    ok(await p.evaluate(() => currentArticle.title) === 'The Rope Bridge Builders', 'tapping the card opened that article');

    // 找一行英文：行首是 4 个字母以上、还没高亮过的词，这一行和下一行都没有高亮
    const target = await p.evaluate(() => { const ps = [...document.querySelectorAll('#vContent .reader p')]; for (let i = 2; i < ps.length; i++) { const p = ps[i]; if (!p.classList.contains('en') || p.querySelector('mark') || !ps[i + 1] || ps[i + 1].querySelector('mark')) continue; const t = p.firstChild; if (!t || t.nodeType !== 3) continue; const m = /^[A-Za-z]{4,}/.exec(t.nodeValue); if (m && !(currentArticle.highlights || []).some(h => h.text && h.text.toLowerCase() === m[0].toLowerCase())) return i; } return -1; });
    if (!ok(target > 0, 'found a line-initial word to test')) return;
    const w = await wordAt(target, '^[A-Za-z]+');
    await longPress(w);
    let s = await st();
    ok(s.float === 'block' && s.sel === w.word, `long-press "${w.word}" shows popover: ${JSON.stringify(s)}`);
    ok(s.fTop >= w.bottom && s.fBottom <= H && s.fLeft >= 0 && s.fRight <= W, `popover sits below the word and on screen: top=${s.fTop} bottom=${s.fBottom} word.bottom=${w.bottom}`);
    ok(JSON.stringify(s.btn) === JSON.stringify(['高亮', '取消']), `buttons ${JSON.stringify(s.btn)}`);

    // 点「高亮」→ 释义框，输入框拿到焦点
    await p.tap('#floatBox .ir-pop-main');
    await p.waitForTimeout(500);
    s = await st();
    ok(s.meaning === 'block' && s.float === 'none' && s.focus === 'meaningInput', `tap 高亮 → meaning box: ${JSON.stringify(s)}`);
    await p.fill('#meaningInput', 'touch-e2e-释义');
    await p.waitForTimeout(450);
    s = await st();
    ok(s.meaning === 'block', `meaning box stays while typing: ${s.meaning}`);
    const before = await p.evaluate(() => new Set(highlights.map(h => h.start + '-' + h.end)).size);
    await p.tap('#meaningBox .ir-pop-main');
    await p.waitForFunction(() => (highlights || []).some(h => h.meaning === 'touch-e2e-释义'));
    await p.waitForTimeout(300);
    const saved = await p.evaluate(() => { const h = highlights.find(h => h.meaning === 'touch-e2e-释义'); const m = document.querySelector(`#vContent mark.hl[data-hid="${h.id}"]`); return { id: h.id, text: h.text, mark: m && m.firstChild.nodeValue, count: document.getElementById('vocabCount').textContent, meaning: document.getElementById('meaningBox').style.display }; });
    ok(saved.text === w.word && saved.mark === w.word && saved.meaning === 'none', `saved line-initial "${w.word}": ${JSON.stringify(saved)}`);
    ok(Number(saved.count) === before + 1, `vocab count ${before} → ${saved.count}`);

    // 点新高亮 → 释义气泡出现且在屏幕内
    const mk = await p.evaluate(id => { const m = document.querySelector(`#vContent mark.hl[data-hid="${id}"]`); m.scrollIntoView({ block: 'center' }); const r = m.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; }, saved.id);
    await p.touchscreen.tap(mk.x, mk.y);
    await p.waitForTimeout(200);
    const tip = await p.evaluate(id => { const m = document.querySelector(`#vContent mark.hl[data-hid="${id}"]`); const t = m.querySelector('.tooltip'); const r = t.getBoundingClientRect(); return { on: m.classList.contains('tip-on'), vis: getComputedStyle(t).display, l: r.left, r: r.right, txt: t.textContent }; }, saved.id);
    ok(tip.on && tip.vis === 'block' && tip.l >= 0 && tip.r <= W && tip.txt === 'touch-e2e-释义', `tap mark shows meaning on screen: ${JSON.stringify(tip)}`);

    // 长按高亮不能弹「删除？」确认框（安卓长按会顺带触发 contextmenu）
    await p.evaluate(id => { lastPointerType = 'touch'; const m = document.querySelector(`#vContent mark.hl[data-hid="${id}"]`); m.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true })); }, saved.id);
    await p.waitForTimeout(150);
    ok(dialogs.length === 0, `no confirm dialog on long-press: ${JSON.stringify(dialogs)}`);

    // 选中已有高亮 → 「删除高亮」→ 没了
    await p.touchscreen.tap(5, 300); await p.waitForTimeout(400);
    await p.evaluate(id => { const m = document.querySelector(`#vContent mark.hl[data-hid="${id}"]`); const r = document.createRange(); r.selectNodeContents(m.firstChild); getSelection().removeAllRanges(); getSelection().addRange(r); }, saved.id);
    await p.waitForTimeout(600);
    s = await st();
    ok(s.float === 'block' && JSON.stringify(s.btn) === JSON.stringify(['取消', '删除高亮']), `select existing highlight → remove option: ${JSON.stringify(s.btn)} float=${s.float}`);
    await p.tap('#floatBox .ir-pop-danger');
    await p.waitForFunction(id => !document.querySelector(`#vContent mark.hl[data-hid="${id}"]`) && !(highlights || []).some(h => h.id === id), saved.id);
    ok(true, 'removed via 删除高亮');
    await p.waitForTimeout(400);

    // 选区收起时浮层跟着收起
    const w2 = await wordAt(target, '^[A-Za-z]+');
    await longPress(w2);
    s = await st(); ok(s.float === 'block', `popover back after re-select: ${s.float}`);
    await p.evaluate(() => getSelection().removeAllRanges());   // 点别处时选区就是这样没的
    await p.waitForTimeout(600);
    s = await st(); ok(s.float === 'none', `popover hides when the selection is dismissed: ${s.float}`);

    // 选区跨两行：浮层不出，提示一次，用户的选区保留（可能还在拖手柄）
    await p.touchscreen.tap(w2.x, w2.y); await p.waitForTimeout(80);
    await p.evaluate(pi => { const ps = document.querySelectorAll('#vContent .reader p'); const t1 = [...ps[pi].childNodes].find(n => n.nodeType === 3); const t2 = [...ps[pi + 1].childNodes].find(n => n.nodeType === 3); const r = document.createRange(); r.setStart(t1, 0); r.setEnd(t2, 2); getSelection().removeAllRanges(); getSelection().addRange(r); }, target);
    await p.waitForTimeout(600);
    s = await st(); ok(s.float === 'none' && s.browserSel.length > 0 && s.toast.length === 1, `cross-line selection: float=${s.float} kept=${s.browserSel.length > 0} toast=${s.toast}`);
    await p.evaluate(() => getSelection().removeAllRanges()); await p.waitForTimeout(500);

    // 词汇面板在手机上是底部面板；点「跳到原文」关掉面板、闪一下那个词
    await p.tap('#vocabToggle'); await p.waitForTimeout(400);
    const sheet = await p.evaluate(() => { const r = document.getElementById('highlightsPanel').getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, width: r.width, items: document.querySelectorAll('#hpBody .ir-vi').length }; });
    ok(sheet.left === 0 && sheet.width === W && Math.round(sheet.bottom) === H && sheet.top > 200 && sheet.items === 5, `vocab bottom sheet ${JSON.stringify(sheet)}`);
    await p.tap('#hpBody .ir-vi:nth-child(3) button[title="跳到原文"]'); await p.waitForTimeout(500);
    const jumped = await p.evaluate(() => ({ open: document.getElementById('highlightsPanel').classList.contains('active'), active: [...document.querySelectorAll('#vContent mark.hl.active')].map(m => m.firstChild.nodeValue) }));
    ok(!jumped.open && JSON.stringify(jumped.active) === '["braid"]', `jump closes sheet and flashes the 3rd word ${JSON.stringify(jumped)}`);

    // 译文开关只藏中文，刷新后还记得
    await p.tap('#zhToggle'); await p.waitForTimeout(200);
    const hid = await p.evaluate(() => ({ hidden: getComputedStyle(document.querySelector('#vContent .reader p.zh')).display === 'none', en: getComputedStyle(document.querySelector('#vContent .reader p.en')).display !== 'none' }));
    await lib.settle(p); await p.reload(); await p.waitForFunction(() => document.querySelector('#vContent .reader p') && currentArticle); await p.waitForTimeout(300);
    const hid2 = await p.evaluate(() => getComputedStyle(document.querySelector('#vContent .reader p.zh')).display === 'none');
    ok(hid.hidden && hid.en && hid2, `译文 toggle hides zh only and survives reload ${JSON.stringify(hid)} ${hid2}`);
    await p.tap('#zhToggle'); await p.waitForTimeout(100);
    const shown = await p.evaluate(() => getComputedStyle(document.querySelector('#vContent .reader p.zh')).display !== 'none');
    ok(shown, '译文 toggle back on');

    ok(errs.length === 0, `page errors: ${errs.join(' | ')}`);
  } catch (e) {
    await p.screenshot({ path: `${cfg.out}/touch-crash-${engine}.png` }).catch(() => {});
    throw e;
  } finally {
    await ctx.close();
  }
};

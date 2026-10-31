// 文章页上的其它操作，桌面和手机各一遍：删除前要确认、图片条和大图、改标题（取消）、改分类（再改回来）、
// 已有朗读音频时的底部音频条、手机上「生成中」的进度文字。截图放到 --out / E2E_OUT 目录，方便人眼看一遍。
module.exports = async function suiteMisc({ cfg, browser, engine, t, lib }) {
  const { IDS } = lib;
  const ok = (c, w) => t.ok(c, w);
  for (const [tag, vp] of [['desk', { width: 1280, height: 820 }], ['phone', { width: 390, height: 844 }]]) {
    const ctx = await lib.newContext(cfg, browser, { viewport: vp, hasTouch: tag === 'phone', deviceScaleFactor: tag === 'phone' ? 2 : 1 });
    const p = await lib.newPage(ctx);
    const errs = []; const dialogs = [];
    p.on('pageerror', e => errs.push(String(e)));
    p.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
    const shot = name => p.screenshot({ path: `${cfg.out}/${tag}-${name}-${engine}.png` });
    try {
      await lib.openList(p, cfg);
      // 删除按钮先问一句（取消 → 什么都不删）
      const n0 = await p.evaluate(() => allItems.length);
      await p.evaluate(() => document.querySelector('.ir-card .ir-card-del').click());
      await p.waitForTimeout(200);
      const n1 = await p.evaluate(() => fetch('/intensive_list').then(r => r.json()).then(d => d.items.length));
      ok(dialogs.length === 1 && /删除/.test(dialogs[0]) && (await p.evaluate(() => allItems.length)) === n0 && n1 === n0, `${tag} delete asks and dismiss keeps it: ${dialogs} (${n0} → ${n1})`);

      // 图片条：缩略图真的加载出来，点开大图，Esc 关掉
      await lib.openArticle(p, IDS.chart);
      await p.waitForFunction(() => document.querySelector('#imagesGrid .image-item img'), null, { timeout: 5000 }).catch(() => {});
      await p.waitForFunction(() => { const i = document.querySelector('#imagesGrid .image-item img'); return i && i.complete && i.naturalWidth > 0; }, null, { timeout: 5000 }).catch(() => {});
      const im = await p.evaluate(() => { const i = document.querySelector('#imagesGrid .image-item img'); return { strip: document.getElementById('articleImages').style.display, loaded: i ? i.naturalWidth : -1, count: document.querySelectorAll('#imagesGrid .image-item').length }; });
      ok(im.strip !== 'none' && im.loaded === 160 && im.count === 1, `${tag} image strip shows a loaded thumbnail ${JSON.stringify(im)}`);
      await shot('images');
      await p.evaluate(() => document.querySelector('#imagesGrid .image-item').click());
      await p.waitForTimeout(400);
      const md = await p.evaluate(() => { const m = document.getElementById('imageModal'); const r = document.getElementById('modalImage').getBoundingClientRect(); return { disp: m.style.display, active: m.classList.contains('active'), w: r.width, h: r.height, counter: document.getElementById('imageCounter').textContent }; });
      ok(md.disp === 'block' && md.active && md.w > 50 && md.counter === '1 / 1', `${tag} image viewer opens ${JSON.stringify(md)}`);
      await shot('modal');
      await p.keyboard.press('Escape'); await p.waitForTimeout(450);
      ok((await p.evaluate(() => document.getElementById('imageModal').style.display)) === 'none', `${tag} Esc closes image viewer`);

      // 改标题：桌面点标题旁的铅笔，手机走 ⋯ 菜单；Esc 取消
      if (tag === 'desk') { await p.hover('.ir-title-wrap'); await p.click('#editTitleBtn'); } else { await p.click('#moreBtn'); await p.click('.ir-menu-item:has-text("修改标题")'); }
      await p.waitForTimeout(150);
      const te = await p.evaluate(() => ({ edit: document.getElementById('titleEditContainer').style.display, val: document.getElementById('titleEditInput').value, focus: document.activeElement.id, menu: document.getElementById('moreMenu').classList.contains('open') }));
      ok(te.edit === 'flex' && te.val === 'Task1-饼图-城市用电来源' && te.focus === 'titleEditInput' && !te.menu, `${tag} title edit opens ${JSON.stringify(te)}`);
      await shot('title');
      await p.keyboard.press('Escape'); await p.waitForTimeout(100);
      const te2 = await p.evaluate(() => ({ edit: document.getElementById('titleEditContainer').style.display, title: document.getElementById('vTitle').textContent, id: currentArticle.id }));
      ok(te2.edit === 'none' && te2.title === 'Task1-饼图-城市用电来源' && te2.id === IDS.chart, `${tag} Esc cancels title edit ${JSON.stringify(te2)}`);

      // ⋯ 菜单改分类：Writing → Listening → Writing，列表上的分类计数跟着变
      const counts = () => p.evaluate(() => [document.getElementById('count-Writing').textContent, document.getElementById('count-Listening').textContent, document.getElementById('moreMenu').classList.contains('open')]);
      const c0 = await counts();
      await p.click('#moreBtn'); await p.selectOption('#vCategory', 'Listening');
      await p.waitForFunction(() => currentArticle.category === 'Listening');
      const c1 = await counts();
      const saved = await p.evaluate(id => fetch('/intensive_article/' + encodeURIComponent(id)).then(r => r.json()).then(d => d.article.category), IDS.chart);
      await p.click('#moreBtn'); await p.selectOption('#vCategory', 'Writing');
      await p.waitForFunction(() => currentArticle.category === 'Writing');
      const c2 = await counts();
      ok(+c1[0] === +c0[0] - 1 && +c1[1] === +c0[1] + 1 && !c1[2] && saved === 'Listening' && c2[0] === c0[0] && c2[1] === c0[1], `${tag} category change moves the article ${JSON.stringify([c0, c1, saved, c2])}`);

      // 已有朗读音频：底部音频条贴着屏幕底，按钮变成「重新生成」
      await lib.openArticle(p, IDS.saltMarsh);
      await p.waitForFunction(() => document.getElementById('audioPanel').style.display === 'block');
      await p.waitForTimeout(400);
      const au = await p.evaluate(() => { const r = document.getElementById('audioPanel').getBoundingClientRect(); const a = document.getElementById('articleAudio'); const lbl = document.getElementById('generateAudioBtn').textContent.trim(); return { bottom: Math.round(r.bottom), h: Math.round(r.height), src: /article_audio_20261015_090500\.mp3$/.test(a.src), lbl }; });
      ok(au.bottom === vp.height && au.h < 70 && au.src && au.lbl === '重新生成', `${tag} audio bar at the bottom ${JSON.stringify(au)}`);
      const dur = await p.waitForFunction(() => { const a = document.getElementById('articleAudio'); return a.readyState >= 1 && isFinite(a.duration) ? a.duration : false; }, null, { timeout: 5000 }).then(h => h.jsonValue()).catch(() => null);
      ok(dur > 2 && dur < 4, `${tag} audio file loads (duration ${dur})`);
      await p.evaluate(() => document.getElementById('vContent').scrollTop = 99999); await p.waitForTimeout(150);
      const last = await p.evaluate(() => { const ps = document.querySelectorAll('#vContent .reader p'); const r = ps[ps.length - 1].getBoundingClientRect(); return { lastBottom: Math.round(r.bottom), barTop: Math.round(document.getElementById('audioPanel').getBoundingClientRect().top) }; });
      ok(last.lastBottom <= last.barTop, `${tag} last line not hidden behind the audio bar ${JSON.stringify(last)}`);
      await shot('audio');
      // 生成音频时的进度文字，在手机上也要看得见（手机上工具栏按钮只留图标）
      await p.evaluate(() => { document.getElementById('generateAudioBtn').innerHTML = btnLabel('spin', '生成第3段... (2/9)'); });
      const busy = await p.evaluate(() => { const s = document.querySelector('#generateAudioBtn .ir-busy'); const l = document.querySelector('#zhToggle .ir-lbl'); return { busy: !!s && getComputedStyle(s).display !== 'none', lbl: l ? getComputedStyle(l).display : null }; });
      ok(busy.busy && (tag === 'desk' ? busy.lbl !== 'none' : busy.lbl === 'none'), `${tag} progress text visible while generating ${JSON.stringify(busy)}`);
      await shot('busy');
      ok(errs.length === 0, `${tag} page errors ${errs.join(' | ')}`);
    } catch (e) {
      await shot('crash').catch(() => {});
      throw e;
    } finally {
      await ctx.close();
    }
  }
};

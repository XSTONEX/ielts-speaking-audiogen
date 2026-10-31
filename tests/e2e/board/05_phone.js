// 390 宽：不能横向溢出，主要功能能用
const { ok, login, open, shot, run } = require('./lib');
async function noOverflow(page, what) {
  const w = await page.evaluate(() => ({ doc: document.documentElement.scrollWidth, body: document.body.scrollWidth, vw: window.innerWidth }));
  ok(w.doc <= w.vw && w.body <= w.vw, `${what}: no horizontal overflow (${w.doc}/${w.vw})`);
}
run(async browser => {
  for (const dark of [false, true]) {
    const mode = dark ? 'dark' : 'light';
    const { page, ctx } = await login(browser, 'chenmo', { width: 390, height: 844, dark });
    await open(page);
    await noOverflow(page, `${mode} main`);
    await shot(page, `40-phone-${mode}`, { fullPage: true });
    // 顺序：等你完成 → 发帖框 → 帖子 → 最近的挑战
    const order = await page.evaluate(() => ['#pendingCard', '#composer', '#postsList', '#recentCard'].map(s => { const n = document.querySelector(s); return n && !n.hidden && getComputedStyle(n).display !== 'none' ? Math.round(n.getBoundingClientRect().top) : null; }));
    console.log('order tops', JSON.stringify(order));
    ok(order[1] < order[2] && (order[3] === null || order[3] > order[2]) && (order[0] === null || order[0] < order[1]), `${mode} phone order pending → composer → posts → recent`);
    if (!dark) {
      await page.click('.mb-composer__row .mb-tools button:has-text("录音")');
      await page.waitForSelector('.ui-dialog .mb-topic');
      await noOverflow(page, 'audio picker');
      await shot(page, `41-phone-audio`);
      await page.locator('.ui-dialog .mb-pick button:has-text("加入")').first().click();
      await page.click('.ui-dialog button:has-text("完成")');
      await page.click('.mb-composer__bar button:has-text("挑战")');
      await page.waitForSelector('.ui-dialog .mb-check');
      await noOverflow(page, 'challenge dialog');
      await shot(page, `42-phone-challenge`);
      const foot = await page.locator('.ui-dialog .ui-dialog__foot').boundingBox();
      ok(foot.y + foot.height <= 844, 'challenge dialog buttons visible on phone');
      await page.keyboard.press('Escape');
      await page.fill('.mb-composer__body textarea', '手机上发的一条测试帖');
      await noOverflow(page, 'composer open');
      await shot(page, `43-phone-composer`);
      await page.click('.mb-composer__send button:has-text("发布")');
      await page.waitForFunction(() => document.querySelector('#postsList .mb-post .mb-post__text')?.textContent.includes('手机上发的'));
      ok(true, 'post from phone works');
      // 做一题看看答题弹窗
      const startBtn = page.locator('.mb-ch button:has-text("开始挑战"), .mb-ch button:has-text("我也做一次")').first();
      if (await startBtn.count()) {
        await startBtn.click();
        await page.waitForSelector('.mb-quiz .mb-opt');
        await noOverflow(page, 'quiz');
        await shot(page, `44-phone-quiz`);
        await page.locator('.mb-opt').first().click();
        await page.waitForSelector('.mb-opt.is-right');
        await page.click('.mb-quiz__head button:has-text("退出")');
        await page.waitForSelector('.ui-dialog[role=alertdialog]');
        await page.click('.ui-dialog[role=alertdialog] button:has-text("退出")');
        ok(await page.locator('.mb-quiz').count() === 0, 'quit quiz on phone');
      } else console.log('SKIP no open challenge for quiz');
      await page.locator('.mb-images__btn').first().click();
      await page.waitForSelector('.mb-lightbox');
      await noOverflow(page, 'lightbox');
      await shot(page, `45-phone-lightbox`);
      await page.keyboard.press('Escape');
      const rk = page.locator('.mb-ch button:has-text("看排名")').first();
      await rk.click();
      await page.waitForSelector('.ui-dialog .mb-ranklist');
      await noOverflow(page, 'ranking');
      await shot(page, `46-phone-ranking`);
    }
    await ctx.close();
  }
});

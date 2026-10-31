// 暗色：主界面、选文章、发起挑战、发帖框、答题、排名、看大图
const { ok, login, open, shot, run } = require('./lib');
run(async browser => {
  const { page } = await login(browser, 'chenmo', { dark: true });
  await open(page);
  ok(await page.evaluate(() => document.documentElement.dataset.theme) === 'dark', 'dark theme applied');
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor.match(/\d+/g).slice(0, 3).map(Number));
  ok(bg[0] + bg[1] + bg[2] < 200, `page background is dark (${bg})`);
  await shot(page, `50-dark-main`);
  await page.click('.mb-composer__row .mb-tools button:has-text("文章")');
  await page.waitForSelector('.ui-dialog .mb-pick');
  await page.locator('.ui-dialog .mb-pick button:has-text("加入")').first().click();
  await shot(page, `51-dark-article-picker`);
  await page.keyboard.press('Escape');
  ok(await page.locator('.mb-composer__atts .mb-att').count() === 1, 'article added in dark mode');
  await page.click('.mb-composer__bar button:has-text("挑战")');
  await page.waitForSelector('.ui-dialog .mb-check');
  await page.click('.ui-dialog .mb-check >> nth=1');
  await page.click('.ui-dialog .ui-chip >> nth=0');
  await shot(page, `52-dark-challenge`);
  await page.keyboard.press('Escape');
  await page.fill('.mb-composer__body textarea', '暗色下的发帖框');
  await shot(page, `53-dark-composer`);
  const start = page.locator('.mb-ch button:has-text("开始挑战"), .mb-ch button:has-text("我也做一次")').first();
  if (await start.count()) {
    await start.click();
    await page.waitForSelector('.mb-quiz .mb-opt');
    await page.keyboard.press('2');
    await page.waitForSelector('.mb-opt.is-right');
    await shot(page, `54-dark-quiz`);
    await page.click('.mb-quiz__head button:has-text("退出")');
    await page.click('.ui-dialog[role=alertdialog] button:has-text("退出")');
    ok(await page.locator('.mb-quiz').count() === 0, 'quiz opens and quits in dark mode');
  }
  await page.locator('.mb-ch button:has-text("看排名")').first().click();
  await page.waitForSelector('.ui-dialog .mb-ranklist');
  ok(await page.locator('.ui-dialog .mb-ranklist').count() === 1, 'ranking opens in dark mode');
  await shot(page, `55-dark-ranking`);
  await page.keyboard.press('Escape');
  await page.locator('.mb-images__btn').first().click();
  await page.waitForSelector('.mb-lightbox');
  ok(await page.locator('.mb-lightbox').count() === 1, 'lightbox opens in dark mode');
  await shot(page, `56-dark-lightbox`);
});

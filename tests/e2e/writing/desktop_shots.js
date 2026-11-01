// 桌面截图：手机改版不能动桌面（>820px）一个像素。
// 同一份假数据、同一串操作，在改版前后的代码上各截一套，再用 compare_shots.py 逐张比像素。
// 用法：WP_SANDBOX=… WP_BASE_URL=… WP_SHOTS=<输出目录> ENGINE=chromium|webkit WIDTH=1280 node desktop_shots.js
// 保存练习记录的接口也在浏览器里拦下（回一个假 id），这样两次跑的数据、时间完全一样；页面时间固定在 2026-11-01 10:00。
const { open, run, ENGINE, SHOTS } = require('./lib');
const path = require('path');

const W = Number(process.env.WIDTH || 1280);
let n = 0;
async function snap(page, name, full = true) {
  n++;
  await page.waitForTimeout(350);
  await page.screenshot({ path: path.join(SHOTS, `${String(n).padStart(2, '0')}-${name}.png`), fullPage: full, animations: 'disabled', caret: 'hide' });
}

run(async browser => {
  if (!SHOTS) { console.log('CRASH 请设置 WP_SHOTS'); process.exit(1); }
  for (const dark of [false, true]) {
    const { ctx, page } = await open(browser, { desktop: true, width: W, height: 900, dark, fixedTime: '2026-11-01T10:00:00' });
    const fakeSave = r => r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ success: true, id: 'fake-record' }) });
    await ctx.route(/\/api\/writing\/(small\/|template\/)?save_practice/, fakeSave);
    const tag = dark ? 'dark-' : '';
    await snap(page, tag + 'home');
    if (dark) {
      await page.click('text=写作思维链'); await page.waitForTimeout(900);
      await page.locator('#subList .mode-btn.practice').first().click(); await page.waitForTimeout(900);
      await page.fill('#transInput', 'Older people who live with their children are rarely alone.');
      await page.click('#submitBtn'); await page.waitForTimeout(1200);
      await snap(page, 'dark-big-result');
      await ctx.close();
      continue;
    }
    // ---- 复习中心、速记、AI（先截，免得后面的操作改了数据） ----
    await page.click('.home-tool >> text=复习中心'); await page.waitForTimeout(1200);
    await snap(page, 'review-small', false);
    await page.click('.review-overlay-tab[data-tab="big"]'); await page.waitForTimeout(700);
    await page.locator('#reviewBigContent .rv-group-head').first().click();
    await page.locator('#reviewBigContent .rv-item-head').first().click();
    await snap(page, 'review-big-item', false);
    await page.click('.review-overlay-tab[data-tab="tpl"]'); await page.waitForTimeout(700);
    await page.click('.review-sort-btn[data-sort="recent"]'); await page.waitForTimeout(500);
    await snap(page, 'review-tpl-recent', false);
    await page.click('.review-overlay-close'); await page.waitForTimeout(400);
    await page.click('.np-fab'); await page.waitForTimeout(700);
    await snap(page, 'notepad', false);
    await page.click('#npWindow button[title="收起"]'); await page.waitForTimeout(600);
    await page.click('#aiFloatBtn'); await page.waitForTimeout(700);
    await snap(page, 'ai-empty', false);
    await page.click('.ai-chat-header-actions button[title="历史记录"]'); await page.waitForTimeout(700);
    await snap(page, 'ai-history', false);
    await page.click('#aiHistoryPanel button'); await page.waitForTimeout(300);
    await page.click('#aiChatWindow button[title="关闭"]'); await page.waitForTimeout(600);

    // ---- 大作文 · 思维链 ----
    await page.click('text=写作思维链'); await page.waitForTimeout(900);
    await snap(page, 'big-directory');
    await page.locator('#subList .mode-btn.learn').first().click(); await page.waitForTimeout(900);
    await snap(page, 'big-learn');
    // 电脑上的荧光笔：拖选一个词，松开鼠标弹出「高亮」
    const sent = page.locator('#exampleList .ex-card.is-open .sentence-en').first();
    await sent.scrollIntoViewIfNeeded();
    const b = await sent.boundingBox();
    await page.mouse.move(b.x + 4, b.y + 12); await page.mouse.down();
    await page.mouse.move(b.x + 60, b.y + 12, { steps: 4 }); await page.mouse.up();
    await snap(page, 'big-learn-hl-toolbar', false);
    await page.mouse.click(5, 5);
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.click('#learningView .seg-btn >> text=实战'); await page.waitForTimeout(900);
    await snap(page, 'big-practice');
    await page.click('text=先看提示'); await page.waitForTimeout(400);
    await snap(page, 'big-practice-hint');
    await page.fill('#transInput', 'Technology have changed the way people communicate.');
    await page.click('#submitBtn'); await page.waitForTimeout(1200);
    await snap(page, 'big-result');
    await page.fill('.practice-followup textarea', '为什么用现在完成时？');
    await page.click('.followup-send'); await page.waitForTimeout(800);
    await snap(page, 'big-followup');
    await page.click('.fb-actions .submit-btn'); await page.waitForTimeout(900);
    await snap(page, 'big-next');
    await page.locator('#sentenceList .sent-item').first().click(); await page.waitForTimeout(500);
    const hist = page.locator('.task-hist-btn');
    if (await hist.count()) { await hist.click(); await page.waitForTimeout(500); await snap(page, 'big-history'); }

    // ---- 小作文 · 仿写 ----
    await page.evaluate(() => backToEntry()); await page.waitForTimeout(600);
    await page.click('text=小作文仿写'); await page.waitForTimeout(900);
    await snap(page, 'small-list');
    await page.locator('#smallExampleList .mode-btn.learn').first().click(); await page.waitForTimeout(900);
    await snap(page, 'small-learn');
    await page.click('#smallLearnImageZone .fig-img'); await page.waitForTimeout(500);
    await snap(page, 'small-lightbox', false);
    await page.keyboard.press('Escape'); await page.waitForTimeout(300);
    await page.click('.sl-go'); await page.waitForTimeout(900);
    await snap(page, 'small-practice');
    await page.fill('#smallTransInput', 'Overall, shared bike use rose in all three cities.');
    await page.click('#smallSubmitBtn'); await page.waitForTimeout(1300);
    await snap(page, 'small-result');

    // ---- 模板 · 大作文 ----
    await page.evaluate(() => backToEntry()); await page.waitForTimeout(600);
    await page.locator('.entry-column.is-big .entry-card').nth(1).click(); await page.waitForTimeout(1000);
    await snap(page, 'tplbig-types');
    await page.locator('.tpl-type-card').first().click(); await page.waitForTimeout(1000);
    await snap(page, 'tplbig-samples');
    await page.locator('#tplBigSamplesBody .tbs-card .tbs-btn').first().click(); await page.waitForTimeout(1000);
    await snap(page, 'tplbig-learn');
    await page.click('#tplBigLearnToolbar .tpl-btn'); await page.waitForTimeout(1000);
    await snap(page, 'tplbig-practice');
    await page.click('.tpl-eye-btn'); await page.waitForTimeout(300);
    await page.fill('#tplAnswer', 'Personally, I totally agree with this view.');
    await page.click('#tplSubmitBtn'); await page.waitForTimeout(1300);
    await snap(page, 'tplbig-result');
    await page.click('.tpl-side-link'); await page.waitForTimeout(1000);
    await snap(page, 'tpl-ref');

    // ---- 模板 · 小作文 ----
    await page.evaluate(() => backToEntry()); await page.waitForTimeout(600);
    await page.locator('.entry-column.is-small .entry-card').nth(1).click(); await page.waitForTimeout(1200);
    await snap(page, 'tplsmall-charts');
    await page.locator('#tplSmallSecGrid .tpl-type-card').nth(2).click(); await page.waitForTimeout(1000);
    await snap(page, 'tplsmall-examples');
    await page.locator('#tplSmallExBody .tbs-card .tbs-btn').first().click(); await page.waitForTimeout(1200);
    await snap(page, 'tplsmall-learn');
    await page.click('.tsl-cta-btn'); await page.waitForTimeout(1200);
    await snap(page, 'tplsmall-practice');
    await page.fill('#tplAnswer', 'Northport began with about 12,000 trips a day.');
    await page.click('#tplSubmitBtn'); await page.waitForTimeout(1300);
    await snap(page, 'tplsmall-result');
    await ctx.close();
  }
  console.log(`SHOTS ${ENGINE} ${W} ${n}`);
});

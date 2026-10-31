// 打开页面：亮色 / 暗色都能渲染出帖子和评论，标题对，标准模式
const { ok, login, open, shot, run } = require('./lib');

run(async browser => {
  for (const dark of [false, true]) {
    const mode = dark ? 'dark' : 'light';
    const { page, ctx } = await login(browser, 'linxia', { dark });
    await open(page);
    ok(await page.locator('.mb-post').count() === 5, `${mode}: 5 posts rendered`);
    ok(await page.locator('.mb-comment').count() === 3, `${mode}: 3 comments rendered`);
    ok(await page.title() === '学习交流小天地 · IELTS Lab', `${mode}: page title`);
    ok((await page.textContent('#postCount')) === '共 5 篇帖子', `${mode}: post count`);
    ok(await page.evaluate(() => document.compatMode) === 'CSS1Compat', `${mode}: standards mode`);
    ok(await page.evaluate(() => document.documentElement.dataset.theme || 'light') === mode, `${mode}: theme applied`);
    await shot(page, `01-main-${mode}`, { fullPage: true });
    await ctx.close();
  }
});

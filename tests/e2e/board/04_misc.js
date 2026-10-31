// 看大图、帖子里播放、链接、删评论、删帖、空列表、读取失败、没登录跳转
const { ok, login, offline, open, shot, run, allowError, BASE } = require('./lib');
run(async browser => {
  let { page, ctx } = await login(browser, 'linxia');
  await open(page);
  // 看大图：林夏的新帖两张图
  const lx = page.locator('#postsList .mb-post').first();
  await lx.locator('.mb-post__atts .mb-images__btn').first().click();
  await page.waitForSelector('.mb-lightbox');
  ok((await page.textContent('.mb-lightbox__count')).startsWith('1 / 2'), 'lightbox opens on a single click with 1 / 2');
  await shot(page, `30-lightbox`);
  await page.keyboard.press('ArrowRight');
  ok((await page.textContent('.mb-lightbox__count')).startsWith('2 / 2'), 'arrow key goes to next image');
  await page.keyboard.press('Escape');
  ok(await page.locator('.mb-lightbox').count() === 0, 'Esc closes lightbox');
  await lx.locator('.mb-post__atts .mb-images__btn').first().click();
  await page.mouse.click(30, 450);
  ok(await page.locator('.mb-lightbox').count() === 0, 'click on blank area closes lightbox');

  // 帖子里直接播放
  const att = page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-att').first();
  await att.locator('.mb-play').click();
  await page.waitForSelector('.mb-player');
  await page.waitForTimeout(400);
  ok(await att.locator('.mb-play[aria-label="暂停"]').count() === 1, 'play button turns into pause');
  await shot(page, `31-playing`);
  // 换另一条：第一条恢复
  const att2 = page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-att').nth(1);
  await att2.locator('.mb-play').click();
  await page.waitForTimeout(300);
  ok(await att.locator('.mb-player').count() === 0 && await att2.locator('.mb-player').count() === 1, 'only one recording plays at a time');
  await page.waitForTimeout(2600); // 静音样本 2 秒，放完复原
  ok(await att2.locator('.mb-player').count() === 0, 'player resets when the recording ends');
  const href = await page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-att a').first().getAttribute('href');
  ok(href.startsWith('/speaking#folder=') && href.includes('&file='), 'single recording links to /speaking#folder=…&file=…');
  ok((await page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-att a').nth(1).getAttribute('href')).startsWith('/combined#folder='), 'collection links to /combined');
  ok((await page.locator('.mb-post[data-post-id="msg_fake_0002"] .mb-att a').getAttribute('href')) === '/intensive#article-20261001100000-glass-bridge', 'article links to /intensive#article-<id>');

  // 删评论：林夏自己在周屿图片帖下的评论
  const imgPost = page.locator('.mb-post[data-post-id="msg_fake_0003"]');
  await imgPost.locator('.mb-comment__del').click();
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  await page.click('.ui-dialog[role=alertdialog] button:has-text("删除")');
  await page.waitForTimeout(800);
  ok(await imgPost.locator('.mb-comment').count() === 0 && (await imgPost.locator('.mb-post__foot .mb-meta').textContent()) === '还没有评论', 'comment deleted after confirm');
  // 删帖：先取消一次
  const art = page.locator('.mb-post[data-post-id="msg_fake_0002"]');
  await art.locator('.mb-iconbtn--danger').click();
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  await shot(page, `32-delete-confirm`);
  await page.click('.ui-dialog[role=alertdialog] button:has-text("取消")');
  ok(await art.count() === 1, 'cancel keeps the post');
  await art.locator('.mb-iconbtn--danger').click();
  await page.click('.ui-dialog[role=alertdialog] button:has-text("删除")');
  await page.waitForTimeout(800);
  ok(await page.locator('.mb-post[data-post-id="msg_fake_0002"]').count() === 0, 'post deleted');
  ok((await page.textContent('#postCount')) === '共 5 篇帖子', 'post count updated');
  ok(await page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-post__head .mb-iconbtn--danger').count() === 0, 'no delete button on other people\'s posts');
  await ctx.close();

  // 空列表和读取失败
  ({ page, ctx } = await login(browser, 'linxia'));
  await page.route('**/api/messages', r => r.fulfill({ status: 200, contentType: 'application/json', body: '{"success":true,"messages":[]}' }));
  await page.goto(BASE + '/message_board');
  await page.waitForSelector('#emptyState');
  await shot(page, `33-empty`);
  await page.click('#emptyState button');
  ok(await page.locator('.mb-composer__body').isVisible(), 'empty state button opens the composer');
  await page.unroute('**/api/messages');
  allowError(/status of 500/);   // 下面故意让帖子列表返回 500
  await page.route('**/api/messages', r => r.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"boom"}' }));
  await page.goto(BASE + '/message_board');
  await page.waitForSelector('.ui-empty:has-text("帖子没读出来")');
  ok(true, 'load failure shows a retry card');
  await ctx.close();

  // 没登录 → 去登录页
  const anon = await browser.newContext();
  await offline(anon);
  const ap = await anon.newPage();
  await ap.goto(BASE + '/message_board');
  await ap.waitForURL('**/login', { timeout: 5000 }).catch(() => {});
  ok(ap.url().endsWith('/login'), 'no token redirects to /login');
  await anon.close();
});

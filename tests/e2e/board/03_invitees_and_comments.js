// 周屿（被 @）做挑战、写带多个附件和挑战的评论；陈默做没被邀请的挑战
const { ok, login, open, shot, run, doQuiz, FX } = require('./lib');
run(async browser => {
  // ---------- 周屿 ----------
  let { page, ctx } = await login(browser, 'zhouyu');
  await open(page);
  const pend = await page.textContent('#pendingCard');
  ok(pend.includes('玻璃桥生词小测') && pend.includes('林夏 邀请你'), 'invitee sees pending challenge with inviter name');
  ok(!(await page.textContent('#recentCard')).includes('null'), 'recent card has no stray null');
  await shot(page, `20-zhouyu-main`);
  await page.click('#pendingCard .mb-pending__title');
  await page.waitForTimeout(700);
  ok(await page.locator('.mb-post.is-flash').count() === 1, 'clicking a pending title flashes its post');
  await shot(page, `21-flash`);
  await page.click('#pendingCard button:has-text("开始")');
  await doQuiz(page);
  await page.waitForSelector('.ui-dialog:has-text("交卷了")', { timeout: 20000 });
  ok((await page.textContent('.ui-dialog')).includes('陈默'), 'result names the remaining invitee');
  await page.click('.ui-dialog button:has-text("看排名")');
  await page.waitForSelector('.ui-dialog .mb-rank');
  ok(await page.locator('.ui-dialog .mb-rank:not(.is-waiting)').count() === 2, 'ranking now has two finishers');
  await shot(page, `22-ranking-two`);
  await page.keyboard.press('Escape');

  // 先打开某帖的评论 → 选录音 → 直接关掉；再给新帖加录音，录音不能跑到评论里（旧 bug）
  const imgPost = page.locator('.mb-post[data-post-id="msg_fake_0003"]');
  await imgPost.locator('.mb-post__foot button').click();
  await imgPost.locator('.mb-reply button:has-text("录音")').click();
  await page.waitForSelector('.ui-dialog .mb-topic');
  await page.keyboard.press('Escape');
  await page.click('.mb-composer__row .mb-tools button:has-text("录音")');
  await page.waitForSelector('.ui-dialog .mb-pick button:has-text("加入")');
  await page.locator('.ui-dialog .mb-pick button:has-text("加入")').first().click();
  await page.click('.ui-dialog button:has-text("完成")');
  ok(await page.locator('.mb-composer__atts .mb-att').count() === 1 && await imgPost.locator('.mb-reply .mb-att').count() === 0, 'audio goes to the composer, not the comment opened earlier');
  await page.click('.mb-composer__send button:has-text("取消")');
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  await page.click('.ui-dialog[role=alertdialog] button:has-text("放弃")');
  ok(!(await page.locator('.mb-composer__body').isVisible()), 'cancel with content asks, then clears');
  await imgPost.locator('.mb-post__foot button').click(); // 收起空评论框
  ok(await imgPost.locator('.mb-reply').count() === 0, 'empty reply closes without asking');

  // 在林夏的新帖下写评论：文章 + 录音 + 图片 + 挑战（不 @ 人）
  const lxPost = page.locator('#postsList .mb-post').first();
  await lxPost.locator('.mb-post__foot button').click();
  const reply = lxPost.locator('.mb-reply');
  await reply.locator('textarea').fill('这篇文章里讲停顿的那段可以参考一下：');
  await reply.locator('button:has-text("文章")').click();
  await page.locator('.ui-dialog .ui-rail__item:has-text("Listening")').click();
  await page.locator('.ui-dialog .mb-pick:has-text("Campus Radio") button:has-text("加入")').click();
  await page.click('.ui-dialog button:has-text("完成")');
  await reply.locator('button:has-text("录音")').click();
  await page.locator('.ui-dialog .ui-rail__item:has-text("Part 3")').click();
  await page.locator('.ui-dialog .mb-pick button:has-text("加入")').first().click();
  await page.click('.ui-dialog button:has-text("完成")');
  ok(await reply.locator('.mb-att').count() === 2, 'second comment attachment does not wipe the first');
  const [fc] = await Promise.all([page.waitForEvent('filechooser'), reply.locator('button:has-text("图片")').click()]);
  await fc.setFiles([FX + '/b.png']);
  await page.waitForFunction(() => document.querySelector('.mb-reply .mb-thumb img') && !document.querySelector('.mb-reply .mb-thumb__mask'), null, { timeout: 10000 });
  await reply.locator('button:has-text("挑战")').click();
  await page.waitForSelector('.ui-dialog .mb-check');
  await page.fill('.ui-dialog input[maxlength="40"]', '旅行话题热身');
  await page.click('.ui-dialog .mb-check:has-text("Campus Radio")');
  await page.click('.ui-dialog .mb-check:has-text("Urban Bees")');
  await page.click('.ui-dialog .ui-seg__btn:has-text("10")');
  await page.click('.ui-dialog button:has-text("创建挑战")');
  await reply.locator('.mb-ch').waitFor();
  await shot(page, `23-reply-editor`);
  await reply.locator('button:has-text("发表")').click();
  await page.waitForFunction(() => document.querySelector('#postsList .mb-post .mb-comments:not([hidden]) .mb-comment'));
  await page.waitForTimeout(800);
  const c = lxPost.locator('.mb-comment').last();
  ok(await c.locator('.mb-att').count() === 2 && await c.locator('.mb-images__img').count() === 1 && await c.locator('.mb-ch').count() === 1, 'comment shows article, audio, image and challenge');
  ok((await lxPost.locator('.mb-post__foot .mb-meta').textContent()).includes('1 条评论'), 'comment count updates');
  ok((await page.textContent('#pendingCard')).includes('旅行话题热身') && (await page.textContent('#pendingCard')).includes('你发起的'), 'challenge inside a comment shows up as pending for its creator');
  ok((await page.textContent('#recentCard')).includes('旅行话题热身'), 'recent card shows the newest challenge');
  await shot(page, `24-comment-posted`);
  await ctx.close();

  // ---------- 陈默 ----------
  ({ page, ctx } = await login(browser, 'chenmo'));
  await open(page);
  const lx = page.locator('#postsList .mb-post').first();
  ok((await lx.locator('.mb-ch').first().textContent()).includes('开始挑战'), 'invited user sees 开始挑战 on the post challenge');
  const cch = lx.locator('.mb-comment .mb-ch');
  ok((await cch.textContent()).includes('我也做一次'), 'uninvited user sees 我也做一次 (not a misleading 查看结果)');
  ok(!(await page.textContent('#pendingCard')).includes('旅行话题热身'), 'uninvited challenge is not pending');
  await shot(page, `25-chenmo-main`, { fullPage: true });
  await cch.locator('button:has-text("看排名")').click();
  await page.waitForSelector('.ui-dialog .mb-ranklist');
  await shot(page, `26-ranking-empty`);
  await page.keyboard.press('Escape');
  await cch.locator('button:has-text("我也做一次")').click();
  await doQuiz(page);
  await page.waitForSelector('.ui-dialog:has-text("交卷了")', { timeout: 30000 });
  await page.keyboard.press('Escape');
  await page.waitForTimeout(600);
  ok((await cch.textContent()).includes('你的成绩'), 'uninvited user score shows after finishing');
  await ctx.close();
});

// 林夏：发一篇带录音、文章、图片、挑战的帖子，然后自己做挑战
const { ok, login, open, shot, run, FX } = require('./lib');
run(async browser => {
  const { page } = await login(browser, 'linxia');
  await open(page);
  // 失效挑战的帖子
  const gone = page.locator('.mb-post[data-post-id="msg_fake_0005"] .mb-ch');
  ok((await gone.textContent()).includes('题目已经不在了'), 'missing challenge shows gone state');

  // 收起的发帖框点「录音」直接展开并打开选录音
  await page.click('.mb-composer__row .mb-tools button:has-text("录音")');
  await page.waitForSelector('.ui-dialog .mb-topic');
  ok(await page.locator('.mb-composer__body').isVisible(), 'composer expands when a tool is clicked');
  await shot(page, `03-audio-picker`);
  // 撇号的那条（以前点了没反应）
  await page.locator('.ui-dialog .mb-pick:has-text("What\'s the most") button:has-text("加入")').click();
  ok(await page.locator('.ui-dialog .mb-pick:has-text("What\'s the most") .ui-tag--ok').count() === 1, 'apostrophe audio can be added');
  // 搜索
  await page.fill('.ui-dialog input[type=search]', 'future');
  await page.waitForTimeout(150);
  ok(await page.locator('.ui-dialog .mb-pick').count() === 1, 'search narrows rows to the matching question');
  await page.fill('.ui-dialog input[type=search]', '');
  await page.click('.ui-dialog .ui-rail__item:has-text("Part 2")');
  await page.locator('.ui-dialog .mb-pick:has-text("整套合集") button:has-text("加入")').click();
  await shot(page, `04-audio-picker-added`);
  await page.click('.ui-dialog button:has-text("完成")');
  ok(await page.locator('.mb-composer__atts .mb-att').count() === 2, 'two audios in the composer');

  // 文章
  await page.click('.mb-composer__bar button:has-text("文章")');
  await page.waitForSelector('.ui-dialog .mb-pick');
  await page.locator('.ui-dialog .mb-pick:has-text("The Glass Bridge") button:has-text("加入")').click();
  await shot(page, `05-article-picker`);
  await page.keyboard.press('Escape');
  ok(await page.locator('.mb-composer__atts .mb-att').count() === 3, 'article added, Esc closes picker');

  // 图片：两张好的 + 一张超大 + 一个不是图片的
  const [fc] = await Promise.all([page.waitForEvent('filechooser'), page.click('.mb-composer__bar button:has-text("图片")')]);
  await fc.setFiles([FX + '/a.png', FX + '/b.png', FX + '/big.jpg', FX + '/note.txt']);
  await page.waitForTimeout(100);
  await shot(page, `06-uploading`);
  await page.waitForFunction(() => !document.querySelector('.mb-thumb__mask'), null, { timeout: 15000 });
  ok(await page.locator('.mb-composer__atts .mb-thumb img').count() === 2, 'two images uploaded, big/non-image rejected');
  ok(await page.locator('.mb-composer__atts .mb-att').count() === 3, 'earlier attachments still visible after adding images');
  const toasts = await page.locator('.ielts-toast').allTextContents();
  console.log('toasts:', JSON.stringify(toasts));

  // 挑战
  await page.click('.mb-composer__bar button:has-text("挑战")');
  await page.waitForSelector('.ui-dialog .mb-check');
  await page.click('.ui-dialog button:has-text("创建挑战")');
  ok((await page.textContent('.ui-dialog .mb-field-err')).includes('名字'), 'title required message');
  await page.fill('.ui-dialog input[maxlength="40"]', '玻璃桥生词小测');
  await page.fill('.ui-dialog input[maxlength="120"]', '看看谁记得最牢 <b>粗</b><img src=x onerror="window.__xss=1">');
  await page.click('.ui-dialog .mb-check:has-text("The Glass Bridge")');
  await page.click('.ui-dialog .ui-chip:has-text("周屿")');
  await page.click('.ui-dialog .ui-chip:has-text("陈默")');
  await shot(page, `07-challenge-create`);
  const box = await page.locator('.ui-dialog').boundingBox();
  ok(box.y >= 0 && box.y + box.height <= 860, 'create dialog fits in 1280x860 (head and buttons visible)');
  await page.click('.ui-dialog button:has-text("创建挑战")');
  await page.waitForSelector('.mb-composer__atts .mb-ch');
  ok(await page.locator('.mb-composer__bar button:has-text("挑战")').isDisabled(), 'challenge button disabled after one challenge');
  await page.fill('.mb-composer__body textarea', '周末前来比一比，玻璃桥那篇的生词都在里面。');
  await shot(page, `02-composer`);
  await page.click('.mb-composer__send button:has-text("发布")');
  await page.waitForFunction(() => document.querySelector('#postsList .mb-post .mb-post__text')?.textContent.includes('周末前来比一比'));
  ok(!(await page.locator('.mb-composer__body').isVisible()), 'composer collapses after posting');
  const first = page.locator('#postsList .mb-post').first();
  ok(await first.locator('.mb-att').count() === 3 && await first.locator('.mb-images__img').count() === 2 && await first.locator('.mb-ch').count() === 1, 'new post shows 3 attachments, 2 images, 1 challenge');
  await page.waitForTimeout(600);
  ok((await first.locator('.mb-ch').textContent()).includes('开始挑战'), 'creator sees 开始挑战');
  ok((await first.locator('.mb-ch__people').textContent()).includes('周屿 · 未完成'), 'invitees shown with display names');
  ok(await first.locator('.mb-ch__desc b').count() === 0 && (await first.locator('.mb-ch__desc').textContent()).includes('<b>'), 'description is plain text');
  ok((await page.textContent('#pendingCard')).includes('玻璃桥生词小测'), 'own challenge listed as pending');
  await shot(page, `08-after-post`);

  // 做题
  await first.locator('button:has-text("开始挑战")').click();
  await page.waitForSelector('.mb-quiz .mb-opt');
  await shot(page, `09-quiz`);
  await page.keyboard.press('1');                       // 第 1 题：数字键
  await page.waitForSelector('.mb-opt.is-right');
  await shot(page, `10-quiz-answered`);
  await page.waitForFunction(() => !document.querySelector('.mb-opt:disabled'), null, { timeout: 4000 });
  await page.click('.mb-quiz__head button:has-text("退出")'); // 第 2 题：退出 → 接着答
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  await shot(page, `11-quiz-quit-confirm`);
  const before = await page.textContent('.mb-timer__num');
  await page.waitForTimeout(1500);
  await page.click('.ui-dialog[role=alertdialog] button:has-text("接着答")');
  const after = await page.textContent('.mb-timer__num');
  ok(before === after, `timer paused while confirming (before ${before}, after ${after})`);
  await page.locator('.mb-opt').nth(1).click();
  await page.waitForFunction(() => !document.querySelector('.mb-opt:disabled'), null, { timeout: 4000 });
  // 第 3 题：等超时
  await page.waitForSelector('.mb-notice:not([hidden])', { timeout: 12000 });
  ok(await page.locator('.mb-opt.is-right').count() === 1, 'timeout reveals the right answer');
  await shot(page, `12-quiz-timeout`);
  await page.waitForFunction(() => !document.querySelector('.mb-opt:disabled'), null, { timeout: 4000 });
  await page.keyboard.press('3');
  await page.waitForFunction(() => !document.querySelector('.mb-opt:disabled') || !document.querySelector('.mb-quiz'), null, { timeout: 4000 });
  await page.keyboard.press('4');
  await page.waitForSelector('.ui-dialog:has-text("交卷了")', { timeout: 8000 });
  await shot(page, `13-result`);
  const resultText = await page.textContent('.ui-dialog');
  ok(resultText.includes('超时'), 'result lists the timed-out word');
  ok(resultText.includes('周屿') && resultText.includes('还没做'), 'result says who has not done it');
  await page.click('.ui-dialog button:has-text("看排名")');
  await page.waitForSelector('.ui-dialog .mb-rank');
  await shot(page, `14-ranking`);
  ok(await page.locator('.ui-dialog .mb-rank-info__desc b').count() === 0, 'ranking description not parsed as HTML');
  ok(await page.locator('.ui-dialog .mb-rank.is-waiting').count() === 2, 'two invitees waiting in ranking');
  await page.click('.ui-dialog__foot button:has-text("关闭")');
  await page.waitForTimeout(500);
  ok((await first.locator('.mb-ch__mine').textContent()).includes('你的成绩'), 'card switches to my score');
  ok(!(await page.textContent('#pendingCard')).includes('玻璃桥生词小测'), 'pending list updates after finishing');
  await shot(page, `15-after-quiz`, { fullPage: false });
  ok(await page.evaluate(() => !window.__xss), 'no script ran from user text');
});

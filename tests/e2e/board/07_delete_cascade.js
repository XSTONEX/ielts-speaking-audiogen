// 删帖时连带删掉它的评论和评论里的挑战。要在刚建好的假数据上跑（msg_fake_0002 还在）
const fs = require('fs');
const path = require('path');
const { ok, login, open, shot, run, BASE, SANDBOX, toks } = require('./lib');

async function call(who, url, json, method) {
  const r = await fetch(BASE + url, {
    method: method || (json ? 'POST' : 'GET'),
    headers: { Authorization: 'Bearer ' + toks[who].token, 'Content-Type': 'application/json' },
    body: json ? JSON.stringify(json) : undefined
  });
  return { status: r.status, body: await r.json() };
}
const content = (text, challenge) => ({ text, audios: [], articles: [], images: [], challenge: challenge || null });
const pendingHas = (page, title) => page.waitForFunction(t => document.querySelector('#pendingCard').textContent.includes(t), title, { timeout: 6000 }).then(() => true, () => false);

run(async browser => {
  // 准备：周屿在林夏的帖子下评论一个挑战（@林夏），陈默再评论一句；林夏另发一条没评论的帖子
  const made = await call('zhouyu', '/api/create_challenge', {
    title: '评论里的挑战', description: '', article_ids: ['20261001100000-glass-bridge'], word_count: 5, mentioned_users: ['linxia'] });
  const chId = made.body.challenge_id;
  ok(made.status === 200 && chId, 'setup: zhouyu created a challenge');
  const ch = { id: chId, title: '评论里的挑战', description: '', vocabulary_count: 5, mentioned_users: ['linxia'] };
  ok((await call('zhouyu', '/api/comments', { post_id: 'msg_fake_0002', type: 'mixed_content', content: content('来比一比', ch) })).status === 200, 'setup: challenge comment');
  ok((await call('chenmo', '/api/comments', { post_id: 'msg_fake_0002', type: 'mixed_content', content: content('我也来') })).status === 200, 'setup: plain comment');
  const lone = await call('linxia', '/api/messages', { type: 'mixed_content', content: content('一条没有评论的帖子'), token: toks.linxia.token });
  const loneId = lone.body.message.id;
  const chFile = path.join(SANDBOX, 'challenges', `${chId}.json`);
  ok(fs.existsSync(chFile), 'setup: challenge file on disk');

  let { page, ctx } = await login(browser, 'linxia');
  await open(page);
  ok(await pendingHas(page, '评论里的挑战'), 'before: pending card lists the comment challenge');
  const target = page.locator('.mb-post[data-post-id="msg_fake_0002"]');
  ok(await target.locator('.mb-comment').count() === 2, 'before: post shows 2 comments');

  // 没评论的帖子：提示只说不能恢复
  await page.locator(`.mb-post[data-post-id="${loneId}"] .mb-post__head .mb-iconbtn--danger`).click();
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  ok((await page.textContent('.ui-dialog[role=alertdialog] .mb-dialog-text')) === '删除后不能恢复。', 'no-comment post: plain warning');
  await page.click('.ui-dialog[role=alertdialog] button:has-text("取消")');

  // 有评论和挑战的帖子
  await target.locator('.mb-post__head .mb-iconbtn--danger').click();
  await page.waitForSelector('.ui-dialog[role=alertdialog]');
  const text = await page.textContent('.ui-dialog[role=alertdialog] .mb-dialog-text');
  ok(text === '下面的 2 条评论会一起删除。其中的单词挑战和大家的成绩也会删除。删除后不能恢复。', 'warning mentions comments and challenge: ' + text);
  await shot(page, '34-delete-cascade-confirm');
  await page.click('.ui-dialog[role=alertdialog] button:has-text("删除")');
  await page.waitForTimeout(900);
  ok(await target.count() === 0, 'post removed from the feed');
  ok(!(await page.textContent('#pendingCard')).includes('评论里的挑战'), 'pending card no longer lists the challenge');
  ok(!(await page.textContent('#recentCard')).includes('评论里的挑战'), 'recent card does not show the challenge');
  await shot(page, '35-after-cascade-delete');

  // 服务器上的数据
  ok((await call('linxia', '/api/comments/msg_fake_0002')).body.comments.length === 0, 'server: no comments left for the post');
  ok((await call('linxia', '/api/get_challenge/' + chId)).status === 404, 'server: challenge gone (404)');
  ok(!fs.existsSync(chFile), 'disk: challenge file deleted');
  const left = JSON.parse(fs.readFileSync(path.join(SANDBOX, 'message_board', 'comments.json'), 'utf8')).map(c => c.id).sort();
  ok(JSON.stringify(left) === JSON.stringify(['comment_fake_0001', 'comment_fake_0002', 'comment_fake_0003']), 'disk: other posts\' comments kept ' + left);

  // 刷新后、换人看都一致
  await open(page);
  ok(await target.count() === 0 && !(await page.textContent('#pendingCard')).includes('评论里的挑战'), 'after reload: still gone');
  await ctx.close();
  ({ page, ctx } = await login(browser, 'zhouyu'));
  await open(page);
  ok(await page.locator('.mb-post[data-post-id="msg_fake_0002"]').count() === 0, 'zhouyu: post gone');
  ok(await page.locator('.mb-post[data-post-id="msg_fake_0001"] .mb-comment').count() === 2, 'zhouyu: comments on other posts still there');
  await ctx.close();
});

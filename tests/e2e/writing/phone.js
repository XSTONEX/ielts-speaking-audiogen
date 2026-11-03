// 手机：每个页面不横向溢出、能点的够大、改版后的每条新流程都走一遍。
// WebKit 390×844（iPhone Safari）/ Chromium 360×780（Android），亮色全走一遍，暗色抽主要几页。
// 键盘弹起用把视口压到 470px 高来模拟（真机的 iOS 键盘只能真机上看）。
const { ok, step, open, shot, overflowX, box, run, ENGINE } = require('./lib');

const KB_H = 470;

async function view(page) { return page.evaluate(() => state.view); }
async function sheetOpen(page) { return page.evaluate(() => { const s = document.querySelector('.wp-sheet'); return !!s && !s.hidden; }); }
async function navBottom(page) { const b = await box(page, '.app-shell-nav'); return b ? b.bottom : 0; }
async function barTop(page) { const b = await box(page, '#wpActBar'); return b ? b.top : (await page.evaluate(() => innerHeight)); }
async function vw(page) { return page.evaluate(() => innerWidth); }
async function vh(page) { return page.evaluate(() => innerHeight); }
async function back(page) { await page.goBack(); await page.waitForTimeout(600); }
async function fontPx(page, sel) { return page.evaluate(s => { const e = document.querySelector(s); return e ? parseFloat(getComputedStyle(e).fontSize) : 0; }, sel); }
async function barLabels(page) { return page.evaluate(() => [...document.querySelectorAll('#wpActBar:not([hidden]) button')].map(b => b.textContent.trim())); }
async function tapBar(page, label, fallback) {
  const btn = page.locator('#wpActBar:not([hidden]) button', { hasText: label }).first();
  if (await btn.count()) await btn.tap();
  else if (fallback) await page.evaluate(fallback);   // 改版前的页面没有操作条：直接调原来的函数，好让后面的检查接着跑
  await page.waitForTimeout(900);
}
// 整屏的窗口：四条边都在屏幕里
async function onScreen(page, sel) {
  const b = await box(page, sel);
  const w = await vw(page), h = await vh(page);
  return { ok: !!b && b.left >= 0 && b.top >= 0 && b.right <= w + 0.5 && b.bottom <= h + 0.5, b };
}
const edges = b => b ? [b.left, b.top, b.right, b.bottom].map(Math.round).join(',') : '无';
// 两个元素在同一行（两列排）
async function sideBySide(page, sel) {
  return page.evaluate(s => {
    const els = [...document.querySelectorAll(s)].filter(e => e.offsetParent);
    if (els.length < 2) return false;
    const a = els[0].getBoundingClientRect(), b = els[1].getBoundingClientRect();
    return Math.abs(a.top - b.top) < 2 && b.left > a.right && a.width < innerWidth * 0.55;
  }, sel);
}
async function noOverflow(page, where) { ok((await overflowX(page)) <= 0, `${where}：没有横向溢出`); }
async function minH(page, sel, h, label) {
  const b = await box(page, sel);
  ok(!!b && b.height >= h - 0.5, `${label} 高度 ≥ ${h}px（实际 ${b ? Math.round(b.height) : '无'}）`);
}
// 键盘弹起：原句和输入框都在导航条和底部操作条之间，提交按钮也在屏幕里
async function keyboardCheck(page, ta, cnSel, label) {
  const { width } = page.viewportSize();
  await page.setViewportSize({ width, height: KB_H });
  await page.waitForTimeout(300);
  await page.tap(ta);
  await page.waitForTimeout(900);
  const nav = await navBottom(page), bar = await barTop(page);
  const cn = await box(page, cnSel), t = await box(page, ta);
  const sub = await box(page, '#wpActBar .is-primary');
  ok(!!cn && cn.top >= nav - 1 && cn.bottom <= bar + 1, `${label} 键盘弹起时原句整句可见（${cn && Math.round(cn.top)}–${cn && Math.round(cn.bottom)}，可见区 ${Math.round(nav)}–${Math.round(bar)}）`);
  ok(!!t && t.top >= nav - 1 && t.bottom <= bar + 1, `${label} 键盘弹起时输入框可见（${t && Math.round(t.top)}–${t && Math.round(t.bottom)}）`);
  ok(!!sub && sub.bottom <= KB_H && sub.height >= 44, `${label} 键盘弹起时「提交批改」不用滚就点得到`);
  await shot(page, `${label}-keyboard`);
  await page.setViewportSize({ width, height: ENGINE === 'webkit' ? 844 : 780 });
  await page.waitForTimeout(300);
}
// 提交后：分数条在导航条和操作条之间，操作条换成「下一句」
async function resultCheck(page, stripSel, label) {
  await page.waitForTimeout(600);
  const nav = await navBottom(page), bar = await barTop(page);
  const s = await box(page, stripSel);
  ok(!!s && s.top >= nav - 1 && s.bottom <= bar + 1, `${label} 出分后分数条就在眼前（${s && Math.round(s.top)}–${s && Math.round(s.bottom)}，可见区 ${Math.round(nav)}–${Math.round(bar)}）`);
  const labels = await barLabels(page);
  ok(labels.some(l => /下一句/.test(l)), `${label} 操作条上有「下一句」（${labels.join(' / ')}）`);
  await shot(page, `${label}-result`);
  // 滚到底：最后一块不被操作条盖住
  await page.evaluate(() => window.scrollTo(0, document.scrollingElement.scrollHeight));
  await page.waitForTimeout(300);
  const lastBottom = await page.evaluate(v => {
    const root = document.getElementById(v);
    const els = [...root.querySelectorAll('.fu-card, .feedback-card, .tpl-fb, .hist-panel')].filter(e => e.offsetParent);
    return els.length ? Math.max(...els.map(e => e.getBoundingClientRect().bottom)) : null;
  }, await view(page));
  ok(lastBottom !== null && lastBottom <= (await barTop(page)) + 1, `${label} 滚到底最后一块不被操作条盖住（底边 ${lastBottom && Math.round(lastBottom)}，操作条 ${Math.round(await barTop(page))}）`);
}

async function home(page) {
  await step('首页', async () => {
    await noOverflow(page, '首页');
    ok(!(await box(page, '.home-head > .nav-btn')), '首页「返回主站」在手机上隐藏（导航条已经能回主站）');
    ok(!(await box(page, '.review-fab')) && !(await box(page, '.np-fab')) && !(await box(page, '.ai-float-btn')), '右下角三个浮动按钮在手机上不显示');
    ok(await sideBySide(page, '.entry-card'), '入口卡两张一行');
    await minH(page, '.home-tool', 44, '工具行');
    await shot(page, 'home');
  });
  await step('首页打开 AI 助手 / 速记', async () => {
    await page.locator('.home-tool', { hasText: 'AI 写作助手' }).tap();
    await page.waitForTimeout(800);
    const ai = await onScreen(page, '#aiChatWindow');
    ok(ai.ok, `AI 写作助手没有跑出屏幕（${edges(ai.b)}）`);
    const inp = await box(page, '#aiChatInput');
    ok(!!inp && inp.bottom <= (await vh(page)) && inp.top >= 0, 'AI 输入框在屏幕里');
    await page.evaluate(() => closeAIChat());
    await page.waitForTimeout(700);
    await page.locator('.home-tool', { hasText: '练习速记' }).tap();
    await page.waitForTimeout(800);
    const np = await onScreen(page, '#npWindow');
    ok(np.ok, `练习速记没有跑出屏幕（${edges(np.b)}）`);
    await page.evaluate(() => Notepad.close());
    await page.waitForTimeout(700);
    ok(!(await page.evaluate(() => state.aiChat.open || Notepad.open)), '关掉后两个窗口都收起');
  });
}

async function bigChain(page) {
  await step('思维链目录', async () => {
    await page.tap('text=写作思维链');
    await page.waitForSelector('#subList .sub-card');
    await page.waitForTimeout(600);
    await noOverflow(page, '思维链目录');
    ok(await sideBySide(page, '#subList .sub-card'), '子类卡两张一行');
    await minH(page, '#catGrid .cat-item', 44, '话题胶囊');
    await minH(page, '#subList .mode-btn', 40, '学习 / 实战按钮');
    await shot(page, 'directory');
    // 话题条吸顶（假数据子类少，页面撑高一点才滚得动）
    await page.evaluate(() => { document.getElementById('subList').style.paddingBottom = '1500px'; window.scrollTo(0, 260); });
    await page.waitForTimeout(300);
    const rail = await box(page, '#directoryView .dir-rail');
    ok(!!rail && Math.abs(rail.top - (await navBottom(page))) <= 2, `话题条往下滚时吸在导航条下面（${rail && Math.round(rail.top)}）`);
    await page.evaluate(() => { document.getElementById('subList').style.paddingBottom = ''; window.scrollTo(0, 0); });
    // ⋯ 工具
    await page.tap('#directoryView .wp-head-btn[aria-label="工具"]');
    await page.waitForTimeout(400);
    const rows = await page.evaluate(() => [...document.querySelectorAll('.wp-sheet-row b')].map(b => b.textContent));
    ok(await sheetOpen(page) && ['复习中心', '练习速记', 'AI 写作助手'].every(t => rows.includes(t)), `⋯ 工具弹层里有复习中心 / 练习速记 / AI 写作助手（${rows.join('、')}）`);
    await minH(page, '.wp-sheet-row', 44, '弹层里的一行');
    await shot(page, 'tools-sheet');
    await back(page);
    ok(!(await sheetOpen(page)) && (await view(page)) === 'directoryView', '返回手势先关弹层，人还在目录页');
  });

  await step('思维链学习页', async () => {
    await page.locator('#subList .mode-btn.learn').first().tap();
    await page.waitForSelector('#exampleList .ex-sent');
    await page.waitForTimeout(600);
    await noOverflow(page, '学习页');
    const kw = await box(page, '.learn-top > .card:first-child'), ch = await box(page, '.learn-top > .card:last-child');
    ok(!!kw && !!ch && ch.top >= kw.bottom, '关键词和逻辑链上下排，不再挤成两栏');
    const en = await box(page, '#exampleList .ex-card.is-open .ex-sent .sentence-en');
    const w = await vw(page);
    ok(!!en && en.width >= w * 0.7, `例句英文有整行宽（${en && Math.round(en.width)} / ${w}）`);
    ok(await page.evaluate(() => { const c = document.querySelector('.chain-cn'); return !!c && c.getBoundingClientRect().width > 150; }), '逻辑链文字不再一字一行');
    await shot(page, 'learn');
    const more = '#exampleList .ex-card.is-open .wp-more';
    await minH(page, more, 40, '每句右上角的 ⋯');
    await page.locator(more).first().tap();
    await page.waitForTimeout(400);
    const rows = await page.evaluate(() => [...document.querySelectorAll('.wp-sheet-row b')].map(b => b.textContent));
    ok(['复制英文', '问 AI', '就练这句'].every(t => rows.includes(t)), `句子的 ⋯ 里有复制 / 问 AI / 就练这句（${rows.join('、')}）`);
    await shot(page, 'sentence-sheet');
    const en0 = await page.evaluate(() => document.querySelector('#exampleList .ex-card.is-open .sentence-en').textContent.trim());
    await page.locator('.wp-sheet-row', { hasText: '问 AI' }).tap();
    await page.waitForTimeout(800);
    const win = await box(page, '#aiChatWindow');
    const inp = await box(page, '#aiChatInput');
    const h = await vh(page);
    ok(!!win && win.left >= 0 && win.right <= w + 0.5 && win.top >= 0 && win.bottom <= h + 0.5, `AI 写作助手整屏打开，没有跑出屏幕（${win && [win.left, win.top, win.right, win.bottom].map(Math.round).join(',')}）`);
    ok(!!inp && inp.bottom <= h && inp.top >= 0, 'AI 输入框在屏幕里');
    ok((await fontPx(page, '#aiChatInput')) >= 16, 'AI 输入框字号 ≥ 16px');
    const chip = await page.evaluate(() => (document.querySelector('.ai-chat-context-chip') || {}).textContent || '');
    ok(chip.length > 10 && en0.startsWith(chip.replace(/\.\.\.|×/g, '').trim().slice(0, 20)), `「问 AI」把这句带进了 AI 助手（${chip.slice(0, 30)}…）`);
    await page.fill('#aiChatInput', '这句的主干是什么？');
    await page.tap('#aiChatSendBtn');
    await page.waitForTimeout(800);
    ok((await page.locator('.ai-chat-msg.assistant').count()) >= 1, 'AI 回复显示出来');
    await shot(page, 'ai-chat');
    await back(page);
    ok(!(await page.evaluate(() => state.aiChat.open)) && (await view(page)) === 'learningView', '返回手势关掉 AI 助手，人还在学习页');
  });

  await step('荧光笔（长按选词）', async () => {
    await page.waitForTimeout(500);
    await page.evaluate(() => {
      const el = document.querySelector('#exampleList .ex-card.is-open .sentence-en');
      el.scrollIntoView({ block: 'center' });
      const tn = el.firstChild;
      const r = document.createRange(); r.setStart(tn, 0); r.setEnd(tn, 4);
      const s = getSelection(); s.removeAllRanges(); s.addRange(r);
    });
    await page.waitForTimeout(800);
    const tb = await box(page, '.wp-hl-toolbar.show');
    ok(!!tb && tb.bottom <= (await barTop(page)) && tb.height >= 44, `选中文字后「高亮」出现在屏幕下方、操作条上面（${tb && Math.round(tb.top)}）`);
    await shot(page, 'highlight-toolbar');
    await page.tap('.wp-hl-toolbar button');
    await page.waitForTimeout(800);
    ok((await page.locator('#exampleList mark.wp-hl').count()) >= 1, '点「高亮」后这个词被标上');
    await page.locator('#exampleList mark.wp-hl').first().tap();
    await page.waitForTimeout(500);
    ok(/取消高亮/.test(await page.evaluate(() => (document.querySelector('.wp-hl-toolbar.show') || {}).textContent || '')), '点已有的高亮出现「取消高亮」');
    await page.tap('.wp-hl-toolbar button');
    await page.waitForTimeout(800);
    ok((await page.locator('#exampleList mark.wp-hl').count()) === 0, '取消高亮后标记去掉');
  });

  await step('思维链实战', async () => {
    await page.evaluate(() => window.scrollTo(0, 0));
    const labels = await barLabels(page);
    ok(labels.some(l => /去实战/.test(l)), `学习页底部有「去实战」（${labels.join(' / ')}）`);
    await tapBar(page, '去实战', () => gotoPractice());
    ok((await view(page)) === 'practiceView', '进实战页');
    await noOverflow(page, '实战页');
    await minH(page, '#practiceView .wp-head-btn[aria-label="练习速记"]', 44, '页头速记按钮');
    await minH(page, '#practiceView .wp-head-btn[aria-label="AI 写作助手"]', 44, '页头 AI 按钮');
    await minH(page, '#practiceView .wp-prow-main', 44, '进度行');
    await minH(page, '#practiceView .seg-btn', 40, '学习 / 实战切换');
    ok(!(await box(page, '#sentenceList')) && !(await box(page, '#pracQBox')), '句子队列和题干收进弹层，不占正文');
    const sub = await box(page, '#wpActBar .is-primary');
    ok(!!sub && sub.height >= 44 && sub.bottom <= (await vh(page)), '「提交批改」在屏幕底部，够大');
    const ta = await box(page, '#transInput');
    ok(!!ta && ta.bottom <= (await barTop(page)), `一进实战页输入框就在屏幕里（底边 ${ta && Math.round(ta.bottom)}）`);
    ok((await fontPx(page, '#transInput')) >= 16, '作答框字号 ≥ 16px');
    await shot(page, 'practice');
    // 句子弹层
    const before = await page.evaluate(() => state.activeSentIdx);
    await page.tap('#practiceView .wp-prow-main');
    await page.waitForTimeout(400);
    ok((await page.locator('.wp-sheet-list .sent-item').count()) >= 2, '进度行点开是这道例题的句子列表');
    await shot(page, 'practice-sentences');
    const target = before === 1 ? 2 : 1;
    await page.locator('.wp-sheet-list .sent-item').nth(target).tap();
    await page.waitForTimeout(600);
    ok(!(await sheetOpen(page)) && (await page.evaluate(() => state.activeSentIdx)) === target, '在弹层里选一句就跳过去，弹层收起');
    const prow = await page.evaluate(() => document.querySelector('#practiceView .wp-prow-txt').textContent);
    ok(prow.includes(`第 ${target + 1}/`), `进度行跟着变（${prow}）`);
    // 题干弹层 + 返回
    await page.tap('#practiceView .wp-prow .wp-chip');
    await page.waitForTimeout(400);
    ok(await sheetOpen(page) && (await page.evaluate(() => document.querySelector('.wp-sheet-q').textContent.length)) > 20, '「题干」弹层里是完整题目');
    await back(page);
    ok(!(await sheetOpen(page)) && (await view(page)) === 'practiceView', '返回手势关题干弹层，人还在实战页');
    await keyboardCheck(page, '#transInput', '#practiceView .task-cn', 'big');
    await page.fill('#transInput', 'Technology have changed the way people communicate, which is very important for a lot of families.');
    await page.locator('#wpActBar .is-primary').tap();
    await page.waitForSelector('#practiceView .feedback-card', { timeout: 5000 });
    await resultCheck(page, '#practiceView .fb-grid .score-ring', 'big');
    ok((await fontPx(page, '#practiceView .practice-followup textarea')) >= 16, '追问输入框字号 ≥ 16px');
    await minH(page, '#practiceView .followup-send', 44, '追问「发送」');
    await page.fill('#practiceView .practice-followup textarea', '为什么用现在完成时？');
    await page.tap('#practiceView .followup-send');
    await page.waitForTimeout(700);
    ok((await page.locator('#practiceView .fu-item').count()) >= 1, '追问有回复');
    const cur = await page.evaluate(() => state.activeSentIdx);
    await tapBar(page, '下一句', () => advanceNext());
    ok((await page.evaluate(() => state.activeSentIdx)) === cur + 1, '「下一句」换到下一句');
    const card = await box(page, '#practiceView .task-card');
    ok(!!card && card.top >= (await navBottom(page)) - 1 && card.top < (await vh(page)) * 0.6, `换句后句子卡回到屏幕上方（${card && Math.round(card.top)}）`);
    // 页头的速记
    await page.tap('#practiceView .wp-head-btn[aria-label="练习速记"]');
    await page.waitForTimeout(700);
    const np = await box(page, '#npWindow');
    const w = await vw(page), h = await vh(page);
    ok(!!np && np.left >= 0 && np.right <= w + 0.5 && np.bottom <= h + 0.5 && np.top >= 0, `练习速记整屏打开，没有跑出屏幕（${np && [np.left, np.top, np.right, np.bottom].map(Math.round).join(',')}）`);
    ok((await fontPx(page, '#npEditor')) >= 16, '速记编辑区字号 ≥ 16px');
    await minH(page, '#npWindow .np-rename', 44, '速记「重命名」');
    await shot(page, 'notepad');
    await back(page);
    ok(!(await page.evaluate(() => Notepad.open)) && (await view(page)) === 'practiceView', '返回手势关速记，人还在实战页');
  });
}

async function smallFangxie(page) {
  await step('仿写列表 / 学习', async () => {
    await page.evaluate(() => backToEntry());
    await page.waitForTimeout(500);
    await page.tap('text=小作文仿写');
    await page.waitForSelector('#smallExampleList .sub-card');
    await page.waitForTimeout(500);
    await noOverflow(page, '仿写题目列表');
    ok(await sideBySide(page, '#smallExampleList .sub-card'), '仿写题目卡两张一行');
    await page.locator('#smallExampleList .mode-btn.learn').first().tap();
    await page.waitForSelector('#smallLearnContent .sl-sent');
    await page.waitForTimeout(600);
    await noOverflow(page, '仿写学习页');
    const en = await box(page, '#smallLearnContent .sl-sent .sentence-en');
    const w = await vw(page);
    ok(!!en && en.width >= w * 0.7, `范文拆解句子有整行宽（${en && Math.round(en.width)} / ${w}）`);
    ok(!(await box(page, '#smallLearnImageZone .fig-swap')), '「换一张」不再压在题图上');
    await shot(page, 'small-learn');
    await page.tap('#smallLearnImageZone .fig-img');
    await page.waitForTimeout(500);
    await minH(page, '.wp-lb-more', 44, '大图右上角的 ⋯');
    await page.tap('.wp-lb-more');
    await page.waitForTimeout(400);
    ok(await page.locator('.wp-sheet-row', { hasText: '换一张题图' }).count() === 1, '大图的 ⋯ 里有「换一张题图」');
    await shot(page, 'lightbox-menu');
    await page.tap('.wp-sheet-x');
    await page.waitForTimeout(400);
    await back(page);
    ok((await page.evaluate(() => document.getElementById('imageLightbox').style.display)) === 'none' && (await view(page)) === 'smallLearnView', '返回手势关大图，人还在学习页');
  });

  await step('仿写实战', async () => {
    const labels = await barLabels(page);
    ok(labels.some(l => /接着练/.test(l)), `仿写学习页底部有「接着练」（${labels.join(' / ')}）`);
    await tapBar(page, '接着练', () => gotoSmallPractice());
    ok((await view(page)) === 'smallPracticeView', '进仿写实战');
    await noOverflow(page, '仿写实战');
    ok(!!(await box(page, '#smallPracticeView .wp-fig-thumb img')), '任务卡上方有题图缩略条');
    ok(!(await box(page, '#smallPracticeView .sp-side')), '侧栏（题图 / 题干 / 句子）收进弹层');
    await page.tap('#smallPracticeView .wp-prow-main');
    await page.waitForTimeout(400);
    ok((await page.locator('.wp-sheet-list .sp-done-item').count()) >= 1 && (await page.locator('.wp-sheet-pills .tpl-step').count()) >= 2, '句子弹层里有段落和本段句子');
    await page.tap('.wp-sheet-x');
    await page.waitForTimeout(300);
    await page.tap('#smallPracticeView .wp-prow .wp-chip');
    await page.waitForTimeout(400);
    ok(!!(await box(page, '.wp-sheet-fig img')), '「题干」弹层里有题图');
    await page.tap('.wp-sheet-x');
    await page.waitForTimeout(300);
    await shot(page, 'small-practice');
    await keyboardCheck(page, '#smallTransInput', '#smallPracticeView .task-cn', 'small');
    await page.fill('#smallTransInput', 'Overall, shared bike use rose in all three cities over the period.');
    await page.locator('#wpActBar .is-primary').tap();
    await page.waitForSelector('#smallPracticeView .feedback-card', { timeout: 5000 });
    await resultCheck(page, '#smallPracticeView .sp-fb-head', 'small');
  });
}

async function templates(page) {
  await step('模板大作文', async () => {
    await page.evaluate(() => backToEntry());
    await page.waitForTimeout(500);
    await page.locator('.entry-column.is-big .entry-card').nth(1).tap();
    await page.waitForSelector('#tplBigTypeGrid .tpl-type-card');
    await page.waitForTimeout(500);
    await noOverflow(page, '模板题型');
    ok(await sideBySide(page, '#tplBigTypeGrid .tpl-type-card'), '题型卡两张一行');
    const ref = await box(page, '#tplBigRefList'), grid = await box(page, '#tplBigTypeGrid');
    ok(!!ref && !!grid && ref.top < grid.top, '总结构 / 句型库排在题型卡上面');
    await page.locator('.tpl-type-card').first().tap();
    await page.waitForSelector('#tplBigSamplesBody .tbs-card');
    await page.waitForTimeout(500);
    await noOverflow(page, '范文列表');
    ok(await sideBySide(page, '#tplBigSamplesBody .tbs-card'), '范文卡两张一行');
    await step('「打开总结构」打得开', async () => {
      // 线上语料的总结构只挂在大作文顶层；以前题型上找不到，按钮退成「回题型列表」、侧栏链接弹「没有配参考资料」
      let alerted = '';
      const onDialog = d => { alerted = d.message(); };
      page.on('dialog', onDialog);
      const btn = page.locator('#tplBigSamplesBody .tbs-foot .tbs-btn');
      ok((await btn.textContent()).trim() === '打开总结构', '范文页底部是「打开总结构」');
      await btn.tap();
      await page.waitForFunction(() => /总结构/.test(document.getElementById('tplRefTitle').textContent), null, { timeout: 4000 }).catch(() => {});
      ok((await view(page)) === 'tplRefView' && /总结构/.test(await page.textContent('#tplRefTitle')), '打开的是总结构');
      ok(!alerted, '没有弹「没有配参考资料」');
      await back(page);
      ok((await view(page)) === 'tplBigSamplesView', '返回回到范文列表');
      page.off('dialog', onDialog);
    });
    await step('「只看骨架」收在 ⋯ 里', async () => {
      await page.tap('#tplBigSamplesView .wp-head-btn[aria-label="工具"]');
      await page.waitForTimeout(400);
      ok(await page.locator('.wp-sheet-row', { hasText: '只看骨架' }).count() === 1, '「只看骨架」收在 ⋯ 里');
      await page.locator('.wp-sheet-row', { hasText: '只看骨架' }).tap();
    });
    await page.waitForTimeout(900);
    if ((await view(page)) !== 'tplBigLearnView') await page.evaluate(() => Tpl.openSkeletonOnly());
    await page.waitForTimeout(600);
    ok((await view(page)) === 'tplBigLearnView', '从 ⋯ 打开骨架对照');
    await noOverflow(page, '模板学习页');
    await shot(page, 'tplbig-learn');
    await step('模板句子的 ⋯', async () => {
      await page.locator('#tplBigLearnBody .wp-more').first().tap();
      await page.waitForTimeout(400);
      ok(await page.locator('.wp-sheet-row', { hasText: '问 AI' }).count() === 1, '模板句子的 ⋯ 里有「问 AI」');
      await page.tap('.wp-sheet-x');
      await page.waitForTimeout(300);
    });
    await tapBar(page, '拿这道题练', () => Tpl.startBigPractice());
    ok((await view(page)) === 'tplBigPracticeView', '「拿这道题练」进实战');
    await noOverflow(page, '模板实战');
    const labels = await barLabels(page);
    ok(labels.length === 3 && /偷看/.test(labels[0]) && /提交批改/.test(labels[2]), `模板实战操作条：偷看 / 跳过 / 提交批改（${labels.join(' / ')}）`);
    await keyboardCheck(page, '#tplAnswer', '#tplBigPracticeView .task-cn', 'tplbig');
    await page.fill('#tplAnswer', 'It is often argued that phones should be banned in libraries.');
    await page.locator('#wpActBar .is-primary').tap();
    await page.waitForSelector('#tplBigPracticeView .tpl-fb', { timeout: 5000 });
    await resultCheck(page, '#tplBigPracticeView .tpl-fb-top', 'tplbig');
    const l2 = await barLabels(page);
    ok(l2.some(l => /再试一次/.test(l)), `出分后操作条上有「再试一次」（${l2.join(' / ')}）`);
  });

  await step('模板小作文', async () => {
    await page.evaluate(() => backToEntry());
    await page.waitForTimeout(500);
    await page.locator('.entry-column.is-small .entry-card').nth(1).tap();
    await page.waitForSelector('#tplSmallSecGrid .tpl-type-card');
    await page.waitForTimeout(600);
    await noOverflow(page, '模板小作文段落');
    ok(await sideBySide(page, '#tplSmallSecGrid .tpl-type-card'), '段落卡两张一行');
    await page.locator('#tplSmallSecGrid .tpl-type-card').nth(2).tap();
    await page.waitForSelector('#tplSmallExBody .tbs-card');
    await page.waitForTimeout(500);
    await noOverflow(page, '模板小作文例题');
    ok(await sideBySide(page, '#tplSmallExBody .tbs-card'), '例题卡两张一行');
    await page.locator('#tplSmallExBody .tbs-card .tbs-btn').first().tap();
    await page.waitForSelector('#tplSmallLearnBody .tsl-item');
    await page.waitForTimeout(600);
    await noOverflow(page, '句型库');
    await minH(page, '#tplSmallLearnBody .tsl-chip', 40, '筛句型胶囊');
    await shot(page, 'tplsmall-learn');
    await tapBar(page, '去实战', () => document.querySelector('.tsl-cta-btn').click());
    ok((await view(page)) === 'tplSmallPracticeView', '句型库「去实战」');
    await noOverflow(page, '模板小作文实战');
    ok(!!(await box(page, '#tplSmallPracticeView .wp-fig-thumb img')), '模板小作文任务卡上有题图缩略条');
    await keyboardCheck(page, '#tplAnswer', '#tplSmallPracticeView .task-cn', 'tplsmall');
    await page.fill('#tplAnswer', 'Northport began with about 12,000 trips a day in 2016.');
    await page.locator('#wpActBar .is-primary').tap();
    await page.waitForSelector('#tplSmallPracticeView .tpl-fb', { timeout: 5000 });
    await resultCheck(page, '#tplSmallPracticeView .tpl-fb-top', 'tplsmall');
  });
}

async function review(page) {
  await step('复习中心', async () => {
    await step('从 ⋯ 打开复习中心', async () => {
      await page.tap('#tplSmallPracticeView .wp-head-btn[aria-label="工具"]');
      await page.waitForTimeout(400);
      await page.locator('.wp-sheet-row', { hasText: '复习中心' }).tap();
    });
    await page.waitForTimeout(1200);
    if (!(await page.evaluate(() => state.drawerOpen))) await page.evaluate(() => toggleReview());
    await page.waitForTimeout(1200);
    await noOverflow(page, '复习中心');
    await minH(page, '.review-overlay-tab', 40, '复习中心页签');
    await minH(page, '#wpSortBtn', 44, '排序按钮');
    await page.tap('.review-overlay-tab[data-tab="big"]');
    await page.waitForTimeout(800);
    await page.locator('#reviewBigContent .rv-group-head').first().tap();
    await page.locator('#reviewBigContent .rv-item-head').first().tap();
    await page.waitForTimeout(300);
    ok(!(await box(page, '#reviewBigContent .rv-item.is-open .rv-del')), '30px 的垃圾桶不再挨着「收起详情」');
    await minH(page, '#reviewBigContent .rv-item.is-open .rv-del-m', 44, '「删除这条」');
    await minH(page, '#reviewBigContent .rv-item.is-open .rv-again', 44, '「再练这一句」');
    await shot(page, 'review');
    await page.tap('#wpSortBtn');
    await page.waitForTimeout(400);
    await page.locator('.wp-sheet-row', { hasText: '最近练的' }).tap();
    await page.waitForTimeout(600);
    ok((await page.evaluate(() => state.reviewSort)) === 'recent' && /最近练的/.test(await page.evaluate(() => document.getElementById('wpSortBtn').textContent)), '排序弹层改成「最近练的」，按钮跟着变');
    await back(page);
    ok(!(await page.evaluate(() => state.drawerOpen)) && (await view(page)) === 'tplSmallPracticeView', '返回手势关复习中心，人还在原来那页');
  });
}

async function darkPass(page) {
  await step('暗色', async () => {
    await noOverflow(page, '暗色首页');
    await shot(page, 'dark-home');
    await page.tap('text=写作思维链');
    await page.waitForSelector('#subList .sub-card');
    await page.locator('#subList .mode-btn.practice').first().tap();
    await page.waitForSelector('#transInput');
    await page.waitForTimeout(500);
    await noOverflow(page, '暗色实战');
    await page.fill('#transInput', 'Older people who live with their children are rarely alone.');
    await page.locator('#wpActBar .is-primary').tap();
    await page.waitForSelector('#practiceView .feedback-card', { timeout: 5000 });
    await page.waitForTimeout(600);
    await noOverflow(page, '暗色批改结果');
    const c = await page.evaluate(() => {
      const b = document.querySelector('#wpActBar .is-primary');
      const cs = getComputedStyle(b);
      return [cs.color, cs.backgroundColor];
    });
    ok(c[0] !== c[1], `暗色下主按钮文字和底色不同（${c.join(' on ')}）`);
    await shot(page, 'dark-result');
  });
}

run(async browser => {
  {
    const { ctx, page } = await open(browser);
    await home(page);
    await bigChain(page);
    await smallFangxie(page);
    await templates(page);
    await review(page);
    await ctx.close();
  }
  {
    const { ctx, page } = await open(browser, { dark: true });
    await darkPass(page);
    await ctx.close();
  }
});

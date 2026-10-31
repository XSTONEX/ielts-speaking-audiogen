// 文章精读（/intensive、/intensive/new）浏览器端到端测试，Chromium + WebKit 各跑一遍。
// 用法见 README.md：node run.js [select|touch|import|misc ...] [chromium|webkit ...]
const lib = require('./lib');

const SUITE_FILES = {
  select: './suite_select',   // 桌面：鼠标划词 → 高亮 / 释义浮层，各种选区端点
  touch: './suite_touch',     // 手机：长按选词、点高亮看释义、词汇底部面板、译文开关
  import: './suite_import',   // /intensive/new 导入九分学长 JSON → 原文 + 题目 + 作答 + 做题划线
  misc: './suite_misc',       // 删除确认、图片条和大图、改标题、改分类、朗读音频条
};

(async () => {
  const cfg = lib.loadConfig(process.argv.slice(2));
  try {
    await lib.preflight(cfg);
  } catch (e) {
    console.error('没法开始：' + e.message);
    process.exit(2);
  }
  console.log(`服务器 ${cfg.baseUrl}，截图放在 ${cfg.out}`);
  const totals = {};
  for (const engine of cfg.engines) {
    totals[engine] = { pass: 0, fail: 0 };
    const browser = await lib.pw[engine].launch();
    try {
      for (const suite of cfg.suites) {
        const t = new lib.Checks(engine, suite);
        await lib.cleanup(cfg);
        const started = Date.now();
        try {
          await require(SUITE_FILES[suite])({ cfg, browser, engine, t, lib });
        } catch (e) {
          t.ok(false, `套件中途出错：${e.message.split('\n').slice(0, 6).join(' | ')}`);
        }
        await lib.cleanup(cfg).catch(e => t.ok(false, `清理失败：${e.message.split('\n')[0]}`));
        totals[engine].pass += t.pass;
        totals[engine].fail += t.fail;
        console.log(`${engine.padEnd(8)} ${suite.padEnd(6)} 通过 ${t.pass}，失败 ${t.fail}（${((Date.now() - started) / 1000).toFixed(1)}s）`);
        t.fails.forEach(f => console.log('    FAIL ' + f));
      }
    } finally {
      await browser.close();
    }
  }
  console.log('\n== 合计');
  let failed = 0;
  for (const [engine, s] of Object.entries(totals)) {
    console.log(`${engine.padEnd(8)} 通过 ${s.pass}，失败 ${s.fail}`);
    failed += s.fail;
  }
  process.exit(failed ? 1 : 0);
})().catch(e => {
  console.error('ERR', e.stack || e.message);
  process.exit(1);
});

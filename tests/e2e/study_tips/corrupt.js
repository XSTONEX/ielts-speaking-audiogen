// 数据文件写坏时：页面要显示「没加载出来」和重新加载，不能显示成空列表让人往里加（加了会把坏文件盖掉）。
// 用法：node corrupt.js chromium|webkit（环境变量见 README.md）。全部通过退出码为 0。
const fs = require('fs');
const path = require('path');
const { pw, BASE, OUT, ENGINE, token, checkCdn, resetFixtures, dataFile } = require('./common');

(async () => {
  await checkCdn();
  resetFixtures();
  const file = dataFile('listening_synonyms');
  const good = fs.readFileSync(file, 'utf8');
  const broken = good.slice(0, 120);   // 写到一半的文件
  fs.writeFileSync(file, broken);
  const browser = await pw[ENGINE].launch();
  const ok = [];
  try {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 860 } });
    await ctx.addInitScript(([t]) => {
      localStorage.setItem('authToken', t);
      localStorage.setItem('ui-theme', 'light');
    }, [token()]);
    const page = await ctx.newPage();
    await page.goto(BASE + '/study_techniques#listening/synonyms');
    await page.waitForSelector('#listBody .ui-empty__title');
    ok.push(['error state shown', (await page.textContent('#listBody')).includes('没加载出来')]);
    ok.push(['new/import disabled', await page.isDisabled('[data-action="group-new"]') && await page.isDisabled('[data-action="import-open"]')]);
    ok.push(['file untouched', fs.readFileSync(file, 'utf8') === broken]);
    fs.mkdirSync(OUT, { recursive: true });
    await page.screenshot({ path: path.join(OUT, `corrupt-${ENGINE}.png`) });
    fs.writeFileSync(file, good);        // 修好后点重新加载
    await page.click('[data-action="retry"]');
    await page.waitForSelector('#listBody .st-group');
    ok.push(['retry loads after fix', (await page.$$('#listBody .st-group')).length === 5]);
    ok.push(['other subjects unaffected', (await page.textContent('#rail a[href="#reading/synonyms"] .ui-rail__count')) === '22']);
  } finally {
    fs.writeFileSync(file, good);
    await browser.close();
  }
  ok.forEach(([name, pass]) => console.log((pass ? 'PASS ' : 'FAIL ') + name));
  console.log(`\n${ENGINE}: ${ok.filter(x => x[1]).length}/${ok.length} passed`);
  process.exit(ok.every(x => x[1]) ? 0 : 1);
})().catch(e => { console.error('CRASH', e); process.exit(2); });

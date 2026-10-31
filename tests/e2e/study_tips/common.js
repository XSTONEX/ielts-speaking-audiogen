// 三个浏览器测试脚本共用的配置和小工具。所有路径、地址都从环境变量来，见 README.md。
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('child_process');

const pw = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const SANDBOX = process.env.STUDY_TIPS_SANDBOX;
if (!SANDBOX) {
  console.error('先设置 STUDY_TIPS_SANDBOX=沙盒目录（怎么建见 README.md）');
  process.exit(2);
}
// 脚本会重置、增删沙盒里的数据：绝不能指向真实仓库
if (fs.existsSync(path.join(SANDBOX, '.git'))) {
  console.error(`${SANDBOX} 里有 .git，像是真实仓库而不是沙盒，不跑`);
  process.exit(2);
}
const BASE = (process.env.STUDY_TIPS_BASE_URL || 'http://localhost:5071').replace(/\/+$/, '');
if (!/^https?:\/\/(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(BASE)) {
  console.error(`STUDY_TIPS_BASE_URL=${BASE} 不是本机地址；这些脚本只对沙盒服务器跑`);
  process.exit(2);
}
const TOKEN_FILE = process.env.STUDY_TIPS_TOKEN_FILE || path.join(SANDBOX, 'e2e_token.txt');
const PYTHON = process.env.PYTHON || 'python3';
const OUT = process.env.STUDY_TIPS_OUT || path.join(os.tmpdir(), 'study_tips_e2e');
const ENGINE = process.argv[2] || 'chromium';
if (!['chromium', 'webkit'].includes(ENGINE)) {
  console.error('用法：node <脚本> chromium|webkit');
  process.exit(2);
}

// 页面在 <head> 里从 jsdelivr 同步加载 marked 和 DOMPurify：连不上时浏览器会一直等，测试只会超时。
// 开跑前先试一下，连不上就直接说明原因退出（退出码 3）。
const CDN_FILES = [
  'https://cdn.jsdelivr.net/npm/marked@5.1.1/marked.min.js',
  'https://cdn.jsdelivr.net/npm/dompurify@3.0.6/dist/purify.min.js'
];
async function checkCdn() {
  for (const url of CDN_FILES) {
    try {
      const res = await fetch(url, { method: 'HEAD', signal: AbortSignal.timeout(10000) });
      if (!res.ok) throw new Error('HTTP ' + res.status);
    } catch (e) {
      console.error(`连不上 ${url}（${e.message}）。页面要从这里加载 Markdown 库，等网络恢复再跑。`);
      process.exit(3);
    }
  }
}

function token() {
  return fs.readFileSync(TOKEN_FILE, 'utf8').trim();
}

// 把沙盒数据恢复成 make_fixtures.py 生成的那一份（每次 id 都是新的）
function resetFixtures() {
  execFileSync(PYTHON, [path.join(__dirname, 'make_fixtures.py'), SANDBOX], { stdio: ['ignore', 'ignore', 'inherit'] });
}

function dataFile(name) {
  return path.join(SANDBOX, 'study_techniques', 'data', name + '.json');
}

function readData(name) {
  return JSON.parse(fs.readFileSync(dataFile(name), 'utf8'));
}

module.exports = { pw, SANDBOX, BASE, OUT, ENGINE, token, checkCdn, resetFixtures, dataFile, readData };

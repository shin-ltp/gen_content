// collect-36kr.mjs - 36kr 深度文章收集器（AI/科技领域）
// 从 /information/AI/ 和 /information/technology/ 收集深度分析文章
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const _require = createRequire('C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
const { chromium } = _require('playwright');
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, delay, atomicWrite } from './collect-utils.mjs';

const OUT = process.env.KR36_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });
const TARGET = parseInt(process.env.KR36_TARGET || '10', 10);
const HEADED = process.argv.includes('--headed');
const REFETCH = process.argv.includes('--refetch');
const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//, '')), '..', '..');
const SESSION_FILE = path.join(PROJECT, 'db', '36kr-session.json');

// 美股/科技/AI 相关关键词过滤
const KEYWORDS = ['AI', '人工智能', '芯片', '半导体', '英伟达', 'NVIDIA', 'OpenAI', '微软',
  'Microsoft', '苹果', 'Apple', '谷歌', 'Google', '亚马逊', 'Amazon', 'Meta', '特斯拉', 'Tesla',
  '美股', '纳斯达克', '标普', '美联储', '降息', '加息', '科技', '大模型', 'GPT', '算力',
  '数据中心', '台积电', 'TSMC', 'AMD', '高通', 'Qualcomm', '博通', '美股研究', '华尔街',
  '投行', '目标价', '评级', '财报', '营收', '白银', '黄金', '原油', '机器人', '具身智能',
  '自动驾驶', '量子计算', '云计算', 'SaaS', '半导体设备', '光刻机', 'ASML', '三星', 'SK海力士',
  '美光', '存储芯片', 'HBM', '先进封装', 'CoWoS', 'Intel', '英特尔'];

function matchesFilter(text) {
  const t = String(text || '').toLowerCase();
  return KEYWORDS.some(kw => t.includes(String(kw).toLowerCase()));
}

async function createBrowser() {
  return await chromium.launch({
    headless: !HEADED,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
  });
}

async function createContext(browser) {
  const ctxOpts = {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    locale: 'zh-CN', viewport: { width: 1920, height: 1080 }
  };
  if (fs.existsSync(SESSION_FILE)) {
    try { ctxOpts.storageState = SESSION_FILE; console.log('[36kr] using saved session'); } catch {}
  }
  const context = await browser.newContext(ctxOpts);
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh'] });
    window.chrome = { runtime: {} };
  });
  return context;
}

async function isCaptchaBlocked(page) {
  try {
    return await page.evaluate(() => {
      return !!document.querySelector('#captcha_container, iframe[src*="bytedance"], iframe[src*="verify"]');
    });
  } catch { return false; }
}

// 从信息流页面收集文章链接
async function collectArticleLinks(browser, url) {
  console.log('[36kr] collecting from ' + url);
  const links = [];
  const context = await createContext(browser);
  const page = await context.newPage();
  try {
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
        await page.waitForTimeout(4000);
        if (await isCaptchaBlocked(page)) {
          process.stderr.write('[36kr] CAPTCHA detected on attempt ' + attempt + '\n');
          if (HEADED) {
            console.log('[36kr] HEADLESS=false - waiting 30s for manual CAPTCHA solve...');
            await page.waitForTimeout(30000);
          } else {
            await page.waitForTimeout(5000);
          }
          if (await isCaptchaBlocked(page)) {
            if (attempt < 3) { await page.waitForTimeout(3000); continue; }
          }
        }
        break;
      } catch (e) {
        process.stderr.write('[36kr] page load attempt ' + attempt + ' failed: ' + e.message.slice(0, 60) + '\n');
        if (attempt < 3) { await page.waitForTimeout(3000); }
      }
    }
    try { await context.storageState({ path: SESSION_FILE }); } catch {}
    
    // 提取文章链接（/p/ 格式）
    const raw = await page.evaluate(() => {
      const results = [];
      const seen = new Set();
      document.querySelectorAll('a').forEach(a => {
        const href = a.href;
        if (!href) return;
        const m = href.match(/\/p\/(\d+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return;
        const title = (a.textContent || '').trim();
        if (title.length > 8) { seen.add(id); results.push({ title: title.slice(0, 200), url: href.split('?')[0] }); }
      });
      return results;
    });
    links.push(...raw);
    console.log('[36kr] found ' + links.length + ' article links');
  } catch (e) { console.error('[36kr] error: ' + e.message); }
  finally { await context.close(); }
  return links;
}

// 提取文章正文
async function fetchArticleBody(page, url) {
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    try { await page.waitForSelector('.article-content, .content', { timeout: 8000 }); } catch {}
    await page.waitForTimeout(1500);
    if (await isCaptchaBlocked(page)) return '';
    return await page.evaluate(() => {
      // 优先使用 .article-content 或 .content
      const sels = ['.article-content', '.content', 'article', '[class*="article"]'];
      for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el) {
          const text = (el.innerText || '').trim();
          if (text.length > 200) return text;
        }
      }
      // fallback: 收集所有段落
      const paras = [...document.querySelectorAll('p')].map(p => p.innerText.trim()).filter(t => t.length > 30);
      if (paras.length > 3) return paras.join('\n\n');
      return '';
    });
  } catch (e) { return ''; }
}

async function run() {
  const seen = loadSeen();
  console.log('[36kr] start (target=' + TARGET + ', mode=articles, headed=' + HEADED + ')');

  const browser = await createBrowser();
  let allLinks = [];
  try {
    // 从两个入口收集文章列表
    const aiLinks = await collectArticleLinks(browser, 'https://36kr.com/information/AI/');
    await delay(3000);
    const techLinks = await collectArticleLinks(browser, 'https://36kr.com/information/technology/');
    allLinks = [...aiLinks, ...techLinks];
  } finally { await browser.close(); }

  if (allLinks.length === 0) {
    // 当日分の素材が既に存在する場合は、反爬による再取得失敗でも全体 FAIL にしない
    const today = new Date().toISOString().slice(0, 10);
    const dayPrefix = 'STK-' + today.replace(/-/g, '') + '-KR';
    let existing = 0;
    try {
      existing = fs.existsSync(OUT)
        ? fs.readdirSync(OUT).filter(f => f.startsWith(dayPrefix) && f.endsWith('.md')).length
        : 0;
    } catch {}
    if (existing > 0) {
      console.log('[36kr] no new links (CAPTCHA or network), 当日分 ' + existing + ' 件は収集済みのため成功扱い');
      process.exit(0);
    }
    console.log('[36kr] no article links found (CAPTCHA or network issue)');
    console.log('[36kr] TIP: run with --headed to solve CAPTCHA manually');
    process.exit(1);
  }

  // 去重
  const urlSeen = new Set();
  const deduped = allLinks.filter(it => {
    const u = it.url;
    if (urlSeen.has(u)) return false;
    urlSeen.add(u);
    return true;
  });

  console.log('[36kr] total: ' + allLinks.length + ' (dedup: ' + deduped.length + ')');

  const today = new Date().toISOString().slice(0, 10);
  let n = 0, dup = 0, filtered = 0;
  let failStreak = 0;
  // 当日既収集分の続番から採番する（再実行で KR001.. を上書きしない）
  const dayPrefix = 'STK-' + today.replace(/-/g, '') + '-KR';
  let seqBase = 0;
  try {
    seqBase = fs.existsSync(OUT)
      ? fs.readdirSync(OUT).filter(f => f.startsWith(dayPrefix) && f.endsWith('.md')).length
      : 0;
  } catch {}
  const bodyBrowser = await createBrowser();
  const bodyContext = await createContext(bodyBrowser);
  const bodyPage = await bodyContext.newPage();

  try {
    for (const it of deduped) {
      if (n >= TARGET) break;
      const rawId = it.url;
      const id = 'kr36:' + String(rawId).replace(/[^a-z0-9]/gi, '').slice(-24);
      if (seenHas(seen, '36kr', id) && !REFETCH) { dup++; continue; }

      // 关键词过滤
      if (!matchesFilter(it.title)) { filtered++; continue; }

      let body = await fetchArticleBody(bodyPage, it.url);
      if (body.length < 200) { await delay(8000); body = await fetchArticleBody(bodyPage, it.url); }
      if (body.length < 200) {
        filtered++; failStreak++;
        console.error('[36kr] 本文取得失敗 (' + failStreak + ' 連続): ' + it.url);
        if (failStreak === 3) { console.error('[36kr] 連続失敗 - 20秒クールダウン'); await delay(20000); }
        else if (failStreak >= 6) { console.error('[36kr] 反爬ブロックの可能性 - 打ち切り'); break; }
        else await delay(3000);
        continue;
      }
      failStreak = 0;

      const meta = {
        id: dayPrefix + String(seqBase + n + 1).padStart(3, '0'),
        category: 'stocks', ticker: '',
        title: it.title.slice(0, 200),
        source: '36kr', source_type: 'media',
        url: it.url,
        relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-36kr', priority: 'TBD',
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };

      const md = frontmatter(meta) + '\n\n## Body\n\n' + body.slice(0, 8000) + '\n';
      atomicWrite(path.join(OUT, meta.id + '.md'), md);
      seenAdd(seen, '36kr', id, { title: it.title.slice(0, 80), body_chars: body.length });
      n++;
      console.log('[' + n + '] ' + it.title.slice(0, 50) + ' (' + body.length + ' chars)');
      // 反爬対策: 記事間 2.5-4秒のランダム間隔
      await delay(2500 + Math.floor(Math.random() * 1500));
    }
  } finally {
    try { await bodyContext.storageState({ path: SESSION_FILE }); } catch {}
    await bodyContext.close();
    await bodyBrowser.close();
  }

  try { saveSeen(seen); } catch (e) { console.error('[36kr] seen 保存失敗: ' + e.message); }
  console.log('\n=== 36kr: new=' + n + ' (dup ' + dup + ' / filtered ' + filtered + ') -> ' + OUT + ' ===');
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

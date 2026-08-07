// collect-36kr.mjs - 36kr collector
// IMPORTANT: 36kr uses ByteDance slide CAPTCHA (rmc.bytedance.com) that blocks headless browsers.
//   - RSS feeds (/feed, /feed-newsflash) are discontinued (return HTML, not XML)
//   - gateway.36kr.com API endpoints all return HTTP 500
//   - DOM extraction works ONLY when session is not challenged (first few visits per IP/day)
// Strategy: Try DOM with persisted storageState (session cookies). If CAPTCHA blocks, graceful degradation.
//   For reliable access: run once with --headed to solve CAPTCHA manually, session persists in db/36kr-session.json
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const _require = createRequire('C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
const { chromium } = _require('playwright');
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter } from './collect-utils.mjs';

const OUT = process.env.KR36_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });
const TARGET = parseInt(process.env.KR36_TARGET || '20', 10);
const HEADED = process.argv.includes('--headed');
const REFETCH = process.argv.includes('--refetch');
const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//, '')), '..', '..');
const SESSION_FILE = path.join(PROJECT, 'db', '36kr-session.json');


const KEYWORDS = ['AI', '人工智能', '芯片', '半导体', '英伟达', 'NVIDIA', 'OpenAI', '微软',
  'Microsoft', '苹果', 'Apple', '谷歌', 'Google', '亚马逊', 'Amazon', 'Meta', '特斯拉', 'Tesla',
  '美股', '纳斯达克', '标普', '美联储', '降息', '加息', '科技', '大模型', 'GPT', '算力',
  '数据中心', '台积电', 'TSMC', 'AMD', '高通', 'Qualcomm', '博通', '美股研究', '华尔街',
  '投行', '目标价', '评级', '财报', '营收', '白银', '黄金', '原油'];

function matchesFilter(text) {
  return KEYWORDS.some(kw => text.includes(kw));
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
  // Load persisted session if available
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

// Check if page is blocked by CAPTCHA
async function isCaptchaBlocked(page) {
  try {
    return await page.evaluate(() => {
      return !!document.querySelector('#captcha_container, iframe[src*="bytedance"], iframe[src*="verify"]');
    });
  } catch { return false; }
}

async function collectNewsflashes(browser) {
  console.log('[36kr] newsflashes DOM extraction (headed=' + HEADED + ')...');
  const items = [];
  const context = await createContext(browser);
  const page = await context.newPage();
  try {
    let loaded = false;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        await page.goto('https://36kr.com/newsflashes', { waitUntil: 'networkidle', timeout: 25000 });
        await page.waitForTimeout(4000);
        // Check for CAPTCHA
        if (await isCaptchaBlocked(page)) {
          process.stderr.write('[36kr] CAPTCHA detected on attempt ' + attempt + '\n');
          if (HEADED) {
            console.log('[36kr] HEADLESS=false - waiting 30s for manual CAPTCHA solve...');
            await page.waitForTimeout(30000);
          } else {
            // wait a bit - sometimes challenge auto-resolves
            await page.waitForTimeout(5000);
          }
          if (await isCaptchaBlocked(page)) {
            if (attempt < 3) { try { await page.waitForTimeout(3000); } catch {} continue; }
          }
        }
        loaded = true;
        break;
      } catch (e) {
        process.stderr.write('[36kr] newsflashes attempt ' + attempt + ' failed: ' + e.message.slice(0, 60) + '\n');
        if (attempt < 3) { try { await page.waitForTimeout(3000); } catch {} }
      }
    }
    // Save session for future runs
    try { await context.storageState({ path: SESSION_FILE }); } catch {}
    if (!loaded) { console.error('[36kr] page load failed after retries'); return items; }
    // Verify content actually loaded (not blank/challenge page)
    const aCount = await page.evaluate(() => document.querySelectorAll('a').length);
    if (aCount < 5) {
      console.error('[36kr] page appears blank/blocked (a tags=' + aCount + ') - likely CAPTCHA');
      return items;
    }
    // scroll to load lazy content
    for (let i = 0; i < 4; i++) {
      try { await page.evaluate(() => window.scrollBy(0, 1200)); } catch {}
      await page.waitForTimeout(800);
    }
    // Extract links: scan ALL <a> tags, filter by numeric newsflash ID
    const raw = await page.evaluate(() => {
      const results = [];
      const seen = new Set();
      document.querySelectorAll('a').forEach(a => {
        const href = a.href;
        if (!href) return;
        const m = href.match(/\/newsflashes\/(\d+)/);
        if (!m) return;
        const id = m[1];
        if (seen.has(id)) return;
        const title = (a.textContent || '').trim();
        if (title.length > 5) { seen.add(id); results.push({ title: title.slice(0, 200), url: href.split('#')[0] }); }
      });
      return results;
    });
    items.push(...raw);
    console.log('[36kr] newsflashes -> ' + items.length + ' items');
  } catch (e) { console.error('[36kr] newsflashes error: ' + e.message); }
  finally { await context.close(); }
  return items;
}

// Extract body text for a newsflash article
async function fetchBody(page, url) {
  try {
    await page.goto(url, { waitUntil: 'networkidle', timeout: 25000 });
    // Wait for SPA to render the newsflash body
    try { await page.waitForSelector('.item-desc, .item-title', { timeout: 8000 }); } catch {}
    await page.waitForTimeout(1000);
    if (await isCaptchaBlocked(page)) return '';
    return await page.evaluate(() => {
      // 36kr newsflash: content inside [class*="newsflash"] or [class*="detail"] containers
      const containerSels = ['.item-desc', '[class*="newsflash-detail-content"]', '[class*="newsflash-detail"]', '[class*="newsflashContent"]', '[class*="item-content"]', '[class*="detail-content"]', '[class*="summary-content"]', '[class*="newsflash"] [class*="content"]', '[class*="detail"] [class*="content"]'];
      for (const sel of containerSels) {
        const el = document.querySelector(sel);
        if (el) { const text = (el.innerText || '').trim(); if (text.length > 30) return text; }
      }
      const pSels = ['[class*="newsflash"] p', '[class*="detail"] p', '[class*="content"] p', 'article p', 'main p'];
      for (const sel of pSels) {
        const paras = [...document.querySelectorAll(sel)].map(p => p.innerText.trim()).filter(t => t.length > 30);
        if (paras.length > 0) return paras.join('\n\n');
      }
      const blocks = [...document.querySelectorAll('div, article, section')]
        .map(e => (e.innerText || '').trim())
        .filter(t => t.length > 200 && t.length < 3000 && !t.includes('登录') && !t.includes('搜索'));
      return blocks.sort((a, b) => b.length - a.length)[0] || '';
    });
  } catch (e) { return ''; }
}

async function run() {
  const seen = loadSeen();
  console.log('[36kr] start (target=' + TARGET + ', mode=DOM, headed=' + HEADED + ')');

  const browser = await createBrowser();
  let items = [];
  try {
    items = await collectNewsflashes(browser);
  } finally { await browser.close(); }

  // CAPTCHA blocked - graceful degradation
  if (items.length === 0) {
    console.log('[36kr] no items retrieved (CAPTCHA or network issue).');
    console.log('[36kr] TIP: run with --headed to solve CAPTCHA manually: node collect-36kr.mjs --headed');
    console.log('[36kr] existing 36kr data in collection/ will be preserved.');
    return;
  }

  // dedup by URL + title
  const urlSeen = new Set();
  const titleSeen = new Set();
  const deduped = items.filter(it => {
    const u = it.url.replace(/[#?].*$/, '');
    const t = it.title.slice(0, 40);
    if (urlSeen.has(u) || titleSeen.has(t)) return false;
    urlSeen.add(u); titleSeen.add(t);
    return true;
  });

  console.log('[36kr] total: ' + items.length + ' (dedup: ' + deduped.length + ')');

  const today = new Date().toISOString().slice(0, 10);
  let n = 0, dup = 0, filtered = 0;
  const bodyBrowser = await createBrowser();
  const bodyContext = await createContext(bodyBrowser);
  const bodyPage = await bodyContext.newPage();

  try {
    for (const it of deduped) {
      if (n >= TARGET) break;
      const rawId = it.url || it.title;
      const id = 'kr36:' + String(rawId).replace(/[^a-z0-9]/gi, '').slice(-24);
      if (seenHas(seen, '36kr', id) && !REFETCH) { dup++; continue; }

      if (!matchesFilter(it.title)) { filtered++; continue; }

      const body = await fetchBody(bodyPage, it.url);

      const meta = {
        id: 'STK-' + today.replace(/-/g, '') + '-KR' + String(n + 1).padStart(3, '0'),
        category: 'stocks', ticker: '',
        title: it.title.slice(0, 200),
        source: '36kr', source_type: 'media',
        url: it.url,
        relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-36kr', priority: 'TBD',
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };

      const bodyText = body || it.title;
      const md = frontmatter(meta) + '\n\n## Body\n\n' + bodyText.slice(0, 4000) + '\n';
      fs.writeFileSync(path.join(OUT, meta.id + '.md'), md, 'utf8');
      seenAdd(seen, '36kr', id, { title: it.title.slice(0, 80), body_chars: bodyText.length });
      n++;
      console.log('[' + n + '] ' + it.title.slice(0, 50) + ' (' + bodyText.length + ' chars)');
    }
  } finally {
    try { await bodyContext.storageState({ path: SESSION_FILE }); } catch {}
    await bodyContext.close();
    await bodyBrowser.close();
  }

  saveSeen(seen);
  console.log('\n=== 36kr: new=' + n + ' (dup ' + dup + ' / filtered ' + filtered + ') -> ' + OUT + ' ===');
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

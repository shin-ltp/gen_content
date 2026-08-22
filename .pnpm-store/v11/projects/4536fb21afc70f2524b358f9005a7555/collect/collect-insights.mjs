// collect-insights.mjs - GS / MS / JPM Insights collection
// GS: direct HTTP fetch
// MS: Playwright stealth + topic-page article discovery + body extraction with nav filter
// JPM: Playwright headless + URL depth filter
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const _require = createRequire('C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
const { chromium } = _require('playwright');
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, stripHtml, UA_HEADERS, atomicWrite } from './collect-utils.mjs';

const OUT = process.env.INSIGHTS_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });



async function createStealthBrowser() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    args: ['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
  });
  return browser;
}

async function stealthPage(browser) {
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    locale: 'en-US', viewport: { width: 1920, height: 1080 }
  });
  await context.addInitScript(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });
    window.chrome = { runtime: {} };
  });
  const page = await context.newPage();
  return { page, context };
}

// ===================== Goldman Sachs (HTTP) =====================
async function collectGS(seen) {
  console.log('[insights] Goldman Sachs (HTTP)...');
  const today = new Date().toISOString().slice(0, 10);
  let n = 0;
  try {
    const r = await fetch('https://www.goldmansachs.com/insights', { headers: UA_HEADERS, signal: AbortSignal.timeout(15000) });
    if (!r.ok) { console.error('[insights] GS HTTP ' + r.status); return 0; }
    const html = await r.text();
    const linkRe = /<a[^>]+href="(\/insights\/[^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
    const items = [];
    let m;
    while ((m = linkRe.exec(html)) !== null) {
      const href = m[1];
      const inner = stripHtml(m[2]);
      if (inner.length > 10 && href.includes('/insights/')) {
        const id = 'gs:' + href.replace(/[^a-z0-9]/gi, '').slice(-30);
        if (seenHas(seen, 'gs-insights', id)) continue;
        items.push({ title: inner.slice(0, 200), url: 'https://www.goldmansachs.com' + href, id });
      }
    }
    const unique = [];
    const seenUrls = new Set();
    for (const it of items) { if (!seenUrls.has(it.url)) { seenUrls.add(it.url); unique.push(it); } }
    for (const it of unique.slice(0, 10)) {
      let body = '';
      try {
        const ar = await fetch(it.url, { headers: UA_HEADERS, signal: AbortSignal.timeout(12000) });
        if (ar.ok) {
          const ahtml = await ar.text();
          const paras = [...ahtml.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)].map(x => stripHtml(x[1])).filter(p => p.length > 30);
          body = paras.slice(0, 30).join('\n\n');
        }
      } catch {}
      const meta = {
        id: 'RES-' + today.replace(/-/g, '') + '-GS' + String(n + 1).padStart(3, '0'),
        category: 'research', ticker: '',
        title: it.title, source: 'Goldman Sachs Insights', source_type: 'research',
        url: it.url, relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-insights', priority: 'TBD',
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const md = frontmatter(meta) + '\n\n## Body\n\n' + (body || '(body not retrieved)') + '\n';
      atomicWrite(path.join(OUT, meta.id + '.md'), md);
      seenAdd(seen, 'gs-insights', it.id, { title: it.title.slice(0, 80), body_chars: body.length });
      n++;
      console.log('[GS] [' + n + '] ' + it.title.slice(0, 50) + ' (' + body.length + ' chars)');
    }
  } catch (e) { console.error('[insights] GS error: ' + e.message); }
  return n;
}

// ===================== Morgan Stanley (topic page + body extraction) =====================
async function collectMS(browser, seen) {
  console.log('[insights] Morgan Stanley (topic discovery)...');
  const today = new Date().toISOString().slice(0, 10);
  let n = 0;
  const { page, context } = await stealthPage(browser);
  try {
    // Discover articles from topic pages (SPA-rendered article lists)
    const topics = ['market-trends', 'technology-disruption'];
    const allArticles = [];
    for (const topic of topics) {
      let loaded = false;
      for (let attempt = 1; attempt <= 2; attempt++) {
        try {
          await page.goto('https://www.morganstanley.com/insights/topics/' + topic, { waitUntil: 'domcontentloaded', timeout: 20000 });
          await page.waitForTimeout(2500);
          // scroll to trigger lazy-loaded article lists
          for (let i = 0; i < 2; i++) { try { await page.evaluate(() => window.scrollBy(0, 1500)); } catch {} await page.waitForTimeout(800); }
          loaded = true;
          break;
        } catch (e) {
          process.stderr.write('[MS] topic ' + topic + ' attempt ' + attempt + ' failed: ' + e.message.slice(0, 60) + '\n');
          if (attempt < 2) { try { await page.waitForTimeout(2000); } catch {} try { await page.goto('about:blank', { timeout: 5000 }); } catch {} }
        }
      }
      if (!loaded) continue;
      const articles = await page.evaluate(() => {
        return [...document.querySelectorAll('a[href*="/insights/articles/"]')]
          .map(a => ({ href: a.href.split('?')[0], text: (a.innerText || a.getAttribute('aria-label') || '').trim().slice(0, 200) }))
          .filter(a => a.text.length > 10)
          .filter((v, i, arr) => arr.findIndex(x => x.href === v.href) === i);
      });
      for (const a of articles) {
        if (!allArticles.find(x => x.href === a.href)) allArticles.push({ ...a, topic });
      }
      process.stderr.write('[MS] topic ' + topic + ': ' + articles.length + ' articles\n');
    }
    process.stderr.write('[MS] total unique articles: ' + allArticles.length + '\n');

    // Visit each article to extract body (filter out nav/footer)
    for (const it of allArticles) {
      if (n >= 6) break;
      const id = 'ms:' + it.href.replace(/[^a-z0-9]/gi, '').slice(-30);
      if (seenHas(seen, 'ms-insights', id)) continue;
      let body = '';
      try {
        await page.goto(it.href, { waitUntil: 'domcontentloaded', timeout: 18000 });
        await page.waitForTimeout(2000);
        body = await page.evaluate(() => {
          // Filter nav/header/footer/menu paragraphs
          const all = [...document.querySelectorAll('p')];
          const content = all.filter(p => {
            const text = p.innerText.trim();
            if (text.length < 60) return false;
            // skip nav/footer/menu elements
            if (p.closest('nav, header, footer, [class*="menu"], [class*="Menu"], [class*="nav-"], [class*="Nav-"], [class*="footer"], [class*="Footer"], [class*="breadcrumb"], [class*="Breadcrumb"], [role="navigation"]')) return false;
            // skip boilerplate phrases
            if (text.includes('At Morgan Stanley, we lead with exceptional')) return false;
            if (text.includes('Learn from our industry leaders')) return false;
            if (text.includes('Sign Up For the Five Ideas')) return false;
            return true;
          });
          return content.map(p => p.innerText.trim()).join('\n\n');
        });
      } catch (e) {
        process.stderr.write('[MS] article body fetch failed: ' + e.message.slice(0, 60) + '\n');
      }
      if (body.length < 200) continue;  // skip if no real content extracted
      const meta = {
        id: 'RES-' + today.replace(/-/g, '') + '-MS' + String(n + 1).padStart(3, '0'),
        category: 'research', ticker: '',
        title: it.text.slice(0, 200), source: 'Morgan Stanley Insights', source_type: 'research',
        url: it.href, relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-insights', priority: 'TBD',
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const md = frontmatter(meta) + '\n\n## Body\n\n' + body.slice(0, 6000) + '\n';
      atomicWrite(path.join(OUT, meta.id + '.md'), md);
      seenAdd(seen, 'ms-insights', id, { title: it.text.slice(0, 80), body_chars: body.length, topic: it.topic });
      n++;
      console.log('[MS] [' + n + '] ' + it.text.slice(0, 50) + ' (' + body.length + ' chars) [' + it.topic + ']');
    }
  } catch (e) { console.error('[insights] MS error: ' + e.message); }
  finally { await context.close(); }
  return n;
}

// ===================== JPMorgan (Playwright) =====================
async function collectJPM(browser, seen) {
  console.log('[insights] JPMorgan...');
  const today = new Date().toISOString().slice(0, 10);
  let n = 0;
  const { page, context } = await stealthPage(browser);
  try {
    let jpmLoaded = false;
    for (let attempt = 1; attempt <= 3; attempt++) {
      try {
        await page.goto('https://www.jpmorgan.com/insights', { waitUntil: 'domcontentloaded', timeout: 30000 });
        await page.waitForTimeout(4000);
        jpmLoaded = true;
        break;
      } catch (e) {
        process.stderr.write('[JPM] attempt ' + attempt + '/3 failed: ' + e.message.slice(0, 80) + '\n');
        if (attempt < 3) { try { await page.waitForTimeout(3000); } catch {} try { await page.goto('about:blank', { timeout: 5000 }); } catch {} }
      }
    }
    if (!jpmLoaded) { console.error('[insights] JPM all retries failed'); return 0; }
    for (let i = 0; i < 3; i++) { try { await page.evaluate(() => window.scrollBy(0, 1000)); } catch {} await page.waitForTimeout(800); }

    const items = await page.evaluate(() => {
      const results = [];
      const seenHrefs = new Set();
      const sels = [
        'a[href*="/insights/"]', 'a[href*="/perspectives/"]', 'article a[href]',
        'h2 a[href]', 'h3 a[href]', 'h4 a[href]',
        '[class*="card"] a[href]', '[class*="Card"] a[href]', '[class*="tile"] a[href]', '[class*="item"] a[href]'
      ];
      for (const sel of sels) {
        try {
          document.querySelectorAll(sel).forEach(a => {
            const href = a.href;
            if (!href || seenHrefs.has(href)) return;
            if (!href.includes('jpmorgan.com')) return;
            if (href.match(/\/insights\/?$/)) return;
            // URL depth filter: skip top-level category pages
            const parts = new URL(href).pathname.split('/').filter(Boolean);
            if (parts.length < 3) return;
            const titleEl = a.querySelector('h1, h2, h3, h4, [class*="title"], [class*="Title"], [class*="heading"]') || a;
            const title = (titleEl.textContent || '').replace(/\s+/g, ' ').trim();
            if (title.length > 15 && href.length > 50) { seenHrefs.add(href); results.push({ title: title.slice(0, 200), url: href.split('?')[0] }); }
          });
        } catch {}
      }
      return results.slice(0, 15);
    });
    process.stderr.write('[JPM] found ' + items.length + ' candidates\n');

    for (const it of items) {
      const id = 'jpm:' + it.url.replace(/[^a-z0-9]/gi, '').slice(-30);
      if (seenHas(seen, 'jpm-insights', id)) continue;
      let body = '';
      try {
        await page.goto(it.url, { waitUntil: 'domcontentloaded', timeout: 18000 });
        await page.waitForTimeout(2000);
        body = await page.evaluate(() => {
          const all = [...document.querySelectorAll('p')];
          const content = all.filter(p => {
            const text = p.innerText.trim();
            if (text.length < 60) return false;
            if (p.closest('nav, header, footer, [class*="menu"], [class*="Menu"], [class*="footer"], [class*="Footer"], [role="navigation"]')) return false;
            return true;
          });
          return content.map(p => p.innerText.trim()).join('\n\n');
        });
      } catch {}
      if (body.length < 200) continue;
      const meta = {
        id: 'RES-' + today.replace(/-/g, '') + '-JPM' + String(n + 1).padStart(3, '0'),
        category: 'research', ticker: '',
        title: it.title.slice(0, 200), source: 'JPMorgan Insights', source_type: 'research',
        url: it.url, relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-insights', priority: 'TBD',
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const md = frontmatter(meta) + '\n\n## Body\n\n' + body.slice(0, 6000) + '\n';
      atomicWrite(path.join(OUT, meta.id + '.md'), md);
      seenAdd(seen, 'jpm-insights', id, { title: it.title.slice(0, 80), body_chars: body.length });
      n++;
      console.log('[JPM] [' + n + '] ' + it.title.slice(0, 50) + ' (' + body.length + ' chars)');
      if (n >= 6) break;
    }
  } catch (e) { console.error('[insights] JPM error: ' + e.message); }
  finally { await context.close(); }
  return n;
}

async function run() {
  const seen = loadSeen();
  console.log('[insights] GS/MS/JPM start');
  const gsN = await collectGS(seen);
  let msN = 0, jpmN = 0;
  let browser = null;
  try {
    browser = await createStealthBrowser();
    try { msN = await collectMS(browser, seen); } catch (e) { console.error('[insights] MS outer error: ' + e.message); }
    try { jpmN = await collectJPM(browser, seen); } catch (e) { console.error('[insights] JPM outer error: ' + e.message); }
  } finally { if (browser) { try { await browser.close(); } catch {} } }
  try { saveSeen(seen); } catch (e) { console.error('[insights] seen 保存失敗: ' + e.message); }
  const total = gsN + msN + jpmN;
  console.log('\n=== insights: GS=' + gsN + ' MS=' + msN + ' JPM=' + jpmN + ' total=' + total + ' -> ' + OUT + ' ===');
  if (total === 0) {
    // 当日分の素材が既に存在する場合は、一時的なネット/反爬不調でも整体 FAIL にしない
    const today = new Date().toISOString().slice(0, 10);
    const dayPrefix = 'RES-' + today.replace(/-/g, '');
    let existing = 0;
    try {
      existing = fs.existsSync(OUT)
        ? fs.readdirSync(OUT).filter(f => f.startsWith(dayPrefix) && f.endsWith('.md')).length
        : 0;
    } catch {}
    if (existing > 0) {
      console.log('[insights] 本日分 ' + existing + ' 件は収集済みのため成功扱い（今回 0 新規）');
      process.exit(0);
    }
    process.exit(1);
  }
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

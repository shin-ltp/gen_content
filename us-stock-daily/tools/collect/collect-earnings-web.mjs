// collect-earnings-web.mjs — ERN(決算)当日Web検索フォールバック収集器
// cnbc-biz RSS が seen-store 全部重複で新規0件でも、旧号の素材をコピー
// せず、SearXNG(news / 過去24時間)で当日の決算ニュースを探して ERN 素材
// として保存する。古い記事を充填する用途には絶対に使わないこと。
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, stripTags, fetchRetry, UA_HEADERS, delay, dateKey, atomicWrite, finish } from './collect-utils.mjs';

const OUT = process.env.EARN_WEB_OUT || './out';
const PIPELINE_DATE = process.env.EARN_WEB_DATE || new Date().toISOString().slice(0, 10);
const MAX_SAVE = Number(process.env.EARN_WEB_MAX || '4');
const SEARCH = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//, '')), '..', 'searxng', 'search.ps1');

fs.mkdirSync(OUT, { recursive: true });

const QUERIES = [
  'quarterly results',
  'earnings report',
  'companies reporting earnings today',
  'US stock earnings',
];

const DOMAIN_BLOCK = /(^|\.)(youtube|youtu|twitter|x|facebook|instagram|tiktok|reddit|wikipedia|linkedin|msn|note)\./i;
const TITLE_RE = /earn|quarter|results|profit|revenue|eps|guidance|outlook/i;
const FIN_HOSTS = /(cnbc|reuters|marketwatch|bloomberg|barrons|wsj|ft|fool|benzinga|seekingalpha|finance\.yahoo|investors)\./i;

function searchNews(query, categories) {
  const r = spawnSync('powershell', [
    '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', SEARCH,
    query, '-Categories', categories, '-TimeRange', 'day', '-MaxResults', '20', '-Raw',
  ], { encoding: 'utf8', timeout: 120000, maxBuffer: 20 * 1024 * 1024 });
  if (r.status !== 0) {
    console.error('[earn-web] search failed: ' + query + ' rc=' + r.status);
    return [];
  }
  try {
    return JSON.parse(r.stdout).results || [];
  } catch (e) {
    console.error('[earn-web] search parse failed: ' + e.message);
    return [];
  }
}

function hostOf(u) { try { return new URL(u).hostname.replace(/^www\./, ''); } catch { return ''; } }
function prevDay(dateStr) {
  const d = new Date(dateStr + 'T00:00:00Z');
  d.setUTCDate(d.getUTCDate() - 2);
  return d.toISOString().slice(0, 10);
}

async function fetchBody(url) {
  try {
    const r = await fetchRetry(
      () => fetch(url, { headers: UA_HEADERS, signal: AbortSignal.timeout(15000) }),
      { retries: 2, delayMs: 1500 },
    );
    if (!r.ok) return '';
    const html = await r.text();
    const paras = [...html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)]
      .map(m => stripTags(m[1])).filter(p => p.length > 60);
    return paras.slice(0, 40).join('\n\n');
  } catch { return ''; }
}

async function run() {
  const seen = loadSeen();
  const byUrl = new Map();
  for (const q of QUERIES) {
    for (const item of searchNews(q, 'news')) {
      const url = String(item.url || item.urlDirect || '');
      if (!/^https?:\/\//.test(url)) continue;
      if (DOMAIN_BLOCK.test(hostOf(url))) continue;
      const title = String(item.title || '').trim();
      if (title.length < 10 || !TITLE_RE.test(title)) continue;
      if (!byUrl.has(url)) byUrl.set(url, { url, title, published: item.publishedDate || '' });
    }
  }
  // news カテゴリで候補が足りなければ general（過去24時間）も念のため掘る
  if (byUrl.size < MAX_SAVE * 3) {
    for (const q of QUERIES.slice(0, 2)) {
      for (const item of searchNews(q, 'general')) {
        const url = String(item.url || '');
        if (!/^https?:\/\//.test(url) || DOMAIN_BLOCK.test(hostOf(url))) continue;
        const title = String(item.title || '').trim();
        if (title.length < 10 || !TITLE_RE.test(title)) continue;
        if (!byUrl.has(url)) byUrl.set(url, { url, title, published: item.publishedDate || '' });
      }
    }
  }
  // 金融メディアを優先し、それ以外は後回し（品質の下限担保）。
  const candidates = [...byUrl.values()].sort((a, b) =>
    (FIN_HOSTS.test(hostOf(b.url)) ? 1 : 0) - (FIN_HOSTS.test(hostOf(a.url)) ? 1 : 0));
  console.log('[earn-web] candidates=' + candidates.length + ' date=' + PIPELINE_DATE);

  let saved = 0;
  let seq = 1;
  for (const c of candidates) {
    if (saved >= MAX_SAVE) break;
    const host = hostOf(c.url);
    const rawId = c.url.replace(/[^a-z0-9]/gi, '').slice(-24);
    if (seenHas(seen, 'earn-web', host + ':' + rawId)) continue;
    const pub = dateKey(c.published);
    // 過去24時間検索でも、明らかに古い publishedDate は除外（誤検出対策）
    if (pub && pub < prevDay(PIPELINE_DATE)) continue;
    const body = await fetchBody(c.url);
    if (body.length < 500) continue;
    const meta = {
      id: 'ERN-ew' + String(seq).padStart(2, '0'),
      category: 'earnings', ticker: '',
      title: c.title.slice(0, 200), source: host, source_type: 'media',
      url: c.url, relevance: 'us-stock',
      collected_at: new Date().toISOString().slice(0, 16),
      collector: 'collect-earnings-web', priority: 'TBD',
      feed: 'searxng-news', pub_date: pub || PIPELINE_DATE,
      assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw',
    };
    const md = frontmatter(meta) + '\n\n## Body\n\n' + body + '\n';
    atomicWrite(path.join(OUT, meta.id + '.md'), md);
    seenAdd(seen, 'earn-web', host + ':' + rawId, { host, title: c.title.slice(0, 80), pub_date: meta.pub_date });
    saved++;
    console.log('[' + saved + '] ' + host + ' | ' + body.length + '字 | ' + c.title.slice(0, 60));
    await delay(500);
  }
  try { saveSeen(seen); } catch (e) { console.error('[earn-web] seen save failed: ' + e.message); }
  finish('earn-web', saved, 0);
}

run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

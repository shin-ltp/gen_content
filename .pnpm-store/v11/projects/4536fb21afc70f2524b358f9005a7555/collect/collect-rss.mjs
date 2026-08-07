// collect-rss.mjs — Reuters/CNBC RSS 收集器（摘要+链接，CNBC尝试SSR全文）
import fs from 'node:fs';
import path from 'node:path';
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, stripTags, fetchRetry } from './collect-utils.mjs';

const OUT = process.env.RSS_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' };

const FEEDS = {
  'cnbc-biz': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839135',
  'cnbc-tech': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114',
  'cnbc-economy': 'https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258'
};


function parseItems(xml) {
  const items = [];
  const blocks = xml.split(/<item[\s>]/i).slice(1);
  for (let raw of blocks) {
    const end = raw.search(/<\/item>/i);
    const blk = end >= 0 ? raw.slice(0, end) : raw;
    const pick = (tag) => {
      const re = new RegExp('<' + tag + '[^>]*>([\\s\\S]*?)<\\/' + tag + '>', 'i');
      const mm = blk.match(re);
      return mm ? stripTags(mm[1]) : '';
    };
    const link = pick('link');
    items.push({ title: pick('title'), link, desc: pick('description'), date: pick('pubDate'), guid: pick('guid') });
  }
  return items;
}

async function tryFullSSR(url) {
  // CNBC 文章页通常可 SSR，Reuters 可能有付费墙；尝试抓，失败返回空
  try {
    const r = await fetch(url, { headers: UA, signal: AbortSignal.timeout(10000) });
    if (!r.ok) return '';
    const html = await r.text();
    // CNBC 用 article-body 或 group 类；通用：取最长的 <p> 集合
    const paras = [...html.matchAll(/<p[^>]*>([\s\S]*?)<\/p>/gi)].map(x => stripTags(x[1])).filter(p => p.length > 40);
    return paras.slice(0, 40).join('\n\n');
  } catch { return ''; }
}

function dateKey(s) { try { return new Date(s).toISOString().slice(0,10); } catch { return ''; } }

async function run() {
  const seen = loadSeen();
  let n = 0, dup = 0;
  for (const [feed, url] of Object.entries(FEEDS)) {
    let xml = '';
    try {
      const r = await fetchRetry(() => fetch(url, { headers: UA, signal: AbortSignal.timeout(15000) }), 3, 2000);
      xml = await r.text();
    } catch (e) { console.error('[feed-skip] ' + feed + ': ' + e.message); continue; }
    if (!xml || xml.length < 100) { console.error('[feed-skip] ' + feed + ': empty response'); continue; }
    const items = parseItems(xml);
    console.log('feed=' + feed + ' items=' + items.length);
    for (const it of items) {
      const rawId = it.guid || it.link || it.title;
      const id = feed + ':' + String(rawId).replace(/[^a-z0-9]/gi,'').slice(-24);
      const skey = 'rss-' + feed;
      if (seenHas(seen, skey, id)) { dup++; continue; }
      const dt = dateKey(it.date);
      let full = '';
      if (it.link && it.link.includes('cnbc.com')) {
        try { full = await tryFullSSR(it.link); } catch (e) { full = ''; }
      }
      if (!it.title || it.title.length < 3) continue;
      const meta = {
        id: 'RSS-' + id, category: 'news', ticker: '',
        title: it.title.slice(0,200), source: feed, source_type: 'media',
        url: it.link, relevance: 'us-stock', collected_at: new Date().toISOString().slice(0,16),
        collector: 'collect-rss', priority: 'TBD', feed: feed, pub_date: dt,
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const body = full || ('(RSS摘要) ' + it.desc);
      const md = frontmatter(meta) + '\n\n## Body\n\n' + body + '\n';
      fs.writeFileSync(path.join(OUT, meta.id.replace(/[^a-z0-9-]/gi,'_') + '.md'), md, 'utf8');
      seenAdd(seen, skey, id, { feed, title: it.title.slice(0,80), pub_date: dt });
      n++;
      console.log('[' + n + '] ' + feed + ' | full=' + full.length + '字 | ' + it.title.slice(0,50));
    }
  }
  saveSeen(seen);
  console.log('\n=== rss: 新增 ' + n + ' (跨天重复 ' + dup + ') -> ' + OUT + ' ===');
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

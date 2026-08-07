// collect-wscn.mjs — 华尔街见闻收集器（分页 + 跨页去重 + SSR全文）
import fs from 'node:fs';
import path from 'node:path';
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd, stats as seenStats } from './seen-store.mjs';
import { frontmatter, stripHtml } from './collect-utils.mjs';
const OUT = process.env.WSCN_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });
const UA = { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' };
const TARGET = parseInt(process.env.WSCN_TARGET || '30', 10);
const REFETCH = process.argv.includes('--refetch');
process.on('unhandledRejection', e => console.error('[REJ] ' + (e&&e.message||e)));

const CONTENT_RE = /"content"\s*:\s*("(?:[^"\\]|\\.)*")/;

async function fetchList(channel, limit, cursor) {
  let url = 'https://api-one-wscn.awtmt.com/apiv1/content/articles?channel=' + channel + '&limit=' + limit;
  if (cursor) url += '&cursor=' + encodeURIComponent(cursor);
  const r = await fetch(url, { headers: UA, signal: AbortSignal.timeout(15000) });
  if (!r.ok) throw new Error('list ' + r.status);
  const j = await r.json();
  return { items: (j.data && j.data.items) ? j.data.items : [], next: (j.data && j.data.next_cursor) ? j.data.next_cursor : '' };
}

async function fetchFull(id) {
  for (let attempt = 1; attempt <= 2; attempt++) {
    try {
      const r = await fetch('https://wallstreetcn.com/articles/' + id, { headers: UA, signal: AbortSignal.timeout(12000) });
      if (!r.ok) { if (attempt < 2) await new Promise(rs => setTimeout(rs, 1000)); continue; }
      const html = await r.text();
      const m = html.match(CONTENT_RE);
      if (!m) return '';
      let decoded = '';
      try { decoded = JSON.parse(m[1]); } catch {
        decoded = m[1].slice(1, -1)
          .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
          .replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\//g, '/').replace(/\\\\/g, '\\');
      }
      return stripHtml(decoded);
    } catch (e) { if (attempt < 2) await new Promise(rs => setTimeout(rs, 1000)); }
  }
  return '';
}


async function processItem(it, ch) {
  const aid = it.id;
  let full = '';
  try { full = await fetchFull(aid); } catch(e) { full = ''; }
  const body = stripHtml(String(it.content_short || ''));
  const symbols = (it.symbols || []).map(s => String(s.display_symbol || s.symbol || '')).filter(Boolean);
  const dt = it.display_time ? new Date(Number(it.display_time)*1000).toISOString().slice(0,10) : '';
  const meta = {
    id: 'WSCN-' + aid, category: 'research', ticker: symbols.join('/') || '',
    title: String(it.title || '').replace(/\n/g,' '),
    source: '华尔街见闻' + (it.source_name ? ' / ' + String(it.source_name) : ''),
    source_type: 'media', url: 'https://wallstreetcn.com/articles/' + aid,
    relevance: 'us-stock', collected_at: new Date().toISOString().slice(0,16),
    collector: 'collect-wscn', priority: 'TBD', channel: ch, symbols: symbols,
    display_time: dt, assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
  };
  const md = frontmatter(meta) + '\n\n## Body\n\n' + (full || '(全文取得失敗) 摘要: ' + body) + '\n';
  fs.writeFileSync(path.join(OUT, 'WSCN-' + aid + '.md'), md, 'utf8');
  return full.length;
}

async function run() {
  const seen = loadSeen();
  console.log('[seen] 履历库已有: ' + Object.keys(seen.articles).length + ' 条');
  const channels = (process.env.WSCN_CHANNELS || 'us-stock,global').split(',');
  const memSeen = new Set();
  let n = 0, skipped = 0, dupSkipped = 0;
  for (const ch of channels) {
    let cursor = '', pages = 0, chN = 0;
    while (chN < TARGET && pages < 8) {
      pages++;
      let res;
      try { res = await fetchList(ch, 20, cursor); } catch(e) { console.error('[ch-skip] ' + ch + ' p' + pages + ': ' + e.message); break; }
      cursor = res.next;
      if (!res.items.length) break;
      for (const it of res.items) {
        if (!it || memSeen.has(it.id)) continue;
        if (seenHas(seen, 'wallstreetcn', it.id) && !REFETCH) { dupSkipped++; continue; }
        memSeen.add(it.id);
        try {
          const flen = await processItem(it, ch);
          seenAdd(seen, 'wallstreetcn', it.id, { channel: ch, title: String(it.title||'').slice(0,80), full_chars: flen });
          n++; chN++;
          console.log('[' + n + '] ' + ch + ' WSCN-' + it.id + ' full=' + flen + '字 | ' + String(it.title||'').slice(0,46));
          await new Promise(r => setTimeout(r, 250));
          if (chN >= TARGET) break;
        } catch(e) { skipped++; console.error('[skip] ' + it.id + ': ' + e.message); }
      }
      if (!cursor) break;
    }
    console.log('-- ' + ch + ': ' + chN + ' 素材 (' + pages + 'ページ)');
  }
  saveSeen(seen);
  console.log('\n=== wallstreetcn: 新增 ' + n + ' 素材 (skip ' + skipped + ' / 跨天重复 ' + dupSkipped + ') -> ' + OUT + ' ===');
  console.log('[seen] 履历库总计: ' + Object.keys(seen.articles).length + ' 条 | ' + JSON.stringify(seenStats(seen)));
}

run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

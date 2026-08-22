// collect-wscn.mjs — 华尔街见闻收集器（分页 + 跨页去重 + SSR全文）
import fs from 'node:fs';
import path from 'node:path';
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd, stats as seenStats, key as seenKey } from './seen-store.mjs';
import { frontmatter, stripHtml, fetchRetry, UA_HEADERS, delay, atomicWrite } from './collect-utils.mjs';
const OUT = process.env.WSCN_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });
const TARGET = parseInt(process.env.WSCN_TARGET || '30', 10);
const REFETCH = process.argv.includes('--refetch');
process.on('unhandledRejection', e => console.error('[REJ] ' + (e&&e.message||e)));

const CONTENT_RE = /"content"\s*:\s*("(?:[^"\\]|\\.)*")/;
const API_JSON_HEADERS = Object.assign({}, UA_HEADERS, { 'Accept': 'application/json' });

async function fetchList(channel, limit, cursor) {
  let url = 'https://api-one-wscn.awtmt.com/apiv1/content/articles?channel=' + channel + '&limit=' + limit;
  if (cursor) url += '&cursor=' + encodeURIComponent(cursor);
  const r = await fetchRetry(() => fetch(url, { headers: UA_HEADERS, signal: AbortSignal.timeout(15000) }),
    { retries: 3, delayMs: 1500 });
  if (!r.ok) throw new Error('list ' + r.status);
  const j = await r.json();
  const items = (j.data && j.data.items) ? j.data.items : [];
  const next = (j.data && j.data.next_cursor) ? j.data.next_cursor : '';
  if (!Array.isArray(items)) throw new Error('list: items が配列でない');
  return { items, next };
}

async function fetchFullApi(id) {
  // 公式 API 経由で本文を取得（ページが反爬で JS シェルを返す場合でも動作する）
  try {
    const url = 'https://api-one-wscn.awtmt.com/apiv1/content/articles/' + id + '?extract=1';
    const r = await fetchRetry(() => fetch(url, { headers: API_JSON_HEADERS, signal: AbortSignal.timeout(15000) }),
      { retries: 2, delayMs: 1200 });
    if (!r.ok) throw new Error('api ' + r.status);
    const j = await r.json();
    if (!j || j.code !== 20000 || !j.data) throw new Error('api code=' + (j && j.code));
    const content = String(j.data.content || '').trim();
    if (!content) throw new Error('api content empty');
    return stripHtml(content);
  } catch (e) {
    console.error('  [api-full-fail] ' + id + ': ' + String(e.message || e).slice(0, 60));
    return '';
  }
}

async function fetchFullHtml(id) {
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const r = await fetch('https://wallstreetcn.com/articles/' + id,
        { headers: UA_HEADERS, signal: AbortSignal.timeout(12000) });
      if (!r.ok) { if (attempt < 3) { await delay(1200); continue; } return ''; }
      const html = await r.text();
      // 反爬で JS シェルのみ返る場合（本文 JSON なし）は空を返す
      if (html.length < 10000 || !html.includes('"content"')) return '';
      const m = html.match(CONTENT_RE);
      if (!m) return '';
      let decoded = '';
      try { decoded = JSON.parse(m[1]); } catch {
        decoded = m[1].slice(1, -1)
          .replace(/\\u([0-9a-fA-F]{4})/g, (_, h) => String.fromCharCode(parseInt(h, 16)))
          .replace(/\\n/g, '\n').replace(/\\"/g, '"').replace(/\\\//g, '/').replace(/\\\\/g, '\\');
      }
      return stripHtml(decoded);
    } catch (e) { if (attempt < 3) { console.error('  [full-retry] ' + id + ': ' + (e&&e.message||e).slice(0,60)); await delay(1200); } }
  }
  return '';
}

async function fetchFull(id) {
  const api = await fetchFullApi(id);
  if (api) return api;
  return fetchFullHtml(id);
}

// 保存済みファイルが「使用に足る本文」を持つか（失敗マーカー無し + 本文400字以上）
function isCleanMaterial(content) {
  if (content.includes('(全文取得失敗)')) return false;
  const body = content.split('## Body').pop() || '';
  return body.replace(/\s+/g, '').length >= 400;
}


async function processItem(it, ch) {
  const aid = it.id;
  let full = '';
  try {
    full = await fetchFull(aid);
    if (!full) { await delay(4000); full = await fetchFull(aid); }
  } catch(e) { full = ''; }
  // 本文取得に失敗した記事は保存しない（後段の検査・利用を汚染しないため）
  if (!full) {
    console.error('  [body-fail] ' + aid + ': 本文取得失敗（保存せずスキップ）');
    return 0;
  }
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
  const md = frontmatter(meta) + '\n\n## Body\n\n' + full + '\n';
  atomicWrite(path.join(OUT, 'WSCN-' + aid + '.md'), md);
  return full.length;
}

async function run() {
  const seen = loadSeen();
  console.log('[seen] 履历库已有: ' + Object.keys(seen.articles).length + ' 条');
  const channels = (process.env.WSCN_CHANNELS || 'us-stock,global').split(',');
  const memSeen = new Set();
  let n = 0, skipped = 0, dupSkipped = 0;
  let alreadyCollected = 0;
  for (const ch of channels) {
    let cursor = '', pages = 0, chN = 0;
    let noProgress = 0;
    let failStreak = 0, chAbort = false;
    while (chN < TARGET && pages < 12) {
      pages++;
      let res;
      try { res = await fetchList(ch, 20, cursor); } catch(e) { console.error('[ch-skip] ' + ch + ' p' + pages + ': ' + e.message); break; }
      cursor = res.next;
      if (!res.items.length) break;
      let addedThisPage = 0;
      for (const it of res.items) {
        if (!it || memSeen.has(it.id)) continue;
        const outFile = path.join(OUT, 'WSCN-' + it.id + '.md');
        // 過去に本文取得に成功した記事のみスキップ。旧データは摘要長が full_chars に
        // 入っていることがあるため、「600字以上」または「失敗マーカー無しの実ファイル」で判定
        const rec = seen.articles[seenKey('wallstreetcn', it.id)];
        const hasCleanFile = fs.existsSync(outFile)
          && isCleanMaterial(fs.readFileSync(outFile, 'utf8'));
        const doneBefore = !!(rec && rec.full_chars >= 600) || hasCleanFile;
        if (doneBefore && !REFETCH) {
          if (fs.existsSync(outFile)) alreadyCollected++; else dupSkipped++;
          continue;
        }
        memSeen.add(it.id);
        try {
          const flen = await processItem(it, ch);
          if (flen <= 0) {
            skipped++; failStreak++;
            if (failStreak === 3) { console.error('[wscn] 連続' + failStreak + '件失敗 - 15秒クールダウン'); await delay(15000); }
            else if (failStreak >= 6) { console.error('[wscn] 反爬ブロックの可能性 - このチャネルを打ち切り'); chAbort = true; }
            if (chAbort) break;
            continue;
          }
          failStreak = 0;
          seenAdd(seen, 'wallstreetcn', it.id, { channel: ch, title: String(it.title||'').slice(0,80), full_chars: flen });
          n++; chN++;
          console.log('[' + n + '] ' + ch + ' WSCN-' + it.id + ' full=' + flen + '字 | ' + String(it.title||'').slice(0,46));
          addedThisPage++;
          // 反爬対策: 記事間 2.5-4秒のランダム間隔
          await delay(2500 + Math.floor(Math.random() * 1500));
          if (chN >= TARGET) break;
        } catch(e) { skipped++; console.error('[skip] ' + it.id + ': ' + e.message); }
      }
      if (chAbort) break;
      noProgress = addedThisPage === 0 ? noProgress + 1 : 0;
      // 2ページ連続で新規が無ければ打ち切り（既読記事のみの循環を防ぐ）
      if (noProgress >= 2) break;
      if (!cursor) break;
      await delay(2000 + Math.floor(Math.random() * 1000));
    }
    console.log('-- ' + ch + ': ' + chN + ' 素材 (' + pages + 'ページ)');
  }
  try { saveSeen(seen); } catch (e) { console.error('[wscn] seen 保存失敗: ' + e.message); }
  console.log('\n=== wallstreetcn: 新增 ' + n + ' 素材 (skip ' + skipped + ' / 跨天重复 ' + dupSkipped + ' / 当日既収集 ' + alreadyCollected + ') -> ' + OUT + ' ===');
  console.log('[seen] 履历库总计: ' + Object.keys(seen.articles).length + ' 条 | ' + JSON.stringify(seenStats(seen)));
  if (n === 0 && alreadyCollected === 0) {
    console.error('=== wallstreetcn: 0 件（完全失敗） ===');
    process.exit(1);
  }
}

run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

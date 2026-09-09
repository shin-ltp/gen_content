// collect-market.mjs — 零认证市場データ収集（Yahoo Finance 公共 API）
// longbridge 認証が使えない環境でも MKT/MAC を供給できるように追加（2026-08-19）。
// 前提: Node 起動時に --use-system-ca（サンドボックス Node はシステムCA非対応のため）
import fs from 'node:fs';
import path from 'node:path';
import { frontmatter, fetchRetry, atomicWrite, delay } from './collect-utils.mjs';

const OUT = process.env.MARKET_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });

const CHART_URL = 'https://query1.finance.yahoo.com/v8/finance/chart/';

const SYMBOLS = {
  SPX: { sym: '^GSPC', name: 'S&P500', cat: 'MKT', note: '米国株式総合指数' },
  DJI: { sym: '^DJI', name: 'ダウ工業株30種', cat: 'MKT', note: '米国株式指数' },
  IXIC: { sym: '^IXIC', name: 'ナスダック総合', cat: 'MKT', note: '米国株式指数' },
  VIX: { sym: '^VIX', name: 'VIX', cat: 'MKT', note: 'ボラティリティ指標' },
  USDJPY: { sym: 'JPY=X', name: 'ドル円', cat: 'MKT', note: '為替' },
  EURUSD: { sym: 'EURUSD=X', name: 'ユーロドル', cat: 'MKT', note: '為替' },
  US10Y: { sym: '^TNX', name: '米国10年債利回り', cat: 'MAC', note: '金利' },
  US2Y: { sym: '^IRX', name: '米国2年債利回り', cat: 'MAC', note: '金利' },
  GOLD: { sym: 'GC=F', name: '金先物', cat: 'MKT', note: 'コモディティ' },
  WTI: { sym: 'CL=F', name: 'WTI原油先物', cat: 'MKT', note: 'コモディティ' },
  BTC: { sym: 'BTC-USD', name: 'ビットコイン', cat: 'MKT', note: '暗号資産' },
  XLK: { sym: 'XLK', name: 'テクノロジーセクター', cat: 'SEC', note: 'セクターETF' },
  XLY: { sym: 'XLY', name: '一般消費財セクター', cat: 'SEC', note: 'セクターETF' },
  XLC: { sym: 'XLC', name: '通信サービスセクター', cat: 'SEC', note: 'セクターETF' },
  XLF: { sym: 'XLF', name: '金融セクター', cat: 'SEC', note: 'セクターETF' },
  XLE: { sym: 'XLE', name: 'エネルギーセクター', cat: 'SEC', note: 'セクターETF' },
  XLV: { sym: 'XLV', name: 'ヘルスケアセクター', cat: 'SEC', note: 'セクターETF' },
  XLI: { sym: 'XLI', name: '資本材セクター', cat: 'SEC', note: 'セクターETF' },
  XLP: { sym: 'XLP', name: '生活必需品セクター', cat: 'SEC', note: 'セクターETF' },
  XLU: { sym: 'XLU', name: '公益セクター', cat: 'SEC', note: 'セクターETF' },
  XLB: { sym: 'XLB', name: '素材セクター', cat: 'SEC', note: 'セクターETF' },
  XLRE: { sym: 'XLRE', name: '不動産セクター', cat: 'SEC', note: 'セクターETF' },
  NVDA: { sym: 'NVDA', name: 'NVDA', cat: 'STK', note: '個別株' },
  AMD: { sym: 'AMD', name: 'AMD', cat: 'STK', note: '個別株' },
  TSLA: { sym: 'TSLA', name: 'TSLA', cat: 'STK', note: '個別株' },
  MSFT: { sym: 'MSFT', name: 'MSFT', cat: 'STK', note: '個別株' },
  AAPL: { sym: 'AAPL', name: 'AAPL', cat: 'STK', note: '個別株' }
};

async function quoteMeta(sym) {
  const url = CHART_URL + encodeURIComponent(sym) + '?range=1d&interval=5m';
  // Yahoo は UA_HEADERS（Node fetch 風 UA）だと 406 を返すため、
  // リクエストはデフォルトヘッダーのまま送る（2026-08-19 実測）
  const r = await fetchRetry(() => fetch(url, { signal: AbortSignal.timeout(15000) }), { retries: 3, delayMs: 1500 });
  const j = await r.json();
  const res = j && j.chart && j.chart.result && j.chart.result[0];
  if (!res) return null;
  const m = res.meta || {};
  const prev = m.chartPreviousClose || m.previousClose;
  const last = m.regularMarketPrice;
  if (typeof last !== 'number' || Number.isNaN(last) || last <= 0) return null;
  const prevAdj = (typeof prev === 'number' && prev > 0) ? prev : null;
  const chgPct = prevAdj ? ((last - prevAdj) / prevAdj * 100) : null;
  return {
    name: m.shortName || m.longName || sym, symbol: sym,
    last, prev: prevAdj, chgPct, currency: m.currency || '',
    dayHigh: m.regularMarketDayHigh, dayLow: m.regularMarketDayLow,
    time: new Date((m.regularMarketTime || Date.now() / 1000) * 1000).toISOString().slice(0, 16)
  };
}

function formatVal(q) {
  let s = String(Number(q.last).toLocaleString('en-US', { maximumFractionDigits: 2 }));
  if (q.currency === 'JPY') s = q.last.toLocaleString('en-US', { maximumFractionDigits: 2 }) + ' 円';
  return s;
}

function pctStr(v) { return (v === null || v === undefined || Number.isNaN(v)) ? '—' : (v >= 0 ? '+' : '') + v.toFixed(2) + '%'; }

async function run() {
  console.log('[market] 零認証 市場データ収集開始 (Yahoo)');
  const today = new Date().toISOString().slice(0, 10);
  const rows = [];
  const keyRows = [];
  let ok = 0, fail = 0;
  for (const [id, cfg] of Object.entries(SYMBOLS)) {
    let q = null;
    try { q = await quoteMeta(cfg.sym); } catch (e) { q = null; }
    if (!q) { console.error('[market] ' + id + ': 取得失敗'); fail++; continue; }
    rows.push({ id, ...cfg, q });
    keyRows.push(cfg.name + ' ' + formatVal(q) + '（' + pctStr(q.chgPct) + '）');
    ok++;
    console.log('[market] [' + ok + '] ' + cfg.name + ': ' + formatVal(q) + ' ' + pctStr(q.chgPct));
    if (ok % 4 === 0) await delay(500); // レート制限対策
  }
  if (ok === 0) {
    console.error('[market] 全銘柄取得失敗。exit 1');
    process.exit(1);
  }
  const mktRows = rows.filter(r => r.cat === 'MKT');
  const macRows = rows.filter(r => r.cat === 'MAC');
  const stkRows = rows.filter(r => r.cat === 'STK');
  const secRows = rows.filter(r => r.cat === 'SEC');

  // 収集器ごとに固有の連番空間を持つ。STK は 36kr(KRxxx) と衝突しないよう
  // Yahoo 由来であることを示す YHxxx を付ける
  const seqByPrefix = {};
  function idFor(catPrefix) {
    seqByPrefix[catPrefix] = (seqByPrefix[catPrefix] || 0) + 1;
    const n = seqByPrefix[catPrefix];
    const suffix = catPrefix === 'STK' ? 'YH' + String(n).padStart(3, '0') : 'YH' + String(n).padStart(2, '0');
    return catPrefix + '-' + today.replace(/-/g, '') + '-' + suffix;
  }

  function writeMaterial(meta, body) {
    const md = frontmatter(meta) + '\n\n## Body\n\n' + body + '\n';
    atomicWrite(path.join(OUT, meta.id + '.md'), md);
  }

  // 01-market.md に集約（MKT スナップ）
  const mktLines = mktRows.map(r => '| ' + r.name + ' | ' + formatVal(r.q) + ' | ' + pctStr(r.q.chgPct) + ' | ' + (r.q.currency || '') + ' |');
  const macLines = macRows.map(r => '| ' + r.name + ' | ' + formatVal(r.q) + ' | ' + pctStr(r.q.chgPct) + ' | ' + (r.q.currency || '') + ' |');
  const snap = '# ' + today + ' 市場スナップ（零認証取得）\n\n' +
    '## 指数・為替・コモディティ\n\n| 指標 | 値 | 変動 | 通貨 |\n|------|----|------|------|\n' + mktLines.join('\n') + '\n\n' +
    (macLines.length ? '## 金利\n\n| 指標 | 値 | 変動 | 通貨 |\n|------|----|------|------|\n' + macLines.join('\n') + '\n' : '') + '\n' +
    '> 出所: Yahoo Finance 公共API | 収集時刻: ' + new Date().toISOString().slice(0, 16) + '\n';
  const snapMeta = {
    id: idFor('MKT'), category: 'market', ticker: '',
    title: today + ' 主要指数・為替・金利スナップ',
    source: 'Yahoo Finance', source_type: 'data',
    url: 'https://finance.yahoo.com/markets/', relevance: 'us-stock',
    collected_at: new Date().toISOString().slice(0, 16),
    collector: 'collect-market', priority: 'TBD',
    pub_date: today, assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified',
    key_data: keyRows
  };
  writeMaterial(snapMeta, snap);

  // 金利は Gate #0 の MAC カテゴリ素材として独立出力（カバレッジ要件）
  if (macRows.length) {
    const macBody = macRows.map(r => '- ' + r.name + ': ' + formatVal(r.q) + '（' + pctStr(r.q.chgPct) + '）').join('\n');
    const macMeta = {
      id: idFor('MAC'), category: 'macro', ticker: '',
      title: today + ' 金利マクロ（米10年・2年債利回り）',
      source: 'Yahoo Finance', source_type: 'data',
      url: 'https://finance.yahoo.com/bonds/', relevance: 'us-stock',
      collected_at: new Date().toISOString().slice(0, 16),
      collector: 'collect-market', priority: 'TBD',
      pub_date: today, assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified',
      key_data: macRows.map(r => r.name + ' ' + formatVal(r.q) + '（' + pctStr(r.q.chgPct) + '）')
    };
    writeMaterial(macMeta, '## 本日の金利\n\n' + macBody + '\n\n> 出所: Yahoo Finance 公共API | 収集時刻: ' + new Date().toISOString().slice(0, 16) + '\n');
  }

  // 個別株を STK 素材として出す（36kr/RSS と別枠で厚み追加）
  for (const r of stkRows) {
    const meta = {
      id: idFor('STK'), category: 'stocks', ticker: r.q.symbol,
      title: r.name + ' 株価 ' + formatVal(r.q) + '（' + pctStr(r.q.chgPct) + '）',
      source: 'Yahoo Finance', source_type: 'data',
      url: 'https://finance.yahoo.com/quote/' + encodeURIComponent(r.q.symbol), relevance: 'us-stock',
      collected_at: new Date().toISOString().slice(0, 16),
      collector: 'collect-market', priority: 'TBD',
      pub_date: today, assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified'
    };
    const body = r.name + ' の終値は ' + formatVal(r.q) + '（' + pctStr(r.q.chgPct) + '）。' +
      '前日比 ' + (r.q.chgPct >= 0 ? '上昇' : '下落') + '。当日高値 ' + (r.q.dayHigh || '—') + '、安値 ' + (r.q.dayLow || '—') + '。\n';
    writeMaterial(meta, body);
  }

  // セクターETF を SECTOR 素材として出力（A-02 市況総括の値上/値下セクターリスト用・2026-08-31）
  if (secRows.length) {
    const sorted = [...secRows].sort((a, b) => (b.q.chgPct || 0) - (a.q.chgPct || 0));
    const secLines = sorted.map(r => '| ' + r.name + ' | ' + r.q.symbol + ' | ' + pctStr(r.q.chgPct) + ' |');
    const secBody = '# ' + today + ' セクター騰落（SPDR 11セクターETF・終値基準）\n\n' +
      '| セクター | ETF | 前日比 |\n|------|------|------|\n' + secLines.join('\n') + '\n\n' +
      '> 出所: Yahoo Finance 公共API | 収集時刻: ' + new Date().toISOString().slice(0, 16) + '\n';
    const secMeta = {
      id: idFor('SEC'), category: 'market', ticker: '',
      title: today + ' セクター騰落スナップ（値上がり/値下がり筆頭）',
      source: 'Yahoo Finance', source_type: 'data',
      url: 'https://finance.yahoo.com/sectors/', relevance: 'us-stock',
      collected_at: new Date().toISOString().slice(0, 16),
      collector: 'collect-market', priority: 'TBD',
      pub_date: today, assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified',
      key_data: sorted.map(r => r.name + ' ' + pctStr(r.q.chgPct))
    };
    writeMaterial(secMeta, secBody);
  }

  console.log('\n=== market: ' + ok + ' 銘柄 (失敗 ' + fail + ') -> ' + OUT + ' ===');
  process.exit(0);
}

run().catch(e => { console.error('FATAL: ' + (e && e.message || e).toString().slice(0, 300)); process.exit(1); });

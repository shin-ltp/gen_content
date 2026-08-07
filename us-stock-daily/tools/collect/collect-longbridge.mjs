// collect-longbridge.mjs — longbridge CLI 一次数据收集（指数/个股/汇率/市场温度）
import fs from 'node:fs';
import path from 'node:path';
import { execSync } from 'node:child_process';
import { frontmatter } from './collect-utils.mjs';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const LB = path.join(PROJECT, 'tools', 'bin', 'longbridge.exe');
const OUT = process.env.LB_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });

const INDICES = ['.SPX.US', '.DJI.US', '.IXIC.US', '.VIX.US'];
const STOCKS = (process.env.LB_STOCKS || 'NVDA.US,AMD.US,PLTR.US,QCOM.US,MSFT.US,AAPL.US,TSLA.US,META.US,AMZN.US,GOOGL.US').split(',');

function lbJSON(args) {
  try {
    const out = execSync('"' + LB + '" ' + args.join(' ') + ' --format json', { encoding: 'utf8', timeout: 30000, stdio: ['pipe','pipe','ignore'] });
    const parsed = JSON.parse(out);
    // データ検証: 配列なら空でなければOK
    if (Array.isArray(parsed) && parsed.length === 0) { console.error('[lb-warn] ' + args.join(' ') + ': empty array'); return null; }
    return parsed;
  } catch (e) {
    console.error('[lb-err] ' + args.join(' ') + ': ' + (e.message || e).slice(0, 100));
    return null;
  }
}

function pct(v) {
  const n = Number(v);
  return isNaN(n) ? '' : (n >= 0 ? '+' : '') + n + '%';
}

function fmt(n) {
  const x = Number(n);
  return isNaN(x) ? '—' : x.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

async function run() {
  const today = new Date().toISOString().slice(0,10);
  const lines = [];
  const keyData = [];
  let successCount = 0;

  // 1. 指数
  const idx = lbJSON(['quote', ...INDICES]);
  if (idx && Array.isArray(idx)) {
    successCount++;
    for (const q of idx) {
      if (!q || !q.symbol) continue;
      const name = {'.SPX.US':'S&P500','.DJI.US':'ダウ','.IXIC.US':'ナスダック','.VIX.US':'VIX'}[q.symbol] || q.symbol;
      lines.push('| ' + name + ' | ' + fmt(q.last) + ' | ' + pct(q.change_percentage) + ' |');
      keyData.push(name + ' ' + fmt(q.last) + '（' + pct(q.change_percentage) + '）');
    }
  }
  // 2. 个股
  const stk = lbJSON(['quote', ...STOCKS]);
  if (stk && Array.isArray(stk)) {
    successCount++;
    for (const q of stk) {
      if (!q || !q.symbol) continue;
      lines.push('| ' + q.symbol + ' | ' + fmt(q.last) + ' | ' + pct(q.change_percentage) + ' |出来高' + fmt(q.volume) + ' |');
      keyData.push(q.symbol + ' ' + fmt(q.last) + '（' + pct(q.change_percentage) + '）');
    }
  }
  // 3. 汇率（取 USDJPY）
  const fx = lbJSON(['exchange-rate']);
  if (fx && fx.exchanges) {
    successCount++;
    const usdjpy = fx.exchanges.find(e => e.base_currency==='USD' && e.other_currency==='JPY');
    if (usdjpy) { lines.push('| ドル円 | ' + usdjpy.average_rate + ' | - |'); keyData.push('ドル円 ' + usdjpy.average_rate); }
  }
  // 4. 市场温度
  const mt = lbJSON(['market-temp', 'US']);
  if (mt && Array.isArray(mt)) {
    successCount++;
    let tempStr = '';
    for (const r of mt) { if (r.field==='Temperature') tempStr += '温度' + r.value; if (r.field==='Description') tempStr += '(' + r.value + ')'; if (r.field==='Valuation') tempStr += ' / 估值' + r.value; }
    if (tempStr) { lines.push('| 市場温度 | ' + tempStr + ' | - |'); keyData.push('市場温度: ' + tempStr); }
  }

  // 全API失敗時は既存ファイルを上書きしない
  if (successCount === 0) {
    console.error('[longbridge] 全API呼び出し失敗。01-market.md を更新せず終了');
    console.error('[longbridge] ヒント: longbridge auth login で再認証が必要かも');
    process.exit(1);
  }
  if (successCount < 3) {
    console.error('[longbridge] 警告: ' + successCount + '/4 APIのみ成功（部分失敗）。取得できたデータでファイル生成します');
  }

  // 生成素材文件
  const meta = {
    id: 'MKT-' + today.replace(/-/g,'') + '-001', category: 'market', ticker: '',
    title: '主要指数・注目銘柄・為替・市場温度スナップ（' + today + '）',
    source: 'longbridge CLI（一次データ）', source_type: 'data',
    url: 'cli://longbridge', relevance: 'us-stock',
    collected_at: new Date().toISOString().slice(0,16), collector: 'collect-longbridge',
    priority: 'TBD', assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified'
  };
  const fm = frontmatter(meta);
  const keyList = keyData.map(k => '  - "' + k + '"').join('\n');
  const md = fm + '\n\nkey_data:\n' + keyList + '\n\n## 概要\n\nlongbridge CLI で取得した一次データ。\n\n## データ表\n\n| 指標 | 値 | 変動 | 備考 |\n|------|----|------|------|\n' + lines.join('\n') + '\n';
  fs.writeFileSync(path.join(OUT, '01-market.md'), md, 'utf8');
  console.log('longbridge: 01-market.md 生成 (指数' + (idx?idx.length:0) + '/株' + (stk?stk.length:0) + '/為替/温度)');
  console.log(keyData.join(' | '));
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });
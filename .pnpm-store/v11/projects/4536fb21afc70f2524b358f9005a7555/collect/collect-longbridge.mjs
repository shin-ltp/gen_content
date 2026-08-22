// collect-longbridge.mjs — longbridge CLI 一次数据收集（指数/个股/汇率/市场温度）
import fs from 'node:fs';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { frontmatter, atomicWrite } from './collect-utils.mjs';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const LB = path.join(PROJECT, 'tools', 'bin', 'longbridge.exe');
const OUT = process.env.LB_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });

// .env の Longbridge API key を読み込む（あれば spawn 時に環境変数として注入。
// これで Windows profile を持たないサンドボックスユーザーでも OAuth の
// home ディレクトリ解決に依存せずに認証できる）
function loadEnv() {
  const envPath = path.join(PROJECT, '.env');
  const env = {};
  if (fs.existsSync(envPath)) {
    for (const line of fs.readFileSync(envPath, 'utf8').split('\n')) {
      const m = line.match(/^([A-Z_]+)=(.*)$/);
      if (m) env[m[1]] = m[2].trim();
    }
  }
  return env;
}
const ENV = loadEnv();
const LB_API = {
  key: ENV.LONGBRIDGE_APP_KEY || '',
  secret: ENV.LONGBRIDGE_APP_SECRET || '',
  token: ENV.LONGBRIDGE_ACCESS_TOKEN || ''
};
const LB_API_CONFIGURED = !!(LB_API.key && LB_API.secret && LB_API.token);

const INDICES = ['.SPX.US', '.DJI.US', '.IXIC.US', '.VIX.US'];
const STOCKS = (process.env.LB_STOCKS || 'NVDA.US,AMD.US,PLTR.US,QCOM.US,MSFT.US,AAPL.US,TSLA.US,META.US,AMZN.US,GOOGL.US').split(',');

function lbJSON(args) {
  try {
    const env = { ...process.env };
    // API key があれば環境変数で注入（OAuth token より優先される）
    if (LB_API.key && LB_API.secret && LB_API.token) {
      env.LONGBRIDGE_APP_KEY = LB_API.key;
      env.LONGBRIDGE_APP_SECRET = LB_API.secret;
      env.LONGBRIDGE_ACCESS_TOKEN = LB_API.token;
    }
    const r = spawnSync(LB, [...args, '--format', 'json'], { encoding: 'utf8', timeout: 30000, env });
    if (r.status !== 0) {
      const msg = String(r.stderr || r.stdout || '').trim();
      console.error('[lb-err] ' + args.join(' ') + ': ' + msg.slice(0, 160));
      if (/Authentication failed|Failed to get home directory|Failed to decrypt auth token|token invalid|invalid|auth|token|login/i.test(msg)) {
        console.error('[longbridge] 認証エラーの可能性 (API key 設定: ' + (LB_API_CONFIGURED ? 'あり' : 'なし') + ')');
        if (!LB_API_CONFIGURED) process.exitCode = 3;
      }
      return null;
    }
    const parsed = JSON.parse(r.stdout);
    if (Array.isArray(parsed) && parsed.length === 0) { console.error('[lb-warn] ' + args.join(' ') + ': empty array'); return null; }
    return parsed;
  } catch (e) {
    console.error('[lb-err] ' + args.join(' ') + ': ' + String(e.message || e).slice(0, 120));
    return null;
  }
}

// 金額・株価として明らかに不正な値を弾く（longbridge が認証切れ・エラー時に 0 や null を返すケースがある）
function rejectBadQuote(q) {
  if (!q || !q.symbol) return true;
  const last = Number(q.last);
  if (isNaN(last) || last <= 0) return true;
  if (q.change_percentage !== undefined && isNaN(Number(q.change_percentage))) return true;
  return false;
}

function pct(v) {
  const n = Number(v);
  return isNaN(n) ? '' : (n >= 0 ? '+' : '') + n + '%';
}

function fmt(n) {
  const x = Number(n);
  return isNaN(x) ? '—' : x.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

// 最低限の健全性チェック: 有効な指数行が存在し、かつ key_data が空でないこと
function sanityCheck(lines, keyData) {
  const hasIndex = lines.some(l => /^\|\s*(S&P500|ダウ|ナスダック|VIX)/.test(l));
  if (!hasIndex) {
    console.error('[longbridge] 健全性チェック失敗: 指数行なし');
    return false;
  }
  if (!keyData.length) {
    console.error('[longbridge] 健全性チェック失敗: key_data が空');
    return false;
  }
  return true;
}

async function run() {
  const previous = path.join(OUT, '01-market.md');
  if (fs.existsSync(previous)) {
    // 既存ファイルのバックアップとして残す（前回値の比較・復旧用）。上書き失敗は致命的ではない
    try { fs.copyFileSync(previous, path.join(OUT, '01-market.last.md')); } catch (e) { console.warn('[longbridge] バックアップ作成失敗: ' + e.message); }
  }
  const today = new Date().toISOString().slice(0,10);
  const lines = [];
  const keyData = [];
  let successCount = 0;

  // 1. 指数
  const idx = lbJSON(['quote', ...INDICES]);
  if (idx && Array.isArray(idx)) {
    successCount++;
    for (const q of idx) {
      if (rejectBadQuote(q)) continue;
      const name = {'.SPX.US':'S&P500','.DJI.US':'ダウ','.IXIC.US':'ナスダック','.VIX.US':'VIX'}[q.symbol] || q.symbol;
      lines.push('| ' + name + ' | ' + fmt(q.last) + ' | ' + pct(q.change_percentage) + ' |');
      keyData.push(name + ' ' + fmt(q.last) + '（' + pct(q.change_percentage) + '）');
    }
    if (!lines.some(l => l.startsWith('| S&P'))) {
      console.error('[longbridge] 指数に有効値なし（S&P欠落）');
      successCount--;
    }
  }
  // 2. 个股
  const stk = lbJSON(['quote', ...STOCKS]);
  if (stk && Array.isArray(stk)) {
    successCount++;
    for (const q of stk) {
      if (rejectBadQuote(q)) continue;
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
    if (process.exitCode === 3) {
      console.error('[longbridge] 認証未設定として SKIP (exit 3)');
      process.exit(3);
    }
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
    priority: 'TBD', assets_needed: '[]', assets_status: 'none', adopted: false, status: 'verified',
    pub_date: today
  };
  const fm = frontmatter(meta);
  const keyList = keyData.map(k => '  - "' + k + '"').join('\n');
  if (!sanityCheck(lines, keyData)) { process.exit(1); }
  const md = fm + '\n\nkey_data:\n' + keyList + '\n\n## 概要\n\nlongbridge CLI で取得した一次データ。\n\n## データ表\n\n| 指標 | 値 | 変動 | 備考 |\n|------|----|------|------|\n' + lines.join('\n') + '\n';
  atomicWrite(path.join(OUT, '01-market.md'), md);
  console.log('longbridge: 01-market.md 生成 (指数' + (idx?idx.length:0) + '/株' + (stk?stk.length:0) + '/為替/温度)');
  console.log(keyData.join(' | '));
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

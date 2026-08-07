// collect-all.mjs — 全收集器のメインディスパッチャー + manifest 自動生成
// 使用方法: node collect-all.mjs [--date YYYY-MM-DD] [--skip email,36kr] [--headed]
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const COLLECT_DIR = path.dirname(new URL(import.meta.url).pathname.replace(/^\//,''));
const NODE = process.execPath;

const args = process.argv.slice(2);
const dateIdx = args.indexOf('--date');
const TODAY = dateIdx >= 0 && args[dateIdx + 1] ? args[dateIdx + 1] : new Date().toISOString().slice(0, 10);
const skipIdx = args.indexOf('--skip');
const SKIP = skipIdx >= 0 && args[skipIdx + 1] ? args[skipIdx + 1].split(',') : [];
const HEADED = args.includes('--headed');

const DAY_DIR = path.join(PROJECT, 'daily-output', TODAY);
const COLLECTION_DIR = path.join(DAY_DIR, 'collection');
const ASSETS_DIR = path.join(DAY_DIR, 'assets');
const PRODUCTION_DIR = path.join(DAY_DIR, 'production');
const REVIEW_DIR = path.join(DAY_DIR, 'review');

for (const d of [COLLECTION_DIR, ASSETS_DIR, PRODUCTION_DIR, REVIEW_DIR]) {
  fs.mkdirSync(d, { recursive: true });
}

const statusPath = path.join(DAY_DIR, 'status.md');
if (!fs.existsSync(statusPath)) {
  const initStatus = '# ' + TODAY + ' \u53CE\u96C6\u72B6\u614B\n\n| Phase | \u72B6\u614B | \u5099\u8003 |\n|-------|------|------|\n| Phase 0 \u53CE\u96C6 | \uD83D\uDEA7 \u9032\u884C\u4E2D | |\n';
  fs.writeFileSync(statusPath, initStatus, 'utf8');
}

const COLLECTORS = [
  { name: 'longbridge', script: 'collect-longbridge.mjs', env: { LB_OUT: COLLECTION_DIR }, label: '\u5E02\u5834\u30C7\u30FC\u30BF\uFF08Longbridge\uFF09' },
  { name: 'rss', script: 'collect-rss.mjs', env: { RSS_OUT: COLLECTION_DIR }, label: 'CNBC/Reuters RSS' },
  { name: 'wscn', script: 'collect-wscn.mjs', env: { WSCN_OUT: COLLECTION_DIR }, label: '\u534E\u5C14\u8857\u89C1\u95FB' },
  { name: '36kr', script: 'collect-36kr.mjs', env: { KR36_OUT: COLLECTION_DIR }, label: '36\u6C2A' },
  { name: 'insights', script: 'collect-insights.mjs', env: { INSIGHTS_OUT: COLLECTION_DIR }, label: 'GS/MS/JPM Insights' },
  { name: 'email', script: 'collect-email.mjs', env: { EMAIL_OUT: COLLECTION_DIR }, label: 'Gmail \u6668\u5831' }
];

function runCollector(collector) {
  return new Promise((resolve) => {
    if (SKIP.includes(collector.name)) {
      console.log('\n>>> SKIP: ' + collector.name);
      resolve({ name: collector.name, ok: true, skipped: true, count: 0 });
      return;
    }
    console.log('\n========================================');
    console.log('>>> START: ' + collector.label + ' (' + collector.script + ')');
    console.log('========================================');
    const scriptPath = path.join(COLLECT_DIR, collector.script);
    if (!fs.existsSync(scriptPath)) {
      console.error('[collect-all] \u30B9\u30AF\u30EA\u30D7\u30C8\u306A\u3057: ' + scriptPath);
      resolve({ name: collector.name, ok: false, count: 0 });
      return;
    }
    const env = { ...process.env, ...collector.env, NODE_PATH: (process.env.NODE_PATH || '') + ';C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules' };
    const childArgs = [scriptPath];
    if (HEADED) childArgs.push('--headed');
    // 收集器開始前のファイル数をスナップショット
    const before = new Set(fs.existsSync(COLLECTION_DIR) ? fs.readdirSync(COLLECTION_DIR).filter(f => f.endsWith('.md') && f !== '00-manifest.md') : []);
    const child = spawn(NODE, childArgs, { env, cwd: COLLECT_DIR, stdio: 'inherit', timeout: 180000 });
    child.on('close', (code) => {
      const after = fs.existsSync(COLLECTION_DIR) ? fs.readdirSync(COLLECTION_DIR).filter(f => f.endsWith('.md') && f !== '00-manifest.md') : [];
      const newCount = after.filter(f => !before.has(f)).length;
      const ok = code === 0 || newCount > 0;  // stderr output causes exit code 1, treat as OK if files were produced
      console.log('>>> ' + (ok ? 'OK' : 'FAIL') + ': ' + collector.name + ' (new=' + newCount + ' / total=' + after.length + ')');
      resolve({ name: collector.name, ok, count: newCount });
    });
    child.on('error', (e) => {
      console.error('[collect-all] ' + collector.name + ' \u8D77\u52D5\u30A8\u30E9\u30FC: ' + e.message);
      resolve({ name: collector.name, ok: false, count: 0 });
    });
  });
}

function generateManifest(results) {
  const files = fs.readdirSync(COLLECTION_DIR).filter(f => f.endsWith('.md') && f !== '00-manifest.md');
  const entries = [];
  const catCounts = { MKT: 0, MAC: 0, RES: 0, STK: 0, ERN: 0, NWS: 0 };

  for (const f of files) {
    const content = fs.readFileSync(path.join(COLLECTION_DIR, f), 'utf8');
    const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
    if (!fmMatch) continue;
    const fm = {};
    for (const line of fmMatch[1].split('\n')) {
      const m = line.match(/^(\w+):\s*(.*)$/);
      if (m) fm[m[1]] = m[2].replace(/^"(.*)"$/, '$1');
    }
    const id = fm.id || f.replace('.md', '');
    const cat = fm.category || 'unknown';
    const ticker = fm.ticker || '\u2014';
    const title = (fm.title || f).slice(0, 60);
    const source = fm.source || '';
    const sourceType = fm.source_type || '';
    const priority = fm.priority || 'TBD';
    const assetsNeeded = fm.assets_needed || '[]';
    const assets = assetsNeeded === '[]' ? 'no' : 'yes';
    const status = fm.status || 'raw';
        // category field-first classification
    const catMap = { market: 'MKT', macro: 'MAC', research: 'RES', stocks: 'STK', earnings: 'ERN', news: 'NWS' };
    const catKey = catMap[cat] || (id.startsWith('RSS') ? 'NWS' : id.split('-')[0]);
    if (catCounts[catKey] !== undefined) catCounts[catKey]++;
    entries.push({ id, cat, ticker, title, source, sourceType, priority, assets, status });
  }

  const total = entries.length;
  const catSummary = Object.entries(catCounts).filter(([,v]) => v > 0).map(([k,v]) => k + ':' + v).join(' / ');
  const now = new Date().toISOString().slice(0, 16);

  let md = '# ' + TODAY + ' \u53CE\u96C6\u7D20\u6750\u30DE\u30B9\u30BF\u30FC\u7D22\u5F15\n\n';
  md += '> \u53CE\u96C6\u30A8\u30FC\u30B8\u30A7\u30F3\u30C8: collect-all (auto) | \u53CE\u96C6\u65E5\u6642: ' + now + '\n';
  md += '> \u5408\u8A08: ' + total + ' \u4EF6\uFF08' + catSummary + '\uFF09\n';
  md += '> \u6536\u96C6\u5668\u7D50\u679C: ' + results.map(r => r.name + '=' + (r.skipped ? 'SKIP' : r.ok ? 'OK' : 'FAIL') + '(' + r.count + ')').join(' / ') + '\n\n';
  md += '## \u7D22\u5F15\n';
  md += '| ID | \u30AB\u30C6\u30B4\u30EA | \u682A\u512A | \u30BF\u30A4\u30C8\u30EB | \u60C5\u5831\u6E90 | \u30BF\u30A4\u30D7 | \u512A\u5148\u5EA6 | \u753B\u50CF\u8981 | \u72B6\u614B |\n';
  md += '|----|----------|------|----------|--------|--------|--------|--------|------|\n';
  for (const e of entries) {
    md += '| ' + e.id + ' | ' + e.cat + ' | ' + e.ticker + ' | ' + e.title + ' | ' + e.source + ' | ' + e.sourceType + ' | ' + e.priority + ' | ' + e.assets + ' | ' + e.status + ' |\n';
  }
  md += '\n## \u53CE\u96C6\u30AB\u30D0\u30EC\u30C3\u30B8\uFF08Gate #0 \u7528\uFF09\n';
  const covChecks = [
    { label: '\u5E02\u5834\u30C7\u30FC\u30BF\uFF08\u6307\u6570\u30FB\u70BA\u66FF\u30FB\u50B5\u5238\u30FB\u5FC3\u7406\uFF09', ok: catCounts.MKT > 0 },
    { label: '\u30DE\u30AF\u30ED\uFF08\u7D4C\u6E08\u30AB\u30EC\u30F3\u30C0\u30FC\u306E\u5F53\u65E5\u30A4\u30D9\u30F3\u30C8\uFF09', ok: catCounts.MAC > 0 },
    { label: '\u5927\u624B\u30EA\u30B5\u30FC\u30C1\uFF08GS/MS/JPM \u7B49\uFF09', ok: catCounts.RES > 0 },
    { label: '\u500B\u5225\u682A\u30FB\u30BB\u30AF\u30BF\u30FC', ok: catCounts.STK > 0 },
    { label: '\u6C7A\u7B97\uFF08\u30B7\u30FC\u30BA\u30F3\u4E2D\uFF09', ok: catCounts.ERN > 0, optional: true },
    { label: '\u30CB\u30E5\u30FC\u30B9\u901F\u5831', ok: catCounts.NWS > 0 }
  ];
  for (const c of covChecks) {
    const mark = c.ok ? '[x]' : (c.optional ? '[ ] (\u975E\u5FC5\u9808)' : '[ ]');
    md += '- ' + mark + ' ' + c.label + '\n';
  }

  const manifestPath = path.join(COLLECTION_DIR, '00-manifest.md');
  fs.writeFileSync(manifestPath, md, 'utf8');
  console.log('\n=== manifest \u751F\u6210: ' + total + ' \u4EF6 -> ' + manifestPath + ' ===');
  return { total, catCounts };
}

function updateStatus(results, manifest) {
  const lines = [];
  lines.push('# ' + TODAY + ' \u53CE\u96C6\u72B6\u614B\n');
  lines.push('| Phase | \u72B6\u614B | \u5099\u8003 |');
  lines.push('|-------|------|------|');
  const allOk = results.every(r => r.ok || r.skipped);
  const status = allOk ? '\u2705 \u5B8C\u4E86' : '\uD83D\uDEA7 \u4E00\u90E8\u5931\u6557';
  lines.push('| Phase 0 \u53CE\u96C6 | ' + status + ' | \u5408\u8A08 ' + manifest.total + ' \u4EF6 |');
  for (const r of results) {
    const mark = r.skipped ? '\u23ED SKIP' : r.ok ? '\u2705' : '\u274C';
    lines.push('| \u2192 ' + r.name + ' | ' + mark + ' | ' + r.count + ' \u30D5\u30A1\u30A4\u30EB |');
  }
  lines.push('\n## Gate #0 \u7C21\u6613\u30C1\u30A7\u30C3\u30AF\n');
  lines.push('- \u7D20\u6750\u6570: ' + manifest.total + ' (\u76EE\u6A19\u226530) \u2192 ' + (manifest.total >= 30 ? '\u2705' : '\u26A0\uFE0F \u4E0D\u8DB3'));
  lines.push('- \u30AB\u30C6\u30B4\u30EA: ' + Object.entries(manifest.catCounts).filter(([,v]) => v > 0).map(([k]) => k).join(', '));
  lines.push('- \u7D22\u5F15\u6574\u5408: \u2705');
  fs.writeFileSync(statusPath, lines.join('\n') + '\n', 'utf8');
}

async function main() {
  console.log('===================================');
  console.log(' collect-all \u2014 ' + TODAY);
  console.log(' \u51FA\u529B: ' + COLLECTION_DIR);
  console.log(' skip: ' + (SKIP.length ? SKIP.join(',') : '(\u306A\u3057)'));
  console.log('===================================\n');
  const results = [];
  for (const col of COLLECTORS) {
    const result = await runCollector(col);
    results.push(result);
  }
  const manifest = generateManifest(results);
  updateStatus(results, manifest);
  console.log('\n===================================');
  console.log(' collect-all \u5B8C\u4E86');
  console.log(' \u5408\u8A08: ' + manifest.total + ' \u4EF6');
  console.log(' \u51FA\u529B: ' + DAY_DIR);
  console.log('===================================');
}
main().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });
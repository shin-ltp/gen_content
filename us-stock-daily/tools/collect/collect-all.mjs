// collect-all.mjs — 全收集器のメインディスパッチャー + manifest 自動生成 + Gate #0 厳格評価
// 使用方法: node collect-all.mjs [--date YYYY-MM-DD] [--skip email,36kr] [--headed] [--no-gate]
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { parseFrontmatter, bodyLength, atomicWrite } from './collect-utils.mjs';
import { scanCollection as verifyScan, evaluate as verifyEvaluate } from './verify-collection.mjs';
import { sendFailureNotification } from './notify-email.mjs';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const COLLECT_DIR = path.dirname(new URL(import.meta.url).pathname.replace(/^\//,''));
const NODE = process.execPath;

const args = process.argv.slice(2);
const dateIdx = args.indexOf('--date');
const TODAY = dateIdx >= 0 && args[dateIdx + 1] ? args[dateIdx + 1] : new Date().toISOString().slice(0, 10);
const skipIdx = args.indexOf('--skip');
const SKIP = skipIdx >= 0 && args[skipIdx + 1] ? args[skipIdx + 1].split(',') : [];
const HEADED = args.includes('--headed');
const NO_GATE = args.includes('--no-gate');

// 出力ルートは環境変数で差し替え可能（オフライン検証・テスト用。既定は daily-output/）
const OUTPUT_ROOT = process.env.COLLECT_ALL_OUT || path.join(PROJECT, 'daily-output');
const DAY_DIR = path.join(OUTPUT_ROOT, TODAY);
const COLLECTION_DIR = path.join(DAY_DIR, 'collection');
const ASSETS_DIR = path.join(DAY_DIR, 'assets');
const PRODUCTION_DIR = path.join(DAY_DIR, 'production');
const REVIEW_DIR = path.join(DAY_DIR, 'review');

for (const d of [COLLECTION_DIR, ASSETS_DIR, PRODUCTION_DIR, REVIEW_DIR]) {
  fs.mkdirSync(d, { recursive: true });
}

const statusPath = path.join(DAY_DIR, 'status.md');
if (!fs.existsSync(statusPath)) {
  atomicWrite(statusPath, '# ' + TODAY + ' \u53CE\u96C6\u72B6\u614B\n\n| Phase | \u72B6\u614B | \u5099\u8003 |\n|-------|------|------|\n| Phase 0 \u53CE\u96C6 | \uD83D\uDEA7 \u9032\u884C\u4E2D | |\n');
}

const COLLECTORS = [
  { name: 'longbridge', script: 'collect-longbridge.mjs', env: { LB_OUT: COLLECTION_DIR }, label: '\u5E02\u5834\u30C7\u30FC\u30BF\uFF08Longbridge\uFF09', maxMs: 120000 },
  { name: 'market', script: 'collect-market.mjs', env: { MARKET_OUT: COLLECTION_DIR }, label: '\u5E02\u5834\u30B9\u30CA\u30C3\u30D7\uFF08Yahoo\u3001\u8A8D\u8A3C\u4E0D\u8981\uFF09', maxMs: 180000 },
  { name: 'rss', script: 'collect-rss.mjs', env: { RSS_OUT: COLLECTION_DIR }, label: 'CNBC/Reuters RSS', maxMs: 240000 },
  { name: 'wscn', script: 'collect-wscn.mjs', env: { WSCN_OUT: COLLECTION_DIR }, label: '\u534E\u5C14\u8857\u89C1\u95FB', maxMs: 600000 },
  { name: '36kr', script: 'collect-36kr.mjs', env: { KR36_OUT: COLLECTION_DIR }, label: '36\u6C2A', maxMs: 900000 },
  { name: 'insights', script: 'collect-insights.mjs', env: { INSIGHTS_OUT: COLLECTION_DIR }, label: 'GS/MS/JPM Insights', maxMs: 900000 },
  { name: 'email', script: 'collect-email-imap.mjs', env: { EMAIL_OUT: COLLECTION_DIR }, label: 'Gmail \u6668\u5831 (IMAP)', maxMs: 300000 }
];

function listMaterialFiles(dir) {
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir).filter(f => f.endsWith('.md') && f !== '00-manifest.md');
}

function runCollector(collector) {
  return new Promise((resolve) => {
    if (SKIP.includes(collector.name)) {
      console.log('\n>>> SKIP: ' + collector.name);
      resolve({ name: collector.name, ok: true, skipped: true, count: 0, code: null, msg: 'user-skip' });
      return;
    }
    console.log('\n========================================');
    console.log('>>> START: ' + collector.label + ' (' + collector.script + ')');
    console.log('========================================');
    const scriptPath = path.join(COLLECT_DIR, collector.script);
    if (!fs.existsSync(scriptPath)) {
      console.error('[collect-all] \u30B9\u30AF\u30EA\u30D7\u30C8\u306A\u3057: ' + scriptPath);
      resolve({ name: collector.name, ok: false, count: 0, code: null, msg: 'script missing' });
      return;
    }
    const env = { ...process.env, ...collector.env, NODE_PATH: (process.env.NODE_PATH || '') + ';C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules' };
    // \u30b5\u30f3\u30c9\u30dc\u30c3\u30af\u30b9 Node \u306e TLS \u306f\u30b7\u30b9\u30c6\u30e0CA\u3092\u4f7f\u308f\u306a\u3044\u3068
    // Gmail \u7b49\u306e\u8a3c\u660e\u66f8\u3092\u691c\u8a3c\u3067\u304d\u306a\u3044\u305f\u3081\u3001\u5168\u5b50\u30d7\u30ed\u30bb\u30b9\u306b --use-system-ca \u3092\u4ed8\u4e0e\u3059\u308b
    const childArgs = ['--use-system-ca', scriptPath];
    if (HEADED) childArgs.push('--headed');
    const before = new Set(listMaterialFiles(COLLECTION_DIR));
    const child = spawn(NODE, childArgs, { env, cwd: COLLECT_DIR, stdio: 'inherit' });
    let settled = false;
    const killTimer = setTimeout(() => {
      if (settled) return;
      settled = true;
      console.error('>>> TIMEOUT: ' + collector.name + ' (' + collector.maxMs + 'ms) -> kill');
      child.kill('SIGKILL');
      resolve({ name: collector.name, ok: false, count: 0, code: null, msg: 'timeout' });
    }, collector.maxMs);
    child.on('close', (code) => {
      if (settled) return;
      settled = true;
      clearTimeout(killTimer);
      const after = listMaterialFiles(COLLECTION_DIR);
      const newFiles = after.filter(f => !before.has(f));
      const newCount = newFiles.length;
      // exit 3 = 設定・認証不足による明示的スキップ（失敗ではなく欠番扱い）
      if (code === 3) {
        console.log('>>> SKIP: ' + collector.name + ' (exit 3: 設定/認証不足)');
        resolve({ name: collector.name, ok: true, skipped: true, count: 0, code, msg: 'config-skip' });
        return;
      }
      const ok = code === 0 && (newCount > 0 || after.length > 0);
      console.log('>>> ' + (ok ? 'OK' : 'FAIL') + ': ' + collector.name + ' (code=' + code + ' new=' + newCount + ' / total=' + after.length + ')');
      resolve({ name: collector.name, ok, count: newCount, code, msg: code === 0 ? 'ok' : 'exit ' + code });
    });
    child.on('error', (e) => {
      if (settled) return;
      settled = true;
      clearTimeout(killTimer);
      console.error('[collect-all] ' + collector.name + ' \u8D77\u52D5\u30A8\u30E9\u30FC: ' + e.message);
      resolve({ name: collector.name, ok: false, count: 0, code: null, msg: e.message });
    });
  });
}

// --- 素材プロファイル収集（manifest および Gate #0 の両方で利用） ---
function scanMaterials() {
  const files = listMaterialFiles(COLLECTION_DIR).sort();
  const entries = [];
  const bad = [];
  for (const f of files) {
    const p = path.join(COLLECTION_DIR, f);
    const content = fs.readFileSync(p, 'utf8');
    const fm = parseFrontmatter(content);
    const id = (fm && fm.id) || f.replace('.md', '');
    const catRaw = (fm && fm.category) || '';
    const catMap = { market: 'MKT', macro: 'MAC', research: 'RES', stocks: 'STK', earnings: 'ERN', news: 'NWS' };
    const catKey = catMap[catRaw] || (String(id).startsWith('RSS') ? 'NWS' : String(id).split('-')[0]);
    const blen = bodyLength(content);
    const hasUrl = !!(fm && fm.url);
    const e = {
      file: f, id, catRaw, catKey,
      title: (fm && fm.title || f).slice(0, 60),
      ticker: (fm && fm.ticker) || '\u2014',
      source: (fm && fm.source) || '',
      sourceType: (fm && fm.source_type) || '',
      priority: (fm && fm.priority) || 'TBD',
      assets: (!fm || fm.assets_needed === '[]' || !fm.assets_needed) ? 'no' : 'yes',
      status: (fm && fm.status) || 'raw',
      bodyLen: blen,
      hasUrl
    };
    if (!fm || !fm.id || !catRaw) bad.push({ file: f, reason: !fm ? 'frontmatter missing' : 'id/category missing' });
    entries.push(e);
  }
  return { entries, bad };
}

// --- Gate #0 評価（コンテンツ品質のみで判定。チャネル健全性は警告・通知扱い） ---
function evaluateGate(scan, results, issues) {
  const counts = { MKT: 0, MAC: 0, RES: 0, STK: 0, ERN: 0, NWS: 0 };
  for (const e of scan.entries) if (counts[e.catKey] !== undefined) counts[e.catKey]++;
  const checks = [];
  const add = (name, pass, detail, critical) => checks.push({ name, pass, detail, critical });

  add('カテゴリカバレッジ（6種）',
    counts.MKT > 0 && counts.MAC > 0 && counts.RES > 0 && counts.STK > 0 && counts.ERN > 0 && counts.NWS > 0,
    'MKT=' + counts.MKT + ' MAC=' + counts.MAC + ' RES=' + counts.RES + ' STK=' + counts.STK + ' ERN=' + counts.ERN + ' NWS=' + counts.NWS);
  const minCount = Number(process.env.GATE0_MIN || '30');
  add('素材数（基準≥' + minCount + '）', scan.entries.length >= minCount, 'total=' + scan.entries.length);
  add('全素材URL完備',
    scan.entries.every(e => e.hasUrl && !/^cli:|^file:|^gmail:/.test(e.url)),
    'url欠落=' + scan.entries.filter(e => !e.hasUrl).length + ' / 擬似URL=' + scan.entries.filter(e => e.hasUrl && /^cli:|^file:|^gmail:/.test(e.url)).map(e => e.id).join(','));
  add('全素材body非空', scan.entries.every(e => e.bodyLen > 0), 'body空=' + scan.entries.filter(e => e.bodyLen === 0).length);
  add('長文密度（≥500字が過半）',
    scan.entries.filter(e => e.bodyLen >= 500).length >= Math.floor(scan.entries.length * 0.5),
    '≥500字=' + scan.entries.filter(e => e.bodyLen >= 500).length + '/' + scan.entries.length);
  add('記録外ファイルなし', scan.bad.length === 0, '不正=' + scan.bad.length + ' ' + scan.bad.map(b => b.file).join(','));
  // 以下は収集プロセスの健康状態。Gate の合格判定には使わず、
  // 失敗時はメール通知と status.md の警告で扱う（2026-08-19 仕様変更）
  const ranAny = results.some(r => !r.skipped);
  add('仕事が1つ以上（警告）',
    !ranAny || results.some(r => !r.skipped && r.ok && r.count > 0),
    results.map(r => r.name + (r.skipped ? '(skip)' : '')).join(','), false);
  const failedSources = results.filter(r => !r.skipped && !r.ok);
  add('収集チャネル健康（通知のみ・合否には影響しない）',
    failedSources.length === 0,
    failedSources.length ? failedSources.map(r => r.name + '(' + r.msg + ')').join(',') : '全OK', false);

  const failed = checks.filter(c => c.critical !== false && !c.pass);
  const warnOnly = checks.filter(c => c.critical === false && !c.pass);
  const pass = failed.length === 0;
  return { pass, checks, failed, warnOnly, counts };
}

function generateManifest(scan, results, gate) {
  const total = scan.entries.length;
  const catSummary = Object.entries(gate.counts).filter(([,v]) => v > 0).map(([k,v]) => k + ':' + v).join(' / ');
  const now = new Date().toISOString().slice(0, 16);
  let md = '# ' + TODAY + ' \u53CE\u96C6\u7D20\u6750\u30DE\u30B9\u30BF\u30FC\u7D22\u5F15\n\n';
  md += '> \u53CE\u96C6\u30A8\u30FC\u30B8\u30A7\u30F3\u30C8: collect-all (auto) | \u53CE\u96C6\u65E5\u6642: ' + now + '\n';
  md += '> \u5408\u8A08: ' + total + ' \u4EF6\uFF08' + catSummary + '\uFF09\n';
  md += '> \u6536\u96C6\u5668\u7D50\u679C: ' + results.map(r => r.name + '=' + (r.skipped ? 'SKIP' : r.ok ? 'OK' : 'FAIL') + '(' + r.count + ')').join(' / ') + '\n\n';
  md += '> Gate #0: ' + (gate.pass ? 'PASS' : '**FAIL**') + ' (不合格項目: ' + (gate.failed.length ? gate.failed.map(c => c.name).join(' / ') : 'なし') + ')\n\n';
  md += '## \u7D22\u5F15\n';
  md += '| ID | \u30AB\u30C6\u30B4\u30EA | \u682A\u512A | \u30BF\u30A4\u30C8\u30EB | \u60C5\u5831\u6E90 | \u30BF\u30A4\u30D7 | \u512A\u5148\u5EA6 | \u753B\u50CF\u8981 | \u72B6\u614B | \u672C\u6587\u9577 |\n';
  md += '|----|----------|------|----------|--------|--------|--------|--------|------|--------|\n';
  for (const e of scan.entries) {
    const t = String(e.title || '').replace(/\r?\n/g, ' ').slice(0, 60);
    md += '| ' + e.id + ' | ' + e.catRaw + ' | ' + e.ticker + ' | ' + t + ' | ' + e.source + ' | ' + e.sourceType + ' | ' + e.priority + ' | ' + e.assets + ' | ' + e.status + ' | ' + e.bodyLen + ' |\n';
  }
  md += '\n## \u53CE\u96C6\u30AB\u30D0\u30EC\u30C3\u30B8\uFF08Gate #0 \u7528\uFF09\n';
  for (const c of gate.checks) {
    md += '- ' + (c.pass ? '[x]' : '[ ]') + ' ' + c.name + ' (' + c.detail + ')\n';
  }
  const manifestPath = path.join(COLLECTION_DIR, '00-manifest.md');
  atomicWrite(manifestPath, md);
  console.log('\n=== manifest \u751F\u6210: ' + total + ' \u4EF6 -> ' + manifestPath + ' ===');
  return total;
}

function updateStatus(results, scan, gate) {
  const missingCats = Object.keys(gate.counts).filter(k => gate.counts[k] === 0);
  const lines = [];
  lines.push('# ' + TODAY + ' \u53CE\u96C6\u72B6\u614B\n');
  lines.push('| Phase | \u72B6\u614B | \u5099\u8003 |');
  lines.push('|-------|------|------|');
  lines.push('| Phase 0 \u53CE\u96C6 | ' + (gate.pass ? '\u2705 \u5B8C\u4E86 (Gate #0 PASS)' : '\u274C Gate #0 FAIL') + ' | \u5408\u8A08 ' + scan.entries.length + ' \u4EF6 |');
  if (!gate.pass) {
    lines.push('| \u2192 \u6B21\u30D5\u30A7\u30FC\u30BA\u3078\u9032\u3081\u306A\u3044 | \u26D4\uFE0F BLOCKED | Gate #0 \u4E0D\u5408\u683C (exit 2) |');
    if (missingCats.length) lines.push('| \u2192 \u4E0D\u8DB3\u30AB\u30C6\u30B4\u30EA | \u26A0\uFE0F | ' + missingCats.join(', ') + ' |');
  }
  for (const r of results) {
    const mark = r.skipped ? '\u23ED SKIP' : r.ok ? '\u2705' : '\u274C';
    lines.push('| \u2192 ' + r.name + ' | ' + mark + ' | ' + r.count + ' \u30D5\u30A1\u30A4\u30EB (' + r.msg + ') |');
  }
  lines.push('\n## Gate #0 \u8A55\u4FA1\n');
  for (const c of gate.checks) {
    lines.push('- ' + (c.pass ? '[\u2713]' : '[ ]') + ' ' + c.name + ' \u2014 ' + c.detail);
  }
  for (const c of gate.warnOnly) lines.push('- \u26A0\uFE0F \u8B66\u544A: ' + c.name + ' \u2014 ' + c.detail);
  atomicWrite(statusPath, lines.join('\n') + '\n');
}

async function main() {
  console.log('===================================');
  console.log(' collect-all \u2014 ' + TODAY);
  console.log(' \u51FA\u529B: ' + COLLECTION_DIR);
  console.log(' skip: ' + (SKIP.length ? SKIP.join(',') : '(\u306A\u3057)') + ' | gate: ' + (NO_GATE ? 'OFF' : 'ON'));
  console.log('===================================\n');
  const results = [];
  for (const col of COLLECTORS) {
    const result = await runCollector(col);
    results.push(result);
  }
  const scan = scanMaterials();
  const gate = evaluateGate(scan, results, []);
  generateManifest(scan, results, gate);
  updateStatus(results, scan, gate);
  const fsScan = verifyScan(COLLECTION_DIR);
  const fsGate = verifyEvaluate(fsScan, { min: Number(process.env.GATE0_MIN || '30'), dir: COLLECTION_DIR });
  const fsText = fsGate.pass
    ? '[x] 独立再評価 (verify-collection): PASS'
    : '[ ] 独立再評価 (verify-collection): FAIL — ' + fsGate.failed.map(c => c.name).join(' / ');
  console.log('\n=== Gate #0 独立再評価 ===');
  console.log(fsText);
  try {
    const st = '\n\n## Gate #0 独立再評価（ファイルシステム実体）\n\n- ' + fsText + '\n';
    fs.appendFileSync(statusPath, st, 'utf8');
  } catch (e) { console.error('[collect-all] status.md 追記失敗: ' + e.message); }
  const combinedPass = gate.pass && fsGate.pass;
  const failedCollectors = results.filter(r => !r.skipped && !r.ok);
  const notifyReasons = [];
  if (failedCollectors.length > 0) {
    notifyReasons.push('信源取得失敗: ' + failedCollectors.map(r => r.name + ' (' + r.msg + ')').join(', '));
  }
  if (!combinedPass) {
    notifyReasons.push('Gate #0 内容判定不合格: ' + [...gate.failed, ...fsGate.failed].map(c => c.name).join(' / '));
  }
  console.log('\n===================================');
  console.log(' collect-all \u5B8C\u4E86');
  console.log(' \u5408\u8A08: ' + scan.entries.length + ' \u4EF6 | Gate #0: ' + (combinedPass ? 'PASS' : 'FAIL'));
  if (!combinedPass) console.log(' \u6B21\u30D5\u30A7\u30FC\u30BA\u3078\u9032\u3081\u306A\u3044: Gate #0 \u4E0D\u5408\u683C\u9805\u76EE\u3092\u89E3\u6D88\u3057\u3066\u518D\u5B9F\u884C\u3059\u308B\u3053\u3068');
  console.log(' \u51FA\u529B: ' + DAY_DIR);
  console.log('===================================');
  if (notifyReasons.length > 0) {
    const subject = '[us-stock-daily] 收集异常通知 ' + TODAY;
    const body = [
      '检测到以下问题，请检查收集流程：',
      '',
      ...notifyReasons.map(r => '- ' + r),
      '',
      '素材统计: ' + JSON.stringify(gate.counts) + ' total=' + scan.entries.length,
      'Gate #0: ' + (combinedPass ? 'PASS' : 'FAIL'),
      '输出目录: ' + DAY_DIR,
      '状态文件: ' + statusPath
    ].join('\n');
    try {
      const r = await sendFailureNotification({ subject, text: body });
      console.log('[notify] 已发送告警邮件 -> ' + r.to);
      try {
        fs.appendFileSync(statusPath, '\n\n## 异常通知\n\n- 已发送邮件: ' + r.to + '（' + r.messageId + '）\n- 事由:\n' + notifyReasons.map(x => '  - ' + x).join('\n') + '\n', 'utf8');
      } catch {}
    } catch (e) {
      console.error('[notify] 告警邮件发送失败: ' + e.message);
      try {
        fs.appendFileSync(statusPath, '\n\n## 异常通知\n\n- 邮件发送失败: ' + e.message + '\n- 事由:\n' + notifyReasons.map(x => '  - ' + x).join('\n') + '\n', 'utf8');
      } catch {}
    }
  }
  if (NO_GATE) {
    console.log('[collect-all] --no-gate: Gate #0 \u8A18\u9332\u306E\u307F\u3001\u30D6\u30ED\u30C3\u30AF\u3057\u307E\u305B\u3093 (exit 0)');
    process.exitCode = 0;
  } else {
    process.exitCode = combinedPass ? 0 : 2;
  }
}
main().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

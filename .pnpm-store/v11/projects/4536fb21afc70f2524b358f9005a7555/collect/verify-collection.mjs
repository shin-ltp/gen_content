// verify-collection.mjs — 独立の Gate #0 評価器（ファイルシステムだけを信頼して検査）
// 使い方: node verify-collection.mjs --dir <collectionDir> [--min N] [--status <statusPath>] [--no-gate]
// 不合格なら exit 2 を返し、後段 Phase 1 をブロックする。素材の実体を見て評価するため、
// collect-all.mjs のメモリ上の結果と二重に検証できる。
import fs from 'node:fs';
import path from 'node:path';
import { parseFrontmatter, bodyLength } from './collect-utils.mjs';

function parseArgs(argv) {
  const opt = { dir: '', min: Number(process.env.GATE0_MIN || '30'), status: '', noGate: false };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--dir') opt.dir = argv[++i] || '';
    else if (a === '--min') opt.min = Number(argv[++i]) || opt.min;
    else if (a === '--status') opt.status = argv[++i] || '';
    else if (a === '--no-gate') opt.noGate = true;
  }
  return opt;
}

// collection/ 以下を再帰的に走査し、.md 素材ファイルを列挙する（00-manifest.md は索引なので除外）
export function scanCollection(dir) {
  if (!fs.existsSync(dir)) return { files: [], entries: [], bad: [], junk: [] };
  const files = [];
  const junk = [];
  const walk = (d) => {
    for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, ent.name);
      if (ent.isDirectory()) { walk(p); continue; }
      if (/\.(tmp|partial)$/.test(ent.name) || /\.tmp-\d+(-\d+)?$/.test(ent.name) || /^~\$/.test(ent.name)) {
        junk.push(p); continue;
      }
      if (ent.name.endsWith('.md') && ent.name !== '00-manifest.md') files.push(p);
    }
  };
  walk(dir);
  files.sort();
  const entries = [];
  const bad = [];
  for (const p of files) {
    const st = fs.statSync(p);
    const content = fs.readFileSync(p, 'utf8');
    const fm = parseFrontmatter(content);
    const fmRaw = (content.match(/^---\n([\s\S]*?)\n---/) || [,''])[1];
    const urlRaw = (fmRaw.split('\n').find(l => /^url\s*:/.test(l)) || '').replace(/^url\s*:\s*/, '').trim();
    const id = (fm && fm.id) || path.basename(p, '.md');
    const catRaw = (fm && fm.category) || '';
    const catMap = { market: 'MKT', macro: 'MAC', research: 'RES', stocks: 'STK', earnings: 'ERN', news: 'NWS' };
    const catKey = (catRaw && catMap[catRaw]) || (String(id).startsWith('RSS') ? 'NWS' : String(id).split('-')[0]);
    const hasUrl = !!urlRaw;
    entries.push({
      file: path.relative(dir, p).replace(/\\/g, '/'),
      id, catRaw, catKey, title: (fm && fm.title) || '',
      ticker: (fm && fm.ticker) || '', source: (fm && fm.source) || '',
      sourceType: (fm && fm.source_type) || '', priority: (fm && fm.priority) || 'TBD',
      status: (fm && fm.status) || 'raw', size: st.size, url: urlRaw,
      bodyLen: bodyLength(content), hasUrl
    });
    if (!fm || !fm.id || !catRaw) bad.push({ file: path.basename(p), reason: !fm ? 'frontmatter missing' : 'id/category missing' });
  }
  return { files, entries, bad, junk };
}

// ファイルシステムに基づく Gate #0 評価。critical=false の項目は警告・ブロックしない。
export function evaluate(scan, opts = {}) {
  const min = opts.min || 30;
  const requireCats = (process.env.GATE0_REQUIRE_CATS || 'MKT,MAC,RES,STK,ERN,NWS').split(',').map(s => s.trim()).filter(Boolean);
  const counts = { MKT: 0, MAC: 0, RES: 0, STK: 0, ERN: 0, NWS: 0 };
  for (const e of scan.entries) if (counts[e.catKey] !== undefined) counts[e.catKey]++;
  const missingCats = requireCats.filter(c => !counts[c]);
  const checks = [];
  const add = (name, pass, detail, critical = true) => checks.push({ name, pass, detail, critical });

  add('素材ファイルが存在する', scan.entries.length > 0, 'total=' + scan.entries.length);
  add('素材数（基準≥' + min + '）', scan.entries.length >= min, 'total=' + scan.entries.length);
  add('6カテゴリカバレッジ', missingCats.length === 0, 'MKT=' + counts.MKT + ' MAC=' + counts.MAC + ' RES=' + counts.RES + ' STK=' + counts.STK + ' ERN=' + counts.ERN + ' NWS=' + counts.NWS + (missingCats.length ? ' / 不足=' + missingCats.join(',') : ''));
  add('全素材URL完備', scan.entries.every(e => e.hasUrl && !/^cli:|^file:|^gmail:/.test(e.url)), 'url欠落=' + scan.entries.filter(e => !e.hasUrl).length);
  add('全素材body非空', scan.entries.every(e => e.bodyLen > 0), 'body空=' + scan.entries.filter(e => e.bodyLen === 0).length);
  add('長文密度（≥500字が過半）', scan.entries.filter(e => e.bodyLen >= 500).length >= Math.floor(scan.entries.length * 0.5), '≥500字=' + scan.entries.filter(e => e.bodyLen >= 500).length + '/' + scan.entries.length);
  add('0バイトファイルなし', scan.entries.every(e => e.size > 0), '0バイト=' + scan.entries.filter(e => e.size === 0).map(e => e.file).join(','));
  const idDup = {};
  for (const e of scan.entries) idDup[e.id] = (idDup[e.id] || 0) + 1;
  const dupIds = Object.entries(idDup).filter(([, n]) => n > 1).map(([id]) => id);
  add('ID重複なし', dupIds.length === 0, dupIds.length ? '重複ID=' + dupIds.join(',') : '');
  add('フロントマター健全（id/category必須）', scan.bad.length === 0, '不正=' + scan.bad.length + ' ' + scan.bad.map(b => b.file + '(' + b.reason + ')').join(','));

  const manifestPath = path.join(opts.dir || '', '00-manifest.md');
  const hasManifest = fs.existsSync(manifestPath);
  let manifestRows = 0;
  if (hasManifest) {
    const md = fs.readFileSync(manifestPath, 'utf8');
    const lines = md.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i];
      if (!/^\| \S/.test(l)) continue;       // セル先頭が空白でないデータ行のみ
      if (l.includes('|----')) continue;     // セパレータ
      if (/^\| ID \|/.test(l)) continue;     // テーブルヘッダ
      manifestRows++;
    }
  }
  add('索引(00-manifest.md)存在', hasManifest, hasManifest ? '' : 'manifest 未生成');
  add('索引行数＝素材ファイル数', hasManifest && manifestRows === scan.entries.length,
    'manifestRows=' + manifestRows + ' / files=' + scan.entries.length);
  add('一時/junkファイルなし', scan.junk.length === 0, 'junk=' + scan.junk.length, false);

  const failed = checks.filter(c => c.critical && !c.pass);
  const warnOnly = checks.filter(c => !c.critical && !c.pass);
  return { pass: failed.length === 0, checks, failed, warnOnly, counts, missingCats };
}

export function renderText(gate) {
  const L = [];
  L.push('## Gate #0 評価（verify-collection）');
  L.push('');
  L.push(gate.pass ? '**PASS**' : '**FAIL**' + (gate.failed.length ? ' — 不合格: ' + gate.failed.map(c => c.name).join(' / ') : ''));
  L.push('');
  for (const c of gate.checks) L.push('- ' + (c.pass ? '[x]' : '[ ]') + ' ' + c.name + ' (' + c.detail + ')');
  for (const c of gate.warnOnly) L.push('- ⚠ 警告: ' + c.name + ' (' + c.detail + ')');
  return L.join('\n');
}

async function main() {
  const opt = parseArgs(process.argv.slice(2));
  if (!opt.dir || !fs.existsSync(opt.dir)) {
    console.error('FATAL: --dir が存在しない: ' + opt.dir);
    process.exit(2);
  }
  const scan = scanCollection(opt.dir);
  const gate = evaluate(scan, opt);
  const text = renderText(gate);
  console.log('\n=== Gate #0 (verify-collection) ===');
  console.log(text);
  console.log('  カウント: ' + JSON.stringify(gate.counts) + ' total=' + scan.entries.length);
  if (opt.status) {
    try {
      const st = '\n\n' + text + '\n';
      fs.appendFileSync(opt.status, st, 'utf8');
    } catch (e) { console.error('[verify] status.md 追記失敗: ' + e.message); }
  }
  if (gate.pass || opt.noGate) {
    if (opt.noGate) console.log('[verify] --no-gate: 記録のみ・ブロックしない (exit 0)');
    process.exitCode = 0;
  } else {
    console.error('[verify] Gate #0 不合格 → 後段 Phase 1 は開始しない (exit 2)');
    process.exitCode = 2;
  }
}

if (process.argv[1] && path.basename(process.argv[1]).startsWith('verify-collection')) {
  main();
}
export { parseArgs };

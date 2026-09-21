// pipeline.mjs — 一日贯通制作流水线状态机 + 看门狗（v3，2026-09-02）
// 所有子代理围绕 daily-output/<date>/pipeline.json 交接：谁产出谁写状态，编排者轮询 check。
// 用法（仓库根执行）:
//   node us-stock-daily/tools/pipeline/pipeline.mjs init   --date YYYY-MM-DD
//   node ... pipeline.mjs set    --date D --id ITEM --state STATE [--note "..."] [--retry] [--audit]
//   node ... pipeline.mjs set    --date D --id ITEM --state STATE --force # 历史日期补做专用
//   node ... pipeline.mjs set    --date D --id ITEM --state running --repair  # skipped 恢复专用
//   node ... pipeline.mjs get    --date D [--id ITEM]
//   node ... pipeline.mjs status --date D
//   node ... pipeline.mjs check  --date D        # 看门狗：发现 stale/failed → exit 2
//   node ... pipeline.mjs deadlines --date D     # 截止检查点判定（结合当前时刻）
//   node ... pipeline.mjs alive  --date D        # 编排者心跳
//   node ... pipeline.mjs engine --date D --state starting|ready|failed [--note "..."]
//   node ... pipeline.mjs resume --date D        # 断点恢复唯一入口（只读）
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const US_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');

const STATES = ['pending', 'running', 'reviewing', 'done', 'failed', 'skipped'];
// [itemId, stage]。draft-* 由写作方置 done 即代表「TTS 可取件」；tts-* 由 TTS 工置 done。
const ITEM_DEFS = [
  ['collect', 'collect'],
  ['triage', 'triage'],
  ['draft-A', 'write-a'],
  ['draft-C', 'write-cd'], ['draft-D', 'write-cd'],
  ['draft-B1', 'write-b'], ['draft-B2', 'write-b'], ['draft-B3', 'write-b'], ['draft-B4', 'write-b'],
  ['tts-A', 'tts-short'], ['tts-C', 'tts-short'], ['tts-D', 'tts-short'],
  ['tts-B1', 'tts-b'], ['tts-B2', 'tts-b'], ['tts-B3', 'tts-b'], ['tts-B4', 'tts-b'],
  ['visual-assets', 'visual'], ['visual-html', 'visual'],
  ['prerender', 'render'], ['assembly', 'render'],
  ['spotcheck', 'final'], ['publish', 'final'],
];
// 各 stage 在 running/reviewing 状态下的失速阈值（分钟）
const TH = {
  collect: { running: 50 },
  triage: { running: 50 },
  'write-a': { running: 45, reviewing: 25 },
  'write-cd': { running: 60, reviewing: 25 },
  'write-b': { running: 80, reviewing: 30 },
  'tts-short': { running: 55 },
  'tts-b': { running: 105 },
  visual: { running: 90 },
  render: { running: 90 },
  final: { running: 45 },
};
const LIVE = new Set(['running', 'reviewing']);
const JST_OFFSET_MS = 9 * 3600000;
import { spawnSync } from 'node:child_process';
const NOTIFY_SCRIPT = path.join(US_ROOT, 'tools', 'collect', 'notify-email.mjs');

function jstNow() { return new Date(Date.now() + JST_OFFSET_MS); }
function jstDate() { return jstNow().toISOString().slice(0, 10); }
function jstHHMM(d = jstNow()) { return d.toISOString().slice(11, 16); }
function jstMinutes(d = jstNow()) { return d.getUTCHours() * 60 + d.getUTCMinutes(); }

function pipelinePath(date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date || '')) die('--date 需要 YYYY-MM-DD');
  return path.join(US_ROOT, 'daily-output', date, 'pipeline.json');
}
function die(msg) { console.error('[pipeline] ' + msg); process.exit(1); }
function load(date) {
  const p = pipelinePath(date);
  if (!fs.existsSync(p)) die('pipeline.json 不存在，先 init: ' + p);
  return JSON.parse(fs.readFileSync(p, 'utf8').replace(/^\uFEFF/, ''));
}
function save(date, st) {
  const p = pipelinePath(date);
  fs.mkdirSync(path.dirname(p), { recursive: true });
  st.updated = new Date().toISOString();
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(st, null, 2));
  fs.renameSync(tmp, p);
}

function notify(subject, text) {
  if (process.env.PIPELINE_NOTIFY === '0') {
    console.warn('[pipeline] notify suppressed: ' + subject);
    return;
  }
  try {
    const r = spawnSync(process.execPath, ['--use-system-ca', NOTIFY_SCRIPT], {
      input: JSON.stringify({ subject, text }),
      encoding: 'utf8',
      timeout: 30000,
    });
    if (r.status !== 0) throw new Error(r.stderr.trim() || `exit ${r.status}`);
    console.log('[pipeline] notified: ' + subject);
  } catch (e) {
    console.warn('[pipeline] notify failed: ' + e.message);
  }
}

function ensureEvent(st, id, to, note) {
  if (st.events.some(e => e.id === id && e.to === to && e.note === note)) return false;
  st.events.push({ t: new Date().toISOString(), id, from: 'contract', to, retry: false, note });
  if (st.events.length > 300) st.events = st.events.slice(-300);
  return true;
}

function sendContractAlert(st, subject, text, note) {
  const changed = ensureEvent(st, 'contract-alert', 'alert', note);
  if (changed) notify(subject, text);
  return changed;
}

function alertProblems(st, date, problems) {
  // Watchdog alerts are deduped in 30-minute buckets so a stuck item pages
  // once per half hour instead of once per poll.
  const bucket = Math.floor(Date.now() / 1800000);
  let changed = false;
  for (const p of problems) {
    const note = `watchdog:${p.kind}:${p.id}:bucket${bucket}`;
    if (!ensureEvent(st, p.id, 'alert', note)) continue;
    changed = true;
    notify(
      `[pipeline] ${p.kind}: ${p.id} (${date})`,
      JSON.stringify({ date, problem: p }, null, 2),
    );
  }
  if (changed) save(date, st);
}

// Cross-episode duplicate guard: triage may only be accepted as done when the
// curated topic-history ledger covers the previous broadcast day. A gap in the
// ledger makes anchor comparison impossible and is exactly how 9/8 -> 9/9
// Apple re-airing slipped through (2026-09-09). --audit is the explicit,
// logged bypass for repaired history or confirmed-continuation cases.
function collectTopicHistoryRows() {
  const histPath = path.join(US_ROOT, 'db', 'topic-history.md');
  if (!fs.existsSync(histPath)) return [];
  const lines = fs.readFileSync(histPath, 'utf8').replace(/^\uFEFF/, '').split(/\r?\n/);
  const rows = [];
  for (const line of lines) {
    const m = line.match(/^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*B-([1-9])\s*\|/);
    if (m) rows.push({ date: m[1], slot: 'B-' + m[2] });
  }
  return rows;
}

function checkTriagerRegistry(date) {
  const rows = collectTopicHistoryRows();
  const dates = [...new Set(rows.map(r => r.date))].sort().reverse();
  const prior = dates.find(d => d < date);
  if (!prior) return;
  const required = ['B-1', 'B-2', 'B-3', 'B-4'];
  const missing = required.filter(s => !rows.some(r => r.date === prior && r.slot === s));
  if (!missing.length) return;
  console.warn('[pipeline] topic-history が前集 ' + prior + ' を欠いています: ' + missing.join(', '));
  console.warn('[pipeline] 主アンカー照合が不能なため重複排除は成立しません（9/8→9/9 Apple 教訓）');
  die([
    'triage done blocked: topic-history.md が前集 ' + prior + ' の ' + missing.join('/') + ' を欠く。',
    '先に Phase 5 の登録を完了するか、outline.md §1 に `継続主題承認` を記録した上で --audit を付けて再実行してください。',
  ].join(' '));
}

// 截止检查点（JST 时刻，触发即告警并顺延补齐；内容完整性不可裁剪）
const DEADLINES = [
  { at: '08:20', need: 'triage', rule: '选题未完成 → 立即告警并加速交接；仍须确定 B1–B4 + A/C/D' },
  { at: '10:30', need: 'draft-B2', rule: 'B2 未锁定 → 立即告警并优先补齐；B3/B4 不压缩' },
  { at: '12:45', need: 'draft-B4', rule: 'B4 未锁定 → 立即告警并优先补齐；B4 与 D 不裁剪、不并入 C' },
  { at: '13:30', need: 'tts-B3', rule: 'TTS 积压 → 立即告警并按串行队列追平；不跳句、不减段' },
  { at: '14:45', need: 'tts-B4', rule: '全部 TTS 未完成 → 立即告警并继续合成；正文不用静音垫替代' },
  { at: '15:30', need: 'assembly', rule: '成片未拼接 → 立即告警并继续渲染；完成质检后整体发布' },
  { at: '16:00', need: 'publish', rule: '未完成发布 → 立即告警；完成 spotcheck 后顺延整体发布，不裁剪内容' },
];
// need 允许的上游等价状态（如 need draft-B4 时 tts-B4 也算过）
const DONE_ALIAS = { 'draft-B2': ['draft-B2', 'tts-B2'], 'draft-B4': ['draft-B4', 'tts-B4'], 'tts-B3': ['tts-B3'], 'tts-B4': ['tts-B4'], 'assembly': ['assembly'], 'triage': ['triage'], 'publish': ['publish'] };

function parseArgs(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i].startsWith('--')) {
      const k = argv[i].slice(2);
      if (['note', 'retry', 'force', 'repair', 'audit'].includes(k) && (i + 1 >= argv.length || argv[i + 1].startsWith('--'))) { out[k] = true; }
      else { out[k] = argv[++i]; if (k === 'retry') out.retry = true; }
    } else out._.push(argv[i]);
  }
  return out;
}

const args = parseArgs(process.argv.slice(2));
const cmd = args._[0];
const date = args.date;

if (cmd === 'init') {
  const p = pipelinePath(date);
  if (fs.existsSync(p) && !args.force) die('已存在（--force 覆盖，会丢状态）: ' + p);
  const today = jstDate();
  if (date !== today && !args.force) {
    die([
      '--date 与当前东京日期不一致。',
      `expected=${today} got=${date}`,
      '定时契约要求只操作当日流水线；补做旧日期必须显式使用 --force。',
    ].join(' '));
  }
  const items = {};
  for (const [id, stage] of ITEM_DEFS) items[id] = { id, stage, state: 'pending', attempts: 0, updated: new Date().toISOString(), note: '' };
  const engine = { state: 'unknown', updated: new Date().toISOString(), note: '' };
  save(date, { date, created: new Date().toISOString(), updated: '', last_alive: new Date().toISOString(), items, engine, events: [] });
  console.log('[pipeline] init ok: ' + p);
  process.exit(0);
}

const st = load(date);

// Outline-driven contract sync: a day may adopt five themes even though the
// legacy contract stops at B4. Extend the tracked items from outline.json so
// draft-B5/tts-B5 are never orphaned outside the watchdog.
try {
  const outlinePath = path.join(US_ROOT, 'daily-output', date, 'production', 'outline.json');
  if (fs.existsSync(outlinePath)) {
    const outline = JSON.parse(fs.readFileSync(outlinePath, 'utf8').replace(/^\uFEFF/, ''));
    const adopted = (outline.b_candidates || []).filter(c => c.duplicate_check !== 'rejected');
    const bCount = ITEM_DEFS.filter(([id]) => /^draft-B\d+$/.test(id)).length;
    let addedAny = false;
    for (let i = bCount + 1; i <= Math.min(adopted.length, 9); i++) {
      for (const [id, stage] of [['draft-B' + i, 'write-b'], ['tts-B' + i, 'tts-b']]) {
        if (!ITEM_DEFS.some(([eid]) => eid === id)) ITEM_DEFS.push([id, stage]);
        if (!st.items[id]) {
          st.items[id] = { id, stage, state: 'pending', attempts: 0, updated: new Date().toISOString(), note: '' };
          addedAny = ensureEvent(st, id, 'added', 'auto-outline-sync') || addedAny;
        }
      }
    }
    if (addedAny && date === jstDate()) save(date, st);
  }
} catch { /* outline が読めない日はレガシー契約のまま */ }

// Infrastructure (WSL TTS engine) bookkeeping; guard writes automatically and
// failures must never break the startup path itself.
if (cmd === 'engine') {
  const allowed = ['unknown', 'starting', 'ready', 'failed'];
  if (!allowed.includes(args.state)) die('--state must be one of: ' + allowed.join('|'));
  if (date !== jstDate() && !args.force) {
    console.log('[pipeline] engine: skip old-date ' + date + ' (today=' + jstDate() + ')');
    process.exit(0);
  }
  if (!st.engine) st.engine = { state: 'unknown', updated: new Date().toISOString(), note: '' };
  const from = st.engine.state;
  st.engine.state = args.state;
  st.engine.updated = new Date().toISOString();
  st.engine.note = args.note || '';
  st.events.push({ t: st.engine.updated, id: 'engine', from, to: args.state, retry: false, note: st.engine.note });
  if (st.events.length > 300) st.events = st.events.slice(-300);
  save(date, st);
  console.log('[pipeline] engine: ' + from + ' -> ' + args.state + (st.engine.note ? ' (' + st.engine.note.slice(0, 120) + ')' : ''));
  process.exit(0);
}

// Read-only resume briefing: the single entry point for post-interruption
// continuation. Never saves; any date allowed.
if (cmd === 'resume') {
  const age = (iso) => {
    if (!iso) return null;
    const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
    return Number.isFinite(m) ? m : null;
  };
  const fmtAge = (m) => (m == null ? '?' : (m >= 0 ? m + 'm前' : Math.abs(m) + 'm後'));
  console.log('date=' + st.date + ' now(JST)=' + jstHHMM() + ' last_alive=' + st.last_alive);
  const hb = age(st.last_alive);
  if (hb != null && hb > 15) console.log('WARN heartbeat stale ' + fmtAge(hb) + ' (run alive first)');
  const eng = st.engine || { state: 'unknown', updated: '', note: '' };
  console.log('engine=' + eng.state + ' updated=' + fmtAge(age(eng.updated)) + (eng.note ? ' note=' + eng.note.slice(0, 120) : ''));
  for (const [id] of ITEM_DEFS) {
    const it = st.items[id];
    const m = age(it.updated);
    const stage = (TH[it.stage] || {})[it.state];
    let hint = '';
    if (it.state === 'done') hint = '→ skip';
    else if (it.state === 'running') hint = '→ continue/takeover ' + fmtAge(m) + (stage ? '/threshold ' + stage + 'm' : '');
    else if (it.state === 'reviewing') hint = '→ review ' + fmtAge(m) + (stage ? '/threshold ' + stage + 'm' : '');
    else if (it.state === 'failed') hint = '→ retry';
    else hint = '→ queued';
    console.log(`${id.padEnd(15)} ${String(it.state).padEnd(9)} ${fmtAge(m).padEnd(8)} ${hint} ${it.note.slice(0, 50)}`);
  }
  const badContent = ITEM_DEFS.filter(([id]) => /^(draft-|tts-)/.test(id) || ['spotcheck', 'publish'].includes(id))
    .filter(([id]) => st.items[id] && st.items[id].state === 'skipped');
  if (badContent.length) console.log('CONTRACT VIOLATION skipped items: ' + badContent.map(([id]) => id).join(', '));
  const next = [];
  for (const [id] of ITEM_DEFS) {
    const it = st.items[id];
    if (it.state === 'running' || it.state === 'reviewing') next.push(id + ': continue or takeover (check stale threshold)');
    if (it.state === 'failed') next.push(id + ': retry');
  }
  const ttsPending = ITEM_DEFS.filter(([id]) => /^tts-/.test(id) && st.items[id].state !== 'done' && st.items[id].state !== 'skipped').length;
  if (eng.state !== 'ready' && ttsPending > 0) next.push('engine: start/check WSL TTS server before TTS work (guard updates engine state)');
  if (hb != null && hb > 15) next.push('heartbeat: run alive first');
  if (!next.length) console.log('NEXT: all tracked items terminal; verify publish/final state');
  else for (const n of next) console.log('NEXT: ' + n);
  process.exit(0);
}

if (cmd === 'set') {
  const it = st.items[args.id];
  if (!it) die('未知 id: ' + args.id + '（init 定义见 pipeline.mjs ITEM_DEFS）');
  if (!STATES.includes(args.state)) die('非法 state: ' + args.state);
  if (date !== jstDate() && !args.force) {
    const subject = '[pipeline] old-date mutation blocked';
    const text = `拒绝修改旧日期流水线: date=${date} today(JST)=${jstDate()} id=${args.id}`;
    sendContractAlert(st, subject, text, `old-date:${date}:${args.id}`);
    save(date, st);
    die(text);
  }
  if (date !== jstDate() && args.force) {
    console.warn(`[pipeline] old-date mutation forced: date=${date} id=${args.id} state=${args.state}`);
  }
  if (it.state === 'done' && args.state !== 'done') {
    const text = `拒绝将已完成 item 回退: date=${date} id=${args.id} done -> ${args.state}`;
    sendContractAlert(st, '[pipeline] done-item regression blocked', text, `regression:${date}:${args.id}:${args.state}`);
    save(date, st);
    die(text);
  }
  if (args.state === 'skipped' && (/^(draft-|tts-)/.test(args.id) || ['spotcheck', 'publish'].includes(args.id))) {
    const text = [
      `内容完整性契约禁止 skipped: date=${date} id=${args.id}`,
      'draft-*/tts-*/spotcheck/publish 不允许因时间不足被裁剪或跳过。',
      '延迟时必须顺延补完；历史遗留的 skipped 用 set --repair 恢复。',
    ].join(' ');
    sendContractAlert(st, '[pipeline] content trim blocked', text, `skip-banned:${date}:${args.id}`);
    save(date, st);
    die(text);
  }
  if (it.state === 'skipped' && args.state !== 'skipped' && !args.repair) {
    const text = [
      `skipped 不可直接翻转: date=${date} id=${args.id}`,
      `requested=${args.state}`,
      '这是内容完整性契约违规。恢复完整内容必须改用 set --repair 并显式记入恢复事件。',
    ].join(' ');
    sendContractAlert(st, '[pipeline] skipped mutation blocked', text, `skipped:${date}:${args.id}`);
    save(date, st);
    die(text);
  }
  if (args.repair) {
    if (it.state !== 'skipped') die('--repair 只允许用于 skipped item');
    it.attempts = (it.attempts || 0) + 1;
  }
  if (args.id === 'triage' && args.state === 'done' && !args.audit) {
    checkTriagerRegistry(date);
  }
  const from = it.state;
  it.state = args.state;
  it.updated = new Date().toISOString();
  it.note = args.note || '';
  if (args.retry) it.attempts = (it.attempts || 0) + 1;
  st.events.push({ t: it.updated, id: it.id, from, to: args.state, retry: !!args.retry, note: it.note });
  if (st.events.length > 300) st.events = st.events.slice(-300);
  save(date, st);
  console.log('[pipeline] ' + it.id + ': ' + from + ' -> ' + args.state + (args.retry ? ' (retry#' + it.attempts + ')' : ''));
  process.exit(0);
}

if (cmd === 'get') {
  console.log(JSON.stringify(args.id ? st.items[args.id] : st, null, 2));
  process.exit(0);
}

if (cmd === 'alive') {
  const now = new Date().toISOString();
  st.updated = now;
  st.last_alive = now;
  for (const it of Object.values(st.items)) {
    if (LIVE.has(it.state)) it.updated = now;
  }
  save(date, st);
  console.log('[pipeline] heartbeat ' + now);
  process.exit(0);
}

if (cmd === 'status') {
  console.log('date=' + st.date + ' now(JST)=' + jstHHMM() + ' last_alive=' + st.last_alive);
  for (const [id] of ITEM_DEFS) {
    const it = st.items[id];
    const mins = Math.round((Date.now() - new Date(it.updated).getTime()) / 60000);
    console.log(`${id.padEnd(15)} ${String(it.state).padEnd(9)} ${('a' + it.attempts).padEnd(3)} ${String(mins + 'm前').padEnd(7)} ${it.note.slice(0, 60)}`);
  }
  process.exit(0);
}

if (cmd === 'check') {
  const problems = [];
  for (const [id, stage] of ITEM_DEFS) {
    const it = st.items[id];
    if (it.state === 'failed') problems.push({ id, kind: 'failed', note: it.note });
    if (!LIVE.has(it.state)) continue;
    const th = (TH[it.stage] || {})[it.state];
    if (th == null) continue;
    const mins = (Date.now() - new Date(it.updated).getTime()) / 60000;
    if (mins > th) problems.push({ id, kind: 'stale', state: it.state, mins_since: Math.round(mins), threshold: th });
  }
  const hb = (Date.now() - new Date(st.last_alive).getTime()) / 60000;
  if (hb > 15) problems.push({ id: 'orchestrator', kind: 'heartbeat', mins_since: Math.round(hb) });
  const badContent = ITEM_DEFS.filter(([id]) => /^(draft-|tts-)/.test(id) || ['spotcheck', 'publish'].includes(id))
    .filter(([id]) => st.items[id] && st.items[id].state === 'skipped');
  if (badContent.length) problems.push(...badContent.map(([id]) => ({ id, kind: 'contract', reason: 'content or final item skipped' })));
  console.log(JSON.stringify({ ok: problems.length === 0, problems }, null, 2));
  if (date === jstDate()) alertProblems(st, date, problems);
  process.exit(problems.length ? 2 : 0);
}

if (cmd === 'deadlines') {
  const nowM = jstMinutes();
  const rows = [];
  for (const d of DEADLINES) {
    const [h, m] = d.at.split(':').map(Number);
    const due = h * 60 + m;
    if (nowM < due) { rows.push({ at: d.at, status: 'future', rule: d.rule }); continue; }
    const ids = DONE_ALIAS[d.need] || [d.need];
    let passed = ids.some(i => st.items[i] && st.items[i].state === 'done');
    if (d.need === 'draft-B4' || d.need === 'tts-B4') {
      // With five adopted themes the B4 deadline means "every B slot", so
      // dynamically added B5 items must also be done before the row is met.
      const prefix = d.need.startsWith('draft') ? 'draft-B' : 'tts-B';
      const allSlots = ITEM_DEFS.map(([id]) => id).filter(id => id.startsWith(prefix));
      passed = allSlots.length > 0 && allSlots.every(i => st.items[i] && st.items[i].state === 'done');
    }
    rows.push({ at: d.at, status: passed ? 'met' : 'BREACH', rule: d.rule });
  }
  console.log(JSON.stringify({ now_jst: jstHHMM(), rows }, null, 2));
  if (date === jstDate()) {
    let changed = false;
    for (const r of rows.filter(r => r.status === 'BREACH')) {
      const note = `deadline:${r.at}:${date}`;
      if (!ensureEvent(st, 'deadline', 'alert', note)) continue;
      changed = true;
      notify(`[pipeline] deadline breach: ${r.at} (${date})`, JSON.stringify({ date, breach: r }, null, 2));
    }
    if (changed) save(date, st);
  }
  process.exit(rows.some(r => r.status === 'BREACH') ? 2 : 0);
}

if (cmd === 'event') {
  const kind = args._[1] || '';
  const actor = args.actor || 'orchestrator';
  const text = args.note || '';
  if (!['dispatched', 'progress', 'collected'].includes(kind)) {
    die('event 的第一个参数必须是 dispatched|progress|collected');
  }
  if (!args.id) die('event 需要 --id（pipeline item，例如 draft-B1 / tts-A）');
  const role = kind === 'dispatched' ? 'dispatcher=' + actor : actor;
  const note = kind + ':' + role + (text ? ' ' + text : '');
  st.events.push({ t: new Date().toISOString(), id: args.id, from: 'event', to: kind, retry: false, note });
  if (st.events.length > 300) st.events = st.events.slice(-300);
  save(date, st);
  console.log('[pipeline] event ' + kind + ' ' + args.id + ' (' + note.slice(0, 120) + ')');
  process.exit(0);
}

die('未知命令: ' + cmd + '（init|set|get|status|check|deadlines|alive|engine|resume）');

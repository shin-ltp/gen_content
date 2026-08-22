// collect-email-imap.mjs — Gmail 晨报收集（IMAP 直连版）
// 用应用专用密码（GMAIL_APP_PASSWORD）通过 IMAP 抓取订阅邮件，绕开浏览器自动化检测。
// 需要在 Node 启动时加 --use-system-ca（沙箱 Node 默认不信任系统根 CA）。
// 依赖: tools/collect/node_modules/imapflow（见 package.json）
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const _require = createRequire('C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
import { ImapFlow } from 'imapflow';
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, stripHtml, atomicWrite } from './collect-utils.mjs';

const PROJECT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\//,'')), '..', '..');
const OUT = process.env.EMAIL_OUT || './out';
fs.mkdirSync(OUT, { recursive: true });

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
const GMAIL_USER = ENV.GOOGLE_EMAIL || '';
const GMAIL_APP_PASS = ENV.GMAIL_APP_PASSWORD || '';

// 各订阅源的检索条件（IMAP 的 FROM 匹配对某些发件人是通配；SINCE 取近 N 天）
const SEARCH_DAYS = Number(process.env.EMAIL_SEARCH_DAYS || '7');
const NEWSLETTERS = [
  { id: 'bloomberg', name: 'Bloomberg Five Things', from: 'Bloomberg', minBody: 100, source: 'Bloomberg' },
  { id: 'wsj', name: 'WSJ Markets A.M.', from: '@wsj.com', minBody: 100, source: 'WSJ' },
  { id: 'yahoo', name: 'Yahoo Finance Morning Brief', from: 'Yahoo Finance', minBody: 100, source: 'Yahoo Finance' },
  { id: 'reuters', name: 'Reuters Morning Wire', from: 'Reuters', minBody: 100, source: 'Reuters' },
  { id: 'semianalysis', name: 'SemiAnalysis Newsletter', from: 'Semianalysis', minBody: 100, source: 'SemiAnalysis' }
];

const IMAP_OPTS = { host: 'imap.gmail.com', port: 993, secure: true, auth: { user: GMAIL_USER, pass: GMAIL_APP_PASS }, logger: false };

// --- MIME 解码工具（零原生依赖；imapflow 返回的 source 是原始 RFC822 文本） ---
function decodeQP(s) {
  return String(s || '')
    .replace(/=\r?\n/g, '')
    .replace(/=([0-9A-Fa-f]{2})/g, (_, h) => { try { return String.fromCharCode(parseInt(h, 16)); } catch { return _; } });
}

function decodeB64(s) {
  try { return Buffer.from(String(s || '').replace(/\s+/g, ''), 'base64').toString('utf8'); }
  catch { return String(s || ''); }
}

// 从 RFC822 原始源码里提取 text/plain（或 text/html）正文，处理 base64 / quoted-printable / 编码头
function extractBodyText(src) {
  if (!src) return '';
  const text = Buffer.isBuffer(src) ? src.toString('utf8') : String(src);
  // 分割 MIME 边界块
  const boundaryMatch = text.match(/boundary="?([^";\s]+)"?/i);
  if (boundaryMatch) {
    const boundary = boundaryMatch[1];
    const parts = text.split('--' + boundary);
    for (const part of parts) {
      if (/Content-Type:\s*text\/plain/i.test(part)) {
        const m = part.match(/Content-Transfer-Encoding:\s*(\S+)/i);
        const enc = m ? m[1].toLowerCase() : '';
        const body = part.replace(/^[\s\S]*?\r?\n\r?\n/, '');
        const clean = body.replace(/^[\s\S]*?(\r?\n){2}/, '');
        if (enc === 'base64') return decodeB64(clean);
        if (enc === 'quoted-printable') return stripHtml(decodeQP(clean));
        if (clean.length > 30) return stripHtml(clean);
      }
    }
    // text/html 兜底
    for (const part of parts) {
      if (/Content-Type:\s*text\/html/i.test(part)) {
        const body = part.replace(/^[\s\S]*?\r?\n\r?\n/, '');
        return stripHtml(body);
      }
    }
    return '';
  }
  // 无边界：整封是 text/plain 或 text/html
  const m = text.match(/Content-Type:\s*text\/(plain|html)[\s\S]*?\r?\n\r?\n([\s\S]*)/i);
  if (m) {
    const encM = text.match(/Content-Transfer-Encoding:\s*(\S+)/i);
    const enc = encM ? encM[1].toLowerCase() : '';
    const body = m[2].replace(/^[\s\S]*?(\r?\n){2}/, '');
    if (enc === 'base64') return decodeB64(body);
    if (enc === 'quoted-printable') return stripHtml(decodeQP(body));
    return stripHtml(body);
  }
  return stripHtml(text);
}

// 从原始 email 里解出可读标题（RFC2047 编码支持）
function decodeSubject(subj) {
  if (!subj) return '';
  const regex = /=\?([^?]+)\?([bBqQ])\?([^?]*)\?=/g;
  let out = subj, m;
  while ((m = regex.exec(subj))) {
    const [, charset, enc, encText] = m;
    const decoded = enc.toLowerCase() === 'b' ? decodeB64(encText) : decodeQP(encText);
    out = out.replace(m[0], decoded);
  }
  return out.replace(/[\r\n]+/g, ' ').trim();
}

// imapflow 的 fetchOne 拿 source + envelope
async function fetchLatest(client, from, since) {
  const lock = await client.getMailboxLock('INBOX');
  try {
    const uids = await client.search({ from, since }, { uid: true });
    if (!uids.length) return null;
    const uid = uids[uids.length - 1];
    const msg = await client.fetchOne(uid, { source: true, envelope: true, uid: true }, { uid: true });
    return { uid, envelope: msg.envelope, source: msg.source };
  } finally {
    lock.release();
  }
}

async function run() {
  if (!GMAIL_USER) {
    console.error('[email-imap] GOOGLE_EMAIL 未設定。SKIP (exit 3)');
    process.exit(3);
  }
  if (!GMAIL_APP_PASS) {
    console.error('[email-imap] GMAIL_APP_PASSWORD 未設定（アプリ専用パスワードが必要）。SKIP (exit 3)');
    process.exit(3);
  }
  console.log('[email-imap] Gmail IMAP 晨報收集開始 (' + GMAIL_USER + ', 検索対象 ' + SEARCH_DAYS + '日)');
  const seen = loadSeen();
  let n = 0, failed = 0, already = 0;
  const today = new Date().toISOString().slice(0, 10);
  const client = new ImapFlow(IMAP_OPTS);
  try {
    await client.connect();
    console.log('[email-imap] IMAP 接続OK');
    const since = new Date(Date.now() - SEARCH_DAYS * 86400000);
    for (const nl of NEWSLETTERS) {
      const skey = 'email-imap-' + nl.id;
      const sid = today + '-' + nl.id;
      if (seenHas(seen, skey, sid)) { already++; console.log('[email-imap] ' + nl.id + ': 今日分取得済み（スキップ）'); continue; }
      console.log('[email-imap] 検索: ' + nl.name + ' (from=' + nl.from + ')');
      let res = null;
      try {
        res = await fetchLatest(client, nl.from, since);
      } catch (e) {
        console.error('[email-imap] ' + nl.id + ' 検索失敗: ' + (e && e.message || e).toString().slice(0, 120));
        failed++; continue;
      }
      if (!res) { console.log('[email-imap] ' + nl.id + ': 該当メールなし（' + SEARCH_DAYS + '日以内）'); failed++; continue; }
      const body = extractBodyText(res.source);
      const title = decodeSubject(res.envelope && res.envelope.subject) || nl.name + ' (' + today + ')';
      if (!body || body.length < nl.minBody) {
        console.log('[email-imap] ' + nl.id + ': 本文抽出失敗（body=' + (body || '').length + '）');
        failed++; continue;
      }
      const meta = {
        id: 'NWS-' + today.replace(/-/g, '') + '-E' + String(n + 1).padStart(3, '0'),
        category: 'news', ticker: '',
        title: title.slice(0, 200),
        source: nl.source + ' Newsletter（Gmail IMAP）', source_type: 'newsletter',
        url: 'gmail-imap://' + nl.id + '/' + res.uid, relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-email-imap', priority: 'TBD',
        newsletter_id: nl.id, pub_date: today,
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const md = frontmatter(meta) + '\n\n## Body\n\n' + body.slice(0, 8000) + '\n';
      atomicWrite(path.join(OUT, 'EMAIL-' + nl.id + '-' + today + '.md'), md);
      seenAdd(seen, skey, sid, { name: nl.name, title: title.slice(0, 80), body_chars: body.length });
      n++;
      console.log('[email-imap] [' + n + '] ' + nl.id + ': ' + body.length + '字 | ' + title.slice(0, 50));
    }
  } catch (e) {
    console.error('[email-imap] 接続/実行エラー: ' + (e && e.message || e).toString().slice(0, 200));
    try { await client.logout(); } catch {}
    process.exit(1);
  }
  try { await client.logout(); } catch {}
  try { saveSeen(seen); } catch (e) { console.error('[email-imap] seen 保存失敗: ' + e.message); }
  if (n === 0 && already === 0) {
    console.error('[email-imap] 0件取得（全ニュースレター失敗）');
    process.exitCode = 1;
  } else {
    console.log('\n=== email-imap: 新增 ' + n + ' 通 (既収集 ' + already + ' / 失敗 ' + failed + ') -> ' + OUT + ' ===');
  }
}

run().catch(e => { console.error('FATAL: ' + (e && e.message || e).toString().slice(0, 300)); process.exit(1); });

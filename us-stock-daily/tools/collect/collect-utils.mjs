// collect-utils.mjs — 共通ユーティリティ（frontmatter / HTML除去 / fetch再試行 / 並列安全書き込み）
import fs from 'node:fs';
import path from 'node:path';

// --- 全collector共通のHTTPヘッダー ---
export const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36';
export const UA_HEADERS = { 'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml',
  'Accept-Language': 'en-US,en;q=0.9' };

// --- frontmatter 生成（全collector共通）---
// 配列は [a, b] 形式、文字列は " をエスケープ、それ以外はそのまま
export function frontmatter(o) {
  const L = ['---'];
  for (const [k, v] of Object.entries(o)) {
    if (v === null || v === undefined) { L.push(k + ': '); continue; }
    if (Array.isArray(v)) {
      L.push(k + ': [' + v.map(x => '"' + String(x).replace(/"/g, '\\"') + '"').join(', ') + ']');
    } else if (typeof v === 'string') {
      L.push(k + ': ' + v.replace(/"/g, '\\"'));
    } else {
      L.push(k + ': ' + v);
    }
  }
  L.push('---');
  return L.join('\n');
}

// --- HTML除去（ブロック要素→改行、タグ除去、エンティティ復元）---
export function stripHtml(html) {
  if (!html) return '';
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, '')
    .replace(/<style[\s\S]*?<\/style>/gi, '')
    .replace(/<!--[\s\S]*?-->/g, '')
    .replace(/<img[^>]*>/gi, '')
    .replace(/<\/(p|div|h[1-6]|blockquote|li|ul|ol|tr)>/gi, '\n')
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCharCode(parseInt(n, 10)))
    .replace(/\u00a0/g, ' ')
    .replace(/[ \t]+/g, ' ')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/^ +| +$/gm, '')
    .trim();
}

// --- CDATA・タグ除去（RSS/XML用・軽量版）---
export function stripTags(s) {
  return (s || '')
    .replace(/<!\[CDATA\[|\]\]>/g, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/&amp;/g, '&')
    .replace(/&apos;/g, "'")
    .replace(/&#39;/g, "'")
    .replace(/&#x27;/g, "'")
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/\s+/g, ' ')
    .trim();
}

// --- fetch 再試行ラッパー（HTTP ステータスも再試行対象に含める） ---
// fn: () => Promise<Response>
// options: { retries, delayMs, backoff, retryOn, timeoutMs }
export async function fetchRetry(fn, options = {}) {
  const { retries = 3, delayMs = 1500, backoff = 2,
    retryOn = (res) => res.status >= 500 || res.status === 429 } = options;
  let lastErr = null;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await Promise.race([
        fn(),
        new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), options.timeoutMs || 30000))
      ]);
      if (!res.ok && retryOn(res)) {
        const err = new Error('HTTP ' + res.status);
        if (attempt < retries) {
          await delay(delayMs * Math.pow(backoff, attempt - 1) + Math.random() * 400);
          continue;
        }
        lastErr = err;
        break;
      }
      return res;
    } catch (e) {
      lastErr = e;
      if (attempt < retries) await delay(delayMs * Math.pow(backoff, attempt - 1) + Math.random() * 400);
    }
  }
  throw lastErr;
}

// --- 遅延ヘルパー（AbortSignal対応・テスト容易化） ---
export function delay(ms) { return new Promise(r => setTimeout(r, ms)); }

// --- JSON をシグネチャ付きで安全に読み取る（壊れたJSON・行編集耐性） ---
// ファイル末尾に "# sig: {name} {mtime}" を付与。シグネチャ不一致なら復元する。
export function safeReadJson(file, def, sig = '') {
  try {
    if (!fs.existsSync(file)) return { value: JSON.parse(JSON.stringify(def)), needWrite: false };
    const raw = fs.readFileSync(file, 'utf8');
    // シグネチャ行（先頭 # の行）を末尾から除去する。末尾に改行が無いケースでも安全に扱う。
    const clean = raw.replace(/[\r\n]+#[^\r\n]*\s*$/, '').trim();
    if (!clean) return { value: JSON.parse(JSON.stringify(def)), needWrite: false };
    const value = JSON.parse(clean);
    const ok = !sig || raw.includes('# sig: ' + sig);
    return { value, needWrite: !ok };
  } catch (e) {
    console.error('[collect-utils] safeReadJson 破損 ' + path.basename(file) + ': ' + e.message + ' -> 初期化');
    return { value: JSON.parse(JSON.stringify(def)), needWrite: true };
  }
}

// --- 原子書き込み（一時ファイル→リネーム。クラッシュで半端ファイルを残さない） ---
export function atomicWrite(file, content, sig = '') {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const data = sig ? String(content).trim() + '\n# sig: ' + sig + '\n' : String(content);
  const tmp = file + '.tmp-' + process.pid + '-' + Date.now();
  fs.writeFileSync(tmp, data, 'utf8');
  try { fs.renameSync(tmp, file); }
  catch (e) {
    // Windows: 対象が存在するとリネームできないケースがあるため上書きにフォールバック
    try { fs.copyFileSync(tmp, file); fs.unlinkSync(tmp); }
    catch (e2) { try { fs.unlinkSync(tmp); } catch {} throw e2; }
  }
}

// --- フロントマターを安全にパース ---
export function parseFrontmatter(content) {
  const fmMatch = String(content || '').match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return null;
  const fm = {};
  for (const line of fmMatch[1].split('\n')) {
    const m = line.match(/^([A-Za-z_]+):\s*(.*)$/);
    if (m) {
      let v = m[2].trim();
      if (v.startsWith('"') && v.endsWith('"')) v = v.slice(1, -1);
      fm[m[1]] = v;
    }
  }
  return fm;
}

// --- 素材本文の実効長（フロントマターを除いた文字数を概算） ---
export function bodyLength(content) {
  const c = String(content || '');
  const fm = parseFrontmatter(c);
  if (!fm) return c.length;
  return c.split('\n---\n').slice(1).join('\n---\n').trim().length;
}

// --- RSS の日付文字列 → YYYY-MM-DD（不正なら空） ---
export function dateKey(s) { try { return new Date(s).toISOString().slice(0, 10); } catch { return ''; } }

// --- 日次ID生成（{CAT}-{YYYYMMDD}-{連番}）---
export function makeId(cat, dateStr, seq) {
  return cat + '-' + dateStr.replace(/-/g, '') + '-' + String(seq).padStart(3, '0');
}

// --- 安全ファイル書き込み（ディレクトリ自動作成）---
export function writeFile(dir, filename, content) {
  fs.mkdirSync(dir, { recursive: true });
  atomicWrite(path.join(dir, filename), content);
}

// --- 安全終了ヘルパー（部分成功でもexit 0、完全失敗時のみexit 1）---
export function finish(name, count, total) {
  if (count > 0) {
    console.log('\n=== ' + name + ': ' + count + ' 件取得成功 ===');
    process.exit(0);
  } else {
    console.error('\n=== ' + name + ': 0 件（完全失敗） ===');
    process.exit(1);
  }
}

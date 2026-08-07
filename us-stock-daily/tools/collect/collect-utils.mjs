// collect-utils.mjs — 共通ユーティリティ（frontmatter / HTML除去 / fetch再試行 / 並列安全書き込み）
import fs from 'node:fs';
import path from 'node:path';

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

// --- fetch 再試行ラッパー ---
// fn: () => Promise<Response> （URLごとに headers/timeout を指定可能）
export async function fetchRetry(fn, retries = 2, delayMs = 1000) {
  let lastErr = null;
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const res = await fn();
      return res;
    } catch (e) {
      lastErr = e;
      if (attempt < retries) await new Promise(r => setTimeout(r, delayMs));
    }
  }
  throw lastErr;
}

// --- 日次ID生成（{CAT}-{YYYYMMDD}-{連番}）---
export function makeId(cat, dateStr, seq) {
  return cat + '-' + dateStr.replace(/-/g, '') + '-' + String(seq).padStart(3, '0');
}

// --- 安全ファイル書き込み（ディレクトリ自動作成）---
export function writeFile(dir, filename, content) {
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(path.join(dir, filename), content, 'utf8');
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

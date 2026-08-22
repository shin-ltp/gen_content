// collect-email.mjs — Gmail 无头浏览器收集 5 份晨报
// Playwright + persistent profile 避免每次重新登录
// 首次运行建议 --headed 手动登录一次，后续自动复用 cookies
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
const _require = createRequire('C:/Users/RW250701/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/');
const { chromium } = _require('playwright');
import { load as loadSeen, save as saveSeen, has as seenHas, add as seenAdd } from './seen-store.mjs';
import { frontmatter, atomicWrite } from './collect-utils.mjs';

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
const GMAIL_PASS = ENV.GOOGLE_PASSWORD || '';
const PROFILE_DIR = path.join(PROJECT, 'tools', 'collect', '.gmail-profile');

// Gmail 検索は「更新・プロモーション」も含めて Newsletters に寄せて実行する
// （ユーザーは default「重要メール」表示では購読メールが見えない点を指摘済み）
const CategoryTab = 'category/updates';

const NEWSLETTERS = [
  { id: 'bloomberg', name: 'Bloomberg Five Things', query: 'from:Bloomberg "five things"', source: 'Bloomberg' },
  { id: 'wsj', name: 'WSJ Markets A.M.', query: 'from:"Wall Street Journal" (markets OR morning)', source: 'WSJ' },
  { id: 'yahoo', name: 'Yahoo Finance Morning Brief', query: 'from:"Yahoo Finance" (morning OR brief)', source: 'Yahoo Finance' },
  { id: 'reuters', name: 'Reuters Morning Wire', query: 'from:Reuters (morning OR wire OR newsletter)', source: 'Reuters' },
  { id: 'semianalysis', name: 'SemiAnalysis Newsletter', query: 'from:Semianalysis', source: 'SemiAnalysis' }
];

async function ensureLoggedIn(page) {
  // 受信トレイに到達していること+ コンテンツが描画されていることを両方確認してから
  // 「ログイン済み」と判定する（URL だけでは accounts.google.com の #inbox と混同するため）
  const isReallyInMail = async () => {
    try {
      await page.waitForURL(/^https:\/\/mail\.google\.com\/mail\//, { timeout: 8000 });
      const row = await page.$('tr.zA, tr[role="row"], [role="main"] .Cp, [role="main"] table');
      return !!row;
    } catch { return false; }
  };
  for (let attempt = 1; attempt <= 2; attempt++) {
    await page.goto('https://mail.google.com/mail/u/0/#inbox', { waitUntil: 'domcontentloaded', timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(4000);
    if (await isReallyInMail()) { console.log('[email] Gmail ログイン済み'); return true; }
    // URL が accounts.google.com のサインインに飛んだ場合は未ログイン
    const emailField = await page.$('input[type="email"], input[name="identifier"], input[type="text"]').catch(() => null);
    if (emailField && GMAIL_USER && GMAIL_PASS && attempt === 1) {
      console.log('[email] Gmail ログイン試行 (try ' + attempt + ')...');
      const ok = await doGoogleLogin(page);
      if (ok) { console.log('[email] Gmail ログイン成功'); return true; }
    }
  }
  if (!GMAIL_USER || !GMAIL_PASS) {
    console.error('[email] GOOGLE_EMAIL / GOOGLE_PASSWORD が .env に設定されていません');
  }
  // Google の自動化検知（「このブラウザまたはアプリは安全でない可能性があります」）や
  // 2FA ブロックを検出したら、わかりやすい手動ログイン指示を出す
  const rejected = await page.evaluate(() => document.body ? /安全でない|unsafe|rejected|再試行/.test(document.body.innerText.slice(0, 400)) : false).catch(() => false);
  if (rejected) {
    console.error('[email] Gmail が自動ログインをブロックしました（自動化検知 or 2FA）。');
  }
  console.error('[email] --headed で一度手動ログインして profile を保存してください: node collect-email.mjs --headed');
  return false;
}

// Google の 2024+ サインインフロー（識別子 -> パスワード）を処理する。
// 2FA / リスク確認ページに当たった場合は即座に失敗扱いにして、
// 静かに profile を汚さない。
async function doGoogleLogin(page) {
  try {
    const emailSel = 'input[type="email"], input[name="identifier"], input[type="text"]';
    await page.waitForSelector(emailSel, { timeout: 15000 });
    await page.fill(emailSel, GMAIL_USER);
    await page.click('#identifierNext, [jsname="V67aGc"]', { timeout: 10000 }).catch(() => page.click('button:has-text("次へ"), button:has-text("Next")'));
    await page.waitForTimeout(2500);
    const pw = await page.$('input[type="password"]').catch(() => null);
    if (!pw) return false; // 2FA や「このデバイスは信頼されていません」等
    await page.fill('input[type="password"]', GMAIL_PASS);
    await page.click('#passwordNext, [jsname="V67aGc"]', { timeout: 10000 }).catch(() => page.click('button:has-text("次へ"), button:has-text("Next")'));
    await page.waitForTimeout(5000);
    await page.waitForURL(/^https:\/\/mail\.google\.com\/mail\//, { timeout: 20000 }).catch(() => {});
    const stillLogin = await page.$('input[type="password"], input[type="email"], input[name="identifier"], input[type="text"]').catch(() => null);
    return !stillLogin;
  } catch (e) {
    console.error('[email] 自動ログイン失敗: ' + (e && e.message || e).toString().slice(0, 120));
    return false;
  }
}

async function searchAndExtract(page, newsletter) {
  // #category/updates タブの上で検索すると、購読メールが「重要メール」優先表示でも見える
  const searchUrl = 'https://mail.google.com/mail/u/0/' + CategoryTab + '/#search/' + encodeURIComponent(newsletter.query);
  await page.goto(searchUrl, { waitUntil: 'domcontentloaded', timeout: 20000 });
  await page.waitForTimeout(3000);
  // Gmail行セレクタ候補（クラス名変更に備えて複数パターン試行）
  const rowSels = ['tr.zA', 'tr[role="row"]', 'div[role="main"] tr.zA'];
  let rows = [];
  for (const sel of rowSels) { rows = await page.$$(sel); if (rows.length > 0) break; }
  if (rows.length === 0) { console.log('[email] ' + newsletter.id + ': 検索結果なし'); return null; }
  const firstRow = rows[0];
  // タイトル取得: 複数セレクタ候補
  const titleSels = ['.bog span', '.xS .bog', 'td:nth-child(2) span'];
  let title = '';
  for (const sel of titleSels) { const el = await firstRow.$(sel); if (el) { title = (await el.textContent().catch(() => '')).trim(); if (title) break; } }
  const senderEl = await firstRow.$('.yW span[email], .yP span');
  const dateEl = await firstRow.$('.xW span, td:nth-child(8) span');
  const sender = senderEl ? (await senderEl.getAttribute('email').catch(() => '')) : '';
  const dateStr = dateEl ? (await dateEl.textContent().catch(() => '')) : '';
  if (!title.trim()) { console.log('[email] ' + newsletter.id + ': タイトル取得失敗'); return null; }
  await firstRow.click();
  await page.waitForTimeout(2000);
  // 本文取得: 複数セレクタ候補
  const bodySels = ['.a3s.aiL', '[data-message-id] .a3s', '.ii.gt .a3s', 'div[role="listitem"] .a3s'];
  let body = '';
  for (const sel of bodySels) {
    const el = await page.$(sel);
    if (el) { body = await el.innerText().catch(() => ''); if (body && body.length > 30) break; }
  }
  await page.goBack().catch(() => {});
  await page.waitForTimeout(1000);
  return { title: title.trim().slice(0, 200), sender, date: dateStr, body: (body || '').slice(0, 8000), url: 'gmail://' + newsletter.id + '/' + Date.now() };
}

async function run() {
  const headed = process.argv.includes('--headed');
  const seen = loadSeen();
  console.log('[email] Gmail collector 開始 (mode=' + (headed ? 'headed' : 'headless') + ')');
  if (!GMAIL_USER) {
    console.error('[email] .env に GOOGLE_EMAIL が設定されていません。SKIP (exit 3)');
    process.exit(3);
  }
  // プロファイル未構築かつパスワード無しの場合は SKIP として終了（仮の success としない）
  const hasProfile = fs.existsSync(path.join(PROFILE_DIR, 'Default', 'Cookies'));
  if (!GMAIL_PASS && !hasProfile) {
    console.error('[email] パスワード未設定かつプロファイル未構築。--headed で初回ログインしてください。SKIP (exit 3)');
    process.exit(3);
  }
  fs.mkdirSync(PROFILE_DIR, { recursive: true });
  const context = await chromium.launchPersistentContext(PROFILE_DIR, {
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: !headed, viewport: { width: 1280, height: 900 },
    args: ['--disable-blink-features=AutomationControlled'],
    ignoreHTTPSErrors: true, timeout: 60000
  });
  const page = context.pages()[0] || await context.newPage();
  try {
    const loggedIn = await ensureLoggedIn(page);
    if (!loggedIn) { console.error('[email] ログイン不可。スキップ。'); await context.close(); return; }
    let collected = 0, failed = 0;
    const today = new Date().toISOString().slice(0, 10);
    for (const nl of NEWSLETTERS) {
      const skey = 'email-' + nl.id;
      const sid = today + '-' + nl.id;
      if (seenHas(seen, skey, sid)) { console.log('[email] ' + nl.id + ': 已取得済み（今日分スキップ）'); continue; }
      console.log('[email] 検索中: ' + nl.name + ' ...');
      let result = null;
      try { result = await searchAndExtract(page, nl); } catch (e) { console.error('[email] ' + nl.id + ' extraction error: ' + (e&&e.message||e).toString().slice(0, 80)); failed++; continue; }
      if (!result || !result.body || result.body.length < 30) { console.log('[email] ' + nl.id + ': 本文が短すぎるまたは取得失敗'); failed++; continue; }
      const meta = {
        id: 'NWS-' + today.replace(/-/g, '') + '-E' + String(collected + 1).padStart(3, '0'),
        category: 'news', ticker: '',
        title: result.title || nl.name + ' (' + today + ')',
        source: nl.source + ' Newsletter（Gmail）', source_type: 'newsletter',
        url: result.url, relevance: 'us-stock',
        collected_at: new Date().toISOString().slice(0, 16),
        collector: 'collect-email', priority: 'TBD',
        newsletter_id: nl.id, sender: result.sender, pub_date: result.date,
        assets_needed: '[]', assets_status: 'none', adopted: false, status: 'raw'
      };
      const md = frontmatter(meta) + '\n\n## Body\n\n' + result.body + '\n';
      atomicWrite(path.join(OUT, 'EMAIL-' + nl.id + '-' + today + '.md'), md);
      seenAdd(seen, skey, sid, { name: nl.name, title: result.title.slice(0, 80), body_chars: result.body.length });
      collected++;
      console.log('[email] [' + collected + '] ' + nl.id + ': ' + result.body.length + '字 | ' + result.title.slice(0, 50));
    }
    try { saveSeen(seen); } catch (e) { console.error('[email] seen 保存失敗: ' + e.message); }
    if (collected === 0) {
      console.error('[email] 0件取得（全ニュースレター失敗、またはログイン問題）');
      process.exitCode = 1;
    }
    else { console.log('\n=== email: 新增 ' + collected + ' 通 (失敗 ' + failed + ') -> ' + OUT + ' ==='); }
  } finally { await context.close(); }
}
run().catch(e => { console.error('FATAL: ' + e.message); process.exit(1); });

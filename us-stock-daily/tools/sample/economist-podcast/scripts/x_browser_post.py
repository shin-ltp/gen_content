"""
X（Twitter）ブラウザ自動投稿 — Playwright（専用プロファイル / headless）。

Playwright 同梱の Chromium と**独立ユーザーデータディレクトリ**
（scripts/.x_browser_profile）を使う。利用者が普段使っている Chrome には
一切触れず、リモートデバッグの手動有効化も不要。実行は既定で headless
（バックグラウンド）なので、投稿中にブラウザで他の作業をしても邪魔にならない。

初回セットアップ（1回だけ）:
  python x_browser_post.py --login
専用ウィンドウが開くので X にログインする（CAPTCHA / 2FA も手動対応可）。
ログイン状態は専用プロファイルに保存され、以降は headless で自動投稿できる。

その他のコマンド:
  python x_browser_post.py --check         # ログイン状態を headless で確認
  python x_browser_post.py --post "テキスト"  # 1件だけ即時投稿（デバッグ用）

デバッグ用にウィンドウを表示したいときは環境変数 X_BROWSER_HEADED=1。

依存: pip install playwright && python -m playwright install chromium
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import (
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

_SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = _SCRIPT_DIR / ".x_browser_profile"

_HOME_URL = "https://x.com/home"
_LOGIN_URL = "https://x.com/login"
_COMPOSE_URL = "https://x.com/compose/post"
_COMPOSE_SEL = '[data-testid="tweetTextarea_0"]'
_TWEET_BUTTONS = ('[data-testid="tweetButtonInline"]', '[data-testid="tweetButton"]')
_HOME_READY_SEL = (
    '[data-testid="SideNav_NewTweet_Button"], '
    '[data-testid="AppTabBar_Home_Link"], '
    '[data-testid="primaryColumn"]'
)
# 実 Chrome と同じ UA を使い、headless 判別を避ける
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
)


# ---------- 基本ユーティリティ ----------

def human_delay(min_sec: float, max_sec: float) -> None:
    time.sleep(random.uniform(min_sec, max_sec))


def post_interval_seconds() -> int:
    """連続投稿間隔（秒）: 3〜5 分のランダム。"""
    return random.randint(180, 300)


def _headed_forced() -> bool:
    """環境変数 X_BROWSER_HEADED=1 でウィンドウ表示を強制（デバッグ用）。"""
    return os.environ.get("X_BROWSER_HEADED", "").strip().lower() in {"1", "true", "yes", "on"}


def _launch_context(p: Any, *, headless: bool) -> BrowserContext:
    """専用プロファイルで Chromium を起動（普段使いの Chrome とは完全分離）。"""
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    ctx = p.chromium.launch_persistent_context(
        user_data_dir=str(PROFILE_DIR),
        headless=headless and not _headed_forced(),
        locale="ja-JP",
        timezone_id="Asia/Tokyo",
        viewport={"width": 1366, "height": 900},
        user_agent=_USER_AGENT,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    ctx.set_default_timeout(30_000)
    return ctx


def _first_page(ctx: BrowserContext) -> Page:
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.on("dialog", lambda d: d.accept())
    return page


def _has_auth_cookie(ctx: BrowserContext) -> bool:
    try:
        return any(c.get("name") == "auth_token" for c in ctx.cookies("https://x.com"))
    except Exception:
        return False


def _is_home_ready(page: Page, timeout_ms: int = 15_000) -> bool:
    try:
        page.wait_for_selector(_HOME_READY_SEL, timeout=timeout_ms)
        return True
    except PlaywrightTimeoutError:
        return False


def _looks_like_login_page(url: str) -> bool:
    u = (url or "").rstrip("/")
    return "/i/flow/login" in u or u.endswith("x.com/login") or u.endswith("twitter.com/login")


# ---------- ログイン ----------

def run_login_flow(*, timeout_sec: float = 600.0) -> bool:
    """見えるウィンドウを1回だけ開き、X に手動ログインしてセッションを保存する。"""
    with sync_playwright() as p:
        ctx = _launch_context(p, headless=False)
        try:
            page = _first_page(ctx)
            page.goto(_HOME_URL, timeout=90_000, wait_until="domcontentloaded")
            if _has_auth_cookie(ctx) and _is_home_ready(page, timeout_ms=20_000):
                print("[X ブラウザ] 既にログイン済みです。操作は不要です。", file=sys.stderr)
                return True
            page.goto(_LOGIN_URL, timeout=90_000, wait_until="domcontentloaded")
            print(
                "[X ブラウザ] 専用ウィンドウを開きました。このウィンドウで X にログインしてください\n"
                "            （CAPTCHA / 2FA もそのまま手動対応できます）。\n"
                f"            ログイン完了を最大 {int(timeout_sec)} 秒待機します…",
                file=sys.stderr,
            )
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                if _has_auth_cookie(ctx):
                    page.wait_for_timeout(1500)
                    print(
                        "[X ブラウザ] ログインを確認しました。セッションを保存しました。\n"
                        "            以降の投稿はバックグラウンド（headless）で自動実行されます。",
                        file=sys.stderr,
                    )
                    return True
                page.wait_for_timeout(1500)
            print("[X ブラウザ] ログイン待機がタイムアウトしました。", file=sys.stderr)
            return False
        finally:
            ctx.close()


def check_browser_ready() -> bool:
    """headless で X ログイン状態を1回チェックする。"""
    try:
        with sync_playwright() as p:
            ctx = _launch_context(p, headless=True)
            try:
                page = _first_page(ctx)
                page.goto(_HOME_URL, timeout=60_000, wait_until="domcontentloaded")
                return _has_auth_cookie(ctx) and _is_home_ready(page, timeout_ms=20_000)
            finally:
                ctx.close()
    except Exception as e:
        print(f"[X ブラウザ] ログイン確認中にエラー: {e}", file=sys.stderr)
        return False


def ensure_x_session(*, timeout_sec: float = 600.0) -> bool:
    """X ログイン状態を確保する。未ログインなら見えるウィンドウでログイン案内。"""
    print("[X ブラウザ] ログイン状態を headless で確認中…", file=sys.stderr)
    if check_browser_ready():
        print("[X ブラウザ] X ログイン OK（専用プロファイル / headless）", file=sys.stderr)
        return True
    print(
        "[X ブラウザ] 未ログイン（または確認失敗）のため、ログインウィンドウを開きます。\n"
        "            このログインは1回だけ。以後はバックグラウンドで完結します。",
        file=sys.stderr,
    )
    return run_login_flow(timeout_sec=timeout_sec)


def wait_for_chrome_cdp(*, timeout_sec: float = 120.0, poll_sec: float = 3.0) -> bool:
    """旧ブラウザ接続待ち API との互換ラッパー（実体は ensure_x_session）。"""
    del poll_sec
    return ensure_x_session(timeout_sec=max(timeout_sec, 300.0))


# ---------- 投稿 ----------

def _text_snippet_for_match(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
    if lines:
        return lines[0][:30]
    tags = re.findall(r"#[^\s#]+", text or "")
    if tags:
        return tags[-1]
    s = (text or "").strip()
    return s[:20]


def _wait_draft_ready(page: Page, timeout_sec: float = 15.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        ready = page.evaluate(
            "sel => !!document.querySelector(sel + ' [data-contents=\"true\"]')",
            _COMPOSE_SEL,
        )
        if ready:
            return
        page.wait_for_timeout(random.uniform(250, 450))
    raise RuntimeError("Draft.js エディタの初期化がタイムアウトしました")


def _fill_compose(page: Page, text: str) -> None:
    """Draft.js 向け: focus 後に insertText で全文入力（React 内部状態を更新）。"""
    editor = page.locator(_COMPOSE_SEL).first
    editor.wait_for(state="visible", timeout=25_000)
    _wait_draft_ready(page)
    page.wait_for_timeout(random.uniform(300, 700))
    editor.click()
    page.wait_for_timeout(random.uniform(200, 500))
    page.keyboard.insert_text(text)
    page.wait_for_timeout(random.uniform(500, 1000))

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    title_snip = lines[0][:20] if lines else ""
    need_url = "youtu" in text or "youtube" in text.lower()
    structure_char = "[" if text.lstrip().startswith("[") else ""
    valid = page.evaluate(
        """({sel, title, needUrl, structureChar, minLen}) => {
            const root = document.querySelector(sel);
            const t = root ? (root.innerText || '') : '';
            const titleOk = !title || t.includes(title);
            const urlOk = !needUrl || t.includes('youtu');
            const structureOk = !structureChar || t.includes(structureChar);
            return titleOk && urlOk && structureOk && t.trim().length >= minLen;
        }""",
        {
            "sel": _COMPOSE_SEL,
            "title": title_snip,
            "needUrl": need_url,
            "structureChar": structure_char,
            "minLen": min(20, max(1, len(text.strip()))),
        },
    )
    if not valid:
        preview = page.evaluate(
            "sel => (document.querySelector(sel) || {}).innerText || ''", _COMPOSE_SEL
        )
        raise RuntimeError(
            "投稿欄の内容検証に失敗しました（タイトル・URL が欠落）。"
            f" preview={str(preview)[:120]!r}"
        )

    btn_ready = page.evaluate(
        """(selectors) => {
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (!el) continue;
                const aria = el.getAttribute('aria-disabled');
                if (aria !== 'true' && !el.disabled) return true;
            }
            return false;
        }""",
        list(_TWEET_BUTTONS),
    )
    if not btn_ready:
        raise RuntimeError("投稿ボタンが有効になりませんでした（Draft.js 状態不一致）")
    page.wait_for_timeout(random.uniform(800, 1500))


def _dismiss_overlays(page: Page) -> None:
    """投稿の邪魔になるバナー類が表示されていれば閉じる。"""
    try:
        page.evaluate(
            """() => {
                const el = document.querySelector('[data-testid="app-bar-close"]');
                if (el) { el.click(); return true; }
                return false;
            }"""
        )
    except Exception:
        pass


def _click_post_button_via_js(page: Page, sel: str) -> bool:
    """JS クリックで投稿ボタンを押す（オーバーレイによる click 遮断を回避）。"""
    try:
        return bool(
            page.evaluate(
                """sel => {
                    const els = Array.from(document.querySelectorAll(sel));
                    for (const el of els) {
                        const aria = el.getAttribute('aria-disabled');
                        if (aria === 'true' || el.disabled) continue;
                        const r = el.getBoundingClientRect();
                        if (r.width <= 0 || r.height <= 0) continue;
                        el.click();
                        return true;
                    }
                    return false;
                }""",
                sel,
            )
        )
    except Exception:
        return False


def _wait_and_click_post_button(page: Page, timeout_sec: float = 30.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        _dismiss_overlays(page)
        for sel in _TWEET_BUTTONS:
            if _click_post_button_via_js(page, sel):
                page.wait_for_timeout(random.uniform(500, 1000))
                return
        page.wait_for_timeout(random.uniform(300, 600))
    raise RuntimeError("投稿ボタンが有効になりませんでした")


def _current_username(page: Page) -> Optional[str]:
    try:
        return page.evaluate(
            """() => {
                const el = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
                if (!el) return null;
                const m = (el.innerText || '').match(/@([A-Za-z0-9_]+)/);
                return m ? m[1] : null;
            }"""
        )
    except Exception:
        return None


def _find_tweet_url_from_profile(page: Page, text: str) -> str:
    """投稿後に URL を取れなかった場合、プロフィールの最新ツイートから探す。"""
    snippet = _text_snippet_for_match(text)
    user = _current_username(page)
    if not user:
        raise RuntimeError("投稿後のツイート URL を取得できませんでした（ログインユーザー不明）")
    page.goto(f"https://x.com/{user}", timeout=60_000, wait_until="domcontentloaded")
    page.wait_for_timeout(random.uniform(2000, 3000))
    url = page.evaluate(
        r"""(snippet) => {
            const articles = document.querySelectorAll('article[data-testid="tweet"]');
            for (const a of articles) {
                const text = a.innerText || '';
                if (snippet && !text.includes(snippet)) continue;
                const link = a.querySelector('a[href*="/status/"]');
                if (!link) continue;
                const h = link.getAttribute('href') || '';
                if (/\/status\/\d+/.test(h)) {
                    return h.startsWith('http') ? h : ('https://x.com' + h);
                }
            }
            return null;
        }""",
        snippet,
    )
    if not url:
        raise RuntimeError("投稿後のツイート URL を取得できませんでした")
    return str(url).split("?")[0]


def _post_one(page: Page, text: str) -> Dict[str, Any]:
    page.goto(_COMPOSE_URL, timeout=60_000, wait_until="domcontentloaded")
    page.wait_for_timeout(random.uniform(500, 1200))
    try:
        page.wait_for_selector(_COMPOSE_SEL, state="visible", timeout=25_000)
    except PlaywrightTimeoutError:
        if _looks_like_login_page(page.url):
            raise RuntimeError(
                "X にログインしていません。先に次を実行してください: "
                "python x_browser_post.py --login"
            )
        raise RuntimeError("投稿入力欄が見つかりません（未ログインまたはページ構成変更の可能性）")

    _fill_compose(page, text)
    _wait_and_click_post_button(page)

    tweet_url: Optional[str] = None
    try:
        page.wait_for_url("**/status/**", timeout=30_000)
        tweet_url = page.url.split("?")[0]
    except PlaywrightTimeoutError:
        page.wait_for_timeout(random.uniform(2000, 3500))

    if not tweet_url:
        tweet_url = _find_tweet_url_from_profile(page, text)

    m = re.search(r"/status/(\d+)", tweet_url)
    tid = m.group(1) if m else ""
    return {"tweet_id": tid, "tweet_url": tweet_url}


def post_tweet_via_browser(text: str) -> Dict[str, Any]:
    """UI 操作で X に1件投稿（headless / 専用プロファイル）。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("投稿テキストが空です")
    with sync_playwright() as p:
        ctx = _launch_context(p, headless=True)
        try:
            page = _first_page(ctx)
            human_delay(0.3, 0.8)
            return _post_one(page, text)
        finally:
            ctx.close()


def post_tweets_batch_via_browser(
    texts: List[str],
    *,
    interval_min: int = 180,
    interval_max: int = 300,
) -> List[Dict[str, Any]]:
    """複数投稿を1ブラウザセッションで連続実行。"""
    cleaned = [t.strip() for t in texts if (t or "").strip()]
    if not cleaned:
        return []
    results: List[Dict[str, Any]] = []
    with sync_playwright() as p:
        ctx = _launch_context(p, headless=True)
        try:
            page = _first_page(ctx)
            for i, t in enumerate(cleaned):
                if i > 0:
                    wait = random.randint(max(0, int(interval_min)), max(int(interval_min), int(interval_max)))
                    print(f"[X] 次の投稿まで {wait} 秒待機…", flush=True)
                    time.sleep(wait)
                row = _post_one(page, t)
                row["batch_index"] = i
                results.append(row)
        finally:
            ctx.close()
    return results


# ---------- 削除 ----------

def delete_tweet_via_browser(tweet_url: str) -> Dict[str, Any]:
    """ツイート URL を開き UI から削除（headless / 専用プロファイル）。"""
    url = (tweet_url or "").strip()
    if not url:
        raise ValueError("tweet_url が空です")
    if not re.search(r"/status/\d+", url):
        raise ValueError(f"無効な tweet_url: {url}")
    with sync_playwright() as p:
        ctx = _launch_context(p, headless=True)
        try:
            page = _first_page(ctx)
            page.goto(url, timeout=60_000, wait_until="domcontentloaded")
            page.wait_for_selector('article[data-testid="tweet"]', timeout=20_000)
            page.wait_for_timeout(random.uniform(600, 1200))
            page.locator('article[data-testid="tweet"] [data-testid="caret"]').first.click(
                timeout=15_000
            )
            page.wait_for_timeout(random.uniform(400, 900))
            deleted = page.evaluate(
                """() => {
                    const els = Array.from(document.querySelectorAll('[role="menuitem"]'));
                    for (const e of els) {
                        const t = (e.innerText || '').trim();
                        if (t === '削除' || t === 'Delete') { e.click(); return true; }
                    }
                    const byTestId = document.querySelector('[data-testid="delete"]');
                    if (byTestId) { byTestId.click(); return true; }
                    return false;
                }"""
            )
            if not deleted:
                raise RuntimeError("menu item not found: 削除")
            page.wait_for_timeout(random.uniform(400, 900))
            page.locator('[data-testid="confirmationSheetConfirm"]').first.click(timeout=15_000)
            page.wait_for_timeout(random.uniform(800, 1500))
            return {"deleted": True, "tweet_url": url}
        finally:
            ctx.close()


# ---------- CLI ----------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="X ブラウザ自動投稿（Playwright / 専用プロファイル / headless）"
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="表示ウィンドウを開き、X に1回手動ログインしてセッションを保存する",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="headless でログイン状態を確認する",
    )
    parser.add_argument(
        "--post",
        metavar="TEXT",
        help="1件だけ即時投稿する（デバッグ用）",
    )
    args = parser.parse_args()

    if args.login:
        ok = run_login_flow()
        raise SystemExit(0 if ok else 1)
    if args.check:
        ok = check_browser_ready()
        if ok:
            print("[X ブラウザ] ログイン済みです。")
        else:
            print("[X ブラウザ] 未ログイン（または確認失敗）。 --login を実行してください。")
        raise SystemExit(0 if ok else 1)
    if args.post:
        result = post_tweet_via_browser(args.post)
        print(json.dumps(result, ensure_ascii=False))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
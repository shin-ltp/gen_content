"""
参考画像取得モジュール（有名人物向け img2img 用素材の自動収集）

analyze_content.py が analysis.json の各記事に付与した image_reference フィールドを
読み込み、`needs_reference=true` の記事について web 検索で素材写真を取得し
articles/images/NNN_ref.jpg として保存する。

取得した画像は generate_images.py の ComfyUI img2img ワークフローで参照される。

【検索バックエンド】（IMAGE_REFERENCE_SEARCH_BACKENDS で優先順を指定）
1. searxng  — 自托管 SearXNG（既定: http://localhost:8888）の image/web 検索
2. wikimedia — Wikipedia ページ画像 + Wikimedia Commons API（高精度・安定）
3. bing     — Bing Image Search API（IMAGE_REFERENCE_BING_API_KEY 設定時）

【使用方法】
    python fetch_reference_images.py <YYYY-MM-DD>
"""
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image as PILImage

from config import (
    IMAGE_REFERENCE_DOWNLOAD_TIMEOUT,
    IMAGE_REFERENCE_ENABLED,
    IMAGE_REFERENCE_MIN_BYTES,
    IMAGE_REFERENCE_SEARCH_BACKENDS,
    IMAGE_REFERENCE_SEARCH_LIMIT,
    IMAGE_REFERENCE_SEARXNG_ENGINES,
    IMAGE_REFERENCE_SEARXNG_TIMEOUT,
    IMAGE_REFERENCE_SEARXNG_URL,
    IMAGE_REFERENCE_USER_AGENT,
    get_issue_dir,
)
from state_manager import StateManager

# Wikimedia API の User-Agent（厳格なポリシーに準拠するため専用ヘッダ）
_WIKIMEDIA_USER_AGENT = (
    "EconomistPodcastResearch/1.0 "
    "(https://example.org/podcast; research@example.org) python-urllib"
)

# Bing Image Search API（オプション・IMAGE_REFERENCE_BING_API_KEY 設定時のみ）
BING_IMAGE_SEARCH_ENDPOINT = "https://api.bing.microsoft.com/v7.0/images/search"

# ストック写真サイトの検索結果ページ（直接画像 URL ではない）を除外
_SKIP_URL_SUBSTRINGS = (
    "shutterstock.com/search",
    "gettyimages.com/photos",
    "pexels.com/search",
    "pixabay.com/images/search",
    "alamy.com/stock-photo",
    "/search?",
    "/images/search",
)

# AI 生成・壁紙・ファンアート等（人物肖像の参考素材として不適切）
_REJECT_IMAGE_DOMAINS = (
    "stablediffusionweb.com",
    "craiyon.com",
    "wixmp.com",
    "4kwallpapers.com",
    "wallpaper",
    "wallpapers.com",
    "freepik.com/premium-photo",
    "generated-by-ai",
    "imgcdn.stablediffusion",
    "pics.craiyon.com",
)

# 優先するニュース・百科事典ドメイン（スコアリング用）
_PREFERRED_NEWS_DOMAINS = (
    "upload.wikimedia.org",
    "reuters.com",
    "apnews.com",
    "bbc.co",
    "nytimes.com",
    "mainichi.jp",
    "britannica.com",
    "afp.com",
    "cdn.britannica.com",
    "rappler.com",
    "ndtvimg.com",
    "alamy.com/comp/",
)


def _get_bing_api_key() -> str:
    """環境変数から Bing API キーを取得（config に依存しない）。"""
    import os
    return os.getenv("IMAGE_REFERENCE_BING_API_KEY", "").strip()


def _is_direct_image_url(url: str) -> bool:
    if not url or not url.startswith("http"):
        return False
    path = urllib.parse.urlparse(url).path.lower()
    return bool(re.search(r"\.(jpe?g|png|webp|gif)(\?|$)", path, re.I))


def _is_rejected_image_url(url: str) -> bool:
    lower = url.lower()
    return any(d in lower for d in _REJECT_IMAGE_DOMAINS)


def _score_image_url(url: str) -> int:
    """URL の優先度スコア（高いほど良い）。負値は除外。"""
    if not url or _is_rejected_image_url(url):
        return -1
    lower = url.lower()
    if "upload.wikimedia.org" in lower and "/thumb/" not in lower:
        return 100
    if "upload.wikimedia.org" in lower:
        return 90
    for i, domain in enumerate(_PREFERRED_NEWS_DOMAINS):
        if domain in lower:
            return 70 - i
    if _is_direct_image_url(url):
        return 10
    return -1


def _rank_image_urls(urls: list[str], limit: int | None = None) -> list[str]:
    """スコア降順に並べ替え、同一スコア内は元の順序を維持。"""
    scored = [(u, _score_image_url(u)) for u in urls]
    ranked = [u for u, s in scored if s >= 0]
    ranked.sort(key=lambda u: _score_image_url(u), reverse=True)
    ranked = _dedupe_urls(ranked)
    if limit is not None:
        return ranked[:limit]
    return ranked


def _is_usable_image_candidate(url: str) -> bool:
    if not url:
        return False
    if _is_rejected_image_url(url):
        return False
    lower = url.lower()
    if any(s in lower for s in _SKIP_URL_SUBSTRINGS):
        return False
    if "upload.wikimedia.org" in lower:
        return True
    return _is_direct_image_url(url)


def _dedupe_urls(urls: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _searxng_search(
    query: str,
    *,
    categories: str | None = None,
) -> list[dict]:
    """SearXNG JSON API で検索する。IMAGE_REFERENCE_SEARXNG_URL 未設定時は空リスト。"""
    base = IMAGE_REFERENCE_SEARXNG_URL
    if not base:
        return []

    params: dict[str, str] = {"q": query, "format": "json"}
    if categories:
        params["categories"] = categories
    if IMAGE_REFERENCE_SEARXNG_ENGINES:
        params["engines"] = IMAGE_REFERENCE_SEARXNG_ENGINES

    url = f"{base}/search?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": IMAGE_REFERENCE_USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=IMAGE_REFERENCE_SEARXNG_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"      [警告] SearXNG 検索失敗 ({query[:60]}): {e}")
        return []

    unresponsive = data.get("unresponsive_engines") or []
    if unresponsive:
        brief = ", ".join(f"{e[0]}({e[1]})" for e in unresponsive[:3] if isinstance(e, list))
        if brief:
            print(f"      [情報] SearXNG 未応答: {brief}")

    return data.get("results") or []


def _extract_image_urls_from_searxng_results(results: list[dict]) -> list[str]:
    """SearXNG 結果から直接ダウンロード可能な画像 URL を抽出する。"""
    urls: list[str] = []
    for item in results:
        for key in ("img_src", "thumbnail"):
            u = (item.get(key) or "").strip()
            if u and _is_usable_image_candidate(u):
                urls.append(u)
        u = (item.get("url") or "").strip()
        if _is_usable_image_candidate(u):
            urls.append(u)
    return _dedupe_urls(urls)


def _extract_wikipedia_title_from_searxng_results(results: list[dict]) -> str | None:
    """SearXNG 結果の URL から Wikipedia 記事タイトルを抽出する。"""
    for item in results:
        u = item.get("url") or ""
        m = re.search(r"wikipedia\.org/wiki/([^#?]+)", u, re.I)
        if m:
            return urllib.parse.unquote(m.group(1).replace("_", " "))
    return None


def _fetch_searxng_image_urls(query: str, count: int) -> list[str]:
    """SearXNG の image カテゴリ（＋必要なら general）で画像 URL を取得する。"""
    results = _searxng_search(query, categories="images")
    urls = _extract_image_urls_from_searxng_results(results)

    if len(urls) < count:
        web_results = _searxng_search(f"{query} photo portrait", categories="general")
        for u in _extract_image_urls_from_searxng_results(web_results):
            if u not in urls:
                urls.append(u)

    if urls:
        print(f"      [情報] SearXNG 画像 URL: {len(urls)} 件（フィルタ前）")
    return _rank_image_urls(urls, limit=count)


def _searxng_find_wikipedia_title(name: str) -> str | None:
    """SearXNG web 検索で Wikipedia 記事タイトルを見つける。"""
    for query in (f"{name} wikipedia", name):
        results = _searxng_search(query, categories="general")
        title = _extract_wikipedia_title_from_searxng_results(results)
        if title:
            print(f"      [情報] SearXNG → Wikipedia: {title}")
            return title
        results = _searxng_search(query, categories="images")
        title = _extract_wikipedia_title_from_searxng_results(results)
        if title:
            print(f"      [情報] SearXNG (images) → Wikipedia: {title}")
            return title
    return None


def _wikimedia_page_image_by_title(title: str) -> str | None:
    """Wikipedia 記事タイトルからページ画像 URL を取得する。"""
    img_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "piprop": "original",
        "format": "json",
    })
    req = urllib.request.Request(img_url, headers={
        "User-Agent": _WIKIMEDIA_USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        original = page.get("original")
        if original:
            return original.get("source")
    return None


def _wikimedia_page_image(name: str) -> str | None:
    """Wikipedia 記事のメインページ画像（肖像）URL を取得する。

    pageimages API は記事の代表的な画像 1 枚を返すため、人物肖像の取得に最適。
    """
    # 1. 記事検索で正確なタイトルを取得
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": name,
        "srlimit": "1",
        "format": "json",
    })
    req = urllib.request.Request(search_url, headers={
        "User-Agent": _WIKIMEDIA_USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"      [警告] Wikipedia 検索失敗 ({name}): {e}")
        return None

    hits = data.get("query", {}).get("search", [])
    if not hits:
        return None

    title = hits[0]["title"]
    print(f"      [情報] Wikipedia 記事: {title}")
    return _wikimedia_page_image_by_title(title)


def _wikimedia_commons_search(query: str, limit: int) -> list[str]:
    """Wikimedia Commons で画像を検索し URL リストを返す（フォールバック用）。"""
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|mime",
        "format": "json",
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": _WIKIMEDIA_USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        print(f"      [警告] Wikimedia Commons 検索失敗 ({query}): {e}")
        return []

    results = []
    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        imageinfo = page.get("imageinfo", [])
        if imageinfo:
            img_url = imageinfo[0].get("url")
            mime = imageinfo[0].get("mime", "")
            # 画像のみ（SVG 等は除外）
            if img_url and mime.startswith("image/") and mime != "image/svg+xml":
                results.append(img_url)
    return results


def _fetch_bing_images(query: str, count: int) -> list[str]:
    """Bing Image Search API で画像 URL のリストを取得する（オプション）。

    戻り値: 画像 URL 文字列のリスト（失敗時は空リスト）
    """
    api_key = _get_bing_api_key()
    if not api_key:
        return []

    params = urllib.parse.urlencode({
        "q": query,
        "count": str(count),
        "safeSearch": "Moderate",
        "aspect": "Square",
        "imageType": "Photo",
    })
    url = f"{BING_IMAGE_SEARCH_ENDPOINT}?{params}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("Ocp-Apim-Subscription-Key", api_key)
    req.add_header("User-Agent", IMAGE_REFERENCE_USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError) as e:
        print(f"      [警告] Bing Image Search 失敗 ({query}): {e}")
        return []

    results = []
    for item in data.get("value", []):
        img_url = item.get("contentUrl") or item.get("thumbnailUrl")
        if img_url:
            results.append(img_url)
        if len(results) >= count:
            break
    return results


def _search_person_image(name: str, query: str, count: int) -> list[str]:
    """人物肖像画像の URL を IMAGE_REFERENCE_SEARCH_BACKENDS の順で検索し、スコア順に返す。"""
    urls: list[str] = []
    collect_limit = max(count * 4, 20)

    for backend in IMAGE_REFERENCE_SEARCH_BACKENDS:
        if backend == "searxng":
            if not IMAGE_REFERENCE_SEARXNG_URL:
                continue
            searxng_urls = _fetch_searxng_image_urls(query, collect_limit)
            for u in searxng_urls:
                if u not in urls:
                    urls.append(u)
            wiki_title = _searxng_find_wikipedia_title(name)
            if wiki_title:
                wiki_url = _wikimedia_page_image_by_title(wiki_title)
                if wiki_url and wiki_url not in urls:
                    urls.append(wiki_url)
                    print(f"      [情報] SearXNG 経由 Wikipedia 画像: {wiki_url[:80]}")

        elif backend == "wikimedia":
            wiki_url = _wikimedia_page_image(name)
            if wiki_url and wiki_url not in urls:
                urls.append(wiki_url)
                print(f"      [情報] Wikipedia ページ画像: {wiki_url[:80]}")

            commons = _wikimedia_commons_search(f"{name} portrait", collect_limit)
            for u in commons:
                if u not in urls:
                    urls.append(u)
            if commons:
                print(f"      [情報] Wikimedia Commons: {len(commons)} 件追加")

        elif backend == "bing":
            if _get_bing_api_key():
                bing_urls = _fetch_bing_images(query, collect_limit)
                for u in bing_urls:
                    if u not in urls:
                        urls.append(u)

    ranked = _rank_image_urls(urls, limit=count)
    if ranked:
        top = ranked[0]
        print(f"      [情報] 最優先 URL (score={_score_image_url(top)}): {top[:80]}")
    return ranked


def _download_and_validate_image(url: str, min_bytes: int) -> bytes | None:
    """画像 URL からダウンロードし、PIL で開けることを検証する。

    戻り値: 画像のバイト列（JPEG 正規化済み）、失敗時は None
    """
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", IMAGE_REFERENCE_USER_AGENT)

    try:
        with urllib.request.urlopen(req, timeout=IMAGE_REFERENCE_DOWNLOAD_TIMEOUT) as resp:
            raw = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ConnectionError):
        return None

    if len(raw) < min_bytes:
        return None

    try:
        img = PILImage.open(io.BytesIO(raw))
        img.verify()
        img = PILImage.open(io.BytesIO(raw))
        if img.mode not in ("RGB", "RGBA", "L"):
            return None
        # JPEG に正規化して返す（ComfyUI LoadImage 互換性）
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        return buf.getvalue()
    except Exception:
        return None


class ReferenceImageFetcher:
    """参考画像取得クラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.images_dir = self.output_dir / "articles" / "images"

    def _load_analysis(self) -> list[dict] | None:
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            print(f"[エラー] {analysis_path} が見つかりません。先に analyze_content を実行してください。")
            return None
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[エラー] analysis.json の読み込みに失敗: {e}")
            return None

    def _has_reference_image(self, aid: int) -> bool:
        """参考画像が既に存在するか確認。"""
        for ext in ("jpg", "jpeg", "png", "webp"):
            ref_path = self.images_dir / f"{int(aid):03d}_ref.{ext}"
            if ref_path.exists():
                return True
        return False

    def _fetch_for_article(self, article: dict) -> bool:
        """1 記事について参考画像を取得・保存する。成功時 True。"""
        aid = article.get("id")
        ref_info = article.get("image_reference") or {}
        if not ref_info.get("needs_reference"):
            return False

        if self._has_reference_image(aid):
            print(f"    [{int(aid):03d}] スキップ（既存）: {ref_info.get('subject_name', '')}")
            return True

        subject_name = ref_info.get("subject_name") or ""
        if not subject_name:
            print(f"    [{int(aid):03d}] subject_name が空、スキップ")
            return False

        search_query = ref_info.get("search_query") or f"{subject_name} official portrait"
        backends_label = ",".join(IMAGE_REFERENCE_SEARCH_BACKENDS)
        print(f"    [{int(aid):03d}] 検索中: {subject_name} [{backends_label}]")
        urls = _search_person_image(subject_name, search_query, IMAGE_REFERENCE_SEARCH_LIMIT)
        if not urls:
            print(f"      → 画像が見つかりませんでした")
            return False

        self.images_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.images_dir / f"{int(aid):03d}_ref.jpg"

        for idx, url in enumerate(urls):
            print(f"      [{idx + 1}/{len(urls)}] ダウンロード試行…")
            raw = _download_and_validate_image(url, IMAGE_REFERENCE_MIN_BYTES)
            if raw:
                out_path.write_bytes(raw)
                print(f"      → 保存: {out_path} ({len(raw):,} bytes)")
                return True
            time.sleep(0.3)

        print(f"      → 全候補の取得に失敗しました")
        return False

    def process_all_articles(self) -> bool:
        """analysis.json 内の needs_reference=true 記事全てについて参考画像を取得する。"""
        if not IMAGE_REFERENCE_ENABLED:
            print("[情報] IMAGE_REFERENCE_ENABLED=0 のため参考画像取得をスキップします。")
            return True

        articles = self._load_analysis()
        if articles is None:
            return False

        targets = [
            a for a in articles
            if a.get("status") == "KEEP"
            and (a.get("image_reference") or {}).get("needs_reference")
        ]

        if not targets:
            print("[情報] 参考画像が必要な記事はありません。")
            return True

        print(f"\n[処理中] {len(targets)} 篇の参考画像を取得")
        if IMAGE_REFERENCE_SEARXNG_URL:
            print(f"  SearXNG: {IMAGE_REFERENCE_SEARXNG_URL}")
        print(f"  バックエンド順: {', '.join(IMAGE_REFERENCE_SEARCH_BACKENDS)}")

        success_count = 0
        for article in targets:
            if self._fetch_for_article(article):
                success_count += 1
            time.sleep(0.5)

        print(
            f"[完了] 参考画像取得: {success_count}/{len(targets)} 件成功"
            f"（{len(targets) - success_count} 件失敗・t2i で代替生成されます）"
        )
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python fetch_reference_images.py <YYYY-MM-DD>")
        sys.exit(1)

    issue_date = sys.argv[1]
    fetcher = ReferenceImageFetcher(issue_date)
    if not fetcher.process_all_articles():
        sys.exit(1)

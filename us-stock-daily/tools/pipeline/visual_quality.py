"""Deterministic image-acquisition quality rules shared by the visual stage.

2026-09-24 contract (fix list B):
- Photograph keywords must name a *photographable* entity (company,
  institution, person, product, building). Indices/ETFs/market moods are
  abstract: search cannot picture them, so route them to generation or to a
  proxy entity (S&P 500 -> NYSE building).
- Content-farm / clipart / GIF domains are rejected before download.
- Thumbnail CDN URLs are normalized to full-resolution variants.
- Wikimedia Commons is queried before the general image search: it always
  returns real photos at original resolution.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.error
import urllib.request

# Domains that systematically serve clipart/decorative or animated results.
BLACKLIST_DOMAINS = {
    "animalia-life.club", "clipartmax.com", "clipart-library.com",
    "clipart-panda.com", "cleanpng.com", "pngtree.com", "pngitem.com",
    "pngwing.com", "pngfre.com", "tenor.com", "giphy.com", "gfycat.com",
    "note.com", "kinsta.com", "digitalspy.com", "cabinetjournal.org",
    "storage.googleapis.com", "freepik.com",
    "flaticon.com", "iconfinder.com", "vecteezy.com", "brighthubpm.com",
    "tutcom.org", "wikihow.com", "pinterest.com", "pinimg.com",
    "shutterstock.com", "gettyimages.co.jp", "istockphoto.com",
    "dreamstime.com", "123rf.com", "depositphotos.com",
    "alamy.com", "alamy.it", "icim-magazine.com", "middlemind.co",
    "onlyinyourstate.com", "mothereahnews.com", "motherearthnews.com",
    "thespruce.com", "realtor.com", "i.kinja-img.com",
    # MSN/aggregator video thumbnails carry burned-in captions (2026-09-24
    # B2-p4 adopted a news-video screenshot with a headline overlay).
    "msn.com",
}

# Substrings checked against the full URL (any position, path included).
BLACKLIST_URL_SUBSTRINGS = (
    "/clipart", "/pngtree", "/icon-", "/icon/", "/gif/", "/animated-",
    "/stock-photo", "/stock-image", "/editorial-image",
    "clip-art", "cartoon",
)

# Abstract financial concepts that can never be photographed directly.
ABSTRACT_PATTERNS = re.compile(
    r"S&P\s*500|S&P500|NASDAQ[- ]?COMPOSITE|NASDAQ100|DOW[- ]?JONES|"
    r"NYSE\s*COMPOSITE|RUSSELL\s*(?:1000|2000|3000)|TOPIX|NIKKEI|"
    r"VIX|CCI|CPI|PPI|GDP|ETF\b|ETN\b|market\s*(?:sentiment|mood)|"
    r"株価指数|指数|市場心理|センチメント|市況|金利水準|バリュエーション|"
    r"risk[- ]off|risk[- ]on|bull\s*market|bear\s*market|強気相場|弱気相場|"
    r"yield\s*curve|利回り曲線|capital\s*flow|資金フロー|volatility|ボラティリティ",
    re.I,
)

# Photographable proxies for famous abstract subjects (pattern -> query).
PROXY_ENTITIES = [
    (re.compile(r"S&P\s*-?\s*500", re.I), "NYSE New York Stock Exchange building"),
    (re.compile(r"NASDAQ[- ]?(?:COMPOSITE|100)?", re.I), "NASDAQ MarketSite tower New York"),
    (re.compile(r"DOW[- ]?JONES", re.I), "Wall Street sign New York"),
    (re.compile(r"(?:US|米国)?(?:TREASURY|国債|財務省)", re.I), "US Treasury Building Washington"),
    (re.compile(r"FOMC|FED|FRB|連邦準備", re.I), "Eccles Building Federal Reserve"),
    (re.compile(r"NIKKEI|日経平均", re.I), "Nikkei building Tokyo Nishijin"),
    (re.compile(r"WHITE\s*HOUSE|ホワイトハウス", re.I), "White House north facade"),
    (re.compile(r"CAPITOL|議会議事堂", re.I), "US Capitol building Washington"),
]


def is_abstract_subject(text: str) -> bool:
    return bool(ABSTRACT_PATTERNS.search(text or ""))


def proxy_query(text: str) -> str | None:
    """Map an abstract index/institution subject to a photographable proxy."""
    for pattern, query in PROXY_ENTITIES:
        if pattern.search(text or ""):
            return query
    return None


def url_domain(url: str) -> str:
    try:
        host = urllib.parse.urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().lstrip(".")


def is_blacklisted(url: str) -> bool:
    domain = url_domain(url)
    if not domain:
        return True
    bare = re.sub(r"^www\.", "", domain)
    parts = bare.split(".")
    hosts = {bare} | {".".join(parts[i:]) for i in range(len(parts) - 1)}
    if hosts & BLACKLIST_DOMAINS:
        return True
    lowered = url.lower()
    return any(s in lowered for s in BLACKLIST_URL_SUBSTRINGS)


def fullres_url(url: str) -> str:
    """Best-effort thumbnail -> original URL normalization for known CDNs."""
    d = url_domain(url)
    if "thumbs.dreamstime" in d:
        m = re.search(r"thumbs\.dreamstime\.com(/blog)?/", url)
        if m:
            return "https://previews-01.dreamstime.com" + url[m.end() - 1:]
    if re.search(r"\balamy\.", d):
        return re.sub(r"https?://[a-z0-9]+\.alamy\.[a-z]+/", "https://c8.alamy.com/", url)
    # Generic 400px-style thumbnail suffixes on stock CDNs.
    url = re.sub(r"[-_](?:400x[0-9]+|[0-9]{2,3}w|thumb(?:nail)?)(\.[a-z]{3,4})$", r"\1",
                 url, flags=re.I)
    url = re.sub(r"/(?:resize|thumb)/", "/", url, flags=re.I)
    return url


def tokens(text: str) -> set[str]:
    return {
        t.lower() for t in re.findall(r"[A-Za-z][A-Za-z0-9&.%'-]{2,}", text or "")
    } - {
        "the", "and", "for", "with", "from", "its", "this", "that", "photo",
        "image", "stock", "high", "resolution", "building", "headquarters",
    }


def entity_overlap(title: str, url: str, keyword: str) -> float:
    """Fraction of keyword content words found in result title+URL."""
    kt = tokens(keyword)
    if not kt:
        return 1.0
    hay = tokens(f"{title} {url}")
    return len(kt & hay) / len(kt)


def wikimedia_search(keyword: str, limit: int = 4) -> list[dict]:
    """Query Wikimedia Commons file search; returns full-res photo candidates."""
    params = {
        "action": "query", "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {keyword}",
        "gsrnamespace": "6", "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
    }
    url = ("https://commons.wikimedia.org/w/api.php?"
           + urllib.parse.urlencode(params))
    req = urllib.request.Request(url, headers={
        "User-Agent": COMMONS_UA,
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 - best-effort layer
        return []
    out: list[dict] = []
    pages = (data.get("query") or {}).get("pages") or {}
    for page in sorted(pages.values(), key=lambda p: p.get("index", 99)):
        info = (page.get("imageinfo") or [{}])[0]
        u = info.get("url", "")
        mime = info.get("mime", "")
        w, h = info.get("width", 0), info.get("height", 0)
        if not u or not mime.startswith("image/") or mime == "image/svg+xml":
            continue
        if min(w, h) < 400 or max(w, h) < 800:
            continue
        out.append({
            "img_src": u,
            "thumbnail_src": u,
            "url": "https://commons.wikimedia.org/wiki/"
                   + urllib.parse.quote(page.get("title", "").replace(" ", "_")),
            "title": page.get("title", ""),
        })
    return out


COMMONS_UA = (
    "us-stock-daily-bot/1.0 (https://localhost; content pipeline research; "
    "contact: local-operator) python-urllib"
)


def download_image(url: str, timeout: int = 30,
                   retries: int = 2) -> tuple[bytes, str]:
    """Fetch image bytes with UA compliance and 429/5xx backoff.

    Returns (payload, content_type); raises on final failure.
    """
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": (COMMONS_UA if "wikimedia" in url or "wikipedia" in url
                               else "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"),
                "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                ctype = resp.headers.get("Content-Type", "").split(";")[0]
                return resp.read(20 * 1024 * 1024), ctype
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (403, 429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
        except Exception as e:  # noqa: BLE001 - timeouts etc. fail fast here
            last = e
            if attempt + 1 < retries:
                time.sleep(1.5)
                continue
            raise
    raise RuntimeError(f"download failed: {last}")

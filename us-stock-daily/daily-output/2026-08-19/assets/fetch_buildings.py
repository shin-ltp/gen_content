"""2026-08-19 Phase 3: HQ/building photo fetch (photo-first policy).

Pipeline: SearXNG images -> filter bad hosts / low resolution -> download from
original host. Fallback: Wikimedia Commons search API + delayed download.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BRANDS = Path(r"D:\work\gen_content\us-stock-daily\assets\brands\companies")
SEARX = "http://127.0.0.1:8888/search"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0"
LOG = BRANDS / "_sources.log"

BAD_HOSTS = (
    "istockphoto", "shutterstock", "gettyimages", "alamy", "dreamstime",
    "adobe", "depositphotos", "123rf", "pinterest", "flickr", "ebay",
    "reddit", "facebook", "twitter", "instagram", "tiktok", "youtube",
    "linkedin", "wallpaper", "clipart", "pngtree", "cleanpng", "pngegg",
    "seeklogo", "worldvectorlogo", "brandsoftheworld", "vectorseek",
    "svgrepo", "wikia", "fandom", "ytimg",
)

PLAN = {
    "walmart-hq": ["Walmart headquarters Bentonville building"],
    "target-hq": ["Target headquarters Minneapolis building exterior"],
    "federal-reserve-hq": ["Federal Reserve Eccles Building Washington DC"],
    "meta-hq": ["Meta headquarters Menlo Park building exterior"],
    "hd-hq": ["Home Depot store exterior building", "The Home Depot Atlanta headquarters"],
    "tsmc-hq": ["TSMC headquarters Hsinchu building"],
    "berkshire-hq": ["Kiewit Plaza Omaha building", "Berkshire Hathaway headquarters Omaha"],
    "apple-hq": ["Apple Park Cupertino building aerial"],
    "microsoft-hq": ["Microsoft headquarters Redmond building campus"],
    "anthropic-hq": ["Anthropic office San Francisco building"],
    "coreweave-hq": ["CoreWeave headquarters building", "CoreWeave data center exterior"],
}


def log(msg: str) -> None:
    print(msg, flush=True)


def log_source(slug: str, url: str, source: str) -> None:
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{slug} | {url} | {source} | {time.strftime('%Y-%m-%d')}\n")


def http_get_json(url: str, timeout: int = 60) -> dict | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        log(f"  GET ERR: {e}")
        return None


def download(url: str, dest: Path, referrer: str | None = None) -> bool:
    headers = {"User-Agent": UA}
    if referrer:
        headers["Referer"] = referrer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = resp.read()
    except Exception as e:
        log(f"  download ERR: {e}")
        return False
    if len(data) < 15000:
        log(f"  too small ({len(data)} B), dropped")
        return False
    dest.write_bytes(data)
    log(f"  saved: {len(data) // 1024} KB")
    return True


def searx_images(query: str) -> list[dict]:
    from urllib.parse import quote
    url = f"{SEARX}?q={quote(query)}&format=json&categories=images"
    data = http_get_json(url)
    if not data:
        return []
    results = data.get("results") or []
    out = []
    for r in results:
        src = r.get("img_src") or ""
        page = r.get("url") or ""
        if not src:
            continue
        if any(b in src for b in BAD_HOSTS) or any(b in page for b in BAD_HOSTS):
            continue
        m = re.match(r"(\d+)", r.get("resolution") or "")
        if m and int(m.group(1)) < 800:
            continue
        out.append(r)
    return out


def commons_search(query: str, width: int = 1600) -> tuple[str, str] | None:
    from urllib.parse import quote
    api = (
        "https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch="
        f"{quote(query)}&srnamespace=6&srlimit=6&format=json"
    )
    data = http_get_json(api, timeout=30)
    if not data:
        return None
    time.sleep(2)
    for s in data.get("query", {}).get("search", []):
        title = s.get("title", "")
        if not re.search(r"\.(jpg|jpeg|png|webp)$", title, re.I):
            continue
        api2 = (
            "https://commons.wikimedia.org/w/api.php?action=query&titles="
            f"{quote(title)}&prop=imageinfo&iiprop=url|size&iiurlwidth={width}&format=json"
        )
        d2 = http_get_json(api2, timeout=30)
        time.sleep(2)
        if not d2:
            continue
        pages = d2.get("query", {}).get("pages", {})
        page = next(iter(pages.values()), {})
        info = (page.get("imageinfo") or [{}])[0]
        if info.get("thumburl") and info.get("width", 0) > width:
            return info["thumburl"], title
        if info.get("url"):
            return info["url"], title
    return None


def main() -> int:
    failed = []
    for slug, queries in PLAN.items():
        dest = BRANDS / f"{slug}.jpg"
        if dest.exists():
            log(f"[{slug}] exists, skip")
            continue
        log(f"=== [{slug}] ===")
        ok = False
        for q in queries:
            log(f"  searx: {q}")
            for cand in searx_images(q)[:8]:
                host = cand["img_src"].split("/")[2] if "//" in cand["img_src"] else "?"
                log(f"  try: {host} ({cand.get('resolution', '?')})")
                if download(cand["img_src"], dest, referrer=cand.get("url")):
                    ok = True
                    log_source(slug, cand["img_src"], f"searx:{q}")
                    break
                time.sleep(1)
            if ok:
                break
            time.sleep(2)
        if not ok:
            for q in queries:
                log(f"  commons: {q}")
                found = commons_search(q)
                if found:
                    url, title = found
                    log(f"  commons file: {title}")
                    if download(url, dest):
                        ok = True
                        log_source(slug, url, f"wikimedia:{q}")
                        break
                time.sleep(3)
        if not ok:
            log(f"  FAILED: {slug}")
            failed.append(slug)
    log("\n=== CURRENT HQ FILES ===")
    for f in sorted(BRANDS.glob("*-hq.*")):
        log(f"{f.name} {f.stat().st_size // 1024} KB")
    if failed:
        log(f"\nFAILED list: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Re-fetch Jim Cramer photo, only accepting CNBC-hosted pages."""
import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0"
SEARX = "http://127.0.0.1:8888/search"
DAILY = Path(r"D:\work\gen_content\us-stock-daily\daily-output\2026-08-19\assets\people")


def searx(q: str) -> dict:
    url = f"{SEARX}?q={quote(q)}&format=json&categories=images"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def dl(url: str, dest: Path, ref: str | None = None) -> tuple[bool, str]:
    h = {"User-Agent": UA}
    if ref:
        h["Referer"] = ref
    req = urllib.request.Request(url, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            data = r.read()
        if len(data) < 12000:
            return False, "too small"
        dest.write_bytes(data)
        return True, f"{len(data) // 1024}KB"
    except Exception as e:
        return False, str(e)[:90]


QUERIES = [
    "Jim Cramer site:cnbc.com",
    "Jim Cramer Mad Money site:cnbc.com",
    "\"Jim Cramer\" CNBC anchor investing club",
]


def main() -> None:
    dest = DAILY / "jim-cramer.jpg"
    ok = False
    for q in QUERIES:
        print(f"q: {q}", flush=True)
        try:
            data = searx(q)
        except Exception as e:
            print(f"  searx ERR {str(e)[:80]}", flush=True)
            continue
        for r in data.get("results", []):
            src = r.get("img_src") or ""
            page = r.get("url") or ""
            if not src:
                continue
            # Accept only if the PAGE is a trustworthy domain
            if "cnbc.com" not in page and "nbcuni" not in src:
                continue
            m = re.match(r"(\d+)", r.get("resolution") or "")
            if m and int(m.group(1)) < 400:
                continue
            host = src.split("/")[2] if "//" in src else "?"
            print(f"  try {host} ({r.get('resolution')}) page={page[:80]}", flush=True)
            good, info = dl(src, dest, page)
            print(f"  -> {info}", flush=True)
            if good:
                ok = True
                with open(DAILY.parent / "_people_sources.log", "a", encoding="utf-8") as f:
                    f.write(f"jim-cramer.jpg | {src} | {page} | retry3-2026-08-23\n")
                break
            time.sleep(1)
        if ok:
            break
        time.sleep(2)
    print("OK" if ok else "FAILED", flush=True)


if __name__ == "__main__":
    main()

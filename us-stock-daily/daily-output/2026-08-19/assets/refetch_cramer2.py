"""Fetch higher-res Jim Cramer photo from CNBC media CDN."""
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
        if len(data) < 40000:
            return False, f"too small {len(data)//1024}KB"
        dest.write_bytes(data)
        return True, f"{len(data) // 1024}KB"
    except Exception as e:
        return False, str(e)[:90]


QUERIES = [
    "Jim Cramer site:cnbc.com",
    "Jim Cramer Mad Money CNBC photo",
    "Jim Cramer CNBC television anchor",
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
        # sort candidates by resolution desc
        cands = []
        for r in data.get("results", []):
            src = r.get("img_src") or ""
            page = r.get("url") or ""
            if not src:
                continue
            if "cnbc" not in src and "cnbc" not in page and "nbcuni" not in src:
                continue
            m = re.match(r"(\d+)", r.get("resolution") or "")
            w = int(m.group(1)) if m else 0
            if w < 700:
                continue
            cands.append((w, r))
        cands.sort(key=lambda x: -x[0])
        print(f"  {len(cands)} CNBC candidates", flush=True)
        for w, r in cands:
            src = r["img_src"]
            host = src.split("/")[2] if "//" in src else "?"
            print(f"  try {host} w={w} ({r.get('resolution')})", flush=True)
            good, info = dl(src, dest, r.get("url"))
            print(f"  -> {info}", flush=True)
            if good:
                ok = True
                with open(DAILY.parent / "_people_sources.log", "a", encoding="utf-8") as f:
                    f.write(f"jim-cramer.jpg | {src} | {r.get('url','')} | retry4-2026-08-23\n")
                break
            time.sleep(1)
        if ok:
            break
        time.sleep(2)
    print("OK" if ok else "FAILED", flush=True)


if __name__ == "__main__":
    main()

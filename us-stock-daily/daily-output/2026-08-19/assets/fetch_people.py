"""Fetch person photos for quoted analysts (photo-first policy: people)."""
import json
import re
import time
import urllib.request
from pathlib import Path
from urllib.parse import quote

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0"
SEARX = "http://127.0.0.1:8888/search"
DAILY = Path(r"D:\work\gen_content\us-stock-daily\daily-output\2026-08-19\assets\people")
DAILY.mkdir(parents=True, exist_ok=True)
BAD = (
    "istockphoto", "shutterstock", "gettyimages", "alamy", "dreamstime", "adobe",
    "depositphotos", "123rf", "pinterest", "vecteezy", "freepik", "pngtree",
    "cleanpng", "wikia", "fandom", "ytimg", "twitter", "reddit", "instagram",
    "tiktok", "facebook",
)


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
        return False, str(e)[:80]


JOBS = {
    "jim-cramer.jpg": [
        "Jim Cramer CNBC Mad Money portrait",
        "Jim Cramer CNBC host photo",
    ],
    "ben-thompson.jpg": [
        "Ben Thompson Stratechery author",
        "Ben Thompson Stratechery portrait",
    ],
}


def main() -> None:
    for dest_name, queries in JOBS.items():
        dest = DAILY / dest_name
        if dest.exists():
            print(f"[{dest_name}] exists, skip", flush=True)
            continue
        ok = False
        for q in queries:
            print(f"[{dest_name}] {q}", flush=True)
            try:
                data = searx(q)
            except Exception as e:
                print(f"  searx ERR {str(e)[:80]}", flush=True)
                continue
            for r in data.get("results", []):
                src = r.get("img_src") or ""
                page = r.get("url") or ""
                if not src or any(b in src for b in BAD) or any(b in page for b in BAD):
                    continue
                m = re.match(r"(\d+)", r.get("resolution") or "")
                if m and int(m.group(1)) < 500:
                    continue
                host = src.split("/")[2] if "//" in src else "?"
                print(f"  try {host} ({r.get('resolution')})", flush=True)
                good, info = dl(src, dest, page)
                print(f"  -> {info}", flush=True)
                if good:
                    ok = True
                    with open(DAILY.parent / "_people_sources.log", "a", encoding="utf-8") as f:
                        f.write(f"{dest_name} | {src} | {page} | 2026-08-23\n")
                    break
                time.sleep(1)
            if ok:
                break
            time.sleep(2)
        if not ok:
            print(f"  FAILED {dest_name}", flush=True)


if __name__ == "__main__":
    main()

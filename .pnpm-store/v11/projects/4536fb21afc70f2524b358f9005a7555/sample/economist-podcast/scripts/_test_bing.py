"""Bing HTML スクレイピングの検証（murl 抽出）"""
import io
import re
import sys
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

queries = [
    "Elon Musk official portrait",
    "Sanae Takaichi official portrait",
    "Xi Jinping official portrait",
]

for q in queries:
    print(f"\n{'='*60}\nQuery: {q}\n{'='*60}")
    url = "https://www.bing.com/images/search?q=" + urllib.parse.quote(q)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        html = resp.read().decode("utf-8", "replace")
        print(f"HTML length: {len(html)}")
        # murl パターン（Bing の画像メタデータ）
        urls = re.findall(r'murl&quot;:&quot;(https?://[^&]+)&quot;', html)
        jpg = [u for u in urls if re.search(r"\.(jpg|jpeg|png|webp)", u, re.I)]
        print(f"murl image count: {len(jpg)}")
        for i, u in enumerate(jpg[:6], 1):
            print(f"  [{i}] {u[:120]}")
    except Exception as e:
        print(f"ERROR: {e}")

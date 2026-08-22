"""Wikimedia Commons / Wikipedia API で人物の公式肖像画を取得する検証"""
import io
import json
import sys
import urllib.parse
import urllib.request

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HEADERS = {
    "User-Agent": "EconomistPodcastResearch/1.0 (https://example.org/podcast; research@example.org) python-urllib",
    "Accept": "application/json",
}


def search_wikipedia_person(name: str) -> dict | None:
    """Wikipedia の記事を検索し、最初の結果のページ画像を取得する。"""
    # 1. 記事検索
    search_url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": name,
        "srlimit": "1",
        "format": "json",
    })
    req = urllib.request.Request(search_url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  検索エラー: {e}")
        return None

    hits = data.get("query", {}).get("search", [])
    if not hits:
        print(f"  記事が見つかりません")
        return None

    title = hits[0]["title"]
    print(f"  Wikipedia 記事: {title}")
    return _get_page_image(title)


def _get_page_image(title: str) -> dict | None:
    """Wikipedia 記事のページ画像（Original）を取得する。"""
    url = "https://en.wikipedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "titles": title,
        "prop": "pageimages",
        "piprop": "original",
        "format": "json",
    })
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  ページ画像エラー: {e}")
        return None

    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        original = page.get("original")
        if original:
            return {"title": title, "url": original["source"], "width": original.get("width"), "height": original.get("height")}
    print(f"  ページ画像なし")
    return None


def search_wikimedia_commons(query: str, limit: int = 5) -> list[dict]:
    """Wikimedia Commons で画像を検索する。"""
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode({
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": "800",
        "format": "json",
    })
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  Commons 検索エラー: {e}")
        return []

    results = []
    pages = data.get("query", {}).get("pages", {})
    for pid, page in pages.items():
        imageinfo = page.get("imageinfo", [])
        if imageinfo:
            info = imageinfo[0]
            results.append({
                "title": page.get("title", ""),
                "url": info.get("url", ""),
                "thumburl": info.get("thumburl", ""),
                "width": info.get("width"),
                "height": info.get("height"),
                "mime": info.get("mime", ""),
            })
    return results


if __name__ == "__main__":
    targets = [
        ("Sanae Takaichi", "高市早苗"),
        ("Elon Musk", "イーロン・マスク"),
        ("Xi Jinping", "習近平"),
    ]

    for en_name, ja_name in targets:
        print(f"\n{'='*60}")
        print(f"{ja_name} ({en_name})")
        print(f"{'='*60}")

        print("\n[Wikipedia ページ画像]")
        result = search_wikipedia_person(en_name)
        if result:
            print(f"  → {result['url']}")
            print(f"  サイズ: {result.get('width')}x{result.get('height')}")

        print("\n[Wikimedia Commons 検索]")
        results = search_wikimedia_commons(f"{en_name} portrait", limit=3)
        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r['title']}")
            print(f"      {r['url'][:100]}")
            print(f"      {r.get('width')}x{r.get('height')} ({r.get('mime')})")

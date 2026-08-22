"""FLUX img2img 実テスト: 記事 060 / 018 を再生成（LLM prompt 再生成なし）"""
import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(
    sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
)

from generate_images import ImageGenerator

issue_date = "2026-08-01"
issue_dir = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist") / issue_date
log_path = issue_dir / "img2img_test.log"

g = ImageGenerator(issue_date)
g._ensure_comfyui_api_ready()

with open(issue_dir / "analysis.json", encoding="utf-8") as f:
    analysis = json.load(f)
by_id = {a["id"]: a for a in analysis}

cover = g._find_cover_image()
images_dir = issue_dir / "articles" / "images"
images_dir.mkdir(parents=True, exist_ok=True)

results = {}
for aid in (60, 18):
    article = by_id.get(aid)
    if not article:
        print(f"[{aid:03d}] analysis.json に未登録", flush=True)
        results[aid] = False
        continue
    base = f"{aid:03d}"
    print(f"\n========== Article {base} img2img ==========", flush=True)
    ok = g._generate_or_copy_article_image(article, images_dir, cover, base)
    results[aid] = ok
    out = images_dir / f"{base}.png"
    if ok and out.exists():
        print(f"  → {out.name}: {out.stat().st_size:,} bytes", flush=True)
    else:
        print("  → FAILED", flush=True)

print("\n========== Summary ==========", flush=True)
for aid, ok in results.items():
    print(f"  [{aid:03d}] {'OK' if ok else 'FAILED'}", flush=True)

log_path.write_text(
    "\n".join(f"[{aid:03d}] {'OK' if ok else 'FAILED'}" for aid, ok in results.items()) + "\n",
    encoding="utf-8",
)
sys.exit(0 if all(results.values()) else 1)

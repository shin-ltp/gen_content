"""テスト用: analysis.json から指定キーワードの記事を検索（cp932 安全）"""
import json
import sys
import io
from pathlib import Path

# stdout を UTF-8 に強制（cp932 エラー回避）
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

issue_date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"
keywords = sys.argv[2:] if len(sys.argv) > 2 else [
    "Sanae", "Takaichi", "Japan", "Musk", "Elon", "Xi", "Trump",
    "Prime Minister", "CEO", "founder", "billionaire"
]

base = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist")
analysis_path = base / issue_date / "analysis.json"

if not analysis_path.exists():
    print(f"[ERROR] {analysis_path} not found")
    sys.exit(1)

with open(analysis_path, "r", encoding="utf-8") as f:
    articles = json.load(f)

print(f"=== Issue {issue_date}: {len(articles)} articles ===")

# summary も含めて本文全文で検索
hits = []
for a in articles:
    text = " ".join([
        a.get("original_title", ""),
        a.get("japanese_title", ""),
        a.get("summary_ja", ""),
        a.get("one_line_intro", ""),
        " ".join(a.get("keywords_ja", [])),
        a.get("section", ""),
    ])
    text_lower = text.lower()
    matched = [kw for kw in keywords if kw.lower() in text_lower]
    if matched:
        hits.append((a, matched, text))

print(f"\n=== Keyword hits: {len(hits)} ===\n")
for a, matched, text in hits:
    aid = a.get("id", "?")
    score = a.get("relevance_score", "?")
    section = a.get("section", "?")
    title_en = a.get("original_title", "")
    title_ja = a.get("japanese_title", "")
    status = a.get("status", "?")
    print(f"[{aid:03d}] {status} score={score} | {section} | matched={matched}")
    print(f"  EN: {title_en}")
    print(f"  JA: {title_ja}")
    print(f"  summary: {a.get('summary_ja', '')[:200]}")
    print()

# image_reference フィールドの有無
has_ref = [a for a in articles if "image_reference" in a]
print(f"\n=== image_reference field present: {len(has_ref)} articles ===")

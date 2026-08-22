"""テスト用: analysis.json の指定記事に image_reference を手動で付与する

バックアップを作成してから、指定 ID に image_reference フィールドを追加する。
テスト終了後にバックアップから復元可能。
"""
import io
import json
import shutil
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

issue_date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-01"
base = Path(r"c:\my_project\crypto-research-jp\contents\audiobook\output\TheEconomist")
analysis_path = base / issue_date / "analysis.json"
backup_path = base / issue_date / "analysis.json.bak_test"

if not analysis_path.exists():
    print(f"[エラー] {analysis_path} が見つかりません")
    sys.exit(1)

# バックアップ作成（未存在時のみ）
if not backup_path.exists():
    shutil.copy2(analysis_path, backup_path)
    print(f"[情報] バックアップ作成: {backup_path}")
else:
    print(f"[情報] バックアップ既存: {backup_path}")

with open(analysis_path, "r", encoding="utf-8") as f:
    articles = json.load(f)

# テスト対象: 高市早苗(060) + 習近平(018)
test_targets = {
    60: {
        "needs_reference": True,
        "subject_type": "head_of_state",
        "subject_name": "Sanae Takaichi",
        "search_query": "Sanae Takaichi official portrait",
        "instruction": (
            "Transform into a cinematic editorial portrait with dramatic lighting, "
            "premium magazine style, neutral dark background, professional stateswoman appearance. "
            "Keep the facial features recognizable."
        ),
    },
    18: {
        "needs_reference": True,
        "subject_type": "head_of_state",
        "subject_name": "Xi Jinping",
        "search_query": "Xi Jinping official portrait",
        "instruction": (
            "Transform into a cinematic editorial portrait with dramatic lighting, "
            "premium magazine style, neutral dark background. "
            "Keep the facial features recognizable."
        ),
    },
}

updated = 0
for article in articles:
    aid = article.get("id")
    if aid in test_targets:
        article["image_reference"] = test_targets[aid]
        updated += 1
        print(f"  [{aid:03d}] image_reference 追加: {test_targets[aid]['subject_name']}")

with open(analysis_path, "w", encoding="utf-8") as f:
    json.dump(articles, f, indent=2, ensure_ascii=False)

print(f"\n[完了] {updated} 篇に image_reference を追加しました")
print(f"  保存先: {analysis_path}")
print(f"  復元時: copy {backup_path} {analysis_path}")

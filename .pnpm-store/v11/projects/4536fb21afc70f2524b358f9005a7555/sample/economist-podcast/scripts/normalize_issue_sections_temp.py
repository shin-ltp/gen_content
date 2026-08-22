"""
一時スクリプト: 既存号の analysis.json と articles/*.md の section から
「大分類 | 副題」形式の副題部分を除去する。

用法:
  python normalize_issue_sections_temp.py YYYY-MM-DD [--report]

--report: 処理後に analyze_content.py --report-only で analysis_summary.txt を再生成

完了後このファイルは削除してよい。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from config import get_issue_dir, normalize_economist_section


def _normalize_sections_list(lst: list[Any]) -> tuple[list[str], bool]:
    """各要素を正規化し、重複を除去（順序維持）。"""
    out: list[str] = []
    seen: set[str] = set()
    changed = False
    str_items = [s for s in lst if isinstance(s, str)]
    if len(str_items) != len(lst):
        changed = True
    for s in str_items:
        n = normalize_economist_section(s)
        if n != s:
            changed = True
        if n in seen:
            changed = True
            continue
        seen.add(n)
        out.append(n)
    return out, changed


def _patch_sections_in_json_obj(obj: Any) -> int:
    """ネストした dict / list 内の section / sections を正規化。変更したキー数（概算）を返す。"""
    updates = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "section" and isinstance(v, str):
                new = normalize_economist_section(v)
                if new != v:
                    obj[k] = new
                    updates += 1
            elif k == "sections" and isinstance(v, list):
                new_list, ch = _normalize_sections_list(v)
                if ch:
                    obj[k] = new_list
                    updates += 1
            else:
                updates += _patch_sections_in_json_obj(v)
    elif isinstance(obj, list):
        for item in obj:
            updates += _patch_sections_in_json_obj(item)
    return updates


def _patch_json_file(path: Path) -> int:
    if not path.is_file():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    n = _patch_sections_in_json_obj(data)
    if n:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
    return n


def _patch_article_md(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^(---\r?\n)([\s\S]*?)(\r?\n---\r?\n)([\s\S]*)$", text)
    if not m:
        return False
    header = m.group(2)
    changed = False
    new_lines: list[str] = []
    for line in header.splitlines():
        if line.startswith("section:"):
            raw = line[len("section:") :].strip()
            if len(raw) >= 2 and raw[0] == raw[-1] == '"':
                val = raw[1:-1].replace('\\"', '"')
            else:
                val = raw
            new_val = normalize_economist_section(val)
            if new_val != val:
                changed = True
                escaped = json.dumps(new_val, ensure_ascii=False)
                line = f"section: {escaped}"
        new_lines.append(line)
    if not changed:
        return False
    new_text = m.group(1) + "\n".join(new_lines) + m.group(3) + m.group(4)
    path.write_text(new_text, encoding="utf-8")
    return True


def main() -> int:
    argv = [a for a in sys.argv[1:] if a != "--report"]
    run_report = "--report" in sys.argv
    if len(argv) < 1:
        print("使用方法: python normalize_issue_sections_temp.py YYYY-MM-DD [--report]")
        return 1
    issue_date = argv[0]
    issue_dir = get_issue_dir(issue_date)

    analysis_path : Path = issue_dir / "analysis.json"
    if not analysis_path.is_file():
        print(f"[エラー] {analysis_path} が見つかりません")
        return 1

    with open(analysis_path, "r", encoding="utf-8") as f:
        rows = json.load(f)

    a_changed = 0
    for row in rows:
        if "section" not in row or not isinstance(row["section"], str):
            continue
        old = row["section"]
        new = normalize_economist_section(old)
        if new != old:
            row["section"] = new
            a_changed += 1

    with open(analysis_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
        f.write("\n")

    articles_dir = issue_dir / "articles"
    md_changed = 0
    if articles_dir.is_dir():
        for md in sorted(articles_dir.glob("*.md")):
            if _patch_article_md(md):
                md_changed += 1

    json_extra = 0
    plan_path = issue_dir / "episodes_plan.json"
    json_extra += _patch_json_file(plan_path)
    episodes_root = issue_dir / "episodes"
    if episodes_root.is_dir():
        for meta_path in sorted(episodes_root.glob("*/metadata.json")):
            json_extra += _patch_json_file(meta_path)

    print(
        f"[完了] {issue_date}: analysis.json 更新 {a_changed} 件, "
        f"articles/*.md 更新 {md_changed} 件, "
        f"その他 JSON（plan/metadata）の section フィールド更新 {json_extra} 件"
    )

    if run_report:
        analyze_py = Path(__file__).resolve().parent / "analyze_content.py"
        subprocess.run(
            [sys.executable, str(analyze_py), issue_date, "--report-only"],
            check=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

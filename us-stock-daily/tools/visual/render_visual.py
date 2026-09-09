"""Render daily-output/<date>/visual.html from visual-data.json.

Design rule: bespoke slides live verbatim in the skeleton
(us-stock-daily/templates/visual-skeleton.html, baseline = 2026-09-09,
the latest Playwright-verified build). Every <div class="swrap"> in the
skeleton carries a {{SLICE:<id>}} marker where its inner HTML goes.
visual-data.json maps slide ids to inner HTML; the renderer splices them
in, asserts the structural invariants (47 ordered slides, balanced divs,
no residual markers), and writes production/visual.html + issue-root copy.

The per-day model workflow is: copy yesterday's visual-data.json, update
the data-bearing slides (S2/S3/C/D + changed B content), run this script,
then run the DOM/screenshot checks. visual.html is never hand-edited.

Usage (repo root):
    python -X utf8 us-stock-daily/tools/visual/render_visual.py --date YYYY-MM-DD
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[3]
SKELETON = REPO / "us-stock-daily" / "templates" / "visual-skeleton.html"
MARKER = re.compile(r"\{\{SLICE:(s\d+)\}\}")


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Render visual.html from visual-data.json")
    ap.add_argument("--date", required=True, help="episode date YYYY-MM-DD")
    ap.add_argument("--data", default=None, help="path to visual-data.json (default: production/visual-data.json)")
    ap.add_argument("--out", default=None, help="write to this path instead of the issue dirs")
    return ap


def render(data: dict, skeleton_path: Path = SKELETON) -> str:
    html = skeleton_path.read_text(encoding="utf-8-sig")
    slices: dict[str, str] = data.get("slices", {})

    unknown = set(slices) - set(MARKER.findall(html))
    if unknown:
        raise SystemExit(f"visual-data has slices with no skeleton marker: {sorted(unknown)}")
    for slide_id, inner in slices.items():
        html = html.replace("{{SLICE:" + slide_id + "}}", inner)

    residual = MARKER.findall(html)
    if residual:
        raise SystemExit(f"unfilled slice markers (missing from visual-data): {residual}")

    ids = re.findall(r'<div class="swrap" id="(s\d+)"', html)
    want = [f"s{i}" for i in range(47)]
    if ids != want:
        raise SystemExit(f"slide ids wrong: got {len(ids)} slides, order head={ids[:6]}")
    opens = len(re.findall(r"<div\b", html))
    closes = html.count("</div>")
    if opens != closes:
        raise SystemExit(f"unbalanced divs: {opens} <div> vs {closes} </div>")
    for bad in ("{{DATE}}", "{{SLICE:"):
        if bad in html:
            raise SystemExit(f"unreplaced placeholder remains: {bad}")
    return html


def main() -> int:
    args = build_arg_parser().parse_args()
    issue = REPO / "us-stock-daily" / "daily-output" / args.date
    data_path = Path(args.data) if args.data else issue / "production" / "visual-data.json"
    if not data_path.is_file():
        raise SystemExit(f"visual-data.json not found: {data_path}")
    data = json.loads(data_path.read_text(encoding="utf-8-sig"))
    html = render(data)
    if args.out:
        Path(args.out).write_text(html, encoding="utf-8-sig", newline="")
        print(f"rendered -> {args.out} ({len(html)} bytes)")
        return 0
    out_prod = issue / "production" / "visual.html"
    out_root = issue / "visual.html"
    for p in (out_prod, out_root):
        p.write_text(html, encoding="utf-8-sig", newline="")
    print(f"rendered {out_prod} + {out_root.name} copy ({len(html)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

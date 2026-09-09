"""One-off: extract the visual skeleton + per-day data from a baseline issue.

Splits production/visual.html at swrap boundaries (div-depth balanced),
writes:
  - us-stock-daily/templates/visual-skeleton.html
      (same file with every slide's inner HTML replaced by {{SLICE:id}})
  - <issue>/production/visual-data.json
      ({"date": ..., "slices": {id: inner_html}})

Round-trip guarantee: render_visual.py on the extracted data reproduces the
baseline byte-for-byte. Re-run this only when adopting a new baseline
design day; per-day changes go through visual-data.json, never the skeleton.
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
SKELETON_PATH = REPO / "us-stock-daily" / "templates" / "visual-skeleton.html"


def find_balanced_close(html: str, open_start: int) -> tuple[int, int]:
    """Return (start, end) of the </div> that closes the <div> at open_start."""
    depth = 0
    for m in re.finditer(r"<div\b|</div>", html[open_start:]):
        if m.group(0).startswith("<div"):
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                s = open_start + m.start()
                return s, s + len("</div>")
    raise ValueError(f"no balanced close for div at offset {open_start}")


def extract(html: str) -> tuple[str, dict[str, str]]:
    pat = re.compile(r'<div class="swrap" id="(s\d+)"[^>]*>')
    matches = list(pat.finditer(html))
    ids = [m.group(1) for m in matches]
    want = [f"s{i}" for i in range(47)]
    if ids != want:
        raise SystemExit(f"expected 47 ordered slides s0..s46, got {len(ids)}: {ids[:8]}...")

    parts: list[str] = []
    slices: dict[str, str] = {}
    pos = 0
    for i, m in enumerate(matches):
        close_start, close_end = find_balanced_close(html, m.start())
        inner = html[m.end(): close_start]
        ws_end = matches[i + 1].start() if i + 1 < len(matches) else len(html)
        between = html[close_end:ws_end]
        parts.append(html[pos:m.start()])
        parts.append(m.group(0) + "{{SLICE:" + m.group(1) + "}}" + html[close_start:close_end] + between)
        slices[m.group(1)] = inner
        pos = ws_end
    parts.append(html[pos:])
    return "".join(parts), slices


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract visual skeleton + data from a baseline issue")
    ap.add_argument("--date", default="2026-09-09")
    args = ap.parse_args()

    src = REPO / "us-stock-daily" / "daily-output" / args.date / "production" / "visual.html"
    if not src.is_file():
        raise SystemExit(f"baseline not found: {src}")
    html = src.read_text(encoding="utf-8-sig")
    skeleton, slices = extract(html)

    SKELETON_PATH.write_text(skeleton, encoding="utf-8-sig", newline="")
    data_path = src.parent / "visual-data.json"
    data_path.write_text(
        json.dumps({"date": args.date, "slices": slices}, ensure_ascii=False, indent=1),
        encoding="utf-8-sig",
    )
    total = sum(len(v) for v in slices.values())
    print(f"skeleton -> {SKELETON_PATH} ({len(skeleton)} bytes)")
    print(f"data     -> {data_path} ({len(slices)} slices, {total} bytes of inner HTML)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

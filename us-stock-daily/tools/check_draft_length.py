"""Phase 2 draft length checker (read-only).

Checks draft narration length against the Phase 2 spec bands:
- B theme writing target : 9-10 min (3,150-3,500 chars at 350 chars/min)
- B theme pass band      : 7-12 min (2,450-4,200 chars)
- B section final window : 25-40 min (8,750-14,000 chars)

Usage:
  python tools/check_draft_length.py 2026-08-19
  python tools/check_draft_length.py 2026-08-19 --adopted B-1,B-2,B-3,B-4
  python tools/check_draft_length.py 2026-08-19 --cpm 340
"""
from __future__ import annotations

import argparse
import io
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

TOOLS_DIR = Path(__file__).resolve().parent
US_STOCK_DAILY = TOOLS_DIR.parent

DEFAULT_CPM = 350.0
BAND_MIN_MIN, BAND_MAX_MIN = 7.0, 12.0
TARGET_MIN_MIN, TARGET_MAX_MIN = 9.0, 10.0
WINDOW_MIN_MIN, WINDOW_MAX_MIN = 25.0, 40.0

_EXCLUDED_SECTION_RE = re.compile(r"シーン表|採用素材|差戻し")
_B_THEME_RE = re.compile(r"^(B-\d+)")


def issue_dir(issue_date: str) -> Path:
    d = US_STOCK_DAILY / "daily-output" / issue_date
    if not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


def parse_sections(path: Path) -> list[tuple[str, str]]:
    """Return [(section_title, narrative_lines_joined)] for a draft markdown."""
    sections: list[tuple[str, str]] = []
    title: str | None = None
    excluded = False
    buf: list[str] = []

    def flush() -> None:
        if title is not None:
            sections.append((title, "".join(buf)))

    for line in path.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^##\s+(.*)", line)
        if m:
            flush()
            title = m.group(1).strip()
            excluded = bool(_EXCLUDED_SECTION_RE.search(title))
            buf = []
            continue
        if title is None or excluded:
            continue
        s = line.strip()
        if not s or s.startswith(("#", "|", ">", "---")):
            continue
        buf.append(s)
    flush()
    return sections


def narr_chars(text: str) -> int:
    text = re.sub(r"【(?:出所|当番組の見解)[^】]*】", "", text)
    text = text.replace("**", "").replace("`", "")
    return len(re.sub(r"\s+", "", text))


def theme_status(chars: int, cpm: float) -> tuple[str, float]:
    minutes = chars / cpm
    if chars < BAND_MIN_MIN * cpm:
        return "SHORT", minutes
    if chars > BAND_MAX_MIN * cpm:
        return "LONG", minutes
    if TARGET_MIN_MIN * cpm <= chars <= TARGET_MAX_MIN * cpm:
        return "TARGET", minutes
    return "PASS", minutes


def main() -> int:
    parser = argparse.ArgumentParser(description="Check draft-B length against Phase 2 bands")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--cpm", type=float, default=DEFAULT_CPM, help="chars per minute (default 350)")
    parser.add_argument(
        "--adopted",
        default="",
        help="comma-separated adopted theme ids (e.g. B-1,B-2,B-3) to check the final window",
    )
    args = parser.parse_args()

    draft_b = issue_dir(args.issue_date) / "production" / "draft-B.md"
    if not draft_b.is_file():
        print(f"[error] draft not found: {draft_b}")
        return 1

    sections = parse_sections(draft_b)
    themes: list[tuple[str, int]] = []
    for title, text in sections:
        m = _B_THEME_RE.match(title)
        if m:
            themes.append((m.group(1), narr_chars(text)))

    if not themes:
        print("[error] no '## B-n' sections found in draft-B.md")
        return 1

    band = f"{int(BAND_MIN_MIN * args.cpm):,}-{int(BAND_MAX_MIN * args.cpm):,}"
    target = f"{int(TARGET_MIN_MIN * args.cpm):,}-{int(TARGET_MAX_MIN * args.cpm):,}"
    window = f"{int(WINDOW_MIN_MIN * args.cpm):,}-{int(WINDOW_MAX_MIN * args.cpm):,}"

    print(f"[check] {args.issue_date} draft-B ({len(themes)} themes, {args.cpm:.0f} chars/min)")
    failed = False
    for theme, chars in themes:
        st, minutes = theme_status(chars, args.cpm)
        mark = {"TARGET": "◎", "PASS": "○", "SHORT": "▼", "LONG": "▲"}[st]
        print(
            f"  {mark} {theme:<6} {chars:>6,}字  {minutes:5.1f}分  {st:<6}"
            f"(通過帯 {band}字 / 目標 {target}字)"
        )
        if st in ("SHORT", "LONG"):
            failed = True

    total_chars = sum(c for _, c in themes)
    total_min = total_chars / args.cpm
    print(
        f"  合計(全テーマ) {total_chars:>6,}字  {total_min:5.1f}分"
        f"  (B窓 25-40分 = {window}字)"
    )

    if args.adopted:
        wanted = {w.strip() for w in args.adopted.split(",") if w.strip()}
        known = {t for t, _ in themes}
        unknown = wanted - known
        if unknown:
            print(f"[error] unknown theme ids: {', '.join(sorted(unknown))}")
            return 1
        sub_chars = sum(c for t, c in themes if t in wanted)
        sub_min = sub_chars / args.cpm
        ok = WINDOW_MIN_MIN * args.cpm <= sub_chars <= WINDOW_MAX_MIN * args.cpm
        print(
            f"  終選(採用 {len(wanted)}テーマ) {sub_chars:>6,}字  {sub_min:5.1f}分  "
            f"{'OK' if ok else 'NG'}"
        )
        if not ok:
            failed = True

    # Informational: A/C/D narration totals (no bands defined for them).
    refs = []
    for corner in ("A", "C", "D"):
        p = issue_dir(args.issue_date) / "production" / f"draft-{corner}.md"
        if not p.is_file():
            continue
        chars = sum(narr_chars(text) for title, text in parse_sections(p) if not _B_THEME_RE.match(title))
        refs.append(f"{corner} {chars:,}字 {chars / args.cpm:.1f}分")
    if refs:
        print(f"[ref] {' / '.join(refs)} (参考値・帯なし)")

    print("[result]", "FAIL" if failed else "PASS")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

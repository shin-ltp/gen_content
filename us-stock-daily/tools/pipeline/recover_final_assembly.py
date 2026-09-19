"""Recover final write_blocks assembly from saved partial segment maps."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import write_blocks as wb


def texts_from_partial_map(path: Path, prefix: str) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    items = []
    for seg in payload.get("segments", []):
        seg_id = str(seg.get("id", ""))
        if not seg_id.startswith(prefix):
            continue
        suffix = seg_id[len(prefix):]
        if not suffix.isdigit():
            continue
        items.append((int(suffix), seg.get("text", "")))
    return [text.strip() for _, text in sorted(items)]


def b_texts_from_partial_map(path: Path, theme_count: int) -> dict[int, str]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    paragraphs: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for seg in payload.get("segments", []):
        seg_id = str(seg.get("id", ""))
        if not seg_id.startswith("B"):
            continue
        tail = seg_id[1:]
        theme_part, part_part = tail.split("-p", 1)
        if not (theme_part.isdigit() and part_part.isdigit()):
            continue
        theme = int(theme_part)
        if 1 <= theme <= theme_count:
            paragraphs[theme].append((int(part_part), seg.get("text", "")))
    return {
        theme: "\n\n".join(text.strip() for _, text in sorted(parts))
        for theme, parts in paragraphs.items()
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("issue_date")
    parser.add_argument(
        "--no-validate", action="store_true",
        help="write artifacts but skip build_pipeline.py validate")
    args = parser.parse_args()

    outline = json.loads(
        (wb.issue_dir(args.issue_date) / wb.OUTLINE_PATH)
        .read_text(encoding="utf-8-sig"))
    adopted = wb.adopted_candidates(outline)
    n = len(adopted)
    if n == 0:
        print("[recover] no adopted B candidates")
        return 1

    tts_dir = wb.issue_dir(args.issue_date) / "production" / "tts"
    opening_texts = texts_from_partial_map(tts_dir / "segment-map.A.json", "A-p")
    news_texts = texts_from_partial_map(tts_dir / "segment-map.C.json", "C-p")
    event_texts = texts_from_partial_map(tts_dir / "segment-map.D.json", "D-p")
    b_texts = b_texts_from_partial_map(tts_dir / "segment-map.B.json", n)

    if len(opening_texts) < n + 1:
        print(f"[recover] opening count={len(opening_texts)} (expected >= {n + 1})")
        return 1
    opening = {
        "previews": wb.previews_from_narration_texts(opening_texts[:n]),
        "market": opening_texts[n],
    }
    if len(news_texts) != 8:
        print(f"[recover] news count={len(news_texts)} (expected 8)")
        return 1
    missing_b = [i for i in range(1, n + 1) if not b_texts.get(i)]
    if missing_b:
        print("[recover] missing B theme texts: "
              + ", ".join(f"B-{i}" for i in missing_b))
        return 1
    if not event_texts:
        event_texts = ["イベント予告はありません。"]

    config, script, segment_map = wb.build_config_and_script(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)

    issue = wb.issue_dir(args.issue_date)
    config_path = issue / wb.CONFIG_PATH
    script_path = issue / wb.SCRIPT_PATH
    map_path = issue / "production" / "segment-map.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    map_path.write_text(
        json.dumps(segment_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    wb.write_draft_markdown(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)
    brief_path = wb.generate_visual_brief(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)
    visual_path = wb.generate_visual_data(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)

    print(f"[recover] script blocks={len(script['blocks'])}")
    print(f"[recover] segment-map segments={len(segment_map['segments'])}")
    print(f"[recover] config -> {config_path}")
    print(f"[recover] script -> {script_path}")
    print(f"[recover] segment-map -> {map_path}")
    print(f"[recover] visual-brief -> {brief_path}")
    print(f"[recover] visual-data -> {visual_path}")

    if args.no_validate:
        return 0
    ok, output = wb.validate_with_build_pipeline(args.issue_date)
    if not ok:
        print(f"[recover] validate FAILED:\n{output[-2000:]}")
        return 2
    print("[recover] validate PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

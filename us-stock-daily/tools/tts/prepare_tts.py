"""Convert content drafts + visual slide map into per-slide TTS text files.

Input:  daily-output/<date>/production/segment-map.json
        (hand-authored mapping: slide id -> narration text, voice, cue)
Output: daily-output/<date>/production/tts/
          NNN_<content-id>.txt   (UTF-8 BOM, Fish-safe Japanese)
          manifest.json          (machine readable, for generate_audio / Remotion)
          segments.md            (human review table)

The segment map is the single source of truth for audio/visual sync:
one TTS file per page transition or intra-page content switch.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts_config import (  # noqa: E402
    CHARS_PER_SEC_JA,
    DEFAULT_VOICES,
    SILENCE_PAUSE_LONG_SEC,
    SILENCE_PAUSE_SHORT_SEC,
    get_issue_dir,
    voice_ref_paths,
)
from ja_tts_normalize import normalize_for_tts  # noqa: E402


def _pause_seconds(text: str) -> float:
    return (
        text.count("[pause long]") * SILENCE_PAUSE_LONG_SEC
        + text.count("[pause short]") * SILENCE_PAUSE_SHORT_SEC
    )


def _estimate_sec(text: str) -> float:
    spoken = re.sub(r"\[pause (?:long|short)\]", "", text)
    return len(spoken) / CHARS_PER_SEC_JA + _pause_seconds(text)


def _slide_ids(visual_html: Path) -> list[str]:
    html = visual_html.read_text(encoding="utf-8-sig")
    return re.findall(r'<div class="swrap" id="(s\d+)"', html)


def _write_bom(path: Path, text: str) -> None:
    """Project rule: all text files are UTF-8 with BOM."""
    path.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))


def prepare(issue_date: str, visual: str | None = None) -> int:
    issue_dir = get_issue_dir(issue_date)
    seg_map_path = issue_dir / "production" / "segment-map.json"
    if not seg_map_path.is_file():
        print(f"[error] segment map not found: {seg_map_path}")
        return 1

    seg_map = json.loads(seg_map_path.read_text(encoding="utf-8-sig"))
    visual_name = visual or seg_map.get("visual", "visual-v2.html")
    visual_html = issue_dir / visual_name
    if not visual_html.is_file():
        print(f"[error] visual html not found: {visual_html}")
        return 1

    slides = _slide_ids(visual_html)
    slide_set = set(slides)

    segments = seg_map.get("segments", [])
    seen_orders: set[int] = set()
    seen_ids: set[str] = set()
    covered_slides: set[str] = set()
    errors: list[str] = []
    default_voice = seg_map.get("voices", {}).get("default", "xiaomei")

    for seg in segments:
        order = seg.get("order")
        seg_id = seg.get("id", "")
        slide = seg.get("slide", "")
        if not isinstance(order, int):
            errors.append(f"segment {seg_id!r}: missing integer 'order'")
            continue
        if order in seen_orders:
            errors.append(f"duplicate order {order:03d} ({seg_id})")
        if seg_id in seen_ids:
            errors.append(f"duplicate id {seg_id!r}")
        seen_orders.add(order)
        seen_ids.add(seg_id)

        if slide and slide not in slide_set:
            errors.append(f"{seg_id}: slide {slide!r} not found in {visual_name}")
        if slide:
            covered_slides.add(slide)

        seg_type = seg.get("type", "tts")
        if seg_type == "tts":
            voice = seg.get("voice", default_voice)
            if voice not in DEFAULT_VOICES:
                errors.append(f"{seg_id}: unknown voice {voice!r}")
            else:
                voice_ref_paths(voice)  # raises if reference assets missing
            if not (seg.get("text") or "").strip():
                errors.append(f"{seg_id}: empty narration text")

    uncovered = [s for s in slides if s not in covered_slides]

    if errors:
        print("[error] segment map validation failed:")
        for e in errors:
            print(f"  - {e}")
        return 1

    tts_dir = issue_dir / "production" / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    for old in tts_dir.glob("*.txt"):
        old.unlink()

    files_meta: list[dict] = []
    total_chars = 0
    total_est = 0.0

    for seg in sorted(segments, key=lambda s: s["order"]):
        order = seg["order"]
        seg_id = seg["id"]
        seg_type = seg.get("type", "tts")
        fname = f"{order:03d}_{seg_id}.txt"
        entry = {
            "order": order,
            "id": seg_id,
            "slide": seg.get("slide", ""),
            "type": seg_type,
            "voice": seg.get("voice", default_voice),
            "file": f"tts/{fname}",
            "title": seg.get("title", ""),
            "cue": seg.get("cue", ""),
            "source": seg.get("source", ""),
        }

        if seg_type == "external":
            entry["asset_hint"] = seg.get("asset_hint", "")
            _write_bom(tts_dir / fname, "")
            files_meta.append(entry)
            continue

        text = normalize_for_tts(seg.get("text", ""))
        _write_bom(tts_dir / fname, text)
        est = _estimate_sec(text)
        entry["chars"] = len(re.sub(r"\[pause (?:long|short)\]", "", text))
        entry["est_sec"] = round(est, 1)
        files_meta.append(entry)
        total_chars += entry["chars"]
        total_est += est

    manifest = {
        "episode": issue_date,
        "visual": visual_name,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "voices": seg_map.get("voices", {"default": "xiaomei"}),
        "total_chars": total_chars,
        "estimated_total_sec": round(total_est, 1),
        "segments": files_meta,
    }
    (tts_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Human review table.
    lines = [
        f"# TTS segments — {issue_date} ({visual_name})",
        "",
        f"- TTS segments: {sum(1 for f in files_meta if f['type'] == 'tts')}",
        f"- External slots (BGM / channel intro): "
        f"{sum(1 for f in files_meta if f['type'] == 'external')}",
        f"- Narration chars: {total_chars:,} / est. {total_est / 60:.1f} min",
        "",
        "| # | file | slide | voice | chars | est sec | title |",
        "|---|------|-------|-------|-------|---------|-------|",
    ]
    for f in files_meta:
        if f["type"] == "external":
            chars = est = "-"
        else:
            chars = f"{f['chars']:,}"
            est = f"{f['est_sec']}"
        lines.append(
            f"| {f['order']:03d} | {f['file']} | {f['slide'] or '-'} "
            f"| {f['voice']} | {chars} | {est} | {f['title']} |"
        )
    _write_bom(tts_dir / "segments.md", "\n".join(lines) + "\n")

    print(f"[ok] wrote {len(files_meta)} segment files -> {tts_dir}")
    print(f"[ok] narration: {total_chars:,} chars, est. {total_est / 60:.1f} min")
    if uncovered:
        print(f"[warn] uncovered slides (silent): {', '.join(uncovered)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prepare TTS texts from segment map")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--visual", default=None, help="override visual html filename")
    args = parser.parse_args()
    sys.exit(prepare(args.issue_date, args.visual))

#!/usr/bin/env python3
"""Rebuild durations.json from existing merged segment WAVs.

A partial generate_audio run can overwrite durations.json with only the
segments it re-rendered.  The segment WAVs and their per-sentence work files
remain valid, so this tool restores the full measured map without re-running
TTS.  It is intentionally read-only outside production/audio/durations.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


DAILY = Path(__file__).resolve().parents[2]
FFPROBE = (
    DAILY / "remotion" / "node_modules"
    / "@remotion" / "compositor-win32-x64-msvc" / "ffprobe.exe"
)


def issue_dir(date: str) -> Path:
    return DAILY / "daily-output" / date


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json_bom(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(b"\xef\xbb\xbf" + data.encode("utf-8"))


def wav_duration(path: Path) -> float:
    exe = str(FFPROBE) if FFPROBE.is_file() else "ffprobe"
    result = subprocess.run(
        [exe, "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", str(path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    return round(float(result.stdout.strip()), 3)


def timeline_from_work(date: str, work_dir: Path) -> list[dict]:
    segments_path = work_dir / "segments.json"
    if not segments_path.is_file():
        return []
    metadata = read_json(segments_path)
    cursor = 0.0
    timeline: list[dict] = []
    for index, piece in enumerate(metadata.get("pieces", [])):
        wav = work_dir / piece["wav"]
        duration = wav_duration(wav)
        after = piece.get("after")
        timeline.append({
            "index": index,
            "text": piece.get("text", ""),
            "wav": wav.relative_to(issue_dir(date)).as_posix(),
            "duration": duration,
            "start": round(cursor, 3),
            "end": round(cursor + duration, 3),
            "pause_after": after,
        })
        cursor += duration
        if after == "pause_long":
            cursor += 1.0
        elif after == "pause_short":
            cursor += 0.45
        elif after == "period":
            cursor += 0.35
    return timeline


def reconstruct(date: str) -> Path:
    root = issue_dir(date)
    map_path = root / "production" / "segment-map.json"
    audio_dir = root / "production" / "audio"
    work_root = root / "production" / "audio_work"
    output = audio_dir / "durations.json"

    segment_map = read_json(map_path)
    tts_segments = [s for s in segment_map.get("segments", []) if s.get("type") == "tts"]
    known_ids = {s["id"] for s in tts_segments}
    existing: dict[str, dict] = {}
    if output.is_file():
        existing = {
            item["id"]: item
            for item in read_json(output).get("segments", [])
            if item.get("id") in known_ids
        }

    restored: list[dict] = []
    missing: list[str] = []
    for meta in tts_segments:
        segment_id = meta["id"]
        old = existing.get(segment_id)
        wav = None
        if old is not None:
            candidate = root / old["file"]
            wav = candidate if candidate.is_file() else None
        if wav is None:
            candidates = sorted(audio_dir.glob(f"*_{segment_id}.wav"))
            wav = candidates[-1] if candidates else audio_dir / f"{meta['order']:03d}_{segment_id}.wav"
        if not wav.is_file():
            missing.append(segment_id)
            continue
        duration = wav_duration(wav)
        item = dict(old or {})
        item.update({
            "order": meta["order"],
            "id": segment_id,
            "slide": meta.get("slide", ""),
            "voice": meta.get("voice", ""),
            "file": wav.relative_to(root).as_posix(),
            "duration": duration,
        })
        if not item.get("sentences"):
            work_dir = work_root / wav.name.removesuffix(".wav")
            item["sentences"] = timeline_from_work(date, work_dir)
        restored.append(item)

    if missing:
        raise RuntimeError(
            "missing segment WAVs: " + ", ".join(missing)
            + "; run generate_audio for these segments first"
        )

    restored.sort(key=lambda item: (item["order"], item["id"]))
    payload = {
        "episode": date,
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "reconstructed_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "sample_rate": 24000,
        "segments": restored,
        "total_duration": round(sum(float(item["duration"]) for item in restored), 3),
    }
    write_json_bom(output, payload)
    print(f"[done] restored {len(restored)} segments -> {output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("date", help="episode date (YYYY-MM-DD)")
    args = parser.parse_args()
    try:
        reconstruct(args.date)
    except (OSError, KeyError, RuntimeError, ValueError) as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

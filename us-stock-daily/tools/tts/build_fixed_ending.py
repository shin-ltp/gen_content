"""Rebuild the reusable ending.wav from the fixed greeting and end BGM.

The ending timeline is intentionally independent of daily TTS:
0.0s BGM fade-in -> 1.5s fixed xiaomei greeting -> speech end -> 4.0s linear
BGM fade-out. The disclaimer is visual-only and is never voiced.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(ROOT / "tools" / "pipeline"))

from fish_local_engine import FishLocalEngine  # noqa: E402
from fish_batch import FishJob  # noqa: E402
from generate_audio import (  # noqa: E402
    build_pieces,
    FIXED_AUDIO_DIR,
    silence_sec,
    _build_fixed_ending,
    _decode_mono_pcm,
    _write_concat_wave,
    _wav_duration_wave,
    audio_duration,
)
from tts_config import WAV_MIN_SIZE, get_issue_dir  # noqa: E402
from write_blocks import ENDING_GREETING_TEXT  # noqa: E402


BGM_SOURCE = ROOT / "assets" / "bgm" / "ending" / "end_03_daytime-tv-theme_46sec.mp3"
EXPECTED_LEAD_SEC = 1.5
EXPECTED_TAIL_SEC = 4.0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--text",
        default=ENDING_GREETING_TEXT,
        help="override the fixed ending greeting (advanced use only)",
    )
    args = parser.parse_args()

    if not BGM_SOURCE.is_file():
        raise FileNotFoundError(f"ending BGM not found: {BGM_SOURCE}")
    text = " ".join(args.text.split())
    if not text:
        raise ValueError("ending greeting is empty")
    if "免責" in text or "投資判断" in text:
        raise ValueError("the ending greeting must not contain the visual disclaimer")

    engine = FishLocalEngine("fixed-assets")
    work_dir = get_issue_dir("fixed-assets") / "production" / ".fixed_ending"
    work_dir.mkdir(parents=True, exist_ok=True)

    # Same sentence-level pipeline as the daily narration: slice at 。,
    # synthesize each sentence separately, and insert the standard period
    # silence between sentences (the final sentence gets no trailing gap).
    pieces = build_pieces(text)
    if not pieces:
        raise ValueError("ending greeting produced no sentences")
    sent_dir = work_dir / "greeting_sentences"
    sent_dir.mkdir(parents=True, exist_ok=True)
    jobs: list[FishJob] = []
    for idx, piece in enumerate(pieces):
        wav = sent_dir / f"sent_{idx:02d}.wav"
        if wav.is_file() and wav.stat().st_size >= WAV_MIN_SIZE:
            continue
        jobs.append(
            FishJob(
                voice="xiaomei",
                text=piece["text"],
                rel_wav=wav.relative_to(engine.issue_dir).as_posix(),
                index=idx,
            )
        )
    if jobs:
        engine.synthesize(jobs)
    else:
        print("[fixed] all greeting sentences cached; skipping TTS")

    concat_entries: list[tuple[Path, float]] = []
    for idx, piece in enumerate(pieces):
        wav = sent_dir / f"sent_{idx:02d}.wav"
        concat_entries.append((wav, 0.0))
        gap = silence_sec(piece["after"]) or 0.0
        if gap > 0:
            concat_entries.append((None, gap))
    tts_wav = work_dir / "greeting_tts.wav"
    _write_concat_wave(concat_entries, tts_wav)

    greeting_pcm = work_dir / "greeting_pcm.wav"
    _decode_mono_pcm(tts_wav, greeting_pcm)
    greeting_sec = _wav_duration_wave(greeting_pcm)
    if greeting_sec <= 1:
        raise RuntimeError(f"fixed greeting is too short: {greeting_sec:.3f}s")

    FIXED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    out_wav, total_sec, end_card_at = _build_fixed_ending(
        engine.issue_dir, work_dir, greeting_pcm, BGM_SOURCE
    )
    expected_total = EXPECTED_LEAD_SEC + greeting_sec + EXPECTED_TAIL_SEC
    if abs(total_sec - expected_total) > 0.002:
        raise RuntimeError(
            f"ending duration mismatch: {total_sec:.3f}s != {expected_total:.3f}s"
        )
    if abs(end_card_at - 4.0) > 0.001:
        raise RuntimeError(f"disclaimer hold mismatch: {end_card_at:.3f}s != 4.000s")
    actual_sec = audio_duration(out_wav)
    if actual_sec < 0 or abs(actual_sec - total_sec) > 0.05:
        raise RuntimeError(
            f"ending WAV duration mismatch: {actual_sec:.3f}s != {total_sec:.3f}s"
        )

    meta = {
        "asset": "assets/audio/fixed/ending.wav",
        "voice": "xiaomei",
        "speechStartSec": EXPECTED_LEAD_SEC,
        "speechEndSec": round(EXPECTED_LEAD_SEC + greeting_sec, 3),
        "disclaimerHoldSec": 4.0,
        "endCardAtSec": round(end_card_at, 3),
        "bgmTailSec": EXPECTED_TAIL_SEC,
        "durationSec": round(total_sec, 3),
    }
    meta_path = FIXED_AUDIO_DIR / "ending.json"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[fixed] rebuilt {out_wav} ({total_sec:.3f}s)")
    print(f"[fixed] speech at 1.500s, disclaimer/end card switch at 4.000s")
    print(f"[fixed] sentences={len(pieces)} (silence 0.350s between sentences)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

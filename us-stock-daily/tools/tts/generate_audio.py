"""Generate narration audio from prepared TTS segment files.

Flow per segment file:
1. Slice text into sentences by [pause long] / [pause short] / 。？！
   (pause markers are NEVER sent to Fish Audio — silences are inserted at
   merge time, which is the reliable way to control pacing with Fish).
2. Synthesize missing sentence WAVs remotely (Mac MLX, grouped by voice).
3. Merge sentence WAVs + silence into one WAV per content block.
4. Emit durations.json with per-segment AND per-sentence timing for the
   later Remotion composition (audio/visual frame-accurate sync).

Usage:
  python generate_audio.py 2026-08-19 --dry-run   # plan only, no SSH
  python generate_audio.py 2026-08-19             # synthesize + merge
  python generate_audio.py 2026-08-19 --only S01-haiku S22-C03
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fish_batch import FishDailyEngine, FishJob  # noqa: E402
from tts_config import FISH_REMOTE_HOST  # noqa: E402
from tts_config import (  # noqa: E402
    CHARS_PER_SEC_JA,
    SAMPLE_RATE,
    SILENCE_PAUSE_LONG_SEC,
    SILENCE_PAUSE_SHORT_SEC,
    SILENCE_PERIOD_SEC,
    WAV_MIN_SIZE,
    get_issue_dir,
)

PAUSE_LONG = "[pause long]"
PAUSE_SHORT = "[pause short]"
DURATION_MAX_RATIO = 1.7
DURATION_MIN_RATIO = 0.2


# ------------------------------------------------------------------ slicing
def slice_sentences(text: str) -> list[tuple[str, str | None]]:
    """Slice by pause markers and sentence enders.

    Returns [(sentence, delimiter_after)] where delimiter_after is one of
    "pause_long" | "pause_short" | "period" | None.
    """
    segments: list[tuple[str, str | None]] = []
    i = 0
    while i < len(text):
        positions = {
            "pause_long": text.find(PAUSE_LONG, i),
            "pause_short": text.find(PAUSE_SHORT, i),
            "period": text.find("。", i),
            "question": text.find("？", i),
            "exclaim": text.find("！", i),
        }
        for k in list(positions):
            if positions[k] == -1:
                positions[k] = len(text) + 1

        kind = min(positions, key=positions.get)  # type: ignore[arg-type]
        pos = positions[kind]
        if pos > len(text):
            rest = text[i:].strip()
            if rest:
                segments.append((rest, None))
            break

        if kind in ("pause_long", "pause_short"):
            seg_text = text[i:pos].strip()
            segments.append((seg_text, kind))
            i = pos + len(PAUSE_LONG if kind == "pause_long" else PAUSE_SHORT)
        else:
            seg_text = text[i : pos + 1].strip()
            if seg_text:
                segments.append((seg_text, "period"))
            i = pos + 1
    return segments


def split_long_sentence(sentence: str, max_chars: int = 120) -> list[tuple[str, str | None]]:
    """Split an over-long sentence at the 、 nearest the middle."""
    if len(sentence) <= max_chars:
        return [(sentence, None)]
    mid = len(sentence) // 2
    commas = [m.start() for m in re.finditer("、", sentence)]
    if not commas:
        return [(sentence, None)]
    cut = min(commas, key=lambda p: abs(p - mid)) + 1
    first = sentence[:cut]
    rest = sentence[cut:].lstrip()
    out = [(first, "pause_short")]
    out.extend(split_long_sentence(rest, max_chars))
    return out


def build_pieces(text: str) -> list[dict]:
    pieces: list[dict] = []
    for raw, after in slice_sentences(text):
        if not raw:
            if after:
                if pieces:
                    pieces[-1]["after"] = after
                else:
                    pieces.append({"text": "", "after": after})
            continue
        for part, part_after in split_long_sentence(raw):
            if not part:
                continue
            pieces.append({"text": part, "after": part_after or after})
    # Final piece has no trailing silence (segment boundary handled globally).
    if pieces:
        pieces[-1]["after"] = None
    return [p for p in pieces if p["text"]]


def silence_sec(after: str | None) -> float:
    if after == "pause_long":
        return SILENCE_PAUSE_LONG_SEC
    if after == "pause_short":
        return SILENCE_PAUSE_SHORT_SEC
    if after == "period":
        return SILENCE_PERIOD_SEC
    return 0.0


# ------------------------------------------------------------------- media
def run_ffmpeg(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-nostats"] + args,
        capture_output=True,
        check=check,
    )


def wav_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        try:
            size = path.stat().st_size
            return max(0.0, (size - 44) / (SAMPLE_RATE * 2))
        except Exception:
            return -1.0


def _wav_duration_wave(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / w.getframerate()
    except Exception:
        return -1.0


def audio_duration(path: Path) -> float:
    """Duration via ffprobe when available, else the stdlib wave module."""
    if shutil.which("ffprobe"):
        d = wav_duration(path)
        if d >= 0:
            return d
    return _wav_duration_wave(path)


def validate_wav(path: Path, text: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    if path.stat().st_size < WAV_MIN_SIZE:
        return False, "too small"
    duration = audio_duration(path)
    if duration < 0.1:
        return False, "silent/too short"
    if len(text) > 10:
        expected = len(text) / CHARS_PER_SEC_JA
        if duration > expected * DURATION_MAX_RATIO:
            return False, f"too long ({duration:.1f}s vs expected {expected:.1f}s)"
        if duration < expected * DURATION_MIN_RATIO:
            return False, f"too short ({duration:.1f}s vs expected {expected:.1f}s)"
    return True, "ok"


# ------------------------------------------------------------- preparation
def prepare_work(issue_dir: Path, seg_meta: dict, force: bool = False) -> tuple[Path, list[dict]]:
    stem = Path(seg_meta["file"]).stem  # NNN_id
    work_dir = issue_dir / "production" / "audio_work" / stem
    work_dir.mkdir(parents=True, exist_ok=True)

    text = (issue_dir / "production" / seg_meta["file"]).read_text(encoding="utf-8-sig")
    pieces = build_pieces(text)
    for idx, piece in enumerate(pieces):
        piece["index"] = idx
        piece["wav"] = f"seg_{idx:04d}.wav"

    info = {
        "segment": seg_meta["id"],
        "slide": seg_meta.get("slide", ""),
        "voice": seg_meta["voice"],
        "total_pieces": len(pieces),
        "silence_config": {
            "pause_long": SILENCE_PAUSE_LONG_SEC,
            "pause_short": SILENCE_PAUSE_SHORT_SEC,
            "period": SILENCE_PERIOD_SEC,
        },
        "pieces": pieces,
    }
    (work_dir / "segments.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if force:
        for old in work_dir.glob("seg_*.wav"):
            old.unlink()
    return work_dir, pieces


def pending_jobs(issue_dir: Path, work_dir: Path, seg_meta: dict, pieces: list[dict]) -> list[FishJob]:
    jobs = []
    for piece in pieces:
        wav = work_dir / piece["wav"]
        if wav.is_file() and wav.stat().st_size >= WAV_MIN_SIZE:
            continue
        rel = wav.relative_to(issue_dir).as_posix()
        jobs.append(
            FishJob(voice=seg_meta["voice"], text=piece["text"], rel_wav=rel, index=piece["index"])
        )
    return jobs


# ------------------------------------------------------------------ merging
def ensure_silences(work_dir: Path) -> dict[str, Path]:
    out = {}
    for label, sec in (
        ("pause_long", SILENCE_PAUSE_LONG_SEC),
        ("pause_short", SILENCE_PAUSE_SHORT_SEC),
        ("period", SILENCE_PERIOD_SEC),
    ):
        p = work_dir / f"silence_{label}.wav"
        if not p.exists():
            run_ffmpeg(
                [
                    "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
                    "-t", str(sec), "-acodec", "pcm_s16le", str(p),
                ]
            )
        out[label] = p
    return out


def _write_concat_wave(
    entries: list[tuple[Path | None, float]], out_wav: Path
) -> None:
    """Concat WAVs (and silence gaps) with the stdlib wave module.

    entries: (wav_path or None, silence_sec_when_None). All input WAVs must
    share the same PCM params; the output inherits them.
    """
    params: tuple | None = None
    with wave.open(str(out_wav), "wb") as out:
        for path, gap in entries:
            if path is None:
                if params is None:
                    raise RuntimeError("silence before any audio frame")
                nch, sw, fr, _ = params
                out.writeframes(b"\x00" * int(fr * gap) * nch * sw)
                continue
            with wave.open(str(path), "rb") as w:
                cur = (w.getnchannels(), w.getsampwidth(), w.getframerate())
                if params is None:
                    params = cur + (w.getcomptype(),)
                    out.setnchannels(cur[0])
                    out.setsampwidth(cur[1])
                    out.setframerate(cur[2])
                    out.setcomptype(w.getcomptype(), w.getcompname())
                elif cur != params[:3]:
                    raise RuntimeError(
                        f"pcm params mismatch in {path.name}: {cur} vs {params[:3]}; "
                        "install ffmpeg for automatic conversion"
                    )
                out.writeframes(w.readframes(w.getnframes()))


def merge_segment(
    issue_dir: Path, work_dir: Path, seg_meta: dict, pieces: list[dict]
) -> tuple[Path, float, list[dict]]:
    use_ffmpeg = shutil.which("ffmpeg") is not None
    silences = ensure_silences(work_dir) if use_ffmpeg else {}
    lines = []
    concat_entries: list[tuple[Path | None, float]] = []
    timeline: list[dict] = []
    cursor = 0.0

    for piece in pieces:
        wav = work_dir / piece["wav"]
        dur = audio_duration(wav)
        if dur < 0:
            raise RuntimeError(f"cannot read duration: {wav}")
        if use_ffmpeg:
            lines.append(f"file '{wav.resolve().as_posix()}'")
        else:
            concat_entries.append((wav, 0.0))
        after = piece.get("after")
        gap = silence_sec(after)
        timeline.append(
            {
                "index": piece["index"],
                "text": piece["text"],
                "wav": wav.relative_to(issue_dir).as_posix(),
                "duration": round(dur, 3),
                "start": round(cursor, 3),
                "end": round(cursor + dur, 3),
                "pause_after": after,
            }
        )
        cursor += dur
        if after:
            if use_ffmpeg:
                lines.append(f"file '{silences[after].resolve().as_posix()}'")
            else:
                concat_entries.append((None, gap))
            cursor += gap

    list_path = work_dir / "concat_list.txt"
    list_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    audio_dir = issue_dir / "production" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(seg_meta["file"]).stem
    out_wav = audio_dir / f"{stem}.wav"
    if use_ffmpeg:
        combined = work_dir / "combined.wav"
        run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(combined)]
        )
        run_ffmpeg(
            [
                "-i", str(combined),
                "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
                str(out_wav),
            ]
        )
    else:
        _write_concat_wave(concat_entries, out_wav)
    return out_wav, cursor, timeline


# -------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate narration audio (Fish Audio via Mac)")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="show plan only, no SSH")
    parser.add_argument("--force", action="store_true", help="re-synthesize existing wavs")
    parser.add_argument("--only", nargs="+", default=None, help="segment ids to process")
    args = parser.parse_args()

    issue_dir = get_issue_dir(args.issue_date)
    manifest_path = issue_dir / "production" / "tts" / "manifest.json"
    if not manifest_path.is_file():
        print("[error] manifest not found; run prepare_tts.py first")
        return 1
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    tts_segments = [s for s in manifest["segments"] if s["type"] == "tts"]
    if args.only:
        wanted = set(args.only)
        tts_segments = [s for s in tts_segments if s["id"] in wanted]
        missing = wanted - {s["id"] for s in tts_segments}
        if missing:
            print(f"[error] unknown segment ids: {', '.join(sorted(missing))}")
            return 1

    works: list[tuple[dict, Path, list[dict]]] = []
    all_jobs: list[FishJob] = []
    for seg in tts_segments:
        work_dir, pieces = prepare_work(issue_dir, seg, force=args.force)
        works.append((seg, work_dir, pieces))
        all_jobs.extend(pending_jobs(issue_dir, work_dir, seg, pieces))

    print(
        f"[plan] {len(tts_segments)} tts segments, "
        f"{sum(len(p) for _, _, p in works)} sentences, "
        f"{len(all_jobs)} to synthesize"
    )
    by_voice: dict[str, int] = {}
    for j in all_jobs:
        by_voice[j.voice] = by_voice.get(j.voice, 0) + 1
    for voice in sorted(by_voice):
        print(f"[plan]   {voice}: {by_voice[voice]} sentences")

    if args.dry_run:
        engine = FishDailyEngine(args.issue_date)
        print(f"[plan] remote host : {FISH_REMOTE_HOST}")
        print(f"[plan] remote root : {engine.remote_root}")
        print("[plan] dry-run: no connection made")
        return 0

    if all_jobs:
        engine = FishDailyEngine(args.issue_date)
        engine.synthesize(all_jobs)

    # Validate; retry failed pieces once with force.
    invalid: list[tuple[Path, dict]] = []
    for seg, work_dir, pieces in works:
        for piece in pieces:
            wav = work_dir / piece["wav"]
            ok, reason = validate_wav(wav, piece["text"])
            if not ok:
                invalid.append((wav, piece))
                print(f"[warn] invalid wav {wav.name}: {reason}")
    if invalid:
        print(f"[error] {len(invalid)} invalid wav(s); re-run with --only and --force")
        return 1

    durations = {
        "episode": args.issue_date,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "sample_rate": SAMPLE_RATE,
        "segments": [],
    }
    total = 0.0
    for seg, work_dir, pieces in works:
        out_wav, dur, timeline = merge_segment(issue_dir, work_dir, seg, pieces)
        rel_audio = out_wav.relative_to(issue_dir).as_posix()
        durations["segments"].append(
            {
                "order": seg["order"],
                "id": seg["id"],
                "slide": seg.get("slide", ""),
                "voice": seg["voice"],
                "file": rel_audio,
                "duration": round(dur, 3),
                "sentences": timeline,
            }
        )
        total += dur
        print(f"[ok] {out_wav.name}  {dur:.1f}s")

    durations["total_duration"] = round(total, 3)
    out_path = issue_dir / "production" / "audio" / "durations.json"
    out_path.write_text(
        json.dumps(durations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[done] total {total / 60:.1f} min -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

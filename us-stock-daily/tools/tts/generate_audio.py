"""Generate narration audio from prepared TTS segment files.

Flow per segment file:
1. Slice text into sentences by [pause long] / [pause short] / 。？！
   (pause markers are NEVER sent to Fish Audio — silences are inserted at
   merge time, which is the reliable way to control pacing with Fish).
2. Synthesize missing sentence WAVs (default: local WSL2 server, grouped by
   voice; fallback engine: Mac MLX over SSH — see fish_local_engine.py).
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
import os
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

from fish_batch import FishJob  # noqa: E402
from fish_local_engine import build_engine  # noqa: E402
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

# Corner-change heads get a news sting, then one second of breathing room
# before the narration starts. The sting is baked into the segment WAV so the
# merged duration is already the exact visual duration Remotion needs.
CORNER_HEAD_IDS = {
    "S02-A01-intro",
    "S04-B1-01",
    "S10-B2-01",
    "S20-B3-01",
    "S28-B4-01",
    "S37-C-intro",
    "S38-D-intro",
}
STING_SOURCE = (
    Path(__file__).resolve().parents[2] / "assets" / "bgm" / "transition"
    / "tr_03_news-sting_5sec.mp3"
)
STING_LEAD_SEC = 1.0
# Opening/ending get their BGM baked into the narration WAV. The lead lets the
# music establish before speech; the tail is the audible outro after speech.
OP_ED_BGM = {
    "005_S00-intro": {
        "source": Path(__file__).resolve().parents[2]
        / "assets/bgm/opening/open_01_inspired_30sec.mp3",
        "lead_sec": 1.0,
        "tail_sec": 3.0,
        "volume": 0.32,
    },
    # Legacy id kept so reruns of older episodes retain their ending music.
    # END-outro is assembled as a reusable fixed asset below, so it is not
    # mixed through the generic opening/ending BGM branch.
    "355_S39-greeting": {
        "source": Path(__file__).resolve().parents[2]
        / "assets/bgm/ending/end_01_and-awaken_28sec.mp3",
        "lead_sec": 0.5,
        "tail_sec": 5.0,
        "volume": 0.34,
    },
}

# ffmpeg is not always on PATH; Remotion ships one with its compositor.
_COMPOSITOR_DIR = (
    Path(__file__).resolve().parents[2]
    / "remotion/node_modules/@remotion/compositor-win32-x64-msvc"
)
FFMPEG = shutil.which("ffmpeg") or str(_COMPOSITOR_DIR / "ffmpeg.exe")
FIXED_AUDIO_DIR = Path(__file__).resolve().parents[2] / "assets" / "audio" / "fixed"


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
        [FFMPEG, "-y", "-loglevel", "error", "-nostats"] + args,
        capture_output=True,
        check=check,
    )


def wav_duration(path: Path) -> float:
    try:
        if shutil.which("ffprobe"):
            probe = "ffprobe"
        else:
            bundled_probe = _COMPOSITOR_DIR / "ffprobe.exe"
            if not bundled_probe.is_file():
                raise FileNotFoundError(bundled_probe)
            probe = str(bundled_probe)
        result = subprocess.run(
            [
                probe, "-v", "error",
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

    # Sentence WAVs are positional. When wording changes, invalidate only the
    # changed entries so untouched sentence audio remains reusable.
    old_info_path = work_dir / "segments.json"
    old_by_index: dict[int, str] = {}
    if old_info_path.is_file():
        try:
            old_info = json.loads(old_info_path.read_text(encoding="utf-8-sig"))
            old_by_index = {
                int(p["index"]): str(p.get("text", ""))
                for p in old_info.get("pieces", [])
            }
        except (OSError, ValueError, TypeError):
            old_by_index = {}
    for piece in pieces:
        if old_by_index.get(piece["index"]) != piece["text"]:
            (work_dir / piece["wav"]).unlink(missing_ok=True)

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


def _pcm_mix(
    entries: list[tuple[Path, float, float, float, float]],
    out_wav: Path,
    sample_rate: int = SAMPLE_RATE,
) -> None:
    """Mix mono 16-bit PCM WAVs without ffmpeg filters.

    entries: (wav, gain, delay_sec, fade_in_sec, fade_out_sec). The Remotion
    bundled ffmpeg can crash on filter_complex amix in this environment, but
    this short Python mixer is deterministic and needs no external codec.
    """
    total = max(
        int(round((delay + _wav_duration_wave(path)) * sample_rate))
        for path, _gain, delay, _fade_in, _fade_out in entries
    )
    handles: list[tuple[wave.Wave_read, float, int, int, float, float]] = []
    for path, gain, delay, fade_in, fade_out in entries:
        w = wave.open(str(path), "rb")
        params = (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getcomptype())
        if params != (1, 2, sample_rate, "NONE"):
            w.close()
            raise RuntimeError(
                f"pcm params mismatch in {path.name}: {params}; "
                f"expected mono 16-bit {sample_rate}Hz PCM"
            )
        handles.append((w, gain, int(round(delay * sample_rate)), w.getnframes(), fade_in, fade_out))

    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_wav), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        chunk_size = sample_rate
        for chunk_start in range(0, total, chunk_size):
            chunk_end = min(total, chunk_start + chunk_size)
            values = [0.0] * (chunk_end - chunk_start)
            for w, gain, offset, length, fade_in, fade_out in handles:
                wav_start = chunk_start - offset
                wav_end = chunk_end - offset
                if wav_end <= 0 or wav_start >= length:
                    continue
                wav_start = max(0, wav_start)
                wav_end = min(length, wav_end)
                w.setpos(wav_start)
                raw = w.readframes(wav_end - wav_start)
                for i in range(0, len(raw), 2):
                    pos = wav_start + i // 2
                    gain_at = gain
                    if fade_in > 0 and pos < fade_in:
                        gain_at *= pos / fade_in
                    if fade_out > 0 and pos >= length - fade_out:
                        gain_at *= max(0.0, (length - pos) / fade_out)
                    values[pos - wav_start] += int.from_bytes(raw[i:i + 2], "little", signed=True) * gain_at
            frames = bytearray(len(values) * 2)
            for i, value in enumerate(values):
                clipped = max(-32768, min(32767, int(round(value))))
                frames[i * 2:i * 2 + 2] = clipped.to_bytes(2, "little", signed=True)
            out.writeframes(bytes(frames))
    for handle, *_rest in handles:
        handle.close()


def _decode_mono_pcm(source: Path, out_wav: Path) -> Path:
    if not source.is_file():
        raise RuntimeError(f"audio source not found: {source}")
    # Always decode: a previously interrupted ffmpeg call can leave a newer
    # but truncated PCM cache, and these files are tiny compared to TTS work.
    run_ffmpeg(
        [
            "-i", str(source),
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
            str(out_wav),
        ]
    )
    return out_wav


def _loop_pcm(source: Path, out_wav: Path, target_sec: float) -> Path:
    """Repeat a mono PCM WAV until it covers the requested duration."""
    if _wav_duration_wave(source) <= 0:
        raise RuntimeError(f"cannot read PCM duration: {source}")
    target_frames = int(round(target_sec * SAMPLE_RATE))
    with wave.open(str(source), "rb") as src, wave.open(str(out_wav), "wb") as out:
        if (src.getnchannels(), src.getsampwidth(), src.getframerate(), src.getcomptype()) != (
            1, 2, SAMPLE_RATE, "NONE"
        ):
            raise RuntimeError(f"pcm params mismatch in {source.name}")
        frames = src.readframes(src.getnframes())
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        written = 0
        while written < target_frames:
            take = min(len(frames) // 2, target_frames - written)
            out.writeframes(frames[:take * 2])
            written += take
    return out_wav


def _mix_op_ed(
    work_dir: Path,
    narration: Path,
    out_wav: Path,
    bgm_source: Path,
    *,
    lead_sec: float,
    tail_sec: float,
    volume: float,
) -> float:
    narration_pcm = work_dir / "narration_pcm.wav"
    bgm_pcm = work_dir / "op_ed_bgm_pcm.wav"
    _decode_mono_pcm(narration, narration_pcm)
    _decode_mono_pcm(bgm_source, bgm_pcm)
    total = _wav_duration_wave(narration_pcm) + lead_sec + tail_sec
    _pcm_mix(
        [
            (narration_pcm, 1.0, 0.0, 0.0, 0.0),
            (bgm_pcm, volume, lead_sec, 0.5, tail_sec),
        ],
        work_dir / "mixed_op_ed.wav",
    )
    shutil.copyfile(work_dir / "mixed_op_ed.wav", out_wav)
    return total


def _build_fixed_ending(
    issue_dir: Path,
    work_dir: Path,
    greeting_wav: Path,
    bgm_source: Path,
) -> tuple[Path, float, float]:
    """Build the reusable disclaimer + pause + greeting + BGM ending asset."""
    disclaimer_candidates = sorted(
        (issue_dir / "production" / "audio").glob("*_END-disclaimer.wav")
    )
    if not disclaimer_candidates:
        raise RuntimeError("fixed ending requires *_END-disclaimer.wav")
    disclaimer = disclaimer_candidates[0]
    if not disclaimer.is_file():
        raise RuntimeError(f"fixed ending requires {disclaimer.name}")
    lead_sec = 0.5
    end_card_pause_sec = 3.5
    tail_sec = 3.0
    bgm_pcm = work_dir / "fixed_ending_bgm_pcm.wav"
    _decode_mono_pcm(bgm_source, bgm_pcm)
    disclaimer_sec = _wav_duration_wave(disclaimer)
    greeting_sec = _wav_duration_wave(greeting_wav)
    total = lead_sec + disclaimer_sec + end_card_pause_sec + greeting_sec + tail_sec
    bgm_loop = work_dir / "fixed_ending_bgm_loop.wav"
    _loop_pcm(bgm_pcm, bgm_loop, total - lead_sec)
    out_wav = FIXED_AUDIO_DIR / "ending.wav"
    _pcm_mix(
        [
            (disclaimer, 1.0, lead_sec, 0.0, 0.0),
            (greeting_wav, 1.0, lead_sec + disclaimer_sec + end_card_pause_sec, 0.0, 0.0),
            (bgm_loop, 0.34, lead_sec, 0.5, tail_sec),
        ],
        out_wav,
    )
    end_card_at = lead_sec + disclaimer_sec + end_card_pause_sec
    meta = {
        "disclaimer_sec": round(disclaimer_sec, 3),
        "end_card_pause_sec": end_card_pause_sec,
        "end_card_at_sec": round(end_card_at, 3),
        "greeting_sec": round(greeting_sec, 3),
        "bgm_tail_sec": tail_sec,
        "total_sec": round(total, 3),
    }
    (work_dir / "fixed_ending_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out_wav, total, end_card_at


def ensure_sting_prefix(work_dir: Path) -> Path:
    """Render the transition sting + lead silence as a reusable PCM prefix."""
    if not STING_SOURCE.is_file():
        raise RuntimeError(f"sting source not found: {STING_SOURCE}")
    out_wav = work_dir / "sting_prefix.wav"
    sting_pcm = work_dir / "sting_pcm.wav"
    lead = work_dir / f"silence_sting_lead.wav"
    if not lead.exists():
        run_ffmpeg(
            [
                "-f", "lavfi", "-i",
                f"anullsrc=r={SAMPLE_RATE}:cl=mono",
                "-t", str(STING_LEAD_SEC), "-acodec", "pcm_s16le", str(lead),
            ]
        )
    if not sting_pcm.exists():
        run_ffmpeg(
            [
                "-i", str(STING_SOURCE),
                "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
                str(sting_pcm),
            ]
        )
    _write_concat_wave([(sting_pcm, 0.0), (lead, 0.0)], out_wav)
    return out_wav


def merge_segment(
    issue_dir: Path, work_dir: Path, seg_meta: dict, pieces: list[dict]
) -> tuple[Path, float, list[dict]]:
    use_ffmpeg = shutil.which("ffmpeg") is not None or Path(FFMPEG).is_file()
    silences = ensure_silences(work_dir) if use_ffmpeg else {}
    sting_path = None
    if seg_meta["id"] in CORNER_HEAD_IDS:
        sting_path = ensure_sting_prefix(work_dir)
        if use_ffmpeg:
            sting_duration = audio_duration(sting_path)
        else:
            sting_duration = _wav_duration_wave(sting_path)
        if sting_duration < 0:
            raise RuntimeError(f"cannot read duration: {sting_path}")
    lines = []
    concat_entries: list[tuple[Path | None, float]] = []
    timeline: list[dict] = []
    cursor = 0.0

    if sting_path is not None:
        cursor = sting_duration
        if use_ffmpeg:
            lines.append(f"file '{sting_path.resolve().as_posix()}'")
        else:
            concat_entries.append((sting_path, 0.0))

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
    merged_wav = out_wav
    if use_ffmpeg:
        combined = work_dir / "combined.wav"
        run_ffmpeg(
            ["-f", "concat", "-safe", "0", "-i", str(list_path), "-c", "copy", str(combined)]
        )
        run_ffmpeg(
            [
                "-i", str(combined),
                "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
                str(merged_wav),
            ]
        )
    else:
        _write_concat_wave(concat_entries, merged_wav)
    op_ed = OP_ED_BGM.get(stem)
    if op_ed is not None:
        lead = float(op_ed["lead_sec"])
        tail = float(op_ed["tail_sec"])
        for sentence in timeline:
            sentence["start"] += lead
            sentence["end"] += lead
        bgm_source = Path(op_ed["source"])
        if not bgm_source.is_file():
            raise RuntimeError(f"BGM source not found: {bgm_source}")
        cursor = _mix_op_ed(
            work_dir, merged_wav, out_wav, bgm_source,
            lead_sec=lead, tail_sec=tail, volume=float(op_ed["volume"]),
        )
    elif seg_meta["id"] == "END-outro":
        bgm_source = (
            Path(__file__).resolve().parents[2]
            / "assets/bgm/ending/end_01_and-awaken_28sec.mp3"
        )
        if not bgm_source.is_file():
            raise RuntimeError(f"BGM source not found: {bgm_source}")
        FIXED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        greeting_pcm = work_dir / "greeting_pcm.wav"
        _decode_mono_pcm(out_wav, greeting_pcm)
        fixed_wav, fixed_total, end_card_at = _build_fixed_ending(
            issue_dir, work_dir, greeting_pcm, bgm_source
        )
        shutil.copyfile(fixed_wav, out_wav)
        for sentence in timeline:
            sentence["start"] += end_card_at
            sentence["end"] += end_card_at
        cursor = fixed_total
        meta_path = FIXED_AUDIO_DIR / "ending.json"
        meta_path.write_text(
            json.dumps(
                {
                    "asset": "assets/audio/fixed/ending.wav",
                    "endCardAtSec": round(end_card_at, 3),
                    "durationSec": round(fixed_total, 3),
                },
                ensure_ascii=False, indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        print(f"[fixed] ending -> {fixed_wav}, end card at {end_card_at:.3f}s")
    elif seg_meta["id"] == "END-disclaimer":
        greeting_candidates = sorted(audio_dir.glob("*_END-outro.wav"))
        if greeting_candidates:
            bgm_source = (
                Path(__file__).resolve().parents[2]
                / "assets/bgm/ending/end_01_and-awaken_28sec.mp3"
            )
            if not bgm_source.is_file():
                raise RuntimeError(f"BGM source not found: {bgm_source}")
            FIXED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
            fixed_wav, fixed_total, end_card_at = _build_fixed_ending(
                issue_dir, work_dir, greeting_candidates[-1], bgm_source
            )
            shutil.copyfile(fixed_wav, out_wav)
            for sentence in timeline:
                sentence["start"] += 0.5
                sentence["end"] += 0.5
            cursor = fixed_total
            meta_path = FIXED_AUDIO_DIR / "ending.json"
            meta_path.write_text(
                json.dumps(
                    {
                        "asset": "assets/audio/fixed/ending.wav",
                        "endCardAtSec": round(end_card_at, 3),
                        "durationSec": round(fixed_total, 3),
                    },
                    ensure_ascii=False, indent=2,
                ) + "\n",
                encoding="utf-8",
            )
            print(f"[fixed] ending -> {fixed_wav}, end card at {end_card_at:.3f}s")
    return out_wav, cursor, timeline


# -------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="Generate narration audio (Fish Audio via Mac)")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="show plan only, no SSH")
    parser.add_argument("--force", action="store_true", help="re-synthesize existing wavs")
    parser.add_argument("--only", nargs="+", default=None, help="segment ids to process")
    parser.add_argument(
        "--engine",
        choices=("auto", "local", "mac"),
        default=os.getenv("FISH_TTS_ENGINE", "auto"),
        help="local = WSL2 server (default when reachable), mac = MLX over SSH",
    )
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
        engine, backend = build_engine(args.issue_date, args.engine, ensure=False)
        print(f"[plan] engine      : {backend}")
        print(f"[plan] endpoint  : {engine.remote_root}")
        print("[plan] dry-run: no connection made")
        return 0

    if all_jobs:
        engine, backend = build_engine(args.issue_date, args.engine, ensure=True)
        print(f"[synth] engine: {backend} -> {engine.remote_root}")
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

    out_path = issue_dir / "production" / "audio" / "durations.json"
    if args.only and out_path.is_file():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8-sig"))
            existing_segments = {
                item.get("id"): item
                for item in existing.get("segments", [])
                if item.get("id")
            }
        except (OSError, json.JSONDecodeError):
            print(f"[warn] cannot merge invalid durations: {out_path}")
            existing_segments = {}
    else:
        existing_segments = {}

    merged = bool(existing_segments)
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

    if merged:
        processed = {item["id"] for item in durations["segments"]}
        preserved = sorted(
            (item for item in existing_segments.values() if item.get("id") not in processed),
            key=lambda item: (item.get("order", 0), item.get("id", "")),
        )
        durations["segments"].extend(preserved)
        durations["segments"].sort(key=lambda item: (item.get("order", 0), item.get("id", ""))
        )
        total = sum(float(item.get("duration", 0)) for item in durations["segments"])
    if any(s["id"] == "S00-intro" for s in durations["segments"]):
        FIXED_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        intro = next(s for s in durations["segments"] if s["id"] == "S00-intro")
        shutil.copyfile(issue_dir / intro["file"], FIXED_AUDIO_DIR / "opening.wav")
        print(f"[fixed] opening -> {FIXED_AUDIO_DIR / 'opening.wav'}")
    out_path.write_text(
        json.dumps(durations, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[done] total {total / 60:.1f} min -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

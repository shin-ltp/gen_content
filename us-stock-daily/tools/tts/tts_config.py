"""us-stock-daily TTS pipeline configuration."""
from __future__ import annotations

import os
from datetime import datetime, time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

TOOLS_TTS_DIR = Path(__file__).resolve().parent
US_STOCK_DAILY = TOOLS_TTS_DIR.parent.parent

# Voice reference audio lives with the show's production assets.
REFS_ROOT = US_STOCK_DAILY / "assets" / "cast_refs"
DEFAULT_VOICES = ("xiaomei", "kyoujyu")

# Remote Fish Audio worker on the Mac (Apple Silicon MLX).
FISH_REMOTE_HOST = os.getenv("FISH_AUDIO_TTS_REMOTE_HOST", "cho@rw-mac-1").strip()
FISH_REMOTE_VENV = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_VENV", "/Users/cho/fish-audio/.venv"
).strip()
FISH_REMOTE_WORKROOT = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_WORKROOT", "/Users/cho/fish-audio/jobs"
).strip()
FISH_REMOTE_WORKER = os.getenv(
    "FISH_AUDIO_TTS_REMOTE_WORKER", "/Users/cho/fish-audio/scripts/fish_audio_mlx_worker.py"
).strip()

# Mac parallel window: work assigned to Mac must FINISH by 10:00 JST.
MAC_WINDOW_END = dt_time(10, 0)
MAC_CHARS_PER_SEC = float(os.getenv("FISH_MAC_CHARS_PER_SEC", "2.0"))
MAC_WINDOW_SAFETY = min(1.0, max(0.05, float(os.getenv("FISH_MAC_WINDOW_SAFETY", "0.75"))))


def mac_window_remaining_sec(now: datetime | None = None) -> float:
    now = now or datetime.now(ZoneInfo("Asia/Tokyo"))
    end = now.replace(
        hour=MAC_WINDOW_END.hour, minute=MAC_WINDOW_END.minute,
        second=0, microsecond=0,
    )
    return max(0.0, (end - now).total_seconds())


def mac_char_budget(now: datetime | None = None) -> int:
    """Max chars assignable to Mac so the batch is estimated to end by 10:00.

    Rate default ~2.0 chars/s is measured from the 2026-09-22 run (321 remote
    sentence jobs, upload/download included). Tune with FISH_MAC_CHARS_PER_SEC
    and FISH_MAC_WINDOW_SAFETY.
    """
    remaining = mac_window_remaining_sec(now)
    if remaining <= 0:
        return 0
    return max(0, int(remaining * MAC_CHARS_PER_SEC * MAC_WINDOW_SAFETY))

# Audio format (Remotion friendly: 44.1kHz / mono / 16bit PCM WAV).
SAMPLE_RATE = 44100
WAV_MIN_SIZE = 1000

# Silence inserted at merge time. Pause markers are never sent to Fish Audio.
SILENCE_PAUSE_LONG_SEC = 1.0
SILENCE_PAUSE_SHORT_SEC = 0.45
SILENCE_PERIOD_SEC = 0.35

# Japanese narration speed used for duration estimates (chars/sec).
CHARS_PER_SEC_JA = 350 / 60


def get_issue_dir(issue_date: str) -> Path:
    d = US_STOCK_DAILY / "daily-output" / issue_date
    if not d.is_dir():
        raise FileNotFoundError(f"issue directory not found: {d}")
    return d


def voice_ref_paths(voice: str) -> tuple[Path, Path]:
    ref_dir = REFS_ROOT / voice
    audio = ref_dir / "ref_audio.wav"
    meta = ref_dir / "ref_meta.json"
    if not audio.is_file():
        raise FileNotFoundError(f"voice reference audio not found: {audio}")
    if not meta.is_file():
        raise FileNotFoundError(f"voice reference meta not found: {meta}")
    return audio, meta

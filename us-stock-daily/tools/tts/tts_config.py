"""us-stock-daily TTS pipeline configuration."""
from __future__ import annotations

import os
from pathlib import Path

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

"""One-shot end-to-end check of FishLocalEngine against the WSL2 server.

Synthesizes a short sentence for xiaomei into production/.local_engine_test/
and prints duration + size. Safe: does not touch real episode wavs.
"""
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fish_batch import FishJob
from fish_local_engine import FishLocalEngine, server_reachable

issue_date = sys.argv[1] if len(sys.argv) > 1 else "2026-08-28"
assert server_reachable(), "WSL2 server not reachable"

engine = FishLocalEngine(issue_date)
text = "本日のもっとも重要なニュースを三つ、厳選してお伝えします。"
job = FishJob(
    voice="xiaomei",
    text=text,
    rel_wav="production/.local_engine_test/selftest.wav",
    index=0,
)
t0 = time.time()
engine.synthesize([job])
dt = time.time() - t0

wav = engine.issue_dir / job.rel_wav
with wave.open(str(wav), "rb") as w:
    dur = w.getnframes() / w.getframerate()
    print(
        f"OK file={wav} size={wav.stat().st_size}B "
        f"rate={w.getframerate()}Hz ch={w.getnchannels()} "
        f"audio_dur={dur:.2f}s wall={dt:.1f}s"
    )

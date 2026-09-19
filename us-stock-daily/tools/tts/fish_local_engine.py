"""Fish Audio S2 Pro synthesis against the local WSL2 server (Windows host).

Default backend for us-stock-daily since 2026-09-02:
    WSL2 Ubuntu-24.04 + torch.compile(triton) + INT8 weights (SKIP_GFX1103_FIX=1)
    -> 317-338 ms/token steady state (~4x faster than Windows-native eager).
    Server ops: see tools/fishaudio-s2-pro/README.md ("WSL2 + compile" section).

This module only speaks HTTP to the api_server and writes sentence WAVs to
exactly the same issue_dir-relative paths the Mac engine uses, so
generate_audio.py's merge/validate/durations logic works unchanged.

Engine selection: build_engine(issue_date, mode) with mode
    auto  -> local WSL2 server; before 10:00 JST, also use Mac MLX in
             parallel when SSH is reachable (default)
    local -> force WSL2 server (error if it cannot be started)
    mac   -> force Mac MLX INT8 over SSH
"""
from __future__ import annotations

import base64
import json
import os
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fish_batch import FishJob  # noqa: E402
from tts_config import get_issue_dir, voice_ref_paths  # noqa: E402

API_URL = os.getenv("FISH_LOCAL_API_URL", "http://127.0.0.1:18790/v1/tts").strip()
REQUEST_TIMEOUT_SEC = int(os.getenv("FISH_LOCAL_TTS_TIMEOUT", "1800"))
# In-flight concurrent requests per client (server-side batching makes this
# ~2.5x faster at n=3). Default 1 keeps the original sequential behavior.
CONCURRENCY = max(1, int(os.getenv("FISH_LOCAL_CONCURRENCY", "1")))
# Japanese measured ~3.5 audio tokens per char; use a safety multiple.
TOKENS_PER_CHAR = float(os.getenv("FISH_LOCAL_TOKENS_PER_CHAR", "4.2"))
WSL_DISTRO = os.getenv("FISH_LOCAL_WSL_DISTRO", "Ubuntu-24.04")
WSL_USER = os.getenv("FISH_LOCAL_WSL_USER", "root")
STARTUP_TIMEOUT_SEC = int(os.getenv("FISH_LOCAL_STARTUP_TIMEOUT", "900"))
READY_HTTP_CODES = {200, 204, 404, 405}
REPO_ROOT = Path(__file__).resolve().parents[3]
START_GUARD = REPO_ROOT / "tools" / "fishaudio-s2-pro" / "wsl" / "start_server_guard.ps1"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"    [{ts}] [fish-local] {msg}", flush=True)


def server_reachable(timeout: float = 3.0) -> bool:
    """Return True only if the HTTP service really answers (not just a port)."""
    return server_ready(timeout)


def server_ready(timeout: float = 3.0) -> bool:
    """Return True only if the HTTP service answers, not merely if a port is held."""
    try:
        req = urllib.request.Request(API_URL, method="OPTIONS")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status in READY_HTTP_CODES
    except urllib.error.HTTPError as e:
        return e.code in READY_HTTP_CODES
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_server(pipeline_date: str | None = None) -> bool:
    """Start the WSL2 fish server idempotently via the guarded launcher.

    The guard probes HTTP first, so a healthy external server is never killed.
    Retry every session; no marker can make a later turn trust an earlier turn.
    """
    if server_ready():
        return True
    if not START_GUARD.is_file():
        _log(f"server launcher missing: {START_GUARD}")
        return False
    _log("starting local WSL2 fish server via guarded launcher")
    date_args = ["-PipelineDate", pipeline_date] if pipeline_date else []
    try:
        proc = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(START_GUARD),
                "-Mode",
                "compile",
                "-WaitSeconds",
                str(STARTUP_TIMEOUT_SEC),
                *date_args,
            ],
            cwd=str(REPO_ROOT),
            timeout=STARTUP_TIMEOUT_SEC + 60,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _log(f"launcher rc={proc.returncode}")
        if proc.stdout.strip():
            _log("launcher: " + proc.stdout.strip().splitlines()[-1][:240])
        if proc.returncode != 0 and proc.stderr.strip():
            _log("launcher stderr: " + proc.stderr.strip()[-400:])
    except (OSError, subprocess.TimeoutExpired) as e:
        _log(f"failed to launch WSL server: {e}")
        return False
    if proc.returncode != 0:
        # The guard may time out while compilation is still finishing; trust
        # the HTTP probe, not the launcher exit code alone.
        _log(f"launcher rc={proc.returncode}; probing server anyway")
    return server_ready()


class FishLocalEngine:
    """Same synthesize(jobs) contract as FishDailyEngine, but via local HTTP."""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        # Parity with FishDailyEngine for --dry-run printing.
        self.remote_root = API_URL

    # ---------------------------------------------------------- request
    def _body_for(self, voice: str, text: str) -> bytes:
        audio_path, meta_path = voice_ref_paths(voice)
        ref_audio = base64.b64encode(audio_path.read_bytes()).decode("ascii")
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        ref_text = str(meta.get("ref_text", meta.get("text", ""))).strip()
        if not ref_text:
            raise RuntimeError(f"ref_text missing in {meta_path}")
        max_new_tokens = max(256, int(len(text) * TOKENS_PER_CHAR) + 64)
        return json.dumps(
            {
                "text": text,
                "format": "wav",
                "chunk_length": 200,
                "max_new_tokens": max_new_tokens,
                "normalize": True,
                "references": [{"audio": ref_audio, "text": ref_text}],
            },
            ensure_ascii=False,
        ).encode("utf-8")

    def _synthesize_one(self, voice: str, text: str, out_path: Path) -> None:
        body = self._body_for(voice, text)
        last_err: Exception | None = None
        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    API_URL,
                    data=body,
                    headers={"Content-Type": "application/json; charset=utf-8"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SEC) as resp:
                    wav = resp.read()
                if len(wav) < 1000 or wav[:4] != b"RIFF":
                    raise RuntimeError(f"bad response: {len(wav)} bytes")
                out_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = out_path.with_name(out_path.name + ".part")
                tmp.write_bytes(wav)
                tmp.replace(out_path)
                return
            except (urllib.error.URLError, TimeoutError, OSError, RuntimeError) as e:
                last_err = e
                _log(f"{out_path.name} attempt {attempt} failed: {e}")
                time.sleep(5)
        raise RuntimeError(f"local TTS failed for {out_path}: {last_err}")

    # ----------------------------------------------------------- public
    def synthesize(self, jobs: list[FishJob]) -> None:
        if not jobs:
            _log("no pending segments")
            return
        if not ensure_server():
            raise RuntimeError(
                f"local Fish server did not become ready at {API_URL}. "
                "Inspect launcher output and the WSL /root/server.log; do not "
                "substitute silence or a slower engine for missing narration."
            )
        by_voice: dict[str, list[FishJob]] = {}
        for j in jobs:
            by_voice.setdefault(j.voice, []).append(j)
        total = len(jobs)
        _log(
            f"local batch on {API_URL}: "
            + ", ".join(f"{v}={len(js)}" for v, js in sorted(by_voice.items()))
        )
        t0 = time.time()
        done = 0
        lock = threading.Lock()

        def run_one(j: FishJob):
            out_path = self.issue_dir / j.rel_wav
            ts0 = time.time()
            self._synthesize_one(j.voice, j.text, out_path)
            return j, out_path, time.time() - ts0

        if CONCURRENCY > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            _log(f"concurrency={CONCURRENCY}")
            with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
                futs = [ex.submit(run_one, j) for j in jobs]
                for fut in as_completed(futs):
                    j, out_path, dt = fut.result()
                    with lock:
                        done += 1
                        _log(f"{done}/{total} {j.voice} {out_path.name} ({dt:.1f}s)")
            _log(f"batch done: {total} wavs in {(time.time() - t0) / 60:.1f} min")
            return
        for voice, voice_jobs in sorted(by_voice.items()):
            _log(f"=== voice: {voice} ({len(voice_jobs)} segments) ===")
            for j in voice_jobs:
                out_path = self.issue_dir / j.rel_wav
                ts0 = time.time()
                self._synthesize_one(voice, j.text, out_path)
                done += 1
                _log(
                    f"{done}/{total} {voice} {out_path.name} "
                    f"({time.time() - ts0:.1f}s)"
                )
        _log(f"batch done: {total} wavs in {(time.time() - t0) / 60:.1f} min")


class ParallelFishEngine:
    """Split complete sentence directories between WSL2 and Mac."""

    def __init__(self, issue_date: str, local_engine, mac_engine):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        self.local_engine = local_engine
        self.mac_engine = mac_engine
        self.remote_root = f"{local_engine.remote_root} + {mac_engine.remote_root}"

    @staticmethod
    def _split_jobs(jobs: list[FishJob]) -> tuple[list[FishJob], list[FishJob]]:
        """Keep a segment's sentence WAVs on one host to avoid scp overlaps."""
        groups: dict[str, tuple[int, list[FishJob]]] = {}
        for job in jobs:
            rel_dir = str(Path(job.rel_wav).parent.as_posix())
            chars, group_jobs = groups.get(rel_dir, (0, []))
            groups[rel_dir] = (chars + len(job.text), group_jobs + [job])

        local: list[FishJob] = []
        mac: list[FishJob] = []
        local_chars = mac_chars = 0
        for _, (chars, group_jobs) in sorted(groups.items()):
            if local_chars <= mac_chars:
                local.extend(group_jobs)
                local_chars += chars
            else:
                mac.extend(group_jobs)
                mac_chars += chars
        _log(
            f"parallel split: local={len(local)} jobs/{local_chars} chars, "
            f"mac={len(mac)} jobs/{mac_chars} chars"
        )
        return local, mac

    def synthesize(self, jobs: list[FishJob]) -> None:
        local_jobs, mac_jobs = self._split_jobs(jobs)
        if not mac_jobs:
            self.local_engine.synthesize(local_jobs)
            return
        if not local_jobs:
            self.mac_engine.synthesize(mac_jobs)
            return

        failures: list[BaseException] = []

        def run(label: str, engine, engine_jobs: list[FishJob]) -> None:
            try:
                engine.synthesize(engine_jobs)
            except BaseException as exc:
                _log(f"{label} branch failed: {exc}")
                failures.append(exc)

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [
                pool.submit(run, "wsl2", self.local_engine, local_jobs),
                pool.submit(run, "mac", self.mac_engine, mac_jobs),
            ]
            for future in futures:
                future.result()
        if failures:
            raise RuntimeError(f"parallel TTS failed: {failures[0]}")


def mac_reachable(issue_date: str) -> tuple[bool, object | None, str]:
    """Probe Mac SSH without launching synthesis."""
    from fish_batch import FishDailyEngine

    engine = FishDailyEngine(issue_date)
    try:
        engine._ssh.ssh_short("echo OK", label="SSH(mac probe)")
    except Exception as exc:
        return False, None, str(exc)
    return True, engine, "ok"


def _warn_mac_unavailable(issue_date: str, reason: str) -> None:
    issue_dir = get_issue_dir(issue_date)
    log_path = issue_dir / "production" / "tts" / "mac-unavailable.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    with log_path.open("a", encoding="utf-8", newline="") as f:
        f.write(f"{stamp}\t{reason.replace(chr(10), ' ')}\n")
    _log(f"Mac unavailable before 10:00 JST; continuing WSL2 only: {reason}")


def build_engine(issue_date: str, engine_mode: str = "auto", *, ensure: bool = False):
    """Return (engine, backend_label); see module docstring for modes."""
    mode = (engine_mode or "auto").strip().lower()
    if mode in ("mac", "remote"):
        from fish_batch import FishDailyEngine

        return FishDailyEngine(issue_date), "mac-mlx-ssh"
    if mode in ("local", "wsl"):
        if ensure and not ensure_server(pipeline_date=issue_date):
            raise RuntimeError(f"local Fish server is not ready at {API_URL}")
        return FishLocalEngine(issue_date), "wsl2-local"
    if mode != "auto":
        raise SystemExit(f"unknown --engine value: {engine_mode}")
    if ensure and not ensure_server(pipeline_date=issue_date):
        raise RuntimeError(
            "auto engine requires the local WSL2 Fish server; refusing to "
            f"fall back to Mac for production TTS. Endpoint={API_URL}"
        )
    if not ensure and not server_ready():
        _log("local WSL2 server not ready (dry-run: startup deferred)")
    if ensure:
        now = datetime.now(ZoneInfo("Asia/Tokyo"))
        if now.hour < 10:
            reachable, mac_engine, reason = mac_reachable(issue_date)
            if reachable and mac_engine is not None:
                local_engine = FishLocalEngine(issue_date)
                return (
                    ParallelFishEngine(issue_date, local_engine, mac_engine),
                    "wsl2-local + mac-mlx-ssh",
                )
            _warn_mac_unavailable(issue_date, reason)
    return FishLocalEngine(issue_date), "wsl2-local"

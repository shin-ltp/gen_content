"""Fish Audio S2 Pro remote batch synthesis (Mac MLX via SSH/SCP).

Adapted from tools/sample/economist-podcast/scripts/fish_audio_batch.py with
one key change: jobs are grouped by voice (kyoujyu / xiaomei) and each voice
runs as its own remote batch with its own reference audio + ref_text.

Worker contract (fish_audio_mlx_worker.py on the Mac, already deployed):
    manifest := {
      "ref_audio": "<relative path under workroot>",
      "ref_text": "<reference transcript>",
      "temperature": 0.7, "top_p": 0.8,
      "segments": [{"text": ..., "wav": "<relative wav path>", "index": n}],
    }
    $ venv/python worker.py --job manifest.json --workroot ROOT --progress-file P
"""
from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from tts_config import (  # noqa: E402
    FISH_REMOTE_HOST,
    FISH_REMOTE_VENV,
    FISH_REMOTE_WORKER,
    FISH_REMOTE_WORKROOT,
    WAV_MIN_SIZE,
    get_issue_dir,
    voice_ref_paths,
)

_LOG_BYTES_MARKER = "__FISH_LOG_BYTES__:"
_STATUS_MARKER = "__FISH_STATUS__:"
_PROGRESS_MARKER = "__FISH_PROGRESS__:"


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"    [{ts}] [fish] {msg}", flush=True)


@dataclass
class FishJob:
    voice: str
    text: str
    rel_wav: str  # posix path relative to the episode dir (mirrors remote root)
    index: int


class _PlainSSHRemote:
    """Plain ssh/scp wrapper (no ControlMaster on Windows OpenSSH)."""

    def __init__(self, host: str):
        self.host = host

    @staticmethod
    def _ssh_opts() -> list[str]:
        return [
            "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=3",
            "-o", "ControlMaster=no",
        ]

    @staticmethod
    def _is_dns_error(err: str) -> bool:
        e = (err or "").lower()
        return (
            "could not resolve hostname" in e
            or "name or service not known" in e
            or "nodename nor servname" in e
        )

    def ssh_short(self, remote_cmd: str, *, label: str = "SSH", timeout: int = 60) -> str:
        cmd = ["ssh", *self._ssh_opts(), self.host, remote_cmd]
        last_err = ""
        for attempt in range(3):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout
                )
                if result.returncode == 0:
                    return result.stdout or ""
                last_err = (result.stderr or "").strip()
            except subprocess.TimeoutExpired:
                last_err = "SSH timeout"
            if self._is_dns_error(last_err) and attempt == 0:
                time.sleep(2)
                continue
            if attempt < 2:
                time.sleep(3)
        raise RuntimeError(f"{label} failed: {last_err}")

    def run_with_retry(
        self, cmd_list: list[str], *, timeout: int, label: str = "SCP"
    ) -> subprocess.CompletedProcess:
        last_err = None
        for attempt in range(3):
            try:
                result = subprocess.run(cmd_list, capture_output=True, timeout=timeout)
                if result.returncode == 0:
                    return result
                last_err = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
            except subprocess.TimeoutExpired:
                last_err = f"{label} timeout ({timeout}s)"
            if self._is_dns_error(str(last_err)) and attempt == 0:
                time.sleep(2)
                continue
            if attempt < 2:
                time.sleep(10)
        raise RuntimeError(f"{label} failed: {last_err}")

    def scp_to_remote(self, local: Path | str, remote: str) -> list[str]:
        return ["scp", *self._ssh_opts(), str(local), f"{self.host}:{remote}"]

    def scp_recursive_from_remote(self, remote_dir: str, local_dir: Path) -> list[str]:
        return [
            "scp", "-r", *self._ssh_opts(), f"{self.host}:{remote_dir}", str(local_dir)
        ]


class FishDailyEngine:
    """Remote Fish Audio batch synthesis for one us-stock-daily episode."""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        self.remote_root = f"{FISH_REMOTE_WORKROOT.rstrip('/')}/usdaily/{issue_date}"
        self._ssh = _PlainSSHRemote(FISH_REMOTE_HOST)

    # ------------------------------------------------------------ helpers
    def _voice_batch_paths(self, voice: str) -> dict[str, str]:
        base = f"{self.remote_root}/{voice}"
        return {
            "manifest": f"{base}/job_manifest.json",
            "log": f"{base}/worker.log",
            "pid": f"{base}/worker.pid",
            "progress": f"{base}/worker.progress.json",
        }

    def _ref_text(self, voice: str) -> str:
        _, meta_path = voice_ref_paths(voice)
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        ref_text = str(meta.get("ref_text", meta.get("text", ""))).strip()
        if not ref_text:
            raise RuntimeError(f"ref_text missing in {meta_path}")
        return ref_text

    def _remote_wav_exists(self, rel_wav: str) -> bool:
        remote = f"{self.remote_root}/{rel_wav}"
        out = self._ssh.ssh_short(
            f"if [ -f '{remote}' ] && [ $(wc -c < '{remote}') -ge {WAV_MIN_SIZE} ]; "
            "then echo YES; else echo NO; fi",
            label="SSH(check wav)",
        )
        return out.strip() == "YES"

    # ------------------------------------------------------- remote worker
    def _prepare_remote(self, voices: set[str]) -> None:
        dirs = [self.remote_root]
        for v in voices:
            dirs.append(f"{self.remote_root}/{v}/refs")
        worker_parent = str(Path(FISH_REMOTE_WORKER).parent)
        if worker_parent not in (".", "~", "/"):
            dirs.append(worker_parent)
        self._ssh.ssh_short("mkdir -p " + " ".join(dirs), label="SSH(mkdir)")

    def _upload_refs(self, voice: str) -> None:
        audio, meta = voice_ref_paths(voice)
        remote_dir = f"{self.remote_root}/{voice}/refs"
        self._ssh.run_with_retry(
            self._ssh.scp_to_remote(audio, f"{remote_dir}/ref_audio.wav"),
            timeout=600,
            label=f"SCP(ref audio {voice})",
        )
        self._ssh.run_with_retry(
            self._ssh.scp_to_remote(meta, f"{remote_dir}/ref_meta.json"),
            timeout=600,
            label=f"SCP(ref meta {voice})",
        )

    def _poll_once(self, paths: dict[str, str], log_offset: int) -> tuple[int, str | None]:
        voice = paths["manifest"].rsplit("/", 2)[-2]
        fetch = (
            f"prog=$(cat {paths['progress']} 2>/dev/null | tr -d '\\n' || echo '{{}}'); "
            f"bytes=$(wc -c < {paths['log']} 2>/dev/null || echo 0); "
            f"if [ $bytes -gt {log_offset} ]; then tail -c +{log_offset + 1} {paths['log']}; fi; "
            f"echo {_PROGRESS_MARKER}$prog; "
            f"echo {_LOG_BYTES_MARKER}$bytes; "
            f"if [ -f {paths['pid']} ] && kill -0 $(cat {paths['pid']}) 2>/dev/null; "
            f"then echo {_STATUS_MARKER}RUNNING; "
            f"elif grep -q '^Done\\.' {paths['log']} 2>/dev/null; "
            f"then echo {_STATUS_MARKER}SUCCESS; "
            f"else echo {_STATUS_MARKER}STOPPED; fi"
        )
        out = self._ssh.ssh_short(fetch, label="SSH(poll)")
        new_offset = log_offset
        status: str | None = None

        if _STATUS_MARKER in out:
            body, _, tail = out.rpartition(_STATUS_MARKER)
            status = tail.strip().splitlines()[0] if tail.strip() else None
            out = body
        if _LOG_BYTES_MARKER in out:
            body, _, tail = out.rpartition(_LOG_BYTES_MARKER)
            try:
                new_offset = int(tail.strip().splitlines()[0])
            except (ValueError, IndexError):
                pass
            out = body
        if _PROGRESS_MARKER in out:
            body, _, tail = out.rpartition(_PROGRESS_MARKER)
            raw = tail.strip().splitlines()[0] if tail.strip() else ""
            try:
                prog = json.loads(raw)
                done = int(prog.get("done", 0))
                total = int(prog.get("total", 0))
                current = str(prog.get("current", ""))
                if total > 0:
                    _log(f"{voice} progress: {done}/{total} ({current})")
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            out = body

        if out.strip():
            sys.stdout.write(out)
            if not out.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()
        return new_offset, status

    def _poll_until_done(self, paths: dict[str, str], timeout: int = 86400) -> None:
        _log("polling remote worker (15s interval)")
        deadline = time.time() + timeout
        log_offset = 0
        failures = 0
        while time.time() < deadline:
            try:
                log_offset, status = self._poll_once(paths, log_offset)
                failures = 0
            except RuntimeError as e:
                failures += 1
                _log(f"poll failed ({failures}): {e}")
                if failures >= 3:
                    raise
                time.sleep(10)
                continue

            if status == "SUCCESS":
                _log("remote worker finished")
                return
            if status == "STOPPED":
                tail = self._ssh.ssh_short(
                    f"tail -n 40 {paths['log']} 2>/dev/null || true",
                    label="SSH(tail)",
                )
                raise RuntimeError(
                    "remote worker crashed:\n" + (tail[-1500:] if tail else "(no log)")
                )
            time.sleep(15)
        raise RuntimeError(f"remote worker timeout ({timeout}s)")

    def _download(self, jobs: list[FishJob]) -> None:
        # Group by work dir and pull whole dirs (fewer scp handshakes).
        by_dir: dict[str, list[FishJob]] = {}
        for j in jobs:
            parent = str(PurePosixPathParent(j.rel_wav))
            by_dir.setdefault(parent, []).append(j)

        for rel_dir, group in sorted(by_dir.items()):
            local_parent = self.issue_dir / Path(rel_dir).parent
            local_parent.mkdir(parents=True, exist_ok=True)
            _log(f"download {rel_dir} ({len(group)} wavs)")
            self._ssh.run_with_retry(
                self._ssh.scp_recursive_from_remote(
                    f"{self.remote_root}/{rel_dir}", local_parent
                ),
                timeout=900,
                label="SCP(wavs)",
            )

        missing = [
            j.rel_wav
            for j in jobs
            if not (self.issue_dir / Path(j.rel_wav)).is_file()
            or (self.issue_dir / Path(j.rel_wav)).stat().st_size < WAV_MIN_SIZE
        ]
        if missing:
            raise RuntimeError(f"download incomplete, {len(missing)} wav(s) missing")

    # ------------------------------------------------------------- public
    def synthesize(self, jobs: list[FishJob]) -> None:
        if not jobs:
            _log("no pending segments")
            return

        by_voice: dict[str, list[FishJob]] = {}
        for j in jobs:
            by_voice.setdefault(j.voice, []).append(j)

        _log(
            f"remote batch on {FISH_REMOTE_HOST}: "
            + ", ".join(f"{v}={len(js)}" for v, js in sorted(by_voice.items()))
        )

        self._prepare_remote(set(by_voice))

        for voice, voice_jobs in sorted(by_voice.items()):
            _log(f"=== voice: {voice} ({len(voice_jobs)} segments) ===")
            self._upload_refs(voice)
            paths = self._voice_batch_paths(voice)

            manifest = {
                "ref_audio": f"{voice}/refs/ref_audio.wav",
                "ref_text": self._ref_text(voice),
                "temperature": 0.7,
                "top_p": 0.8,
                "segments": [
                    {"text": j.text, "wav": j.rel_wav, "index": j.index}
                    for j in voice_jobs
                ],
            }
            # Remote manifest is written WITHOUT BOM (worker json.load safety).
            manifest_local = self.issue_dir / "production" / f".fish_manifest_{voice}.json"
            manifest_local.parent.mkdir(parents=True, exist_ok=True)
            manifest_local.write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._ssh.run_with_retry(
                self._ssh.scp_to_remote(manifest_local, paths["manifest"]),
                timeout=600,
                label=f"SCP(manifest {voice})",
            )

            inner = (
                f"{FISH_REMOTE_VENV}/bin/python -u {FISH_REMOTE_WORKER} "
                f"--job {paths['manifest']} "
                f"--workroot {self.remote_root} "
                f"--progress-file {paths['progress']}"
            )
            self._ssh.ssh_short(
                f"rm -f {paths['progress']}; : > {paths['log']}",
                label="SSH(cleanup)",
            )
            launch_script = f"{self.remote_root}/{voice}/launch_worker.sh"
            b64 = base64.b64encode(f"#!/bin/bash\n{inner}\n".encode()).decode()
            self._ssh.ssh_short(
                f"echo {b64} | base64 -d > {launch_script} && chmod +x {launch_script}",
                label="SSH(write launch)",
            )
            pid = self._ssh.ssh_short(
                f"nohup bash {launch_script} > {paths['log']} 2>&1 & echo $! > {paths['pid']}",
                label="SSH(launch)",
            )
            _log(f"worker started (pid={pid.strip() or '?'})")
            self._poll_until_done(paths)

        self._download(jobs)
        _log("all wavs downloaded")


def PurePosixPathParent(rel: str) -> str:
    parts = rel.split("/")
    return "/".join(parts[:-1])

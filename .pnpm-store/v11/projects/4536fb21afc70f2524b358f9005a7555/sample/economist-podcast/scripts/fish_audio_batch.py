"""Fish Audio S2 Pro INT8 remote batch synthesis (Mac MLX via SSH/SCP).

Uses _PlainSSHRemote (plain ssh/scp) to cho@rw-mac-1 — not gcloud compute ssh.
Worker: fish_audio_mlx_worker.py (Apple Silicon MLX INT8).
"""
from __future__ import annotations

import base64
import json
import re
import sys
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import (
    FISH_AUDIO_TTS_CHECKPOINT,
    FISH_AUDIO_TTS_CHUNK_LENGTH,
    FISH_AUDIO_TTS_COMPILE,
    FISH_AUDIO_TTS_HALF,
    FISH_AUDIO_TTS_MAX_SEQ_LEN,
    FISH_AUDIO_TTS_REF_AUDIO,
    FISH_AUDIO_TTS_REF_META,
    FISH_AUDIO_TTS_REMOTE_HOST,
    FISH_AUDIO_TTS_REMOTE_PROJECT,
    FISH_AUDIO_TTS_REMOTE_PYTHONPATH,
    FISH_AUDIO_TTS_REMOTE_VENV,
    FISH_AUDIO_TTS_REMOTE_WORKROOT,
    FISH_AUDIO_TTS_REMOTE_WORKER,
    FISH_AUDIO_TTS_REMOTE_ZONE,
    GCP_PROJECT_ID,
    PROJECT_ROOT,
    get_issue_dir,
)
from qwen_tts_batch import cleanup_stale_local_ssh


class _PlainSSHRemote:
    """Plain SSH/SCP wrapper for non-GCP hosts (e.g. Mac MLX).

    On non-Windows, uses ControlMaster so poll loops reuse one TCP session.
    Windows OpenSSH ControlMaster often fails with
    ``getsockname failed: Not a socket`` — disabled there.
    """

    def __init__(self, host: str, *, lock_path: Path | None = None):
        self.host = host
        self.lock_path = lock_path
        self._control_path: Path | None = None
        # ControlMaster needs Unix domain sockets; unreliable on Windows OpenSSH.
        if lock_path is not None and sys.platform != "win32":
            safe = re.sub(r"[^\w.-]+", "_", host)
            self._control_path = lock_path.parent / f".ssh_cm_{safe}"

    def _ssh_opts(self) -> list[str]:
        opts = [
            "-o", "ConnectTimeout=15",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", "BatchMode=yes",
            "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=3",
        ]
        if self._control_path is not None:
            opts += [
                "-o", "ControlMaster=auto",
                "-o", f"ControlPath={self._control_path}",
                "-o", "ControlPersist=600",
            ]
        else:
            opts += ["-o", "ControlMaster=no"]
        return opts

    @staticmethod
    def _is_dns_error(err: str) -> bool:
        e = (err or "").lower()
        return (
            "could not resolve hostname" in e
            or "name or service not known" in e
            or "nodename nor servname" in e
        )

    def ssh_short(self, remote_cmd: str, *, label: str = "SSH") -> str:
        cmd = ["ssh", *self._ssh_opts(), self.host, remote_cmd]
        last_err = ""
        for attempt in range(3):
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    return result.stdout or ""
                last_err = (result.stderr or "").strip()
            except subprocess.TimeoutExpired:
                last_err = "SSH timeout"
            # mDNS (.local) 失敗は短い待機で1回だけ再試行（3×長待ちしない）
            if self._is_dns_error(last_err):
                if attempt == 0:
                    time.sleep(2)
                    continue
                break
            if attempt < 2:
                time.sleep(3)
        raise RuntimeError(f"{label} failed: {last_err}")

    def run_with_retry(self, cmd_list, *, timeout: int, label: str = "SCP") -> subprocess.CompletedProcess:
        last_err = None
        for attempt in range(3):
            try:
                result = subprocess.run(cmd_list, capture_output=True, timeout=timeout)
                if result.returncode == 0:
                    return result
                last_err = result.stderr.decode("utf-8", errors="replace").strip()[-500:]
            except subprocess.TimeoutExpired:
                last_err = f"{label} timeout ({timeout}s)"
            if self._is_dns_error(str(last_err)):
                if attempt == 0:
                    time.sleep(2)
                    continue
                break
            if attempt < 2:
                time.sleep(10)
        raise RuntimeError(f"{label} failed: {last_err}")

    def scp_to_remote(self, local: Path | str, remote: str) -> list[str]:
        return ["scp", *self._ssh_opts(), str(local), f"{self.host}:{remote}"]

    def scp_from_remote(self, remote: str, local: Path | str) -> list[str]:
        return ["scp", *self._ssh_opts(), f"{self.host}:{remote}", str(local)]

    def scp_recursive_from_remote(self, remote_dir: str, local_dir: Path | str) -> list[str]:
        return [
            "scp", "-r", *self._ssh_opts(),
            f"{self.host}:{remote_dir}", str(local_dir),
        ]
WAV_MIN_SIZE = 1000

_LOG_BYTES_MARKER = "__FISH_LOG_BYTES__:"
_STATUS_MARKER = "__FISH_STATUS__:"
_PROGRESS_MARKER = "__FISH_PROGRESS__:"


def _fish_log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"      [{ts}] [FishAudio] {msg}", flush=True)


@dataclass
class FishAudioSegmentJob:
    work_dir: Path
    seg: dict


def _load_ref_text() -> str:
    meta_path = FISH_AUDIO_TTS_REF_META
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ref_text = str(meta.get("text", meta.get("ref_text", ""))).strip()
        if ref_text:
            return ref_text
    raise RuntimeError(
        f"Fish Audio reference text not found. Set FISH_AUDIO_TTS_REF_META: {meta_path}"
    )


def _remote_job_root(issue_date: str) -> str:
    return f"{FISH_AUDIO_TTS_REMOTE_WORKROOT.rstrip('/')}/{issue_date}"


def _wav_rel_path(issue_dir: Path, work_dir: Path, wav_file: str) -> str:
    rel = work_dir.relative_to(issue_dir)
    return str(rel / wav_file).replace("\\", "/")


class FishAudioBatchEngine:
    """Remote Fish Audio S2 Pro INT8 batch synthesis (Mac MLX worker over SSH)."""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        self.remote_root = _remote_job_root(issue_date)
        self._ref_text = _load_ref_text()
        self._gcloud = _PlainSSHRemote(
            FISH_AUDIO_TTS_REMOTE_HOST,
            lock_path=self.issue_dir / ".gcloud_ssh.lock",
        )
        self._log_path = f"{self.remote_root}/worker.log"
        self._pid_path = f"{self.remote_root}/worker.pid"
        self._progress_path = f"{self.remote_root}/worker.progress.json"
        self._last_reported_done = -1
        self._poll_expected_total = 0
        self._batch_episode: str | None = None
        self._current_pending: list[dict] = []

    @staticmethod
    def _infer_episode_id(pending: list[dict]) -> str | None:
        eps: set[str] = set()
        for seg in pending:
            parts = seg["wav"].replace("\\", "/").split("/")
            if len(parts) >= 2 and parts[0] == "episodes":
                eps.add(parts[1])
        return next(iter(eps)) if len(eps) == 1 else None

    def _set_batch_context(self, pending: list[dict]) -> None:
        self._current_pending = pending
        self._batch_episode = self._infer_episode_id(pending)
        if self._batch_episode:
            ep_base = f"{self.remote_root}/episodes/{self._batch_episode}"
            self._log_path = f"{ep_base}/worker.log"
            self._pid_path = f"{ep_base}/worker.pid"
            self._progress_path = f"{ep_base}/worker.progress.json"
            _fish_log(f"Episode context: episodes/{self._batch_episode}/")

    def _ensure_remote_setup(self) -> None:
        parts = [f"{self.remote_root}/episodes"]
        if self._batch_episode:
            parts.append(f"{self.remote_root}/episodes/{self._batch_episode}")
        worker_parent = FISH_AUDIO_TTS_REMOTE_WORKER.rsplit("/", 1)[0]
        if worker_parent and worker_parent not in (".", "~"):
            parts.append(worker_parent)
        cmd = "mkdir -p " + " ".join(parts)
        self._gcloud.ssh_short(cmd, label="SSH(fish setup)")

    def _remote_wav_ready_count(self, pending: list[dict]) -> int:
        if not pending:
            return 0
        prefixes = self._download_prefixes_for_pending(pending)
        total = 0
        for prefix in sorted(prefixes):
            remote_aw = f"{self.remote_root}/{prefix}/audio_work"
            cmd = (
                f"find {remote_aw} -type f -name 'seg_*.wav' "
                f"-size +{WAV_MIN_SIZE}c 2>/dev/null | wc -l"
            )
            try:
                out = self._gcloud.ssh_short(cmd, label="SSH(count fish wavs)")
                total += int(out.strip())
            except (RuntimeError, ValueError):
                pass
        return total

    def _count_local_pending(self, pending: list[dict]) -> int:
        return sum(
            1
            for seg in pending
            if (self.issue_dir / seg["wav"]).is_file()
            and (self.issue_dir / seg["wav"]).stat().st_size >= WAV_MIN_SIZE
        )

    def _emit_progress(self, prog: dict) -> bool:
        try:
            done = int(prog.get("done", 0))
            total = int(prog.get("total") or self._poll_expected_total or 0)
        except (TypeError, ValueError):
            return False
        if total <= 0:
            total = self._poll_expected_total
        if total <= 0:
            return False
        if done <= self._last_reported_done and self._last_reported_done >= 0:
            return False

        self._last_reported_done = done
        current = str(prog.get("current", ""))
        short = Path(current.replace("\\", "/")).name if current else ""
        pct = 100.0 * done / total
        avg_rtf = prog.get("avg_rtf", 0)
        if short and short not in ("starting", "done"):
            detail = f" — {short}"
        elif current == "done":
            rtf_info = f" | avg RTF={avg_rtf:.2f}" if avg_rtf else ""
            detail = f" — 完了{rtf_info}"
        else:
            detail = ""
        _fish_log(f"远程合成进度: {done}/{total} ({pct:.1f}%){detail}")
        return True

    def _remote_worker_status(self) -> str:
        cmd = (
            f"if [ -f {self._pid_path} ] && kill -0 $(cat {self._pid_path}) 2>/dev/null; then "
            f"echo RUNNING; "
            f"elif grep -q '^Done\\.' {self._log_path} 2>/dev/null; then "
            f"echo SUCCESS; "
            f"else echo STOPPED; fi"
        )
        return self._gcloud.ssh_short(cmd, label="SSH(fish status)").strip()

    def _poll_once(self, log_offset: int) -> tuple[int, str | None]:
        fetch = (
            f"prog=$(cat {self._progress_path} 2>/dev/null | tr -d '\\n' || echo '{{}}'); "
            f"bytes=$(wc -c < {self._log_path} 2>/dev/null || echo 0); "
            f"if [ $bytes -gt {log_offset} ]; then "
            f"  tail -c +{log_offset + 1} {self._log_path}; "
            f"fi; "
            f"echo {_PROGRESS_MARKER}$prog; "
            f"echo {_LOG_BYTES_MARKER}$bytes; "
            f"if [ -f {self._pid_path} ] && kill -0 $(cat {self._pid_path}) 2>/dev/null; then "
            f"echo {_STATUS_MARKER}RUNNING; "
            f"elif grep -q '^Done\\.' {self._log_path} 2>/dev/null; then "
            f"echo {_STATUS_MARKER}SUCCESS; "
            f"else echo {_STATUS_MARKER}STOPPED; fi"
        )
        out = self._gcloud.ssh_short(fetch, label="SSH(fish poll)")
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
                self._emit_progress(prog)
            except (json.JSONDecodeError, ValueError):
                pass
            out = body

        if out.strip():
            sys.stdout.write(out)
            if not out.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

        return new_offset, status

    def _poll_until_done(self, poll_interval: int = 15, timeout: int = 86400) -> None:
        _fish_log(f"轮询远程 worker (每{poll_interval}s, timeout={timeout}s)")
        deadline = time.time() + timeout
        log_offset = 0
        consecutive_failures = 0

        while time.time() < deadline:
            try:
                log_offset, status = self._poll_once(log_offset)
                consecutive_failures = 0
            except RuntimeError as e:
                consecutive_failures += 1
                _fish_log(f"轮询失败 ({consecutive_failures}): {e}")
                if consecutive_failures >= 3:
                    status = self._remote_worker_status()
                    if status == "RUNNING":
                        consecutive_failures = 0
                    elif status == "SUCCESS":
                        return
                time.sleep(10)
                continue

            if status == "SUCCESS":
                try:
                    raw = self._gcloud.ssh_short(
                        f"cat {self._progress_path} 2>/dev/null | tr -d '\\n' || true",
                        label="SSH(final progress)",
                    )
                    prog = json.loads(raw) if raw.strip() else {}
                    self._emit_progress(prog)
                except (RuntimeError, json.JSONDecodeError):
                    pass
                _fish_log("远程 worker 正常结束")
                return
            if status == "STOPPED":
                tail_err = self._gcloud.ssh_short(
                    f"tail -n 40 {self._log_path} 2>/dev/null || true",
                    label="SSH(fish tail)",
                )
                raise RuntimeError(
                    "远程 Fish Audio worker 异常结束:\n"
                    + (tail_err[-1500:] if tail_err else "(无日志)")
                )

            time.sleep(poll_interval)

        raise RuntimeError(f"远程 worker 超时 ({timeout}s)")

    def _upload_ref_assets(self) -> None:
        if not FISH_AUDIO_TTS_REF_AUDIO.exists():
            raise RuntimeError(f"Fish Audio 参考音频不存在: {FISH_AUDIO_TTS_REF_AUDIO}")
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(
                FISH_AUDIO_TTS_REF_AUDIO, f"{self.remote_root}/ref_audio.wav"
            ),
            timeout=600,
            label="SCP(fish ref audio)",
        )
        if FISH_AUDIO_TTS_REF_META.exists():
            self._gcloud.run_with_retry(
                self._gcloud.scp_to_remote(
                    FISH_AUDIO_TTS_REF_META, f"{self.remote_root}/ref_meta.json"
                ),
                timeout=600,
                label="SCP(fish ref meta)",
            )

    def _upload_worker(self) -> None:
        scripts_dir = PROJECT_ROOT / "hosting_ai" / "fish-audio" / "scripts"
        local_worker = scripts_dir / "fish_audio_mlx_worker.py"
        if not local_worker.exists():
            raise RuntimeError(f"Fish Audio MLX worker 脚本不存在: {local_worker}")
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(local_worker, FISH_AUDIO_TTS_REMOTE_WORKER),
            timeout=600,
            label="SCP(fish mlx worker)",
        )

    def _download_prefixes_for_pending(self, pending: list[dict]) -> set[str]:
        prefixes: set[str] = set()
        for seg in pending:
            rel = seg["wav"].replace("\\", "/")
            parts = rel.split("/")
            if len(parts) >= 3:
                prefixes.add(f"{parts[0]}/{parts[1]}")
        return prefixes

    def _download_wavs_bulk(self, pending: list[dict]) -> int:
        groups: dict[str, list[dict]] = {}
        for seg in pending:
            rel = seg["wav"].replace("\\", "/")
            parts = rel.split("/")
            key = (
                "/".join(parts[:4])
                if len(parts) >= 5
                else str(Path(rel).parent).replace("\\", "/")
            )
            groups.setdefault(key, []).append(seg)

        total = len(pending)
        for idx, (article_key, segs) in enumerate(sorted(groups.items()), 1):
            remote_dir = f"{self.remote_root}/{article_key}"
            local_parent = self.issue_dir / Path(article_key).parent
            local_parent.mkdir(parents=True, exist_ok=True)
            before = self._count_local_pending(pending)
            _fish_log(
                f"下载 [{idx}/{len(groups)}] {Path(article_key).name}/ "
                f"({len(segs)} files, {before}/{total})"
            )
            self._gcloud.run_with_retry(
                self._gcloud.scp_recursive_from_remote(remote_dir, local_parent),
                timeout=900,
                label=f"SCP(fish {Path(article_key).name})",
            )

        downloaded = self._count_local_pending(pending)
        _fish_log(f"下载校验: {downloaded}/{total} WAV")
        return downloaded

    def synthesize_segments(
        self, jobs: list[FishAudioSegmentJob], *, force: bool = False
    ) -> None:
        if not jobs:
            return

        pending: list[dict] = []
        for job in jobs:
            wav_path = job.work_dir / job.seg["wav_file"]
            if (
                not force
                and wav_path.exists()
                and wav_path.stat().st_size >= WAV_MIN_SIZE
            ):
                continue
            seg_dict = {
                "text": job.seg["text"],
                "wav": _wav_rel_path(self.issue_dir, job.work_dir, job.seg["wav_file"]),
                "index": job.seg["index"],
            }
            if force:
                seg_dict["force"] = True
            pending.append(seg_dict)

        if not pending:
            _fish_log("全部片段 WAV 已存在，跳过")
            return

        cleanup_stale_local_ssh(
            self.issue_date, lock_path=self.issue_dir / ".gcloud_ssh.lock"
        )
        self._set_batch_context(pending)
        self._poll_expected_total = len(pending)
        self._last_reported_done = -1

        _fish_log(
            f"远程合成: {len(pending)} 片段 "
            f"(EP {self._batch_episode or '?'}, MLX 8bit+OPT1/2, "
            f"host={FISH_AUDIO_TTS_REMOTE_HOST})"
        )

        self._ensure_remote_setup()
        _fish_log("上传参考音频与 worker...")
        self._upload_ref_assets()
        self._upload_worker()

        manifest: dict = {
            "ref_audio": "ref_audio.wav",
            "ref_text": self._ref_text,
            "temperature": 0.7,
            "top_p": 0.8,
            "segments": pending,
        }

        manifest_local = self.issue_dir / ".fish_audio_job_manifest.json"
        manifest_local.parent.mkdir(parents=True, exist_ok=True)
        manifest_local.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        remote_manifest = f"{self.remote_root}/job_manifest.json"
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(manifest_local, remote_manifest),
            timeout=600,
            label="SCP(fish manifest)",
        )

        progress_arg = f"--progress-file {self._progress_path}"
        inner_cmd = (
            f"{FISH_AUDIO_TTS_REMOTE_VENV}/bin/python -u {FISH_AUDIO_TTS_REMOTE_WORKER} "
            f"--job {self.remote_root}/job_manifest.json "
            f"--workroot {self.remote_root} {progress_arg}"
        )

        cleanup = (
            f"if [ -f {self._pid_path} ]; then "
            f"  oldpid=$(cat {self._pid_path} 2>/dev/null); "
            f"  kill $oldpid 2>/dev/null || true; "
            f"fi; "
            f"rm -f {self._progress_path}; "
            f": > {self._log_path}"
        )
        self._gcloud.ssh_short(cleanup, label="SSH(fish cleanup)")

        launch_script_path = f"{self.remote_root}/launch_worker.sh"
        script_content = f"#!/bin/bash\n{inner_cmd}\n"
        b64 = base64.b64encode(script_content.encode("utf-8")).decode("ascii")
        write_script = (
            f"echo {b64} | base64 -d > {launch_script_path} "
            f"&& chmod +x {launch_script_path}"
        )
        self._gcloud.ssh_short(write_script, label="SSH(write launch script)")

        launch = (
            f"nohup bash {launch_script_path} "
            f"> {self._log_path} 2>&1 & echo $! > {self._pid_path}"
        )
        pid_out = self._gcloud.ssh_short(launch, label="SSH(fish launch)")
        _fish_log(f"远程 worker 已启动 (pid={pid_out or '?'})")

        self._poll_until_done()

        remote_ready = self._remote_wav_ready_count(pending)
        if remote_ready < len(pending):
            raise RuntimeError(
                f"远程合成后 WAV 不足: {remote_ready}/{len(pending)}"
            )

        _fish_log(f"开始批量下载: {len(pending)} 个片段")
        self._download_wavs_bulk(pending)

        missing = [
            seg["wav"]
            for seg in pending
            if not (self.issue_dir / seg["wav"]).exists()
            or (self.issue_dir / seg["wav"]).stat().st_size < WAV_MIN_SIZE
        ]
        if missing:
            _fish_log(f"批量下载后仍缺 {len(missing)} 个，逐个补拉")
            for rel in missing:
                remote_wav = f"{self.remote_root}/{rel}"
                local_wav = self.issue_dir / rel
                local_wav.parent.mkdir(parents=True, exist_ok=True)
                self._gcloud.run_with_retry(
                    self._gcloud.scp_from_remote(remote_wav, local_wav),
                    timeout=120,
                    label="SCP(individual)",
                )

        downloaded = self._count_local_pending(pending)
        if downloaded < len(pending):
            raise RuntimeError(f"下载不完整: {downloaded}/{len(pending)}")
        _fish_log(f"下载完成: {downloaded}/{len(pending)} 片段")

    def synthesize_from_work_dir(
        self, work_dir: Path, segments: list[dict], *, force: bool = False
    ) -> None:
        jobs = [FishAudioSegmentJob(work_dir=work_dir, seg=s) for s in segments]
        self.synthesize_segments(jobs, force=force)

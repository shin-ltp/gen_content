"""VoxCPM2 remote batch synthesis (llm-spot GPU).

Reuses _GcloudRemote SSH/SCP infrastructure from qwen_tts_batch.
Differences from Qwen engine:
  - VoxCPM2 processes segments sequentially (no true batch)
  - float16 + torch.compile for T4 optimization
  - Prompt Cache avoids re-encoding reference audio per segment
  - Different venv / worker script on remote
"""
from __future__ import annotations

import base64
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import (
    GCP_PROJECT_ID,
    PROJECT_ROOT,
    VOXCPM_TTS_CFG,
    VOXCPM_TTS_MODEL,
    VOXCPM_TTS_REF_AUDIO,
    VOXCPM_TTS_REF_META,
    VOXCPM_TTS_REMOTE_HOST,
    VOXCPM_TTS_REMOTE_PROJECT,
    VOXCPM_TTS_REMOTE_VENV,
    VOXCPM_TTS_REMOTE_WORKROOT,
    VOXCPM_TTS_REMOTE_WORKER,
    VOXCPM_TTS_REMOTE_ZONE,
    VOXCPM_TTS_STEPS,
    get_issue_dir,
)
# Reuse SSH infrastructure from Qwen engine (same GPU host, same patterns)
from qwen_tts_batch import (
    _GcloudRemote,
    _log,
    _ssh_option_flags,
    cleanup_stale_local_ssh,
)

WAV_MIN_SIZE = 1000

_LOG_BYTES_MARKER = "__VOXCPM_LOG_BYTES__:"
_STATUS_MARKER = "__VOXCPM_STATUS__:"
_PROGRESS_MARKER = "__VOXCPM_PROGRESS__:"


def _voxcpm_log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"      [{ts}] [VoxCPM] {msg}", flush=True)


@dataclass
class VoxCPMSegmentJob:
    """Single segment to synthesize."""
    work_dir: Path
    seg: dict


def _load_ref_text() -> str:
    meta_path = VOXCPM_TTS_REF_META
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ref_text = str(meta.get("text", meta.get("ref_text", ""))).strip()
        if ref_text:
            return ref_text
    raise RuntimeError(
        f"VoxCPM reference text not found. Set VOXCPM_TTS_REF_META: {meta_path}"
    )


def _remote_job_root(issue_date: str) -> str:
    return f"{VOXCPM_TTS_REMOTE_WORKROOT.rstrip('/')}/{issue_date}"


def _wav_rel_path(issue_dir: Path, work_dir: Path, wav_file: str) -> str:
    rel = work_dir.relative_to(issue_dir)
    return str(rel / wav_file).replace("\\", "/")


class VoxCPMBatchEngine:
    """Remote VoxCPM2 batch synthesis engine (float16 + torch.compile + Prompt Cache)."""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        self.remote_root = _remote_job_root(issue_date)
        self._ref_text = _load_ref_text()
        self._project = VOXCPM_TTS_REMOTE_PROJECT or GCP_PROJECT_ID or "fuzoku-sns"
        self._gcloud = _GcloudRemote(
            self._project,
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
            _voxcpm_log(f"Episode context: episodes/{self._batch_episode}/")

    def _ensure_remote_setup(self) -> None:
        parts = [f"{self.remote_root}/episodes"]
        if self._batch_episode:
            parts.append(f"{self.remote_root}/episodes/{self._batch_episode}")
        worker_parent = VOXCPM_TTS_REMOTE_WORKER.rsplit("/", 1)[0]
        if worker_parent and worker_parent not in (".", "~"):
            parts.append(worker_parent)
        cmd = "mkdir -p " + " ".join(parts)
        self._gcloud.ssh_short(cmd, label="SSH(voxcpm setup)")

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
                out = self._gcloud.ssh_short(cmd, label="SSH(count voxcpm wavs)")
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
        total_gen = prog.get("total_gen_time_sec", 0)
        total_audio = prog.get("total_audio_sec", 0)
        avg_rtf = prog.get("avg_rtf", 0)
        if short and short not in ("starting", "done"):
            detail = f" — {short}"
        elif current == "done":
            rtf_info = f" | avg RTF={avg_rtf:.2f}" if avg_rtf else ""
            detail = f" — 完了{rtf_info}"
        else:
            detail = ""
        _voxcpm_log(f"远程合成进度: {done}/{total} ({pct:.1f}%){detail}")
        return True

    def _remote_worker_status(self) -> str:
        cmd = (
            f"if [ -f {self._pid_path} ] && kill -0 $(cat {self._pid_path}) 2>/dev/null; then "
            f"echo RUNNING; "
            f"elif grep -q '^Done\\.' {self._log_path} 2>/dev/null; then "
            f"echo SUCCESS; "
            f"else echo STOPPED; fi"
        )
        return self._gcloud.ssh_short(cmd, label="SSH(voxcpm status)").strip()

    def _poll_once(self, log_offset: int) -> tuple[int, str | None]:
        # NOTE: avoid literal double-quote (") in remote command — on Windows,
        # subprocess.Popen converts the arg list to a single command-line string
        # and gcloud.cmd mangles embedded " chars when forwarding through SSH,
        # causing remote bash: unexpected EOF while looking for matching `"'
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
        out = self._gcloud.ssh_short(fetch, label="SSH(voxcpm poll)")
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
        _voxcpm_log(f"轮询远程 worker (每{poll_interval}s, timeout={timeout}s)")
        deadline = time.time() + timeout
        log_offset = 0
        last_progress = time.time()
        consecutive_failures = 0

        while time.time() < deadline:
            try:
                log_offset, status = self._poll_once(log_offset)
                consecutive_failures = 0
                last_progress = time.time()
            except RuntimeError as e:
                consecutive_failures += 1
                _voxcpm_log(f"轮询失败 ({consecutive_failures}): {e}")
                if consecutive_failures >= 3:
                    status = self._remote_worker_status()
                    if status == "RUNNING":
                        consecutive_failures = 0
                    elif status == "SUCCESS":
                        return
                time.sleep(10)
                continue

            if status == "SUCCESS":
                # Final progress update
                try:
                    raw = self._gcloud.ssh_short(
                        f"cat {self._progress_path} 2>/dev/null | tr -d '\\n' || true",
                        label="SSH(final progress)",
                    )
                    prog = json.loads(raw) if raw.strip() else {}
                    self._emit_progress(prog)
                except (RuntimeError, json.JSONDecodeError):
                    pass
                _voxcpm_log("远程 worker 正常结束")
                return
            if status == "STOPPED":
                tail_err = self._gcloud.ssh_short(
                    f"tail -n 40 {self._log_path} 2>/dev/null || true",
                    label="SSH(voxcpm tail)",
                )
                raise RuntimeError(
                    "远程 VoxCPM worker 异常结束:\n"
                    + (tail_err[-1500:] if tail_err else "(无日志)")
                )

            time.sleep(poll_interval)

        raise RuntimeError(f"远程 worker 超时 ({timeout}s)")

    def _upload_ref_assets(self) -> None:
        if not VOXCPM_TTS_REF_AUDIO.exists():
            raise RuntimeError(f"VoxCPM 参考音频不存在: {VOXCPM_TTS_REF_AUDIO}")
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(VOXCPM_TTS_REF_AUDIO, f"{self.remote_root}/ref_audio.wav"),
            timeout=600, label="SCP(voxcpm ref audio)",
        )
        if VOXCPM_TTS_REF_META.exists():
            self._gcloud.run_with_retry(
                self._gcloud.scp_to_remote(VOXCPM_TTS_REF_META, f"{self.remote_root}/ref_meta.json"),
                timeout=600, label="SCP(voxcpm ref meta)",
            )

    def _upload_worker(self) -> None:
        local_worker = PROJECT_ROOT / "hosting_ai" / "VoxCPM" / "scripts" / "voxcpm_synth_worker.py"
        if not local_worker.exists():
            raise RuntimeError(f"VoxCPM worker 脚本不存在: {local_worker}")
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(local_worker, VOXCPM_TTS_REMOTE_WORKER),
            timeout=600, label="SCP(voxcpm worker)",
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
            key = "/".join(parts[:4]) if len(parts) >= 5 else str(Path(rel).parent).replace("\\", "/")
            groups.setdefault(key, []).append(seg)

        total = len(pending)
        for idx, (article_key, segs) in enumerate(sorted(groups.items()), 1):
            remote_dir = f"{self.remote_root}/{article_key}"
            local_parent = self.issue_dir / Path(article_key).parent
            local_parent.mkdir(parents=True, exist_ok=True)
            before = self._count_local_pending(pending)
            _voxcpm_log(f"下载 [{idx}/{len(groups)}] {Path(article_key).name}/ ({len(segs)} files, {before}/{total})")
            self._gcloud.run_with_retry(
                self._gcloud.scp_recursive_from_remote(remote_dir, local_parent),
                timeout=900, label=f"SCP(voxcpm {Path(article_key).name})",
            )

        downloaded = self._count_local_pending(pending)
        _voxcpm_log(f"下载校验: {downloaded}/{total} WAV")
        return downloaded

    def synthesize_segments(self, jobs: list[VoxCPMSegmentJob], *, force: bool = False) -> None:
        """Batch synthesize segments, download to local audio_work/.

        Args:
            force: If True, force regeneration even if remote WAV exists
                   (used for validation-failed retries). If False (default),
                   skip segments whose local WAV already exists (resume).
        """
        if not jobs:
            return

        pending: list[dict] = []
        for job in jobs:
            wav_path = job.work_dir / job.seg["wav_file"]
            if not force and wav_path.exists() and wav_path.stat().st_size >= WAV_MIN_SIZE:
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
            _voxcpm_log("全部片段 WAV 已存在，跳过")
            return

        cleanup_stale_local_ssh(self.issue_date, lock_path=self.issue_dir / ".gcloud_ssh.lock")
        self._set_batch_context(pending)
        self._poll_expected_total = len(pending)
        self._last_reported_done = -1

        _voxcpm_log(
            f"远程合成: {len(pending)} 片段 "
            f"(EP {self._batch_episode or '?'}, "
            f"cfg={VOXCPM_TTS_CFG}, steps={VOXCPM_TTS_STEPS}, "
            f"model={VOXCPM_TTS_MODEL})"
        )

        self._ensure_remote_setup()
        _voxcpm_log("上传参考音频与 worker...")
        self._upload_ref_assets()
        self._upload_worker()

        # Build manifest
        manifest = {
            "model": VOXCPM_TTS_MODEL,
            "ref_audio": "ref_audio.wav",
            "ref_text": self._ref_text,
            "cfg_value": VOXCPM_TTS_CFG,
            "inference_timesteps": VOXCPM_TTS_STEPS,
            "segments": pending,
        }
        manifest_local = self.issue_dir / ".voxcpm_job_manifest.json"
        manifest_local.parent.mkdir(parents=True, exist_ok=True)
        manifest_local.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        remote_manifest = f"{self.remote_root}/job_manifest.json"
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(manifest_local, remote_manifest),
            timeout=600, label="SCP(voxcpm manifest)",
        )

        # Launch remote worker via nohup
        # Write launch script to remote to avoid Windows→gcloud→SSH quoting issues.
        # The inner command is long and contains paths with / and $ which get mangled
        # when passed inline through Windows subprocess → gcloud.cmd → SSH → remote bash.
        progress_arg = f"--progress-file {self._progress_path}"
        inner_cmd = (
            f"source {VOXCPM_TTS_REMOTE_VENV}/bin/activate && "
            f"python -u {VOXCPM_TTS_REMOTE_WORKER} "
            f"--job {self.remote_root}/job_manifest.json "
            f"--workroot {self.remote_root} {progress_arg}"
        )

        # Cleanup stale worker
        cleanup = (
            f"if [ -f {self._pid_path} ]; then "
            f"  oldpid=$(cat {self._pid_path} 2>/dev/null); "
            f"  kill $oldpid 2>/dev/null || true; "
            f"fi; "
            f"rm -f {self._progress_path}; "
            f": > {self._log_path}"
        )
        self._gcloud.ssh_short(cleanup, label="SSH(voxcpm cleanup)")

        # Write launch script to remote, then execute it via nohup
        # This avoids all quoting issues with long command strings through Windows SSH
        launch_script_path = f"{self.remote_root}/launch_worker.sh"
        script_content = (
            f"#!/bin/bash\n"
            f"{inner_cmd}\n"
        )
        # Upload script content via base64 to avoid ANY quoting issues
        import base64
        b64 = base64.b64encode(script_content.encode("utf-8")).decode("ascii")
        write_script = f"echo {b64} | base64 -d > {launch_script_path} && chmod +x {launch_script_path}"
        self._gcloud.ssh_short(write_script, label="SSH(write launch script)")

        launch = (
            f"nohup bash {launch_script_path} "
            f"> {self._log_path} 2>&1 & echo $! > {self._pid_path}"
        )
        pid_out = self._gcloud.ssh_short(launch, label="SSH(voxcpm launch)")
        _voxcpm_log(f"远程 worker 已启动 (pid={pid_out or '?'})")

        self._poll_until_done()

        # Verify + download
        remote_ready = self._remote_wav_ready_count(pending)
        if remote_ready < len(pending):
            raise RuntimeError(
                f"远程合成后 WAV 不足: {remote_ready}/{len(pending)}"
            )

        _voxcpm_log(f"开始批量下载: {len(pending)} 个片段")
        downloaded = self._download_wavs_bulk(pending)

        # Individual retry for missing
        missing = [
            seg["wav"] for seg in pending
            if not (self.issue_dir / seg["wav"]).exists()
            or (self.issue_dir / seg["wav"]).stat().st_size < WAV_MIN_SIZE
        ]
        if missing:
            _voxcpm_log(f"批量下载后仍缺 {len(missing)} 个，逐个补拉")
            for rel in missing:
                remote_wav = f"{self.remote_root}/{rel}"
                local_wav = self.issue_dir / rel
                local_wav.parent.mkdir(parents=True, exist_ok=True)
                self._gcloud.run_with_retry(
                    self._gcloud.scp_from_remote(remote_wav, local_wav),
                    timeout=120, label="SCP(individual)",
                )

        downloaded = self._count_local_pending(pending)
        if downloaded < len(pending):
            raise RuntimeError(f"下载不完整: {downloaded}/{len(pending)}")
        _voxcpm_log(f"下载完成: {downloaded}/{len(pending)} 片段")

    def synthesize_from_work_dir(self, work_dir: Path, segments: list[dict], *, force: bool = False) -> None:
        """Retry/resume within a single article."""
        jobs = [VoxCPMSegmentJob(work_dir=work_dir, seg=s) for s in segments]
        self.synthesize_segments(jobs, force=force)

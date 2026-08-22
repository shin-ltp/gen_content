"""
Qwen3-TTS 远程批量合成（llm-spot GPU）。

本地 orchestrator：上传 job manifest + 参考音，SSH 触发 worker，
下载 WAV 到与 Fish 版相同的 audio_work/ 路径（断点续跑兼容）。

SSH 改进（尤其 Windows）:
- ConnectTimeout / ServerAlive / ControlPath=none / gcloud --quiet
- 短命令带重试；超时后 **强制终止进程树**（Windows taskkill /T）
- 长 worker 默认 nohup 后台 + 单次 SSH 轮询日志与状态（减少连接数）
- 远程 worker 仍在跑时可附着轮询，避免误杀 GPU 任务
- 完成后递归 SCP 批量下载，替代数百次单文件 SCP
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import (
    GCP_PROJECT_ID,
    PROJECT_ROOT,
    QWEN_TTS_BATCH_SIZE,
    QWEN_TTS_DTYPE,
    QWEN_TTS_LANGUAGE,
    QWEN_TTS_MODEL,
    QWEN_TTS_REF_AUDIO,
    QWEN_TTS_REF_META,
    QWEN_TTS_REMOTE_HOST,
    QWEN_TTS_REMOTE_PROJECT,
    QWEN_TTS_REMOTE_VENV,
    QWEN_TTS_REMOTE_WORKROOT,
    QWEN_TTS_REMOTE_WORKER,
    QWEN_TTS_REMOTE_ZONE,
    QWEN_TTS_SSH_CONNECT_TIMEOUT,
    QWEN_TTS_SSH_DETACHED_WORKER,
    QWEN_TTS_SSH_POLL_INTERVAL_SEC,
    QWEN_TTS_SSH_RETRY_COUNT,
    QWEN_TTS_SSH_RETRY_WAIT_SEC,
    QWEN_TTS_SSH_SHORT_TIMEOUT,
    QWEN_TTS_SSH_USE_IAP,
    QWEN_TTS_SSH_WORKER_TIMEOUT,
    get_issue_dir,
)

WAV_MIN_SIZE = 1000
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPTS_DIR.parent
_DEFAULT_GCE_KEYFILE = _SKILL_ROOT / "google_gce_default_app.json"

_LOG_BYTES_MARKER = "__QWEN_LOG_BYTES__:"
_STATUS_MARKER = "__QWEN_STATUS__:"
_PROGRESS_MARKER = "__QWEN_PROGRESS__:"
_LOG_PROGRESS_RE = re.compile(
    r"\[\s*(\d+)\/(\d+)\]\s+(\S+\.wav)?",
    re.IGNORECASE,
)


def _log(msg: str) -> None:
    """进度日志（orchestrate W2 → p_audio.log / 终端，立即 flush）。"""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"      [{ts}] [Qwen] {msg}", flush=True)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cleanup_stale_local_ssh(
    issue_date: str,
    lock_path: Path | None = None,
) -> None:
    """清理本机僵死的 gcloud/ssh，并解除 stale 的 SSH 锁（死机/强杀后常残留）。"""
    if lock_path is not None and lock_path.exists():
        try:
            age = time.time() - lock_path.stat().st_mtime
            holder = lock_path.read_text(encoding="utf-8").strip()
            if (holder.isdigit() and not _pid_alive(int(holder))) or age > 120:
                lock_path.unlink(missing_ok=True)
                _log(f"已清除 stale SSH 锁 ({lock_path.name})")
        except OSError:
            pass
    if sys.platform != "win32":
        return
    marker = f"jobs/{issue_date}"
    ps = (
        f"Get-CimInstance Win32_Process | Where-Object {{ "
        f"$_.CommandLine -and $_.CommandLine -like '*{marker}*' -and "
        f"($_.Name -eq 'ssh.exe' -or $_.CommandLine -like '*gcloud*compute*ssh*' "
        f"-or $_.CommandLine -like '*gcloud*compute*scp*') "
        f"}} | ForEach-Object {{ "
        f"Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}"
    )
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            timeout=45,
        )
    except Exception:
        pass


class _GcloudSSHLock:
    """跨 Worker 进程的 gcloud SSH/SCP 互斥锁（Windows 并发 OpenSSH 会挂死）。"""

    def __init__(self, lock_path: Path, *, timeout: float = 600, stale_sec: float = 180):
        self.lock_path = lock_path
        self.timeout = timeout
        self.stale_sec = stale_sec
        self._fd: int | None = None
        self._wait_logged = False

    def __enter__(self) -> "_GcloudSSHLock":
        deadline = time.time() + self.timeout
        while time.time() < deadline:
            if self.lock_path.exists():
                try:
                    age = time.time() - self.lock_path.stat().st_mtime
                    if age > self.stale_sec:
                        self.lock_path.unlink(missing_ok=True)
                    else:
                        holder = self.lock_path.read_text(encoding="utf-8").strip()
                        if holder.isdigit() and not _pid_alive(int(holder)):
                            self.lock_path.unlink(missing_ok=True)
                        elif not self._wait_logged:
                            self._wait_logged = True
                            _log(
                                f"等待 SSH 锁（持有者 pid={holder or '?'}，"
                                f"已等待 {int(age)}s）…"
                            )
                except OSError:
                    pass
            try:
                self._fd = os.open(
                    self.lock_path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.write(self._fd, str(os.getpid()).encode("ascii"))
                return self
            except FileExistsError:
                time.sleep(0.5)
        raise RuntimeError(
            f"无法获取 gcloud SSH 锁（{self.lock_path}，等待 {self.timeout}s）。"
            "可能有僵死 SSH/锁；请重启 orchestrate 或删除 .gcloud_ssh.lock。"
        )

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self.lock_path.unlink(missing_ok=True)
        except OSError:
            pass


def _kill_process_tree(pid: int) -> None:
    """终止 gcloud/ssh 及其子进程。Windows 上 subprocess timeout 不会自动杀子进程。"""
    if pid <= 0:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, OSError, PermissionError):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


@dataclass
class QwenSegmentJob:
    """单个待合成片段。"""

    work_dir: Path
    seg: dict


def _load_ref_text() -> str:
    meta_path = QWEN_TTS_REF_META
    if meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ref_text = str(meta.get("ref_text", "")).strip()
        if ref_text:
            return ref_text
    raise RuntimeError(
        f"Qwen 参考文本未配置。请设置 QWEN_TTS_REF_META 或确保 {meta_path} 含 ref_text。"
    )


def _gcloud_env() -> dict[str, str]:
    env = os.environ.copy()
    if _DEFAULT_GCE_KEYFILE.exists() and not env.get("GOOGLE_APPLICATION_CREDENTIALS"):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = str(_DEFAULT_GCE_KEYFILE)
    return env


def _shell_quote_bash(s: str) -> str:
    return "'" + s.replace("'", "'\"'\"'") + "'"


def _ssh_option_flags(prefix: str) -> list[str]:
    """gcloud --ssh-flag / --scp-flag 用 OpenSSH 选项。"""
    t = QWEN_TTS_SSH_CONNECT_TIMEOUT
    opts = [
        f"-o ConnectTimeout={t}",
        "-o ConnectionAttempts=3",
        "-o TCPKeepAlive=yes",
        "-o ServerAliveInterval=15",
        "-o ServerAliveCountMax=4",
        "-o BatchMode=yes",
        "-o StrictHostKeyChecking=accept-new",
        "-o ControlPath=none",
        "-o ControlMaster=no",
    ]
    return [f"{prefix}={opt}" for opt in opts]


class _GcloudRemote:
    """gcloud compute ssh/scp 封装（超时・重试・进程树强杀・全局 SSH 锁）。"""

    def __init__(self, project: str, *, lock_path: Path | None = None):
        self.project = project
        self.lock_path = lock_path

    def _candidates(self, cmd: list[str]) -> list[list[str]]:
        if not cmd:
            return [cmd]
        if cmd[0] == "gcloud":
            return [cmd, ["gcloud.cmd", *cmd[1:]]]
        return [cmd]

    def _ssh_base(self) -> list[str]:
        args = [
            "gcloud",
            "--quiet",
            "compute",
            "ssh",
            QWEN_TTS_REMOTE_HOST,
            "--zone",
            QWEN_TTS_REMOTE_ZONE,
            "--project",
            self.project,
        ]
        if QWEN_TTS_SSH_USE_IAP:
            args.append("--tunnel-through-iap")
        return args

    def _scp_base(self) -> list[str]:
        args = [
            "gcloud",
            "--quiet",
            "compute",
            "scp",
            "--zone",
            QWEN_TTS_REMOTE_ZONE,
            "--project",
            self.project,
        ]
        if QWEN_TTS_SSH_USE_IAP:
            args.append("--tunnel-through-iap")
        return args

    def run(
        self,
        cmd: list[str],
        *,
        timeout: int,
        capture: bool = True,
    ) -> subprocess.CompletedProcess:
        lock_ctx = (
            _GcloudSSHLock(self.lock_path)
            if self.lock_path is not None
            else nullcontext()
        )
        with lock_ctx:
            return self._run_unlocked(cmd, timeout=timeout, capture=capture)

    def _run_unlocked(
        self,
        cmd: list[str],
        *,
        timeout: int,
        capture: bool,
    ) -> subprocess.CompletedProcess:
        env = _gcloud_env()
        last_err = ""
        for candidate in self._candidates(cmd):
            try:
                popen_kwargs: dict = {"env": env}
                if capture:
                    popen_kwargs["stdout"] = subprocess.PIPE
                    popen_kwargs["stderr"] = subprocess.PIPE
                    popen_kwargs["text"] = True
                    popen_kwargs["encoding"] = "utf-8"
                    popen_kwargs["errors"] = "replace"
                else:
                    popen_kwargs["stdout"] = None
                    popen_kwargs["stderr"] = None

                proc = subprocess.Popen(candidate, **popen_kwargs)
                try:
                    stdout, stderr = proc.communicate(timeout=timeout)
                except subprocess.TimeoutExpired:
                    _log(
                        f"gcloud 超时 ({timeout}s)，强制终止进程树 pid={proc.pid}…"
                    )
                    _kill_process_tree(proc.pid)
                    time.sleep(2)
                    try:
                        proc.communicate(timeout=15)
                    except subprocess.TimeoutExpired:
                        _kill_process_tree(proc.pid)
                        time.sleep(1)
                    raise RuntimeError(
                        f"gcloud 命令超时 ({timeout}s): {' '.join(candidate)}"
                    )

                if proc.returncode == 0:
                    return subprocess.CompletedProcess(
                        candidate, 0, stdout, stderr
                    )
                if capture:
                    last_err = (stderr or stdout or "").strip()[:800]
                else:
                    last_err = f"exit code {proc.returncode}"
            except FileNotFoundError:
                continue
        raise RuntimeError(f"gcloud 命令失败: {' '.join(cmd)}\n{last_err}")

    def run_with_retry(
        self,
        cmd: list[str],
        *,
        timeout: int,
        capture: bool = True,
        label: str = "gcloud",
    ) -> subprocess.CompletedProcess:
        last_err: RuntimeError | None = None
        for attempt in range(1, QWEN_TTS_SSH_RETRY_COUNT + 1):
            try:
                return self.run(cmd, timeout=timeout, capture=capture)
            except RuntimeError as e:
                last_err = e
                if attempt >= QWEN_TTS_SSH_RETRY_COUNT:
                    break
                _log(
                    f"{label} 失败 ({attempt}/{QWEN_TTS_SSH_RETRY_COUNT})，"
                    f"{QWEN_TTS_SSH_RETRY_WAIT_SEC}s 后重试…"
                )
                time.sleep(QWEN_TTS_SSH_RETRY_WAIT_SEC)
                from tts_backends import recover_gce_vm_if_stopped

                if recover_gce_vm_if_stopped(reason=f"{label} 重试前 VM 确认"):
                    _log("VM 起動後 30 秒待機…")
                    time.sleep(30)
        assert last_err is not None
        raise last_err

    def ssh_cmd(self, remote_cmd: str) -> list[str]:
        cmd = self._ssh_base()
        cmd.extend(_ssh_option_flags("--ssh-flag"))
        cmd.extend(["--command", remote_cmd])
        return cmd

    def scp_to_remote(self, local: Path, remote: str) -> list[str]:
        cmd = self._scp_base()
        cmd.extend(_ssh_option_flags("--scp-flag"))
        cmd.extend([str(local), f"{QWEN_TTS_REMOTE_HOST}:{remote}"])
        return cmd

    def scp_from_remote(self, remote: str, local: Path) -> list[str]:
        cmd = self._scp_base()
        cmd.extend(_ssh_option_flags("--scp-flag"))
        cmd.extend([f"{QWEN_TTS_REMOTE_HOST}:{remote}", str(local)])
        return cmd

    def scp_recursive_from_remote(self, remote_dir: str, local_dir: Path) -> list[str]:
        cmd = self._scp_base()
        cmd.extend(["--recurse"])
        cmd.extend(_ssh_option_flags("--scp-flag"))
        cmd.extend([f"{QWEN_TTS_REMOTE_HOST}:{remote_dir}", str(local_dir)])
        return cmd

    def ssh_short(self, remote_cmd: str, *, label: str = "SSH") -> str:
        result = self.run_with_retry(
            self.ssh_cmd(remote_cmd),
            timeout=QWEN_TTS_SSH_SHORT_TIMEOUT,
            capture=True,
            label=label,
        )
        return (result.stdout or "").strip()

    def ssh_stream(self, remote_cmd: str, *, timeout: int) -> None:
        self.run_with_retry(
            self.ssh_cmd(remote_cmd),
            timeout=timeout,
            capture=False,
            label="SSH(stream)",
        )


def _remote_job_root(issue_date: str) -> str:
    return f"{QWEN_TTS_REMOTE_WORKROOT.rstrip('/')}/{issue_date}"


def _wav_rel_path(issue_dir: Path, work_dir: Path, wav_file: str) -> str:
    rel = work_dir.relative_to(issue_dir)
    return str(rel / wav_file).replace("\\", "/")


class QwenRemoteBatchEngine:
    """远程 Qwen3-TTS 批量合成引擎。"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.issue_dir = get_issue_dir(issue_date)
        self.remote_root = _remote_job_root(issue_date)
        self._ref_text = _load_ref_text()
        self._project = QWEN_TTS_REMOTE_PROJECT or GCP_PROJECT_ID or "fuzoku-sns"
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
        if len(eps) == 1:
            return next(iter(eps))
        return None

    def _set_batch_context(self, pending: list[dict]) -> None:
        """每章独立 worker.log / worker.pid / progress.json，避免 EP05 Done 误判 EP06。"""
        self._current_pending = pending
        self._batch_episode = self._infer_episode_id(pending)
        if self._batch_episode:
            ep_base = f"{self.remote_root}/episodes/{self._batch_episode}"
            self._log_path = f"{ep_base}/worker.log"
            self._pid_path = f"{ep_base}/worker.pid"
            self._progress_path = f"{ep_base}/worker.progress.json"
            _log(f"本章远程状态目录: episodes/{self._batch_episode}/")
        else:
            self._log_path = f"{self.remote_root}/worker.log"
            self._pid_path = f"{self.remote_root}/worker.pid"
            self._progress_path = f"{self.remote_root}/worker.progress.json"

    def _ensure_remote_setup(self) -> None:
        """一次 SSH 创建全部远程目录（避免 Windows 上多次并发 mkdir 挂死）。"""
        parts = [f"{self.remote_root}/episodes"]
        if self._batch_episode:
            parts.append(f"{self.remote_root}/episodes/{self._batch_episode}")
        worker_parent = QWEN_TTS_REMOTE_WORKER.rsplit("/", 1)[0]
        if worker_parent and worker_parent not in (".", "~"):
            parts.append(worker_parent)
        cmd = "mkdir -p " + " ".join(parts)
        self._gcloud.ssh_short(cmd, label="SSH(setup dirs)")

    def _remote_wav_ready_count(self, pending: list[dict]) -> int:
        """SSH 统计远程 pending 对应目录下已合成的 seg_*.wav 数量。"""
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
                out = self._gcloud.ssh_short(cmd, label="SSH(count remote wavs)")
                total += int(out.strip())
            except (RuntimeError, ValueError):
                pass
        return total

    def _local_progress_path(self) -> Path:
        return self.issue_dir / ".qwen_remote_progress.json"

    def _emit_remote_progress(self, prog: dict) -> bool:
        """远程 worker.progress.json → 本地一行进度日志 + 仪表盘用 JSON。"""
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
        batch = prog.get("batch")
        batch_s = f", batch {batch}" if batch else ""
        if short and short not in ("starting", "done"):
            detail = f" — {short}"
        elif current == "done":
            detail = " — 完成"
        else:
            detail = ""
        _log(f"远程合成进度: {done}/{total} ({pct:.1f}%){batch_s}{detail}")

        payload = {
            "done": done,
            "total": total,
            "current": current,
            "batch": batch,
            "updated_at": datetime.now().isoformat(),
        }
        self._local_progress_path().write_text(
            json.dumps(payload, ensure_ascii=False),
            encoding="utf-8",
        )
        return True

    def _scan_log_chunk_for_progress(self, text: str) -> None:
        """旧 worker 无 progress.json 时，从日志行 [n/total] 解析进度。"""
        last: tuple[int, int, str] | None = None
        for m in _LOG_PROGRESS_RE.finditer(text):
            last = (int(m.group(1)), int(m.group(2)), (m.group(3) or "").strip())
        if not last:
            return
        done, total, wav = last
        if self._poll_expected_total <= 0:
            self._poll_expected_total = total
        self._emit_remote_progress({"done": done, "total": total, "current": wav})

    def _parse_progress_json(self, raw: str) -> dict | None:
        raw = raw.strip()
        if not raw or raw == "{}":
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def _scp_to_remote(self, local: Path, remote: str) -> None:
        self._gcloud.run_with_retry(
            self._gcloud.scp_to_remote(local, remote),
            timeout=600,
            label="SCP(upload)",
        )

    def _scp_from_remote(self, remote: str, local: Path) -> None:
        local.parent.mkdir(parents=True, exist_ok=True)
        self._gcloud.run_with_retry(
            self._gcloud.scp_from_remote(remote, local),
            timeout=600,
            label="SCP(download)",
        )

    def _remote_worker_status(self) -> str:
        cmd = (
            f"if [ -f {self._pid_path} ] && kill -0 $(cat {self._pid_path}) 2>/dev/null; then "
            f"echo RUNNING; "
            f"elif grep -q '^Done\\.$' {self._log_path} 2>/dev/null; then "
            f"echo SUCCESS; "
            f"else echo STOPPED; fi"
        )
        return self._gcloud.ssh_short(cmd, label="SSH(worker status)").strip()

    def _poll_remote_worker_once(self, log_offset: int) -> tuple[int, str | None, bool]:
        """单次 SSH：增量日志 + 进度 JSON + worker 状态。"""
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
            f"elif grep -q '^Done\\.$' {self._log_path} 2>/dev/null; then "
            f"echo {_STATUS_MARKER}SUCCESS; "
            f"else echo {_STATUS_MARKER}STOPPED; fi"
        )
        out = self._gcloud.ssh_short(fetch, label="SSH(poll)")
        new_offset = log_offset
        status: str | None = None
        got_new_log = False

        if _STATUS_MARKER in out:
            body, _, status_tail = out.rpartition(_STATUS_MARKER)
            status = status_tail.strip().splitlines()[0] if status_tail.strip() else None
            out = body

        if _LOG_BYTES_MARKER in out:
            body, _, bytes_tail = out.rpartition(_LOG_BYTES_MARKER)
            try:
                new_offset = int(bytes_tail.strip().splitlines()[0])
            except (ValueError, IndexError):
                pass
            out = body

        if _PROGRESS_MARKER in out:
            body, _, prog_tail = out.rpartition(_PROGRESS_MARKER)
            prog_raw = prog_tail.strip().splitlines()[0] if prog_tail.strip() else ""
            prog = self._parse_progress_json(prog_raw)
            if prog:
                self._emit_remote_progress(prog)
            out = body

        if out.strip():
            got_new_log = True
            self._scan_log_chunk_for_progress(out)
            sys.stdout.write(out)
            if not out.endswith("\n"):
                sys.stdout.write("\n")
            sys.stdout.flush()

        return new_offset, status, got_new_log

    def _upload_ref_assets(self) -> None:
        if not QWEN_TTS_REF_AUDIO.exists():
            raise RuntimeError(f"Qwen 参考音频不存在: {QWEN_TTS_REF_AUDIO}")
        self._scp_to_remote(QWEN_TTS_REF_AUDIO, f"{self.remote_root}/ref_audio.wav")
        if QWEN_TTS_REF_META.exists():
            self._scp_to_remote(QWEN_TTS_REF_META, f"{self.remote_root}/ref_meta.json")

    def _upload_worker_if_needed(self) -> None:
        worker_remote = QWEN_TTS_REMOTE_WORKER
        local_worker = PROJECT_ROOT / "hosting_ai" / "qwen-tts" / "scripts" / "batch_synth_worker.py"
        if not local_worker.exists():
            raise RuntimeError(f"Worker 脚本不存在: {local_worker}")
        self._scp_to_remote(local_worker, worker_remote)

    def _launch_remote_worker(self, inner_cmd: str) -> None:
        cleanup = (
            f"if [ -f {self._pid_path} ]; then "
            f"  oldpid=$(cat {self._pid_path} 2>/dev/null); "
            f"  kill $oldpid 2>/dev/null || true; "
            f"fi; "
            f"rm -f {self._progress_path}; "
            f": > {self._log_path}"
        )
        self._gcloud.ssh_short(cleanup, label="SSH(worker cleanup)")

        launch = (
            f"nohup bash -lc {_shell_quote_bash(inner_cmd)} "
            f"> {self._log_path} 2>&1 & echo $! > {self._pid_path}"
        )
        pid_out = self._gcloud.ssh_short(launch, label="SSH(launch worker)")
        _log(f"远程 worker 已后台启动 (pid={pid_out or '?'})")

    def _poll_remote_worker_until_done(self) -> None:
        _log(
            f"轮询远程日志（每 {QWEN_TTS_SSH_POLL_INTERVAL_SEC}s，"
            f"单次 SSH 超时 {QWEN_TTS_SSH_SHORT_TIMEOUT}s）"
        )
        deadline = time.time() + QWEN_TTS_SSH_WORKER_TIMEOUT
        log_offset = 0
        last_progress_at = time.time()
        consecutive_failures = 0

        while time.time() < deadline:
            try:
                log_offset, status, got_new_log = self._poll_remote_worker_once(log_offset)
                consecutive_failures = 0
                if got_new_log:
                    last_progress_at = time.time()
            except RuntimeError as e:
                consecutive_failures += 1
                _log(f"轮询失败 ({consecutive_failures}): {e}")
                if consecutive_failures >= QWEN_TTS_SSH_RETRY_COUNT:
                    status = self._remote_worker_status()
                    if status == "RUNNING":
                        _log("SSH 轮询失败但远程 worker 仍在运行，继续等待…")
                        consecutive_failures = 0
                    elif status == "SUCCESS":
                        ready = self._remote_wav_ready_count(self._current_pending)
                        need = self._poll_expected_total or len(self._current_pending)
                        if need > 0 and ready >= need:
                            _log("远程 worker 已完成（轮询中断后确认）")
                            return
                        _log(
                            f"远程 Done. 但 WAV 仅 {ready}/{need}，继续等待…"
                        )
                        consecutive_failures = 0
                time.sleep(QWEN_TTS_SSH_RETRY_WAIT_SEC)
                continue

            if status == "SUCCESS":
                ready = self._remote_wav_ready_count(self._current_pending)
                need = self._poll_expected_total or len(self._current_pending)
                if need > 0 and ready < need:
                    raise RuntimeError(
                        f"远程 worker 日志显示 Done. 但 WAV 仅 {ready}/{need}。"
                        f"请检查 episodes/{self._batch_episode or '?'} 远程目录。"
                    )
                # 终态再拉一次进度（确保 100% 行写入 p_audio.log）
                try:
                    raw = self._gcloud.ssh_short(
                        f"cat {self._progress_path} 2>/dev/null | tr -d '\\n' || true",
                        label="SSH(final progress)",
                    )
                    prog = self._parse_progress_json(raw)
                    if prog:
                        self._emit_remote_progress(prog)
                    elif self._poll_expected_total > 0:
                        self._emit_remote_progress(
                            {
                                "done": self._poll_expected_total,
                                "total": self._poll_expected_total,
                                "current": "done",
                            }
                        )
                except RuntimeError:
                    pass
                _log("远程 worker 正常结束")
                return
            if status == "STOPPED":
                tail_err = self._gcloud.ssh_short(
                    f"tail -n 40 {self._log_path} 2>/dev/null || true",
                    label="SSH(worker tail)",
                )
                raise RuntimeError(
                    "远程 worker 异常结束（日志中无 Done.）。末尾:\n"
                    + (tail_err[-1500:] if tail_err else "(无日志)")
                )

            if time.time() - last_progress_at > 1800:
                _log("30 分钟无新日志，继续等待 worker…")
                last_progress_at = time.time()

            time.sleep(QWEN_TTS_SSH_POLL_INTERVAL_SEC)

        raise RuntimeError(
            f"远程 worker 超时 ({QWEN_TTS_SSH_WORKER_TIMEOUT}s)。"
            "可增大 QWEN_TTS_SSH_WORKER_TIMEOUT 或检查 llm-spot。"
        )

    def _run_remote_worker_detached(self, inner_cmd: str, pending: list[dict]) -> None:
        """nohup 后台跑 worker，短 SSH 轮询（Windows 长 SSH 会话回避）。"""
        need = len(pending)
        ready = self._remote_wav_ready_count(pending)
        if need > 0 and ready >= need:
            _log(f"远程 WAV 已齐全 ({ready}/{need})，跳过 GPU worker")
            return

        status = self._remote_worker_status()
        if status == "RUNNING":
            _log("远程 worker 仍在运行 → 附着轮询（不重启 GPU 任务）")
        elif status == "SUCCESS":
            _log(
                f"远程日志有 Done. 但 WAV 仅 {ready}/{need} "
                f"（上一章残留或未完成）→ 重新启动 worker"
            )
            self._launch_remote_worker(inner_cmd)
        else:
            self._launch_remote_worker(inner_cmd)

        self._poll_remote_worker_until_done()

    def _run_remote_worker(self, inner_cmd: str, pending: list[dict]) -> None:
        if QWEN_TTS_SSH_DETACHED_WORKER:
            self._run_remote_worker_detached(inner_cmd, pending)
            return
        _log("以下 Batch / [n/total] 行为远程 GPU 实时输出（同期 SSH 模式）")
        self._gcloud.ssh_stream(inner_cmd, timeout=QWEN_TTS_SSH_WORKER_TIMEOUT)

    def _download_prefixes_for_pending(self, pending: list[dict]) -> set[str]:
        prefixes: set[str] = set()
        for seg in pending:
            rel = seg["wav"].replace("\\", "/")
            parts = rel.split("/")
            if len(parts) >= 3:
                prefixes.add(f"{parts[0]}/{parts[1]}")
        return prefixes

    def _count_local_pending(self, pending: list[dict]) -> int:
        return sum(
            1
            for seg in pending
            if (self.issue_dir / seg["wav"]).is_file()
            and (self.issue_dir / seg["wav"]).stat().st_size >= WAV_MIN_SIZE
        )

    def _scp_with_progress(
        self,
        cmd: list[str],
        pending: list[dict],
        *,
        timeout: int,
        label: str,
    ) -> None:
        """长 SCP 期间每 20s 输出本地已收到文件数（避免「看起来没开始」）。"""
        stop = threading.Event()
        total = len(pending)

        def _heartbeat() -> None:
            started = time.time()
            last_n = -1
            while not stop.wait(20):
                n = self._count_local_pending(pending)
                if n != last_n or int(time.time() - started) % 60 < 20:
                    _log(
                        f"{label} 传输中… 本地 {n}/{total} WAV "
                        f"({int(time.time() - started)}s)"
                    )
                    last_n = n

        t = threading.Thread(target=_heartbeat, daemon=True)
        t.start()
        try:
            _log(f"{label} 已获取 SSH 锁，开始传输…")
            self._gcloud.run_with_retry(
                cmd, timeout=timeout, capture=True, label=label
            )
        finally:
            stop.set()
            t.join(timeout=1)

    @staticmethod
    def _group_pending_by_article_dir(
        pending: list[dict],
    ) -> list[tuple[str, list[dict]]]:
        """按 episodes/NN/audio_work/intro|01|… 分组，便于分批 SCP + 进度。"""
        groups: dict[str, list[dict]] = {}
        for seg in pending:
            rel = seg["wav"].replace("\\", "/")
            parts = rel.split("/")
            if len(parts) >= 5:
                key = "/".join(parts[:4])
            else:
                key = str(Path(rel).parent).replace("\\", "/")
            groups.setdefault(key, []).append(seg)
        return sorted(groups.items())

    def _download_wavs_bulk(self, pending: list[dict]) -> int:
        """按文章目录分批 SCP，每批有进度日志（避免单次递归 SCP 长时间无输出）。"""
        groups = self._group_pending_by_article_dir(pending)
        if not groups:
            return 0

        total = len(pending)
        n_groups = len(groups)
        for idx, (article_key, segs) in enumerate(groups, 1):
            remote_dir = f"{self.remote_root}/{article_key}"
            # episodes/08/audio_work/01 → local …/episodes/08/audio_work/
            local_parent = self.issue_dir / Path(article_key).parent
            local_parent.mkdir(parents=True, exist_ok=True)
            article_name = Path(article_key).name
            before = self._count_local_pending(pending)
            _log(
                f"下载 [{idx}/{n_groups}] {article_name}/ "
                f"({len(segs)} 文件，已完成 {before}/{total})…"
            )
            self._scp_with_progress(
                self._gcloud.scp_recursive_from_remote(remote_dir, local_parent),
                pending,
                timeout=max(900, QWEN_TTS_SSH_SHORT_TIMEOUT * 4),
                label=f"SCP({article_name})",
            )
            after = self._count_local_pending(pending)
            _log(f"↓ [{idx}/{n_groups}] {article_name}/ 完成，累计 {after}/{total} WAV")

        downloaded = self._count_local_pending(pending)
        _log(f"下载校验: {downloaded}/{total} 片段有效")
        return downloaded

    def synthesize_segments(self, jobs: list[QwenSegmentJob], *, force: bool = False) -> None:
        """批量合成多个片段，下载到本地 audio_work/。

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
            _log("全部片段 WAV 已存在，跳过远程合成")
            return

        cleanup_stale_local_ssh(
            self.issue_date,
            lock_path=self.issue_dir / ".gcloud_ssh.lock",
        )
        self._set_batch_context(pending)
        self._poll_expected_total = len(pending)
        self._last_reported_done = -1

        _log(
            f"远程批量合成: {len(pending)} 片段 "
            f"(EP {self._batch_episode or '?'}, batch={QWEN_TTS_BATCH_SIZE}, "
            f"model={QWEN_TTS_MODEL}, ssh_connect={QWEN_TTS_SSH_CONNECT_TIMEOUT}s, "
            f"ssh_kill=on, detached={'on' if QWEN_TTS_SSH_DETACHED_WORKER else 'off'})"
        )

        self._ensure_remote_setup()
        _log("上传参考音频与 manifest...")
        self._upload_ref_assets()
        self._upload_worker_if_needed()

        manifest = {
            "model": QWEN_TTS_MODEL,
            "ref_audio": "ref_audio.wav",
            "ref_text": self._ref_text,
            "language": QWEN_TTS_LANGUAGE,
            "dtype": QWEN_TTS_DTYPE,
            "batch_size": QWEN_TTS_BATCH_SIZE,
            "segments": pending,
        }
        manifest_local = self.issue_dir / ".qwen_job_manifest.json"
        manifest_local.parent.mkdir(parents=True, exist_ok=True)
        manifest_local.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        remote_manifest = f"{self.remote_root}/job_manifest.json"
        self._scp_to_remote(manifest_local, remote_manifest)

        progress_arg = f" --progress-file {self._progress_path}"
        inner_cmd = (
            f"source {QWEN_TTS_REMOTE_VENV}/bin/activate && "
            f"python -u {QWEN_TTS_REMOTE_WORKER} "
            f"--job {self.remote_root}/job_manifest.json "
            f"--workroot {self.remote_root}{progress_arg}"
        )
        _log("启动远程 worker（常驻模型 + prompt 缓存 + batch）…")
        self._run_remote_worker(inner_cmd, pending)

        remote_ready = self._remote_wav_ready_count(pending)
        if remote_ready < len(pending):
            raise RuntimeError(
                f"远程合成后 WAV 不足: {remote_ready}/{len(pending)}。"
                f"episodes/{self._batch_episode}/audio_work 可能未生成。"
            )

        total_dl = len(pending)
        _log(f"开始批量下载 WAV: {total_dl} 个片段")
        downloaded = self._download_wavs_bulk(pending)

        missing = [
            seg["wav"]
            for seg in pending
            if not (self.issue_dir / seg["wav"]).exists()
            or (self.issue_dir / seg["wav"]).stat().st_size < WAV_MIN_SIZE
        ]
        if missing:
            _log(f"批量下载后仍缺 {len(missing)} 个，逐个补拉…")
            for rel in missing:
                remote_wav = f"{self.remote_root}/{rel}"
                local_wav = self.issue_dir / rel
                self._scp_from_remote(remote_wav, local_wav)

        downloaded = sum(
            1
            for seg in pending
            if (self.issue_dir / seg["wav"]).exists()
            and (self.issue_dir / seg["wav"]).stat().st_size >= WAV_MIN_SIZE
        )
        if downloaded < total_dl:
            still = total_dl - downloaded
            raise RuntimeError(f"下载不完整: {downloaded}/{total_dl}（仍缺 {still} 个）")

        _log(f"下载完成: {downloaded}/{total_dl} 片段")

    def synthesize_from_work_dir(
        self,
        work_dir: Path,
        segments: list[dict],
        *,
        force: bool = False,
    ) -> None:
        """单篇文章内重试/补合成。"""
        jobs = [QwenSegmentJob(work_dir=work_dir, seg=s) for s in segments]
        self.synthesize_segments(jobs, force=force)

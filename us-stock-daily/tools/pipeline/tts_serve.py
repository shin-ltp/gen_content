"""Background TTS queue runner.

write_blocks.py pushes finalized blocks into production/tts/tts-queue.json
and pings this runner with tts-serve.py --wake <date>. The runner polls the
queue, and for each pending batch runs tts_dispatch in single-batch mode so
writing can continue while TTS is in progress.

Windows: this process stays alive for the whole writing session and shuts down
when the queue is drained after write_blocks completes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import contextlib
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
DISPATCH = _TOOLS_DIR / "tts_dispatch.py"
QUEUE_PATH = "production/tts/tts-queue.json"
PID_PATH = "production/tts/tts-serve.pid"
LOCK_PATH = "production/tts/tts-queue.lock"
POLL_SECONDS = 15
MAX_BATCH_ATTEMPTS = 2
MAX_RUNNER_RESTARTS = 3
MAC_HOST_DEFAULT = "cho@rw-mac-1"
MAC_WORKROOT_DEFAULT = "/Users/cho/fish-audio/jobs"


def issue_dir(date: str) -> Path:
    d = _US_ROOT / "daily-output" / date
    if not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


def queue_file(date: str) -> Path:
    return issue_dir(date) / QUEUE_PATH


def pid_file(date: str) -> Path:
    return issue_dir(date) / PID_PATH


@contextlib.contextmanager
def queue_lock(date: str):
    """Serialize queue mutations across the writer and background runner."""
    path = issue_dir(date) / LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        import msvcrt

        with path.open("a+b") as f:
            msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    with path.open("a+b") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def load_queue(date: str) -> dict:
    path = queue_file(date)
    if not path.is_file():
        return {"batches": [], "done": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(data, dict):
            return {"batches": [], "done": False}
        data.setdefault("batches", [])
        data.setdefault("done", False)
        return data
    except (OSError, json.JSONDecodeError):
        return {"batches": [], "done": False}


def save_queue(date: str, data: dict) -> None:
    path = queue_file(date)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)


def repair_empty_batches(date: str, data: dict) -> tuple[dict, bool]:
    """Replace lost empty segment lists before the queue starts a batch."""
    from tts_dispatch import block_segments_from_manifest

    changed = False
    for batch in data.get("batches", []):
        if batch.get("segments"):
            continue
        block = str(batch.get("block", "?"))
        try:
            segs = block_segments_from_manifest(date, block)
        except SystemExit as exc:
            batch["status"] = "failed"
            batch["note"] = f"empty segments; manifest recovery failed: {exc}"
            changed = True
            continue
        if segs:
            batch["segments"] = segs
            batch["note"] = f"empty segments rebuilt from manifest ({len(segs)})"
            changed = True
        else:
            batch["status"] = "failed"
            batch["note"] = f"empty segments; no '{block}' segments in manifest"
            changed = True
    return data, changed


def _pid_alive(pid: int) -> bool:
    # os.kill(pid, 0) is NOT a liveness probe on Windows: any signal value
    # other than the CTRL_* events maps to TerminateProcess and would kill
    # the very process we are checking.
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def running_pid(date: str) -> int | None:
    path = pid_file(date)
    if not path.is_file():
        return None
    try:
        pid = int(path.read_text(encoding="ascii").strip())
        return pid if _pid_alive(pid) else None
    except (OSError, ValueError):
        return None


def run_batch(date: str, block: str, *, force: bool, window_off: bool) -> int:
    cmd = [sys.executable, str(DISPATCH), date,
           "--batch", block]
    if force:
        cmd.append("--force")
    if window_off:
        cmd.append("--window-off")
    print(f"[serve] [{datetime.now():%H:%M:%S}] start batch {block}")
    try:
        r = subprocess.run(cmd, cwd=str(_US_ROOT))
        return r.returncode
    except KeyboardInterrupt:
        return 130


def _start_runner(date: str, *, force: bool = False,
                  window_off: bool = False) -> int:
    """Ensure exactly one background runner; 0 when alive or started."""
    pid = running_pid(date)
    if pid is not None:
        print(f"[wait] runner already running (pid={pid})")
        return 0
    with queue_lock(date):
        data = load_queue(date)
        data.setdefault("batches", [])
        data.setdefault("done", False)
        save_queue(date, data)
    cmd = [sys.executable, str(Path(__file__).resolve()), date, "--serve"]
    if force:
        cmd.append("--force")
    if window_off:
        cmd.append("--window-off")
    log_path = issue_dir(date) / "review" / "tts-serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        proc = subprocess.Popen(
            cmd, cwd=str(_US_ROOT), stdout=open(log_path, "ab"),
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        proc = subprocess.Popen(
            cmd, cwd=str(_US_ROOT), stdout=open(log_path, "ab"),
            stderr=subprocess.STDOUT, start_new_session=True)
    print(f"[wait] started runner pid={proc.pid} (log: {log_path})")
    time.sleep(1)
    if proc.poll() is not None:
        print(f"[wait] runner exited early with code {proc.returncode}")
        return 1
    return 0


def _mac_progress(date: str) -> dict:
    """Read-only snapshot of remote worker progress (empty when unreachable)."""
    host = os.getenv("FISH_AUDIO_TTS_REMOTE_HOST", MAC_HOST_DEFAULT).strip()
    workroot = os.getenv(
        "FISH_AUDIO_TTS_REMOTE_WORKROOT", MAC_WORKROOT_DEFAULT,
    ).strip().rstrip("/")
    root = f"{workroot}/usdaily/{date}"
    script = (
        f"for f in {root}/*/worker.progress.json; do "
        'if [ -f "$f" ]; then printf "%s=" "$f"; cat "$f"; echo; fi; done'
    )
    cmd = [
        "ssh", "-o", "ConnectTimeout=10", "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new", host, script,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if r.returncode != 0:
        return {}
    out: dict = {}
    for line in r.stdout.splitlines():
        path, sep, payload = line.partition("=")
        if not sep:
            continue
        try:
            out[path.rstrip("/").split("/")[-1]] = json.loads(payload)
        except json.JSONDecodeError:
            continue
    return out


def _progress_signature(date: str) -> str:
    """Everything that proves forward motion: local WAVs + Mac worker state."""
    audio = issue_dir(date) / "production" / "audio"
    wavs = sorted(audio.rglob("*.wav")) if audio.is_dir() else []
    local = [
        len(wavs),
        sum(w.stat().st_size for w in wavs),
        int(max((w.stat().st_mtime for w in wavs), default=0)),
    ]
    return json.dumps({"local": local, "mac": _mac_progress(date)},
                      sort_keys=True)


def _mark_batch(date: str, block: str, status: str, note: str) -> None:
    with queue_lock(date):
        data = load_queue(date)
        for b in data.get("batches", []):
            if b.get("block") == block:
                b["status"] = status
                b["note"] = note
                b["finished_at"] = datetime.now().isoformat(timespec="seconds")
                break
        if data.get("batches") and all(
                x.get("status") == "done" for x in data["batches"]):
            data["done"] = True
        save_queue(date, data)


def _summary(date: str) -> dict:
    data = load_queue(date)
    return {
        "runner_pid": running_pid(date),
        "done": data.get("done", False),
        "batches": [
            {"block": b.get("block"), "status": b.get("status"),
             "attempts": b.get("attempts"), "note": b.get("note", "")}
            for b in data.get("batches", [])
        ],
    }


def cmd_wait(args: argparse.Namespace) -> int:
    """Bounded monitor encoding the 30-minute stall rule.

    Exit codes: 0 all done, 1 failed batches, 2 timeout / unrecoverable
    runner. Progress is judged by local WAV activity plus the read-only Mac
    worker progress files, so a long-but-healthy remote batch survives.
    """
    deadline = time.time() + args.timeout_min * 60
    stall_sec = args.stall_min * 60
    restarts = 0
    last_sig: str | None = None
    last_change = time.time()
    data = load_queue(args.issue_date)
    batches = data.get("batches", [])
    if batches and all(b.get("status") in ("done", "failed") for b in batches):
        failed = [b.get("block") for b in batches if b.get("status") == "failed"]
        print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
        return 1 if failed else 0
    if data.get("done"):
        print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
        return 0
    if _start_runner(args.issue_date, force=args.force,
                     window_off=args.window_off) != 0:
        print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
        return 2

    while time.time() < deadline:
        data = load_queue(args.issue_date)
        batches = data.get("batches", [])
        terminal = all(b.get("status") in ("done", "failed")
                       for b in batches) if batches else False
        if terminal:
            failed = [b.get("block") for b in batches
                      if b.get("status") == "failed"]
            print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
            return 1 if failed else 0
        if data.get("done"):
            print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
            return 0

        pending = [b for b in batches if b.get("status") == "queued"]
        running = [b for b in batches if b.get("status") == "running"]
        if (pending or running) and running_pid(args.issue_date) is None:
            if restarts >= MAX_RUNNER_RESTARTS:
                print(f"[wait] runner died; restart budget exhausted "
                      f"({restarts})")
                print(json.dumps(_summary(args.issue_date),
                                 ensure_ascii=False))
                return 2
            restarts += 1
            print(f"[wait] runner died with pending work; restart "
                  f"{restarts}/{MAX_RUNNER_RESTARTS}")
            if _start_runner(args.issue_date, force=args.force,
                             window_off=args.window_off) != 0:
                print(json.dumps(_summary(args.issue_date),
                                 ensure_ascii=False))
                return 2

        if running:
            sig = _progress_signature(args.issue_date)
            now = time.time()
            if sig != last_sig:
                last_sig = sig
                last_change = now
            elif now - last_change >= stall_sec:
                block = str(running[0].get("block", "?"))
                print(f"[wait] batch {block} stalled for {args.stall_min}min; "
                      f"re-dispatching (cached WAVs are reused)")
                cmd = [sys.executable, str(DISPATCH), args.issue_date,
                       "--batch", block]
                if args.force:
                    cmd.append("--force")
                try:
                    code = subprocess.run(
                        cmd, cwd=str(_US_ROOT),
                        timeout=min(args.redispatch_min * 60,
                                    max(60, deadline - now)),
                    ).returncode
                except subprocess.TimeoutExpired:
                    code = 124
                if code == 0:
                    _mark_batch(args.issue_date, block, "done",
                                "stalled; re-dispatched by --wait (exit 0)")
                else:
                    attempts = int(running[0].get("attempts", 1) or 1)
                    if attempts < MAX_BATCH_ATTEMPTS:
                        _mark_batch(args.issue_date, block, "queued",
                                    f"stalled; re-dispatch exit {code}")
                    else:
                        _mark_batch(args.issue_date, block, "failed",
                                    f"stalled; re-dispatch exit {code}")
                last_sig = None
                last_change = time.time()

        time.sleep(args.poll_sec)

    print(f"[wait] timeout after {args.timeout_min}min")
    print(json.dumps(_summary(args.issue_date), ensure_ascii=False))
    return 2


def cmd_serve(args: argparse.Namespace) -> int:
    qpath = queue_file(args.issue_date)
    qpath.parent.mkdir(parents=True, exist_ok=True)
    with queue_lock(args.issue_date):
        if not qpath.exists():
            save_queue(args.issue_date, {"batches": [], "done": False})
        else:
            # A batch left "running" means the previous runner died mid-flight.
            # Requeue it so the new runner picks the work back up instead of
            # blocking the whole queue behind a zombie state.
            recovered = load_queue(args.issue_date)
            recovered, changed = repair_empty_batches(args.issue_date, recovered)
            for b in recovered.get("batches", []):
                if b.get("status") == "running":
                    attempts = int(b.get("attempts", 1) or 1)
                    if attempts < MAX_BATCH_ATTEMPTS:
                        b["status"] = "queued"
                        b["attempts"] = attempts + 1
                    else:
                        b["status"] = "failed"
                        b["note"] = "runner died twice; manual recovery required"
                    b["recovered_at"] = datetime.now().isoformat(timespec="seconds")
                    changed = True
            if changed:
                save_queue(args.issue_date, recovered)
                print("[serve] requeued batch(es) left running by a dead runner")
    if not args.replace and running_pid(args.issue_date) is not None:
        print("[serve] already running; wake-only")
        return 0
    pid_path = pid_file(args.issue_date)
    pid_tmp = pid_path.with_suffix(".tmp")
    pid_tmp.write_text(str(os.getpid()), encoding="ascii")
    os.replace(pid_tmp, pid_path)
    print(f"[serve] pid={os.getpid()} queue={qpath}")
    try:
        while True:
            data = load_queue(args.issue_date)
            data, repaired = repair_empty_batches(args.issue_date, data)
            if repaired:
                save_queue(args.issue_date, data)
            pending = [b for b in data.get("batches", [])
                       if b.get("status") == "queued"]
            if pending:
                batch = pending[0]
                block = batch.get("block", "?")
                batch["status"] = "running"
                batch["attempts"] = int(batch.get("attempts", 0) or 0) + 1
                batch["started_at"] = datetime.now().isoformat(timespec="seconds")
                save_queue(args.issue_date, data)
                code = run_batch(args.issue_date, block,
                                 force=args.force, window_off=args.window_off)
                with queue_lock(args.issue_date):
                    data = load_queue(args.issue_date)
                    for b in data.get("batches", []):
                        if b.get("block") == block and b.get("status") == "running":
                            attempts = int(b.get("attempts", 1) or 1)
                            if code == 0:
                                b["status"] = "done"
                                b["finished_at"] = datetime.now().isoformat(timespec="seconds")
                                b["exit_code"] = 0
                            elif attempts < MAX_BATCH_ATTEMPTS:
                                # Transient failures (engine hiccup, dispatch bug
                                # fixed mid-flight) get one automatic retry.
                                b["status"] = "queued"
                                b["note"] = f"exit {code}; auto-retry"
                            else:
                                b["status"] = "failed"
                                b["finished_at"] = datetime.now().isoformat(timespec="seconds")
                                b["exit_code"] = code
                    batches = data.get("batches", [])
                    if batches and all(
                            b.get("status") == "done" for b in batches):
                        data["done"] = True
                        print("[serve] all batches done; queue marked done")
                    save_queue(args.issue_date, data)
                print(f"[serve] batch {block} exit={code}")
                continue
            batches = data.get("batches", [])
            terminal = all(
                b.get("status") in ("done", "failed") for b in batches
            ) if batches else False
            if data.get("done") and not pending:
                print("[serve] queue drained and marked done; exiting")
                return 0
            if terminal and not pending:
                failed = [b.get("block") for b in batches
                          if b.get("status") == "failed"]
                if failed:
                    print(f"[serve] queue drained with failed batches: {failed}")
                    return 1
                print("[serve] queue drained and marked done; exiting")
                return 0
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("[serve] interrupted")
        return 130
    finally:
        if running_pid(args.issue_date) == os.getpid():
            pid_file(args.issue_date).unlink(missing_ok=True)


def cmd_wake(args: argparse.Namespace) -> int:
    pid = running_pid(args.issue_date)
    if pid is not None:
        print(f"[wake] runner already running (pid={pid}); it will pick up the queue")
        return 0
    with queue_lock(args.issue_date):
        data = load_queue(args.issue_date)
        data.setdefault("batches", [])
        data.setdefault("done", False)
        save_queue(args.issue_date, data)
    cmd = [sys.executable, str(Path(__file__).resolve()), args.issue_date, "--serve"]
    if args.force:
        cmd.append("--force")
    if args.window_off:
        cmd.append("--window-off")
    log_path = issue_dir(args.issue_date) / "review" / "tts-serve.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        proc = subprocess.Popen(
            cmd, cwd=str(_US_ROOT), stdout=open(log_path, "ab"),
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    else:
        proc = subprocess.Popen(
            cmd, cwd=str(_US_ROOT), stdout=open(log_path, "ab"),
            stderr=subprocess.STDOUT,
            start_new_session=True)
    print(f"[wake] started runner pid={proc.pid} (log: {log_path})")
    time.sleep(1)
    if proc.poll() is not None:
        print(f"[wake] runner exited early with code {proc.returncode}")
        return 1
    return 0


def cmd_finish(args: argparse.Namespace) -> int:
    with queue_lock(args.issue_date):
        data = load_queue(args.issue_date)
        data["done"] = True
        save_queue(args.issue_date, data)
    print("[finish] queue marked done; runner will exit when idle")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    data = load_queue(args.issue_date)
    pid = running_pid(args.issue_date)
    print(json.dumps({"runner_pid": pid, **data}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="TTS background queue runner")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--serve", action="store_true",
                        help="run the queue loop in foreground")
    parser.add_argument("--wake", action="store_true",
                        help="start the runner in background if not running")
    parser.add_argument("--finish", action="store_true",
                        help="mark queue done (runner exits after drain)")
    parser.add_argument("--status", action="store_true",
                        help="print queue and runner state")
    parser.add_argument("--wait", action="store_true",
                        help="bounded monitor: wait for completion, restart "
                             "dead runners, re-dispatch stalled batches")
    parser.add_argument("--timeout-min", type=int, default=180,
                        help="--wait overall timeout in minutes (default 180)")
    parser.add_argument("--poll-sec", type=int, default=60,
                        help="--wait poll interval in seconds (default 60)")
    parser.add_argument("--stall-min", type=int, default=30,
                        help="--wait stall threshold in minutes (default 30)")
    parser.add_argument("--redispatch-min", type=int, default=45,
                        help="--wait re-dispatch timeout in minutes (default 45)")
    parser.add_argument("--replace", action="store_true",
                        help="start a new runner even if one appears to be alive")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--window-off", action="store_true")
    args = parser.parse_args()
    if args.serve:
        return cmd_serve(args)
    if args.wake:
        return cmd_wake(args)
    if args.finish:
        return cmd_finish(args)
    if args.status:
        return cmd_status(args)
    if args.wait:
        return cmd_wait(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

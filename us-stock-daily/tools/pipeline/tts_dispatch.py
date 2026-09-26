"""Dispatch TTS work between this machine and the Mac helper.

Scheduling rules:

* Per-block queueing (user requirement): when a content block is finalized by
  write_blocks.py, its segments are pushed to production/tts/tts-queue.json and
  the queue runner (tts-serve.py) starts that batch immediately while writing
  continues. Each batch is synthesized with local WSL2 and the Mac helper in
  parallel; batches themselves run serially.
* Mac work is capped so the assigned chars are estimated to FINISH by 10:00
  JST (time-based char budget from tts_config.mac_char_budget). After 10:00
  (or if Mac is unreachable, or the budget is exhausted): local-only run.
* If the Mac worker dies mid-batch, the Mac branch of that batch is retried on
  Mac once, then rerouted to local WSL2 (segments already cached are skipped).

Usage:
  python tts_dispatch.py 2026-09-12 --dry-run
  python tts_dispatch.py 2026-09-12
  python tts_dispatch.py 2026-09-12 --force
  python tts_dispatch.py 2026-09-12 --window-off   # force the >=10:00 path
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
_TTS_DIR = _US_ROOT / "tools" / "tts"
sys.path.insert(0, str(_TTS_DIR))
from tts_config import (  # noqa: E402
    MAC_WINDOW_END,
    mac_char_budget,
    mac_window_remaining_sec,
)
GENERATE = _TTS_DIR / "generate_audio.py"
RECONSTRUCT = _TTS_DIR / "reconstruct_durations.py"
MANIFEST_PATH = "production/tts/manifest.json"
QUEUE_PATH = "production/tts/tts-queue.json"

PROBE_TIMEOUT = 8
RETRY_DELAY_SECONDS = 10


def issue_dir(date: str) -> Path:
    d = _US_ROOT / "daily-output" / date
    if not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


def mac_host() -> str:
    import os
    return os.getenv("FISH_AUDIO_TTS_REMOTE_HOST", "cho@rw-mac-1").strip()


def window_open(now: datetime | None = None) -> bool:
    now = now or datetime.now(ZoneInfo("Asia/Tokyo"))
    return now.time() < MAC_WINDOW_END


def mac_reachable() -> tuple[bool, str]:
    cmd = ["ssh", "-o", "BatchMode=yes",
           "-o", f"ConnectTimeout={PROBE_TIMEOUT}",
           mac_host(), "echo ok"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           timeout=PROBE_TIMEOUT + 5)
        ok = r.returncode == 0 and "ok" in (r.stdout or "")
        detail = (r.stdout or "").strip() or (r.stderr or "").strip()[:200]
        return ok, detail
    except FileNotFoundError:
        return False, "ssh command not found"
    except subprocess.TimeoutExpired:
        return False, f"ssh probe timed out after {PROBE_TIMEOUT}s"


def load_segments(date: str) -> list[dict]:
    path = issue_dir(date) / MANIFEST_PATH
    if not path.is_file():
        raise SystemExit(f"[error] manifest not found: {path} (run prepare_tts first)")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    segs = [s for s in data.get("segments", []) if s.get("type") == "tts"]
    if not segs:
        raise SystemExit("[error] manifest has no tts segments")
    return segs


def block_segments_from_manifest(date: str, block: str) -> list[dict]:
    """Rebuild a lost batch's segment list from the canonical TTS manifest."""
    all_segs = load_segments(date)
    if block == "B":
        return [s for s in all_segs if str(s.get("id", "")).startswith("B")]
    return [s for s in all_segs
            if str(s.get("id", "")).startswith(f"{block}-")]


def resolve_batch_segments(date: str, block: str, segments: list[dict]) -> list[dict]:
    """Never turn a damaged empty batch into an accidental full-manifest run."""
    segs = [s for s in segments if s.get("type") == "tts"]
    if segs:
        return segs
    segs = block_segments_from_manifest(date, block)
    if not segs:
        raise SystemExit(
            f"[error] batch '{block}' has no segments and none match it in "
            f"{MANIFEST_PATH}; refusing to dispatch the whole manifest")
    print(f"[recover] batch '{block}' segments were empty; rebuilt "
          f"{len(segs)} ids from manifest")
    return segs


def estimate_work(date: str, segs: list[dict]) -> dict[str, int]:
    """Character estimate per segment id (fallback 0 if txt missing)."""
    root = issue_dir(date)
    est: dict[str, int] = {}
    for s in segs:
        rel = s.get("file", "")
        p = root / "production" / rel if rel else None
        n = 0
        if p and p.is_file():
            n = len(p.read_text(encoding="utf-8-sig"))
        est[s["id"]] = n
    return est


def balanced_split(
    segs: list[dict], est: dict[str, int], mac_cap: int | None = None,
) -> tuple[list[str], list[str]]:
    """Longest-processing-time-first greedy split by estimated chars.

    `mac_cap` is a hard ceiling on Mac chars (10:00 JST finish rule). Groups
    over the ceiling are moved to local even if that unbalances the split.
    """
    ordered = sorted((s["id"] for s in segs), key=lambda i: est.get(i, 0), reverse=True)
    load = {"local": 0, "mac": 0}
    out: dict[str, list[str]] = {"local": [], "mac": []}
    for sid in ordered:
        side = "local" if load["local"] <= load["mac"] else "mac"
        out[side].append(sid)
        load[side] += est.get(sid, 0)
    if mac_cap is not None:
        mac_chars = load["mac"]
        if mac_chars > mac_cap:
            for sid in sorted(out["mac"], key=lambda i: est.get(i, 0), reverse=True):
                if mac_chars <= mac_cap:
                    break
                out["mac"].remove(sid)
                out["local"].append(sid)
                mac_chars -= est.get(sid, 0)
    return out["local"], out["mac"]


def run_generate(date: str, *, engine: str, only: list[str] | None = None,
                 force: bool = False) -> subprocess.Popen:
    cmd = [sys.executable, str(GENERATE), date, "--engine", engine]
    if only:
        cmd += ["--only", *only]
    if force:
        cmd.append("--force")
    return subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace")


def wait_and_report(p: subprocess.Popen, label: str) -> tuple[int, str]:
    out, _ = p.communicate()
    tail = "\n".join((out or "").strip().splitlines()[-8:])
    status = "OK" if p.returncode == 0 else f"FAIL({p.returncode})"
    print(f"[{label}] {status}")
    if tail:
        for line in tail.splitlines():
            print(f"  {label} | {line}")
    return p.returncode, out or ""


def reconstruct(date: str) -> int:
    r = subprocess.run([sys.executable, str(RECONSTRUCT), date],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print((r.stdout or "").strip())
    if r.returncode != 0:
        print((r.stderr or "").strip())
    return r.returncode


def process_batch(date: str, batch_segs: list[dict], est: dict[str, int],
                  in_window: bool, *, force: bool, dry_run: bool,
                  label: str) -> int:
    """Run one batch with local+Mac parallelism (or local-only off-window)."""
    reachable = False
    if in_window and not dry_run:
        reachable, _ = mac_reachable()
    elif in_window and dry_run:
        reachable = True
    cap = mac_char_budget() if (in_window and reachable) else 0
    remaining_min = mac_window_remaining_sec() / 60.0
    reason = None
    if not in_window:
        reason = "after 10:00 window"
    elif not reachable:
        reason = "mac unreachable"
    elif cap <= 0:
        reason = "mac char budget exhausted"
    if reason:
        print(f"[{label}] local-only run ({len(batch_segs)} segments): {reason}")
        if dry_run:
            return 0
        ids = [s["id"] for s in batch_segs]
        p = run_generate(date, engine="local", only=ids, force=force)
        code, _ = wait_and_report(p, f"{label}/local")
        return code

    local_ids, mac_ids = balanced_split(batch_segs, est, mac_cap=cap)
    print(f"[{label}] mac window: {remaining_min:.0f}min left / char cap {cap}")
    if not mac_ids:
        print(f"[{label}] local-only run ({len(batch_segs)} segments): cap {cap} too small")
        if dry_run:
            return 0
        ids = [s["id"] for s in batch_segs]
        p = run_generate(date, engine="local", only=ids, force=force)
        code, _ = wait_and_report(p, f"{label}/local")
        return code
    print(f"[{label}] local: {len(local_ids)} segments / "
          f"{sum(est.get(i, 0) for i in local_ids)} chars")
    print(f"[{label}] mac:   {len(mac_ids)} segments / "
          f"{sum(est.get(i, 0) for i in mac_ids)} chars")
    if dry_run:
        return 0

    p_local = run_generate(date, engine="local", only=local_ids, force=force)
    p_mac = run_generate(date, engine="mac", only=mac_ids, force=force)
    code_local, _ = wait_and_report(p_local, f"{label}/local")
    code_mac, _ = wait_and_report(p_mac, f"{label}/mac")

    if code_local != 0:
        print(f"[retry] local failed; retrying once in {RETRY_DELAY_SECONDS}s")
        import time as _time
        _time.sleep(RETRY_DELAY_SECONDS)
        p = run_generate(date, engine="local", only=local_ids, force=True)
        code_local, _ = wait_and_report(p, f"{label}/local-retry")
    if code_mac != 0:
        print(f"[retry] mac failed; retrying once in {RETRY_DELAY_SECONDS}s")
        import time as _time
        _time.sleep(RETRY_DELAY_SECONDS)
        p = run_generate(date, engine="mac", only=mac_ids, force=True)
        code_mac, _ = wait_and_report(p, f"{label}/mac-retry")
        if code_mac != 0:
            print(f"[fallback] mac branch rerouted to local WSL2 ({len(mac_ids)} segments)")
            p = run_generate(date, engine="local", only=mac_ids, force=True)
            code_mac, _ = wait_and_report(p, f"{label}/mac-local-fallback")

    if code_local != 0 or code_mac != 0:
        print(f"[error] batch '{label}' still failing (local={code_local}, mac={code_mac})")
        return 2
    return 0


def verify_batch_audio(date: str, segs: list[dict]) -> list[str]:
    """Return segment ids whose merged WAV is missing or suspiciously small."""
    audio_dir = issue_dir(date) / "production" / "audio"
    missing = []
    for seg in segs:
        sid = str(seg.get("id", ""))
        candidates = sorted(audio_dir.glob(f"*_{sid}.wav"))
        if not candidates or candidates[-1].stat().st_size < 1024:
            missing.append(sid)
    return missing


def run_reconstruct(date: str, *, allow_missing: bool) -> int:
    cmd = [sys.executable, str(RECONSTRUCT), date]
    if allow_missing:
        cmd.append("--allow-missing")
    r = subprocess.run(cmd, cwd=str(_US_ROOT))
    return r.returncode


def today_jst() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")


def pipeline_item_for_block(block: str, date: str) -> list[str]:
    if block in ("A", "C", "D"):
        return [f"tts-{block}"]
    if re.fullmatch(r"B\d+", block):
        return [f"tts-{block}"]
    if block == "B":
        # One queued B batch covers every theme slot in the current outline;
        # resolve the actual slots from segment ids (B1-p2 -> tts-B1). Slide
        # ids must never be used here: they produced bogus tts-s12 items.
        try:
            smap = json.loads((issue_dir(date) / "production" / "segment-map.json")
                              .read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return ["tts-B1"]
        slots = {
            m.group(1) for seg in smap.get("segments", [])
            if seg.get("type") == "tts"
            for m in [re.fullmatch(r"(B\d+)-p\d+", str(seg.get("id", "")))]
            if m
        }
        if slots:
            return [f"tts-{s}" for s in sorted(slots, key=lambda s: int(s[1:]))]
        return ["tts-B1"]
    return []


def cmd_preflight(args: argparse.Namespace) -> int:
    """Automation Step 0: check/start the local engine and probe the Mac.

    Local: ready -> report; else spawn start_server_guard async (STARTED_ASYNC
    semantics; progress lands in .runtime/tts-engine/engine-progress.json).
    Mac: read-only SSH probe + venv/worker/dirs check. Mac degradation is a
    warning only; dispatch falls back to local automatically.
    """
    import fish_local_engine

    report: dict = {"date": args.issue_date, "local": {}, "mac": {}}
    ok = True
    try:
        if fish_local_engine.server_ready():
            report["local"] = {"state": "ready", "api": fish_local_engine.API_URL}
        elif not fish_local_engine.START_GUARD.is_file():
            report["local"] = {
                "state": "failed",
                "error": f"launcher missing: {fish_local_engine.START_GUARD}",
            }
            ok = False
        else:
            cmd = [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(fish_local_engine.START_GUARD),
                "-Mode", "compile",
                "-WaitSeconds", str(fish_local_engine.STARTUP_TIMEOUT_SEC),
                "-PipelineDate", args.issue_date, "-NoWait",
            ]
            proc = subprocess.Popen(
                cmd, cwd=str(_US_ROOT),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            progress = (
                fish_local_engine.REPO_ROOT / ".runtime" / "tts-engine"
                / "engine-progress.json"
            )
            report["local"] = {
                "state": "starting",
                "guard_pid": proc.pid,
                "progress_file": str(progress),
            }
    except Exception as e:  # noqa: BLE001 - report and exit 2
        report["local"] = {"state": "failed", "error": str(e)[:300]}
        ok = False

    reachable, detail = mac_reachable()
    report["mac"] = {"reachable": reachable, "detail": (detail or "")[:200]}
    if reachable:
        workroot = os.getenv(
            "FISH_AUDIO_TTS_REMOTE_WORKROOT", "/Users/cho/fish-audio/jobs",
        ).strip().rstrip("/")
        worker = os.getenv(
            "FISH_AUDIO_TTS_REMOTE_WORKER",
            "/Users/cho/fish-audio/scripts/fish_audio_mlx_worker.py",
        ).strip()
        venv = os.getenv(
            "FISH_AUDIO_TTS_REMOTE_VENV", "/Users/cho/fish-audio/.venv",
        ).strip()
        remote_cmd = (
            f"mkdir -p {workroot}/usdaily/{args.issue_date} && "
            f"test -x {venv}/bin/python && test -f {worker} && echo MAC_READY"
        )
        try:
            r = subprocess.run(
                ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                 mac_host(), remote_cmd],
                capture_output=True, text=True, timeout=30,
            )
            ready = r.returncode == 0 and "MAC_READY" in (r.stdout or "")
            report["mac"]["service"] = "ready" if ready else "degraded"
            if not ready:
                report["mac"]["detail"] = (
                    (r.stderr or r.stdout or "").strip()[-300:]
                )
        except (OSError, subprocess.TimeoutExpired) as e:
            report["mac"]["service"] = "degraded"
            report["mac"]["detail"] = str(e)[:200]
    print(json.dumps(report, ensure_ascii=False))
    return 0 if ok else 2


def update_pipeline_state(date: str, block: str, ok: bool, detail: str) -> None:
    """Mirror batch completion into pipeline.json via the state machine CLI."""
    node = shutil.which("node")
    if not node:
        print("[pipeline] node not found; skip state update")
        return
    state = "done" if ok else "failed"
    for item in pipeline_item_for_block(block, date):
        cmd = [node, str(_TOOLS_DIR / "pipeline.mjs"), "set", "--date", date,
               "--id", item, "--state", state, "--note", detail[:180]]
        r = subprocess.run(cmd, cwd=str(_US_ROOT), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        print((r.stdout or r.stderr or "").strip())


def load_queue(date: str) -> list[dict]:
    qpath = issue_dir(date) / QUEUE_PATH
    if not qpath.is_file():
        return []
    try:
        data = json.loads(qpath.read_text(encoding="utf-8-sig"))
        return data.get("batches", []) if isinstance(data, dict) else []
    except (OSError, json.JSONDecodeError):
        return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Dispatch TTS across local and Mac")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--batch", default=None,
                        help="process a single queued batch by block id (e.g. A)")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--preflight", action="store_true",
        help="check/start local TTS engine (async guard) and probe the Mac "
             "worker; print one JSON report",
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="show split plan without starting synthesis")
    parser.add_argument("--window-off", action="store_true",
                        help="pretend the Mac window is closed (testing)")
    parser.add_argument("--no-reconstruct", action="store_true",
                        help="skip durations rebuild after a successful batch")
    args = parser.parse_args()
    if len(args.issue_date) != 10:
        raise SystemExit("[error] issue date must be YYYY-MM-DD")

    if args.preflight:
        return cmd_preflight(args)

    in_window = window_open() and not args.window_off
    if args.batch:
        queue = load_queue(args.issue_date)
        batch = next((b for b in queue if b.get("block") == args.batch), None)
        if not batch:
            raise SystemExit(f"[error] batch '{args.batch}' not found in queue")
        segs = resolve_batch_segments(args.issue_date, args.batch,
                                      batch.get("segments", []))
        est = estimate_work(args.issue_date, segs)
        print(f"[window] in_window={in_window} batch={args.batch} segments={len(segs)}")
        if args.dry_run:
            reachable, detail = (mac_reachable() if in_window else (False, ""))
            print(f"[window] mac_reachable={reachable}" + (f" ({detail})" if detail else ""))
        code = process_batch(args.issue_date, segs, est, in_window,
                             force=args.force, dry_run=args.dry_run,
                            label=f"batch-{args.batch}")
        if args.dry_run:
            return 0
        if code != 0:
            update_pipeline_state(args.issue_date, args.batch, False,
                                  f"dispatch exit={code}")
            return code
        missing = verify_batch_audio(args.issue_date, segs)
        if missing:
            update_pipeline_state(args.issue_date, args.batch, False,
                                  "missing wav: " + ", ".join(missing[:8]))
            print(f"[error] missing WAVs after batch {args.batch}: "
                  + ", ".join(missing))
            return 3
        if not args.no_reconstruct:
            # Batch mode is incremental: other batches may not be synthesized
            # yet, so durations.json must accept the segments that exist.
            rcode = run_reconstruct(args.issue_date, allow_missing=True)
            if rcode != 0:
                update_pipeline_state(args.issue_date, args.batch, False,
                                      "reconstruct failed")
                return rcode
        update_pipeline_state(args.issue_date, args.batch, True,
                              f"batch ok ({len(segs)} segments)")
        return 0

    queue = load_queue(args.issue_date)
    print(f"[window] in_window={in_window} queued_batches={len(queue)}")
    if not queue:
        # Backward-compatible whole-manifest mode.
        segs = load_segments(args.issue_date)
        est = estimate_work(args.issue_date, segs)
        if args.dry_run:
            reachable, detail = (mac_reachable() if in_window else (False, ""))
            print(f"[window] mac_reachable={reachable}" + (f" ({detail})" if detail else ""))
        code = process_batch(args.issue_date, segs, est, in_window,
                             force=args.force, dry_run=args.dry_run, label="all")
        if args.dry_run:
            return 0
        if code != 0:
            return code
        rcode = reconstruct(args.issue_date)
        if rcode != 0:
            print("[error] reconstruct_durations failed")
            return rcode
        print("[done] TTS complete, durations rebuilt")
        return 0

    all_ok = True
    for batch in queue:
        block = str(batch.get("block", "?"))
        segs = resolve_batch_segments(args.issue_date, block,
                                      batch.get("segments", []))
        est = estimate_work(args.issue_date, segs)
        code = process_batch(args.issue_date, segs, est, in_window,
                             force=args.force, dry_run=args.dry_run,
                             label=f"batch-{block}")
        if code != 0:
            all_ok = False
            break
    if args.dry_run:
        return 0
    if not all_ok:
        return 2
    rcode = reconstruct(args.issue_date)
    if rcode != 0:
        print("[error] reconstruct_durations failed")
        return rcode
    print("[done] queued TTS complete, durations rebuilt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

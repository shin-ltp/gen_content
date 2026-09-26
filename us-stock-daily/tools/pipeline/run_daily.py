"""Daily pipeline orchestrator: code-owned sequencing, per-stage state.

Stages (sequential, each resumable):
  1. collect   node collect-all.mjs (Gate #0 hard filter)
  2. select    analyze_topics.py (stage 0 code filter + 2 LLM calls)
  3. write     write_blocks.py     (contract + script + drafts)
  4. qa        pre_tts_qa.py       (full narration gate: japanese/length/
                                   disclaimer/segment-map/tts-txt)
  5. tts       tts_dispatch.py     (parallel local/Mac inside the morning window)

State file: production/pipeline-progress.json with atomic writes. A crashed
run resumes at the first non-passed stage; use --from <stage> to force.

Usage:
  python run_daily.py 2026-09-12
  python run_daily.py 2026-09-12 --from write
  python run_daily.py 2026-09-12 --skip tts
  python run_daily.py 2026-09-12 --status
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
COLLECT = _US_ROOT / "tools" / "collect" / "collect-all.mjs"
STATE_PATH = "production/pipeline-progress.json"

STAGES = ["collect", "select", "write", "qa", "tts"]


def issue_dir(date: str, *, create: bool = False) -> Path:
    d = _US_ROOT / "daily-output" / date
    if create:
        d.mkdir(parents=True, exist_ok=True)
    elif not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


class ProgressState:
    """Atomic JSON state for cross-run crash recovery."""

    def __init__(self, date: str):
        self.date = date
        self.path = issue_dir(date, create=True) / STATE_PATH

    def read(self) -> dict:
        for _ in range(5):
            try:
                if self.path.is_file():
                    return json.loads(self.path.read_text(encoding="utf-8-sig"))
                break
            except (OSError, json.JSONDecodeError):
                time.sleep(0.05)
        return {"episode": self.date, "stages": {}}

    def write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        os.replace(tmp, self.path)

    def mark(self, stage: str, status: str, note: str = "") -> None:
        data = self.read()
        data.setdefault("stages", {})[stage] = {
            "status": status,
            "at": datetime.now().isoformat(timespec="seconds"),
            "note": note,
        }
        data["updated_at"] = datetime.now().isoformat(timespec="seconds")
        self.write(data)

    def reset_running(self) -> None:
        """Reset stale in_progress entries left by a crashed run."""
        data = self.read()
        for name, st in data.get("stages", {}).items():
            if st.get("status") == "in_progress":
                st["status"] = "pending"
                st["note"] = "reset from stale in_progress"
        self.write(data)


def run_cmd(args: list[str], label: str, timeout: int = 7200) -> tuple[int, str]:
    """Run a subprocess and stream nothing (log captured). Returns (code, log)."""
    print(f"[run] {label}: {' '.join(args)}")
    try:
        r = subprocess.run(args, cwd=str(_US_ROOT), timeout=timeout,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired as e:
        return 124, f"timed out after {timeout}s"
    except FileNotFoundError as e:
        return 127, f"command not found: {e}"
    out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
    tail = "\n".join(out.splitlines()[-10:])
    for line in tail.splitlines():
        print(f"  {label} | {line}")
    return r.returncode, out


def write_log(date: str, stage: str, log: str) -> None:
    log_dir = issue_dir(date, create=True) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    name = f"{datetime.now().strftime('%H%M%S')}-{stage}.log"
    (log_dir / name).write_text(log, encoding="utf-8")


def cmd_collect(date: str, extra: list[str]) -> tuple[int, str]:
    args = ["node", str(COLLECT), "--date", date] + extra
    return run_cmd(args, "collect", timeout=3600)


def cmd_select(date: str, extra: list[str]) -> tuple[int, str]:
    return run_cmd([sys.executable, str(_TOOLS_DIR / "analyze_topics.py"), date],
                   "select", timeout=3600)


def cmd_write(date: str, extra: list[str]) -> tuple[int, str]:
    return run_cmd([sys.executable, str(_TOOLS_DIR / "write_blocks.py"), date],
                   "write", timeout=7200)


def cmd_qa(date: str, extra: list[str]) -> tuple[int, str]:
    # Pre-TTS narration gate (2026-09-26 QA restructure). The composition
    # gate (final_qa.py: decode integrity + A/V sync + layout frames) runs
    # after the Remotion render, outside these stages.
    return run_cmd([sys.executable, str(_TOOLS_DIR / "pre_tts_qa.py"), date],
                   "qa", timeout=3600)


def cmd_tts(date: str, extra: list[str]) -> tuple[int, str]:
    code, log = run_cmd(
        [sys.executable, str(_US_ROOT / "tools" / "tts" / "prepare_tts.py"), date, "--partial"],
        "tts_prepare", timeout=900)
    if code != 0:
        return code, log
    a = [sys.executable, str(_TOOLS_DIR / "tts_dispatch.py"), date]
    tts_budget = int(os.getenv("TTS_STAGE_TIMEOUT", str(12 * 3600)))
    return run_cmd(a, "tts", timeout=tts_budget)


STAGE_CMDS = {
    "collect": cmd_collect,
    "select": cmd_select,
    "write": cmd_write,
    "qa": cmd_qa,
    "tts": cmd_tts,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily pipeline orchestrator")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--from", dest="from_stage", choices=STAGES,
                        help="restart from a specific stage")
    parser.add_argument("--skip", nargs="+", default=[],
                        help="stages to skip")
    parser.add_argument("--status", action="store_true",
                        help="show state and exit")
    parser.add_argument("collect_args", nargs="*",
                        help="extra args passed to collect-all.mjs")
    args = parser.parse_args()

    state = ProgressState(args.issue_date)
    state.reset_running()

    if args.status:
        print(json.dumps(state.read(), ensure_ascii=False, indent=2))
        return 0

    stages = [s for s in STAGES if s not in (args.skip or [])]
    start = STAGES.index(args.from_stage) if args.from_stage else 0
    stages = stages[start:]

    for stage in stages:
        st = state.read().get("stages", {}).get(stage, {})
        if st.get("status") == "passed":
            print(f"[skip] {stage}: already passed")
            continue
        state.mark(stage, "in_progress")
        code, log = STAGE_CMDS[stage](args.issue_date, args.collect_args)
        write_log(args.issue_date, stage, log)
        if code == 0:
            state.mark(stage, "passed")
            print(f"[ok] {stage} passed")
        else:
            state.mark(stage, "failed", f"exit {code}")
            print(f"[fail] {stage} exit {code}; state saved; "
                  f"re-run run_daily.py --from {stage} after fixing")
            return code
    print("[done] all requested stages passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

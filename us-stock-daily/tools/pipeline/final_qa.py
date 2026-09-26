"""Final QA = Remotion composition gate (post-render), all mechanical, zero LLM.

2026-09-26 QA restructure. Rework-cost rule: every check belongs at the
cheapest point that can still fix it cheaply.
  - narration text checks (simplified-kanji / disclaimer contract / draft
    length / paragraph-number consistency / tts-txt equality, plus an
    optional advisory semantic review)  -> pre_tts_qa.py, enforced by
    write_blocks.py BEFORE a block is queued for TTS (post-TTS wording
    fixes cost a resynth + full re-render: 9/24 diesel, 9/25 wording).
  - image content/layout checks (asset refs / portrait meta / s1 preview /
    aspect ratio / real-DOM audit / vision contact sheet) -> visual_qa_gate.py
    + visual_dom_audit.mjs, auto-run by prepare_visual_assets.py right after
    render_visual.py (9/24 s1 layout incident cost a full re-render).
  - what is left HERE inspects only the rendered composition itself:
    1. decode_integrity : ffprobe -count_frames full decode. Read frames
      must equal the slot-frame sum and stderr must be empty (9/24: two
      renders raced on one file; the header read fine but the decode died
      at frame 50072/57572 with NAL errors).
    2. av_sync          : every segment audio exists and its measured wav
      length matches the timeline durationSec; exactDuration slots must
      contain their audio (END fixed card).
    3. layout_frames    : extract one mp4 frame at each segment's content
      midpoint and perceptually compare it with the expected slide shot
      PNG (mirrors Episode.tsx, which shows exactly seg.image; the END
      slot is sampled on both sides of image2AtSec so the disclaimer still
      must be on screen last). Catches stale/mismatched composition,
      blank or black frames and wrong-slide A/V drift.

Usage:
  python -X utf8 final_qa.py 2026-09-26 [path-to-mp4] [--skip-frames]
Exit codes: 0 = pass, 1 = usage/environment error, 2 = composition defect.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
PUBLIC = _US_ROOT / "remotion" / "public"
COMPOSITOR = (_US_ROOT / "remotion" / "node_modules" / "@remotion"
              / "compositor-win32-x64-msvc")
FFPROBE = COMPOSITOR / "ffprobe.exe"
FFMPEG = COMPOSITOR / "ffmpeg.exe"

# Fallback only; the live value is parsed from remotion/src/constants.ts so
# the gate cannot silently drift from the renderer.
FLIP_FRAMES_DEFAULT = 16

# mean-abs gray diff (0-255 scale, downsampled 96x54). The same PNG through
# the h264 round-trip stays far below the fail band; different slides measure
# well above it (9/25 calibration: same < 10, adjacent > 20).
FRAME_FAIL_DIFF = 25
FRAME_WARN_DIFF = 12


def _flip_frames() -> int:
    src = _US_ROOT / "remotion" / "src" / "constants.ts"
    try:
        m = re.search(r"FLIP_FRAMES\s*=\s*(\d+)", src.read_text(encoding="utf-8"))
        if m:
            return int(m.group(1))
    except OSError:
        pass
    return FLIP_FRAMES_DEFAULT


def _probe(exe: Path, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([str(exe), "-v", "error", *args],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def _wav_duration(path: Path) -> float | None:
    r = _probe(FFPROBE, ["-show_entries", "format=duration", "-of",
                         "json", str(path)])
    try:
        return float(json.loads(r.stdout)["format"]["duration"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


def slot_math(input_data: dict) -> tuple[list[dict], int]:
    """Mirror Episode.tsx: slot = content + 2*FLIP + sting pad (exact slots: content)."""
    fps = input_data["fps"]
    flip = _flip_frames()
    sting_frames = round(input_data.get("stingFrames") or 180)
    rows: list[dict] = []
    cursor = 0
    for seg in input_data["segments"]:
        content = max(1, round(seg["durationSec"] * fps))
        sting_pad = (sting_frames + fps) if seg.get("sting") else 0
        if seg.get("exactDuration"):
            slot, audio_from = content, 0
        else:
            slot, audio_from = content + 2 * flip + sting_pad, flip + sting_pad
        rows.append({"seg": seg, "from": cursor, "slot": slot,
                     "content": content, "audio_from": audio_from})
        cursor += slot
    return rows, cursor


def check_decode_integrity(mp4: Path, total_frames: int, fps: int) -> tuple[bool, str]:
    """Full-decode validation: counting frames also exposes NAL corruption."""
    if not mp4.is_file() or mp4.stat().st_size < 1_000_000:
        return False, f"episode video missing or tiny: {mp4}"
    r = _probe(FFPROBE, ["-count_frames", "-select_streams", "v:0",
                         "-show_entries", "stream=nb_read_frames:format=duration",
                         "-of", "json", str(mp4)])
    err_lines = [ln for ln in (r.stderr or "").splitlines() if ln.strip()]
    try:
        data = json.loads(r.stdout)
        read_frames = int(data["streams"][0]["nb_read_frames"])
        duration = float(data["format"]["duration"])
    except (KeyError, IndexError, ValueError, TypeError, json.JSONDecodeError):
        return False, ("ffprobe full decode failed (rc="
                       f"{r.returncode}): "
                       f"{'; '.join(err_lines[:3]) or 'no frame count in output'}")
    problems = []
    if err_lines:
        problems.append(f"decode stderr x{len(err_lines)}: {err_lines[0][:160]}")
    if read_frames != total_frames:
        problems.append(f"decoded frames {read_frames} != timeline {total_frames}")
    if abs(duration - total_frames / fps) > 2.0:
        problems.append(f"container duration {duration:.1f}s != frame math "
                        f"{total_frames / fps:.1f}s")
    return (not problems,
            f"{read_frames} frames decoded clean, duration {duration:.1f}s"
            if not problems else "\n".join(problems))


def check_av_sync(rows: list[dict]) -> tuple[bool, str]:
    """Measured audio length vs timeline slot, per segment."""
    problems: list[str] = []
    checked = 0
    for row in rows:
        seg = row["seg"]
        audio = seg.get("audio")
        if not audio:
            continue
        path = PUBLIC / audio
        if not path.is_file() or path.stat().st_size < 1000:
            problems.append(f"{seg['id']}: audio missing/empty ({audio})")
            continue
        checked += 1
        if seg.get("timingSource") != "measured":
            continue  # estimated slots have no wav-length contract
        dur = _wav_duration(path)
        if dur is None:
            problems.append(f"{seg['id']}: unreadable audio duration ({audio})")
            continue
        if seg.get("exactDuration"):
            if dur > seg["durationSec"] + 0.05:
                problems.append(
                    f"{seg['id']}: audio {dur:.3f}s exceeds exact slot "
                    f"{seg['durationSec']:.3f}s (END card would clip)")
        elif abs(dur - seg["durationSec"]) > 0.25:
            problems.append(
                f"{seg['id']}: wav {dur:.3f}s vs timeline "
                f"{seg['durationSec']:.3f}s (drift {dur - seg['durationSec']:+.3f}s)")
    return not problems, (f"{checked} segment audio(s) match the timeline"
                          if not problems else "\n".join(problems))


def _gray(path: Path, size: tuple[int, int] = (96, 54)):
    from PIL import Image
    with Image.open(path) as im:
        return im.convert("L").resize(size)


def _lum_stats(img) -> tuple[float, float]:
    data = img.tobytes()
    mean = sum(data) / len(data)
    var = sum((d - mean) ** 2 for d in data) / len(data)
    return mean, var ** 0.5


def _mean_abs_diff(a_img, b_img) -> float:
    ba, bb = a_img.tobytes(), b_img.tobytes()
    return sum(abs(x - y) for x, y in zip(ba, bb)) / len(ba)


def _extract_frame(mp4: Path, t_sec: float, out_png: Path) -> bool:
    r = subprocess.run(
        [str(FFMPEG), "-nostdin", "-v", "error", "-ss", f"{max(t_sec, 0.0):.3f}",
         "-i", str(mp4), "-frames:v", "1", "-y", str(out_png)],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0 and out_png.is_file()


def _sample_windows(row: dict, fps: int) -> list[tuple[float, str]]:
    """(slot-local seconds, expected public-relative image) pairs.

    Timestamps avoid the pixel-dissolve transitions Episode.tsx paints at
    every slot boundary (outgoing overlay in the first FLIP frames, incoming
    overlay in the last FLIP frames). That flat window is also where the
    narration audio actually runs, so it doubles as the A/V alignment check.
    """
    seg = row["seg"]
    out: list[tuple[float, str]] = []
    image = seg.get("image")
    if not image:
        return out  # code-rendered EndCard: no shot to compare against
    flip_sec = _flip_frames() / fps
    if seg.get("exactDuration"):
        if seg.get("image2") and seg.get("image2AtSec") is not None:
            switch = float(seg["image2AtSec"])
            if switch >= 1.0:
                # first half: the slide itself (END-disclaimer still)
                mid = max(switch / 2.0, min(flip_sec, switch - flip_sec))
                out.append((mid, image))
            else:
                out.append((0.6, image))
            tail_mid = (switch + seg["durationSec"]) / 2.0
            out.append((min(tail_mid, seg["durationSec"] - flip_sec),
                        seg["image2"]))
        else:
            out.append((seg["durationSec"] / 2.0, image))
        return out
    start = row["audio_from"] / fps
    end = start + row["content"] / fps
    out.append(((start + end) / 2.0, image))
    return out


def check_layout_frames(mp4: Path, rows: list[dict], fps: int,
                        sample_dir: Path) -> tuple[bool, str, list[dict]]:
    sample_dir.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []
    notes: list[str] = []
    frames: list[dict] = []
    idx = 0
    for row in rows:
        seg = row["seg"]
        seg_id = str(seg.get("id", f"order{seg.get('order')}"))
        windows = _sample_windows(row, fps)
        if not windows:
            # no shot for this slot: verify it is not a black screen either
            idx += 1
            out_png = sample_dir / f"{idx:03d}_{re.sub(r'[^0-9A-Za-z_.-]', '_', seg_id)}.png"
            t = (row["from"] + row["slot"] / 2.0) / fps
            if _extract_frame(mp4, t, out_png):
                mean, std = _lum_stats(_gray(out_png))
                if mean < 8 and std < 2:
                    problems.append(f"{seg_id}: blank/black frame at {t:.1f}s")
                notes.append(f"{seg_id}: code-rendered end card sampled "
                             f"(no shot comparison)")
            continue
        for local_sec, img_rel in windows:
            idx += 1
            shot = PUBLIC / img_rel
            if not shot.is_file():
                problems.append(f"{seg_id}: expected shot missing: {img_rel}")
                continue
            out_png = sample_dir / f"{idx:03d}_{re.sub(r'[^0-9A-Za-z_.-]', '_', seg_id)}.png"
            # row["from"] is in frames, local_sec is slot-local seconds.
            t = row["from"] / fps + local_sec
            if not _extract_frame(mp4, t, out_png):
                problems.append(f"{seg_id}: frame extraction failed at {t:.1f}s")
                continue
            frame_img = _gray(out_png)
            shot_img = _gray(shot)
            diff = _mean_abs_diff(frame_img, shot_img)
            mean, std = _lum_stats(frame_img)
            shot_mean, shot_std = _lum_stats(shot_img)
            frames.append({"id": seg_id, "t_sec": round(t, 2),
                           "image": img_rel, "diff": round(diff, 2)})
            if mean < 10 and shot_mean > 30:
                problems.append(f"{seg_id}: black frame at {t:.1f}s "
                                f"(expected {img_rel})")
            elif std < 1.5 and shot_std > 6:
                problems.append(f"{seg_id}: blank flat frame at {t:.1f}s "
                                f"(expected {img_rel})")
            elif diff > FRAME_FAIL_DIFF:
                problems.append(f"{seg_id}: frame@{t:.1f}s differs from "
                                f"{img_rel} (mean-abs diff {diff:.1f}; "
                                f"stale composition or misaligned cut)")
            elif diff > FRAME_WARN_DIFF:
                notes.append(f"{seg_id}: diff {diff:.1f} vs {img_rel} (warn band)")
    out = (f"{idx} sampled frame(s) match their expected slide shots"
           if not problems else "\n".join(problems))
    if notes:
        out += "\nnote: " + "; ".join(notes[:6])
    return not problems, out, frames


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Final QA: Remotion composition gate (A/V sync + layout)")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("mp4", nargs="?",
                        help="default: daily-output/<date>/episode.mp4")
    parser.add_argument("--skip-frames", action="store_true",
                        help="decode + av_sync only (skip per-segment frame "
                             "extraction; cheaper re-check loop)")
    args = parser.parse_args()

    issue = _US_ROOT / "daily-output" / args.issue_date
    if not issue.is_dir():
        print(f"[error] issue directory not found: {issue}")
        return 1
    if not FFPROBE.is_file() or not FFMPEG.is_file():
        print(f"[error] remotion compositor binaries not found under {COMPOSITOR}")
        return 1
    input_path = PUBLIC / "remotion_input.json"
    if not input_path.is_file():
        print(f"[error] {input_path} missing (run prepare_remotion first)")
        return 1
    input_data = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if str(input_data.get("episode", "")) != args.issue_date:
        print(f"[error] remotion_input.json is for episode "
              f"'{input_data.get('episode')}', not {args.issue_date}: "
              "rerun prepare_remotion before rendering/QA")
        return 2

    mp4 = Path(args.mp4) if args.mp4 else issue / "episode.mp4"
    fps = int(input_data["fps"])
    rows, total_frames = slot_math(input_data)

    print(f"[final-qa] {args.issue_date}: {len(rows)} segments, "
          f"{total_frames} frames ({total_frames / fps:.1f}s)")
    checks: list[dict] = []

    def _run(name: str, fn) -> bool:
        passed, out = fn
        checks.append({"check": name, "passed": passed, "output": out[-3000:]})
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
        if not passed:
            for line in out.strip().splitlines()[:12]:
                print(f"         {line}")
        return passed

    _run("decode_integrity", check_decode_integrity(mp4, total_frames, fps))
    _run("av_sync", check_av_sync(rows))
    frames: list[dict] = []
    if args.skip_frames:
        print("  [SKIP] layout_frames (--skip-frames)")
    else:
        sample_dir = issue / "production" / "final-qa"
        passed, out, frames = check_layout_frames(mp4, rows, fps, sample_dir)
        _run("layout_frames", (passed, out))

    report = {
        "stage": "composition",
        "date": args.issue_date,
        "mp4": str(mp4),
        "expected_frames": total_frames,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "layout_samples": frames,
    }
    report_path = issue / "review" / "final-qa.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    failed = [c for c in checks if not c["passed"]]
    print(f"[final-qa] report -> {report_path}")
    if failed:
        print(f"[final-qa] FAILED: {', '.join(c['check'] for c in failed)}")
        return 2
    print("[final-qa] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

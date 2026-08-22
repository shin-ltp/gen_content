#!/usr/bin/env python3
"""用指定 reference 重新合成单个 Fish Audio 片段（远程 Mac MLX / SSH）。"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
from pathlib import Path

# Windows UTF-8
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def main() -> int:
    p = argparse.ArgumentParser(description="重新合成单个 Fish Audio 片段")
    p.add_argument("issue_date", help="YYYY-MM-DD")
    p.add_argument("--episode", "-e", required=True, help="例: 01")
    p.add_argument("--article", "-a", required=True, help="例: 01")
    p.add_argument("--seg", "-s", type=int, required=True, help="片段 index，例: 2 → seg_0002.wav")
    p.add_argument(
        "--ref-dir",
        type=Path,
        default=None,
        help="参考音目录（含 ref_audio.wav + ref_meta.json）；未指定则用 TTS_REF_ROLE",
    )
    args = p.parse_args()

    if args.ref_dir is not None:
        ref_dir = args.ref_dir.resolve()
        os.environ["TTS_REF_AUDIO"] = str(ref_dir / "ref_audio.wav")
        os.environ["TTS_REF_META"] = str(ref_dir / "ref_meta.json")

    from config import get_issue_dir
    from fish_audio_batch import FishAudioBatchEngine, FishAudioSegmentJob

    issue_dir = get_issue_dir(args.issue_date)
    ep = args.episode.zfill(2)
    art = args.article.zfill(2)
    work_dir = issue_dir / "episodes" / ep / "audio_work" / art
    segments_path = work_dir / "segments.json"
    if not segments_path.exists():
        print(f"ERROR: {segments_path} 不存在", file=sys.stderr)
        return 1

    segments = json.loads(segments_path.read_text(encoding="utf-8")).get("segments", [])
    target = next((s for s in segments if s.get("index") == args.seg), None)
    if target is None or not target.get("has_text"):
        print(f"ERROR: index={args.seg} 的文本片段不存在", file=sys.stderr)
        return 1

    wav_name = target["wav_file"]
    wav_path = work_dir / wav_name
    if wav_path.exists():
        wav_path.unlink()
        print(f"已删除旧文件: {wav_path}")

    engine = FishAudioBatchEngine(args.issue_date)
    job = FishAudioSegmentJob(work_dir=work_dir, seg=target)
    print(
        f"合成: {args.issue_date} EP{ep} art{art} {wav_name}\n"
        f"  文本: {target['text'][:80]}{'…' if len(target['text']) > 80 else ''}"
    )
    engine.synthesize_segments([job], force=True)

    if wav_path.exists() and wav_path.stat().st_size > 1000:
        print(f"完成: {wav_path}")
        return 0
    print(f"ERROR: 合成失败，{wav_path} 未生成", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

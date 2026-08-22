"""
metadata.json に YouTube 用の静的フィールドを書き込む（アップロード・API 不要）。

- title / sections_jp: upload_youtube と同じロジック
- 各記事の youtube_start_sec / youtube_start_time: episodes/XX/video/remotion_input.json
  を優先し、remotion/src/Composition.tsx の articleVisuals（FPS=30 丸め）と一致
- video_id / video_url: 空（手動追記用）。既に video_id がある場合は既定で保持

使用例:
  python backfill_youtube_stub.py --issue 2026-03-21 01 02 03 04 05 06
  python backfill_youtube_stub.py --issue 2026-03-21 01 --no-preserve
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
if str(_script_dir) not in sys.path:
    sys.path.insert(0, str(_script_dir))

from upload_youtube import apply_youtube_metadata_stub


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--issue", required=True, help="出版日 YYYY-MM-DD")
    parser.add_argument(
        "episodes",
        nargs="+",
        metavar="EP",
        help="エピソード番号（例: 01 02）",
    )
    parser.add_argument(
        "--no-preserve",
        action="store_true",
        help="既存の video_id / video_url も空に戻す",
    )
    args = parser.parse_args()
    for raw in args.episodes:
        ep = str(raw).strip().zfill(2)
        apply_youtube_metadata_stub(
            args.issue,
            ep,
            preserve_existing_ids=not args.no_preserve,
        )


if __name__ == "__main__":
    main()

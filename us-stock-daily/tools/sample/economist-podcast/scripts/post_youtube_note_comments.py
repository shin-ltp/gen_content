"""
各エピソードの metadata.json から YouTube video_id を読み、note まとめページへの案内コメントを投稿する。

使用例:
  python post_youtube_note_comments.py --issue 2026-04-04 \\
    --note-url https://note.com/global_clip/n/nb360265b6d4b

前提:
  - upload_youtube.py と同じ OAuth クライアント・トークン（youtube / youtube.force-ssl 相当のスコープ）
  - 各 episodes/XX/metadata.json に youtube.video_id があること

動作:
  - 号の総記事数・動画本数は episodes_plan.json または各 metadata から集計（upload_youtube と同様）
  - 既に認証チャンネルが同じ note URL を含むコメントをその動画に投稿済みならスキップ
  - YouTube Data API v3 には「コメントを固定」する公式メソッドがないため、投稿後は
    YouTube スタジオでの手動固定が必要（実行時に明示）

参考: upload_youtube.py（認証・号ディレクトリ）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from config import get_issue_dir

from upload_youtube import (
    YouTubeAuthRequiredError,
    obtain_youtube_credentials,
)

COMMENT_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


def _format_md(date_str: str) -> str:
    from datetime import datetime

    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}月{dt.day}日"


def _normalize_comment_text(s: str) -> str:
    t = unicodedata.normalize("NFKC", s or "")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"[ \t　]+", " ", t)
    t = re.sub(r"\n+", "\n", t).strip()
    return t


def _get_total_articles_for_issue(issue_dir: Path) -> int:
    plan_path = issue_dir / "episodes_plan.json"
    if plan_path.exists():
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            total = plan.get("total_articles")
            if total is not None:
                return int(total)
        except Exception:
            pass
    episodes_dir = issue_dir / "episodes"
    if not episodes_dir.exists():
        return 0
    total = 0
    for ep_dir in sorted(episodes_dir.iterdir()):
        if not ep_dir.is_dir():
            continue
        meta_path = ep_dir / "metadata.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                total += int(meta.get("article_count", len(meta.get("articles", []))))
            except Exception:
                pass
    return total


def _get_episode_count_for_issue(issue_dir: Path) -> int:
    plan_path = issue_dir / "episodes_plan.json"
    if plan_path.exists():
        try:
            with open(plan_path, "r", encoding="utf-8") as f:
                plan = json.load(f)
            n = plan.get("episode_count")
            if n is not None:
                return max(0, int(n))
        except Exception:
            pass
    episodes_dir = issue_dir / "episodes"
    if not episodes_dir.exists():
        return 0
    return sum(
        1 for d in episodes_dir.iterdir() if d.is_dir() and d.name.isdigit()
    )


def _build_comment_body(
    issue_date: str,
    total_articles: int,
    episode_count: int,
    note_url: str,
) -> str:
    md = _format_md(issue_date)
    url = str(note_url).strip()
    lines = [
        f"「ザ・エコノミスト 」{md}号 から計{total_articles}篇の記事を厳選し"
        f"{episode_count}本の動画にまとめ、読み解いてまいります。",
        "全記事の一覧や各動画へのリンクは下記のページにまとめてあります。是非ご覧ください。",
        url,
    ]
    return "\n".join(lines)


def _iter_episode_metadata_paths(issue_dir: Path) -> list[Path]:
    episodes_dir = issue_dir / "episodes"
    if not episodes_dir.exists():
        return []
    out: list[Path] = []
    for ep_dir in sorted(episodes_dir.iterdir(), key=lambda d: d.name):
        if not ep_dir.is_dir() or not ep_dir.name.isdigit():
            continue
        p = ep_dir / "metadata.json"
        if p.exists():
            out.append(p)
    return out


def _load_video_rows(issue_dir: Path) -> list[tuple[str, str]]:
    """(episode_dir_name, video_id) のリスト。"""
    rows: list[tuple[str, str]] = []
    for meta_path in _iter_episode_metadata_paths(issue_dir):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            continue
        yt = meta.get("youtube") if isinstance(meta.get("youtube"), dict) else {}
        vid = str(yt.get("video_id", "")).strip()
        if not vid:
            continue
        rows.append((meta_path.parent.name, vid))
    return rows


def _get_my_channel_id(youtube) -> str:
    req = youtube.channels().list(part="id", mine=True)
    resp = req.execute()
    items = resp.get("items") or []
    if not items:
        raise RuntimeError("認証ユーザーのチャンネル ID を取得できませんでした。")
    cid = items[0].get("id")
    if not cid:
        raise RuntimeError("チャンネル ID が空です。")
    return str(cid)


def _author_channel_id(comment_snippet: dict[str, Any]) -> str | None:
    ac = comment_snippet.get("authorChannelId")
    if isinstance(ac, dict):
        v = ac.get("value")
        return str(v).strip() if v else None
    return None


def _existing_duplicate_note_comment(
    youtube,
    video_id: str,
    my_channel_id: str,
    note_url: str,
    expected_normalized: str,
) -> tuple[bool, str | None]:
    """自チャンネルのトップレベルコメントで、本文が一致するか note URL を含むなら重複とみなす。"""
    url_key = str(note_url).strip()
    page_token = None
    while True:
        req = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            maxResults=100,
            textFormat="plainText",
            pageToken=page_token,
        )
        resp = req.execute()
        for item in resp.get("items", []):
            sn = item.get("snippet") or {}
            top = sn.get("topLevelComment") or {}
            csn = top.get("snippet") or {}
            aid = _author_channel_id(csn)
            if aid != my_channel_id:
                continue
            raw = str(csn.get("textOriginal") or csn.get("textDisplay") or "")
            norm = _normalize_comment_text(raw)
            if norm == expected_normalized:
                return True, top.get("id")
            if url_key and url_key in raw:
                return True, top.get("id")
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return False, None


def _insert_top_level_comment(youtube, channel_id: str, video_id: str, text: str) -> dict[str, Any]:
    body = {
        "snippet": {
            "channelId": channel_id,
            "videoId": video_id,
            "topLevelComment": {"snippet": {"textOriginal": text}},
        }
    }
    return (
        youtube.commentThreads()
        .insert(part="snippet", body=body)
        .execute()
    )


def run_post_comments(
    issue_date: str,
    note_url: str,
    *,
    client_secrets_file: str | None = None,
    token_file: str | None = None,
    dry_run: bool = False,
) -> bool:
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as e:
        raise RuntimeError(
            "YouTube 依存ライブラリが不足しています。"
            " `pip install -r .cursor/skills/economist-podcast/requirements.txt` を実行してください。"
        ) from e

    issue_dir = get_issue_dir(issue_date)
    if not issue_dir.exists():
        print(f"[エラー] 号ディレクトリが見つかりません: {issue_dir}")
        return False

    nu = str(note_url).strip()
    if not nu.startswith(("http://", "https://")):
        print(f"[エラー] --note-url が有効な URL ではありません: {note_url!r}")
        return False

    total_articles = _get_total_articles_for_issue(issue_dir)
    episode_count = _get_episode_count_for_issue(issue_dir)
    body_text = _build_comment_body(issue_date, total_articles, episode_count, nu)
    expected_norm = _normalize_comment_text(body_text)

    rows = _load_video_rows(issue_dir)
    if not rows:
        print("[エラー] metadata に video_id があるエピソードがありません。")
        return False

    skill_root = Path(__file__).resolve().parent.parent
    cs = Path(client_secrets_file) if client_secrets_file else (skill_root / "youtube_client.json")
    tf = Path(token_file) if token_file else (skill_root / "youtube_token.json")
    ni = os.environ.get("YOUTUBE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")

    if dry_run:
        print("[dry-run] 以下のコメントを各動画に投稿する予定です。")
        print("---")
        print(body_text)
        print("---")
        for ep_name, vid in rows:
            print(f"  ep={ep_name}  video_id={vid}")
        print(
            "\n[注意] YouTube Data API v3 にはコメント固定の公式 API がありません。"
            " 投稿後は YouTube スタジオで手動固定してください。"
        )
        return True

    try:
        creds = obtain_youtube_credentials(
            cs,
            tf,
            non_interactive=ni,
            scopes=COMMENT_SCOPES,
        )
    except YouTubeAuthRequiredError as e:
        print(f"[エラー] {e}")
        return False

    youtube = build("youtube", "v3", credentials=creds)
    try:
        my_ch = _get_my_channel_id(youtube)
    except Exception as e:
        print(f"[エラー] {e}")
        return False

    print(
        f"[情報] issue={issue_date}  total_articles={total_articles}  "
        f"episodes={episode_count}  videos={len(rows)}"
    )
    ok_all = True
    for ep_name, video_id in rows:
        label = f"ep={ep_name} video_id={video_id}"
        try:
            dup, _cid = _existing_duplicate_note_comment(
                youtube,
                video_id,
                my_ch,
                nu,
                expected_norm,
            )
            if dup:
                print(f"[スキップ] {label}  既に同内容（または同一 note URL）の自チャンネルコメントがあります。")
                continue
            _insert_top_level_comment(youtube, my_ch, video_id, body_text)
            print(f"[OK] {label}  コメントを投稿しました。")
            print(
                "      → 固定: YouTube スタジオの該当動画ページで、今回のコメントを「ピン留め」してください。"
                "（Data API v3 非対応）"
            )
        except HttpError as e:
            print(f"[API エラー] {label}  {e}")
            ok_all = False
        except Exception as e:
            print(f"[エラー] {label}  {e}")
            ok_all = False

    return ok_all


def main() -> None:
    parser = argparse.ArgumentParser(
        description="metadata の video_id ごとに note 案内コメントを投稿する",
    )
    parser.add_argument("--issue", required=True, help="出版日 (YYYY-MM-DD)")
    parser.add_argument(
        "--note-url",
        required=True,
        help="note.com など一覧ページの URL",
    )
    parser.add_argument(
        "--client-secrets",
        default=None,
        help="OAuth client secrets JSON（省略時はスキル既定）",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="OAuth トークン（省略時はスキル既定）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼ばず本文と対象 video_id のみ表示",
    )
    args = parser.parse_args()
    ok = run_post_comments(
        args.issue,
        args.note_url,
        client_secrets_file=args.client_secrets,
        token_file=args.token_file,
        dry_run=args.dry_run,
    )
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

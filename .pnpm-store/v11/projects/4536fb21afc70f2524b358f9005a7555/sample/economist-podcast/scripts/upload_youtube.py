"""
YouTube アップロードモジュール

用途:
  - 指定した issue_date / episode_id の動画を YouTube にアップロードする
  - episode 01 の場合は当該号のプレイリストを新規作成する
  - サムネイルを設定し、可能ならプレイリストへ動画を追加する
  - 説明欄に Remotion 構成に沿った記事画面切替タイムスタンプを出力する

使用例:
  python upload_youtube.py --issue 2026-03-07 --episode 01
  python upload_youtube.py --issue 2026-03-07 --episode 02 --privacy unlisted
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from config import (
    SECTION_JP_MAPPING,
    get_issue_dir,
)
import text_llm

# OAuth スコープ: 動画アップロード・プレイリスト操作・サムネイル設定に必要
SCOPES = ["https://www.googleapis.com/auth/youtube"]

# Remotion 側（remotion/src/Composition.tsx）と同じ時間定数を使用
MAIN_COVER_SEC = 32
DISCLAIMER_SEC = 5
OVERVIEW_SEC_MIN = 60
OPEN_AUDIO_SEC = 39
OPEN_AUDIO_START_SEC = 1
ARTICLE_GAP_SEC = 8
# remotion/src/constants.ts と Composition.tsx の articleVisuals の丸めに合わせる
REMOTION_FPS = 30


def compute_youtube_visual_start_seconds(
    article_durations_sec: list[float],
    *,
    intro_duration_sec: float = 0.0,
    main_cover_sec: float = MAIN_COVER_SEC,
    disclaimer_sec: float = DISCLAIMER_SEC,
    overview_sec_default: float = OVERVIEW_SEC_MIN,
    fps: int = REMOTION_FPS,
) -> list[float]:
    """remotion/src/Composition.tsx の articleVisuals.from と同一（フレーム境界に丸めた秒）。

    第1記事: overviewEnd フレーム → 秒へ戻す。
    第2記事以降: Math.round(articleStartSecs[i] * fps) / fps
    """
    open_end_sec = OPEN_AUDIO_START_SEC + OPEN_AUDIO_SEC
    intro_start_sec = open_end_sec + 1
    intro_end_sec = intro_start_sec + max(0.0, intro_duration_sec)

    if intro_duration_sec > 0:
        overview_sec_min_from_intro = intro_end_sec - (main_cover_sec + disclaimer_sec)
    else:
        overview_sec_min_from_intro = 0.0
    overview_sec = max(overview_sec_default, overview_sec_min_from_intro)

    overview_end_frames = round((main_cover_sec + disclaimer_sec + overview_sec) * fps)

    current_article_start_sec = intro_end_sec + 1
    article_start_secs: list[float] = []
    for dur in article_durations_sec:
        dur_sec = max(float(dur or 0), 0.0)
        article_start_secs.append(current_article_start_sec)
        end_sec = current_article_start_sec + dur_sec
        current_article_start_sec = end_sec + ARTICLE_GAP_SEC

    n = len(article_durations_sec)
    out: list[float] = []
    for index in range(n):
        if index == 0:
            vf = overview_end_frames
        else:
            vf = round(article_start_secs[index] * fps)
        out.append(round(vf / fps, 1))
    return out


def compute_youtube_visual_starts_from_remotion_props(
    props: dict[str, Any],
    fps: int = REMOTION_FPS,
) -> list[float]:
    """episodes/XX/video/remotion_input.json の内容から章開始秒を算出する。"""
    articles = props.get("articles") or []
    durations = [float(a.get("durationSec", 0) or 0) for a in articles]

    intro_block = props.get("episodeIntroAudio") or {}
    intro_dur = float(intro_block.get("durationSec", 0) or 0)

    idur = props.get("introDurations") or {}
    mc = float(idur.get("mainCoverSec", MAIN_COVER_SEC) or MAIN_COVER_SEC)
    dis = float(idur.get("disclaimerSec", DISCLAIMER_SEC) or DISCLAIMER_SEC)
    ov_raw = idur.get("overviewSec")
    ov_default = float(ov_raw) if ov_raw is not None else float(OVERVIEW_SEC_MIN)

    return compute_youtube_visual_start_seconds(
        durations,
        intro_duration_sec=intro_dur,
        main_cover_sec=mc,
        disclaimer_sec=dis,
        overview_sec_default=ov_default,
        fps=fps,
    )


def compute_article_visual_switch_seconds(metadata: dict[str, Any]) -> list[float]:
    """remotion_input が無いときのみ。metadata の duration_sec / intro を使用。"""
    articles = metadata.get("articles") or []
    durations = [float(a.get("duration_sec", 0) or 0) for a in articles]
    intro_dur = float((metadata.get("intro") or {}).get("duration_sec", 0) or 0)
    return compute_youtube_visual_start_seconds(
        durations,
        intro_duration_sec=intro_dur,
        main_cover_sec=MAIN_COVER_SEC,
        disclaimer_sec=DISCLAIMER_SEC,
        overview_sec_default=float(OVERVIEW_SEC_MIN),
        fps=REMOTION_FPS,
    )


def resolve_youtube_visual_start_seconds(
    issue_date: str,
    episode_id: str,
    metadata: dict[str, Any],
) -> list[float]:
    """優先: video/remotion_input.json。無ければ metadata のみ。"""
    ep_id = str(episode_id).zfill(2)
    rpath = (
        get_issue_dir(issue_date) / "episodes" / ep_id / "video" / "remotion_input.json"
    )
    if rpath.exists():
        try:
            with open(rpath, "r", encoding="utf-8") as f:
                props = json.load(f)
            return compute_youtube_visual_starts_from_remotion_props(props)
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass
    return compute_article_visual_switch_seconds(metadata)


def build_youtube_video_title(issue_date: str, metadata: dict[str, Any]) -> str:
    """_build_video_title と同じロジック（API 不要）。"""
    md = _format_md(issue_date)
    sections = metadata.get("sections", [])[:2]
    labels = [SECTION_JP_MAPPING.get(s, s) for s in sections]
    section_text = "、".join(labels) if labels else "注目テーマ"
    return f"海外メディア「ザ・エコノミスト 」{md}号 {section_text}"


def build_youtube_sections_jp(metadata: dict[str, Any]) -> list[str]:
    return [SECTION_JP_MAPPING.get(s, s) for s in metadata.get("sections", [])]


def build_youtube_metadata_stub(
    issue_date: str,
    episode_id: str,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], list[float]]:
    """video_id / video_url は空文字、publish_at は None。
    duration はローカル episode MP4 があれば ffprobe。
    各記事の切り替え秒は video/remotion_input.json を優先し、Composition.tsx と同一ロジック。
    """
    ep_id = str(episode_id).zfill(2)
    issue_dir = get_issue_dir(issue_date)
    video_path = (
        issue_dir / "episodes" / ep_id / "video" / f"episode_{issue_date}_{ep_id}.mp4"
    )
    duration_sec = (
        _get_local_video_duration_sec(video_path) if video_path.exists() else 0.0
    )
    duration_iso = _sec_to_iso_duration(duration_sec) if duration_sec > 0 else ""

    article_start_secs = resolve_youtube_visual_start_seconds(
        issue_date, ep_id, metadata
    )
    youtube_block: dict[str, Any] = {
        "video_url": "",
        "video_id": "",
        "publish_at": None,
        "duration_sec": round(duration_sec, 1) if duration_sec > 0 else 0.0,
        "duration_iso": duration_iso,
        "title": build_youtube_video_title(issue_date, metadata),
        "sections_jp": build_youtube_sections_jp(metadata),
    }
    return youtube_block, article_start_secs


def apply_youtube_metadata_stub(
    issue_date: str,
    episode_id: str,
    *,
    preserve_existing_ids: bool = True,
) -> bool:
    """metadata.json に youtube スタブと各記事の youtube_start_* を書き込む。"""
    ep_id = str(episode_id).zfill(2)
    meta_path = get_issue_dir(issue_date) / "episodes" / ep_id / "metadata.json"
    if not meta_path.exists():
        print(f"[stub] スキップ（ファイルなし）: {meta_path}")
        return False
    with open(meta_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    yt_new, starts = build_youtube_metadata_stub(issue_date, ep_id, metadata)
    old = metadata.get("youtube") if isinstance(metadata.get("youtube"), dict) else {}
    if preserve_existing_ids and str(old.get("video_id", "")).strip():
        yt_new["video_id"] = str(old["video_id"]).strip()
        vu = str(old.get("video_url", "")).strip()
        yt_new["video_url"] = vu or f"https://youtu.be/{yt_new['video_id']}"
        if old.get("publish_at") is not None:
            yt_new["publish_at"] = old["publish_at"]
        if not yt_new["duration_sec"] and old.get("duration_sec"):
            yt_new["duration_sec"] = float(old["duration_sec"])
            yt_new["duration_iso"] = str(old.get("duration_iso", ""))
    metadata["youtube"] = yt_new
    for idx, art in enumerate(metadata.get("articles", [])):
        sec = starts[idx] if idx < len(starts) else 0.0
        art["youtube_start_sec"] = round(sec, 1)
        art["youtube_start_time"] = _sec_to_ts(sec)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    print(f"[stub] 更新しました: {meta_path}")
    return True


class YouTubeAuthRequiredError(Exception):
    """非対話モードでトークンが無効なため再認証できない場合に送出する。"""
    pass


def obtain_youtube_credentials(
    client_secrets_file: Path,
    token_file: Path,
    *,
    non_interactive: bool = False,
    scopes: list[str] | None = None,
):
    """YouTube API 用の有効な Credentials を返す。

    トークンファイルを読み、期限切れなら refresh_token で更新し、
    それでも無効なら（対話可なら）ブラウザで OAuth フローを実行する。
    更新・新規取得時は token_file に保存する。

    scopes:
        省略時はモジュール先頭の SCOPES（動画アップロード等）。
        コメント投稿など別メソッド用に force-ssl を追加する場合は明示してください。
    """
    try:
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise RuntimeError(
            "YouTube 依存ライブラリが不足しています。"
            " `pip install -r .cursor/skills/economist-podcast/requirements.txt` を実行してください。"
        ) from e

    if not client_secrets_file.exists():
        raise FileNotFoundError(
            f"client secrets ファイルが見つかりません: {client_secrets_file}"
        )

    want_scopes = scopes if scopes is not None else SCOPES

    def _token_file_has_scopes(tf: Path, required: list[str]) -> bool:
        """token JSON の scopes フィールドを直接読み、必要な scope が全て含まれるか判定する。"""
        try:
            raw = json.loads(tf.read_text(encoding="utf-8"))
            granted = raw.get("scopes") or []
            granted_set = {str(s).strip() for s in granted}
            return all(str(s).strip() in granted_set for s in required)
        except Exception:
            return False

    scope_missing = False
    if token_file.exists() and not _token_file_has_scopes(token_file, want_scopes):
        scope_missing = True
        print(
            f"[YouTube] 既存トークンに必要な scope が不足しています。再認証が必要です。"
            f"\n  必要: {want_scopes}"
        )

    creds = None
    if token_file.exists() and not scope_missing:
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), want_scopes)
        except Exception:
            creds = None

    need_save = False
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                need_save = True
            except RefreshError as e:
                err_msg = str(e).lower()
                if "invalid_grant" in err_msg or "expired" in err_msg or "revoked" in err_msg:
                    print("[YouTube] トークンが期限切れまたは無効です。再認証を行います。")
                    if token_file.exists():
                        token_file.unlink()
                    creds = None
                else:
                    raise
        if not creds or not creds.valid:
            if non_interactive:
                raise YouTubeAuthRequiredError(
                    "トークンが無効または期限切れです。"
                    " 手動で python upload_youtube.py --issue ... --episode ... を実行して再認証してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_file), want_scopes
            )
            creds = flow.run_local_server(port=0)
            need_save = True
        if need_save and creds:
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json(), encoding="utf-8")

    return creds


def ensure_youtube_oauth_at_workflow_start(
    client_secrets_file: str | Path | None = None,
    token_file: str | Path | None = None,
    *,
    non_interactive: bool = False,
) -> None:
    """ワークフロー開始時に OAuth を済ませ、長時間実行後のアップロード段階での期限切れを防ぐ。

    client_secrets / token の既定パスは YouTubeEpisodeUploader と同一（skill ルート直下）。
    """
    skill_root = Path(__file__).resolve().parent.parent
    cs = Path(client_secrets_file) if client_secrets_file else (skill_root / "youtube_client.json")
    tf = Path(token_file) if token_file else (skill_root / "youtube_token.json")
    ni = non_interactive or (
        os.environ.get("YOUTUBE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")
    )
    obtain_youtube_credentials(cs, tf, non_interactive=ni)
    print(
        "[YouTube] OAuth トークンを確認しました（ワークフロー先頭での事前認証）。",
        flush=True,
    )


def _format_md(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.month}月{dt.day}日"


def _format_issue_header(date_str: str) -> str:
    """号の表記用（例: ザ・エコノミスト　2026年3月7日号）"""
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"ザ・エコノミスト　{dt.year}年{dt.month}月{dt.day}日号"


def _sec_to_ts(sec: float) -> str:
    total = max(0, int(round(sec)))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_iso_duration(iso_dur: str) -> float:
    """YouTube API の duration (PT1H2M30S) を秒に変換する。"""
    if not iso_dur or not iso_dur.startswith("PT"):
        return 0.0
    total = 0.0
    for m in re.finditer(r"(\d+)([HMS])", iso_dur):
        n = int(m.group(1))
        u = m.group(2)
        if u == "H":
            total += n * 3600
        elif u == "M":
            total += n * 60
        else:
            total += n
    return total


def _sec_to_iso_duration(sec: float) -> str:
    """秒数を YouTube API 形式の ISO 8601 duration (PT1H2M30S) に変換する。"""
    total = max(0, int(round(sec)))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    parts = []
    if h:
        parts.append(f"{h}H")
    if m or parts:
        parts.append(f"{m}M")
    parts.append(f"{s}S")
    return "PT" + "".join(parts)


def _get_local_video_duration_sec(video_path: Path) -> float:
    """ローカル MP4 の総再生時間（秒）を ffprobe で取得する。失敗時は 0.0。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(video_path),
            ],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return max(0.0, float(result.stdout.strip()))
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        return 0.0


JST = timezone(timedelta(hours=9))
PUBLISH_WINDOW_START_HOUR = 14
PUBLISH_WINDOW_END_HOUR = 19
PUBLISH_INTERVAL_HOURS = 3


def _parse_youtube_publish_at(publish_str: str) -> datetime | None:
    """metadata.json の youtube.publish_at (ISO8601 UTC) を datetime に変換する。"""
    if not publish_str:
        return None
    try:
        time_str = publish_str.replace(".000Z", "").replace("Z", "")
        if "." in time_str:
            time_str = time_str.split(".")[0]
        return datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _load_episode_publish_at(issue_dir: Path, episode_id: str) -> datetime | None:
    """指定エピソード metadata.json から予約公開日時 (UTC) を読み取る。"""
    meta_path = issue_dir / "episodes" / str(episode_id).zfill(2) / "metadata.json"
    if not meta_path.exists():
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        publish_str = (meta.get("youtube") or {}).get("publish_at")
        return _parse_youtube_publish_at(publish_str) if publish_str else None
    except Exception:
        return None


def _adjust_publish_at_to_window(dt_utc: datetime) -> datetime:
    """JST 14:00–19:00 の公開枠内になるよう、必要なら翌日以降 14:00 へ繰り上げる。"""
    dt_jst = dt_utc.astimezone(JST)
    while True:
        day = dt_jst.replace(hour=0, minute=0, second=0, microsecond=0)
        window_start = day.replace(hour=PUBLISH_WINDOW_START_HOUR)
        window_end = day.replace(hour=PUBLISH_WINDOW_END_HOUR)
        if dt_jst < window_start:
            dt_jst = window_start
        if dt_jst <= window_end:
            return dt_jst.astimezone(timezone.utc)
        dt_jst = (day + timedelta(days=1)).replace(hour=PUBLISH_WINDOW_START_HOUR)


def _calculate_first_episode_publish_at(issue_date: str, now_utc: datetime | None = None) -> datetime:
    """第1話: JST 14:00–19:00 のみ考慮（前話との間隔は不要）。"""
    now_utc = now_utc or datetime.now(timezone.utc)
    now_jst = now_utc.astimezone(JST)
    try:
        issue_dt = datetime.strptime(issue_date, "%Y-%m-%d").replace(tzinfo=JST)
    except ValueError:
        issue_dt = now_jst.replace(hour=0, minute=0, second=0, microsecond=0)

    window_start = issue_dt.replace(
        hour=PUBLISH_WINDOW_START_HOUR, minute=0, second=0, microsecond=0
    )
    if now_jst < window_start:
        candidate_jst = window_start
    else:
        candidate_jst = now_jst + timedelta(minutes=15)
    return _adjust_publish_at_to_window(candidate_jst.astimezone(timezone.utc))


class YouTubeEpisodeUploader:
    def __init__(
        self,
        issue_date: str,
        episode_id: str,
        client_secrets_file: str | None = None,
        token_file: str | None = None,
        privacy_status: str = "private",
        schedule_publish_minutes: int = 30,
        non_interactive: bool = False,
    ):
        self.issue_date = issue_date
        self.episode_id = str(episode_id).zfill(2)
        self.issue_dir = get_issue_dir(issue_date)
        self.ep_dir = self.issue_dir / "episodes" / self.episode_id
        self.video_dir = self.ep_dir / "video"
        self.metadata_path = self.ep_dir / "metadata.json"

        skill_root = Path(__file__).resolve().parent.parent
        self.client_secrets_file = Path(
            client_secrets_file or (skill_root / "youtube_client.json")
        )
        self.token_file = Path(token_file or (skill_root / "youtube_token.json"))
        self.privacy_status = privacy_status
        self.schedule_publish_minutes = max(0, int(schedule_publish_minutes))
        self.non_interactive = non_interactive or (
            os.environ.get("YOUTUBE_NON_INTERACTIVE", "").lower() in ("1", "true", "yes")
        )

        self.youtube = None

    def _load_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.exists():
            raise FileNotFoundError(f"metadata.json が見つかりません: {self.metadata_path}")
        with open(self.metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _resolve_video_path(self) -> Path:
        video_path = self.video_dir / f"episode_{self.issue_date}_{self.episode_id}.mp4"
        if not video_path.exists():
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")
        return video_path

    def _resolve_thumbnail_path(self) -> Path | None:
        thumb_path = self.video_dir / f"thumbnail_{self.issue_date}_{self.episode_id}.jpg"
        if thumb_path.exists():
            return thumb_path
        # 拡張子違いにも対応
        for ext in ("png", "jpeg", "webp"):
            p = self.video_dir / f"thumbnail_{self.issue_date}_{self.episode_id}.{ext}"
            if p.exists():
                return p
        return None

    def _authenticate(self):
        try:
            from googleapiclient.discovery import build
        except ImportError as e:
            raise RuntimeError(
                "YouTube 依存ライブラリが不足しています。"
                " `pip install -r .cursor/skills/economist-podcast/requirements.txt` を実行してください。"
            ) from e

        creds = obtain_youtube_credentials(
            self.client_secrets_file,
            self.token_file,
            non_interactive=self.non_interactive,
        )
        self.youtube = build("youtube", "v3", credentials=creds)

    def _section_labels(self, metadata: dict[str, Any], limit: int = 2) -> list[str]:
        sections = metadata.get("sections", [])[:limit]
        return [SECTION_JP_MAPPING.get(s, s) for s in sections]

    def _episode_key_tags(self, metadata: dict[str, Any]) -> list[str]:
        raw = str(metadata.get("episode_key", "")).strip()
        if not raw:
            return []
        candidates = [x.strip() for x in raw.split(",") if x.strip()]
        # tags 全体は 500 文字制限があるため、余裕を持って切り詰める
        tags: list[str] = []
        total = 0
        for t in candidates:
            if len(t) > 30:
                t = t[:30]
            next_total = total + len(t)
            if tags:
                next_total += 1  # comma
            if next_total > 480:
                break
            tags.append(t)
            total = next_total
        return tags

    def _build_common_intro_line(self, metadata: dict[str, Any]) -> str:
        md = _format_md(self.issue_date)
        sections = self._section_labels(metadata, limit=2)
        section_text = "、".join(sections) if sections else "注目テーマ"
        article_count = int(metadata.get("article_count", len(metadata.get("articles", []))))
        return (
            f"イギリスが誇る世界のトップメディア『ザ・エコノミスト』{md}号"
            f"　{section_text}セクション計 {article_count}篇の記事をお届けします。"
        )

    def _build_video_title(self, metadata: dict[str, Any]) -> str:
        md = _format_md(self.issue_date)
        sections = self._section_labels(metadata, limit=2)
        section_text = "、".join(sections) if sections else "注目テーマ"
        return f"海外メディア「ザ・エコノミスト 」{md}号 {section_text}"

    def _build_playlist_title(self) -> str:
        return f"ザ・エコノミスト {self.issue_date}号"

    def _get_total_articles_for_issue(self) -> int:
        """当該号の全エピソードの記事数の合計を返す。episodes_plan.json 優先、なければ各 episode の metadata を合算。"""
        plan_path = self.issue_dir / "episodes_plan.json"
        if plan_path.exists():
            try:
                with open(plan_path, "r", encoding="utf-8") as f:
                    plan = json.load(f)
                total = plan.get("total_articles")
                if total is not None:
                    return int(total)
            except Exception:
                pass
        episodes_dir = self.issue_dir / "episodes"
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

    def _get_episode_count_for_issue(self) -> int:
        """当該号の総チャプター数（動画本数）。episodes_plan.json 優先、なければ episodes/ のサブディレクトリ数。"""
        plan_path = self.issue_dir / "episodes_plan.json"
        if plan_path.exists():
            try:
                with open(plan_path, "r", encoding="utf-8") as f:
                    plan = json.load(f)
                n = plan.get("episode_count")
                if n is not None:
                    return max(0, int(n))
            except Exception:
                pass
        episodes_dir = self.issue_dir / "episodes"
        if not episodes_dir.exists():
            return 0
        return sum(
            1
            for d in episodes_dir.iterdir()
            if d.is_dir() and d.name.isdigit()
        )

    def _build_playlist_description(self, metadata: dict[str, Any]) -> str:
        """プレイリストは全章を含むため、セクション情報は出さず、出版日・総記事数・動画本数のみ動的出力。"""
        md = _format_md(self.issue_date)
        total = self._get_total_articles_for_issue()
        episode_count = self._get_episode_count_for_issue()
        return (
            f"イギリスが誇る世界のトップメディア『ザ・エコノミスト』{md}号 計{total}篇の記事を"
            f"{episode_count}本の動画にまとめて深く読み解く。"
        )

    def _compute_article_visual_switch_seconds(self, metadata: dict[str, Any]) -> list[float]:
        return resolve_youtube_visual_start_seconds(
            self.issue_date, self.episode_id, metadata
        )

    def _build_video_description(self, metadata: dict[str, Any]) -> str:
        intro_line = self._build_common_intro_line(metadata)
        articles = metadata.get("articles", [])
        switch_secs = self._compute_article_visual_switch_seconds(metadata)

        lines: list[str] = []
        lines.append(intro_line)
        lines.append("")
        lines.append("00:00 オープンニング")

        for idx, article in enumerate(articles):
            ts = _sec_to_ts(switch_secs[idx] if idx < len(switch_secs) else 0)
            one_line = str(article.get("one_line_intro", "")).strip()
            if not one_line:
                one_line = str(article.get("japanese_title", "")).strip() or f"{idx + 1}記事目"
            lines.append(f"{ts} {one_line}")

        lines.append("")
        lines.append(
            "グローバル・クリップは海外のトップメディアから知るべき『情報のエッセンス』を厳選し、"
            "深く読み解きます。忖度のない多角的な視点で、"
            "世界のリアルをお届けします。"
        )
        lines.append("")
        lines.append("『ザ・エコノミスト』")
        lines.append(
            "イギリスが誇る新聞週刊誌、単なる経済誌の枠を超え、"
            "最新AIから国際情勢の裏側まで、地球の『今』を網羅した極上の知性をお届けします。"
        )
        return "\n".join(lines)

    def _resolve_news_category_id(self) -> str:
        # 既定値: News & Politics
        default_id = "25"
        try:
            req = self.youtube.videoCategories().list(part="snippet", regionCode="JP")
            resp = req.execute()
            for item in resp.get("items", []):
                sn = item.get("snippet", {})
                title = sn.get("title", "")
                if title in ("ニュースと政治", "News & Politics"):
                    return item.get("id", default_id)
        except Exception:
            pass
        return default_id

    def _insert_playlist(self, metadata: dict[str, Any]) -> str:
        body = {
            "snippet": {
                "title": self._build_playlist_title(),
                "description": self._build_playlist_description(metadata),
                "defaultLanguage": "ja",
            },
            "status": {"privacyStatus": "public"},
        }
        req = self.youtube.playlists().insert(part="snippet,status", body=body)
        resp = req.execute()
        return resp["id"]

    def _find_playlist_by_title(self, title: str) -> str | None:
        page_token = None
        while True:
            req = self.youtube.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50,
                pageToken=page_token,
            )
            resp = req.execute()
            for item in resp.get("items", []):
                if item.get("snippet", {}).get("title") == title:
                    return item.get("id")
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return None

    def _calculate_publish_at(self) -> datetime | None:
        """
        予約公開日時 (UTC):
          - 第1話: JST 14:00–19:00 のみ（号日 14:00 以前なら 14:00、以降なら現在+15分を枠内に調整）
          - 第2話以降: 直前話の公開時刻 + 3 時間を JST 14:00–19:00 に収める
        """
        now_utc = datetime.now(timezone.utc)
        try:
            ep_num = int(self.episode_id)
        except ValueError:
            ep_num = 1

        if ep_num == 1:
            return _calculate_first_episode_publish_at(self.issue_date, now_utc)

        prev_publish_at: datetime | None = None
        for i in range(1, ep_num):
            ep_id = f"{i:02d}"
            loaded = _load_episode_publish_at(self.issue_dir, ep_id)
            if loaded is not None:
                prev_publish_at = loaded
            elif prev_publish_at is None:
                prev_publish_at = _calculate_first_episode_publish_at(self.issue_date, now_utc)
            else:
                prev_publish_at = _adjust_publish_at_to_window(
                    prev_publish_at + timedelta(hours=PUBLISH_INTERVAL_HOURS)
                )

        if prev_publish_at is None:
            prev_publish_at = _calculate_first_episode_publish_at(self.issue_date, now_utc)

        return _adjust_publish_at_to_window(
            prev_publish_at + timedelta(hours=PUBLISH_INTERVAL_HOURS)
        )

    def _upload_video(self, metadata: dict[str, Any], video_path: Path) -> str:
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as e:
            raise RuntimeError(
                "YouTube 依存ライブラリが不足しています。"
                " `pip install -r .cursor/skills/economist-podcast/requirements.txt` を実行してください。"
            ) from e

        category_id = self._resolve_news_category_id()
        status: dict[str, Any] = {"privacyStatus": self.privacy_status}
        if self.schedule_publish_minutes > 0:
            status["privacyStatus"] = "private"
            publish_at = self._calculate_publish_at()
            if publish_at:
                status["publishAt"] = publish_at.strftime("%Y-%m-%dT%H:%M:%S.000Z")
                jst_str = publish_at.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S JST")
                print(f"[YouTube] 予約公開日時を設定: {jst_str}")
        body = {
            "snippet": {
                "title": self._build_video_title(metadata),
                "description": self._build_video_description(metadata),
                "tags": self._episode_key_tags(metadata),
                "categoryId": category_id,
                "defaultLanguage": "ja",
                "defaultAudioLanguage": "ja",
            },
            "status": status,
        }
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
        req = self.youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            _, response = req.next_chunk()
        return response["id"]

    def _set_thumbnail(self, video_id: str, thumbnail_path: Path):
        try:
            from googleapiclient.http import MediaFileUpload
        except ImportError as e:
            raise RuntimeError(
                "YouTube 依存ライブラリが不足しています。"
                " `pip install -r .cursor/skills/economist-podcast/requirements.txt` を実行してください。"
            ) from e

        media = MediaFileUpload(str(thumbnail_path), mimetype="image/jpeg")
        self.youtube.thumbnails().set(videoId=video_id, media_body=media).execute()

    def _add_video_to_playlist(self, playlist_id: str, video_id: str):
        body = {
            "snippet": {
                "playlistId": playlist_id,
                "resourceId": {"kind": "youtube#video", "videoId": video_id},
            }
        }
        self.youtube.playlistItems().insert(part="snippet", body=body).execute()

    def _get_video_details(self, video_id: str) -> dict[str, Any]:
        """アップロード後の動画の contentDetails（duration）と status（publishAt）を取得する。"""
        req = self.youtube.videos().list(
            id=video_id,
            part="contentDetails,status",
        )
        resp = req.execute()
        items = resp.get("items", [])
        if not items:
            return {}
        item = items[0]
        content = item.get("contentDetails", {})
        status = item.get("status", {})
        duration_iso = content.get("duration", "") or ""
        return {
            "duration_iso": duration_iso,
            "duration_sec": _parse_iso_duration(duration_iso),
            "publish_at": status.get("publishAt"),  # 予約公開時のみ存在
        }

    def _update_metadata_youtube(
        self,
        metadata: dict[str, Any],
        video_id: str,
        video_title: str,
        publish_at: str | None,
        duration_sec: float,
        duration_iso: str,
        sections_jp: list[str],
        article_start_secs: list[float],
    ) -> None:
        """アップロード完了後、episode の metadata.json に YouTube 情報を追記する。"""
        video_url = f"https://youtu.be/{video_id}"
        youtube_block: dict[str, Any] = {
            "video_url": video_url,
            "video_id": video_id,
            "publish_at": publish_at,
            "duration_sec": round(duration_sec, 1),
            "duration_iso": duration_iso,
            "title": video_title,
            "sections_jp": sections_jp,
        }
        metadata["youtube"] = youtube_block
        articles = metadata.get("articles", [])
        for idx, art in enumerate(articles):
            start_sec = article_start_secs[idx] if idx < len(article_start_secs) else 0.0
            art["youtube_start_sec"] = round(start_sec, 1)
            art["youtube_start_time"] = _sec_to_ts(start_sec)
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        print(f"[YouTube] metadata.json を更新しました: {self.metadata_path}")

    def _is_last_episode(self) -> bool:
        """当該エピソードが当該号の最終章かどうかを返す。"""
        plan_path = self.issue_dir / "episodes_plan.json"
        if plan_path.exists():
            try:
                with open(plan_path, "r", encoding="utf-8") as f:
                    plan = json.load(f)
                last_num = int(plan.get("episode_count", 0))
                return int(self.episode_id) >= last_num
            except Exception:
                pass
        episodes_dir = self.issue_dir / "episodes"
        if not episodes_dir.exists():
            return True
        ep_dirs = sorted(d.name for d in episodes_dir.iterdir() if d.is_dir() and d.name.isdigit())
        return ep_dirs and self.episode_id == ep_dirs[-1]

    def _generate_post_intro(self) -> str:
        """Episode 01 の第1・第2記事（今週の世界）から、日本人の関心を引く導入文を PRO モデルで生成（100〜200字）。"""
        ep01_dir = self.issue_dir / "episodes" / "01"
        meta_path = ep01_dir / "metadata.json"
        if not meta_path.exists():
            return ""
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except Exception:
            return ""
        articles = meta.get("articles", [])[:2]
        if len(articles) < 2:
            return ""
        art1 = articles[0]
        art2 = articles[1]
        title1 = str(art1.get("japanese_title", "")).strip()
        title2 = str(art2.get("japanese_title", "")).strip()
        summary1 = str(art1.get("summary_ja", "")).strip()[:500]
        summary2 = str(art2.get("summary_ja", "")).strip()[:500]
        if not text_llm.is_configured():
            return ""
        try:
            prompt = (
                "あなたは日本のニュース解説ポッドキャストのプロデューサーです。\n\n"
                "以下の2本の記事（『ザ・エコノミスト』今週の世界：政治・ビジネス）の内容を踏まえ、"
                "日本人の大衆心理に訴えかけ、動画番組への視聴意欲を高める導入文を書いてください。\n\n"
                "【条件】\n"
                "- 100字以上200字以内\n"
                "- 日本人が最も関心を持つ話題を抽出し、引き込まれる書き出しにする\n"
                "- 余計な説明や改行は不要。導入文のみ1行で出力\n\n"
                f"【記事1】{title1}\n{summary1}\n\n"
                f"【記事2】{title2}\n{summary2}"
            )
            intro = text_llm.generate_text(prompt, tier="pro").strip()[:250]
            if 50 <= len(intro) <= 250:
                return intro
        except Exception as e:
            print(f"[投稿] 導入文生成失敗: {e}")
        return ""

    def _build_post_content(self) -> str:
        """全エピソードの情報を集め、投稿用テキストを構築する。"""
        header = _format_issue_header(self.issue_date)
        intro = self._generate_post_intro()
        lines: list[str] = [header, ""]
        if intro:
            lines.append(intro)
            lines.append("")
        lines.append("【各章の内容】")
        lines.append("")
        episodes_dir = self.issue_dir / "episodes"
        if not episodes_dir.exists():
            return "\n".join(lines)
        for ep_dir in sorted(episodes_dir.iterdir(), key=lambda d: d.name):
            if not ep_dir.is_dir() or not ep_dir.name.isdigit():
                continue
            meta_path = ep_dir / "metadata.json"
            if not meta_path.exists():
                continue
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                continue
            yt = meta.get("youtube", {})
            title = str(yt.get("title", "")).strip()
            if not title:
                title = self._build_video_title(meta)
            lines.append(f"■ {title}")
            articles = meta.get("articles", [])
            for idx, art in enumerate(articles, 1):
                jp_title = str(art.get("japanese_title", "")).strip()
                if not jp_title:
                    jp_title = str(art.get("one_line_intro", "")).strip() or "記事"
                lines.append(f"  {idx}. {jp_title}")
            video_url = str(yt.get("video_url", "")).strip()
            if video_url:
                lines.append(f"  {video_url}")
            lines.append("")
        return "\n".join(lines).rstrip()

    def _run_post_upload_publish(self) -> None:
        """最終章アップロード完了後、投稿用テキストを生成して出力する。"""
        content = self._build_post_content()
        out_path = self.issue_dir / "post_content.txt"
        try:
            out_path.write_text(content, encoding="utf-8")
            print(f"[投稿] 投稿用テキストを保存しました: {out_path}")
        except OSError as e:
            print(f"[投稿] ファイル保存失敗: {e}")
        print("\n" + "=" * 60)
        print("[投稿] 生成された投稿内容:")
        print("=" * 60)
        print(content)
        print("=" * 60)

    def run(self) -> bool:
        try:
            from googleapiclient.errors import HttpError
        except ImportError:
            HttpError = Exception

        try:
            metadata = self._load_metadata()
            video_path = self._resolve_video_path()
            thumbnail_path = self._resolve_thumbnail_path()
            self._authenticate()

            playlist_id = None
            playlist_title = self._build_playlist_title()
            if self.episode_id == "01":
                print(f"[YouTube] Episode 01 のため新規プレイリストを作成します: {playlist_title}")
                playlist_id = self._insert_playlist(metadata)
            else:
                playlist_id = self._find_playlist_by_title(playlist_title)
                if not playlist_id:
                    print(f"[YouTube][警告] プレイリストが見つかりません。追加をスキップします: {playlist_title}")

            print(f"[YouTube] 動画をアップロード中: {video_path.name}")
            video_id = self._upload_video(metadata, video_path)
            print(f"[YouTube] アップロード完了: videoId={video_id}")

            # アップロード直後に metadata を書き込む（サムネ・プレイリストより先）。
            # サムネ/プレイリストで例外が出ても動画は既に YouTube 上にあるため、
            # 先に永続化しておかないと episode_progress だけ完了扱いになり得る不整合を防ぐ。
            # orchestrate の tail ワーカー単体でもここで完結する。
            try:
                details = self._get_video_details(video_id)
            except Exception as de:
                print(
                    f"[YouTube][警告] 動画詳細取得に失敗しました。"
                    f" ローカル長さで metadata を更新します: {de}"
                )
                details = {}
            local_duration_sec = _get_local_video_duration_sec(video_path)
            if local_duration_sec > 0:
                duration_sec = local_duration_sec
                duration_iso = _sec_to_iso_duration(local_duration_sec)
            else:
                duration_sec = details.get("duration_sec", 0.0)
                duration_iso = details.get("duration_iso", "")
            publish_at = details.get("publish_at")
            video_title = self._build_video_title(metadata)
            sections_jp = [
                SECTION_JP_MAPPING.get(s, s)
                for s in metadata.get("sections", [])
            ]
            article_start_secs = self._compute_article_visual_switch_seconds(metadata)
            self._update_metadata_youtube(
                metadata,
                video_id=video_id,
                video_title=video_title,
                publish_at=publish_at,
                duration_sec=duration_sec,
                duration_iso=duration_iso,
                sections_jp=sections_jp,
                article_start_secs=article_start_secs,
            )

            if thumbnail_path:
                print(f"[YouTube] サムネイルを設定中: {thumbnail_path.name}")
                try:
                    self._set_thumbnail(video_id, thumbnail_path)
                except Exception as te:
                    print(
                        f"[YouTube][警告] サムネイル設定に失敗しました（metadata は既に更新済み）: {te}"
                    )
            else:
                print("[YouTube][警告] サムネイル画像が見つからないため設定をスキップしました。")

            if playlist_id:
                print(f"[YouTube] プレイリストに追加中: playlistId={playlist_id}")
                try:
                    self._add_video_to_playlist(playlist_id, video_id)
                except Exception as pe:
                    print(
                        f"[YouTube][警告] プレイリスト追加に失敗しました（metadata は既に更新済み）: {pe}"
                    )

            if self._is_last_episode():
                print("[YouTube] 最終章のアップロード完了。投稿用テキストを生成します。")
                self._run_post_upload_publish()

            print("[YouTube] 処理が完了しました。")
            return True
        except YouTubeAuthRequiredError as e:
            print(f"[YouTube][エラー] {e}")
            return False
        except HttpError as e:
            print(f"[YouTube][エラー] API エラー: {e}")
            return False
        except Exception as e:
            print(f"[YouTube][エラー] {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="YouTube に指定エピソードをアップロードする")
    parser.add_argument("--issue", required=True, help="出版日 (YYYY-MM-DD)")
    parser.add_argument("--episode", required=True, help="エピソードID (例: 01)")
    parser.add_argument(
        "--client-secrets",
        default=None,
        help="OAuth client secrets JSON のパス（省略時は skill 既定値）",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="OAuth トークン保存先（省略時は skill 既定値）",
    )
    parser.add_argument(
        "--privacy",
        default=os.getenv("YOUTUBE_PRIVACY_STATUS", "private"),
        choices=["private", "unlisted", "public"],
        help="YouTube 公開設定（予約公開時は private に上書き）",
    )
    parser.add_argument(
        "--schedule-minutes",
        type=int,
        default=30,
        metavar="MIN",
        help="アップロード後、指定分数経過で自動公開する（0 で予約なし、既定 30）",
    )
    parser.add_argument(
        "--no-schedule",
        action="store_true",
        help="予約公開しない（--schedule-minutes 0 と同じ）",
    )
    parser.add_argument(
        "--post-only",
        action="store_true",
        help="アップロードせず、投稿用テキストのみ生成する（全章アップロード済み時用）",
    )
    args = parser.parse_args()
    schedule_minutes = 0 if args.no_schedule else max(0, args.schedule_minutes)

    uploader = YouTubeEpisodeUploader(
        issue_date=args.issue,
        episode_id=args.episode,
        client_secrets_file=args.client_secrets,
        token_file=args.token_file,
        privacy_status=args.privacy,
        schedule_publish_minutes=schedule_minutes,
    )
    if args.post_only:
        uploader._run_post_upload_publish()
        raise SystemExit(0)
    ok = uploader.run()
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

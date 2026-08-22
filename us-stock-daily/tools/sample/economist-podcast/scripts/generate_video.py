"""
Remotion 用データ準備モジュール
各エピソードのメタデータ・音声・挿絵をもとに remotion/public/ へアセット注入し、
video/remotion_input.json と public/remotion_input.json を書き出す。

実際の MP4 レンダリングは orchestrate.py の render_video サブステップ（npx remotion render）が担当する。
本モジュールは npx / Remotion CLI を起動しない。

前提:
  - remotion/ は git 管理。src/ にテンプレート、根に Remotion 設定。
  - remotion/public/ は毎回 generate_video が注入: 先に中身を全削除し、
    共通チャンネル用アセットと当該エピソード用アセット・remotion_input.json をコピーする。

動画の構成（remotion/src/Composition.tsx と同期）:
  - 冒頭: メインカバー → Disclaimer → EpisodeOverview（画面）
    - メインカバー: チャンネルロゴ・「ザ・エコノミスト YYYY-MM-DD」・注目記事4篇・セクションラベル。右側は当該エピソードに is_cover_story の記事があり号に cover 画像があるとき雑誌表紙、それ以外は先頭記事（最小 order）の挿絵＋ロゴ。
    - EpisodeOverview の表示長は動的: intro がある場合は intro 終了まで（最低 OVERVIEW_SEC=60）。intro なしは introDurations.overviewSec または 60 秒。
  - 音声・画面の時間軸（すべて動的）:
    - open.mp3: 1 秒地点から再生（39 秒）。共通アセット。
    - intro.mp3: open 終了 + 1 秒から。episodeIntroAudio.durationSec で長さ指定。assets/{date}/{ep}/intro.mp3。
    - 記事音声（audio_01.mp3 等）: intro 終了 + 1 秒から、記事間は GAP_SEC=8 秒。
    - closing.mp3: 最後の記事終了 + 1 秒から。episodeClosingAudio.durationSec。assets/{date}/{ep}/closing.mp3。
    - end.mp3: closing 終了 + 0.5 秒から（28 秒）。共通アセット。その終了 + 1 秒で動画終了。
  - 動画総長: calcTotalFrames(articles, introDurationSec, closingDurationSec) で算出（open → intro → articles → closing → end）。
  - 末尾画面:
    - EpisodeOverview Reprise: closing.mp3 と同時開始（最後の記事終了 + 1 秒）。終了は Ending 開始と一致。
    - Ending 画面: 動画終了 16 秒前から表示（ENDING_DISPLAY_SEC=16）。
  - 末尾 BGM: bgm_openning.mp3 の最後 30 秒を動画終了 30 秒前から再生（フェードイン付き）。アセットの総長は Composition.tsx の OPENING_BGM_TOTAL_SEC で要調整。
"""
import json
import subprocess
import shutil
import argparse
from pathlib import Path

from config import get_issue_dir, SECTION_JP_MAPPING, PROJECT_ROOT
from state_manager import StateManager

# Remotion プロジェクトとチャンネルアセットのパス（プロジェクトルート直下）
REMOTION_DIR = PROJECT_ROOT / "remotion"
CHANNEL_DIR = PROJECT_ROOT / "channel"

TOP_ARTICLES_COUNT = 4
SECTION_LABELS_COUNT = 2


def _truthy_is_cover_story(article: dict) -> bool:
    """metadata.json の is_cover_story を真偽として解釈する。"""
    v = article.get("is_cover_story", False)
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes")
    return bool(v)


def _episode_has_cover_story(metadata: dict) -> bool:
    return any(_truthy_is_cover_story(a) for a in metadata.get("articles", []))


def _min_article_order(metadata: dict) -> int:
    orders: list[int] = []
    for a in metadata.get("articles", []):
        if a.get("order") is not None:
            orders.append(int(a["order"]))
    return min(orders) if orders else 1


def _get_audio_duration_sec(audio_path: Path) -> float:
    """ffprobe で音声ファイルの長さ（秒）を取得する。失敗時は 0.0。

    metadata.json に duration_sec が無い／0 の場合でも Remotion のタイムラインを
    実ファイルに合わせるために使う（generate_audio 経由で未更新のエピソード対策）。
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=120,
        )
        return max(0.0, float(result.stdout.strip()))
    except Exception:
        return 0.0


# Intro timing (must be kept in sync with remotion/src/Composition.tsx defaults)
# 全エピソードで episode id=1 と同じ設定を使用（MainCover 32s, Disclaimer 5s, Overview 60s）
MAIN_COVER_SEC_DEFAULT = 32
DISCLAIMER_SEC_DEFAULT = 5
OVERVIEW_SEC_DEFAULT = 60


class VideoGenerator:
    """動画生成クラス"""

    def __init__(
        self, issue_date: str, episode_id: str | None = None, render: bool = False
    ):
        self.issue_date = issue_date
        self.episode_id = episode_id
        # render は orchestrate 等の既存呼び出し互換用。本モジュールは常に準備のみ（レンダリングしない）。
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)

    def _ensure_remotion_dir(self) -> bool:
        """Remotion プロジェクトが存在するか確認する（テンプレートのコピーは行わない）"""
        if not REMOTION_DIR.exists():
            print(f"[エラー] Remotion プロジェクトが見つかりません: {REMOTION_DIR}")
            print("    remotion/ は git で管理されています。リポジトリを確認してください。")
            return False
        return True

    def _clean_public_dir(self) -> None:
        """remotion/public/ の内容をすべて削除する。プレビュー・レンダリング用に毎回 generate_video が注入する前提。"""
        public_dir = REMOTION_DIR / "public"
        if not public_dir.exists():
            return
        for item in public_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink()
                    print(f"    [クリア] {item.name}")
                else:
                    shutil.rmtree(item)
                    print(f"    [クリア] {item.name}/")
            except Exception as e:
                print(f"    [警告] 削除失敗 {item}: {e}")

    def _copy_channel_assets(self) -> None:
        """チャンネル共通アセットを remotion/public/ にコピーする（更新がある場合のみ）"""
        public_dir = REMOTION_DIR / "public"
        public_dir.mkdir(parents=True, exist_ok=True)

        assets = {
            "channel_logo.png": CHANNEL_DIR / "global_clip_logo_no_word.png",
            "logo_red.svg": CHANNEL_DIR / "logo-red.svg",
        }
        for dst_name, src_path in assets.items():
            dst_path = public_dir / dst_name
            # ファイルが存在しない、または更新されている場合のみコピー
            if src_path.exists() and (
                not dst_path.exists()
                or src_path.stat().st_mtime > dst_path.stat().st_mtime
            ):
                shutil.copy2(src_path, dst_path)
                print(f"    チャンネルアセットをコピー: {dst_name}")

    def _copy_bgm_assets(self) -> None:
        """Remotion で使用する BGM を remotion/public/ にコピーする。

        - bgm_openning.mp3
        - bgm_break.mp3
        - open.mp3（全エピソード共通のオープニング）
        - end.mp3（全エピソード共通のエンディング）
        """
        public_dir = REMOTION_DIR / "public"
        public_dir.mkdir(parents=True, exist_ok=True)

        # このスキル配下の assests ディレクトリ（綴りは既存構成に合わせる）
        skill_root = Path(__file__).resolve().parent.parent
        bgm_dir = skill_root / "assests"

        bgm_files = {
            "bgm_openning.mp3": bgm_dir / "bgm_openning.mp3",
            "bgm_break.mp3": bgm_dir / "bgm_break.mp3",
            "open.mp3": bgm_dir / "open.mp3",
            "end.mp3": bgm_dir / "end.mp3",
        }

        for dst_name, src_path in bgm_files.items():
            if not src_path.exists():
                print(f"    [警告] BGM ファイルが見つかりません: {src_path}")
                continue
            dst_path = public_dir / dst_name
            if not dst_path.exists() or src_path.stat().st_mtime > dst_path.stat().st_mtime:
                shutil.copy2(src_path, dst_path)
                print(f"    BGM アセットをコピー: {dst_name}")

    def _copy_audio_to_public(self, audio_files: list[Path]) -> list[str]:
        """音声ファイルをRemotionのpublic/にコピーし、ファイル名リストを返す"""
        public_dir = REMOTION_DIR / "public"
        public_dir.mkdir(parents=True, exist_ok=True)
        
        copied_filenames = []
        for i, src in enumerate(audio_files):
            # audio_01.mp3 のような形式にリネーム
            # 元ファイル名が数字のみ(01.mp3)を想定
            stem = src.stem  # "01"
            try:
                # 数字のみの場合は audio_XX.mp3 にする
                num = int(stem)
                dst_name = f"audio_{num:02d}.mp3"
            except ValueError:
                # 数字以外ならそのまま audio_prefix
                dst_name = f"audio_{src.name}"
            
            dst_path = public_dir / dst_name
            shutil.copy2(src, dst_path)
            copied_filenames.append(dst_name)
            
        return copied_filenames

    def _copy_to_public(self, src: Path, assets_subdir: str) -> str | None:
        """ファイルをRemotionのpublic/assets/にコピーし、staticFile用の相対パスを返す。

        Returns:
            "assets/{subdir}/{filename}" 形式の文字列。Remotion側で staticFile() に渡す。
            ファイルが存在しない場合は None。
        """
        if not src.exists():
            return None
        
        # public/assets/{date}/{ep}/filename
        public_assets_dir = REMOTION_DIR / "public" / "assets" / assets_subdir
        public_assets_dir.mkdir(parents=True, exist_ok=True)
        
        dst = public_assets_dir / src.name
        shutil.copy2(src, dst)
        
        # Windowsパスのバックスラッシュをスラッシュに変換（Remotion/Web用）
        rel_path = f"assets/{assets_subdir}/{src.name}"
        return rel_path

    def _copy_first_article_image(
        self, images_dir: Path, first_order: int, assets_subdir: str
    ) -> str | None:
        """最小 order の記事の挿絵を public にコピーし相対パスを返す（拡張子は png→jpg→jpeg→webp）。"""
        base = f"{int(first_order):02d}"
        for ext in ("png", "jpg", "jpeg", "webp"):
            rel = self._copy_to_public(images_dir / f"{base}.{ext}", assets_subdir)
            if rel:
                return rel
        return None

    def _validate_episode_assets(self, ep_dir: Path, metadata: dict) -> bool:
        """metadata.json の記事リストをもとに、audio/ と images/ のファイル有無をチェックする。

        - audio/{order:02d}.mp3 または .wav が全記事分存在すること
        - images/{order:02d}.png / .jpg / .jpeg / .webp のいずれかが全記事分存在すること
        いずれか不足していればエラーを表示して False を返し、Remotion 用出力は行わない。
        """
        articles = metadata.get("articles", [])
        audio_dir = ep_dir / "audio"
        images_dir = ep_dir / "images"

        ok = True

        if not audio_dir.exists():
            print(f"[エラー] 音声ディレクトリが見つかりません: {audio_dir}")
            ok = False
        if not images_dir.exists():
            print(f"[エラー] 画像ディレクトリが見つかりません: {images_dir}")
            ok = False
        if not ok:
            return False

        missing_audio: list[str] = []
        missing_images: list[str] = []

        for article in articles:
            order = article.get("order")
            if order is None:
                continue
            base = f"{int(order):02d}"

            # 音声ファイルチェック
            audio_candidates = [
                audio_dir / f"{base}.mp3",
                audio_dir / f"{base}.wav",
            ]
            if not any(p.exists() for p in audio_candidates):
                missing_audio.append(base)

            # 画像ファイルチェック（拡張子は複数許容）
            image_candidates = [
                images_dir / f"{base}.png",
                images_dir / f"{base}.jpg",
                images_dir / f"{base}.jpeg",
                images_dir / f"{base}.webp",
            ]
            if not any(p.exists() for p in image_candidates):
                missing_images.append(base)

        if missing_audio:
            print(f"[エラー] 次の記事の音声ファイルが不足しています（audio ディレクトリを確認してください）: {', '.join(missing_audio)}")
            ok = False
        if missing_images:
            print(f"[エラー] 次の記事の画像ファイルが不足しています（images ディレクトリを確認してください）: {', '.join(missing_images)}")
            ok = False

        return ok

    def _prepare_video_metadata(self, ep_dir: Path) -> dict | None:
        """Remotion 用メタデータを準備する（プレビュー・レンダリングの単一ソース）。

        - 画像・音声パスはすべて public/ からの相対パス（Remotion 側で staticFile() 使用）。
        - メインカバー: エピソード内に is_cover_story の記事があり号に cover 画像がある → 雑誌表紙。それ以外 → 先頭記事（最小 order）の挿絵＋ロゴ。
        - 注目記事は relevance_score 上位 TOP_ARTICLES_COUNT 件、セクションラベルは前 SECTION_LABELS_COUNT 個の日本語名。
        """
        metadata_path = ep_dir / "metadata.json"
        if not metadata_path.exists():
            return None

        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        # 音声・画像ファイルが揃っているか事前に検証し、不足があればここで中断する
        if not self._validate_episode_assets(ep_dir, metadata):
            return None

        assets_subdir = f"{self.issue_date}/{ep_dir.name}"

        # --- 音声ファイルの収集とコピー ---
        audio_dir = ep_dir / "audio"
        audio_files_src: list[Path] = []
        article_order_to_src: dict[int, Path] = {}
        # 記事本文用のトラックだけを対象にする（intro.mp3 / closing.mp3 などは除外）
        for article in metadata.get("articles", []):
            order = article.get("order")
            if order is None:
                continue
            o = int(order)
            base = f"{o:02d}"
            candidates = [
                audio_dir / f"{base}.mp3",
                audio_dir / f"{base}.wav",
            ]
            src = next((p for p in candidates if p.exists()), None)
            if src is not None:
                audio_files_src.append(src)
                article_order_to_src[o] = src

        # 記事用音声を public/audio_XX.mp3 にコピーし、そのファイル名リストを取得
        audio_filenames = self._copy_audio_to_public(audio_files_src)

        images_dir = ep_dir / "images"

        # --- エピソード固有の intro / closing 音声（任意） ---
        intro_info = metadata.get("intro") or {}
        closing_info = metadata.get("closing") or {}

        intro_audio_rel = None
        closing_audio_rel = None
        intro_duration_sec = float(intro_info.get("duration_sec", 0.0) or 0.0)
        closing_duration_sec = float(closing_info.get("duration_sec", 0.0) or 0.0)

        if audio_dir.exists():
            intro_src = audio_dir / "intro.mp3"
            if intro_src.exists():
                intro_audio_rel = self._copy_to_public(intro_src, assets_subdir)
                if intro_duration_sec <= 0:
                    intro_duration_sec = round(_get_audio_duration_sec(intro_src), 3)

            closing_src = audio_dir / "closing.mp3"
            if closing_src.exists():
                closing_audio_rel = self._copy_to_public(closing_src, assets_subdir)
                if closing_duration_sec <= 0:
                    closing_duration_sec = round(_get_audio_duration_sec(closing_src), 3)

        has_cover_story = _episode_has_cover_story(metadata)
        first_ord = _min_article_order(metadata)

        # --- 雑誌表紙（当該エピソードに表紙記事があるときだけコピー・参照） ---
        cover_rel = None
        if has_cover_story:
            for ext in ["jpg", "jpeg", "png", "webp"]:
                cover_path = self.output_dir / f"cover.{ext}"
                if cover_path.exists():
                    cover_rel = self._copy_to_public(cover_path, assets_subdir)
                    break

        # --- 先頭記事（最小 order）の挿絵（cover にはフォールバックしない） ---
        first_image_rel = self._copy_first_article_image(
            images_dir, first_ord, assets_subdir
        )

        # --- 注目記事（relevance_score 昇順で上位4篇）---
        top_articles = sorted(
            metadata.get("articles", []),
            key=lambda a: a.get("relevance_score", 4),
        )[:TOP_ARTICLES_COUNT]

        # --- セクション日本語ラベル（前2個）---
        sections = metadata.get("sections", [])
        section_labels = [
            SECTION_JP_MAPPING.get(s, s)
            for s in sections[:SECTION_LABELS_COUNT]
        ]

        # --- Remotion用メタデータ構築 ---
        # 全エピソードで episode id=1 と同じイントロ長を使用
        intro_durations = {
            "mainCoverSec": MAIN_COVER_SEC_DEFAULT,
            "disclaimerSec": DISCLAIMER_SEC_DEFAULT,
            "overviewSec": OVERVIEW_SEC_DEFAULT,
        }

        video_meta = {
            "issueDate": self.issue_date,
            "episodeNum": metadata["episode_num"],
            "programTitle": f"ザ・エコノミスト {self.issue_date}",
            "sections": sections,
            "articleCount": metadata["article_count"],
            "estimatedMinutes": metadata["estimated_minutes"],
            "coverImage": cover_rel,
            "mainCover": {
                "title": f"ザ・エコノミスト {self.issue_date}",
                "sections": sections,
                "sectionLabels": section_labels,
                "topArticles": [
                    a.get("japanese_title", a["original_title"])
                    for a in top_articles
                ],
                "firstArticleImage": first_image_rel,
            },
            "articles": [],
            "audioFiles": audio_filenames,  # ["audio_01.mp3", ...]（記事本文のみ）
            "introDurations": intro_durations,
            # エピソードの冒頭・締め用の別トラック情報（Remotion 側で使用）
            "episodeIntroAudio": {
                "audioPath": intro_audio_rel,
                "durationSec": intro_duration_sec,
            } if intro_audio_rel else None,
            "episodeClosingAudio": {
                "audioPath": closing_audio_rel,
                "durationSec": closing_duration_sec,
            } if closing_audio_rel else None,
            # 全エピソード共通のオープニング／エンディング音源（パスは public/ 直下）
            "globalOpenAudio": {
                "audioPath": "open.mp3",
            },
            "globalEndAudio": {
                "audioPath": "end.mp3",
            },
        }

        # --- 各記事のカバー情報 ---
        for article in metadata.get("articles", []):
            order = article["order"]
            # 画像コピー
            image_rel = self._copy_to_public(
                images_dir / f"{order:02d}.png", assets_subdir
            )

            # 音声パスのマッチング（ファイル名ベース）
            # audioFilesは ["audio_01.mp3", "audio_02.mp3"...] なので、
            # orderが一致するものを探す
            target_audio = f"audio_{order:02d}.mp3"
            audio_path_rel = target_audio if target_audio in audio_filenames else None

            dur_sec = float(article.get("duration_sec", 0) or 0)
            if dur_sec <= 0:
                src_for_order = article_order_to_src.get(int(order))
                if src_for_order is not None:
                    probed = _get_audio_duration_sec(src_for_order)
                    if probed > 0:
                        dur_sec = round(probed, 3)
            else:
                dur_sec = round(dur_sec, 3)

            section_name = article["section"]
            video_meta["articles"].append({
                "order": order,
                "originalTitle": article.get("original_title", ""),
                "japaneseTitle": article.get(
                    "japanese_title", article["original_title"]
                ),
                "oneLineIntro": article.get("one_line_intro", ""),
                "summaryJa": article.get("summary_ja", ""),
                "section": section_name,
                "sectionLabel": SECTION_JP_MAPPING.get(
                    section_name, section_name
                ),
                "isCoverStory": article.get("is_cover_story", False),
                "imagePath": image_rel,
                "audioPath": audio_path_rel,
                "durationSec": dur_sec,
            })

        return video_meta

    def _export_remotion_inputs(self, ep_dir: Path, video_meta: dict) -> bool:
        """remotion_input.json をエピソード video/ と remotion/public/ に書き出す（レンダリングは行わない）。"""
        video_dir = ep_dir / "video"
        video_dir.mkdir(exist_ok=True)

        # メタデータを保存（Remotionプロジェクト側で参照するため）
        # 1. エピソード固有の video/remotion_input.json（バックアップ兼ログ）
        meta_path_local = video_dir / "remotion_input.json"
        with open(meta_path_local, "w", encoding="utf-8") as f:
            json.dump(video_meta, f, indent=2, ensure_ascii=False)

        # 2. Remotionプロジェクトの public/remotion_input.json（レンダリング用）
        #    これにより、npm run dev (Studio) でプレビューしやすくなる
        public_meta_path = REMOTION_DIR / "public" / "remotion_input.json"
        try:
            shutil.copy2(meta_path_local, public_meta_path)
            print(f"    [設定] メタデータを配置しました: {public_meta_path}")
        except Exception as e:
            print(f"    [警告] publicへのメタデータ配置失敗: {e}")

        # 出版日付・エピソードIDをファイル名に含め、他号で上書きしないようにする（render_video の出力先と一致）
        output_path = video_dir / f"episode_{self.issue_date}_{self.episode_id}.mp4"
        print(f"    [準備完了] 想定 MP4 出力先（orchestrate render_video 参照）: {output_path}")
        print(f"    手動レンダリング例:")
        print(f"    cd {REMOTION_DIR}")
        print(f"    npx remotion render Episode --props={public_meta_path} --output={output_path}")
        return True

    def process(self) -> bool:
        """指定されたエピソードの動画を生成する"""
        # GENERATE_VIDEO はエピソード単位で episode_progress.json に記録（orchestrate が管理）

        # エピソードIDが指定されていない場合はエラー
        if not self.episode_id:
             print("[エラー] エピソードIDを指定してください")
             return False

        print("[準備] Remotion プロジェクトを確認中...")
        if not self._ensure_remotion_dir():
            return False

        print("[準備] public/ をクリアしてからアセットを注入します...")
        self._clean_public_dir()
        self._copy_channel_assets()
        self._copy_bgm_assets()

        episodes_dir = self.output_dir / "episodes"
        if not episodes_dir.exists():
            print("[エラー] エピソードディレクトリが見つかりません。")
            return False

        target_dir = episodes_dir / self.episode_id
        if not target_dir.exists():
                print(f"[エラー] 指定されたエピソードIDが見つかりません: {self.episode_id}")
                return False
        
        # 単一エピソード処理
        ep_dir = target_dir
        print(f"\n[処理中] エピソード {ep_dir.name} の動画準備中...")

        video_meta = self._prepare_video_metadata(ep_dir)
        if not video_meta:
            print(f"  [警告] メタデータの準備に失敗しました")
            return False

        success = self._export_remotion_inputs(ep_dir, video_meta)

        status = "完了" if success else "失敗"
        print(f"\n[{status}] エピソード {self.episode_id} の Remotion 用データ準備が{status}しました")
        return success


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Remotion 用 remotion_input.json と public アセットを書き出す（レンダリングは orchestrate の render_video が担当）"
    )
    parser.add_argument("date", help="発行日 (YYYY-MM-DD)")
    parser.add_argument("episode", help="エピソードID (例: 01)")
    args = parser.parse_args()

    generator = VideoGenerator(args.date, args.episode)
    generator.process()

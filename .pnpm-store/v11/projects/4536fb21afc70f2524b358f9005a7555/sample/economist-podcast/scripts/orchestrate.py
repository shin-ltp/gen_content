"""
ワークフロー統合モジュール（マルチプロセス対応版）
3つのワーカープロセスでポッドキャスト制作を並列管理する。

【プロセス構成】
  主プロセス ── 起動・監視・進捗表示
    ├─ Worker 1 [resources]: リソース生成
    │    process_source → analyze_content → [WebUI確認] → rewrite_content
    │    → group_episodes → [WebUI確認] → prepare_tts（全章）
    │    → generate_images（全章）→ 音声「成功完了」のみ監視 → renderable 付与（失敗時は不可）
    │
    ├─ Worker 2 [audio]: 音声合成
    │    計画順に 1 話ずつ。失敗時は次話に進まず待機後に同じ話を再試行（AUDIO_RETRY_WAIT_SEC）
    │
    └─ Worker 3 [render]: レンダリング・アップロード（計画順に **MP4 レンダーは厳密直列**）
         renderable + generate_audio=completed かつ「前話の render_video 完了」後に当該話へ
         → generate_video → npx remotion render → thumbnail → upload

【設計原則：レンダーは計画順で MP4 のみ厳密直列】
  - 各エピソードについて音声成功完了・挿絵済みで renderable となり得る。
  - Worker 3 は **episodes_plan 順**で、前話の npx remotion render（render_video）が
    **完了**してから次話の generate_video / レンダーを開始する（public/ と Chrome を
    一話ずつ占有）。
  - 同一話の音声未完了なら当該話は renderable にならず、Worker 3 はその話に入らない。

【ワーカー間 IPC】
  episode_progress.json を共有状態ファイルとして使用。
  各ワーカーは担当フィールドのみ書き込む。アトミック書き込みで競合を防ぐ。
    Worker 1 が書く: prepare_tts, tts_ready, generate_images, renderable
    Worker 2 が書く: generate_audio
    Worker 3 が書く: generate_video, render_video, render_thumbnail, upload_youtube
  _meta セクション: 全ワーカーが更新可能な全体状態（episodes_defined, p1_status 等）

【使用方法】
  # 全プロセス起動（通常実行）
  python orchestrate.py --issue YYYY-MM-DD

  # 進捗確認（別ターミナルから随時）
  python orchestrate.py --issue YYYY-MM-DD --status

  # ワーカー単体で再起動（クラッシュ・中断後）
  python orchestrate.py --issue YYYY-MM-DD --worker resources
  python orchestrate.py --issue YYYY-MM-DD --worker audio
  python orchestrate.py --issue YYYY-MM-DD --worker render

  # 特定の前処理ステップからやり直し（状態をリセットして再実行）
  python orchestrate.py --issue YYYY-MM-DD --from EXTRACT_TEXT

  # 特定ワーカーの制作進捗をリセット
  python orchestrate.py --issue YYYY-MM-DD --reset-worker resources
  python orchestrate.py --issue YYYY-MM-DD --reset-worker audio
  python orchestrate.py --issue YYYY-MM-DD --reset-worker render
"""

import argparse
import io
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── sys.path setup (サブプロセスとして起動された場合も機能するよう最初に設定) ──
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Windows/终端编码兼容：统一 stdout/stderr 为 UTF-8，避免仪表盘与子进程日志乱码
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from config import TTS_BACKEND, get_issue_dir, PROJECT_ROOT
from episode_audio_check import episode_audio_is_complete, episode_audio_missing
from state_manager import StateManager
from webui_server import serve_and_wait

REMOTION_DIR = PROJECT_ROOT / "remotion"

# ── ステップ定義 ──
ORCHESTRATION_STEPS = [
    "EXTRACT_TEXT",
    "ANALYZE_ARTICLES",
    "REVIEW_ANALYSIS",
    "REWRITE_ARTICLES",
    "GENERATE_IMAGES",
    "GROUP_EPISODES",
]
STEP_LABELS = {
    "EXTRACT_TEXT": "テキスト抽出",
    "ANALYZE_ARTICLES": "記事分析・スコアリング",
    "REVIEW_ANALYSIS": "記事分析レビュー (WebUI)",
    "REWRITE_ARTICLES": "記事改写",
    "GENERATE_IMAGES": "挿絵生成",
    "GROUP_EPISODES": "エピソード分組・確認 (WebUI)",
}

# エピソード単位のサブステップ（表示・リセット用）
EP_SUBSTEPS = [
    "prepare_tts",
    "generate_images",
    "generate_audio",
    "generate_video",
    "render_video",
    "render_thumbnail",
    "upload_youtube",
]
EP_SUBSTEP_LABELS = {
    "prepare_tts": "TTS テキスト準備",
    "generate_images": "挿絵生成",
    "generate_audio": "音声合成",
    "generate_video": "Remotion データ準備",
    "render_video": "動画レンダリング",
    "render_thumbnail": "サムネイル生成",
    "upload_youtube": "YouTube アップロード",
}

# ワーカーごとが「所有する」フィールド（再起動時の stale-in_progress リセット用）
WORKER_OWNED_FIELDS: dict[str, list[str]] = {
    "resources": ["prepare_tts", "generate_images"],
    "audio": ["generate_audio"],
    "render": ["generate_video", "render_video", "render_thumbnail", "upload_youtube"],
}

POLL_INTERVAL_SEC = 5
EPISODES_WAIT_TIMEOUT_SEC = 24 * 3600  # 最大24時間待機
# Worker 2/3: 起動直後の stale な p1_status=failed:* を即打ち切りしない猶予（秒）
EPISODES_FAILED_GRACE_SEC = 60
# 音声合成がネットワーク等で失敗した場合、次のエピソードに進まずこの秒数待って同じ話を再試行する
AUDIO_RETRY_WAIT_SEC = 60
# Worker 2: p_audio.log 在此秒数内无更新且 JSON 为 in_progress → 视为 SSH 挂死并重置
AUDIO_STALE_LOG_SEC = int(os.environ.get("AUDIO_STALE_LOG_SEC", "900"))

# update_meta 時に他ワーカーが先に書いた値を取りこぼさないようマージする _meta キー
_META_MERGE_KEYS = (
    "episodes_defined",
    "total_episodes",
    "p1_tts_all_done",
    "p1_images_all_done",
    "p1_render_flags_all_set",
)


# ════════════════════════════════════════════════════════════
#  ProgressState — クロスプロセス共有状態（JSONアトミック書き込み）
# ════════════════════════════════════════════════════════════

class ProgressState:
    """episode_progress.json を使ったクロスプロセス対応の状態管理クラス。

    書き込みは .tmp ファイル経由の os.replace() でアトミックに行い、
    読み込みは JSON 破損時に最大5回リトライする。
    """

    def __init__(self, output_dir: Path, issue_date: str):
        self.path = output_dir / "episode_progress.json"
        self.issue_date = issue_date

    def read(self) -> dict:
        """安全な読み込み（JSON破損・一時ロック時はリトライ）。"""
        for _ in range(5):
            try:
                if self.path.exists():
                    return json.loads(self.path.read_text(encoding="utf-8"))
                return {}
            except (json.JSONDecodeError, OSError):
                time.sleep(0.05)
        return {}

    def _write(self, data: dict):
        """アトミック書き込み (.tmp → os.replace)。"""
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp, self.path)

    # ── _meta ヘルパー ──

    def get_meta(self) -> dict:
        return self.read().get("_meta", {})

    def set_meta(self, key: str, value) -> None:
        """_meta の単一フィールドをアトミック更新（update_meta 経由でマージ保護）。"""
        self.update_meta({key: value})

    def update_meta(self, updates: dict) -> None:
        """_meta の複数フィールドをアトミック更新。

        複数ワーカーが同時に書くと、古いスナップショットで上書きして
        episodes_defined 等が欠落することがある。書き込み直前に再読込し、
        updates に含まれない重要キーは最新ファイル側の値と OR マージする。
        """
        for _ in range(15):
            try:
                data = self.read()
                meta = data.setdefault("_meta", {"issue_date": self.issue_date})
                fresh_meta = self.read().get("_meta", {})
                meta.update(updates)
                for k in _META_MERGE_KEYS:
                    if k in updates:
                        continue
                    a, b = meta.get(k), fresh_meta.get(k)
                    if k == "total_episodes":
                        meta[k] = max(a or 0, b or 0) or a or b
                    elif k == "episodes_defined":
                        meta[k] = bool(a) or bool(b)
                    else:
                        # p1_tts_all_done, p1_images_all_done, p1_render_flags_all_set
                        meta[k] = bool(a) or bool(b)
                meta["updated_at"] = datetime.now().isoformat()
                self._write(data)
                return
            except Exception:
                time.sleep(0.1)

    # ── エピソード ヘルパー ──

    def get_episode(self, ep_id: str) -> dict:
        return self.read().get(ep_id, {})

    def update_episode(self, ep_id: str, updates: dict) -> None:
        """エピソードフィールドをアトミック更新。

        書き込み直前に再読込し updates のみ上書きする。古いスナップショットで
        他ワーカーの generate_audio=in_progress 等が蘇生する競合を防ぐ。
        """
        for _ in range(10):
            try:
                data = self.read()
                ep = dict(data.get(ep_id, {}))
                ep.update(updates)
                ep["updated_at"] = datetime.now().isoformat()
                data[ep_id] = ep
                self._write(data)
                return
            except Exception:
                time.sleep(0.1)

    def get_all_episodes(self) -> dict[str, dict]:
        """_meta を除く全エピソードデータを返す。"""
        data = self.read()
        return {k: v for k, v in data.items() if k != "_meta"}

    def reset_worker_stale_states(self, worker: str) -> None:
        """ワーカー再起動時に stale な "in_progress" 状態をリセット。"""
        owned_fields = WORKER_OWNED_FIELDS.get(worker, [])
        for _ in range(10):
            try:
                data = self.read()
                changed = False
                for ep_id, ep_data in data.items():
                    if ep_id == "_meta":
                        continue
                    for field in owned_fields:
                        if ep_data.get(field) == "in_progress":
                            ep_data[field] = "pending"
                            changed = True
                if changed:
                    self._write(data)
                return
            except Exception:
                time.sleep(0.1)

    def reset_worker_fields(self, worker: str) -> None:
        """ワーカーが担当するすべての進捗フィールドを完全リセット（--reset-worker 用）。"""
        owned_fields = WORKER_OWNED_FIELDS.get(worker, [])
        # resources は tts_ready / renderable フラグも担当
        extra_flags = {
            "resources": ["tts_ready", "renderable"],
            "audio": [],
            "render": [],
        }
        all_fields = owned_fields + extra_flags.get(worker, [])

        for _ in range(10):
            try:
                data = self.read()
                for ep_id, ep_data in data.items():
                    if ep_id == "_meta":
                        continue
                    for field in all_fields:
                        if field in ep_data:
                            # boolean フラグは False に、文字列フィールドは "pending" に
                            ep_data[field] = False if field in ("tts_ready", "renderable") else "pending"
                    # Worker 3 リセット時はエピソード全体の "status" もリセット
                    if worker == "render" and ep_data.get("status") == "completed":
                        ep_data["status"] = "pending"
                # _meta もリセット
                meta = data.get("_meta", {})
                worker_keys = {
                    "resources": ["p1_status", "p1_tts_all_done", "p1_images_all_done",
                                  "p1_render_flags_all_set", "episodes_defined", "webui_url", "webui_label"],
                    "audio": ["p2_status", "p2_complete"],
                    "render": ["p3_status", "p3_complete"],
                }
                for key in worker_keys.get(worker, []):
                    meta.pop(key, None)
                self._write(data)
                return
            except Exception:
                time.sleep(0.1)


# ════════════════════════════════════════════════════════════
#  ユーティリティ
# ════════════════════════════════════════════════════════════

def _safe_exec(fn) -> bool:
    """関数を実行し、成功なら True を返す。SystemExit もキャッチする。"""
    try:
        result = fn()
        return result if isinstance(result, bool) else True
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
        return code == 0
    except Exception as e:
        print(f"[エラー] 予期しないエラー: {e}", flush=True)
        return False


def _ensure_youtube_oauth_before_long_run() -> None:
    """render / アップロード前有効なため、長時間実行の後半でトークン切れにならないよう先頭で OAuth を済ませる。"""
    from upload_youtube import YouTubeAuthRequiredError, ensure_youtube_oauth_at_workflow_start

    print(
        "\n[YouTube] 長時間実行に備え、ワークフロー先頭で OAuth トークンを確認します"
        "（必要ならブラウザが開きます）。",
        flush=True,
    )
    try:
        ensure_youtube_oauth_at_workflow_start(non_interactive=False)
    except FileNotFoundError as e:
        print(f"[エラー] YouTube 認証用ファイルがありません: {e}", flush=True)
        print(
            "  render ワーカーは YouTube アップロードに youtube_client.json が必要です。",
            flush=True,
        )
        sys.exit(1)
    except YouTubeAuthRequiredError as e:
        print(f"[エラー] YouTube 認証: {e}", flush=True)
        sys.exit(1)
    except RuntimeError as e:
        print(f"[エラー] {e}", flush=True)
        sys.exit(1)


def _ep_id(ep_num: int) -> str:
    return f"{ep_num:02d}"


def _load_episodes_plan(output_dir: Path) -> list[dict]:
    """episodes_plan.json からエピソードリストを読み込む。"""
    plan_path = output_dir / "episodes_plan.json"
    if not plan_path.exists():
        return []
    try:
        with open(plan_path, "r", encoding="utf-8") as f:
            plan = json.load(f)
        return plan.get("episodes", [])
    except Exception:
        return []


def _pid_is_alive(pid) -> bool:
    """プロセスが生存中か（Windows / POSIX 共通）。"""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ProcessLookupError, ValueError, TypeError):
        return False


def _episodes_definition_possible(prog: ProgressState, output_dir: Path) -> bool:
    """episodes_defined が立ち得るか（plan あり・分組完了・TTS 進捗あり）。"""
    episodes = _load_episodes_plan(output_dir)
    if episodes:
        return True
    data = prog.read()
    any_tts_progress = any(
        k != "_meta"
        and isinstance(v, dict)
        and (v.get("prepare_tts") == "completed" or v.get("tts_ready"))
        for k, v in data.items()
    )
    if any_tts_progress:
        return True
    return StateManager(prog.issue_date).is_completed("GROUP_EPISODES")


def _repair_episodes_defined_if_stale(prog: ProgressState, output_dir: Path) -> None:
    """複数ワーカー競合で _meta.episodes_defined が欠落した場合に復旧する。

    episodes_plan.json が存在し、かつ GROUP_EPISODES 完了または
    episode_progress に TTS 準備済みがあれば、エピソードは定義済みとみなす。
    """
    if prog.get_meta().get("episodes_defined"):
        return
    episodes = _load_episodes_plan(output_dir)
    if not episodes:
        return
    data = prog.read()
    any_tts_progress = any(
        k != "_meta"
        and isinstance(v, dict)
        and (v.get("prepare_tts") == "completed" or v.get("tts_ready"))
        for k, v in data.items()
    )
    state = StateManager(prog.issue_date)
    if state.is_completed("GROUP_EPISODES") or any_tts_progress:
        print(
            f"[修復] episodes_defined が欠落していたため復旧しました（{len(episodes)} エピソード）。",
            flush=True,
        )
        prog.update_meta({
            "episodes_defined": True,
            "total_episodes": len(episodes),
        })


def _prime_progress_before_workers(prog: ProgressState, output_dir: Path) -> None:
    """主プロセス起動前: plan から episodes_defined を復旧し、誤終了した Worker 2/3 状態を掃除。"""
    _repair_episodes_defined_if_stale(prog, output_dir)
    meta = prog.get_meta()
    updates: dict = {}
    for key in ("p2_status", "p3_status"):
        if str(meta.get(key, "")).startswith("failed:episodes_not_defined"):
            updates[key] = "waiting"
    if updates:
        prog.update_meta(updates)
    # Audio ワーカー未起動時に残った generate_audio=in_progress を掃除
    if not _pid_is_alive(meta.get("p2_pid")):
        data = prog.read()
        changed = False
        for ep_id, ep_data in data.items():
            if ep_id == "_meta" or not isinstance(ep_data, dict):
                continue
            if ep_data.get("generate_audio") == "in_progress":
                ep_data["generate_audio"] = "pending"
                changed = True
        if changed:
            prog._write(data)


def _worker_restartable_after_exit(worker: str, prog: ProgressState, output_dir: Path) -> bool:
    """主プロセスがワーカーを自動再起動してよいか（回復可能な誤終了のみ）。"""
    if worker not in ("audio", "render"):
        return False
    status_key = "p2_status" if worker == "audio" else "p3_status"
    status = str(prog.get_meta().get(status_key, ""))
    if not status.startswith("failed:episodes_not_defined"):
        return False
    meta = prog.get_meta()
    return bool(meta.get("episodes_defined")) or _episodes_definition_possible(prog, output_dir)


def _wait_episodes_defined(prog: ProgressState, output_dir: Path, label: str) -> bool:
    """episodes_defined フラグが立つまで待機する。

    Worker 1 の p1_status=failed:* は、再実行で回復し得る場合（plan あり・分組済み等）は
    待機を継続する。前回実行の stale な failed 状態で Worker 2/3 が誤終了しないよう。
    待機ループ内で _repair_episodes_defined_if_stale を呼び、欠落フラグを自動修復する。
    """
    print(f"\n[{label}] エピソード定義を待機中（plan または進捗から自動復旧します）...", flush=True)
    deadline = time.time() + EPISODES_WAIT_TIMEOUT_SEC
    started_at = time.time()
    while True:
        if time.time() > deadline:
            print(f"[{label}] エピソード定義待ちでタイムアウトしました。", flush=True)
            return False
        _repair_episodes_defined_if_stale(prog, output_dir)
        meta = prog.get_meta()
        if meta.get("episodes_defined"):
            return True
        p1 = meta.get("p1_status", "") or ""
        if p1.startswith("failed"):
            recoverable = _episodes_definition_possible(prog, output_dir)
            w1_alive = _pid_is_alive(meta.get("p1_pid"))
            in_grace = (time.time() - started_at) < EPISODES_FAILED_GRACE_SEC
            if recoverable or w1_alive or in_grace:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            print(f"[{label}] Worker 1 が失敗したため終了します。(p1_status={p1})", flush=True)
            return False
        time.sleep(POLL_INTERVAL_SEC)


# ════════════════════════════════════════════════════════════
#  サブステップ実行関数
# ════════════════════════════════════════════════════════════

def _run_prepare_tts(issue_date: str, ep_num: int) -> bool:
    from prepare_tts import TTSTextPreparer
    return _safe_exec(lambda: TTSTextPreparer(issue_date).prepare_all_episodes(episode_numbers=[ep_num]))


def _run_generate_images(issue_date: str, ep_num: int) -> bool:
    from generate_images import ImageGenerator
    return _safe_exec(lambda: ImageGenerator(issue_date).process_all_episodes(
        episode_num=ep_num, skip_review=True
    ))


def _p_audio_log_stale_sec(output_dir: Path) -> float | None:
    """p_audio.log 距上次写入的秒数。无文件则 None。"""
    log = output_dir / "p_audio.log"
    if not log.is_file():
        return None
    return time.time() - log.stat().st_mtime


def _audio_log_has_ep_start(output_dir: Path, eid: str) -> bool:
    """p_audio.log に当該 EP の合成開始行があるか（中断残留 in_progress の判定用）。"""
    log = output_dir / "p_audio.log"
    if not log.is_file():
        return False
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    needle = f"EP {eid} 音声合成 開始"
    return needle in text


def _kill_hung_qwen_ssh_processes(issue_date: str) -> None:
    """orchestrate Worker 2 用：僵死 SSH 清理。"""
    from qwen_tts_batch import cleanup_stale_local_ssh
    from config import get_issue_dir

    cleanup_stale_local_ssh(
        issue_date,
        lock_path=get_issue_dir(issue_date) / ".gcloud_ssh.lock",
    )


def _run_generate_audio(issue_date: str, ep_id: str) -> bool:
    from generate_audio import AudioGenerator

    backend = TTS_BACKEND
    return _safe_exec(
        lambda: AudioGenerator(issue_date, backend=backend).process_all_episodes(
            target_episodes=[ep_id]
        )
    )


def _run_generate_video(issue_date: str, ep_id: str) -> bool:
    from generate_video import VideoGenerator
    gen = VideoGenerator(issue_date, episode_id=ep_id, render=False)
    return _safe_exec(gen.process)


def _run_remotion_cmd(cmd_str: str, label: str, timeout: int = 10800) -> bool:
    print(f"    $ {cmd_str}", flush=True)
    try:
        result = subprocess.run(
            cmd_str,
            cwd=str(REMOTION_DIR),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True
        stderr_tail = (result.stderr or result.stdout or "")[-600:]
        print(f"    [エラー] {label} 失敗 (exit {result.returncode})", flush=True)
        if stderr_tail.strip():
            print(f"    {stderr_tail.strip()}", flush=True)
        return False
    except subprocess.TimeoutExpired:
        print(f"    [エラー] {label} タイムアウト ({timeout}s)", flush=True)
        return False
    except Exception as e:
        print(f"    [エラー] {label}: {e}", flush=True)
        return False


def _run_render_video(issue_date: str, ep_id: str, output_dir: Path) -> bool:
    props = REMOTION_DIR / "public" / "remotion_input.json"
    output_mp4 = (
        output_dir / "episodes" / ep_id / "video" / f"episode_{issue_date}_{ep_id}.mp4"
    )
    output_mp4.parent.mkdir(parents=True, exist_ok=True)
    cmd = f'npx remotion render Episode --props="{props}" --output="{output_mp4}"'
    return _run_remotion_cmd(cmd, "動画レンダリング", timeout=10800)


def _run_render_thumbnail(issue_date: str, ep_id: str, output_dir: Path) -> bool:
    props = REMOTION_DIR / "public" / "remotion_input.json"
    output_jpg = (
        output_dir / "episodes" / ep_id / "video" / f"thumbnail_{issue_date}_{ep_id}.jpg"
    )
    output_jpg.parent.mkdir(parents=True, exist_ok=True)
    cmd = (
        f'npx remotion still Episode --props="{props}"'
        f' --output="{output_jpg}" --frame=0 --image-format=jpeg'
    )
    return _run_remotion_cmd(cmd, "サムネイル生成", timeout=300)


def _run_upload_youtube(issue_date: str, ep_id: str) -> bool:
    from upload_youtube import YouTubeEpisodeUploader
    uploader = YouTubeEpisodeUploader(
        issue_date=issue_date, episode_id=ep_id, non_interactive=True
    )
    return _safe_exec(uploader.run)


def _prior_episodes_render_video_cleared(
    prog: ProgressState,
    all_eids: list[str],
    eid: str,
    output_dir: Path | None = None,
    issue_date: str | None = None,
) -> bool:
    """episodes_plan 順で、この話より前の話の MP4 レンダー（render_video）が済んでいること。

    - 前話が status=failed（いずれかの致命手前/含むで打ち切り）なら通過してよい。
    - それ以外は前話の render_video が completed になるまで EPk のパイプライン
      （generate_video 含む）に入らない。generate_video が public/ を上書きするため、
      前話の npx remotion render が走っている最中に次話を開始しない。
    - JSON 欠落時はディスク上の MP4 があれば render_video を復旧する。
    """
    try:
        idx = all_eids.index(eid)
    except ValueError:
        return True
    for prev_eid in all_eids[:idx]:
        ep = prog.get_episode(prev_eid)
        if ep.get("status") == "failed":
            continue
        if ep.get("render_video") == "completed":
            continue
        if output_dir and issue_date:
            mp4 = (
                output_dir
                / "episodes"
                / prev_eid
                / "video"
                / f"episode_{issue_date}_{prev_eid}.mp4"
            )
            if mp4.is_file() and mp4.stat().st_size > 10_000:
                prog.update_episode(
                    prev_eid,
                    {"render_video": "completed", "generate_video": "completed"},
                )
                continue
        return False
    return True


def _retry_reset_failed_render_episode(prog: ProgressState, eid: str) -> None:
    """致命失敗で status=failed になった話を、Remotion パイプライン先頭から再実行できるよう戻す。"""
    for _ in range(15):
        try:
            data = prog.read()
            ep = data.setdefault(eid, {})
            ep["status"] = "pending"
            ep["generate_video"] = "pending"
            ep["render_video"] = "pending"
            ep["render_thumbnail"] = "pending"
            ep["upload_youtube"] = "pending"
            ep.pop("failed_substep", None)
            ep.pop("failed_at", None)
            ep["updated_at"] = datetime.now().isoformat()
            prog._write(data)
            return
        except Exception:
            time.sleep(0.1)


def _request_episode_audio_regeneration(
    prog: ProgressState, eid: str, missing: list[str], source: str
) -> None:
    """欠落音声があるため generate_audio とレンダーパイプラインを pending に戻す。"""
    print(
        f"  [{source}] EP {eid} 音声不足 ({', '.join(missing)})"
        f" → 音声再生成を依頼します。",
        flush=True,
    )
    for _ in range(15):
        try:
            data = prog.read()
            ep = data.setdefault(eid, {})
            ep["generate_audio"] = "pending"
            ep["renderable"] = False
            ep["generate_video"] = "pending"
            ep["render_video"] = "pending"
            ep["render_thumbnail"] = "pending"
            ep["upload_youtube"] = "pending"
            ep["status"] = "pending"
            ep.pop("failed_substep", None)
            ep.pop("failed_at", None)
            ep["updated_at"] = datetime.now().isoformat()
            prog._write(data)
            return
        except Exception:
            time.sleep(0.1)


def _ensure_generate_video_before_render(prog: ProgressState, eid: str) -> None:
    """render_video 未完了のときは、必ず generate_video を再実行して public/ を当該話に同期する。"""
    ep = prog.get_episode(eid)
    if ep.get("render_video") == "completed":
        return
    if ep.get("generate_video") != "completed":
        return
    print(
        f"  [準備] EP {eid} render_video 前に remotion/public を再同期します"
        f"（generate_video を再実行）。",
        flush=True,
    )
    prog.update_episode(eid, {"generate_video": "pending"})


# ════════════════════════════════════════════════════════════
#  Worker 1: リソース生成
# ════════════════════════════════════════════════════════════

def run_worker_resources(issue_date: str) -> None:
    """Worker 1: 前処理からTTS・画像生成まで、逐次実行するパイプライン。

    Phase A: 前処理（テキスト抽出〜エピソード分組）
    Phase B: 各エピソードの TTS テキスト準備
    Phase C: 各エピソードの挿絵生成（Worker 2 が並行して音声合成）
    Phase D: 音声完了を監視し renderable フラグを付与（Worker 3 に通知）
    """
    output_dir = get_issue_dir(issue_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    prog = ProgressState(output_dir, issue_date)
    prog.update_meta({"p1_status": "starting", "p1_pid": os.getpid(), "p1_status_started_at": datetime.now().isoformat()})

    def _phase(name: str):
        print(f"\n{'─'*60}\n  {name}\n{'─'*60}", flush=True)

    print(f"\n{'='*60}\n  [Worker 1] リソース生成 開始  ({issue_date})\n{'='*60}\n", flush=True)

    # ── Phase A: 前処理 ─────────────────────────────────────

    # Step 1: EXTRACT_TEXT
    state = StateManager(issue_date)
    if not state.is_completed("EXTRACT_TEXT"):
        _phase("Step 1/5: テキスト抽出")
        prog.update_meta({"p1_status": "running:extract_text", "p1_status_started_at": datetime.now().isoformat()})
        from process_source import SourceProcessor
        if not _safe_exec(lambda: SourceProcessor(issue_date).extract_text()):
            prog.set_meta("p1_status", "failed:extract_text")
            print("[中断] テキスト抽出に失敗しました。", flush=True)
            return
    else:
        print("[スキップ] EXTRACT_TEXT（完了済み）", flush=True)

    # Step 2: ANALYZE_ARTICLES
    state = StateManager(issue_date)
    if not state.is_completed("ANALYZE_ARTICLES") and not state.is_completed("REVIEW_ANALYSIS"):
        _phase("Step 2/5: 記事分析・スコアリング")
        prog.update_meta({"p1_status": "running:analyze", "p1_status_started_at": datetime.now().isoformat()})
        from analyze_content import ContentAnalyzer
        if not _safe_exec(lambda: ContentAnalyzer(issue_date).analyze_articles()):
            prog.set_meta("p1_status", "failed:analyze")
            print("[中断] 記事分析に失敗しました。", flush=True)
            return
    else:
        print("[スキップ] ANALYZE_ARTICLES（完了済み）", flush=True)

    # Step 3: REVIEW_ANALYSIS (WebUI)
    state = StateManager(issue_date)
    if not state.is_completed("REVIEW_ANALYSIS"):
        _phase("Step 3/5: 記事分析レビュー (WebUI)")
        if not state.is_completed("ANALYZE_ARTICLES"):
            state.complete_step("ANALYZE_ARTICLES")

        prog.update_meta({
            "p1_status": "waiting:analysis_review",
            "p1_status_started_at": datetime.now().isoformat(),
            "webui_label": _analysis_review_webui_label(output_dir),
        })

        def _on_analysis_started(url: str):
            prog.update_meta({
                "webui_url": url,
                "webui_label": _analysis_review_webui_label(output_dir),
            })

        serve_and_wait(output_dir, "analysis", on_started=_on_analysis_started)
        prog.update_meta({
            "webui_url": None,
            "webui_label": None,
            "p1_status": "running",
            "p1_status_started_at": datetime.now().isoformat(),
        })
        state = StateManager(issue_date)
        if not state.is_completed("REVIEW_ANALYSIS"):
            state.complete_step("REVIEW_ANALYSIS")
    else:
        print("[スキップ] REVIEW_ANALYSIS（完了済み）", flush=True)

    # Step 4: REWRITE_ARTICLES
    state = StateManager(issue_date)
    if not state.is_completed("REWRITE_ARTICLES"):
        _phase("Step 4/6: 記事改写")
        prog.update_meta({"p1_status": "running:rewrite", "p1_status_started_at": datetime.now().isoformat()})
        from rewrite_content import ContentRewriter
        if not _safe_exec(lambda: ContentRewriter(issue_date).rewrite_articles()):
            prog.set_meta("p1_status", "failed:rewrite")
            print("[中断] 記事改写に失敗しました。", flush=True)
            return
    else:
        print("[スキップ] REWRITE_ARTICLES（完了済み）", flush=True)

    # Step 5: GENERATE_IMAGES
    state = StateManager(issue_date)
    if not state.is_completed("GENERATE_IMAGES"):
        _phase("Step 5/7: 挿絵生成")
        prog.update_meta({"p1_status": "running:generate_images", "p1_status_started_at": datetime.now().isoformat()})

        from generate_images import ImageGenerator
        if not _safe_exec(lambda: ImageGenerator(issue_date).process_all_articles(skip_review=True)):
            prog.set_meta("p1_status", "failed:generate_images")
            print("[中断] 挿絵生成に失敗しました。", flush=True)
            return
    else:
        print("[スキップ] GENERATE_IMAGES（完了済み）", flush=True)

    # Step 6: GROUP_EPISODES (WebUI)
    state = StateManager(issue_date)
    plan_path = output_dir / "episodes_plan.json"
    if not state.is_completed("GROUP_EPISODES"):
        _phase("Step 6/7: エピソード分組・確認 (WebUI)")
        prog.update_meta({"p1_status": "running:group", "p1_status_started_at": datetime.now().isoformat()})
        from group_episodes import EpisodeGrouper
        grouper = EpisodeGrouper(issue_date)

        had_plan_on_disk = plan_path.exists()
        if not had_plan_on_disk:
            if not _safe_exec(grouper.group_episodes):
                prog.set_meta("p1_status", "failed:group_episodes")
                print("[中断] エピソード分組に失敗しました。", flush=True)
                return
        else:
            print(
                "[情報] episodes_plan.json が存在します。WebUI で確認・編集してください。",
                flush=True,
            )

        prog.update_meta({
            "p1_status": "waiting:group_confirm",
            "p1_status_started_at": datetime.now().isoformat(),
            "webui_label": "エピソード編集・確認",
        })

        def _on_group_started(url: str):
            prog.update_meta({"webui_url": url, "webui_label": "エピソード編集・確認"})

        episodes_draft = grouper._draft_plan if not had_plan_on_disk else None
        serve_and_wait(
            output_dir,
            "episodes",
            on_started=_on_group_started,
            episodes_plan_draft=episodes_draft,
        )
        prog.update_meta({
            "webui_url": None,
            "webui_label": None,
            "p1_status": "running",
            "p1_status_started_at": datetime.now().isoformat(),
        })

        if not _safe_exec(lambda: grouper.sync_metadata_after_group_confirm()):
            prog.set_meta("p1_status", "failed:sync_after_group")
            print(
                "[中断] エピソード確認後の同期に失敗しました（保存・metadata の有無を確認してください）。",
                flush=True,
            )
            return
    else:
        print("[スキップ] GROUP_EPISODES（完了済み）", flush=True)
        if plan_path.exists():
            from group_episodes import EpisodeGrouper

            if not _safe_exec(
                lambda: EpisodeGrouper(issue_date).sync_metadata_after_group_confirm()
            ):
                prog.set_meta("p1_status", "failed:sync_after_group")
                print(
                    "[中断] エピソードメタデータの同期に失敗しました。episodes_plan / metadata を確認してください。",
                    flush=True,
                )
                return

    # ComfyUI: 生图阶段已在 GENERATE_IMAGES 结束时停止；此处再确保释放后再开 TTS
    from generate_images import stop_comfyui_container_if_running
    stop_comfyui_container_if_running()

    # ── Phase B: TTS テキスト準備（全エピソード） ──────────

    episodes = _load_episodes_plan(output_dir)
    if not episodes:
        prog.set_meta("p1_status", "failed:no_episodes")
        print("[エラー] episodes_plan.json にエピソードが見つかりません。", flush=True)
        return

    total = len(episodes)
    # Worker 2/3 が待機解除できるよう episodes_defined フラグを立てる
    prog.update_meta({"episodes_defined": True, "total_episodes": total})
    
    # 挿絵は分組前に全生成・コピー済みのため、全エピソードについて completed とする
    for ep_data in episodes:
        eid = _ep_id(ep_data["episode_num"])
        prog.update_episode(eid, {"generate_images": "completed"})
        
    print(f"\n[情報] {total} エピソードが定義されました。Worker 2/3 が開始可能になりました。", flush=True)

    _phase(f"Phase B: TTS テキスト準備（全 {total} エピソード）")
    for ep_data in episodes:
        ep_num = ep_data["episode_num"]
        eid = _ep_id(ep_num)
        ep_prog = prog.get_episode(eid)

        if ep_prog.get("prepare_tts") == "completed":
            print(f"  [スキップ] EP {eid} TTS テキスト準備（完了済み）", flush=True)
            # tts_ready フラグが未設定なら付与（前回の中断からの再起動対応）
            if not ep_prog.get("tts_ready"):
                prog.update_episode(eid, {"tts_ready": True})
            continue

        prog.update_meta({"p1_status": f"running:prepare_tts:{eid}", "p1_status_started_at": datetime.now().isoformat()})
        print(f"\n  [EP {eid}] TTS テキスト準備...", flush=True)
        if _run_prepare_tts(issue_date, ep_num):
            prog.update_episode(eid, {"prepare_tts": "completed", "tts_ready": True})
            print(f"  [完了] EP {eid} TTS テキスト準備 → Worker 2 へ通知", flush=True)
        else:
            prog.update_episode(eid, {"prepare_tts": "failed"})
            prog.set_meta("p1_status", f"failed:prepare_tts:{eid}")
            print(f"  [エラー] EP {eid} TTS テキスト準備に失敗しました。", flush=True)
            return

    prog.set_meta("p1_tts_all_done", True)
    prog.update_meta({"p1_images_all_done": True})

    # ── Phase C: 音声完了を監視 → renderable フラグ付与 ───
    # 各エピソードは独立: 当該話の generate_audio が「成功完了」した時点でだけ
    # その話に renderable を付与する。他話の音声進捗は関係しない。

    _phase("Phase C: 音声完了を監視と renderable 付与（エピソード単位・独立）")
    prog.update_meta({"p1_status": "running:wait_audio_for_render", "p1_status_started_at": datetime.now().isoformat()})
    _repair_episodes_defined_if_stale(prog, output_dir)

    all_eids = [_ep_id(ep["episode_num"]) for ep in episodes]
    deadline = time.time() + EPISODES_WAIT_TIMEOUT_SEC

    while True:
        if time.time() > deadline:
            prog.set_meta("p1_status", "failed:audio_wait_timeout")
            print("[エラー] 音声合成完了待ちでタイムアウトしました。", flush=True)
            return

        all_episodes_data = prog.get_all_episodes()
        all_renderable = True

        for eid in all_eids:
            ep = all_episodes_data.get(eid, {})
            # レンダー・UP まで終わった話は Phase D の対象外（再び renderable を付け直さない）
            if ep.get("status") == "completed":
                continue

            ep_dir = output_dir / "episodes" / eid
            audio_disk_ok = episode_audio_is_complete(ep_dir)

            # 旧バージョンで付いた誤 renderable を解除（音声未成功またはディスク不足）
            if ep.get("renderable") and (
                ep.get("generate_audio") != "completed" or not audio_disk_ok
            ):
                updates = {"renderable": False}
                if ep.get("generate_audio") == "completed" and not audio_disk_ok:
                    updates["generate_audio"] = "pending"
                prog.update_episode(eid, updates)
                reason = "音声が未完了または失敗" if ep.get("generate_audio") != "completed" else "音声ファイル不足"
                print(
                    f"  [修復] EP {eid} の renderable を解除しました（{reason}）。",
                    flush=True,
                )
                all_renderable = False
                continue

            if ep.get("renderable"):
                continue

            images_ok = ep.get("generate_images") == "completed"
            if not images_ok and _disk_has_images(ep_dir):
                prog.update_episode(eid, {"generate_images": "completed"})
                images_ok = True
                print(
                    f"  [修復] EP {eid} generate_images をディスクから復旧しました。",
                    flush=True,
                )
            if not images_ok:
                all_renderable = False
                continue

            # JSON とディスクの両方が揃ったエピソードのみレンダー可能
            if ep.get("generate_audio") == "completed":
                if audio_disk_ok:
                    prog.update_episode(eid, {"renderable": True})
                    print(
                        f"  [通知] EP {eid} → renderable 付与（音声完了・Worker 3 へ）",
                        flush=True,
                    )
                else:
                    missing = episode_audio_missing(ep_dir)
                    prog.update_episode(eid, {"generate_audio": "pending", "renderable": False})
                    print(
                        f"  [修復] EP {eid} generate_audio を pending に戻しました"
                        f"（不足: {', '.join(missing)}）。",
                        flush=True,
                    )
                    all_renderable = False
            else:
                all_renderable = False

        if all_renderable:
            break

        time.sleep(POLL_INTERVAL_SEC)

    prog.update_meta({
        "p1_render_flags_all_set": True,
        "p1_status": "complete",
        "p1_status_started_at": datetime.now().isoformat(),
    })
    print(f"\n[完了] Worker 1 全タスク完了。\n", flush=True)


# ════════════════════════════════════════════════════════════
#  Worker 2: 音声合成
# ════════════════════════════════════════════════════════════

def run_worker_audio(issue_date: str) -> None:
    """Worker 2: tts_ready を満たしたエピソードを**計画順に**音声合成する。

    前の話が generate_audio=completed になるまで次の話に進まない。
    合成失敗時は次話に進まず、一定秒待って同じ話を pending に戻し再試行する（間隔は AUDIO_RETRY_WAIT_SEC）。
    全話が音声完了するまで終了しない（失敗を最終状態にしない）。

    再起動時に stale な "in_progress" は "pending" にリセットする。
    """
    output_dir = get_issue_dir(issue_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    prog = ProgressState(output_dir, issue_date)

    # 再起動時の stale in_progress リセット
    prog.reset_worker_stale_states("audio")
    prog.update_meta({"p2_status": "waiting", "p2_pid": os.getpid()})

    print(f"\n{'='*60}\n  [Worker 2] 音声合成 開始  ({issue_date})\n{'='*60}\n", flush=True)

    if not _wait_episodes_defined(prog, output_dir, "Worker 2"):
        prog.set_meta("p2_status", "failed:episodes_not_defined")
        return

    episodes = _load_episodes_plan(output_dir)
    all_eids = [_ep_id(ep["episode_num"]) for ep in episodes]
    total = len(all_eids)

    prog.update_meta({"p2_status": "running"})
    print(
        f"\n[Worker 2] {total} エピソードの音声合成ループを開始します。"
        f"（TTS_BACKEND={TTS_BACKEND}）",
        flush=True,
    )

    deadline = time.time() + EPISODES_WAIT_TIMEOUT_SEC

    while True:
        if time.time() > deadline:
            prog.set_meta("p2_status", "failed:timeout")
            print("[エラー] 音声合成タイムアウト。", flush=True)
            return

        # 計画順で「最初に音声が未完了の話」だけを扱う（07 が未完なら 08 に進まない）
        target_eid: str | None = None
        for eid in all_eids:
            ep_check = prog.get_episode(eid)
            ga = ep_check.get("generate_audio")
            ep_dir = output_dir / "episodes" / eid
            if ga != "completed":
                target_eid = eid
                break
            if not episode_audio_is_complete(ep_dir):
                missing = episode_audio_missing(ep_dir)
                prog.update_episode(eid, {"generate_audio": "pending", "renderable": False})
                print(
                    f"  [修復] EP {eid} generate_audio を pending に戻しました"
                    f"（JSON は completed だが不足: {', '.join(missing)}）。",
                    flush=True,
                )
                target_eid = eid
                break

        if target_eid is None:
            break

        ep = prog.get_episode(target_eid)
        audio_status = ep.get("generate_audio", "pending")

        if not ep.get("tts_ready"):
            prog.set_meta("p2_status", f"waiting:tts:{target_eid}")
            time.sleep(POLL_INTERVAL_SEC)
            continue

        if audio_status == "failed":
            print(
                f"\n  [Worker 2] EP {target_eid} 音声合成が失敗しました。"
                f" {AUDIO_RETRY_WAIT_SEC} 秒待って再試行します（次のエピソードには進みません）。",
                flush=True,
            )
            prog.set_meta("p2_status", f"waiting:retry_audio:{target_eid}")
            time.sleep(AUDIO_RETRY_WAIT_SEC)
            prog.update_episode(target_eid, {"generate_audio": "pending"})
            continue

        if audio_status == "in_progress":
            stale = _p_audio_log_stale_sec(output_dir)
            orphan = not _audio_log_has_ep_start(output_dir, target_eid)
            if orphan and (stale is None or stale > POLL_INTERVAL_SEC * 2):
                print(
                    f"\n  [修復] EP {target_eid} generate_audio=in_progress だがログに合成開始なし"
                    f" → 中断残留と判断し pending に戻します。",
                    flush=True,
                )
                prog.update_episode(target_eid, {"generate_audio": "pending"})
                continue
            if stale is not None and stale > AUDIO_STALE_LOG_SEC:
                print(
                    f"\n  [修復] EP {target_eid} p_audio.log が {int(stale)}s 更新なし "
                    f"→ SSH ハング疑い。プロセス掃除後 pending に戻します。",
                    flush=True,
                )
                _kill_hung_qwen_ssh_processes(issue_date)
                prog.update_episode(target_eid, {"generate_audio": "pending"})
            else:
                time.sleep(POLL_INTERVAL_SEC)
            continue

        # pending → 実行
        prog.update_episode(target_eid, {"generate_audio": "in_progress"})
        prog.set_meta("p2_status", f"running:audio:{target_eid}")
        print(f"\n  [Worker 2] EP {target_eid} 音声合成 開始...", flush=True)

        if _run_generate_audio(issue_date, target_eid):
            ep_dir = output_dir / "episodes" / target_eid
            missing = episode_audio_missing(ep_dir)
            if missing:
                prog.update_episode(target_eid, {"generate_audio": "pending", "renderable": False})
                print(
                    f"  [警告] EP {target_eid} 音声ファイル不足: {', '.join(missing)}"
                    f" → pending に戻して再試行します。",
                    flush=True,
                )
            else:
                prog.update_episode(target_eid, {"generate_audio": "completed"})
                print(f"  [完了] EP {target_eid} 音声合成", flush=True)
        else:
            prog.update_episode(target_eid, {"generate_audio": "failed"})
            print(
                f"  [エラー] EP {target_eid} 音声合成に失敗しました。"
                f" {AUDIO_RETRY_WAIT_SEC} 秒後に同じ話を再試行します。",
                flush=True,
            )

        # 失敗時は次ループで failed 分岐が sleep→pending→再実行する

    prog.update_meta({"p2_status": "complete", "p2_complete": True})
    print(f"\n[完了] Worker 2 全エピソードの音声合成が完了しました。\n", flush=True)


# ════════════════════════════════════════════════════════════
#  Worker 3: レンダリング・アップロード
# ════════════════════════════════════════════════════════════

def run_worker_render(issue_date: str) -> None:
    """Worker 3: エピソード単位で動画レンダリングとアップロードを行う。

    開始条件: 当該エピソードが renderable かつ generate_audio=completed のときのみ
    その話のパイプラインに入る。

    **動画（npx remotion render）は計画順に厳密に直列**: episodes_plan 上で前の話の
    render_video が完了するまで、次話の generate_video も含めパイプラインに入らない
    （public/ 占有・Chrome の二重起動を避ける）。前話が status=failed なら次話へ進む。

    status=failed の話はスキップせず、起動時に generate_video からやり直して再試行する。
    render_video 未完了のときは常に generate_video を先行して remotion/public を当該話へ同期する。

    再起動時に generate_video が完了済みでも render_video が未完の場合は、
    remotion/public/ が上書きされている可能性があるため generate_video から再実行する。
    upload_youtube 失敗時は警告を記録して処理を継続する（致命エラーとしない）。
    """
    output_dir = get_issue_dir(issue_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    prog = ProgressState(output_dir, issue_date)

    # 再起動時の stale in_progress リセット
    prog.reset_worker_stale_states("render")
    prog.update_meta({"p3_status": "waiting", "p3_pid": os.getpid()})

    print(f"\n{'='*60}\n  [Worker 3] レンダリング・アップロード 開始  ({issue_date})\n{'='*60}\n", flush=True)

    if os.environ.get("YOUTUBE_OAUTH_PRIMED_BY_ORCHESTRATE") != "1":
        _ensure_youtube_oauth_before_long_run()

    if not _wait_episodes_defined(prog, output_dir, "Worker 3"):
        prog.set_meta("p3_status", "failed:episodes_not_defined")
        return

    episodes = _load_episodes_plan(output_dir)
    all_eids = [_ep_id(ep["episode_num"]) for ep in episodes]
    total = len(all_eids)

    # 異常終了で render_video だけ in_progress が残った場合は pending に戻す。
    # generate_video はリセットしない（同一話のレンダー中断では public はまだ当該話向けのままが多く、
    # 再レンダのみでよい。旧ロジックは「render 未完なら generate_video も pending」として
    # 再起動のたびに EP01 から generate_video し直しになっていた）。
    for eid in all_eids:
        ep = prog.get_episode(eid)
        if ep.get("render_video") == "in_progress":
            prog.update_episode(eid, {"render_video": "pending"})
            print(
                f"  [復旧] EP {eid} render_video を pending に戻しました（中断時の in_progress 掃除）。",
                flush=True,
            )

    prog.update_meta({"p3_status": "running"})
    print(f"\n[Worker 3] {total} エピソードのレンダリングループを開始します。", flush=True)

    # レンダーパイプライン定義（エピソードごと直列）
    RENDER_PIPELINE: list[tuple[str, str, bool]] = [
        # (フィールド名, ラベル, 失敗時に致命エラーとするか)
        ("generate_video",   "Remotion データ準備",  True),
        ("render_video",     "動画レンダリング",      True),
        ("render_thumbnail", "サムネイル生成",        True),
        ("upload_youtube",   "YouTube アップロード",  False),  # 失敗しても継続
    ]

    deadline = time.time() + EPISODES_WAIT_TIMEOUT_SEC

    while True:
        if time.time() > deadline:
            prog.set_meta("p3_status", "failed:timeout")
            print("[エラー] レンダリングタイムアウト。", flush=True)
            return

        all_episodes_data = prog.get_all_episodes()
        processed_this_round = False

        for eid in all_eids:
            ep = all_episodes_data.get(eid, {})

            if ep.get("status") == "completed":
                continue
            if not ep.get("renderable"):
                continue
            # 章ごと独立の要請: この話の音声が成功完了していること（他話は見ない）
            if ep.get("generate_audio") != "completed":
                continue

            if not _prior_episodes_render_video_cleared(
                prog, all_eids, eid, output_dir, issue_date
            ):
                # 前話の MP4 レンダー完了まで待つ（同一 round で後続話に進まない）
                continue

            # このエピソードのみパイプライン実行（failed は再試行・render 前に必ず generate_video）
            ep_gate = prog.get_episode(eid)
            if ep_gate.get("status") == "failed":
                print(
                    f"\n  [再試行] EP {eid} は failed のため Remotion データ準備から再実行します。",
                    flush=True,
                )
                _retry_reset_failed_render_episode(prog, eid)
            else:
                _ensure_generate_video_before_render(prog, eid)

            print(f"\n{'─'*60}\n  [Worker 3] EP {eid} レンダリングパイプライン開始\n{'─'*60}", flush=True)
            prog.set_meta("p3_status", f"running:{eid}")

            ep_failed = False
            for field, label, is_fatal in RENDER_PIPELINE:
                # 最新状態を取得
                ep_current = prog.get_episode(eid)
                if ep_current.get(field) == "completed":
                    print(f"  [スキップ] EP {eid} {label}（完了済み）", flush=True)
                    continue

                print(f"\n  [Worker 3] EP {eid} {label}...", flush=True)
                prog.update_episode(eid, {field: "in_progress"})

                # ランナー呼び出し
                if field == "generate_video":
                    success = _run_generate_video(issue_date, eid)
                elif field == "render_video":
                    success = _run_render_video(issue_date, eid, output_dir)
                elif field == "render_thumbnail":
                    success = _run_render_thumbnail(issue_date, eid, output_dir)
                elif field == "upload_youtube":
                    success = _run_upload_youtube(issue_date, eid)
                else:
                    success = False

                if success:
                    prog.update_episode(eid, {field: "completed"})
                    print(f"  [完了] EP {eid} {label}", flush=True)
                else:
                    if field == "generate_video":
                        ep_dir = output_dir / "episodes" / eid
                        missing = episode_audio_missing(ep_dir)
                        if missing:
                            _request_episode_audio_regeneration(prog, eid, missing, "Worker 3")
                            ep_failed = True
                            break
                    prog.update_episode(eid, {field: "failed"})
                    if is_fatal:
                        prog.update_episode(eid, {
                            "status": "failed",
                            "failed_substep": field,
                            "failed_at": datetime.now().isoformat(),
                        })
                        print(f"  [エラー] EP {eid} {label} 失敗。このエピソードをスキップします。", flush=True)
                        ep_failed = True
                        break
                    else:
                        print(f"  [警告] EP {eid} {label} 失敗（処理は継続します）。", flush=True)

            if not ep_failed:
                prog.update_episode(eid, {
                    "status": "completed",
                    "completed_at": datetime.now().isoformat(),
                })
                print(f"\n  [完了] EP {eid} 全工程完了", flush=True)

            processed_this_round = True
            all_episodes_data = prog.get_all_episodes()

        # 終了判定: レンダー対象（renderable かつ音声完了）の話がすべて completed
        # failed は再試行するため、(completed|failed) で打ち切らない
        meta = prog.get_meta()
        if meta.get("p1_render_flags_all_set"):
            all_render_done = True
            for eid in all_eids:
                ep = prog.get_episode(eid)
                if not ep.get("renderable"):
                    continue
                if ep.get("generate_audio") != "completed":
                    continue
                if ep.get("status") != "completed":
                    all_render_done = False
                    break
            if all_render_done:
                break

        if not processed_this_round:
            time.sleep(POLL_INTERVAL_SEC)

    prog.update_meta({"p3_status": "complete", "p3_complete": True})
    print(f"\n[完了] Worker 3 全エピソードのレンダリング・アップロードが完了しました。\n", flush=True)
    _cleanup_mac_remote_if_done(issue_date, prog)


# ════════════════════════════════════════════════════════════
#  進捗表示
# ════════════════════════════════════════════════════════════

_STATUS_ICON = {
    "completed": "✓",
    "failed": "✗",
    "in_progress": "▶",
    "pending": "-",
    True: "✓",
    False: "-",
    None: "-",
}


def _icon(value) -> str:
    if isinstance(value, str):
        return _STATUS_ICON.get(value, value[:1])
    return _STATUS_ICON.get(value, "-")


def _p1_status_label(p1_status: str | None) -> str:
    if p1_status is None:
        return "未開始"
        
    mapping = {
        "starting": "起動中",
        "running": "実行中",
        "running:extract_text": "テキスト抽出中",
        "running:analyze": "記事分析中",
        "waiting:analysis_review": "⚠ WebUI確認待ち（記事分析）",
        "running:rewrite": "記事改写中",
        "running:group": "エピソード分組中",
        "waiting:group_confirm": "⚠ WebUI確認待ち（分組確認）",
        "running:wait_audio_for_render": "音声完了待ち",
        "complete": "完了 ✓",
        "failed": "失敗 ✗",
    }
    for prefix, label in mapping.items():
        if p1_status.startswith(prefix):
            return label
    return p1_status


def _episode_disk_tail_hints(output_dir: Path, issue_date: str, eid: str) -> dict:
    """JSON が欠けていても、ディスク上の成果物からダッシュボード表示用ヒントを返す。"""
    base = output_dir / "episodes" / eid
    hints: dict[str, bool] = {}
    audio_dir = base / "audio"
    if audio_dir.is_dir() and any(audio_dir.glob("*.mp3")):
        hints["has_audio_files"] = True
    vd = base / "video"
    mp4 = vd / f"episode_{issue_date}_{eid}.mp4"
    jpg = vd / f"thumbnail_{issue_date}_{eid}.jpg"
    try:
        if mp4.is_file() and mp4.stat().st_size > 10_000:
            hints["has_mp4"] = True
        if jpg.is_file() and jpg.stat().st_size > 1_000:
            hints["has_thumb"] = True
    except OSError:
        pass
    meta_path = base / "metadata.json"
    if meta_path.is_file():
        try:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            yt = m.get("youtube") or {}
            if isinstance(yt, dict) and (yt.get("video_id") or yt.get("video_url")):
                hints["has_youtube_meta"] = True
        except (json.JSONDecodeError, OSError):
            pass
    return hints


def _read_remote_tts_progress_hint(output_dir: Path) -> str:
    """仪表盘 Worker 2 行显示的远程 TTS batch 进度（Fish / VoxCPM / Qwen 共通）。"""
    qwen_p = output_dir / ".qwen_remote_progress.json"
    if qwen_p.is_file():
        try:
            d = json.loads(qwen_p.read_text(encoding="utf-8"))
            done = int(d.get("done", 0))
            total = int(d.get("total", 0))
            if total > 0:
                pct = 100.0 * done / total
                return f"  Qwen {done}/{total} ({pct:.0f}%)"
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    log_path = output_dir / "p_audio.log"
    if log_path.is_file():
        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
            import re

            for tag, label in (("[FishAudio]", "Fish"), ("[VoxCPM]", "VoxCPM")):
                lines = [l for l in text.splitlines() if f"{tag} 远程合成进度" in l]
                if lines:
                    last = lines[-1]
                    m = re.search(r"(\d+)/(\d+)\s*\((\d+\.?\d*)%\)", last)
                    if m:
                        done, total, pct = m.group(1), m.group(2), m.group(3)
                        return f"  {label} {done}/{total} ({pct}%)"
        except (OSError, ValueError):
            pass

    return ""


def _read_analysis_skipped_summary(output_dir: Path) -> str | None:
    """analysis_skipped.json から分析失败跳过の要約行を読む。無ければ raw/ と analysis.json から推定。"""
    path = output_dir / "analysis_skipped.json"
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            summary = (data.get("summary") or "").strip()
            if summary:
                return summary.replace("[情報] ", "")
            count = int(data.get("count", 0))
            indices = data.get("skipped_raw_indices") or []
            if count == 0:
                return "分析失败跳过: 0 篇"
            raw_list = ", ".join(f"{int(i):03d}" for i in indices)
            return f"分析失败跳过: {count} 篇 (RAW {raw_list})"
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            pass

    analysis_path = output_dir / "analysis.json"
    raw_dir = output_dir / "raw"
    if not analysis_path.is_file() or not raw_dir.is_dir():
        return None
    try:
        raw_indices = sorted(int(p.stem) for p in raw_dir.glob("*.txt") if p.stem.isdigit())
        articles = json.loads(analysis_path.read_text(encoding="utf-8"))
        analyzed = {int(a["raw_index"]) for a in articles if isinstance(a.get("raw_index"), (int, float))}
        skipped = [i for i in raw_indices if i not in analyzed]
        if not skipped:
            return "分析失败跳过: 0 篇"
        raw_list = ", ".join(f"{i:03d}" for i in skipped)
        return f"分析失败跳过: {len(skipped)} 篇 (RAW {raw_list})"
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None


def _analysis_review_webui_label(output_dir: Path) -> str:
    """記事分析レビュー待ちのダッシュボード表示用ラベル（跳过件数を含む）。"""
    base = "記事分析レビュー"
    skipped = _read_analysis_skipped_summary(output_dir)
    if skipped:
        return f"{base} · {skipped}"
    return base


def _format_status_table(issue_date: str, prog: ProgressState, log_dir: Path) -> str:
    data = prog.read()
    meta = data.get("_meta", {})
    episodes_data = {k: v for k, v in data.items() if k != "_meta"}
    all_eids = sorted(episodes_data.keys())
    output_dir = prog.path.parent

    W = 64
    lines: list[str] = []
    lines.append("=" * W)
    lines.append(f"  The Economist {issue_date}  制作ダッシュボード")
    lines.append("=" * W)

    p1 = meta.get("p1_status", "未開始")
    p2 = meta.get("p2_status", "未開始")
    p3 = meta.get("p3_status", "未開始")

    p1_started = meta.get("p1_status_started_at")
    p1_elapsed = ""
    if p1_started:
        try:
            sec = int((datetime.now() - datetime.fromisoformat(p1_started)).total_seconds())
            mm, ss = divmod(max(0, sec), 60)
            hh, mm = divmod(mm, 60)
            p1_elapsed = f" ({hh:02d}:{mm:02d}:{ss:02d})"
        except Exception:
            p1_elapsed = ""
    lines.append(f"  Worker 1 [リソース生成]   {_p1_status_label(p1)}{p1_elapsed}")
    qwen_hint = _read_remote_tts_progress_hint(output_dir)
    lines.append(f"  Worker 2 [音声合成]       {p2}{qwen_hint}")
    lines.append(f"  Worker 3 [レンダリング]   {p3}")

    webui_url = meta.get("webui_url")
    webui_label = meta.get("webui_label", "")
    if webui_url:
        lines.append("-" * W)
        lines.append(f"  ⚠  ブラウザで確認が必要です: {webui_label}")
        lines.append(f"     URL: {webui_url}")

    if all_eids:
        lines.append("-" * W)
        header = f"  {'EP':>3}  {'TTS':>4}  {'画像':>4}  {'音声':>4}  {'動画準':>4}  {'レン':>4}  {'UP':>4}  状態"
        lines.append(header)
        lines.append("-" * W)
        for eid in all_eids:
            ep = episodes_data[eid]
            disk = _episode_disk_tail_hints(output_dir, issue_date, eid)

            def _eff(field: str, disk_key: str | None = None) -> str:
                v = ep.get(field)
                if v in ("completed", "failed", "in_progress"):
                    return v
                if disk_key and disk.get(disk_key):
                    return "completed"
                return v if isinstance(v, str) else "pending"

            ga = _eff("generate_audio", "has_audio_files")
            gv = _eff("generate_video", "has_mp4")
            rv = _eff("render_video", "has_mp4")
            uy = _eff("upload_youtube", "has_youtube_meta")

            status = ep.get("status", "pending")
            done_disk = (
                disk.get("has_mp4") and disk.get("has_thumb") and disk.get("has_youtube_meta")
            )
            if status == "completed":
                status_str = "完了 ✓"
            elif done_disk:
                status_str = "完了 ✓（出力ファイル）"
            elif status == "failed":
                fs = ep.get("failed_substep", "?")
                status_str = f"失敗({EP_SUBSTEP_LABELS.get(fs, fs)[:4]})"
            elif ep.get("generate_audio") == "in_progress":
                status_str = "音声合成中"
            elif ep.get("generate_video") == "in_progress":
                status_str = "動画準備中"
            elif ep.get("render_video") == "in_progress":
                status_str = "レンダー中"
            elif ep.get("renderable"):
                status_str = "レンダー待ち"
            elif ep.get("tts_ready"):
                status_str = "TTS完了"
            else:
                status_str = "待機中"

            row = (
                f"  {eid:>3}  "
                f"{_icon(ep.get('prepare_tts')):>4}  "
                f"{_icon(ep.get('generate_images')):>4}  "
                f"{_icon(ga):>4}  "
                f"{_icon(gv):>4}  "
                f"{_icon(rv):>4}  "
                f"{_icon(uy):>4}  "
                f"{status_str}"
            )
            lines.append(row)

    # ログファイル末尾を表示（W2 は Qwen 远程进度行を優先表示）
    _log_tail_lines = {"W1": 2, "W2": 6, "W3": 2}
    for worker_name, log_file in [
        ("W1", log_dir / "p_resources.log"),
        ("W2", log_dir / "p_audio.log"),
        ("W3", log_dir / "p_render.log"),
    ]:
        if log_file.exists():
            try:
                text = log_file.read_text(encoding="utf-8", errors="replace")
                n_tail = _log_tail_lines.get(worker_name, 2)
                all_lines = [l for l in text.splitlines() if l.strip()]
                if worker_name == "W2":
                    progress_lines = [
                        l for l in all_lines if "远程合成进度" in l or "[Qwen] 远程" in l or "[VoxCPM]" in l
                    ]
                    last_lines = progress_lines[-2:] + all_lines[-max(2, n_tail - 2):]
                    # 去重保序
                    seen: set[str] = set()
                    deduped: list[str] = []
                    for ll in last_lines:
                        if ll not in seen:
                            seen.add(ll)
                            deduped.append(ll)
                    last_lines = deduped[-n_tail:]
                else:
                    last_lines = all_lines[-n_tail:]
                if last_lines:
                    lines.append("-" * W)
                    for ll in last_lines:
                        lines.append(f"  [{worker_name}] {ll[:W-8]}")
            except Exception:
                pass

    lines.append("=" * W)
    lines.append(f"  更新: {datetime.now().strftime('%H:%M:%S')}  (5秒ごとに自動更新)")
    return "\n".join(lines)


def _print_status(issue_date: str):
    """--status: 現在の進捗をターミナルに表示する。"""
    output_dir = get_issue_dir(issue_date)
    prog = ProgressState(output_dir, issue_date)
    state = StateManager(issue_date)

    print(f"\n{'='*64}")
    print(f"  The Economist {issue_date} 号 - 制作進捗状況")
    print(f"{'='*64}")
    print("  【前処理ステップ】")
    for step in ORCHESTRATION_STEPS:
        label = STEP_LABELS.get(step, step)
        if state.is_completed(step):
            mark = "[完了]   "
        elif state.is_waiting_user(step):
            mark = "[確認待ち]"
        elif state.status.get("current_step") == step:
            mark = "[進行中] "
        else:
            mark = "[未着手] "
        print(f"    {mark} {label}")

    print("\n  【エピソード制作】")
    episodes_data = prog.get_all_episodes()
    if not episodes_data:
        print("    （まだ開始されていません）")
    else:
        for eid in sorted(episodes_data.keys()):
            ep = episodes_data[eid]
            status = ep.get("status", "pending")
            if status == "completed":
                print(f"    EP {eid}: 完了 ✓")
            elif status == "failed":
                fs = ep.get("failed_substep", "?")
                print(f"    EP {eid}: 失敗 ({EP_SUBSTEP_LABELS.get(fs, fs)})")
            else:
                done = [s for s in EP_SUBSTEPS if ep.get(s) == "completed"]
                print(f"    EP {eid}: 進行中 ({len(done)}/{len(EP_SUBSTEPS)} 完了)")

    meta = prog.get_meta()
    print(f"\n  Worker 1: {meta.get('p1_status', '未開始')}")
    print(f"  Worker 2: {meta.get('p2_status', '未開始')}")
    print(f"  Worker 3: {meta.get('p3_status', '未開始')}")

    webui_url = meta.get("webui_url")
    if webui_url:
        print(f"\n  ⚠ WebUI 確認待ち: {webui_url}")

    print(f"{'='*64}\n")


# ════════════════════════════════════════════════════════════
#  前処理ステップリセット（--from STEP）
# ════════════════════════════════════════════════════════════

def _reset_from_step(issue_date: str, from_step: str) -> None:
    """指定ステップ以降の StateManager の状態をリセットする。

    GROUP_EPISODES 以前からリセットする場合は episode_progress.json の _meta も
    クリアする（episodes_defined フラグなどが古い状態で残らないよう）。
    制作進捗（エピソードごとのサブステップ）はリセットしない。
    制作進捗をリセットしたい場合は --reset-worker を使用すること。
    """
    if from_step not in ORCHESTRATION_STEPS:
        print(f"[エラー] 不明なステップ: {from_step}")
        print(f"  有効: {', '.join(ORCHESTRATION_STEPS)}")
        sys.exit(1)

    state = StateManager(issue_date)
    idx = ORCHESTRATION_STEPS.index(from_step)
    for step in ORCHESTRATION_STEPS[idx:]:
        state.status["completed_steps"] = [
            s for s in state.status["completed_steps"] if s != step
        ]
        state.status.get("step_details", {}).pop(step, None)
    state.status["current_step"] = None
    state._save()

    # GROUP_EPISODES 以前からリセットする場合は episode_progress.json の _meta もリセット
    # （episodes_defined などの古いフラグが Worker 2/3 を誤って起動させないよう）
    if idx <= ORCHESTRATION_STEPS.index("GROUP_EPISODES"):
        output_dir = get_issue_dir(issue_date)
        prog = ProgressState(output_dir, issue_date)
        prog.update_meta({
            "episodes_defined": False,
            "p1_tts_all_done": False,
            "p1_images_all_done": False,
            "p1_render_flags_all_set": False,
            "p1_status": None,
            "webui_url": None,
            "webui_label": None,
        })
        print(f"[リセット] episode_progress.json の _meta フラグもリセットしました。")
        print(f"  注意: 制作進捗（音声・動画等）はそのまま保持されます。")
        print(f"        制作進捗もリセットしたい場合: --reset-worker resources / audio / render")

    print(f"[リセット] {from_step} 以降の前処理ステップを未完了に戻しました。")
    print(f"  再実行: python orchestrate.py --issue {issue_date}")


# ════════════════════════════════════════════════════════════
#  ディスク実体から episode_progress.json を同期
# ════════════════════════════════════════════════════════════

def _atomic_write_episode_progress(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(tmp, path)


def _load_episode_metadata(ep_dir: Path) -> dict:
    p = ep_dir / "metadata.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _disk_audio_status(ep_dir: Path, article_count: int) -> str:
    """intro / 全記事 NN.mp3 / closing が揃えば completed。それ以外は pending（部分ファイルは再開用）。"""
    ad = ep_dir / "audio"
    if not ad.is_dir():
        return "pending"
    has_intro = (ad / "intro.mp3").is_file()
    has_closing = (ad / "closing.mp3").is_file()
    n_articles = sum(
        1
        for i in range(1, max(article_count, 12) + 1)
        if (ad / f"{i:02d}.mp3").is_file()
    )
    if has_intro and has_closing and article_count > 0 and n_articles >= article_count:
        return "completed"
    return "pending"


def _disk_has_tts(ep_dir: Path) -> bool:
    td = ep_dir / "tts"
    return td.is_dir() and any(td.glob("*.txt"))


def _disk_has_images(ep_dir: Path) -> bool:
    im = ep_dir / "images"
    return im.is_dir() and (any(im.glob("*.png")) or any(im.glob("*.jpg")))


def sync_progress_from_disk(issue_date: str) -> None:
    """episodes_plan / 出力フォルダの実ファイルを読み、episode_progress.json を整合させる。

    - 音声: intro + 全記事番号 mp3 + closing
    - 動画: episode_{issue}_{id}.mp4 / thumbnail_{issue}_{id}.jpg
    - YouTube: metadata.json の youtube.video_id（無ければ既存 JSON の completed を維持）
    """
    output_dir = get_issue_dir(issue_date)
    if not output_dir.is_dir():
        print(f"[エラー] 出力ディレクトリがありません: {output_dir}")
        sys.exit(1)

    episodes = _load_episodes_plan(output_dir)
    if not episodes:
        print(f"[エラー] episodes_plan.json が無いかエピソードが空です。")
        sys.exit(1)

    prog_path = output_dir / "episode_progress.json"
    data = json.loads(prog_path.read_text(encoding="utf-8")) if prog_path.exists() else {}
    meta = data.setdefault("_meta", {"issue_date": issue_date})
    fresh_meta = dict(data.get("_meta", {}))

    now = datetime.now().isoformat()
    lines_out: list[str] = []

    for ep_data in episodes:
        ep_num = ep_data["episode_num"]
        eid = _ep_id(ep_num)
        ep_dir = output_dir / "episodes" / eid
        md = _load_episode_metadata(ep_dir)
        article_count = int(
            md.get("article_count") or ep_data.get("article_count") or 0
        )

        prev = dict(data.get(eid, {})) if isinstance(data.get(eid), dict) else {}

        if _disk_has_tts(ep_dir):
            ep: dict = {
                "prepare_tts": "completed",
                "tts_ready": True,
            }
        else:
            ep = {
                "prepare_tts": prev.get("prepare_tts", "pending"),
                "tts_ready": bool(prev.get("tts_ready")),
            }
        if _disk_has_images(ep_dir):
            ep["generate_images"] = "completed"
        else:
            ep["generate_images"] = prev.get("generate_images", "pending")

        au_st = _disk_audio_status(ep_dir, article_count)
        if au_st == "completed":
            ep["generate_audio"] = "completed"
        elif prev.get("generate_audio") == "failed":
            ep["generate_audio"] = "failed"
        elif prev.get("generate_audio") == "in_progress":
            # 実行中ワーカーを壊さない（JSON 競合で in_progress が消えた場合の再開用）
            ep["generate_audio"] = "in_progress"
        else:
            ep["generate_audio"] = "pending"

        mp4 = ep_dir / "video" / f"episode_{issue_date}_{eid}.mp4"
        jpg = ep_dir / "video" / f"thumbnail_{issue_date}_{eid}.jpg"
        mp4_ok = mp4.is_file() and mp4.stat().st_size > 10_000
        jpg_ok = jpg.is_file() and jpg.stat().st_size > 1_000

        if mp4_ok:
            ep["generate_video"] = "completed"
            ep["render_video"] = "completed"
        else:
            ep["generate_video"] = prev.get("generate_video", "pending")
            ep["render_video"] = prev.get("render_video", "pending")

        if jpg_ok:
            ep["render_thumbnail"] = "completed"
        else:
            ep["render_thumbnail"] = prev.get("render_thumbnail", "pending")

        yt = md.get("youtube") if isinstance(md.get("youtube"), dict) else {}
        has_yt = bool(yt.get("video_id") or yt.get("video_url"))
        if has_yt:
            ep["upload_youtube"] = "completed"
        elif prev.get("upload_youtube") == "completed":
            ep["upload_youtube"] = "completed"
        elif mp4_ok and jpg_ok and ep.get("generate_audio") == "completed":
            ep["upload_youtube"] = prev.get("upload_youtube", "pending")
        else:
            ep["upload_youtube"] = prev.get("upload_youtube", "pending")

        # renderable: 画像＋音声がともに成功完了したときのみ（失敗時はレンダー不可）
        img_ok = ep.get("generate_images") == "completed"
        if img_ok and ep.get("generate_audio") == "completed":
            ep["renderable"] = True
        else:
            ep["renderable"] = False

        # エピソード全体ステータス
        tail_done = (
            mp4_ok
            and jpg_ok
            and ep.get("generate_audio") == "completed"
            and ep.get("upload_youtube") == "completed"
        )
        if tail_done:
            ep["status"] = "completed"
            ep["completed_at"] = prev.get("completed_at") or now
        elif ep.get("generate_audio") == "failed":
            ep["status"] = "failed"
        elif prev.get("status") == "completed" and not tail_done:
            # ディスクと矛盾 → 実体優先で落とす
            ep["status"] = "pending"
        else:
            ep["status"] = prev.get("status", "pending")

        ep["updated_at"] = now
        data[eid] = ep

        lines_out.append(
            f"  EP{eid}  音声={ep['generate_audio']:11s} 動画={'✓' if mp4_ok else '-'} "
            f"サムネ={'✓' if jpg_ok else '-'}  YT={'✓' if ep['upload_youtube']=='completed' else ep['upload_youtube']}  "
            f"全体={ep['status']}"
        )

    # plan に無いキーは残すが _meta と plan 内 eid 以外のゴミは触らない
    meta["issue_date"] = issue_date
    meta["episodes_defined"] = True
    meta["total_episodes"] = len(episodes)
    meta["updated_at"] = now
    for k in ("p1_pid", "p2_pid", "p3_pid"):
        meta.pop(k, None)
    meta.setdefault("p1_tts_all_done", True)
    meta.setdefault("p1_images_all_done", True)
    meta["p1_render_flags_all_set"] = all(
        (data.get(_ep_id(ep["episode_num"]), {}) or {}).get("renderable")
        for ep in episodes
    )
    meta["p1_status"] = (
        "complete" if meta["p1_render_flags_all_set"] else "running:wait_audio_for_render"
    )
    # orchestrate 実行中に sync しても Worker 2/3 の running 状態を潰さない
    for k in ("p2_status", "p3_status", "p2_pid", "p3_pid"):
        live = fresh_meta.get(k)
        if live is not None and str(live).startswith("running"):
            meta[k] = live
        elif k.endswith("_status"):
            meta.setdefault(k, "waiting")
    data["_meta"] = meta

    _atomic_write_episode_progress(prog_path, data)

    print(f"\n{'='*64}")
    print(f"  episode_progress.json をディスク実体に同期しました  ({issue_date})")
    print(f"  保存先: {prog_path}")
    print(f"{'='*64}")
    print("\n".join(lines_out))
    print(f"{'='*64}\n")
    print(
        "  注: metadata.json に youtube が無い場合、既存 JSON で upload_youtube=completed "
        "ならそのまま維持します。初回のみ pending になります。\n"
    )


# ════════════════════════════════════════════════════════════
#  Mac 远程临时文件清理（Fish jobs / ComfyUI output）
# ════════════════════════════════════════════════════════════

def _workflow_fully_complete(prog: ProgressState, output_dir: Path) -> bool:
    """p1/p2/p3 完了かつ renderable な全エピソードが status=completed か。"""
    meta = prog.get_meta()
    if meta.get("p1_status") != "complete":
        return False
    if not meta.get("p2_complete"):
        return False
    if not meta.get("p3_complete"):
        return False

    plan_path = output_dir / "episodes_plan.json"
    if not plan_path.exists():
        return False
    with open(plan_path, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    for ep in episodes:
        eid = _ep_id(ep["episode_num"])
        ep_prog = prog.get_episode(eid)
        if not ep_prog.get("renderable"):
            continue
        if ep_prog.get("generate_audio") != "completed":
            return False
        if ep_prog.get("status") != "completed":
            return False
    return True


def _cleanup_mac_remote_if_done(issue_date: str, prog: ProgressState) -> None:
    """全流程成功后清除 Mac 上当期 Fish job / ComfyUI 输出（幂等）。"""
    if prog.get_meta().get("mac_remote_cleaned"):
        return
    output_dir = get_issue_dir(issue_date)
    if not _workflow_fully_complete(prog, output_dir):
        return
    try:
        from mac_remote_cleanup import cleanup_mac_issue_artifacts

        cleanup_mac_issue_artifacts(issue_date)
        prog.update_meta({
            "mac_remote_cleaned": True,
            "mac_remote_cleaned_at": datetime.now().isoformat(),
        })
    except Exception as e:
        print(f"  [警告] Mac 远程清理失败（本地成果不受影响）: {e}", flush=True)


# ════════════════════════════════════════════════════════════
#  主プロセス: ワーカー起動・監視・進捗表示
# ════════════════════════════════════════════════════════════

def run_main(issue_date: str, workers: list[str]) -> None:
    """主プロセス: 指定されたワーカーを起動し、進捗を監視・表示する。"""
    output_dir = get_issue_dir(issue_date)
    output_dir.mkdir(parents=True, exist_ok=True)
    prog = ProgressState(output_dir, issue_date)

    script_path = Path(__file__).resolve()
    base_cmd = [sys.executable, str(script_path), "--issue", issue_date]
    child_env = os.environ.copy()
    # 强制子 Python 进程进入 UTF-8 模式，避免日志中日文被本地代码页编码
    child_env["PYTHONUTF8"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONUNBUFFERED"] = "1"

    print(f"\n{'='*64}")
    print(f"  The Economist ポッドキャスト制作ワークフロー")
    print(f"  対象号: {issue_date}")
    print(f"  起動ワーカー: {', '.join(workers)}")
    print(f"{'='*64}\n")

    _prime_progress_before_workers(prog, output_dir)

    if "render" in workers:
        _ensure_youtube_oauth_before_long_run()
        # 子プロセスの Worker 3 で同じ OAuth を二重に走らせない
        child_env["YOUTUBE_OAUTH_PRIMED_BY_ORCHESTRATE"] = "1"

    log_files: dict[str, object] = {}
    processes: dict[str, subprocess.Popen] = {}

    try:
        for worker in workers:
            log_path = output_dir / f"p_{worker}.log"
            lf = open(log_path, "w", encoding="utf-8", buffering=1)
            log_files[worker] = lf
            cmd = base_cmd + ["--worker", worker]
            proc = subprocess.Popen(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(SCRIPTS_DIR),
                env=child_env,
            )
            processes[worker] = proc
            print(f"  [起動] Worker {worker}  PID={proc.pid}  ログ: {log_path.name}")

        print(f"\n全ワーカーを起動しました。Ctrl+C で中断できます。\n", flush=True)

        DISPLAY_INTERVAL = 5.0
        last_display = 0.0

        while True:
            now = time.time()
            if now - last_display >= DISPLAY_INTERVAL:
                os.system("cls" if os.name == "nt" else "clear")
                print(_format_status_table(issue_date, prog, output_dir))
                print()

                # クラッシュ検知・回復可能な誤終了は自動再起動
                for worker, proc in list(processes.items()):
                    rc = proc.poll()
                    if rc is None:
                        continue
                    if rc != 0:
                        print(f"  [警告] Worker {worker} が異常終了しました (exit={rc})")
                        print(f"         ログ: {output_dir / f'p_{worker}.log'}")
                    if _worker_restartable_after_exit(worker, prog, output_dir):
                        log_path = output_dir / f"p_{worker}.log"
                        lf = log_files.get(worker)
                        if lf and not lf.closed:
                            lf.close()
                        lf = open(log_path, "a", encoding="utf-8", buffering=1)
                        log_files[worker] = lf
                        cmd = base_cmd + ["--worker", worker]
                        new_proc = subprocess.Popen(
                            cmd,
                            stdout=lf,
                            stderr=subprocess.STDOUT,
                            cwd=str(SCRIPTS_DIR),
                            env=child_env,
                        )
                        processes[worker] = new_proc
                        print(
                            f"  [再起動] Worker {worker} を再開しました PID={new_proc.pid}"
                            f"（episodes_defined 復旧後の誤終了を検知）",
                            flush=True,
                        )

                last_display = now

            # 全ワーカー終了チェック
            if all(proc.poll() is not None for proc in processes.values()):
                break

            time.sleep(1.0)

        # 最終表示
        os.system("cls" if os.name == "nt" else "clear")
        print(_format_status_table(issue_date, prog, output_dir))
        print()

        all_ok = all(proc.returncode == 0 for proc in processes.values())
        if all_ok:
            prog = ProgressState(output_dir, issue_date)
            _cleanup_mac_remote_if_done(issue_date, prog)
            print(f"{'='*64}")
            print(f"  全工程完了！")
            print(f"  出力先: {output_dir}")
            print(f"{'='*64}\n")
        else:
            print(f"\n[エラー] 一部のワーカーが失敗しました。")
            for worker, proc in processes.items():
                if proc.returncode != 0:
                    print(f"  Worker {worker}: exit={proc.returncode}")
                    print(f"  ログ: {output_dir / f'p_{worker}.log'}")
            print(f"\n  ワーカー単体を再起動して再開できます:")
            print(f"  python orchestrate.py --issue {issue_date} --worker <resources|audio|render>")

    except KeyboardInterrupt:
        print(f"\n\n[中断] Ctrl+C が押されました。ワーカーを停止します...", flush=True)
        for worker, proc in processes.items():
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                    print(f"  Worker {worker} を停止しました。")
                except subprocess.TimeoutExpired:
                    proc.kill()
                    print(f"  Worker {worker} を強制終了しました。")
        print("\n進捗は保存されています。再開するには:")
        print(f"  python orchestrate.py --issue {issue_date}")

    finally:
        for lf in log_files.values():
            try:
                lf.close()
            except Exception:
                pass


# ════════════════════════════════════════════════════════════
#  CLI エントリーポイント
# ════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(
        description="The Economist ポッドキャスト制作ワークフロー（マルチプロセス版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  # 全プロセス起動（通常実行）
  python orchestrate.py --issue 2026-03-15

  # 進捗確認（別ターミナルから）
  python orchestrate.py --issue 2026-03-15 --status

  # ワーカー単体で再起動（クラッシュ後の再開）
  python orchestrate.py --issue 2026-03-15 --worker resources
  python orchestrate.py --issue 2026-03-15 --worker audio
  python orchestrate.py --issue 2026-03-15 --worker render

  # 前処理ステップからやり直し
  python orchestrate.py --issue 2026-03-15 --from REWRITE_ARTICLES

  # ワーカーの制作進捗をリセットして再実行
  python orchestrate.py --issue 2026-03-15 --reset-worker audio
  python orchestrate.py --issue 2026-03-15 --reset-worker render

前処理ステップ一覧:
  EXTRACT_TEXT      テキスト抽出
  ANALYZE_ARTICLES  記事分析・スコアリング
  REVIEW_ANALYSIS   記事分析レビュー (WebUI)
  REWRITE_ARTICLES  記事改写
  GROUP_EPISODES    エピソード分組・確認 (WebUI)
""",
    )
    parser.add_argument("--issue", required=True, help="号数（YYYY-MM-DD 形式）")
    parser.add_argument("--status", action="store_true", help="現在の進捗状況を表示して終了")
    parser.add_argument(
        "--sync-progress-from-disk",
        action="store_true",
        help="episode_progress.json を episodes_plan・出力フォルダの実ファイルに合わせて更新して終了",
    )
    parser.add_argument(
        "--worker",
        choices=["resources", "audio", "render"],
        metavar="WORKER",
        help="単体ワーカーとして実行: resources | audio | render",
    )
    parser.add_argument(
        "--workers",
        nargs="+",
        choices=["resources", "audio", "render"],
        metavar="WORKER",
        default=["resources", "audio", "render"],
        help="起動するワーカーを指定（デフォルト: 全ワーカー）",
    )
    parser.add_argument(
        "--from",
        dest="from_step",
        metavar="STEP",
        help="指定ステップ以降の前処理をリセットして再実行",
    )
    parser.add_argument(
        "--reset-worker",
        dest="reset_worker",
        choices=["resources", "audio", "render"],
        metavar="WORKER",
        help="指定ワーカーの制作進捗をリセット",
    )

    args = parser.parse_args()
    issue_date = args.issue

    # -- 進捗表示モード --
    if args.status:
        _print_status(issue_date)
        return

    if args.sync_progress_from_disk:
        sync_progress_from_disk(issue_date)
        return

    # -- 前処理ステップリセット --
    if args.from_step:
        _reset_from_step(issue_date, args.from_step.upper())
        return

    # -- ワーカー制作進捗リセット --
    if args.reset_worker:
        output_dir = get_issue_dir(issue_date)
        prog = ProgressState(output_dir, issue_date)
        prog.reset_worker_fields(args.reset_worker)
        print(f"[リセット] Worker {args.reset_worker} の制作進捗をリセットしました。")
        print(f"  再起動: python orchestrate.py --issue {issue_date} --worker {args.reset_worker}")
        return

    # -- 単体ワーカーモード（主プロセスから subprocess.Popen で起動される） --
    if args.worker:
        if args.worker == "resources":
            run_worker_resources(issue_date)
        elif args.worker == "audio":
            run_worker_audio(issue_date)
        elif args.worker == "render":
            run_worker_render(issue_date)
        return

    # -- 主プロセスモード: 全ワーカーを起動して監視 --
    run_main(issue_date, args.workers)


if __name__ == "__main__":
    main()

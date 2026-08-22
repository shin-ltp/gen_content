"""
音声生成モジュール（Fish Audio S2 Pro INT8 / Qwen3-TTS / VoxCPM2）

バックエンド（TTS_BACKEND、既定 fish）:
- fish: Fish Audio S2 Pro INT8 voice clone（Mac MLX・SSH 远程 batch・fish_audio_mlx_worker.py）
- qwen: Qwen3-TTS voice clone（llm-spot GCE GPU・远程 batch・バックアップ用）
- voxcpm: VoxCPM2 voice clone（llm-spot GCE GPU・远程 batch・バックアップ用）

Fish Audio（Mac / Apple Silicon MLX）:
- INT8 量子化 + MLX 推論（既定ホスト: cho@rw-mac-1）
- 参考音声 VQ トークンをキャッシュし全セグメントで再利用
- 接続は gcloud ではなく通常の SSH/SCP（GCE VM 自動起動は行わない）

動作仕様:
- エピソードのみ指定時: 当該エピソードの全 txt（intro, 01〜NN, closing）を順に変換
- エラー発生時: 即時終了（sys.exit(1)）
- 正常応答時: セグメント・記事・エピソード間の追加待機なしで次の処理へ進む

処理フロー:
1. TTS テキストを [pause long], [pause short], 句号（。）でスライス。
2. 各スライスを作業ディレクトリ（audio_work/）に保存し、
   バックエンドに応じた並列数で生成する。正常応答後は追加待機しない。
3. 全 WAV 生成後に検証（存在・サイズ・再生時間）。問題があればリトライ。
4. 全 WAV 正常なら無音を挟んで ffmpeg で連結 → MP3 出力。
5. 作業ディレクトリは削除しない（再実行時に既存 WAV を再利用）。
"""
import json
import os
import re
import subprocess
import sys
import io
import time
from pathlib import Path
from typing import Literal

from config import (
    FISH_AUDIO_TTS_REMOTE_HOST,
    QWEN_TTS_BATCH_SIZE,
    QWEN_TTS_DTYPE,
    QWEN_TTS_MODEL,
    QWEN_TTS_REMOTE_HOST,
    TTS_REF_AUDIO,
    TTS_REF_DIR,
    TTS_REF_ROLE,
    VOXCPM_TTS_CFG,
    VOXCPM_TTS_MODEL,
    VOXCPM_TTS_REMOTE_HOST,
    VOXCPM_TTS_STEPS,
    TTS_BACKEND,
    get_issue_dir,
)
from episode_audio_check import episode_audio_missing
from state_manager import StateManager
import text_llm

# Windows環境でのUnicodeEncodeErrorを防止
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── 拼接パラメータ ──────────────────────────────────────────
SILENCE_PAUSE_LONG_SEC = 1.0
SILENCE_PAUSE_SHORT_SEC = 0.35
SILENCE_PERIOD_SEC = 0.35
SAMPLE_RATE = 44100

# ── 並列・リトライ ──────────────────────────────────────────
MAX_RETRIES = 3
# 検証失敗時の再生成前に待機する秒数（1回目1分、2回目2分、3回目5分）
RETRY_WAIT_BEFORE_ROUND_SEC = (60, 120, 300)

# ── WAV 検証 ────────────────────────────────────────────────
# 日本語 TTS の文字数/秒（01 記事の実サンプル平均 ≈5.94、350/60≈5.83 で期待時間を算出）
CHARS_PER_SEC_JA = 350 / 60          # ≈5.83 chars/sec
DURATION_MAX_RATIO = 1.7              # 期待時間の 1.7 倍超 → 繰り返しの疑い（この場合のみテキスト改写）
DURATION_MIN_RATIO = 0.2              # 期待時間の 0.2 倍未満 → 音声欠落の疑い（TTS 再生成のみ）
WAV_MIN_SIZE = 1000                   # 最小ファイルサイズ (bytes)

# WAV 検証失敗の種別（テキスト改写は too_long のみ）
FAILURE_TOO_LONG = "too_long"
FAILURE_TOO_SHORT = "too_short"
FAILURE_MISSING = "missing"           # 未生成・サイズ不足・無音・時間取得失敗等


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ユーティリティ関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _rewrite_segment_for_retry(text: str) -> str | None:
    """再生時間超過（TTS 繰り返し疑い）時のみ呼ぶ。意味を保ち長さを近似に保って言い換える。
    Flash モデルを使用。失敗時は None を返す。"""
    if not text_llm.is_configured() or not text.strip():
        return None
    try:
        prompt = (
            "以下の日本語テキストを、意味を完全に保持し、文字数（長さ）をほぼ同じに保ちながら、"
            "わずかに言い換えてください。TTSで読み上げる際に繰り返しや音声欠落が起きる可能性がある表現を避けるためです。"
            "改行や余計な説明・引用符は不要。改写後のテキストのみを1行で出力してください。\n\n"
            f"【原文】\n{text}"
        )
        rewritten = text_llm.generate_text(prompt, tier="flash").strip().strip('"\'')
        if rewritten and len(rewritten) > 10:
            return rewritten
    except Exception as e:
        print(f"        [警告] テキスト改写失敗: {e}")
    return None


def _normalize_break_to_markup(text: str) -> str:
    """<break time="Xs" /> を [pause short]/[pause long] に置換（旧 TTS ファイル互換）。"""
    out = re.sub(r'<break\s+time="2\.0s"\s*/>', "[pause long]", text, flags=re.I)
    out = re.sub(r'<break\s+time="1\.5s"\s*/>', "[pause long]", out, flags=re.I)
    out = re.sub(r'<break\s+time="0\.7s"\s*/>', "[pause short]", out, flags=re.I)
    out = re.sub(r'<break\s+time="[\d.]+s"\s*/>', "[pause short]", out, flags=re.I)
    return out


def _slice_by_pause_and_period(
    text: str,
) -> list[tuple[str, Literal["pause_long", "pause_short", "period"] | None]]:
    """[pause long], [pause short], 句点（。・？）でスライスする。
    返却: [(セグメントテキスト, 直後の区切り種別), ...]
    区切り種別が None のときは末尾（その後に区切りなし）。
    """
    text = _normalize_break_to_markup(text)
    segments: list[tuple[str, Literal["pause_long", "pause_short", "period"] | None]] = []
    i = 0
    while i < len(text):
        next_long = text.find("[pause long]", i)
        next_short = text.find("[pause short]", i)
        next_period = text.find("。", i)
        next_qmark = text.find("？", i)
        if next_long == -1:
            next_long = len(text) + 1
        if next_short == -1:
            next_short = len(text) + 1
        if next_period == -1:
            next_period = len(text) + 1
        if next_qmark == -1:
            next_qmark = len(text) + 1

        min_pos = min(next_long, next_short, next_period, next_qmark)

        # 区切りが見つからない → 残り全部を最終セグメントとして追加
        if min_pos > len(text):
            seg_text = text[i:].strip()
            if seg_text:
                segments.append((seg_text, None))
            break

        if next_long <= next_short and next_long <= next_period and next_long <= next_qmark:
            seg_text = text[i:next_long].strip()
            segments.append((seg_text, "pause_long"))
            i = next_long + len("[pause long]")
        elif next_short <= next_long and next_short <= next_period and next_short <= next_qmark:
            seg_text = text[i:next_short].strip()
            segments.append((seg_text, "pause_short"))
            i = next_short + len("[pause short]")
        elif next_period <= next_qmark:
            seg_text = text[i : next_period + 1].strip()
            segments.append((seg_text, "period"))
            i = next_period + 1
        else:
            seg_text = text[i : next_qmark + 1].strip()
            segments.append((seg_text, "period"))
            i = next_qmark + 1

    return segments


def _is_mp3_response(raw: bytes) -> bool:
    """応答が MP3 かどうか（ID3 タグまたは MP3 フレーム同期で判定）。"""
    if len(raw) < 2:
        return False
    if raw.startswith(b"ID3"):
        return True
    if raw[0] == 0xFF and (raw[1] & 0xE0) == 0xE0:
        return True
    return False


def _run_ffmpeg(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """ffmpeg を実行。check=True で戻り値が 0 でない場合 CalledProcessError。"""
    return subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-nostats"] + args,
        capture_output=True,
        check=check,
    )


def _silence_duration(
    after: Literal["pause_long", "pause_short", "period"] | None,
) -> float:
    """区切り種別に対応する無音秒数を返す。"""
    if after == "pause_long":
        return SILENCE_PAUSE_LONG_SEC
    if after == "pause_short":
        return SILENCE_PAUSE_SHORT_SEC
    if after == "period":
        return SILENCE_PERIOD_SEC
    return 0.0


# ── WAV 保存・検証 ──────────────────────────────────────────

def _save_normalized_wav(raw_bytes: bytes, wav_path: Path) -> bool:
    """API 応答バイトを正規化して WAV (44100Hz, mono, 16-bit PCM) で保存する。"""
    if raw_bytes.startswith(b"RIFF"):
        ext = ".wav"
    elif _is_mp3_response(raw_bytes):
        ext = ".mp3"
    else:
        ext = ".dat"
    tmp_path = wav_path.with_name(wav_path.stem + "_raw" + ext)
    tmp_path.write_bytes(raw_bytes)
    try:
        _run_ffmpeg([
            "-i", str(tmp_path),
            "-ar", str(SAMPLE_RATE), "-ac", "1", "-acodec", "pcm_s16le",
            str(wav_path),
        ])
        return True
    except subprocess.CalledProcessError:
        return False
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


def _get_wav_duration_sec(wav_path: Path) -> float:
    """WAV ファイルの再生時間（秒）を返す。失敗時は -1。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(wav_path),
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        # フォールバック: PCM 44100Hz mono 16bit として推定
        try:
            size = wav_path.stat().st_size
            return max(0, (size - 44) / (SAMPLE_RATE * 2))
        except Exception:
            return -1.0


def _tts_file_sort_key(f: Path) -> tuple:
    """TTS ファイルの再生順序: intro → 01, 02, ... → closing"""
    stem = f.stem.lower()
    if stem == "intro":
        return (0, "")
    if stem == "closing":
        return (2, "")
    if stem.isdigit():
        return (1, stem.zfill(2))
    return (3, stem)


def _validate_wav(wav_path: Path, text: str) -> tuple[bool, str, str | None]:
    """WAV ファイルの妥当性を検証する。

    Returns:
        (valid, reason, failure_kind)
        failure_kind は invalid 時のみ。too_long のときだけテキスト改写対象。
    """
    if not wav_path.exists():
        return False, "ファイルが存在しません", FAILURE_MISSING

    size = wav_path.stat().st_size
    if size < WAV_MIN_SIZE:
        return False, f"ファイルサイズが小さすぎます ({size} bytes)", FAILURE_MISSING

    duration = _get_wav_duration_sec(wav_path)
    if duration < 0:
        return False, "再生時間の取得に失敗", FAILURE_MISSING
    if duration < 0.1:
        return (
            False,
            f"無音または再生時間が極端に短い ({duration:.2f}秒)",
            FAILURE_MISSING,
        )

    text_len = len(text)
    if text_len > 10:
        expected = text_len / CHARS_PER_SEC_JA
        if duration > expected * DURATION_MAX_RATIO:
            return (
                False,
                f"再生時間が長すぎ ({duration:.1f}秒, 期待≈{expected:.1f}秒, "
                f"上限{expected * DURATION_MAX_RATIO:.1f}秒) — 繰り返しの可能性",
                FAILURE_TOO_LONG,
            )
        if duration < expected * DURATION_MIN_RATIO:
            return (
                False,
                f"再生時間が短すぎ ({duration:.1f}秒, 期待≈{expected:.1f}秒)",
                FAILURE_TOO_SHORT,
            )

    return True, "OK", None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AudioGenerator
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AudioGenerator:
    """TTS バックエンド（Fish Audio / Qwen / VoxCPM）を用いた音声生成（スライス + 検証 + 無音拼接）。"""

    def __init__(self, issue_date: str, backend: str | None = None):
        self.issue_date = issue_date
        self._backend_name = (backend or TTS_BACKEND).strip().lower()
        if self._backend_name not in ("fish", "qwen", "voxcpm"):
            self._backend_name = "fish"

        self.fish_engine = None
        self.voxcpm_engine = None
        self.qwen_engine = None

        if not TTS_REF_AUDIO.exists():
            raise RuntimeError(
                f"参考音频不存在: {TTS_REF_AUDIO}\n"
                f"请设置 TTS_REF_ROLE（当前: {TTS_REF_ROLE}）或 TTS_REF_DIR。"
            )

        if self._backend_name == "fish":
            from fish_audio_batch import FishAudioBatchEngine

            self.fish_engine = FishAudioBatchEngine(issue_date)
        elif self._backend_name == "voxcpm":
            from voxcpm_batch import VoxCPMBatchEngine

            self.voxcpm_engine = VoxCPMBatchEngine(issue_date)
        elif self._backend_name == "qwen":
            from qwen_tts_batch import QwenRemoteBatchEngine

            self.qwen_engine = QwenRemoteBatchEngine(issue_date)

        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)

    def _synthesize_segments(
        self,
        work_dir: Path,
        segments: list[dict],
        *,
        force: bool = False,
    ) -> None:
        if self._backend_name == "fish" and self.fish_engine is not None:
            self.fish_engine.synthesize_from_work_dir(work_dir, segments, force=force)
        elif self._backend_name == "voxcpm" and self.voxcpm_engine is not None:
            self.voxcpm_engine.synthesize_from_work_dir(work_dir, segments, force=force)
        elif self._backend_name == "qwen" and self.qwen_engine is not None:
            self.qwen_engine.synthesize_from_work_dir(work_dir, segments, force=force)

    # ── 作業ディレクトリ準備 ─────────────────────────────────

    def _prepare_work_dir(
        self,
        text: str,
        output_path: Path,
    ) -> tuple[Path, list[dict], list[dict], list[dict], bool]:
        """スライス・segments.json・欠損 WAV 一覧を準備する。

        Returns:
            (work_dir, segments_info, text_segs, missing, is_resume)
        """
        segments = _slice_by_pause_and_period(text)
        if not segments:
            return output_path.parent.parent / "audio_work" / output_path.stem, [], [], [], False

        work_dir = output_path.parent.parent / "audio_work" / output_path.stem
        work_dir.mkdir(parents=True, exist_ok=True)

        segments_info: list[dict] = []
        for i, (seg_text, after) in enumerate(segments):
            segments_info.append({
                "index": i,
                "text": seg_text,
                "after": after,
                "has_text": bool(seg_text),
                "silence_sec": _silence_duration(after),
                "wav_file": f"seg_{i:04d}.wav" if seg_text else None,
            })

        info_path = work_dir / "segments.json"
        is_resume = False
        if info_path.exists():
            try:
                existing = json.loads(info_path.read_text(encoding="utf-8"))
                existing_segs = existing.get("segments", [])
                if len(existing_segs) == len(segments_info) and all(
                    e["text"] == n["text"]
                    for e, n in zip(existing_segs, segments_info)
                ):
                    is_resume = True
            except (json.JSONDecodeError, KeyError):
                pass

        if is_resume:
            print(f"      作業ディレクトリ再利用: audio_work/{work_dir.name}/")
        else:
            for old in work_dir.glob("seg_*.wav"):
                old.unlink(missing_ok=True)
            info_path.write_text(
                json.dumps(
                    {
                        "source": output_path.stem,
                        "total_segments": len(segments_info),
                        "text_segments": sum(
                            1 for s in segments_info if s["has_text"]
                        ),
                        "silence_config": {
                            "pause_long": SILENCE_PAUSE_LONG_SEC,
                            "pause_short": SILENCE_PAUSE_SHORT_SEC,
                            "period": SILENCE_PERIOD_SEC,
                        },
                        "segments": segments_info,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

        text_segs = [s for s in segments_info if s["has_text"]]
        missing = [
            s for s in text_segs
            if not (work_dir / s["wav_file"]).exists()
            or (work_dir / s["wav_file"]).stat().st_size < WAV_MIN_SIZE
        ]
        return work_dir, segments_info, text_segs, missing, is_resume

    # ── メイン生成フロー ────────────────────────────────────

    def _generate_audio(self, text: str, output_path: Path) -> tuple[bool, float]:
        """テキストから MP3 音声を生成する（作業ディレクトリ方式）。

        1. テキストをスライス
        2. 作業ディレクトリに segments.json を保存
        3. 欠損 WAV のみ合成（Fish / VoxCPM / Qwen 远程 batch）
        4. 全 WAV を検証 → 問題あればリトライ
        5. 無音挿入しながら ffmpeg で連結 → MP3 出力

        Returns: (成功フラグ, 音声の再生時間秒)
        """
        work_dir, segments_info, text_segs, missing, _is_resume = self._prepare_work_dir(
            text, output_path
        )
        if not segments_info:
            print("      [警告] 空テキストのためスキップします。")
            return False, 0.0

        info_path = work_dir / "segments.json"
        total_text = len(text_segs)

        if missing:
            print(f"      生成対象: {len(missing)}/{total_text} セグメント")
            self._synthesize_segments(work_dir, missing)
        else:
            print(f"      全 {total_text} セグメントの WAV が存在 → 検証へ")

        # ── 検証 + リトライ ──
        bad, rewrite_eligible = self._validate_wavs(work_dir, text_segs)
        for retry_round in range(MAX_RETRIES):
            if not bad:
                break
            wait_sec = RETRY_WAIT_BEFORE_ROUND_SEC[retry_round]
            print(
                f"      リトライ {retry_round + 1}/{MAX_RETRIES}: "
                f"{len(bad)} セグメント（再生成前に {wait_sec} 秒待機）"
            )
            time.sleep(wait_sec)
            retry_segs = [s for s in text_segs if s["index"] in bad]
            # 2回目以降: 再生時間超過（繰り返し疑い）のセグメントのみテキスト改写
            rewrite_segs = [s for s in retry_segs if s["index"] in rewrite_eligible]
            if retry_round >= 1 and text_llm.is_configured() and rewrite_segs:
                print(
                    f"        テキスト改写（{text_llm.get_model_name('flash')}）: "
                    f"{len(rewrite_segs)} セグメント（再生時間超過のみ）"
                )
                rewritten_count = 0
                for s in rewrite_segs:
                    new_text = _rewrite_segment_for_retry(s["text"])
                    if new_text:
                        s["text"] = new_text
                        rewritten_count += 1
                        print(f"          seg_{s['index']:04d}: 改写済み")
                if rewritten_count > 0:
                    try:
                        meta = json.loads(info_path.read_text(encoding="utf-8"))
                        for seg in meta.get("segments", []):
                            for s in rewrite_segs:
                                if seg["index"] == s["index"]:
                                    seg["text"] = s["text"]
                                    break
                        info_path.write_text(
                            json.dumps(meta, indent=2, ensure_ascii=False),
                            encoding="utf-8",
                        )
                    except (json.JSONDecodeError, OSError) as e:
                        print(f"        [警告] segments.json 更新失敗: {e}")
            for s in retry_segs:
                (work_dir / s["wav_file"]).unlink(missing_ok=True)
            self._synthesize_segments(work_dir, retry_segs, force=True)
            bad, rewrite_eligible = self._validate_wavs(work_dir, text_segs)

        if bad:
            backend_label = {
                "fish": "Fish Audio S2 Pro",
                "qwen": "Qwen3-TTS",
                "voxcpm": "VoxCPM2",
            }.get(self._backend_name, "TTS")
            raise RuntimeError(
                f"検証失敗が {MAX_RETRIES} 回再生成後も解消しませんでした: "
                f"{len(bad)} セグメント（{backend_label} の繰り返し・欠落等の可能性）。"
                "処理を中止します。"
            )

        # ── 合併 ──
        return self._merge_from_work_dir(work_dir, segments_info, output_path)

    # ── WAV 検証 ────────────────────────────────────────────

    def _validate_wavs(
        self,
        work_dir: Path,
        text_segs: list[dict],
    ) -> tuple[set[int], set[int]]:
        """全テキストセグメントの WAV を検証する。

        Returns:
            (bad, rewrite_eligible)
            - bad: 再生成が必要なセグメント index
            - rewrite_eligible: bad のうち再生時間超過（繰り返し疑い）のみ。LLM 改写対象。
        """
        bad: set[int] = set()
        rewrite_eligible: set[int] = set()
        for s in text_segs:
            wav_path = work_dir / s["wav_file"]
            valid, reason, failure_kind = _validate_wav(wav_path, s["text"])
            if not valid:
                bad.add(s["index"])
                if failure_kind == FAILURE_TOO_LONG:
                    rewrite_eligible.add(s["index"])
                print(f"        [NG] seg_{s['index']:04d}: {reason}")
        if not bad:
            print(f"      [検証OK] 全 {len(text_segs)} セグメント正常")
        else:
            ok_count = len(text_segs) - len(bad)
            rewrite_note = (
                f", 改写対象 {len(rewrite_eligible)} 件（超過のみ）"
                if rewrite_eligible
                else ""
            )
            print(
                f"      [検証] {ok_count}/{len(text_segs)} 正常, "
                f"{len(bad)} 件問題あり{rewrite_note}"
            )
        return bad, rewrite_eligible

    # ── ffmpeg 合併 ─────────────────────────────────────────

    def _merge_from_work_dir(
        self,
        work_dir: Path,
        segments_info: list[dict],
        output_path: Path,
    ) -> tuple[bool, float]:
        """作業ディレクトリの WAV を無音挿入しながら連結 → MP3 出力。

        Returns: (成功フラグ, 音声の再生時間秒)
        """
        # 無音 WAV（同じ PCM フォーマットに統一）
        silence_files: dict[str, Path] = {}
        for label, sec in [
            ("pause_long", SILENCE_PAUSE_LONG_SEC),
            ("pause_short", SILENCE_PAUSE_SHORT_SEC),
            ("period", SILENCE_PERIOD_SEC),
        ]:
            p = work_dir / f"silence_{label}.wav"
            if not p.exists():
                _run_ffmpeg([
                    "-f", "lavfi", "-i", f"anullsrc=r={SAMPLE_RATE}:cl=mono",
                    "-t", str(sec),
                    "-acodec", "pcm_s16le",
                    str(p),
                ])
            silence_files[label] = p

        # concat リスト作成
        lines: list[str] = []
        has_audio = False
        for seg in segments_info:
            if seg["has_text"]:
                wav_path = work_dir / seg["wav_file"]
                if wav_path.exists() and wav_path.stat().st_size >= WAV_MIN_SIZE:
                    lines.append(f"file '{wav_path}'")
                    has_audio = True
            if seg["after"] in silence_files:
                lines.append(f"file '{silence_files[seg['after']]}'")

        if not has_audio:
            print("      [エラー] 有効な音声セグメントがありません。")
            return False, 0.0

        # 古い合併結果を削除
        for old_name in ("concat_list.txt", "combined.wav"):
            (work_dir / old_name).unlink(missing_ok=True)

        list_path = work_dir / "concat_list.txt"
        list_path.write_text("\n".join(lines), encoding="utf-8")

        try:
            combined = work_dir / "combined.wav"
            _run_ffmpeg([
                "-f", "concat", "-safe", "0",
                "-i", str(list_path),
                "-c", "copy",
                str(combined),
            ])
            _run_ffmpeg([
                "-i", str(combined),
                "-acodec", "libmp3lame", "-ab", "128k",
                str(output_path),
            ])
            duration = _get_wav_duration_sec(combined)
            dur_str = f" ({duration:.1f}秒)" if duration > 0 else ""
            print(f"      合併完了: {output_path.name}{dur_str}")
            return True, max(duration, 0.0)
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode("utf-8", errors="replace") if e.stderr else ""
            print(f"      [エラー] ffmpeg 連結失敗: {stderr[:300]}")
            return False, 0.0

    # ── メタデータ更新 ─────────────────────────────────────

    @staticmethod
    def _update_article_duration(
        ep_dir: Path, article_order: int, duration_sec: float
    ) -> None:
        """metadata.json の該当記事に duration_sec を書き込む。"""
        meta_path = ep_dir / "metadata.json"
        if not meta_path.exists():
            return
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            for article in meta.get("articles", []):
                if article.get("order") == article_order:
                    article["duration_sec"] = round(duration_sec, 1)
                    break
            else:
                return
            meta_path.write_text(
                json.dumps(meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except (json.JSONDecodeError, OSError) as e:
            print(f"      [警告] メタデータ更新失敗: {e}")

    @staticmethod
    def _update_special_duration(
        ep_dir: Path, kind: str, duration_sec: float
    ) -> None:
        """intro / closing の duration_sec を metadata.json に反映する。

        形式:
          ...,
          "total_chars": ...,
          "estimated_minutes": ...,
          "intro": { "duration_sec": ... },
          "closing": { "duration_sec": ... },
          "articles": [...]
        """
        kind = kind.lower()
        if kind not in {"intro", "closing"}:
            return

        meta_path = ep_dir / "metadata.json"
        if not meta_path.exists():
            return

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"      [警告] メタデータ読込失敗: {e}")
            return

        # 既存の intro / closing 情報を保持しつつ、指定 kind を更新
        existing_intro = meta.get("intro")
        existing_closing = meta.get("closing")

        if kind == "intro":
            intro_obj = {"duration_sec": round(duration_sec, 1)}
            closing_obj = existing_closing
        else:  # closing
            intro_obj = existing_intro
            closing_obj = {"duration_sec": round(duration_sec, 1)}

        new_meta = {}
        inserted = False
        for k, v in meta.items():
            new_meta[k] = v
            if k == "estimated_minutes":
                # estimated_minutes の直後に intro / closing を配置
                if intro_obj is not None:
                    new_meta["intro"] = intro_obj
                if closing_obj is not None:
                    new_meta["closing"] = closing_obj
                inserted = True

        # estimated_minutes が見つからなかった場合は末尾に追加
        if not inserted:
            if intro_obj is not None:
                new_meta["intro"] = intro_obj
            if closing_obj is not None:
                new_meta["closing"] = closing_obj

        try:
            meta_path.write_text(
                json.dumps(new_meta, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as e:
            print(f"      [警告] メタデータ書込失敗: {e}")

    # ── エピソード一括処理 ──────────────────────────────────

    def process_all_episodes(
        self,
        target_episodes: list[str] | None = None,
        target_articles: list[str] | None = None,
    ) -> bool:
        """全エピソードの音声を生成する。"""
        # GENERATE_AUDIO はエピソード単位で episode_progress.json に記録（orchestrate が管理）

        print(
            f"[設定] 参考音: role={TTS_REF_ROLE} ({TTS_REF_DIR.name}/{TTS_REF_AUDIO.name})",
            flush=True,
        )
        if self._backend_name == "fish":
            print(
                f"[設定] TTS: Fish Audio S2 Pro INT8 MLX (remote={FISH_AUDIO_TTS_REMOTE_HOST})",
                flush=True,
            )
        elif self._backend_name == "voxcpm":
            print(
                f"[設定] TTS: VoxCPM2 ({VOXCPM_TTS_MODEL}, remote={VOXCPM_TTS_REMOTE_HOST})",
                flush=True,
            )
            print(
                f"[設定] VoxCPM float16 + torch.compile, "
                f"cfg={VOXCPM_TTS_CFG}, steps={VOXCPM_TTS_STEPS}",
                flush=True,
            )
            print(
                "[設定] Prompt Cache 有効（参考音声エンコード 1 回のみ）",
                flush=True,
            )
        elif self._backend_name == "qwen":
            print(
                f"[設定] TTS: Qwen3-TTS ({QWEN_TTS_MODEL}, remote={QWEN_TTS_REMOTE_HOST})",
                flush=True,
            )
            print(
                f"[設定] Qwen batch={QWEN_TTS_BATCH_SIZE}, dtype={QWEN_TTS_DTYPE}",
                flush=True,
            )
        print(
            "[設定] 进度输出: 本进程 stdout → orchestrate 时写入 p_audio.log；"
            "主终端每 5 秒刷新末尾日志",
            flush=True,
        )
        episodes_dir = self.output_dir / "episodes"
        if not episodes_dir.exists():
            print("[エラー] エピソードディレクトリが見つかりません。")
            return False

        episode_dirs = sorted(d for d in episodes_dir.iterdir() if d.is_dir())
        if target_episodes:
            normalized = {e.zfill(2) for e in target_episodes}
            episode_dirs = [d for d in episode_dirs if d.name in normalized]
            print(f"[情報] 対象エピソード: {', '.join(sorted(normalized))}")
            if not episode_dirs:
                print("[警告] 指定されたエピソードが見つかりません。")
                return False

        # 全タスクを事前に列挙
        all_tasks: list[tuple[Path, Path, Path]] = []   # (ep_dir, tts_file, audio_dir)
        for ep_dir in episode_dirs:
            tts_dir = ep_dir / "tts"
            if not tts_dir.exists():
                continue
            audio_dir = ep_dir / "audio"
            tts_files = sorted(tts_dir.glob("*.txt"), key=_tts_file_sort_key)
            if target_articles:
                # intro/closing はそのまま、数値はゼロ埋め 2 桁に正規化
                normalized_articles: set[str] = set()
                for a in target_articles:
                    a_str = str(a).strip()
                    if not a_str:
                        continue
                    if a_str.lower() in {"intro", "closing"}:
                        normalized_articles.add(a_str.lower())
                    else:
                        normalized_articles.add(a_str.zfill(2))
                tts_files = [f for f in tts_files if f.stem.lower() in normalized_articles]
            for f in tts_files:
                all_tasks.append((ep_dir, f, audio_dir))

        if not all_tasks:
            print("[情報] 対象となるTTSファイルがありません。")
            return True

        print(f"[情報] 対象ファイル: {len(all_tasks)} 個\n")

        # Fish Audio: 全タスクの欠損セグメントを1回の远程 batch で合成
        if self._backend_name == "fish" and self.fish_engine is not None:
            from fish_audio_batch import FishAudioSegmentJob

            pre_jobs: list[FishAudioSegmentJob] = []
            for _ep_dir, tts_file, audio_dir in all_tasks:
                audio_path = audio_dir / f"{tts_file.stem}.mp3"
                if audio_path.exists():
                    continue
                text = tts_file.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                work_dir, _segments_info, _text_segs, missing, _ = self._prepare_work_dir(
                    text, audio_path
                )
                for seg in missing:
                    pre_jobs.append(FishAudioSegmentJob(work_dir=work_dir, seg=seg))
            if pre_jobs:
                print(
                    f"[FishAudio] 预扫描: {len(pre_jobs)} 个待合成片段，"
                    f"启动单次远程 batch（INT8 + fp16 + compile）\n",
                    flush=True,
                )
                self.fish_engine.synthesize_segments(pre_jobs)
                print(flush=True)

        # VoxCPM: 全タスクの欠損セグメントを1回の远程 batch で合成
        elif self._backend_name == "voxcpm" and self.voxcpm_engine is not None:
            from voxcpm_batch import VoxCPMSegmentJob
            pre_jobs: list[VoxCPMSegmentJob] = []
            for _ep_dir, tts_file, audio_dir in all_tasks:
                audio_path = audio_dir / f"{tts_file.stem}.mp3"
                if audio_path.exists():
                    continue
                text = tts_file.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                work_dir, _segments_info, _text_segs, missing, _ = self._prepare_work_dir(
                    text, audio_path
                )
                for seg in missing:
                    pre_jobs.append(VoxCPMSegmentJob(work_dir=work_dir, seg=seg))
            if pre_jobs:
                print(
                    f"[VoxCPM] 预扫描: {len(pre_jobs)} 个待合成片段，"
                    f"启动单次远程 batch（float16 + compile + Prompt Cache）\n",
                    flush=True,
                )
                self.voxcpm_engine.synthesize_segments(pre_jobs)
                print(flush=True)

        # Qwen: 全タスクの欠損セグメントを1回の远程 batch で合成（モデル・prompt 常驻）
        elif self._backend_name == "qwen" and self.qwen_engine is not None:
            from qwen_tts_batch import QwenSegmentJob
            pre_jobs: list[QwenSegmentJob] = []
            for _ep_dir, tts_file, audio_dir in all_tasks:
                audio_path = audio_dir / f"{tts_file.stem}.mp3"
                if audio_path.exists():
                    continue
                text = tts_file.read_text(encoding="utf-8")
                if not text.strip():
                    continue
                work_dir, _segments_info, _text_segs, missing, _ = self._prepare_work_dir(
                    text, audio_path
                )
                for seg in missing:
                    pre_jobs.append(QwenSegmentJob(work_dir=work_dir, seg=seg))
            if pre_jobs:
                print(
                    f"[Qwen] 预扫描: {len(pre_jobs)} 个待合成片段，"
                    f"启动单次远程 batch（batch={QWEN_TTS_BATCH_SIZE}）\n",
                    flush=True,
                )
                self.qwen_engine.synthesize_segments(pre_jobs)
                print(flush=True)

        total_generated = 0
        total_skipped = 0
        total_failed = 0
        current_ep: str | None = None

        for task_idx, (ep_dir, tts_file, audio_dir) in enumerate(all_tasks, 1):
            if ep_dir.name != current_ep:
                current_ep = ep_dir.name
                print(f"── エピソード {current_ep} ──")

            stem = tts_file.stem
            is_numeric_article = stem.isdigit()

            audio_dir.mkdir(exist_ok=True)
            audio_path = audio_dir / f"{tts_file.stem}.mp3"

            article_order = int(stem) if is_numeric_article else None
            special_kind = stem.lower() if stem.lower() in {"intro", "closing"} else None

            if audio_path.exists():
                duration = _get_wav_duration_sec(audio_path)
                if duration > 0:
                    if is_numeric_article and article_order is not None:
                        self._update_article_duration(ep_dir, article_order, duration)
                    elif special_kind is not None:
                        self._update_special_duration(ep_dir, special_kind, duration)
                print(
                    f"  [{task_idx}/{len(all_tasks)}] "
                    f"スキップ（既存）: {tts_file.name}"
                )
                total_skipped += 1
                continue

            text = tts_file.read_text(encoding="utf-8")
            if not text.strip():
                print(
                    f"  [{task_idx}/{len(all_tasks)}] "
                    f"[エラー] 空の TTS ファイル: {tts_file.name}"
                )
                print("\n[中止] 空の TTS テキストのため処理を終了します。")
                sys.exit(1)

            text_bytes = len(text.encode("utf-8"))
            print(
                f"  [{task_idx}/{len(all_tasks)}] "
                f"生成中: {tts_file.name} ({text_bytes:,} bytes)"
            )

            try:
                ok, duration = self._generate_audio(text, audio_path)
                if ok:
                    total_generated += 1
                    if duration > 0:
                        if is_numeric_article and article_order is not None:
                            self._update_article_duration(ep_dir, article_order, duration)
                        elif special_kind is not None:
                            self._update_special_duration(ep_dir, special_kind, duration)
                    print(f"      → 完了: {audio_path.name}")
                else:
                    total_failed += 1
                    print("      → [エラー] 音声生成失敗")
                    print("\n[中止] エラーが発生したため処理を終了します。")
                    sys.exit(1)
            except RuntimeError as e:
                print(f"      → [エラー] {e}")
                print("\n[中止] 検証失敗の連続再生成上限に達したため終了します。")
                sys.exit(1)
            except Exception as e:
                print(f"      → [エラー] {e}")
                print("\n[中止] エラーが発生したため処理を終了します。")
                sys.exit(1)

        print(
            f"\n[完了] 音声生成完了: "
            f"生成 {total_generated}, スキップ {total_skipped}, "
            f"失敗 {total_failed}"
        )

        targeted_ep_dirs = sorted({ep_dir for ep_dir, _, _ in all_tasks})
        all_complete = True
        for ep_dir in targeted_ep_dirs:
            missing = episode_audio_missing(ep_dir)
            if missing:
                print(
                    f"[エラー] EP {ep_dir.name} 音声ファイル不足: "
                    f"{', '.join(missing)}"
                )
                all_complete = False
        if not all_complete:
            return False
        return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TTS（Fish Audio S2 Pro / Qwen3-TTS / VoxCPM2）で音声ファイルを生成します。"
    )
    parser.add_argument("issue_date", help="雑誌の号数（YYYY-MM-DD）")
    parser.add_argument(
        "--episode", "-e", nargs="+", help="処理するエピソード番号（例: 01 02）"
    )
    parser.add_argument(
        "--article", "-a", nargs="+", help="処理する記事番号（例: 01 02）"
    )
    parser.add_argument(
        "--tts-backend",
        choices=["fish", "qwen", "voxcpm"],
        default=None,
        help="TTS: fish / qwen / voxcpm。未指定時は環境変数 TTS_BACKEND（既定 fish）。",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="GUIエディタを起動してセグメントを可視化・編集する。",
    )
    args = parser.parse_args()

    if args.gui:
        from audio_editor_gui import AudioEditorApp
        app = AudioEditorApp(
            args.issue_date,
            episode=args.episode[0] if args.episode else None,
            article=args.article[0] if args.article else None,
            backend=args.tts_backend,
        )
        app.mainloop()
    else:
        generator = AudioGenerator(
            args.issue_date,
            backend=args.tts_backend,
        )
        generator.process_all_episodes(
            target_episodes=args.episode,
            target_articles=args.article,
        )

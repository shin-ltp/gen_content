"""
音声生成モジュール
Google Cloud Text-to-Speech API（Chirp 3 HD）を使用してTTSテキストから音声を生成する。

Chirp 3 HD の利用:
  - 音声名は {locale}-Chirp3-HD-{VoiceName} 形式（例: ja-JP-Chirp3-HD-Algieba）
  - 休止は markup の [pause short] / [pause long] で指定（text だとタグが読み上げられる）
  - SSML を使う場合は input を ssml にし <speak> で囲む

長文対策として、
  - テキストはおおよそ 2,000バイトごとに「適切な位置」で分割（段落 → 文単位）
  - 各チャンクを個別に合成し、メモリ上で連結して1つの音声ファイルとして保存する

末尾が速く聞こえる場合の要因と対策:
  - 最後のチャンクが短い文の羅列になり、文間の間が詰まる → speaking_rate を 0.95 に固定して全体のテンポをやや落とし、ばらつきを軽減
  - チャンク境界で無音がなく詰まって聞こえる → [pause short] 等で区切りを維持

参照: https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
"""
import re
import sys
import io
import time
from pathlib import Path

from google.cloud import texttospeech
from google.api_core import exceptions as google_exceptions
from io import BytesIO
from pydub import AudioSegment

from config import (
    TTS_VOICE_NAME,
    TTS_LANGUAGE_CODE,
    get_issue_dir,
)
from state_manager import StateManager

# Windows環境でのUnicodeEncodeErrorを防止
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


class AudioGenerator:
    """Chirp 3 HD を用いた音声生成クラス（チャンク分割 & 結合）"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        # 通常の TTS クライアント
        self.client = texttospeech.TextToSpeechClient()

    # Chirp 3 HD では prompt は非対応。トーンは音声名（VOICE_NAME）で選ぶ。
    # 必要に応じて SSML や markup（[pause short] 等）で間や発音を制御可能。
    # 参照: https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd

    # Chirp 3 は「1文」が長いと 400 エラーを返す。句点で区切った後も長い文は「、」でさらに分割する。
    # 280 でも「しかし...」等でエラーになるため、より厳しく 200 に設定。
    MAX_SENTENCE_BYTES = 180

    # <break time="Xs" /> を Chirp 3 の markup に変換（prepare_tts は [pause] を直接出力するが、旧ファイル互換のため残す）
    _BREAK_TO_MARKUP = [
        (re.compile(r'<break\s+time="2\.0s"\s*/>', re.I), "[pause long]"),
        (re.compile(r'<break\s+time="1\.5s"\s*/>', re.I), "[pause long]"),
        (re.compile(r'<break\s+time="0\.7s"\s*/>', re.I), "[pause short]"),
        (re.compile(r'<break\s+time="(\d+(?:\.\d+)?)s"\s*/>', re.I), "[pause]"),  # その他
    ]

    def _normalize_break_to_markup(self, text: str) -> str:
        """TTS テキスト内の <break time="Xs" /> を Chirp 3 の [pause short]/[pause long] に置換する。"""
        out = text
        for pattern, repl in self._BREAK_TO_MARKUP:
            out = pattern.sub(repl, out)
        return out

    def _split_long_sentence(self, sentence: str) -> list[str]:
        """1文が MAX_SENTENCE_BYTES を超える場合、「、」で分割して短い文のリストにする。"""
        enc = sentence.encode("utf-8")
        if len(enc) <= self.MAX_SENTENCE_BYTES:
            return [sentence]
        parts: list[str] = []
        for fragment in sentence.split("、"):
            if not fragment.strip():
                continue
            if not parts:
                parts.append(fragment)
                continue
            cand = parts[-1] + "、" + fragment
            if len(cand.encode("utf-8")) <= self.MAX_SENTENCE_BYTES:
                parts[-1] = cand
            else:
                parts.append(fragment)
        return [p.strip() for p in parts if p.strip()]

    def _is_pause_markup(self, s: str) -> bool:
        """Chirp 3 の [pause short]/[pause long]/[pause] のみのセグメントかどうか。"""
        t = s.strip()
        return bool(re.match(r"^\[pause(\s+short|\s+long)?\]$", t))

    def _paragraph_to_segments(self, para: str) -> list[str]:
        """段落を「短い文」のリストに分解する（Chirp 3 の文長制限に合わせる）。"""
        segments: list[str] = []
        for sent in para.replace("。", "。\n").split("\n"):
            sent = sent.strip()
            if not sent:
                continue
            for s in self._split_long_sentence(sent):
                if self._is_pause_markup(s):
                    segments.append(s.strip())
                elif not s.endswith("。"):
                    segments.append(s + "。")
                else:
                    segments.append(s)
        return segments

    def _split_text_into_chunks(self, text: str, max_bytes: int = 2000) -> list[str]:
        """テキストを max_bytes 以下のチャンクに分割する。

        まず <break> を Chirp 3 の [pause] に置換し、全段落を「短い文」セグメントに分解してから
        セグメントを max_bytes 以下にまとめる。
        """
        # <break time="Xs" /> を [pause short]/[pause long] に変換（読み上げ防止）
        text = self._normalize_break_to_markup(text)
        # 全テキストを段落 → 短い文セグメントに分解
        all_segments: list[str] = []
        for para in text.split("\n\n"):
            para = para.strip()
            if not para:
                continue
            all_segments.extend(self._paragraph_to_segments(para))

        if not all_segments:
            return [text] if text.strip() else []

        # セグメントを max_bytes 以下のチャンクに結合。
        # 句号「。」の直後にスペースを挟むと、Chirp 3 が文境界を認識しやすく、
        # 句間の間が詰まって聞こえる問題を軽減する（[pause] の前にはスペースを入れない）。
        chunks: list[str] = []
        current = ""
        for seg in all_segments:
            if not current:
                cand = seg
            else:
                need_space = (
                    current.rstrip().endswith("。")
                    and seg.strip()
                    and not self._is_pause_markup(seg)
                )
                cand = (current + (" " if need_space else "") + seg).strip()
            if len(cand.encode("utf-8")) <= max_bytes:
                current = cand
            else:
                if current:
                    chunks.append(current)
                current = seg
        if current:
            chunks.append(current)

        return chunks if chunks else [text]

    def _synthesize_chunk(self, text: str) -> bytes:
        """1チャンクのテキストを Chirp 3 HD で合成する。

        Chirp 3 HD: 休止は markup の [pause short]/[pause long] のみ有効（text だと読み上げられる）。
        チャンクに [pause が含まれる場合は SynthesisInput(markup=)、それ以外は text= を使用。
        参照: https://docs.cloud.google.com/text-to-speech/docs/chirp3-hd
        """
        if "[pause" in text:
            synthesis_input = texttospeech.SynthesisInput(markup=text)
        else:
            synthesis_input = texttospeech.SynthesisInput(text=text)

        voice = texttospeech.VoiceSelectionParams(
            language_code=TTS_LANGUAGE_CODE,
            name=TTS_VOICE_NAME,
        )

        # 語速を固定（0.95）で末尾の「速く聞こえる」を軽減
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=0.95,
        )

        # 一時的な 5xx エラー（502/503 等）に対してはリトライする
        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = self.client.synthesize_speech(
                    input=synthesis_input, voice=voice, audio_config=audio_config
                )
                return response.audio_content
            except google_exceptions.GoogleAPICallError as e:
                message = str(e)
                # ステータスコードやメッセージに 502/503 が含まれる場合は再試行
                if ("502" in message or "503" in message) and attempt < max_retries:
                    wait = 2 ** attempt
                    print(
                        f"        [警告] 一時的なエラーが発生しました（{message}）。"
                        f" {wait}秒待機してリトライします... ({attempt}/{max_retries})"
                    )
                    time.sleep(wait)
                    last_error = e
                    continue
                last_error = e
                break
            except Exception as e:  # その他のエラーは即座に失敗
                last_error = e
                break

        # ここまで来た場合はリトライしても失敗
        raise last_error if last_error is not None else RuntimeError(
            "Unknown error in _synthesize_chunk"
        )

    def _generate_audio(self, text: str, output_path: Path) -> bool:
        """テキストを音声に変換して保存する。

        - 約2,000バイトごとにチャンク分割
        - 各チャンクを個別に合成し、メモリ上で連結して1本のMP3として保存
        """
        chunks = self._split_text_into_chunks(text, max_bytes=2000)

        if not chunks:
            print("      [警告] 空テキストのためスキップします。")
            return False

        if len(chunks) == 1:
            audio_content = self._synthesize_chunk(chunks[0])
            with open(output_path, "wb") as f:
                f.write(audio_content)
            return True

        print(f"      テキストを{len(chunks)}チャンクに分割して合成中...")
        combined = AudioSegment.empty()
        for i, chunk in enumerate(chunks, start=1):
            audio_bytes = self._synthesize_chunk(chunk)
            segment = AudioSegment.from_mp3(BytesIO(audio_bytes))
            combined += segment
            print(f"        チャンク {i}/{len(chunks)} 完了")
            time.sleep(0.3)  # レート制限対策

        combined.export(str(output_path), format="mp3")
        return True

    def process_all_episodes(
        self,
        target_episodes: list[str] | None = None,
        target_articles: list[str] | None = None,
    ) -> bool:
        """全エピソードの音声を生成する（Chirp 3 HD + チャンク分割）。

        target_episodes / target_articles を指定した場合は、
        該当するエピソード・記事のみ音声を生成する。
        例: episode="01", article="01" で 01/tts/01.txt のみ生成。
        """
        self.state.start_step("GENERATE_AUDIO")

        print(f"[設定] Chirp 3 HD / 音声: {TTS_VOICE_NAME}, 言語: {TTS_LANGUAGE_CODE}")

        episodes_dir = self.output_dir / "episodes"
        if not episodes_dir.exists():
            print("[エラー] エピソードディレクトリが見つかりません。")
            return False

        episode_dirs = sorted(d for d in episodes_dir.iterdir() if d.is_dir())

        # エピソード指定がある場合はフィルタリング（"1" と "01" の両方を許容）
        if target_episodes:
            normalized = {e.zfill(2) for e in target_episodes}
            episode_dirs = [d for d in episode_dirs if d.name in normalized]
            print(f"[情報] 対象エピソード: {', '.join(sorted(normalized))}")
            if not episode_dirs:
                print("[警告] 指定されたエピソードが見つかりませんでした。")
                self.state.complete_step("GENERATE_AUDIO", {"total_generated": 0})
                return False

        total_generated = 0

        for ep_dir in episode_dirs:
            tts_dir = ep_dir / "tts"
            if not tts_dir.exists():
                print(f"[警告] TTSテキストが見つかりません: {ep_dir.name}")
                continue

            audio_dir = ep_dir / "audio"
            audio_dir.mkdir(exist_ok=True)

            tts_files = sorted(tts_dir.glob("*.txt"))

            # 記事番号指定がある場合はフィルタリング（"1" と "01" の両方を許容）
            if target_articles:
                normalized_articles = {a.zfill(2) for a in target_articles}
                tts_files = [f for f in tts_files if f.stem in normalized_articles]

            if not tts_files:
                print(f"\n[情報] エピソード {ep_dir.name}: 対象となるTTSファイルがありません。")
                continue

            print(f"\n[処理中] エピソード {ep_dir.name}: {len(tts_files)}個の音声を生成")

            for tts_file in tts_files:
                audio_path = audio_dir / f"{tts_file.stem}.mp3"

                # 既に生成済みの場合はスキップ
                if audio_path.exists():
                    print(f"    スキップ（既存）: {tts_file.name}")
                    continue

                with open(tts_file, "r", encoding="utf-8") as f:
                    text = f.read()

                if not text.strip():
                    print(f"    スキップ（空ファイル）: {tts_file.name}")
                    continue

                text_bytes = len(text.encode("utf-8"))
                print(f"    生成中: {tts_file.name} ({text_bytes:,}バイト)")

                try:
                    if not self._generate_audio(text, audio_path):
                        print("      → [エラー] 音声生成に失敗したためスキップします。")
                        continue
                    total_generated += 1
                    print(f"      → 完了: {audio_path.name}")
                except Exception as e:
                    print(f"      → [エラー] {e}")
                    continue

                # APIレート制限対策（念のため少し待つ）
                time.sleep(0.5)

        self.state.complete_step("GENERATE_AUDIO", {"total_generated": total_generated})
        print(f"\n[完了] 音声生成完了: {total_generated}ファイル")
        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Chirp 3 HD を用いて音声ファイルを生成します。",
    )
    parser.add_argument("issue_date", help="雑誌の号数（YYYY-MM-DD）")
    parser.add_argument(
        "--episode",
        "-e",
        nargs="+",
        help="処理するエピソード番号（例: 01 02）。省略時は全エピソード。",
    )
    parser.add_argument(
        "--article",
        "-a",
        nargs="+",
        help="処理する記事番号（例: 01 02）。省略時は全記事。",
    )

    args = parser.parse_args()

    generator = AudioGenerator(args.issue_date)
    generator.process_all_episodes(
        target_episodes=args.episode,
        target_articles=args.article,
    )

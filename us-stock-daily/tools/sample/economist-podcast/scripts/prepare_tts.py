"""
TTS用テキスト準備モジュール
メタデータを元に各エピソードの記事を処理し、TTS用テキストファイルを生成する。
PREPARE_TTS_TXT_GENERATION_PROVIDER（既定: gemini + GEMINI_FLASH_MODEL）で導入・転換文の生成、
英語のカタカナ化、口語化を行う。
出力は Chirp 3 HD 用に最適化し、休止は [pause short] / [pause long] で指定する。

エピソードの構成:
  導入パート（intro.txt）→ エピソード紹介（発行日・記事数）→ 全記事の一言紹介（one_line_intro）読み上げ → 定型文＋視聴案内
  最初の記事（01.txt）→ 本文
  2記事目以降 → 転換文（前記事からの自然な橋渡し）+ 本文
  エンディング（最終ファイル）→ エピソード全体の締めメッセージ
"""
import sys
import json
import re
import io
import time
from collections import Counter
from pathlib import Path
import argparse

# Windows環境でのUnicodeEncodeErrorを防止
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config import (
    SECTION_JP_MAPPING,
    PREPARE_TTS_TXT_GENERATION_PROVIDER,
    PREPARE_TTS_API_MIN_INTERVAL_SEC,
    GEMINI_FLASH_MODEL,
    ensure_section_mappings,
    get_issue_dir,
)
from state_manager import StateManager
import text_llm


class TTSTextPreparer:
    """TTS用テキスト準備クラス（Chirp 3 HD 用 [pause] 出力）"""

    # Chirp 3 HD の休止は markup の [pause short] / [pause long] で指定（text だと読み上げられる）
    PAUSE_SHORT = "[pause short]"
    PAUSE_LONG = "[pause long]"

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.articles_dir = self.output_dir / "articles"
        self._tts_llm_provider = PREPARE_TTS_TXT_GENERATION_PROVIDER

    def _tts_llm_provider_label(self) -> str:
        label = text_llm.provider_label(self._tts_llm_provider)
        if self._tts_llm_provider == "gemini":
            return f"{label} ({GEMINI_FLASH_MODEL})"
        return label

    @staticmethod
    def _wait_for_rate_limit_after_call(elapsed_sec: float) -> None:
        """Gemini 15 RPM 制限対策: 連続呼び出しの最小間隔を空ける。"""
        wait_sec = PREPARE_TTS_API_MIN_INTERVAL_SEC - elapsed_sec
        if wait_sec > 0:
            print(
                f"    [レート制限] {wait_sec:.1f} 秒待機"
                f"（{PREPARE_TTS_API_MIN_INTERVAL_SEC:.0f} 秒/回）..."
            )
            time.sleep(wait_sec)

    # ================================================================
    # ヘルパーメソッド
    # ================================================================

    # 括弧内が「読み」ではなく説明等の場合は置換しない（ひらがなのみでも黒リスト）
    _READING_BLACKLIST = frozenset({"なし", "など"})

    @staticmethod
    def _strip_pronunciation_parentheses(text: str) -> str:
        """漢語の後ろの読み括弧「語（読み）」を「読み」だけに置換し、TTSで二重に読まないようにする。
        例: 国防総省（こくぼうそうしょう）→ こくぼうそうしょう
        括弧内がひらがな・カタカナ・・ー／のみで2文字以上かつ黒リストにない場合のみ置換する。
        """
        # 括弧内が「読み」とみなせるパターン: 漢字始まりの語の直後（ひらがな読み）のみ置換
        # 語は漢字で始まるものに限定し、「と相違（そうい）」の「と」が消えないようにする
        pattern = re.compile(
            r"([\u4e00-\u9fff]"  # 漢字で始まる
            r"[^\n（。、！？]*?)"  # 語の続き（句読点を含まない・非貪欲）
            r"（"  # 全角開き括弧
            r"([ぁ-んァ-ン・ー／ 　]+?)"  # 読み（ひらがな・カタカナ・中黒・長音・スラッシュ・空白）
            r"）"  # 全角閉じ括弧
        )

        def repl(m: re.Match) -> str:
            reading = m.group(2).strip()
            if reading in TTSTextPreparer._READING_BLACKLIST:
                return m.group(0)
            return reading

        return pattern.sub(repl, text)

    @staticmethod
    def _slice_by_pause_and_period(
        text: str,
    ) -> list[tuple[str, str | None]]:
        """[pause long], [pause short], 。, ？ でスライスする（generate_audio の分片規則と同一）。
        返却: [(セグメントテキスト, 直後の区切り種別), ...]
        区切り種別は "pause_long" | "pause_short" | "period" | None。"""
        segments: list[tuple[str, str | None]] = []
        i = 0
        pl, ps = "[pause long]", "[pause short]"
        while i < len(text):
            next_long = text.find(pl, i)
            next_short = text.find(ps, i)
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

            if min_pos > len(text):
                seg_text = text[i:].strip()
                if seg_text:
                    segments.append((seg_text, None))
                break

            if next_long <= next_short and next_long <= next_period and next_long <= next_qmark:
                seg_text = text[i:next_long].strip()
                # 空セグメントでも追加し、直後の [pause long] を出力で失わない
                segments.append((seg_text, "pause_long"))
                i = next_long + len(pl)
            elif next_short <= next_long and next_short <= next_period and next_short <= next_qmark:
                seg_text = text[i:next_short].strip()
                # 空セグメントでも追加し、直後の [pause short] を出力で失わない
                segments.append((seg_text, "pause_short"))
                i = next_short + len(ps)
            elif next_period <= next_qmark:
                seg_text = text[i : next_period + 1].strip()
                if seg_text:
                    segments.append((seg_text, "period"))
                i = next_period + 1
            else:
                seg_text = text[i : next_qmark + 1].strip()
                if seg_text:
                    segments.append((seg_text, "period"))
                i = next_qmark + 1

        return segments

    def _insert_pause_in_long_paragraphs(
        self,
        text: str,
        max_chars: int = 120,
    ) -> str:
        """[pause long]/[pause short]/。/？で分割した「分片」のうち、長さがmax_charsを超えるものだけ、
        「、」の位置で2分割し、間に[pause short]を挿入する。分割点は段落の中間位置に最も近い「、」を用いる。
        既存の区切りで分かれた短い分片には触れない。"""

        segments = self._slice_by_pause_and_period(text)
        result_parts: list[str] = []

        for seg_text, delim in segments:
            if len(seg_text) <= max_chars:
                result_parts.append(seg_text)
            else:
                # 中間位置に最も近い「、」で分割（前後の偏りを避ける）
                mid = len(seg_text) // 2
                comma_positions = [i for i, c in enumerate(seg_text) if c == "、"]
                split_pos = (
                    min(comma_positions, key=lambda i: abs(i - mid))
                    if comma_positions
                    else -1
                )
                if split_pos == -1:
                    result_parts.append(seg_text)
                else:
                    first = seg_text[: split_pos + 1]
                    second = seg_text[split_pos + 1 :].lstrip()
                    result_parts.append(first)
                    result_parts.append(self.PAUSE_SHORT)
                    if second:
                        result_parts.append(second)

            if delim == "pause_long":
                result_parts.append(self.PAUSE_LONG)
            elif delim == "pause_short":
                result_parts.append(self.PAUSE_SHORT)
            # delim == "period" or None: 区切りはセグメントに含まれているか不要

        return "\n".join(result_parts)

    def _format_issue_date_ja(self) -> str:
        """発行日を日本語表記に変換する（例: 2026-02-07 → 2月7日）"""
        parts = self.issue_date.split("-")
        if len(parts) == 3:
            month = int(parts[1])
            day = int(parts[2])
            return f"{month}月{day}日"
        return self.issue_date

    @staticmethod
    def _ensure_ending_punctuation(text: str) -> str:
        """文末に句読点がない場合は「。」を付加する（TTSの停頓を確保）"""
        if not text:
            return text
        if text[-1] not in ("。", "？", "！", "…"):
            return text + "。"
        return text

    @staticmethod
    def _spoken_year_19xx(year: int) -> str:
        """1900–1999 を TTS 用読み上げ表記に変換（例: 1990 → 千九百九十年）。"""
        if year < 1900 or year > 1999:
            raise ValueError(year)
        remainder = year - 1900
        if remainder == 0:
            return "千九百年"
        digits = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
        if remainder < 10:
            return f"千九百{digits[remainder]}年"
        if remainder < 20:
            ones = digits[remainder % 10]
            return f"千九百十{ones}年"
        tens, ones = divmod(remainder, 10)
        tens_part = [
            "",
            "十",
            "二十",
            "三十",
            "四十",
            "五十",
            "六十",
            "七十",
            "八十",
            "九十",
        ][tens]
        return f"千九百{tens_part}{digits[ones]}年"

    @staticmethod
    def _convert_19xx_years_for_tts(text: str) -> str:
        """西暦 19XX（および 19XX年・19XX年代）を千九百…形式に置換する。"""
        if not text:
            return text

        def repl(m: re.Match) -> str:
            year = int(m.group(1))
            suffix = m.group(2) or ""
            spoken = TTSTextPreparer._spoken_year_19xx(year)
            if suffix == "年代":
                return spoken[:-1] + "年代"
            if suffix == "年":
                return spoken
            return spoken

        return re.sub(r"(?<![0-9])(19\d{2})(年|年代)?(?![0-9])", repl, text)

    # 一覧番号 (1)、（2）、… の TTS 読み（アラビア数字の誤読防止）
    _LIST_NUMBER_ONES_KATAKANA = (
        "",
        "イチ",
        "ニ",
        "サン",
        "ヨン",
        "ゴ",
        "ロク",
        "シチ",
        "ハチ",
        "キュウ",
    )

    @classmethod
    def _int_to_katakana_list_number(cls, n: int) -> str:
        """TTS 用の番号読み（1→イチ, 10→ジュウ, 11→ジュウイチ, 20→ニジュウ …）。"""
        ones = cls._LIST_NUMBER_ONES_KATAKANA
        if n <= 0:
            return str(n)
        if n < 10:
            return ones[n]
        if n < 20:
            return "ジュウ" if n == 10 else "ジュウ" + ones[n % 10]
        if n < 100:
            tens, rem = divmod(n, 10)
            spoken = ones[tens] + "ジュウ"
            if rem:
                spoken += ones[rem]
            return spoken
        return str(n)

    _LIST_NUMBER_PARENS_RE = re.compile(
        r"(?:\(|（)(\d{1,2})(?:\)|）)(?=[、,])"
    )

    @classmethod
    def _convert_list_number_parentheses_for_tts(cls, text: str) -> str:
        """(1)、（2）、… を イチ、ニ、… に置換し、括弧を除去して番号の読みを統一する。"""

        def repl(m: re.Match) -> str:
            return cls._int_to_katakana_list_number(int(m.group(1)))

        return cls._LIST_NUMBER_PARENS_RE.sub(repl, text)

    def _postprocess_tts_text(self, text: str) -> str:
        """TTS 出力の後処理（読み括弧除去の後に適用）。"""
        text = self._strip_pronunciation_parentheses(text)
        text = self._convert_list_number_parentheses_for_tts(text)
        text = self._convert_19xx_years_for_tts(text)
        return self._insert_pause_in_long_paragraphs(text, max_chars=120)

    def _format_sections_natural(self, sections_jp_list: list) -> str:
        """セクション名のリストを自然な日本語の列挙形式にする
        例: ["アジア"] → "アジア"
        例: ["アジア", "米国"] → "アジアと米国"
        例: ["アジア", "米国", "ビジネス"] → "アジア、米国とビジネス"
        """
        if not sections_jp_list:
            return ""
        if len(sections_jp_list) == 1:
            return sections_jp_list[0]
        if len(sections_jp_list) == 2:
            return f"{sections_jp_list[0]}と{sections_jp_list[1]}"
        return "、".join(sections_jp_list[:-1]) + f"と{sections_jp_list[-1]}"

    def _build_intro_opening_fixed(
        self, date_ja: str, sections_jp_list: list, article_count: int
    ) -> str:
        """intro.txt の冒頭を固定句式で構築する
        本日は、ザ・エコノミスト{日期}号「{section_1}」、「{section_2}」のセクションより、計{article_num}篇の記事をご用意いたしました。
        """
        if not sections_jp_list:
            sections_part = "のセクションより"
        elif len(sections_jp_list) == 1:
            sections_part = f"「{sections_jp_list[0]}」のセクションより"
        elif len(sections_jp_list) == 2:
            sections_part = f"「{sections_jp_list[0]}」、「{sections_jp_list[1]}」のセクションより"
        else:
            sections_part = f"「{sections_jp_list[0]}」、「{sections_jp_list[1]}」などのセクションより"
        return f"本日は、ザ・エコノミスト{date_ja}号{sections_part}、計{article_count}篇の記事をご用意いたしました。"

    # ================================================================
    # エンディングメッセージ
    # ================================================================

    def _build_closing_message(self, sections_jp_list: list) -> str:
        """エピソードのエンディングメッセージを構築する（定型テンプレート）"""
        date_ja = self._format_issue_date_ja()
        sections_text = self._format_sections_natural(sections_jp_list)

        return (
            f"{self.PAUSE_LONG}\n"
            f"いかがでしたか？ 国内のニュースだけでは見えてこない、世界の本質的な流れ。"
            f" 少し違う角度から物事を見るだけで、日常の景色も変わって見えるかもしれません。\n"
            f"{self.PAUSE_SHORT}\n"
            f"本日、ザ・エコノミスト{date_ja}号、"
            f"{sections_text}セクションの記事をお届けしました。"
            f"他のセクションも気になる方は是非チャンネルのホーム画面からチェックしてください。\n"
        )

    # ================================================================
    # TTS変換（テキスト生成 LLM）
    # ================================================================

    def _llm_plain_text(self, prompt: str) -> str:
        """PREPARE_TTS_TXT_GENERATION_PROVIDER（既定: gemini + GEMINI_FLASH_MODEL）で本文を生成する。"""
        provider_label = self._tts_llm_provider_label()
        if not text_llm.is_configured(self._tts_llm_provider):
            print(
                f"    [エラー] テキスト生成 API が未設定です"
                f"（{text_llm.required_env_hint(self._tts_llm_provider)}）"
            )
            return ""

        call_start = time.monotonic()
        try:
            text = text_llm.generate_text(
                prompt,
                tier="flash",
                provider_override=self._tts_llm_provider,
            )
        except Exception as e:
            print(f"    [エラー] {provider_label} テキスト生成失敗: {e}")
            return ""

        if PREPARE_TTS_API_MIN_INTERVAL_SEC > 0:
            self._wait_for_rate_limit_after_call(time.monotonic() - call_start)

        if not (text or "").strip():
            print(f"    [エラー] {provider_label} が空の応答を返しました")
            return ""
        if text_llm.is_moderation_rejection(text):
            print(f"    [エラー] {provider_label} がコンテンツ審査で拒否しました")
            return ""
        return text

    def _generate_intro_text(self, context_info: dict) -> str:
        """エピソード導入部（intro.txt）のテキストを生成する"""
        date_ja = self._format_issue_date_ja()
        sections_jp_list = context_info.get("sections_jp_list", [])
        article_count = context_info.get("article_count", 0)

        # 冒頭は固定句式を使用（LLMに任せない）
        fixed_opening = self._build_intro_opening_fixed(
            date_ja, sections_jp_list, article_count
        )

        articles_intro = context_info.get("all_articles_intro", [])
        articles_bullet = ""
        if articles_intro:
            for idx, item in enumerate(articles_intro):
                intro = item.get("one_line_intro", "").strip()
                articles_bullet += f"- {intro}\n" if intro else "- （一言紹介なし）\n"
        else:
            articles_bullet = "（なし）"

        intro_instruction = f"""
この記事は、ポッドキャストのエピソード（第{context_info['ep_num']}回）の**導入パート**です。
**冒頭の1文は既に固定で用意されているため、出力に含めないでください。**
以下の構成で、**2番目以降**の導入スクリプトのみを作成してください。

**【構成（この順で出力すること）】**
1. **全記事の一言紹介の読み上げ**
   ** 以下の「一言紹介」を**掲載順に**そのまま読み上げてください。文言はメタデータの one_line_intro を変更せず使用すること。
   各紹介の**前**に、掲載順の番号を「(1)、」「(2)、」…「(N)、」の形で付けて読むこと。
   リスト:
{articles_bullet}

2. **定型文＋視聴の案内**
   次の2つを続けて述べてください。
   - 定型文（このまま使用）:「[pause long] 素晴らしい内容が満載でございます。是非最後までお付き合いください。」
   - 視聴の案内（このまま使用）: 「また動画の下に目印がついていますので、気になる記事に直接移動していただいて構いません。[pause short] では早速、最初の記事から読み解いてまいりましょう。」

[pause long]
"""

        prompt = f"""あなたはプロのポッドキャスト編集者兼ナレーターです。
以下の指示に従って、ニュースキャストが読み上げるための**「導入パートの台本」**を作成してください。

## ペルソナ（語り口の統一ルール — 番組全体を通じて厳守）
穏やかで知的、そして信頼感のあるベテラン男性アナウンサーです。
長年の経験に裏打ちされた包容力があり、物事を多角的かつ弁証法的に捉える視点を持っています。
決してリスナーに対して上から目線にならず、親しみやすく語り口が特徴です。

**語尾・表現の禁止事項**:
- 「～ですよ」「～だよ」「～よね」等のカジュアルすぎる語尾は**使用禁止**です。
- 代わりに「～でございます」「～と言えるでしょう」「～かもしれませんね」
  「～ではないでしょうか」等の、丁寧で落ち着いた表現を使ってください。

## 作成指示
{intro_instruction}

## 出力フォーマット
作成した読み上げテキストのみを出力してください。余計な説明は不要です。"""

        try:
            rest_text = self._llm_plain_text(prompt)
            # 固定冒頭 + LLM生成（一言紹介＋定型文・視聴案内）
            return f"{fixed_opening}\n\n{rest_text}"
        except Exception as e:
            print(f"    [エラー] 導入生成失敗: {e}")
            return fixed_opening  # 失敗時も固定冒頭は返す

    def _convert_to_tts_friendly(
        self,
        md_content: str,
        context_info: dict,
        current_article: dict = None,
        prev_article: dict = None,
        is_last_article: bool = False,
    ) -> str:
        """
        MarkdownテキストをTTS用に変換する。
        - 転換文の追加（2記事目以降）
        - Markdown記号の除去
        - 英語→カタカナ変換
        - エンディングは別ファイルで追加（本文には含めない）

        Args:
            md_content: 改写済みのMarkdown記事テキスト
            context_info: エピソードのコンテキスト情報
            current_article: 現在の記事のメタデータ（タイトル紹介用）
            prev_article: 前の記事のメタデータ（transitionの場合に使用）
            is_last_article: エピソードの最終記事かどうか
        """
        # Front Matterの除去（万が一残っている場合）
        body_content = re.sub(r"^---[\s\S]*?---\n", "", md_content).strip()
        # 旧版改写で付与されたコメンタリーは読み上げ対象外
        body_content = re.split(r"\n【コメンタリー】\n", body_content, maxsplit=1)[0].strip()
        
        # ── 転換文の指示（2記事目以降） ──
        intro_instruction = ""
        if prev_article and current_article:
            prev_one_line = prev_article.get("one_line_intro", "").strip()
            current_one_line = current_article.get("one_line_intro", "").strip()

            intro_instruction = f"""
1. **転換文の追加**: この記事はエピソードの途中の記事です。
   **参照するデータ**: 前の記事と今回紹介する記事の**一言紹介（one_line_intro）**を参照して転換文を作成してください。

   - **前の記事の一言紹介**: 「{prev_one_line}」
   - **今回紹介する記事の一言紹介**: 「{current_one_line}」

   上記2つの一言紹介の内容を踏まえて、前の話題から今回の話題へ自然に切り替わる**転換（ブリッジ）の言葉**を冒頭に入れ、この記事の本文へと繋げてください。

   **転換文の自然な接続ルール（重要）**:
   - 前の記事と今回の記事の一言紹介の内容を踏まえ、話題の切り替えを自然に演出してください。
     例: 前の一言紹介で触れたテーマから視点を変えて今回の一言紹介のテーマへ繋ぐ、など。
   - 転換文は長々書かず、簡潔に留めてください。
   - **重要**: 転換文と記事本文の間には必ず `[pause short]` を入れてください。
"""
        else:
             # 1記事目、または転換不要な場合
             pass

        # ── エンディング指示（最終記事の場合） ──
        ending_instruction = ""
        if is_last_article:
            ending_instruction = f"""
8. **最終記事の処理**: この記事はエピソードの最終記事です。
   記事本文の後に自然な区切り {self.PAUSE_LONG} を入れてください。
   ※ エンディングの挨拶は後工程で自動追加されるため、
     締めの言葉や「以上で…」等の結びは**絶対に入れないでください**。
"""

        # ── メインプロンプト ──
        prompt = f"""あなたはプロのポッドキャスト編集者兼ナレーターです。
以下のMarkdown原稿を、ニュースキャストが読み上げるための**「読み上げ台本」**に変換してください。

## ペルソナ（語り口の統一ルール — 番組全体を通じて厳守）
穏やかで知的、そして信頼感のあるベテラン男性アナウンサーです。
長年の経験に裏打ちされた包容力があり、物事を多角的かつ弁証法的に捉える視点を持っています。
決してリスナーに対して上から目線にならず、親しみやすく語り口が特徴です。

**語尾・表現の禁止事項**:
- 「～ですよ」「～だよ」「～よね」等のカジュアルすぎる語尾は**使用禁止**です。
- 代わりに「～でございます」「～と言えるでしょう」「～かもしれませんね」
  「～ではないでしょうか」等の、丁寧で落ち着いた表現を使ってください。

## 変換ルール
1. **Markdown記号の完全除去**: 見出し記号(#)、太字(**)、リンク形式などを全て削除し、プレーンテキストにしてください。
2. **英語のカタカナ化**: 記事の英語タイトル以外に本文中に出てくる英単語は、一般的なカタカナ表記（または日本語訳）に直してください（例: "FRB"→"エフアールビー"、"AI"→"エーアイ"、"GDP"→"ジーディーピー"）。固有名詞も読み上げ可能な形にしてください。
3. **理解しやすい言葉**: 難しい漢字や熟語、論文調の文章は適宜で聞きやすい言葉に直してください。ただしペルソナの品格を損なわないこと。
4. **多読漢字のかな表記（TTS 誤読防止）**: TTSが誤読しやすい漢字は、**漢字を削除し、ひらがなに置き換え**てください。ただし全体がひらがなだらけにならないよう、本当に誤読されやすいものに絞ること。
   ⚠ **絶対禁止**: 漢字を残したまま読みを併記する形式。以下のいずれも禁止です:
   - 「漢字（よみ）」（括弧による読み付記）
   - 「漢字、よみ」（読点による読み付記）
   TTSはテキストをそのまま読み上げるため、漢字と読みの両方が発音され二重読みになります。
   ❌ 波紋（はもん）→「はもん、はもん」と二重に読まれる
   ❌ 波紋、はもん → 同上
   ✅ はもん → 正しく1回だけ読まれる
5. **導入・転換の追加**:
{intro_instruction}
6. **休止の指定（Chirp 3 用・重要）**:
   間（ポーズ）は次のマークアップのみ使用してください。それ以外のタグは使わないでください。
   - やや長い区切り（導入と本文の間など）: 「[pause long]」を単独で1行に書く。
   - 短い区切り（段落間・話題の変わり目）: 「[pause short]」を単独で1行に書く。
   ルール:
   - **転換部**と**記事本文**の間には、必ず 1行で [pause short] を入れてください（転換がある場合）。
   - 記事内の段落間や話題の変わり目には、適宜 1行で [pause short] を入れて、聞きやすいリズムを作ってください。
7. **19XX年の読み（TTS 誤読防止）**: 西暦1900〜1999年はアラビア数字のまま残さないこと。必ず**千九百…**形式に変換してください。
   - 例: 1990年 → 千九百九十年、1945年 → 千九百四十五年、1918年 → 千九百十八年、1905年 → 千九百五年、1900年 → 千九百年
   - 例: 1990年代 → 千九百九十年代
   - 2000年以降の西暦はこの形式の対象外（そのまま、または文脈に合う自然な読み）

{ending_instruction}
## 入力テキスト（Markdown）
{body_content}

## 出力フォーマット
変換後の読み上げテキストのみを出力してください。余計な説明は不要です。"""

        tts_text = self._llm_plain_text(prompt)
        if not tts_text.strip():
            print("    [警告] LLM 変換失敗のため改写原文を使用します")
            return body_content
        return tts_text

    # ================================================================
    # エピソードキーワード集約
    # ================================================================

    @staticmethod
    def _compute_episode_key(articles: list) -> str:
        """各記事の keywords_ja を集約し、出現回数でソートして上位30件をカンマ区切り文字列で返す。"""
        counter = Counter()
        for a in articles:
            for kw in a.get("keywords_ja") or []:
                k = (kw or "").strip()
                if k:
                    counter[k] += 1
        # 出現回数降順、同率なら出現順を維持するためキーでソート
        top30 = [kw for kw, _ in counter.most_common(30)]
        return ",".join(top30)  # カンマ区切りでコピー用

    def _update_episode_key_in_metadata(self, ep_dir: Path, meta: dict) -> None:
        """metadata.json の episode_key を計算して更新し、ファイルに書き戻す。"""
        articles = meta.get("articles", [])
        key_string = self._compute_episode_key(articles)
        meta["episode_key"] = key_string
        metadata_path = ep_dir / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        print(f"    → episode_key を更新しました（上位30キーワード、{len(key_string):,}文字）")

    # ================================================================
    # メイン処理
    # ================================================================

    def prepare_all_episodes(
        self,
        episode_limit: int | None = None,
        episode_numbers: list[int] | None = None,
        article_ids: set[int] | None = None,
    ) -> bool:
        """全エピソードのTTS用テキストを準備する

        Args:
            episode_limit: 処理するエピソード数の上限（None の場合は全エピソード）
            episode_numbers: 処理するエピソード番号のリスト（例: [1, 3, 5] → 01, 03, 05 のみ）。None の場合は全エピソード
            article_ids: 処理する記事IDの集合（例: {2, 5, 7}）。None の場合はエピソード内の全記事
        """
        # PREPARE_TTS はエピソード単位で episode_progress.json に記録（orchestrate が管理）
        episodes_dir = self.output_dir / "episodes"
        if not episodes_dir.exists():
            print("[エラー] エピソードディレクトリが見つかりません。GROUP_EPISODESを先に実行してください。")
            return False

        print(
            f"[情報] TTS テキスト生成モデル: {self._tts_llm_provider_label()} "
            f"(tier=flash)"
        )
        if PREPARE_TTS_API_MIN_INTERVAL_SEC > 0:
            print(f"[情報] API 呼び出し間隔: 最低 {PREPARE_TTS_API_MIN_INTERVAL_SEC:.0f} 秒（15 RPM 対策）")

        episode_dirs = sorted(d for d in episodes_dir.iterdir() if d.is_dir())
        total_files = 0

        for ep_idx, ep_dir in enumerate(episode_dirs):
            # 特定エピソード指定時は、番号が一致するものだけ処理
            if episode_numbers is not None:
                try:
                    ep_num = int(ep_dir.name)
                except ValueError:
                    continue
                if ep_num not in episode_numbers:
                    continue
            # episode_limit が指定されている場合は、その数だけ処理して終了
            elif episode_limit is not None and ep_idx >= episode_limit:
                break

            metadata_path = ep_dir / "metadata.json"
            if not metadata_path.exists():
                print(f"[警告] メタデータが見つかりません: {ep_dir.name}")
                continue

            with open(metadata_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            tts_dir = ep_dir / "tts"
            tts_dir.mkdir(exist_ok=True)

            print(f"\n[処理中] エピソード {ep_dir.name} のTTSテキストを準備中...")

            articles = meta.get("articles", [])

            # 各記事の keywords_ja を集約し、出現回数上位30を episode_key として metadata に保存
            self._update_episode_key_in_metadata(ep_dir, meta)

            # ── エピソード情報の準備（導入生成用）──
            raw_sections = meta.get("sections", [])
            ensure_section_mappings(raw_sections)
            sections_jp_list = [SECTION_JP_MAPPING.get(s, s) for s in raw_sections]
            sections_jp = "、".join(sections_jp_list)
            # 導入文の紹介用：3つ以上ある場合は先頭2つ＋「など」に省略
            if len(sections_jp_list) >= 3:
                sections_jp_intro = "、".join(sections_jp_list[:2]) + "など"
            else:
                sections_jp_intro = sections_jp

            # 注目記事（スコア順）のサマリー
            top_articles_meta = sorted(articles, key=lambda a: a["relevance_score"])[:2]
            top_articles_summary = "、".join(
                [a.get("japanese_title", "") for a in top_articles_meta]
            )

            # エピソード内の全記事（掲載順・導入文では one_line_intro のみ読み上げ）
            all_articles_intro = [
                {
                    "title": a.get("japanese_title", a.get("original_title", "")),
                    "one_line_intro": self._ensure_ending_punctuation(
                        a.get("one_line_intro", "").strip()
                    ),
                }
                for a in articles
            ]
            context_info = {
                "ep_num": meta.get("episode_num"),
                "sections_jp": sections_jp,
                "sections_jp_intro": sections_jp_intro,
                "sections_jp_list": sections_jp_list,
                "article_count": len(articles),
                "top_articles": top_articles_summary,
                "all_articles_intro": all_articles_intro,
            }

            # ── 記事ごとの処理 ──
            # 導入パート（00.txt）の生成
            # 記事ID指定がない場合、または導入生成が明示的に除外されていない場合に生成
            # ただし、導入はエピソード全体のものなので、記事ID指定がある場合でも
            # 「そのエピソードの準備」の一環として生成しておくのが安全か、あるいは逆か。
            # 今回は「記事ID指定がある＝再生成」のケースが多いと想定し、生成する方針で。
            # （intro.txtの生成コストはLLM呼び出し1回分）
            intro_path = tts_dir / "intro.txt"
            if intro_path.exists():
                print(f"    スキップ（既存）: intro.txt")
            else:
                print(f"    導入パート生成中: intro.txt...")
                intro_text = self._generate_intro_text(context_info)
                intro_text = self._postprocess_tts_text(intro_text)
                with open(intro_path, "w", encoding="utf-8") as f:
                    f.write(intro_text)
                print(f"    → 生成完了: intro.txt ({len(intro_text):,}文字)")
                total_files += 1

            prev_article_meta = None  # 前の記事のメタデータ（転換文生成用）
            episode_files = 0  # このエピソードで生成したファイル数（ヒント表示用）

            for i, article_meta in enumerate(articles):
                article_id = article_meta["id"]
                # 特定記事指定時は、該当IDのみ処理（スキップ時も prev_article_meta は更新）
                if article_ids is not None and article_id not in article_ids:
                    prev_article_meta = article_meta
                    continue

                article_path = self.articles_dir / f"{article_id:03d}.md"

                if not article_path.exists():
                    print(f"    [警告] 記事ファイルなし: {article_id}")
                    prev_article_meta = article_meta
                    continue

                with open(article_path, "r", encoding="utf-8") as f:
                    md_content = f.read()

                # 最終記事かどうかの判定
                is_last_article = (i == len(articles) - 1)
                
                filename = f"{i+1:02d}.txt"  # 01.txt, 02.txt...
                if (tts_dir / filename).exists():
                    print(f"    スキップ（既存）: {filename}")
                else:
                    type_label = "transition" if i > 0 else "first_article"
                    if is_last_article:
                        type_label += "＋エンディング"

                    print(f"    変換中: {article_id:03d}.md ({type_label})...")

                    tts_text = self._convert_to_tts_friendly(
                        md_content,
                        context_info,
                        current_article=article_meta,
                        prev_article=prev_article_meta if i > 0 else None,
                        is_last_article=is_last_article,
                    )
                    tts_text = self._postprocess_tts_text(tts_text)

                    with open(tts_dir / filename, "w", encoding="utf-8") as f:
                        f.write(tts_text)

                    print(f"    → 生成完了: {filename} ({len(tts_text):,}文字)")
                    total_files += 1
                    episode_files += 1

                # 次の記事の転換文生成のために現在の記事情報を保持
                prev_article_meta = article_meta

            # エンディング（締めメッセージ）の生成（記事が1本以上ある場合）
            if articles:
                closing_filename = "closing.txt"
                closing_path = tts_dir / closing_filename
                if closing_path.exists():
                    print(f"    スキップ（既存）: {closing_filename}")
                else:
                    print(f"    エンディング生成中: {closing_filename}...")
                    closing_text = self._build_closing_message(sections_jp_list)
                    closing_text = self._postprocess_tts_text(closing_text)
                    with open(closing_path, "w", encoding="utf-8") as f:
                        f.write(closing_text)
                    print(f"    → 生成完了: {closing_filename} ({len(closing_text):,}文字)")
                    total_files += 1

            # --articles 指定で該当が1件もない場合、エピソード内の記事IDを表示
            if article_ids is not None and episode_files == 0 and articles:
                ids_in_ep = [a["id"] for a in articles]
                print(f"    [ヒント] 指定した記事IDはこのエピソードにありません。エピソード {ep_dir.name} の記事ID: {ids_in_ep}")

        print(f"\n[完了] TTS用テキスト準備完了: 合計{total_files}ファイル")
        return True


def _parse_comma_ints(s: str) -> list[int]:
    """カンマ区切り文字列を整数リストに変換（例: '1,3,5' → [1, 3, 5]）"""
    if not s or not s.strip():
        return []
    return [int(x.strip()) for x in s.split(",") if x.strip()]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The Economist ポッドキャスト用TTSテキスト生成")
    parser.add_argument("issue_date", help="発行日 (YYYY-MM-DD)")
    parser.add_argument(
        "--episode-limit",
        type=int,
        default=0,
        help="処理するエピソード数の上限（0 の場合は全エピソード）",
    )
    parser.add_argument(
        "--episodes",
        type=str,
        default="",
        metavar="N,M,...",
        help="処理するエピソード番号をカンマ区切りで指定（例: 1,3,5 → 01, 03, 05 のみ）。未指定時は --episode-limit または全エピソード",
    )
    parser.add_argument(
        "--articles",
        type=str,
        default="",
        metavar="ID,ID,...",
        help="処理する記事IDをカンマ区切りで指定（例: 2,5,7）。IDはメタデータの記事id（002.md→2, 003.md→3）。未指定時はエピソード内の全記事",
    )

    args = parser.parse_args()

    preparer = TTSTextPreparer(args.issue_date)
    limit = args.episode_limit if args.episode_limit > 0 else None
    episode_numbers = _parse_comma_ints(args.episodes) if args.episodes else None
    article_ids = set(_parse_comma_ints(args.articles)) if args.articles else None

    preparer.prepare_all_episodes(
        episode_limit=limit,
        episode_numbers=episode_numbers,
        article_ids=article_ids,
    )

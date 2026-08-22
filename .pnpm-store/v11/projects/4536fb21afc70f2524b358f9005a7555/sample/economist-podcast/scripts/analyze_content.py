"""
記事分析・スコアリングモジュール
ANALYSIS_TXT_GENERATION_PROVIDER（既定: gemini + GEMINI_PRO_MODEL, tier=pro）で RAW を複数記事ずつ
バッチ分析し、日本人向け関心度スコアを付与する。スコア最低の10%を除外対象としてマークする。
"""
import sys
import json
import re
import math
import time
from pathlib import Path

from config import (
    RELEVANCE_TIERS_DESC,
    DROP_BOTTOM_PERCENT,
    ANALYSIS_TXT_GENERATION_PROVIDER,
    ANALYSIS_BATCH_SIZE,
    ANALYSIS_API_MIN_INTERVAL_SEC,
    ANALYSIS_MAX_RETRIES,
    ANALYSIS_RETRY_BASE_WAIT_SEC,
    GEMINI_PRO_MODEL,
    get_issue_dir,
    normalize_economist_section,
)
from state_manager import StateManager
import text_llm

# 記事分析結果の JSON Schema（google.genai 用）
ANALYSIS_ARTICLE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "raw_index": {"type": "integer"},
        "original_title": {"type": "string"},
        "japanese_title": {"type": "string"},
        "section": {"type": "string"},
        "summary_ja": {"type": "string"},
        "one_line_intro": {"type": "string"},
        "keywords_ja": {
            "type": "array",
            "items": {"type": "string"},
        },
        "relevance_score": {"type": "integer"},
        "is_cover_story": {"type": "boolean"},
        "original_char_count": {"type": "integer"},
        "image_reference": {
            "type": "object",
            "properties": {
                "needs_reference": {"type": "boolean"},
                "subject_type": {
                    "type": "string",
                    "enum": ["business_leader", "head_of_state", "none"],
                },
                "subject_name": {"type": "string"},
                "search_query": {"type": "string"},
                "instruction": {"type": "string"},
            },
        },
    },
    "required": [
        "id",
        "raw_index",
        "original_title",
        "japanese_title",
        "section",
        "summary_ja",
        "one_line_intro",
        "keywords_ja",
        "relevance_score",
        "is_cover_story",
        "original_char_count",
    ],
}

# 分析 API の応答は上記オブジェクトの配列
ANALYSIS_RESPONSE_JSON_SCHEMA = {
    "type": "array",
    "items": ANALYSIS_ARTICLE_JSON_SCHEMA,
}


class ContentAnalyzer:
    """記事分析クラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self._analysis_provider = ANALYSIS_TXT_GENERATION_PROVIDER

    def _analysis_provider_label(self) -> str:
        label = text_llm.provider_label(self._analysis_provider)
        if self._analysis_provider == "gemini":
            return f"{label} ({GEMINI_PRO_MODEL})"
        return label

    def _build_analysis_prompt(self, text: str, *, batch_note: str | None = None) -> str:
        """記事分析用のプロンプトを構築"""
        tier_desc = "\n".join(
            f"  - スコア{k}（{'最高' if k == 1 else '高' if k == 2 else '中' if k == 3 else '低'}）: {v}"
            for k, v in RELEVANCE_TIERS_DESC.items()
        )
        batch_section = ""
        if batch_note:
            batch_section = f"\n## 分批处理说明\n{batch_note}\n"
        return f"""あなたは『The Economist』誌の分析エキスパートです。
以下のテキストは『The Economist』{self.issue_date}号から抽出された一部または全文です。
{batch_section}
## タスク
テキストから個別の記事を特定し、**テキスト中に初めて登場する順序で**各記事について以下の情報を抽出してください。
広告・アプリ推薦などの目次以外の本文はすべて対象とします。

## 順序と番号のルール（厳守）
- テキストは [RAW 001], [RAW 002], … で区切られたブロックです。各ブロックはソース（EPUB の章など）の**出現順**です。
- **記事の並び順**: 必ず、先頭から末尾まで記事が**初めて出現する順**で列挙してください。
- **The world this week**: 誌面の冒頭にある「The world this week」の Politics / Business 等も、出現順に**省略せず**1本以上の記事として含めてください。
- **id**: 先頭に出現する記事を id=1、次を id=2、… と通し番号にしてください。
- **raw_index**: 各記事が主に含まれるブロックの 1 始まり番号を整数で入れてください（例: [RAW 001] のブロック内の記事なら raw_index=1、[RAW 003] なら raw_index=3）。後工程でそのブロックだけを使って改写するため必須です。

## 各記事の抽出情報
1. 英語の原題
2. タイトルの日本語訳
3. 所属セクションは**大分類名のみ**（例: Leaders, Briefing, United States）。
   ソースに「Leaders | Defeating Viktor」のように副題がある場合は**パイプの左だけ**（Leaders）を出力すること。
   （Leaders, Briefing, United States, The Americas, Asia, China,
   Middle East & Africa, Europe, Britain, International, Business, Letters,
   Finance & economics, Science & technology, Culture, Obituary 等）
4. 記事の日本語要約（3〜4文）
5. 記事の一言紹介（25文字以内）
6. 主要キーワード（日本語、3〜5個）
7. 日本の読者にとっての関心度スコア（1〜5）
8. 当該号のカバーストーリー（表紙記事）かどうか
9. 原文のおおよその英語文字数
10. **image_reference**（参考画像による img2img 生成の要否）:
    - `needs_reference`: 当該記事が **「世界トップクラスの商業リーダー（CEO・起業家・投資家等）」** または **「主要国の元首・政府首脳（G7/G20 等）」** を主題とし、その人物の肖像を編集部風イラストに合成すべき場合は `true`。それ以外は `false`。
    - `subject_type`: `business_leader`（商業リーダー）/ `head_of_state`（国家元首・政府首脳）/ `none`（該当なし・`needs_reference=false` の場合は `none`）
    - `subject_name`: 人物のフルネーム（英語表記）。複数いる場合はメインの1名のみ。`needs_reference=false` 時は空文字。
    - `search_query`: 画像検索用クエリ（英語）。`"{{subject_name}} official portrait"` の形式を推奨。
    - `instruction`: img2img 用の編集指示（英語）。例: `"Transform into a cinematic editorial portrait with dramatic lighting, premium magazine style, neutral background"`
    - 【厳守】`needs_reference=true` にするのは **当該人物が記事の主題であり、かつ世界規模で知名度が高い場合のみ**。単なる言及・登場人物は `false`。
    - 【厳守】`subject_type=head_of_state` は G7・G20・BRICS 等の主要国の元首・首相・大統領・党总书记レベルに限定。地方政治家・中堅国の閣僚は `none`。

## 国名の表記（japanese_title・one_line_intro で厳守・TTS 誤読防止）
- **japanese_title** と **one_line_intro** では、国名・地域名を**単一漢字の略称**で書かないこと。
  - 禁止例：米、英、中、韓、仏、独、露、伊、印 など（「米国の関税」「英国首相」の「米」「英」単独も不可）
  - 正しい例：**米国**、**英国**、**中国**、**韓国**、**フランス**、**ドイツ**、**ロシア**、または **アメリカ**、**イギリス** など、音声合成が誤読しにくい**2文字以上の表記**
  - 変換例：× 英首相辞任 → ○ 英国首相辞任　× 米関税の衝撃 → ○ 米国関税の衝撃　× 中東（「中」は国名略称ではないので可）
- summary_ja・keywords_ja でも同様の単字国名略称は避けること。

## 関心度スコアの基準
{tier_desc}

※ 複数のカテゴリに該当する場合は、最も高い（数字が小さい）スコアを採用してください。

## テキスト
{text}"""

    def _load_raw_blocks(self) -> list[tuple[int, str]] | None:
        """raw/ 内の各ファイルを (raw_index, 本文) のリストで返す。"""
        raw_dir = self.output_dir / "raw"
        if not raw_dir.exists():
            return None
        paths = sorted(raw_dir.glob("*.txt"), key=lambda p: p.name)
        if not paths:
            return None
        blocks: list[tuple[int, str]] = []
        for i, p in enumerate(paths, 1):
            with open(p, "r", encoding="utf-8") as f:
                blocks.append((i, f.read()))
        return blocks

    @staticmethod
    def _blocks_to_text(blocks: list[tuple[int, str]]) -> str:
        return "\n\n".join(
            f"[RAW {raw_index:03d}]\n\n{content}" for raw_index, content in blocks
        )

    @staticmethod
    def _split_raw_blocks_into_batches(
        blocks: list[tuple[int, str]], batch_size: int
    ) -> list[list[tuple[int, str]]]:
        """RAW ブロックを batch_size 件ずつに分割する。"""
        size = max(1, batch_size)
        return [blocks[i : i + size] for i in range(0, len(blocks), size)]

    def _normalize_articles(self, articles: list, valid_raw_indices: set[int] | None = None) -> list:
        """raw_index・section を正規化。valid_raw_indices がある場合は範囲外を最近傍に補正。"""
        if valid_raw_indices:
            sorted_valid = sorted(valid_raw_indices)
            min_r, max_r = sorted_valid[0], sorted_valid[-1]

            def _clamp_raw_index(v: int) -> int:
                if v in valid_raw_indices:
                    return v
                if v < min_r:
                    return min_r
                if v > max_r:
                    return max_r
                return min(sorted_valid, key=lambda x: abs(x - v))

        for article in articles:
            if "raw_index" not in article or not isinstance(article.get("raw_index"), (int, float)):
                raw_guess = 1
            else:
                raw_guess = max(1, int(article["raw_index"]))
            if valid_raw_indices:
                raw_guess = _clamp_raw_index(raw_guess)
            article["raw_index"] = raw_guess
            if "section" in article and isinstance(article["section"], str):
                article["section"] = normalize_economist_section(article["section"])
        return articles

    def _fetch_articles_from_llm(
        self,
        text: str,
        *,
        batch_note: str | None = None,
        batch_label: str = "",
    ) -> list | None:
        """1回分の LLM 呼び出しで記事リストを取得。失敗時は None。"""
        prompt = self._build_analysis_prompt(text, batch_note=batch_note)
        response_text = ""
        provider_label = self._analysis_provider_label()
        try:
            if not text_llm.is_configured(self._analysis_provider):
                print(
                    f"[エラー] テキスト生成 API が未設定です"
                    f"（{text_llm.required_env_hint(self._analysis_provider)}）。"
                )
                return None
            response_text = text_llm.generate_json(
                prompt,
                json_schema=ANALYSIS_RESPONSE_JSON_SCHEMA,
                tier="pro",
                provider_override=self._analysis_provider,
            )
            if text_llm.is_moderation_rejection(response_text):
                print(f"[エラー] {provider_label} API がリクエストを拒否しました（コンテンツ審査）。")
                print(f"  {batch_label}レスポンス: {response_text[:300]}")
                self._save_raw_response(response_text, batch_label)
                return None
            articles = self._parse_json_response(response_text)
            if not isinstance(articles, list):
                print(f"[エラー] LLM 応答が配列ではありません{batch_label}")
                self._save_raw_response(response_text, batch_label)
                return None
            return articles
        except json.JSONDecodeError as e:
            print(f"[エラー] LLMレスポンスのJSON解析に失敗{batch_label}: {e}")
            print(f"  レスポンス（先頭500文字）: {response_text[:500]}")
            self._save_raw_response(response_text, batch_label)
            return None
        except Exception as e:
            print(f"[エラー] {provider_label} API呼び出しに失敗{batch_label}: {e}")
            return None

    def _save_raw_response(self, response_text: str, batch_label: str) -> None:
        suffix = re.sub(r"[^\w\-]+", "_", batch_label.strip()) or "unknown"
        path = self.output_dir / f"analysis_raw_response_{suffix}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(response_text)

    @staticmethod
    def _wait_for_rate_limit(elapsed_sec: float) -> None:
        """RPM 制限対策: 前回呼び出しから最低 ANALYSIS_API_MIN_INTERVAL_SEC 秒空ける。"""
        wait_sec = ANALYSIS_API_MIN_INTERVAL_SEC - elapsed_sec
        if wait_sec > 0:
            print(f"  [レート制限] {wait_sec:.1f} 秒待機（{ANALYSIS_API_MIN_INTERVAL_SEC:.0f} 秒/回）...")
            time.sleep(wait_sec)

    @staticmethod
    def _retry_backoff_wait(attempt: int) -> float:
        """指数バックオフ: attempt=1 で ANALYSIS_RETRY_BASE_WAIT_SEC、以降 2 倍ずつ増加。"""
        return ANALYSIS_RETRY_BASE_WAIT_SEC * (2 ** (attempt - 1))

    def _fetch_articles_with_retry(
        self,
        text: str,
        *,
        batch_note: str | None = None,
        batch_label: str = "",
    ) -> list | None:
        """リトライ付きで LLM 呼び出しを行う。

        モデレーション拒否・JSON 解析失敗はリトライしない（再試行しても同じ結果の可能性が高いため）。
        API 通信エラーや空応答などの一時的失敗のみリトライ対象。
        """
        max_retries = max(0, ANALYSIS_MAX_RETRIES)
        provider_label = self._analysis_provider_label()

        for attempt in range(1 + max_retries):
            attempt_label = f"（試行 {attempt + 1}/{1 + max_retries}）" if attempt > 0 else ""
            if attempt > 0:
                wait_sec = self._retry_backoff_wait(attempt)
                print(f"  [リトライ] {wait_sec:.0f} 秒待機後に再試行します{attempt_label}...")
                time.sleep(wait_sec)
                print(f"[処理中]{batch_label} 再試行中{attempt_label}...")

            articles = self._fetch_articles_from_llm(
                text,
                batch_note=batch_note,
                batch_label=batch_label + attempt_label,
            )
            if articles is not None:
                return articles

            if attempt < max_retries:
                print(
                    f"  [警告] {provider_label} API 呼び出し失敗{batch_label}{attempt_label}。"
                    f"リトライ可能（残り {max_retries - attempt} 回）"
                )

        print(f"[エラー] {provider_label} API 呼び出しが {1 + max_retries} 回すべて失敗しました{batch_label}")
        return None

    def _batch_progress_path(self) -> Path:
        """バッチ分析の進捗ファイルパス。"""
        return self.output_dir / "analysis_batch_progress.json"

    def _load_batch_progress(self) -> dict | None:
        """保存済みのバッチ進捗を読み込む。"""
        path = self._batch_progress_path()
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[警告] バッチ進捗ファイルの読み込みに失敗、最初からやり直します: {e}")
            return None

    def _save_batch_progress(self, articles: list, batch_idx: int, n_batches: int) -> None:
        """バッチ分析の中間結果を保存（中断後に再開可能にするため）。"""
        path = self._batch_progress_path()
        progress = {
            "issue_date": self.issue_date,
            "batch_idx": batch_idx,
            "n_batches": n_batches,
            "articles": articles,
            "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(progress, f, indent=2, ensure_ascii=False)

    def _clear_batch_progress(self) -> None:
        """バッチ分析完了後に進捗ファイルを削除。"""
        path = self._batch_progress_path()
        if path.exists():
            path.unlink()

    def _analyze_in_batches(self, batch_size: int | None = None) -> list | None:
        """RAW を複数記事ずつバッチ分析し、出現順にマージした記事リストを返す。

        バッチ単位で進捗を保存するため、API 呼び出し失敗で中断しても
        次回実行時に途中から再開できる（analysis_batch_progress.json）。
        """
        blocks = self._load_raw_blocks()
        if not blocks:
            return None

        per_batch = batch_size or ANALYSIS_BATCH_SIZE
        batches = self._split_raw_blocks_into_batches(blocks, per_batch)
        total_chars = sum(len(c) for _, c in blocks)
        n_batches = len(batches)

        # 保存済み進捗があれば途中から再開
        saved = self._load_batch_progress()
        merged: list = []
        start_batch_idx = 1
        if (
            saved
            and saved.get("issue_date") == self.issue_date
            and saved.get("n_batches") == n_batches
            and isinstance(saved.get("articles"), list)
        ):
            merged = saved["articles"]
            start_batch_idx = saved.get("batch_idx", 0) + 1
            if 1 <= start_batch_idx <= n_batches:
                print(
                    f"[再開] バッチ {start_batch_idx}/{n_batches} から再開します"
                    f"（前回完了: {len(merged)} 篇）"
                )
            else:
                # すべて完了していた場合は進捗を破棄して最初から
                merged = []
                start_batch_idx = 1
        else:
            print(
                f"[情報] テキスト分析（{n_batches} バッチ × 最大 {per_batch} 記事）: "
                f"{len(blocks)} ブロック, {total_chars:,} 文字"
            )
            print(f"  プロバイダ: {self._analysis_provider_label()} (tier=pro)")
            if ANALYSIS_API_MIN_INTERVAL_SEC > 0:
                print(f"  API 呼び出し間隔: 最低 {ANALYSIS_API_MIN_INTERVAL_SEC:.0f} 秒")
            if ANALYSIS_MAX_RETRIES > 0:
                print(
                    f"  リトライ: 最大 {ANALYSIS_MAX_RETRIES} 回"
                    f"（待機 {ANALYSIS_RETRY_BASE_WAIT_SEC:.0f} 秒〜・指数バックオフ）"
                )

        for batch_idx, batch_blocks in enumerate(batches, 1):
            if batch_idx < start_batch_idx:
                continue

            raw_indices = {r for r, _ in batch_blocks}
            raw_range = f"RAW {min(raw_indices):03d}–{max(raw_indices):03d}"
            batch_chars = sum(len(c) for _, c in batch_blocks)
            label = f" [バッチ {batch_idx}/{n_batches}, {raw_range}]"
            print(f"[処理中]{label} {len(batch_blocks)} 記事, {batch_chars:,} 文字...")

            batch_note = (
                f"本提示は当該号の**{len(batch_blocks)} ブロック分**です（分批処理、"
                f"バッチ {batch_idx}/{n_batches}）。"
                "**raw_index** は文中の `[RAW NNN]` の **NNN（全局编号）** をそのまま整数で入れてください。"
                "本批内の id は出現順に 1 から付けて構いません（後工程で全体通し番号に直します）。"
                "このテキスト範囲に含まれない記事は出力しないでください。"
            )
            text = self._blocks_to_text(batch_blocks)

            call_start = time.monotonic()
            articles = self._fetch_articles_with_retry(
                text,
                batch_note=batch_note if n_batches > 1 else None,
                batch_label=label,
            )
            elapsed = time.monotonic() - call_start

            if articles is None:
                # 進捗を保存した上で None を返す（次回再開可能）
                self._save_batch_progress(merged, batch_idx - 1, n_batches)
                print(
                    f"[中断] バッチ {batch_idx}/{n_batches} で失敗。"
                    f"進捗を保存しました（{len(merged)} 篇完了）。再実行で続きから再開できます。"
                )
                return None
            self._normalize_articles(articles, valid_raw_indices=raw_indices)
            merged.extend(articles)
            print(f"  → {len(articles)} 篇を検出（累計 {len(merged)} 篇）")

            # バッチごとに進捗を保存
            self._save_batch_progress(merged, batch_idx, n_batches)

            if batch_idx < n_batches and ANALYSIS_API_MIN_INTERVAL_SEC > 0:
                self._wait_for_rate_limit(elapsed)

        # 全バッチ完了：進捗ファイルを削除
        self._clear_batch_progress()

        for idx, article in enumerate(merged):
            article["id"] = idx + 1
        return merged

    @staticmethod
    def _dedupe_cover_story_flags(articles: list) -> int:
        """LLM が複数記事に is_cover_story=true を付けた場合、1本だけ残す。

        優先順位: Leaders セクション > 関心度スコア（小さいほど高）> id（若いほど先）。
        戻り値は false に戻した記事数。
        """
        marked = [a for a in articles if a.get("is_cover_story")]
        if len(marked) <= 1:
            return 0

        def _rank_key(a: dict) -> tuple:
            is_leaders = 0 if (a.get("section") or "") == "Leaders" else 1
            score = a.get("relevance_score", 99)
            if not isinstance(score, int):
                try:
                    score = int(score)
                except (TypeError, ValueError):
                    score = 99
            aid = a.get("id", 999999)
            if not isinstance(aid, int):
                try:
                    aid = int(aid)
                except (TypeError, ValueError):
                    aid = 999999
            return (is_leaders, score, aid)

        winner = min(marked, key=_rank_key)
        winner_id = winner.get("id")
        demoted = 0
        for article in articles:
            if article.get("is_cover_story") and article.get("id") != winner_id:
                article["is_cover_story"] = False
                demoted += 1
        return demoted

    @staticmethod
    def _apply_drop_filter(articles: list) -> tuple[int, int, int]:
        """スコア下位 DROP_BOTTOM_PERCENT を DROP にし、(total, kept, dropped) を返す。"""
        total = len(articles)
        drop_count = max(1, math.floor(total * DROP_BOTTOM_PERCENT))
        articles_sorted_for_drop = sorted(
            articles,
            key=lambda x: (-x.get("relevance_score", 4), x.get("original_char_count", 0)),
        )
        drop_ids = {a["id"] for a in articles_sorted_for_drop[:drop_count]}
        for article in articles:
            article["status"] = "DROP" if article["id"] in drop_ids else "KEEP"
        kept = sum(1 for a in articles if a["status"] == "KEEP")
        dropped = sum(1 for a in articles if a["status"] == "DROP")
        return total, kept, dropped

    def _coerce_parsed_to_article_list(self, parsed: object) -> list | None:
        if isinstance(parsed, list):
            return parsed
        if not isinstance(parsed, dict):
            return None
        for key in ("articles", "items", "data", "results"):
            value = parsed.get(key)
            if isinstance(value, list):
                return value
        if "id" in parsed and "raw_index" in parsed:
            return [parsed]
        return None

    def _parse_json_response(self, response_text: str) -> list:
        """LLMレスポンスから記事配列 JSON を安全に抽出してパースする"""
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```", response_text, re.DOTALL
        )
        json_str = json_match.group(1).strip() if json_match else response_text.strip()

        try:
            parsed = json.loads(json_str)
            articles = self._coerce_parsed_to_article_list(parsed)
            if articles is not None:
                return articles
        except json.JSONDecodeError:
            pass

        # 連結された複数 JSON オブジェクト（Xiaomi json_object 制約の副産物など）
        decoder = json.JSONDecoder()
        idx = 0
        merged: list = []
        while idx < len(json_str):
            while idx < len(json_str) and json_str[idx].isspace():
                idx += 1
            if idx >= len(json_str):
                break
            parsed, end = decoder.raw_decode(json_str, idx)
            chunk = self._coerce_parsed_to_article_list(parsed)
            if chunk:
                merged.extend(chunk)
            idx = end

        if merged:
            return merged

        return json.loads(json_str)

    def _write_summary_report(
        self,
        articles: list,
        total: int,
        kept: int,
        dropped: int,
    ) -> None:
        """分析完了後に汇总報告を出力する（保留数・DROP一覧）"""
        report_path = self.output_dir / "analysis_summary.txt"
        drop_list = [a for a in articles if a.get("status") == "DROP"]
        # 除外記事は id 順で出力
        drop_list.sort(key=lambda a: a.get("id", 0))

        lines = [
            f"# The Economist {self.issue_date} 号 記事分析 汇总報告",
            "",
            "## 統計",
            f"  総記事数: {total} 篇",
            f"  採用（KEEP）: {kept} 篇",
            f"  除外（DROP）: {dropped} 篇",
            "",
            "## 除外（DROP）記事一覧",
            "",
        ]
        for a in drop_list:
            aid = a.get("id", "")
            orig = a.get("original_title", "")
            jp = a.get("japanese_title", "")
            sec = a.get("section", "")
            score = a.get("relevance_score", "")
            lines.append(f"  [{aid}] {orig}")
            lines.append(f"      日本語: {jp}")
            lines.append(f"      セクション: {sec} | 関心度: {score}")
            lines.append("")

        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        try:
            print(f"  汇总報告: {report_path}")
        except UnicodeEncodeError:
            print(f"  Summary report: {report_path}")

    def analyze_articles(self) -> bool:
        """記事を分析してスコアリングを行う"""
        self.state.start_step("ANALYZE_ARTICLES")

        raw_dir = self.output_dir / "raw"
        if not raw_dir.exists() or not list(raw_dir.glob("*.txt")):
            print("[エラー] raw/ が見つからないか空です。先に process_source でテキスト抽出を実行してください。")
            return False

        n_files = len(list(raw_dir.glob("*.txt")))
        print(f"[情報] raw/ から {n_files} ファイルを分析します")

        articles = self._analyze_in_batches()
        if articles is None:
            return False
        if not articles:
            print("[エラー] 分析に成功した記事がありません。")
            return False

        total, kept, dropped = self._apply_drop_filter(articles)

        demoted_cover = self._dedupe_cover_story_flags(articles)
        if demoted_cover:
            winner = next(a for a in articles if a.get("is_cover_story"))
            print(
                f"[情報] カバーストーリーを1本に正規化: "
                f"id={winner.get('id')} ({winner.get('japanese_title', '')}), "
                f"{demoted_cover} 件を is_cover_story=false に修正"
            )

        # 分析結果を保存
        analysis_path = self.output_dir / "analysis.json"
        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(articles, f, indent=2, ensure_ascii=False)

        # 完了後に自動で汇总報告を出力
        self._write_summary_report(articles, total, kept, dropped)

        print(f"[完了] 記事分析完了: 全{total}篇（採用: {kept}篇、除外: {dropped}篇）")
        print(f"  分析結果: {analysis_path}")

        # ユーザーレビューを要求
        self.state.request_user_review(
            "ANALYZE_ARTICLES",
            "analysis.json を確認してください。記事のスコアやステータス(KEEP/DROP)を必要に応じて修正した後、--approve で承認してください。",
        )
        return True

    def append_one_line_intro_only(self) -> bool:
        """
        既存の analysis.json を読み込み、LLM で「一言紹介」のみを再抽出して
        各記事に one_line_intro を追加する。KEEP/DROP やその他フィールドは変更しない。
        """
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            print("[エラー] analysis.json が見つかりません。先に分析を実行してください。")
            return False

        if not self._load_raw_blocks():
            print("[エラー] raw/ が見つからないか空です。")
            return False

        with open(analysis_path, "r", encoding="utf-8") as f:
            existing_articles = json.load(f)

        print("[処理中] 一言紹介（one_line_intro）のみ再抽出し、既存結果にマージします...")
        new_articles = self._analyze_in_batches()
        if new_articles is None or not new_articles:
            return False

        # (raw_index, タイトル) でマッチして one_line_intro のみ上書き（分批後 id は再採番済みのため）
        def _intro_key(a: dict) -> tuple:
            return (
                a.get("raw_index", 0),
                (a.get("original_title") or "").strip().lower(),
            )

        new_by_key = {_intro_key(a): a.get("one_line_intro", "") for a in new_articles}

        updated = 0
        for article in existing_articles:
            key = _intro_key(article)
            if key in new_by_key:
                article["one_line_intro"] = new_by_key[key]
                updated += 1
            else:
                article["one_line_intro"] = article.get("one_line_intro", "")

        with open(analysis_path, "w", encoding="utf-8") as f:
            json.dump(existing_articles, f, indent=2, ensure_ascii=False)

        print(f"[完了] analysis.json に一言紹介を追加しました（{updated} 件）。KEEP/DROP 等は変更していません。")
        print(f"  保存先: {analysis_path}")
        return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python analyze_content.py <YYYY-MM-DD> [--report-only | --append-intro-only]")
        print("  --report-only: analysis.json が既にある場合、分析は行わず汇总報告のみ出力する。")
        print("  --append-intro-only: 既存の analysis.json に「一言紹介」のみ追加する（KEEP/DROP は変更しない）。")
        sys.exit(1)
    issue_date = sys.argv[1]
    report_only = "--report-only" in sys.argv
    append_intro_only = "--append-intro-only" in sys.argv
    analyzer = ContentAnalyzer(issue_date)
    if append_intro_only:
        if not analyzer.append_one_line_intro_only():
            sys.exit(1)
    elif report_only:
        analysis_path = analyzer.output_dir / "analysis.json"
        if not analysis_path.exists():
            print(f"[エラー] {analysis_path} が見つかりません。先に分析を実行してください。")
            sys.exit(1)
        with open(analysis_path, "r", encoding="utf-8") as f:
            articles = json.load(f)
        total = len(articles)
        kept = sum(1 for a in articles if a.get("status") == "KEEP")
        dropped = sum(1 for a in articles if a.get("status") == "DROP")
        analyzer._write_summary_report(articles, total, kept, dropped)
        try:
            print(f"[完了] 汇总報告を出力しました: {analyzer.output_dir / 'analysis_summary.txt'}")
        except UnicodeEncodeError:
            print(f"[Done] Summary report written: {analyzer.output_dir / 'analysis_summary.txt'}")
    else:
        analyzer.analyze_articles()

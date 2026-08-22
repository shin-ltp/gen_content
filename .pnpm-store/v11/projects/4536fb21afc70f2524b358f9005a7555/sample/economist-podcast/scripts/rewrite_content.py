"""
記事改写モジュール
分析済みの各記事を日本語ポッドキャスト原稿に改写する。
"""
import sys
import json
import re
import io
import argparse
import traceback

# Windows環境でのUnicodeEncodeErrorを防止
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import text_llm

from config import (
    get_issue_dir,
)
from state_manager import StateManager

# 改写の第2段（メタデータ抽出）専用 JSON Schema
# 本文生成はプレーンテキストで独立呼び出しするため、ここには含めない
REWRITE_META_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_ja": {"type": "string"},
        "one_line_intro": {"type": "string"},
        "title_ja": {"type": "string"},
        "keywords_ja": {
            "type": "array",
            "items": {"type": "string"},
        },
        "image_prompt": {"type": "string"},
    },
    "required": [
        "title_ja",
        "summary_ja",
        "one_line_intro",
        "keywords_ja",
        "image_prompt",
    ],
}


class ContentRewriter:
    """記事改写クラス"""

    def __init__(self, issue_date: str):
        self.issue_date = issue_date
        self.state = StateManager(issue_date)
        self.output_dir = get_issue_dir(issue_date)
        self.articles_dir = self.output_dir / "articles"
        self.articles_dir.mkdir(parents=True, exist_ok=True)

    def _extract_json_str(self, response_text: str) -> str:
        json_match = re.search(
            r"```(?:json)?\s*\n?(.*?)\n?```", response_text, re.DOTALL
        )
        return json_match.group(1).strip() if json_match else response_text.strip()

    def _coerce_dict_with_key(self, parsed: object, required_key: str) -> dict | None:
        """指定キーを含む dict を再帰的に探す。ルート配列やラップ済み構造に対応。"""
        if not isinstance(parsed, dict):
            return None
        if required_key in parsed:
            return parsed
        for key in ("article", "result", "data", "output", "metadata"):
            nested = parsed.get(key)
            if isinstance(nested, dict) and required_key in nested:
                return nested
        return None

    def _parse_json_response(self, response_text: str, required_key: str = "content") -> dict | None:
        """LLMレスポンスからJSONオブジェクトを抽出し、指定キーを含むものを返す"""
        if text_llm.is_moderation_rejection(response_text):
            print(f"    [エラー] {text_llm.provider_label()} API がリクエストを拒否しました（コンテンツ審査）。")
            print(f"      {response_text[:300]}")
            return None

        json_str = self._extract_json_str(response_text)
        try:
            parsed = json.loads(json_str)
            data = self._coerce_dict_with_key(parsed, required_key)
            if data is not None:
                if not data.get(required_key):
                    print(f"    [警告] JSONは有効ですが {required_key} が空です。")
                return data
        except json.JSONDecodeError:
            pass

        try:
            json_match = re.search(r"(\{.*\})", json_str, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group(1))
                data = self._coerce_dict_with_key(parsed, required_key)
                if data is not None:
                    return data
        except json.JSONDecodeError:
            pass

        if "```json" in response_text:
            print("    [警告] JSON形式のようですが解析に失敗しました。")
        return None

    def _get_chars_limit(self, article_meta: dict) -> tuple[int, int]:
        """記事の優先度に基づく文字数制限を返す。戻り値: (min_chars, max_chars)"""
        score = article_meta.get("relevance_score", 2)
        if score == 1:
            max_chars = 4000
        elif score == 2:
            max_chars = 3300
        else:
            max_chars = 2800
        min_chars = round(max_chars * 0.65)
        return (min_chars, max_chars)

    def _strip_code_fence(self, text: str) -> str:
        text = (text or "").strip()
        m = re.search(r"```(?:\w*)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        return m.group(1).strip() if m else text

    def _enforce_content_char_limit(
        self, body: str, min_chars: int, max_chars: int
    ) -> str:
        """初回出力が上限を超えた場合に編集リトライで収める。"""
        if len(body) <= max_chars:
            return body

        current = body
        for attempt in range(1, 3):
            print(
                f"    [情報] content が上限超過のため圧縮リトライ {attempt}/2: "
                f"{len(current):,} 文字 → 目標 {min_chars}〜{max_chars} 文字"
            )
            prompt = f"""あなたは日本語ポッドキャストの編集者です。次の原稿を**文字数制限内**に必ず収めてください。

【厳守】
- 出力全体の総文字数（改行・スペース・空行をすべて含む）は **{min_chars} 文字以上 {max_chars} 文字以下**。
- **{max_chars} を1文字でも超えてはならない。** 超えそうなら論点を残してさらに削る。
- 著者の論点・主張・主要な事実・数字は可能な限り残す。
- 段落分けと段落間の空行は維持する。
- **中国語の直訳・語感**（例：热带雨林、象牙塔、「进行」「此外」など）は使わず、**自然な日本語**を維持する。
- **出力は短縮後の本文テキストのみ**。見出し・説明・「圧縮しました」などのメタ文言は禁止。

--- 原稿（現在 {len(current)} 文字）---
{current}
"""
            try:
                trimmed = self._strip_code_fence(
                    text_llm.generate_text(prompt, tier="pro")
                )
            except Exception as e:
                print(f"    [警告] 圧縮リトライ失敗: {e}")
                break
            if not trimmed:
                print("    [警告] 圧縮レスポンスが空。前段の本文を保持します。")
                break
            current = trimmed
            if len(current) <= max_chars:
                if len(current) < min_chars:
                    print(
                        f"    [警告] 圧縮後が目標下限を下回りました: {len(current):,} < {min_chars}"
                    )
                return current

        if len(current) > max_chars:
            print(
                f"    [警告] 圧縮後も上限超過のままです: {len(current):,} > {max_chars:,}。"
                f" 必要に応じて手動で編集してください。"
            )
        return current

    def _expand_content_char_limit(
        self, body: str, raw_text: str, min_chars: int, max_chars: int
    ) -> str:
        """初回出力が下限を下回った場合に、原文に基づき内容を拡充するリトライ。"""
        if len(body) >= min_chars:
            return body

        current = body
        for attempt in range(1, 3):
            print(
                f"    [情報] content が下限未満のため拡充リトライ {attempt}/2: "
                f"{len(current):,} 文字 → 目標 {min_chars}〜{max_chars} 文字"
            )
            prompt = f"""あなたは日本語ポッドキャストの編集者です。以下の短すぎる原稿を、**原文の情報を使って内容を拡充**し、文字数制限内に収めてください。

【厳守】
- 出力全体の総文字数（改行・スペース・空行をすべて含む）は **{min_chars} 文字以上 {max_chars} 文字以下**。
- **{min_chars} 文字未満になってはならない。** 不足する場合は原文から論点・事実・数字・具体例を取り出して丁寧に展開する。
- 原文の論点・主張・主要な事実・数字・具体例・比喩・分析の論理展開を可能な限り復元し、丁寧に説明しながら展開する。
- **単なる水増し・繰り返し・無意味な装飾・感想・コメンタリー・挨拶・締めは禁止**。情報量を増やすことが目的。
- 段落分けと段落間の空行を維持し、3〜5文程度で改行する聴きやすい構成を保つ。
- **中国語の直訳・語感**は使わず、**自然な日本語**を維持する。
- **出力は拡充後の本文テキストのみ**。見出し・説明・メタ文言は禁止。

--- 原文（情報源）---
{raw_text}

--- 現在の短い原稿（{len(current)} 文字・これをベースに拡充）---
{current}
"""
            try:
                expanded = self._strip_code_fence(
                    text_llm.generate_text(prompt, tier="pro")
                )
            except Exception as e:
                print(f"    [警告] 拡充リトライ失敗: {e}")
                break
            if not expanded:
                print("    [警告] 拡充レスポンスが空。前段の本文を保持します。")
                break
            current = expanded
            if len(current) >= min_chars:
                if len(current) > max_chars:
                    print(
                        f"    [情報] 拡充後に上限超過: {len(current):,} > {max_chars:,}。"
                        f" 圧縮プロセスに引き渡します。"
                    )
                return current

        if len(current) < min_chars:
            print(
                f"    [警告] 拡充後も下限未満のままです: {len(current):,} < {min_chars:,}。"
                f" 必要に応じて手動で編集してください。"
            )
        return current

    def _build_body_prompt(self, article_meta: dict, raw_text: str) -> str:
        """本文生成専用プロンプト。メタデータ・画像プロンプトは分離し、注意力を本文に集中させる。"""
        min_chars, max_chars = self._get_chars_limit(article_meta)

        return f"""あなたは穏やかで知的、そして信頼感のあるベテラン男性アナウンサーです。
長年の経験に裏打ちされた包容力があり、物事を多角的かつ弁証法的に捉える視点を持っています。
決してリスナーに対して上から目線にならず、親しみやすさと品格を兼ね備えた語り口が特徴です。

## タスク
以下の英語の記事原文を、日本語のポッドキャスト原稿（本文のみ）に書き直してください。
**あなたが今やるべきことは「本文を十分に展開して書くこと」だけ**です。
メタデータ・タイトル・要約・キーワード・画像プロンプト・JSON整形は一切不要です。本文テキストのみを出力してください。

## 文字数（最重要・厳守）
- 本文の総文字数（改行・空行をすべて含む）は **{min_chars} 文字以上 {max_chars} 文字以下**。
- **下限 {min_chars} 文字の遵守は上限 {max_chars} 文字と同等に重要**です。下限を下回ることは重大な違反として扱われます。
- 目安は **{min_chars}〜{max_chars} 字の中〜上限寄り**（できるだけ {min_chars} 字以上を確保）。
- **最初から短く書かないでください。** 原文の内容を十分に読み取り、論点・事実・数字・論理展開・具体例を丁寧に展開してから、上限を超えそうな場合のみ調整してください。
- 2,000 字前後の短い要約原稿は作らないこと。原文の密度を保ったまま日本語で再構成してください。

## 記述スタイル
### 基本設定
- 出力言語: 日本語
- 文体: 落ち着いた大人の男性アナウンサーによる、耳で聴いて心地よい自然な語り
- **段落・改行**: 論点ごと・話題ごとに適切に段落分けし、段落と段落の間に改行（空行）を入れること。長い一続きの文章にせず、3〜5文程度で改行して聴きやすい構成にすること。

### 第三者的な視点
- 「著者は～と分析しています」「～という例が挙げられました」「この記事では～と指摘されています」「著者はこの現象をXXと名付けました」といった客観的な紹介スタンスを持ってください。
- 記事の内容を自分の意見として断定するのではなく、あくまで著者の見解として紹介するスタンスです。

### 平易な表現・自然な日本語
- 生僻な表現や難解な言い回しを避け、一般的なリスナーが理解しやすい平易な語彙を用いる。
- **日本のリスナーに聞き慣れた自然な日本語**であること。中国語の語彙・慣用句・接続の癖をそのまま日本語に写さない。
- 比喩・慣用句は**日本語で定着した言い方**に置き換える（例：× 象牙塔 → ○ 象牙の塔／学問の殿堂；× 双刃剑 → ○ 諸刃の剣）。
- **一文の長さ**: 長い文は適切に分割し、耳で聴いて理解しやすい長さ（目安：40〜60文字程度）に収める。

### 専門用語・概念の解説
- 一般的なリスナーが深く理解していない可能性のある専門用語、現象、科学原理、市場メカニズムなどは、その理解が記事の核心に関わる場合、平易な解説を自然な形で織り交ぜてください。
- 解説は本文の論旨を圧迫しないよう簡潔に留め、1記事あたり最大2回まで。

## 絶対に守ること（禁止事項）
- 自己紹介・挨拶・寒暄・謝辞・締めを一切入れない。
- 雑誌名・記事の導入パラグラフを入れない。
- 最後に記事のまとめ・お別れの挨拶を入れない（後工程で追加されます）。
- **出力は本文テキストのみ**。タイトル・要約・キーワード・画像指示・JSON・説明文は一切出力しない。

## 必ず保持すべき要素（字数調整時も優先）
- 記事の核心的な論点と主張
- 論点を支える主要な根拠とデータ
- 推論・分析の論理展開
- 独自の視点や切り口
- 具体的な事例・数字・比喩

## 原文テキスト
（以下の英語テキストは記事の全文です。この情報を余すところなく活用し、密度の高い日本語原稿に書き直してください）
{raw_text}"""

    def _build_meta_prompt(self, raw_text: str) -> str:
        """メタデータ＋画像プロンプト抽出専用プロンプト。原文を入力とする。"""
        return f"""あなたは日本語ポッドキャストの編集者です。以下の英語記事原文を読み、
ポッドキャスト配信に必要なメタデータと画像生成用プロンプトを抽出してください。

## タスク
原文を読み、以下の5つのフィールドから成るJSONオブジェクトを出力してください。
**本文（content）は出力しないでください**。本文は別工程で生成済みです。

## 各フィールドのルール
- **title_ja**: 記事の日本語タイトル。**20文字以内（厳守・超過禁止）**。
  - 英題のインパクト・語感・編集部の「効かせ方」を最優先に再現。
  - 短文で口に出して自然な日本語にすること。本文を根拠にした無難な説明タイトルにはしない。
  - 単語の機械的な並べ替え・生硬な漢語の列挙は避ける。
  - **中国語由来の語感・慣用句**（例：象牙塔、热带雨林）を使わない。
  - **国名は単一漢字略称（米・英・中・韓等）を使わず**、米国・英国・中国・韓国、またはアメリカ・イギリス等の**2文字以上の表記**とすること（TTS 誤読防止）。

- **summary_ja**: 記事の要約（3〜4文、常体、客観的）。原文の内容を正確に反映。**中国語の直訳調を避け、自然な日本語**で書く。

- **one_line_intro**: 記事の一言紹介（**25文字以内**、常体、客観的）。**中国語の直訳調を避ける**。**国名は単一漢字略称（米・英・中・韓等）を使わず**、2文字以上の表記とすること（TTS 誤読防止）。

- **keywords_ja**: 主要キーワード（**日本語、3〜5個**）。日本語として自然な語を選ぶ（中国語特有の四字熟語・簡体字表記は不可）。

- **image_prompt**: 画像生成用プロンプト（**英語のみ・日本語禁止**）。記事の主題を**視覚的な比喩・シーン**として描写する。タイトル・見出し・キーワードの列挙は禁止。
  - 【スタイルの選び方】: 以下の5種類から**記事のテーマ・トーンに最も合うものを1つだけ**自律的に選び、プロンプト冒頭で英語に訳して明示（セクション・カテゴリによる固定割当は禁止）：
    - モノクローム → monochrome
    - 水彩イラスト → watercolor illustration
    - ドキュメンタリー写真風 → documentary photography style
    - シネマティック写真 → cinematic photography
    - 手描きスケッチ風 → hand-drawn sketch style
  - 【主題の視覚化】: 記事の核心を**1つの印象的なシーン**に凝縮する。構図はシンプルに、余計な要素を詰め込まない。**インパクト**と**高級感**（refined, premium, striking visual）を意識する。
  - 【国・地域が主題の場合】: 該当国・地域を象徴する要素を**積極的に**用いる（例：象徴的なランドマーク、代表的な動物、国旗の色やモチーフ）。ただし**国家元首・政治家の肖像を直接描かない**こと（シルエット・後ろ姿・象徴物のみで示す）。
  - 【品質要件（必ず含める）】: high quality, highly detailed, professional, striking composition, clean and elegant
  - 【構図の注意】: 「雑誌の表紙」「ポスター」「書籍カバー」のレイアウトは禁止。文字を載せる余白や帯を想定しない。**純粋なイラスト／シーンのみ**。
  - 【禁止事項（必ず含める）】: image_prompt 内に日本語・中国語・韓国語を一切書かない（keywords_ja や title_ja をそのまま貼らない）。No text, no typography, no words, no letters, no numbers, no captions, no headlines, no logos, no watermarks, no characters in any language. No recognizable portraits of political leaders or heads of state.

## 原文テキスト
{raw_text}"""

    def _get_raw_text_for_article(self, article: dict) -> str | None:
        """
        当該記事の改写に使う生テキストを取得する。
        現在は各記事が独立したファイル (raw/NNN.txt) に保存されているため、それを直接読み込む。
        """
        raw_dir = self.output_dir / "raw"
        if not raw_dir.exists():
            return None
        
        article_id = article.get("id")
        target_idx = article_id if article_id is not None else article.get("raw_index")

        if target_idx is None:
            return None

        try:
            idx = int(target_idx)
            p = raw_dir / f"{idx:03d}.txt"
            if p.exists():
                print(f"    [読込] {p.name}")
                with open(p, "r", encoding="utf-8") as f:
                    content = f.read()
                    if not content.strip():
                        print(f"    [警告] ファイル {p.name} は空です。")
                        return None
                    return content
        except (TypeError, ValueError):
            pass
            
        return None

    def rewrite_articles(self, limit: int = 0, force: bool = False, article_ids: list[int] | None = None) -> bool:
        """全KEEP記事を日本語ポッドキャスト原稿に改写する"""
        self.state.start_step("REWRITE_ARTICLES")

        if not text_llm.is_configured():
            print(
                f"[エラー] テキスト生成 API が未設定です。"
                f"（{text_llm.required_env_hint()} を .env に設定してください）"
            )
            return False

        print(
            f"[情報] 改写モデル: {text_llm.provider_label()} / {text_llm.get_model_name('pro')}"
        )

        # 分析結果の読み込み
        analysis_path = self.output_dir / "analysis.json"
        if not analysis_path.exists():
            print("[エラー] analysis.json が見つかりません。先に記事分析を実行してください。")
            return False

        with open(analysis_path, "r", encoding="utf-8") as f:
            articles = json.load(f)

        raw_dir = self.output_dir / "raw"
        if not raw_dir.exists() or not list(raw_dir.glob("*.txt")):
            print("[エラー] raw/ が見つからないか空です。先に process_source でテキスト抽出を実行してください。")
            return False
        print(f"[情報] raw/ 内の個別テキストファイルを読み込みます")

        kept_articles = [a for a in articles if a.get("status") == "KEEP"]

        if article_ids:
            id_set = set(article_ids)
            kept_articles = [a for a in kept_articles if a["id"] in id_set]
            print(f"[指定] ID={sorted(id_set)} の {len(kept_articles)} 篇を処理します")
            force = True  # 指定 ID の場合は常に上書き
        elif limit > 0:
            kept_articles = kept_articles[:limit]
            print(f"[制限] 最初の{limit}篇のみ処理します")

        print(f"[処理中] {len(kept_articles)}篇の記事を改写します...\n")

        success_count = 0

        for i, article in enumerate(kept_articles):
            article_file = self.articles_dir / f"{article['id']:03d}.md"

            # 既に改写済みの場合はスキップ
            if article_file.exists() and not force:
                print(f"  [{i+1}/{len(kept_articles)}] スキップ（既存）: {article.get('japanese_title', article['original_title'])}")
                success_count += 1
                continue

            raw_text = self._get_raw_text_for_article(article)
            if not raw_text:
                print(f"  [{i+1}/{len(kept_articles)}] [エラー] 該当記事の raw テキストを取得できません: ID={article.get('id')}")
                continue

            title = article.get("japanese_title", article["original_title"])
            print(f"  [{i+1}/{len(kept_articles)}] 改写中: {title} ({len(raw_text)}文字)")

            try:
                # ===== 第1段階: 本文生成（プレーンテキスト・注意力を本文に集中）=====
                body_prompt = self._build_body_prompt(article, raw_text)
                body_response = text_llm.generate_text(body_prompt, tier="pro")
                rewritten_body = self._strip_code_fence(body_response).strip()

                if not rewritten_body:
                    print(f"    [エラー] 本文生成が空でした。レスポンス先頭:\n{body_response[:500]}...")
                    continue

                min_chars, max_chars = self._get_chars_limit(article)

                # 字数調整: 上限超過なら圧縮、下限未満なら原文ベースで拡充
                if len(rewritten_body) > max_chars * 1.1:
                    print(
                        f"    [情報] 初回本文が上限超過: {len(rewritten_body):,} > {max_chars:,}"
                    )
                    rewritten_body = self._enforce_content_char_limit(
                        rewritten_body, min_chars, max_chars
                    )
                elif len(rewritten_body) < min_chars:
                    print(
                        f"    [情報] 初回本文が下限未満: {len(rewritten_body):,} < {min_chars}"
                        f" → 原文ベースで拡充リトライ"
                    )
                    expanded = self._expand_content_char_limit(
                        rewritten_body, raw_text, min_chars, max_chars
                    )
                    # 拡充後に上限を超えた場合は圧縮プロセスに引き渡す
                    if len(expanded) > max_chars:
                        rewritten_body = self._enforce_content_char_limit(
                            expanded, min_chars, max_chars
                        )
                    else:
                        rewritten_body = expanded

                # ===== 第2段階: メタデータ＋画像プロンプト抽出（原文を入力）=====
                meta_prompt = self._build_meta_prompt(raw_text)
                meta_response = text_llm.generate_json(
                    meta_prompt,
                    json_schema=REWRITE_META_JSON_SCHEMA,
                    tier="pro",
                )
                meta_result = self._parse_json_response(meta_response, required_key="title_ja")
                if not meta_result:
                    print(f"    [警告] メタデータ解析に失敗。既存メタデータを保持します。")
                    if meta_response:
                        debug_path = self.output_dir / f"rewrite_meta_response_{article['id']:03d}.txt"
                        with open(debug_path, "w", encoding="utf-8") as f:
                            f.write(meta_response)

                # 日本語タイトル（第2段階で再生成 → front matter / analysis.json / 後工程の基準）
                TITLE_MAX_CHARS = 20
                new_title = ""
                if meta_result:
                    new_title = (meta_result.get("title_ja") or "").strip()
                if not new_title:
                    new_title = (
                        article.get("japanese_title", "").strip()
                        or article.get("original_title", "")
                    )
                if len(new_title) > TITLE_MAX_CHARS:
                    print(
                        f"    [警告] title_ja が {len(new_title)} 文字のため "
                        f"{TITLE_MAX_CHARS} 文字に切り詰めます: {new_title!r}"
                    )
                    new_title = new_title[:TITLE_MAX_CHARS]
                article["japanese_title"] = new_title

                if meta_result:
                    if meta_result.get("summary_ja"):
                        article["summary_ja"] = meta_result["summary_ja"]
                    if meta_result.get("one_line_intro"):
                        article["one_line_intro"] = meta_result["one_line_intro"]
                    if meta_result.get("keywords_ja") and isinstance(meta_result["keywords_ja"], list):
                        article["keywords_ja"] = meta_result["keywords_ja"]

                    image_prompt = (meta_result.get("image_prompt") or "").strip()
                    if image_prompt:
                        images_dir = self.articles_dir / "images"
                        images_dir.mkdir(parents=True, exist_ok=True)
                        prompt_file = images_dir / f"{article['id']:03d}_prompt.txt"
                        try:
                            with open(prompt_file, "w", encoding="utf-8") as f:
                                f.write(image_prompt)
                        except Exception as e:
                            print(f"    [警告] image_prompt の保存に失敗: {e}")

                keywords = article.get("keywords_ja", [])
                keywords_str = json.dumps(keywords, ensure_ascii=False)
                summary = article.get("summary_ja", "").replace('"', '\\"')
                intro = article.get("one_line_intro", "").replace('"', '\\"')
                title_fm = article.get("japanese_title", article["original_title"]).replace('"', '\\"')
                
                front_matter = f"""---
title: "{title_fm}"
origin_title: {article['original_title']}
source: "The Economist {self.issue_date}"
summary: "{summary}"
one_line_intro: "{intro}"
section: "{article['section']}"
author: "Adust"
priority: {article['relevance_score']}
keywords: {keywords_str}
---

"""
                with open(article_file, "w", encoding="utf-8") as f:
                    f.write(front_matter + rewritten_body)

                try:
                    with open(analysis_path, "w", encoding="utf-8") as f:
                        json.dump(articles, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"    [警告] analysis.json の更新に失敗: {e}")

                success_count += 1
                c_body, c_max = len(rewritten_body), max_chars
                body_ok = "OK" if c_body <= c_max else "超過"
                print(
                    f"    → 完了 本文 {c_body:,} 文字 / 上限 {c_max:,} {body_ok}\n"
                )

            except Exception as e:
                print(f"    → [エラー] {e}\n")
                traceback.print_exc()
                continue
        
        print(f"\n[完了] 記事改写完了: {success_count}/{len(kept_articles)}篇")

        self.state.complete_step("REWRITE_ARTICLES", {"rewritten_count": success_count})
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="The Economist記事の日本語改写")
    parser.add_argument("issue_date", help="発行日 (YYYY-MM-DD)")
    parser.add_argument("--limit", type=int, default=0, help="処理する記事数を制限")
    parser.add_argument("--force", action="store_true", help="既存ファイルを上書き")
    parser.add_argument("--ids", type=str, default="", help="処理する記事IDをカンマ区切りで指定（例: 1,4,18）")
    
    args = parser.parse_args()
    
    article_ids = None
    if args.ids:
        article_ids = [int(x.strip()) for x in args.ids.split(",") if x.strip()]
    
    rewriter = ContentRewriter(args.issue_date)
    rewriter.rewrite_articles(limit=args.limit, force=args.force, article_ids=article_ids)



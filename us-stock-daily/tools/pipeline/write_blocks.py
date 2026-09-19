"""Code-orchestrated episode writing: LLM API calls + mechanical validation.

Produces the episode contract (episode.config.json + script.json) and the
draft markdown files needed by existing QA tools. Code owns structure and
validation; LLM calls only produce bounded content units.

Usage:
  python write_blocks.py 2026-09-12
  python write_blocks.py 2026-09-12 --only A B-1 C D
  python write_blocks.py 2026-09-12 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
sys.path.insert(0, str(_TOOLS_DIR))

import text_llm  # noqa: E402
import episode_contract  # noqa: E402
from episode_contract import (  # noqa: E402
    CONTRACT_NEW_EFFECTIVE_DATE,
    CONTRACT_SKELETON_SLIDES,
    NEWS_ITEM_COUNT,
    OPENING_VISUAL_ASSET,
    PREVIEW_SUMMARY_MAX_CHARS,
    PREVIEW_SUMMARY_MIN_CHARS,
    PREVIEW_TITLE_MAX_CHARS,
    PREVIEW_MAX_CHARS,
    PREVIEW_MIN_CHARS,
    ending_slide_ids,
    event_slide_number,
    opening_end_phrase,
    opening_theme_prefix,
    news_slide_number,
    strip_opening_end_phrase,
    strip_opening_theme_prefix,
    theme_image_asset,
)

OUTLINE_PATH = "production/outline.json"
CONFIG_PATH = "production/episode.config.json"
SCRIPT_PATH = "production/script.json"

MAX_B_CHARS = 4200
MAX_RETRIES = 3
BLOCKS_PER_B = 8

EVENTS_PLACEHOLDER_TEXT = "イベント予告はありません。"

_SIMPLIFIED = set(
    "为这说们对时还过发币张价钱买卖车东项银长门问"
    "间书让记论计议语读谈应变两严丰举义乐习乡从众"
    "优传伤债值偿兑兰关兴军农凭卫压历归录彻忆忧怀"
    "总恋惊惯愿战户报择损换敌无显暂术权极构标样"
    "检欢步毕气汉测济涨满烦热监盘现确码离种积稳穷"
    "竞笔签简类紧红约级纯纵纷纸绍经结绕绘给络绝统"
    "继绩续维综绿缓编缩缴罗罚联胜脑腾节范荣获营虑"
    "虽见观规视觉认训设访证评识诉译负财责败货质贴"
    "费资赏赠趋跃轨转轮软轻载较辅辆输边达迁运进远"
    "违连迟适选递遗针钢铁错闲闻阅队阶阳阴陆陈险"
    "隐难韩页顶顺须顾预领频题额风飞饮驱驶验骤鱼鸟"
    "龄马环职肃决"
)
_JP_VOCAB_ERRORS = {
    "指引": "ガイダンス／業績見通し", "財報": "決算", "财报": "決算",
    "市值": "時価総額", "目标价": "目標株価", "营收": "売上高",
    "牛市": "強気相場", "熊市": "弱気相場", "多头": "買い方", "空头": "売り方",
}

ENDING_GREETING_TEXT = (
    "以上、本日の米国株の市場分析でした。内容が参考になりましたら、"
    "高評価とチャンネル登録をお願いします。本番組は毎週火曜日から土曜日の朝に更新し、"
    "週末には1週間を振り返る「週間まとめ」もお届けしています。"
    "では、また次回の放送でお会いしましょう。"
)

PREAMBLE = """あなたは日本の証券・資産運用業界で長く実務に携わったベテラン金融アナリストであり、
個人投資家向け株式番組の脚本も手がける専門家です。入力素材は「日本語へ訳す対象」では
ありません。事実を取り出したうえで、日本の投資情報として自然な放送台本を最初から書き
直すための材料として扱ってください。

【基本姿勢】
- まず事実・数字・出所・論点を抽出し、その後に素材の文章から離れて日本語で構成を設計する。
- 素材の語順・見出し・比喩・キャッチコピー・断片文を写さない。
- 中国語素材を語彙単位で置換する作業をしない。日本の金融・投資コミュニティで
  定着した標準用語と文体的距離感を使う。

【聴取しやすさの設計】
- 各論点は「結論 → 最重要の根拠 → 聴き手の判断視点」の順で設計する。
- 1文に複数の因果や条件を入れない。長い因果連鎖は短文へ分割する。
- 権威的な漢語連続・形容詞過多・修辞的な強調で水増ししない。

【絶対禁止】
- 強気相場は「強気相場」「上昇相場」「株高」で表現する。
- 弱気相場は「弱気相場」「下落相場」で表現する。
- ナレーションでは英語の会計年度略称を使わない。「2028年度」等の日本語表記で書く。
- 「+70%」のような記号式ではなく「70%増」と、音読して成立する文にする。"""

OPENING_DISCLAIMER = (
    "なお、本番組は投資判断を助ける情報提供であり、売買の推奨ではありません。"
    "投資の最終判断は、ご自身の責任において行ってください。"
)

# Chinese simplified terms that occasionally leak through generation.
_NORMALIZE_MAP = {
    "布伦特": "ブレント",
}


def normalize_jp(text: str) -> str:
    """Deterministic term normalization applied to every generated unit."""
    for src, dst in _NORMALIZE_MAP.items():
        text = text.replace(src, dst)
    return text


def issue_dir(date: str) -> Path:
    d = _US_ROOT / "daily-output" / date
    if not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


def adopted_candidates(outline: dict) -> list[dict]:
    return [c for c in outline.get("b_candidates", [])
            if c.get("duplicate_check") != "rejected"]


def read_article_text(issue: Path, item_id: str) -> str:
    for pattern in ("*.md", "*.txt"):
        for f in (issue / "collection").glob(pattern):
            if item_id in f.stem or item_id in f.name:
                return f.read_text(encoding="utf-8-sig")[:8000]
    return ""


def stripped_len(text: str) -> int:
    return len(re.sub(r"\s", "", text))


def ensure_visual_skeleton(date: str) -> None:
    """Extend the legacy visual skeleton for the date-gated v3 layout.

    The 2026-09-09 skeleton contains s0..s56. The v3 contract allocates pages
    sequentially and reserves the final two pages for END-card and
    END-disclaimer; five themes therefore need s0..s59. Extend to s60 so
    N=6 still has one spare wrapper, matching the shipped template.
    """
    if date < CONTRACT_NEW_EFFECTIVE_DATE:
        return
    path = _US_ROOT / "templates" / "visual-skeleton.html"
    html = path.read_text(encoding="utf-8-sig")
    ids = re.findall(r'<div class="swrap" id="s([0-9]+)"', html)
    numbers = [int(value) for value in ids]
    if numbers != list(range(len(numbers))):
        raise RuntimeError(f"visual skeleton slide ids are not contiguous: {ids}")
    additions = [
        f'<div class="swrap" id="s{number}" data-note="">{{{{SLICE:s{number}}}}}</div>'
    for number in range(len(numbers), CONTRACT_SKELETON_SLIDES + 1)
    ]
    if not additions:
        return
    html = html.replace("</body>", "\n" + "\n".join(additions) + "\n</body>")
    path.write_text(html, encoding="utf-8", newline="")
    print(f"  [visual] extended skeleton to s{len(numbers) + len(additions) - 1}")


def validate_japanese(text: str) -> list[str]:
    errors: list[str] = []
    simplified = sorted({c for c in text if c in _SIMPLIFIED})
    if simplified:
        errors.append("simplified Chinese chars found: " + "".join(simplified[:10]))
    for word, correct in _JP_VOCAB_ERRORS.items():
        if word in text:
            errors.append(f"Chinese vocab '{word}' must be '{correct}'")
    return errors


def retry_feedback(prompt: str, errors: list[str]) -> str:
    return prompt + "\n\n【前回の検査で不合格だった項目 — 必ず修正してください】\n" + \
        "\n".join(f"  - {e}" for e in errors)


# ---------------------------------------------------------------------------
# Content generation (LLM calls with code-enforced validation loops)
# ---------------------------------------------------------------------------


def gen_single_preview(date: str, outline: dict, cand: dict,
                       position: int, n: int) -> dict:
    """Generate ONE theme preview: hook title + one <=80 char summary."""
    issue = issue_dir(date)
    title = cand.get("title", "")
    hook = cand.get("question_hook", "")
    source_ids = cand.get("source_ids", [])
    excerpts = []
    for sid in source_ids[:2]:
        txt = read_article_text(issue, sid)
        if txt:
            excerpts.append(txt[:600])
    material = "\n---\n".join(excerpts) or "（素材なし。テーマの知識で執筆してください。）"

    prompt = f"""{PREAMBLE}

【タスク】番組冒頭の「テーマ予告」を1件分だけ JSON で生成してください。

【テーマ {position}/{n}】{title}
【問いのフック】{hook or "（なし）"}

【参照素材（抜粋）】
{material}

【出力要件】
- title: 一文の短いフック見出し（{PREVIEW_TITLE_MAX_CHARS}字以内）。
  目を引くが誇張しない。テーマの固有名詞または主要キーワードを含める。
- summary: {PREVIEW_SUMMARY_MAX_CHARS}字以内の紹介文（句読点含む）。
  title に続けて読んで自然につながる導入であること。
- title と summary のどちらも、細部の仕様・数字の羅列や
  専門用語の展開をしない。概観だけをつかませ、続きを気にさせる。
- summary は自然な文で終える。最後を設問にして悬念を残してもよい。
- テーマ内の固有名詞または数字を1-2個入れる。
- 他のテーマには触れない。挨拶・締めの固定文は含めない。

【出力形式】有効な JSON のみ:
{{
  "title": "...",
  "summary": "..."
}}"""

    schema = json.dumps({
        "type": "object",
        "required": ["title", "summary"],
        "properties": {
            "title": {"type": "string", "maxLength": PREVIEW_TITLE_MAX_CHARS},
            "summary": {"type": "string",
                        "minLength": PREVIEW_SUMMARY_MIN_CHARS,
                        "maxLength": PREVIEW_SUMMARY_MAX_CHARS},
        },
    }, ensure_ascii=False)

    last_errors: list[str] = []
    for attempt in range(1, MAX_RETRIES + 1):
        full_prompt = retry_feedback(prompt, last_errors) if last_errors else prompt
        try:
            result = text_llm.generate_json(full_prompt, tier="flash", schema_hint=schema)
        except Exception as e:
            last_errors = [f"API call failed: {e}"]
            print(f"  [preview {position}] attempt {attempt}: API error")
            continue

        errors: list[str] = []
        title_out = str(result.get("title", "")).strip()
        summary = str(result.get("summary", "")).strip()
        # strip fixed phrases if model added them anyway
        summary = strip_opening_theme_prefix(summary)
        summary = strip_opening_end_phrase(summary).strip()
        t_sz = stripped_len(title_out)
        s_sz = stripped_len(summary)
        if not title_out:
            errors.append("title is empty")
        elif t_sz > PREVIEW_TITLE_MAX_CHARS:
            errors.append(
                f"title length {t_sz} exceeds {PREVIEW_TITLE_MAX_CHARS}"
            )
        if not PREVIEW_SUMMARY_MIN_CHARS <= s_sz <= PREVIEW_SUMMARY_MAX_CHARS:
            errors.append(
                f"summary length {s_sz} outside "
                f"{PREVIEW_SUMMARY_MIN_CHARS}-{PREVIEW_SUMMARY_MAX_CHARS}"
            )
        errors.extend(validate_japanese(title_out + summary))
        if not errors:
            print(f"  [preview {position}] OK "
                  f"(title {t_sz} + summary {s_sz} chars, attempt {attempt})")
            return {
                "title": normalize_jp(title_out),
                "summary": normalize_jp(summary),
            }
        print(f"  [preview {position}] attempt {attempt}: {len(errors)} error(s)")
        for e in errors[:5]:
            print(f"    - {e}")
        last_errors = errors

    raise RuntimeError(f"preview {position} failed after {MAX_RETRIES} attempts: {last_errors}")


def gen_opening_package(date: str, outline: dict) -> dict:
    """Assemble opening package: per-theme previews + one flash call for the rest."""
    adopted = adopted_candidates(outline)
    n = len(adopted)

    previews: list[dict] = []
    for i, cand in enumerate(adopted, 1):
        preview = gen_single_preview(date, outline, cand, i, n)
        previews.append(preview)

    start_phrase = opening_theme_prefix(n)
    previews[0]["summary"] = start_phrase + previews[0]["summary"]
    end_phrase = opening_end_phrase(n)
    previews[-1]["summary"] += end_phrase

    issue = issue_dir(date)
    market_texts = []
    market_files = sorted((issue / "collection").glob("MKT-*.md"))
    if not market_files:
        raise RuntimeError(
            f"market summary requires collection/MKT-*.md; none found for {date}"
        )
    for f in market_files[:3]:
        market_texts.append(f.read_text(encoding="utf-8-sig")[:1500])
    market_source_names = "、".join(f.name for f in market_files[:3])
    market_key_data = _market_key_data(date)

    theme_titles = "\n".join(f"  {i+1}. {c.get('title', '')}" for i, c in enumerate(adopted))
    prompt = f"""{PREAMBLE}

【タスク】オープニングの残り2要素を JSON で生成してください。

【本日のテーマ（{n}件）】
{theme_titles}

【市況データ（{market_source_names} の先頭部分）】
{chr(10).join(market_texts)}

【出力要件】
market は前日の米国市場サマリーである。文字数の硬い上限・下限は設けない。
- MKT素材から、市場の方向を最も説明する決定的要因を必ず取り上げる。
  金利、為替、暗号資産、商品、VIX等の重要な動きが素材にある場合は、その方向と
  具体的な数値・変動幅を省略しない。
- 値上がり・値下がりセクター、または代表個別株群のうち当日最も重要な動きを、
  方向と理由を添えて取り上げる。
- 主要指数は最大1つのみ言及し、指数の数値羅列は禁止する。
- 免責事項・投資助言の決まり文句（「投資判断を助ける情報提供であり…」等）は
  絶対に書かない。免責は番組末尾の静止画で表示するため、ナレーションには入らない。
- 視聴者が翌日のリスクと注目点を取れるよう、結論→決定的要因→影響範囲→
  注目視点の論理で書く。素材が不足する項目は推測で埋めず省略する。

【出力形式】有効な JSON のみ:
{{
  "market": "..."
}}"""

    schema = json.dumps({
        "type": "object",
        "required": ["market"],
        "properties": {
            "market": {"type": "string"},
        },
    }, ensure_ascii=False)

    last_errors: list[str] = []
    for attempt in range(1, MAX_RETRIES + 1):
        full_prompt = retry_feedback(prompt, last_errors) if last_errors else prompt
        try:
            result = text_llm.generate_json(full_prompt, tier="flash", schema_hint=schema)
        except Exception as e:
            last_errors = [f"API call failed: {e}"]
            print(f"  [opening-rest] attempt {attempt}: API error")
            continue

        errors: list[str] = []
        market = str(result.get("market", "")).strip()
        if OPENING_DISCLAIMER in market or "投資判断を助ける" in market:
            errors.append(
                "market includes disclaimer text; disclaimer is END-card "
                "visual only and must never appear in narration")
        idx_matches = re.findall(
            r"(S&P500|S&P 500|ナスダック|NASDAQ|ダウ|ダウ工業株30種)", market
        )
        if len(idx_matches) >= 2:
            errors.append(f"market lists {len(idx_matches)} major indexes; max 1")
        if any("ビットコイン" in item for item in market_key_data) and not any(
            keyword in market for keyword in ("ビットコイン", "暗号資産", "BTC")
        ):
            errors.append("market omits Bitcoin despite MKT key_data")
        bond_items = [item for item in market_key_data if "米国10年債利回り" in item]
        if bond_items:
            bond_change = _percent_from_item(bond_items[0])
            bond_value = _number_from_item(bond_items[0])
            if (abs(bond_change) >= 0.5 or bond_value >= 5.0) and not any(
                keyword in market for keyword in ("金利", "債", "国債")
            ):
                errors.append("market omits the decisive US 10-year yield move")
        if any("セクター" in item for item in market_key_data) and "セクター" not in market:
            errors.append("market omits sector rotation despite MKT key_data")
        errors.extend(validate_japanese(market))
        if not errors:
            print(f"  [opening-rest] OK (attempt {attempt})")
            return {
                "previews": previews,
                "market": normalize_jp(market),
            }
        print(f"  [opening-rest] attempt {attempt}: {len(errors)} error(s)")
        for e in errors[:5]:
            print(f"    - {e}")
        last_errors = errors

    raise RuntimeError(f"opening rest failed after {MAX_RETRIES} attempts: {last_errors}")


def _market_key_data(date: str) -> list[str]:
    """Read the first MKT file's machine-readable key_data row."""
    files = sorted((issue_dir(date) / "collection").glob("MKT-*.md"))
    if not files:
        return []
    raw = files[0].read_text(encoding="utf-8-sig")
    match = re.search(r"^key_data:\s*\[(.*)\]\s*$", raw, re.MULTILINE)
    if not match:
        return []
    try:
        value = json.loads("[" + match.group(1) + "]")
        return [str(item) for item in value]
    except json.JSONDecodeError:
        return []


def _number_from_item(item: str) -> float:
    match = re.search(r"([+-]?\d[\d,.]*)", item)
    if not match:
        return 0.0
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return 0.0


def _percent_from_item(item: str) -> float:
    match = re.search(r"([+-]\d+(?:\.\d+)?)%", item)
    return float(match.group(1)) if match else 0.0


def gen_b_theme(date: str, cand: dict, slot: int) -> str:
    """Generate one B theme's full text via pro API with retry."""
    issue = issue_dir(date)
    theme = cand.get("title", "")
    hook = cand.get("question_hook", "")
    source_ids = cand.get("source_ids", [])
    articles = "\n\n".join(
        f"=== {sid} ===\n{read_article_text(issue, sid)}" for sid in source_ids
    ) or "（対応する素材が見つかりません。テーマの知識に基づき、出典を明示しながら執筆してください。）"

    prompt = f"""{PREAMBLE}

【今回のテーマ（B-{slot}）】{theme}
"""
    if hook:
        prompt += f"【問いのフック】{hook}\n"
    prompt += f"""
【コーナー固有の指示】
メインテーマ。結論→最重要根拠→リスナーの判断視点の順で展開。
最後に必ず行動結論（大手目標株価・買い/積み増し/損切り価格・ポジション目安・リスク）を示す。
2-3のバリュエーション手法で交差検証。レンジで示す。

【参照素材】
{articles}

【出力】ナレーション本文のみ。見出し・マークダウン記法不要。
段落間は空行で区切る。全体は{MAX_B_CHARS}字（空白除く）を超えない。
分量は素材の密度と論理の完全性で決め、最低字数の硬い条件を設けない。
8段落程度に分けてください。"""

    full_prompt = prompt
    last_errors: list[str] = []
    text = ""
    sz = 0
    for attempt in range(1, MAX_RETRIES + 1):
        if last_errors:
            full_prompt = retry_feedback(prompt, last_errors)
        try:
            text = text_llm.generate_text(full_prompt, tier="pro")
        except Exception as e:
            print(f"  [B-{slot}] attempt {attempt}: API error: {e}")
            last_errors = [f"API call failed: {e}"]
            continue
        errors = validate_japanese(text)
        sz = stripped_len(text)
        if sz > MAX_B_CHARS:
            errors.append(f"length {sz} exceeds hard max {MAX_B_CHARS}")
        if not errors:
            print(f"  [B-{slot}] OK ({sz} chars, attempt {attempt})")
            return text
        print(f"  [B-{slot}] attempt {attempt}: {sz} chars, {len(errors)} error(s)")
        for e in errors[:3]:
            print(f"    - {e}")
        last_errors = errors

    print(f"  [B-{slot}] FAILED after {MAX_RETRIES} attempts; keeping last attempt ({sz} chars)")
    return text


def gen_news_package(date: str, outline: dict) -> list[str]:
    """Generate 8 news highlights via one flash JSON call."""
    issue = issue_dir(date)
    items = outline.get("news_highlights", [])
    summaries = "\n".join(
        f"  {i+1}. {it.get('source_id', '')}: {it.get('title_ja', '')}"
        for i, it in enumerate(items))
    articles = "\n\n".join(
        f"=== {it.get('source_id', '')} ===\n{read_article_text(issue, it.get('source_id', ''))[:3000]}"
        for it in items)

    prompt = f"""{PREAMBLE}

【タスク】ニュースハイライト8本のナレーション本文を JSON で生成してください。

【ニュース候補】
{summaries}

【参照素材】
{articles}

【出力要件】
- 各ニュースは80-200字のナレーション本文。
- 冒頭で順番を示す（「1つ目は、」「次は、」「3つ目は、」等）。
- 結論を先に、補足数字は2-3個まで。

【出力形式】有効な JSON のみ:
{{
  "items": [
    {{"index": 1, "text": "..."}},
    ...
  ]
}}"""

    schema = json.dumps({
        "type": "object", "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "required": ["index", "text"],
            "properties": {"index": {"type": "integer"}, "text": {"type": "string"}},
        }}},
    }, ensure_ascii=False)

    full_prompt = prompt
    last_errors: list[str] = []
    result: dict = {}
    for attempt in range(1, MAX_RETRIES + 1):
        if last_errors:
            full_prompt = retry_feedback(prompt, last_errors)
        try:
            result = text_llm.generate_json(full_prompt, tier="flash", schema_hint=schema)
        except Exception as e:
            last_errors = [f"API call failed: {e}"]
            continue
        got = result.get("items", [])
        errors: list[str] = []
        if len(got) != 8:
            errors.append(f"items count={len(got)} (expected 8)")
        texts = []
        for item in got:
            t = item.get("text", "")
            texts.append(t)
            sz = stripped_len(t)
            if sz < 40 or sz > 300:
                errors.append(f"item {item.get('index', '?')} length {sz} outside 40-300")
        errors.extend(validate_japanese(" ".join(texts)))
        if not errors:
            print(f"  [news] OK (attempt {attempt})")
            return [normalize_jp(t) for t in texts]
        print(f"  [news] attempt {attempt}: {len(errors)} error(s)")
        last_errors = errors

    print(f"  [news] FAILED after {MAX_RETRIES} attempts; using last attempt")
    return [item.get("text", "") for item in (result.get("items") or [{}] * 8)]


def gen_events_package(outline: dict) -> list[str]:
    """Generate event preview paragraphs via one flash JSON call."""
    if not outline.get("events_d_needed"):
        return [EVENTS_PLACEHOLDER_TEXT]
    cal_summary = outline.get("events_d_summary", "")
    prompt = f"""{PREAMBLE}

【タスク】直近イベント予告のナレーション本文を JSON で生成してください。

【イベント情報】
{cal_summary}

【出力要件】
- 2-4段落。各段落80-250字。
- 各段落は1-2個の関連イベントを扱う。
- 日時は自然な日本語表現で書く。
- 市場への影響観点を含める。

【出力形式】有効な JSON のみ:
{{
  "items": [{{"text": "..."}}, ...]
}}"""

    schema = json.dumps({
        "type": "object", "required": ["items"],
        "properties": {"items": {"type": "array", "items": {
            "type": "object", "required": ["text"],
            "properties": {"text": {"type": "string"}},
        }}},
    }, ensure_ascii=False)
    try:
        result = text_llm.generate_json(prompt, tier="flash", schema_hint=schema)
        texts = [item.get("text", "") for item in result.get("items", []) if item.get("text")]
        print(f"  [events] {len(texts)} paragraph(s)")
        return texts or [EVENTS_PLACEHOLDER_TEXT]
    except Exception as e:
        print(f"  [events] API error: {e}; using placeholder")
        return [EVENTS_PLACEHOLDER_TEXT]


# ---------------------------------------------------------------------------
# Config / script building (pure code, deterministic)
# ---------------------------------------------------------------------------


def split_paragraphs(text: str, target: int) -> list[str]:
    """Split text into paragraphs, adjusting count toward target."""
    parts = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not parts:
        return [text.strip()] if text.strip() else [""]
    if len(parts) > target:
        head = parts[:target - 1]
        head.append("\n\n".join(parts[target - 1:]))
        return head
    while len(parts) < target and len(parts) >= 2:
        idx = max(range(len(parts)), key=lambda i: stripped_len(parts[i]))
        sentences = [s for s in re.split(r"(?<=[。！？])\s*", parts[idx]) if s.strip()]
        if len(sentences) < 2:
            break
        mid = len(sentences) // 2
        parts[idx:idx + 1] = ["".join(sentences[:mid]), "".join(sentences[mid:])]
    return parts


def build_config_and_script(
    date: str,
    outline: dict,
    opening: dict,
    b_texts: dict[int, str],
    news_texts: list[str],
    event_texts: list[str],
    *,
    partial: bool = False,
) -> tuple[dict, dict, dict]:
    """Build episode.config.json and script.json from generated content."""
    adopted = adopted_candidates(outline)
    n = len(adopted)

    corners = [
        {"id": "OP", "kind": "opening", "order": 1, "title": "オープニング"},
        {"id": "MKT", "kind": "market", "order": 2, "title": "市場概況"},
        *[{"id": f"B{i}", "kind": "themes", "order": 2 + i, "title": f"B{i}"}
          for i in range(1, n + 1)],
        {"id": "NEWS", "kind": "news", "order": 40, "title": "ニュースハイライト"},
        {"id": "EVENTS", "kind": "events", "order": 41, "title": "直近イベント予告"},
        {"id": "ED", "kind": "ending", "order": 50, "title": "エンディング"},
    ]

    blocks: list[dict] = []
    narration: dict[str, str] = {}
    block_order: dict[str, int] = {}

    def add_block(bid: str, corner: str, order: int, slide: str,
                  voice: str, title: str, cue: str, text: str) -> None:
        # Hard contract: the disclaimer is a visual END card only. It must
        # never enter narration text, no matter which block leaks it in.
        text = text.replace(OPENING_DISCLAIMER, "").rstrip()
        blocks.append({
            "id": bid, "corner": corner, "order": order, "slide": slide,
            "voice": voice, "title": title, "cue": cue, "source": date,
        })
        narration[bid] = text
        block_order[bid] = order

    previews = opening.get("previews", [])[:n]
    preview_v2 = episode_contract.is_preview_v2(date)
    for i, preview_item in enumerate(previews):
        if isinstance(preview_item, str):
            ptext = preview_item
        else:
            title = str(preview_item.get("title", "")).strip()
            summary = str(preview_item.get("summary", "")).strip()
            ptext = (
                f"{title}[pause short]{summary}"
                if preview_v2 and title
                else summary
            )
        # Fixed opening/closing phrases are assembly-owned, not LLM output.
        if preview_v2:
            ptext = strip_opening_theme_prefix(ptext)
            ptext = strip_opening_end_phrase(ptext)
            if i == 0:
                ptext = opening_theme_prefix(n) + ptext
            if i == n - 1:
                ptext += opening_end_phrase(n)
        slide = episode_contract.preview_list_slide_id() if preview_v2 else f"s{i+1}"
        cue = f"carousel idx={i}" if preview_v2 else ""
        add_block(f"A-p{i+1}", "OP", i + 1, slide, "xiaomei",
                  f"A 第{i+1}", cue, ptext)
    market_slide_number = 2 if preview_v2 else n + 1
    add_block(f"A-p{n+1}", "OP", n + 1, f"s{market_slide_number}", "xiaomei",
              "A market", "", opening.get("market", ""))

    theme_order = 200
    canonical_themes: list[str] = []
    slide_counter = market_slide_number + 1
    for ti in range(1, n + 1):
        paras = split_paragraphs(b_texts.get(ti, ""), BLOCKS_PER_B)
        for pi, ptext in enumerate(paras, 1):
            bid = f"B{ti}-p{pi}"
            add_block(bid, f"B{ti}", theme_order, f"s{slide_counter}",
                      "xiaomei", f"B{ti} 第{pi}", "", ptext)
            canonical_themes.append(bid)
            theme_order += 1
            slide_counter += 1

    canonical_news: list[str] = []
    # Eight C-p* items share the aggregate News page; each item switches the
    # highlight state on that one page rather than allocating another slide.
    news_slide_num = news_slide_number(
        n,
        sum(len(split_paragraphs(b_texts.get(i, ""), BLOCKS_PER_B))
            for i in range(1, n + 1)),
        date,
    )
    slide_counter = news_slide_num
    for ci, ntext in enumerate(news_texts, 1):
        bid = f"C-p{ci}"
        news_slide = f"s{news_slide_num}"
        add_block(bid, "NEWS", 399 + ci, news_slide, "xiaomei",
                  f"ニュース{ci}", f"news idx={ci - 1}", ntext)
        canonical_news.append(bid)
    slide_counter += 1

    canonical_events: list[str] = []
    event_slide_num = event_slide_number(
        n,
        sum(len(split_paragraphs(b_texts.get(i, ""), BLOCKS_PER_B))
            for i in range(1, n + 1)),
        date,
    )
    for di, etext in enumerate(event_texts):
        bid = f"D-p{di}"
        add_block(bid, "EVENTS", 500 + di, f"s{event_slide_num}", "xiaomei",
                  f"イベント{di+1}", "", etext)
        canonical_events.append(bid)

    # The new layout keeps a distinct visual end card before the fixed
    # disclaimer. Legacy episodes intentionally retain s56 for News3.
    end_card_slide, ending_slide = _ending_slide_ids(
        date, outline, opening, b_texts, news_texts, event_texts
    )
    if date >= CONTRACT_NEW_EFFECTIVE_DATE:
        ensure_visual_skeleton(date)

    blocks.sort(key=lambda b: (b["order"], b["id"]))
    canonical = {
        "opening": [b["id"] for b in sorted(
            (b for b in blocks if b["corner"] == "OP"),
            key=lambda b: (b["order"], b["id"]))],
        "market": [],
        "themes": canonical_themes,
        "news": canonical_news,
        "events": canonical_events,
        "ending": [],
    }

    config = {
        "episode": date,
        "language": "ja-JP",
        "corners": corners,
        "blocks": blocks,
        "canonical_order": canonical,
        "fixed_slots": [
            {"id": "OPENING", "corner": "OP", "order": 0,
             "slide": episode_contract.OPENING_SLIDE_ID,
             "voice": "kyoujyu", "source": "assets/audio/fixed/opening.wav"},
            *([
                {"id": "END-card", "corner": "ED", "order": 800,
                 "slide": end_card_slide, "visual": "end-card"}
            ] if date >= CONTRACT_NEW_EFFECTIVE_DATE else []),
            {"id": "END-disclaimer", "corner": "ED", "order": 900,
             "slide": (
                 ending_slide
                 if date >= CONTRACT_NEW_EFFECTIVE_DATE
                 else "s47"
             ),
             "source": "assets/audio/fixed/ending.wav",
             "visual_only": True},
        ],
        "visuals": {"html": "visual.html", "slide_id_pattern": "^s[0-9]+$"},
        "voices": {"default": "xiaomei"},
        "outputs": {
            "segment_map": "production/segment-map.json",
            "tts_dir": "production/tts",
            "durations": "production/audio/durations.json",
            "remotion_input": "remotion/public/remotion_input.json",
        },
    }
    ordered_ids = sorted(narration, key=lambda x: block_order[x])
    def keep(seg_block: str) -> bool:
        if not partial:
            return True
        done: set[str] = set()
        if opening:
            done.add("A")
        if b_texts:
            done.add("B")
        if news_texts:
            done.add("C")
        if event_texts:
            done.add("D")
        return seg_block in done

    mapped = [
        {
            "order": b["order"],
            "id": b["id"],
            "slide": b["slide"],
            "voice": b["voice"],
            "cue": b.get("cue", ""),
            "text": narration[b["id"]],
            "type": "tts",
        }
        for b in blocks
        if keep(next(iter(block_of_segment(b["id"])), ""))
    ]
    fixed_segments: list[dict] = []
    for slot in config["fixed_slots"]:
        if slot["id"] == "OPENING":
            fixed_segments.append({
                "order": slot["order"],
                "id": slot["id"],
                "slide": slot["slide"],
                "type": "external",
                "title": "Opening fixed asset",
                "asset_hint": slot["source"],
            })
        elif slot.get("visual") == "end-card":
            fixed_segments.append({
                "order": slot["order"],
                "id": slot["id"],
                "slide": slot["slide"],
                "type": "external",
                "title": "Ending card visual",
            })
        else:
            fixed_segments.append({
                "order": slot["order"],
                "id": slot["id"],
                "slide": slot["slide"],
                "type": "external",
                "title": "Ending fixed visual and audio timeline",
                "asset_hint": slot["source"],
            })
    segment_map = {
        "episode": date,
        "language": "ja-JP",
        "visual": "visual.html",
        "voices": {"default": "xiaomei"},
        "segments": sorted(mapped + fixed_segments, key=lambda s: s["order"]),
    }
    script = {
        "episode": date,
        "language": "ja-JP",
        "source": "write_blocks.py",
        "blocks": [{"id": bid, "text": narration[bid]} for bid in ordered_ids],
    }
    return config, script, segment_map


def write_draft_markdown(date: str, outline: dict,
                         opening: dict, b_texts: dict[int, str],
                         news_texts: list[str], event_texts: list[str]) -> None:
    """Write draft-{A,B,C,D}.md for compatibility with existing QA tools."""
    prod = issue_dir(date) / "production"
    prod.mkdir(parents=True, exist_ok=True)

    lines = ["# オープニング", ""]
    for p in opening.get("previews", []):
        if isinstance(p, dict):
            title = re.sub(r"\[pause[^\]]*\]", "", str(p.get("title", "")))
            summary = re.sub(r"\[pause[^\]]*\]", "", str(p.get("summary", "")))
            lines += [f"【{title}】{summary}", ""]
        else:
            lines += [str(p), ""]
    lines += [opening.get("market", ""), ""]
    (prod / "draft-A.md").write_text("\n".join(lines), encoding="utf-8")

    lines = []
    for i, cand in enumerate(adopted_candidates(outline), 1):
        lines += [f"## B-{i} {cand.get('title', '')}", "", b_texts.get(i, ""), ""]
    (prod / "draft-B.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# ニュースハイライト", ""]
    for t in news_texts:
        lines += [t, ""]
    (prod / "draft-C.md").write_text("\n".join(lines), encoding="utf-8")

    lines = ["# イベント予告", ""]
    for t in event_texts:
        lines += [t, ""]
    (prod / "draft-D.md").write_text("\n".join(lines), encoding="utf-8")


def _esc(text: str) -> str:
    return (str(text).replace("&", "&amp;")
            .replace("<", "&lt;").replace(">", "&gt;"))


def _short(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", str(text)).strip()
    return clean if len(clean) <= limit else clean[:limit - 1] + "…"


def _visual_pages(
    date: str,
    outline: dict,
    opening: dict,
    b_texts: dict[int, str],
    news_texts: list[str],
    event_texts: list[str],
) -> list[dict]:
    """One entry per narration slide, with its initial asset requirement."""
    pages: list[dict] = []
    adopted = adopted_candidates(outline)
    theme_names = {i + 1: c.get("title", "") for i, c in enumerate(adopted)}

    pages.append({
                "slide": episode_contract.OPENING_SLIDE_ID,
                "block": "OPENING", "kind": "opening",
                "heading": "オープニングタイトル", "text": "",
                "asset": OPENING_VISUAL_ASSET,
        "asset_kind": "template", "theme": "オープニング",
        "status": "planned",
    })
    preview_count = len(adopted)
    preview_v2 = episode_contract.is_preview_v2(date)
    previews = opening.get("previews", [])[:preview_count]
    if preview_v2:
        pages.append({
            "slide": episode_contract.preview_list_slide_id(),
            "block": "A-p1", "kind": "preview",
            "heading": f"本日のテーマ {preview_count}件",
            "previews": previews,
            "text": " ".join(
                str(p.get("title", "")) for p in previews
            ),
            "asset": theme_image_asset(1, 1),
            "asset_kind": "theme-image", "theme": "本日のテーマ",
            "status": "planned",
        })
    else:
        for i, preview in enumerate(previews, 1):
            text = (
                preview if isinstance(preview, str)
                else preview.get("summary", "")
            )
            theme = theme_names.get(i, f"テーマ{i}")
            pages.append({
                "slide": f"s{i}", "block": f"A-p{i}", "kind": "preview",
                "heading": f"予告テーマ {i}", "text": text,
                "asset": theme_image_asset(i, 1), "asset_kind": "theme-image",
                "theme": theme, "status": "planned",
            })
    market_slide_number = (
        2 if preview_v2 else preview_count + 1
    )
    pages.append({
        "slide": f"s{market_slide_number}", "block": "MKT",
        "kind": "market", "heading": "前日市況",
        "text": opening.get("market", ""), "asset": "",
        "asset_kind": "", "theme": "市況", "status": "no-asset",
    })

    slide_counter = market_slide_number + 1
    for ti in range(1, len(adopted) + 1):
        theme = theme_names.get(ti, f"B{ti}")
        paragraphs = split_paragraphs(b_texts.get(ti, ""), BLOCKS_PER_B)
        for pi, paragraph in enumerate(paragraphs, 1):
            pages.append({
                "slide": f"s{slide_counter}", "block": f"B{ti}-p{pi}",
                "kind": "theme", "heading": f"{theme} — {pi}/{len(paragraphs)}",
                "text": paragraph,
                "asset": theme_image_asset(ti, pi), "asset_kind": "theme-image",
                "theme": theme,
                "status": "planned",
            })
            slide_counter += 1

    news_page_number = news_slide_number(
        len(adopted),
        sum(len(split_paragraphs(b_texts.get(i, ""), BLOCKS_PER_B))
            for i in range(1, len(adopted) + 1)),
        date,
    )
    pages.append({
        "slide": f"s{news_page_number}", "block": "C-p1", "kind": "news",
        "heading": f"ニュースハイライト 1/{len(news_texts)}",
        "text": news_texts[0] if news_texts else "",
        "asset": "", "asset_kind": "", "theme": "NEWS",
        "status": "no-asset",
    })
    for ci, news_text in enumerate(news_texts, 1):
        pages.append({
            "slide": f"s{news_page_number}", "block": f"C-p{ci}",
            "kind": "news-state",
            "heading": f"ニュースハイライト {ci}/8", "text": news_text,
            "asset": "", "asset_kind": "", "theme": "NEWS",
            "status": "no-asset",
        })
    event_page_number = event_slide_number(
        len(adopted),
        sum(len(split_paragraphs(b_texts.get(i, ""), BLOCKS_PER_B))
            for i in range(1, len(adopted) + 1)),
        date,
    )
    pages.append({
        "slide": f"s{event_page_number}", "block": "D-p0", "kind": "event",
        "heading": "直近イベント",
        "text": " ".join(event_texts).strip(), "asset": "",
        "asset_kind": "", "theme": "EVENTS", "status": "no-asset",
    })
    for di, event_text in enumerate(event_texts):
        pages.append({
            "slide": f"s{event_page_number}", "block": f"D-p{di}",
            "kind": "event-state",
            "heading": f"直近イベント {di}", "text": event_text,
            "asset": "", "asset_kind": "", "theme": "EVENTS",
            "status": "no-asset",
        })
    return pages


def _ending_slide_ids(
    date: str,
    outline: dict,
    opening: dict,
    b_texts: dict[int, str],
    news_texts: list[str],
    event_texts: list[str],
) -> tuple[str, str]:
    """Derive fixed END slides from the same numbering as build_config_and_script."""
    adopted = adopted_candidates(outline)
    theme_page_count = sum(
        len(split_paragraphs(b_texts.get(i, ""), BLOCKS_PER_B))
        for i in range(1, len(adopted) + 1)
    )
    return ending_slide_ids(
        len(adopted), theme_page_count, date
    )


def generate_visual_brief(
    date: str,
    outline: dict,
    opening: dict,
    b_texts: dict[int, str],
    news_texts: list[str],
    event_texts: list[str],
) -> Path:
    """Write the Phase 3 input: one asset requirement per narration slide."""
    pages = _visual_pages(date, outline, opening, b_texts, news_texts, event_texts)
    previews = opening.get("previews", [])[:len(adopted_candidates(outline))]
    lines = [
        "# 視覚設計ブリーフ",
        "",
        f"- 対象: {date}",
        "- 生成: write_blocks.py（Slide切分と同時に確定）",
        "- 実行: python -X utf8 us-stock-daily/tools/pipeline/prepare_visual_assets.py "
        f"--date {date}",
        "- 素材命名: 当日 assets/ 直下に b<テーマ番号>-<ページ番号>.png（例: b1-1.png）。"
        "S0 固定背景は opening.png。",
        "- B各テーマは各ページに1枚のテーマ画像を要求する。p1 は記事全体を基準に取得し、"
        "p2以降は各段落を基準に判定する。段落の行動主体がテーマ主体から逸脱しない限り p1 の画像を再利用し、"
        "逸脱した場合のみその段落に応じた新規取得を行う。",
        "- キーワード優先順: ①新製品発表=製品写真→発表会会場写真（講話・声明等のニュース事件は記事配図優先）"
        "②行動主体=企業・機関は社名が鮮明な建物写真、人物はアナリスト引用のみ肖像で他は現場写真"
        "③抽象主体（市況・心理・価格変動・マクロデータ）=生成テーマ画像（imagegen・Mac fallback 禁止）。",
        "- 取得順: 当日 assets → 共有 media_resources（キーワード資産DB）→ SearXNG 画像検索"
        "（LLMが品質・主題適合で選図）→ imagegen（抽象主体・または検索全滅時の最終手段）。",
        "- 採用画像は portrait（人物肖像）フラグを記録する。肖像は左側円形表示、それ以外は左側全高表示。"
        "A予告は対応テーマの p1 画像を巡回使用する。",
        "- 取得できない場合は missing を出力し、合成前に必ず解消する。",
        "- 中国語ソース画像は取得・表示しない。",
        "- C-p1..C-p8 と D-p0.. は同一ページの状態遷移であり、素材要求ではない。",
        "",
        "| Slide | Block | 種別 | 見出し | 素材種別 | 候補アセット | 状態 |",
        "|---|---|---|---|---|---|---|",
    ]
    for page in pages:
        if page["kind"].endswith("-state"):
            continue
        lines.append(
            "| {slide} | {block} | {kind} | {heading} | {asset_kind} | {asset} | {status} |".format(
                slide=page["slide"], block=page["block"], kind=page["kind"],
                heading=_short(page["heading"], 60),
                asset_kind=page["asset_kind"], asset=page["asset"],
                status=page["status"],
            )
        )
    lines += [
        "",
        "## 備考",
        "",
        "- `status: no-asset` の C/D・市況・END系は画像参照を作らない。",
        "- `status: planned` は prepare_visual_assets.py が `fetched` / `generated` / "
        "`media-cache` / `reused` / `cached` / `missing` へ更新する。",
        "- 当日 `assets/manifest.jsonl` に出所・状態・キーワード・portrait フラグ・取得日時を記録し、"
        "`assets/image-meta.json` に表示スタイル用の metadata を保存する。",
        "- 検索や生成で実際に採用した拡張子が変わる場合は、本表と visual-data.json の",
        "  両方の参照を同一パスへ更新してから render_visual.py を実行する。",
        "",
    ]
    path = issue_dir(date) / "production" / "visual-brief.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")

    themes: list[dict] = []
    for page in pages:
        if page["kind"] != "theme":
            continue
        match = re.fullmatch(r"B(\d+)-p(\d+)", page["block"])
        if not match:
            continue
        number = int(match.group(1))
        if not themes or themes[-1]["number"] != number:
            themes.append({
                "number": number, "title": page.get("theme", ""),
                "pages": [],
            })
        themes[-1]["pages"].append({
            "slide": page["slide"], "block": page["block"],
            "page": int(match.group(2)), "text": page.get("text", ""),
        })
    for theme in themes:
        theme["full_text"] = "\n".join(p["text"] for p in theme["pages"])
    preview_v2 = episode_contract.is_preview_v2(date)
    json_payload: dict = {"date": date, "themes": themes}
    if preview_v2:
        json_payload["preview"] = {
            "slide": episode_contract.preview_list_slide_id(),
            "items": [
                {
                    "number": i,
                    "title": str(preview.get("title", "")),
                    "asset": theme_image_asset(i, 1),
                }
                for i, preview in enumerate(previews, 1)
            ],
        }
    json_path = path.parent / "visual-brief.json"
    json_path.write_text(
        json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _slide_logo() -> str:
    return ('<div class="show-logo"><img src="../../assets/logo.png" '
            'alt="Smart Assets 米国株"><span>Smart Assets 米国株</span></div>')


def _opening_title_card(date: str, background: str, subtitle: str) -> str:
    """Build the fixed S0 title card defined by vision-design.md §0.1."""
    issue_date = datetime.date.fromisoformat(date)
    weekday = "月火水木金土日"[issue_date.weekday()]
    display_date = issue_date.strftime(f"%Y年%m月%d日（{weekday}）配信")
    return (
        f'\n<div class="slabel">s0 — Opening title card</div>\n'
        '<div class="slide">'
        '<div class="opening">'
        f'<img src="{_esc(background)}" alt=""></div>'
        '<div class="oc">'
        '<div class="omain">'
        '<div class="olockup">'
        '<img src="../../assets/logo.png" alt="">'
        '<div>'
        '<div class="och-name">Smart Assets 米国株投資チャンネル</div>'
        '<h1>米国株<span class="acc">デイリー</span><br>深層分析</h1>'
        '</div></div>'
        f'<div class="date-badge">{_esc(display_date)}</div>'
        f'<p class="osub">{_esc(_short(subtitle, 120))}</p>'
        '</div></div></div>\n'
    )


def _photo(path: str, alt: str = "") -> str:
    if not path:
        return ""
    return (f'<div class="photo-frame"><img src="{_esc(path)}" '
            f'alt="{_esc(alt)}"></div>')


def _preview_list_slide(
    label: str,
    theme_count: int,
    previews: list[dict],
) -> str:
    """One aggregate preview page: title list left, theme photos right."""
    items: list[str] = []
    photos: list[str] = []
    for i, preview in enumerate(previews):
        title = _short(str(preview.get("title", "")), 42)
        state = "active" if i == 0 else "dimmed"
        items.append(
            f'<div class="topic-item {state}"><div class="topic-number">{i + 1}</div>'
            f'<div class="topic-title">{_esc(title)}</div></div>'
        )
        photo = _photo(theme_image_asset(i + 1, 1), f"テーマ{i + 1}")
        photo = photo.replace(
            'class="photo-frame"', f'class="photo-frame {state}"', 1
        )
        photos.append(photo)
    return (
        f'\n<div class="slabel">{_esc(label)}</div>\n'
        '<div class="slide preview-list">' + _slide_logo() +
        '<div class="chrome">'
        f'<div class="sec-title">本日のテーマ（{theme_count}件）</div>'
        '<div class="preview-grid">'
        '<div class="topic-list">' + "".join(items) + "</div>"
        '<div class="photo-stack">' + "".join(photos) + "</div>"
        "</div></div></div>\n"
    )


def _split_slide(label: str, chip: str, title: str, photo_html: str,
                 content_html: str) -> str:
    return (
        f'\n<div class="slabel">{_esc(label)}</div>\n'
        '<div class="slide split">' + _slide_logo() +
        '<div class="chrome">'
        f'<div class="theme-chip">{_esc(chip)}</div>'
        f'<div class="sec-title">{_esc(title)}</div>'
        '<div class="body">'
        f'<div class="visual">{photo_html}</div>'
        f'<div class="content" style="display:flex;flex-direction:column;gap:16px">'
        f'{content_html}</div></div></div></div>\n'
    )


def _bright_slide(label: str, chip: str, title: str,
                  content_html: str) -> str:
    return (
        f'\n<div class="slabel">{_esc(label)}</div>\n'
        '<div class="slide bright">' + _slide_logo() +
        '<div class="chrome">'
        f'<div class="theme-chip">{_esc(chip)}</div>'
        f'<div class="sec-title">{_esc(title)}</div>'
        f'{content_html}</div></div>\n'
    )


def _steps(items: list[str]) -> str:
    rows = "".join(
        f'<div class="step"><div class="no">{number}</div>'
        f'<div class="tx">{item}</div></div>'
        for number, item in enumerate(items, 1)
    )
    return f'<div class="body col" style="gap:16px">{rows}</div>'


def _news_items(texts: list[str], active_index: int) -> str:
    items = []
    for i, text in enumerate(texts, 1):
        sentences = [s for s in text.split("。") if s.strip()]
        title = _esc(_short(sentences[0] if sentences else text, 40))
        sub = _esc(_short("。".join(sentences[1:]), 50))
        cls = "active" if i == active_index else "dim"
        items.append(
            f'<div class="n-item {cls}"><div class="n-num">{i}</div>'
            f'<div class="n-tx"><div class="n-title">{title}</div>'
            f'<div class="n-sub">{sub}</div></div></div>'
        )
    return f'<div class="news-grid">{"".join(items)}</div>'


def _market_items(market_text: str, key_data: list[str]) -> str:
    index_items = [item for item in key_data if any(
        name in item for name in ("S&P500", "ダウ", "ナスダック")
    )][:3]
    sector_items = [item for item in key_data if "セクター" in item]
    up_sectors = [item for item in sector_items if _percent_from_item(item) >= 0]
    down_sectors = [item for item in sector_items if _percent_from_item(item) < 0]
    other_names = ("VIX", "ドル円", "ユーロドル", "米国10年債利回り", "米国2年債利回り",
                   "金先物", "WTI", "ビットコイン")
    other_items = [item for item in key_data if any(name in item for name in other_names)]
    sentences = [s.strip() + "。" for s in market_text.split("。") if s.strip()]
    if not sentences:
        sentences = ["MKT素材の要点を確認できませんでした。"]

    index_html = '<div class="idx-grid">'
    for item in index_items:
        name, remainder = item.split(" ", 1) if " " in item else (item, "")
        change = _percent_from_item(item)
        cls = "up" if change >= 0 else "down"
        index_html += (
            f'<div class="idx-card"><div class="idx-name">{_esc(name)}</div>'
            f'<div class="idx-val">{_esc(_short(remainder, 28))}</div>'
            f'<div class="idx-chg {cls}">{change:+.2f}%</div></div>'
        )
    index_html += "</div>"

    def sector_rows(items: list[str], direction: str) -> str:
        if not items:
            return f'<div class="row-item"><span class="nm">確認できる{direction}セクターなし</span></div>'
        rows = []
        for item in items[:3]:
            sector = item.split("セクター", 1)[0] + "セクター"
            change = _percent_from_item(item)
            cls = "up" if change >= 0 else "down"
            rows.append(
                f'<div class="row-item"><span class="nm">{_esc(sector)}</span>'
                f'<span class="v {cls}">{change:+.2f}%</span></div>'
            )
        return "".join(rows)

    sector_html = (
        '<div class="block-row">'
        '<div class="sec-block upb"><h3>値上がりセクター</h3>'
        + sector_rows(up_sectors, "上昇") +
        '</div><div class="sec-block dn"><h3>値下がりセクター</h3>'
        + sector_rows(down_sectors, "下落") +
        "</div></div>"
    )

    other_html = '<div class="strip">' + "".join(
        f'<div class="mi"><span class="mn">{_esc(_short(item.split(" ", 1)[0], 22))}</span>'
        f'<span class="mv">{_esc(_short(" ".join(item.split(" ", 1)[1:]), 30))}</span></div>'
        for item in other_items
    ) + "</div>"
    points = "".join(
        f'<div class="step"><div class="no">{i}</div>'
        f'<div class="tx">{_esc(_short(sentence, 150))}</div></div>'
        for i, sentence in enumerate(sentences[:2], 1)
    )
    return ('<div class="body col" style="gap:15px">' + index_html +
            sector_html + other_html +
            f'<div class="body col" style="gap:10px">{points}</div></div>')


def generate_visual_data(
    date: str,
    outline: dict,
    opening: dict,
    b_texts: dict[int, str],
    news_texts: list[str],
    event_texts: list[str],
) -> Path:
    """Create the renderer's per-slide HTML, using Phase 3's expected paths."""
    pages = _visual_pages(date, outline, opening, b_texts, news_texts, event_texts)
    slices: dict[str, str] = {}
    key_data = _market_key_data(date)

    opening_page = pages[0]
    title_topics = [
        _short(candidate.get("title", ""), 42)
        for candidate in adopted_candidates(outline)
    ]
    slices[opening_page["slide"]] = _opening_title_card(
        date,
        opening_page["asset"],
        "、".join(title_topics),
    )

    for page in pages:
        kind = page["kind"]
        slide = page["slide"]
        if slide == "s0":
            continue
        text_html = _esc(page["text"])
        if kind == "news-state" or kind == "event-state":
            continue
        if kind == "preview":
            if episode_contract.is_preview_v2(date):
                slices[slide] = _preview_list_slide(
                    f"{slide} — 予告",
                    len(adopted_candidates(outline)),
                    page.get("previews", []),
                )
            else:
                slices[slide] = _split_slide(
                    f"{slide} — 予告", f"テーマ {page['block'][3:]}",
                    page["heading"],
                    _photo(page["asset"], page["theme"]),
                    f'<div class="hero-lab">{text_html}</div>',
                )
        elif kind == "market":
            slices[slide] = _bright_slide(
                f"{slide} — 市況", "前日市況", page["heading"],
                _market_items(page["text"], key_data),
            )
        elif kind == "theme":
            page_number = int(page["block"].rsplit("-p", 1)[1])
            slices[slide] = _split_slide(
                f"{slide} — テーマ", f"B{page['block'].split('-')[0][1:]} {page_number}/8",
                _short(page["heading"], 52), _photo(page["asset"], page["theme"]),
                f'<div class="hero-lab">{text_html}</div>',
            )
        elif kind == "news":
            index = int(page["block"].rsplit("-p", 1)[1])
            slices[slide] = _bright_slide(
                f"{slide} — ニュース", f"ニュース {index}/8",
                page["heading"], _news_items(news_texts, index),
            )
        elif kind == "event":
            slices[slide] = _bright_slide(
                f"{slide} — イベント", "直近イベント", page["heading"],
                _steps([_esc(item) for item in event_texts]),
            )

    end_slide, disclaimer_slide = _ending_slide_ids(
        date, outline, opening, b_texts, news_texts, event_texts
    )
    slices[end_slide] = _bright_slide(
        f"{end_slide} — END", "エンディング", "本日の解説はここまで",
        '<div class="body col" style="gap:18px">'
        '<div class="hero-lab">ご視聴ありがとうございました。高評価とチャンネル登録をお願いします。</div>'
        '<div class="chips"><div class="chip">週末は週間まとめ</div>'
        '<div class="chip">火曜から土曜まで配信</div></div></div>',
    )
    slices[disclaimer_slide] = (
        f'\n<div class="slabel">{disclaimer_slide} — 免責事項</div>\n'
        '<div class="slide disclaimer">' + _slide_logo() +
        '<div class="disc-body"><div class="disc-title">免責事項</div>'
        '<div class="disc-text">本番組は金融・投資に関する情報提供とリテラシー向上を目的としたものであり、'
        'いかなる投資助言も行うものではありません。<br>投資の最終判断は、ご自身の責任において行ってください。</div>'
        '</div></div>\n'
    )
    # The extended v3 skeleton is intentionally longer than any supported
    # episode. Renderer treats unused referenced wrappers as empty.
    last_slide = int(disclaimer_slide[1:])
    for number in range(last_slide + 1, CONTRACT_SKELETON_SLIDES + 1):
        slices[f"s{number}"] = ""

    path = issue_dir(date) / "production" / "visual-data.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"date": date, "episode": date, "slices": slices}
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def validate_with_build_pipeline(date: str) -> tuple[bool, str]:
    """Run build_pipeline.py validate as a post-write check."""
    orch = _US_ROOT / "tools" / "orchestrator" / "build_pipeline.py"
    try:
        r = subprocess.run(
            [sys.executable, str(orch), "validate", "--date", date],
            capture_output=True, text=True, timeout=60,
            cwd=str(_US_ROOT), encoding="utf-8", errors="replace",
        )
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)


def load_old_sections(date: str, n: int) -> tuple[dict, dict[int, str], list[str], list[str]]:
    """Load reusable text from an existing script.json when regenerating partially."""
    script_path = issue_dir(date) / SCRIPT_PATH
    if not script_path.is_file():
        return {}, {}, [], []
    try:
        old = json.loads(script_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}, {}, [], []
    old_by_id = {b.get("id"): b.get("text", "") for b in old.get("blocks", [])
                 if isinstance(b, dict)}
    previews = previews_from_narration_texts(
        [old_by_id.get(f"A-p{i + 1}", "") for i in range(n)]
    )
    opening = {
        "previews": previews,
        "market": old_by_id.get(f"A-p{n+1}", ""),
    }
    b_texts: dict[int, str] = {}
    for i in range(1, n + 1):
        paras = []
        pi = 1
        while f"B{i}-p{pi}" in old_by_id:
            paras.append(old_by_id[f"B{i}-p{pi}"])
            pi += 1
        if paras:
            b_texts[i] = "\n\n".join(paras)
    news_texts = [old_by_id.get(f"C-p{i}", "") for i in range(1, 9)]
    news_texts = [t for t in news_texts if t]
    event_texts = []
    di = 0
    while f"D-p{di}" in old_by_id:
        event_texts.append(old_by_id[f"D-p{di}"])
        di += 1
    return opening, b_texts, news_texts, event_texts


def previews_from_narration_texts(texts: list[str]) -> list[dict]:
    """Normalize narration previews into the title+summary contract."""
    previews: list[dict] = []
    for text in texts:
        raw = strip_opening_theme_prefix(str(text or ""))
        raw = strip_opening_end_phrase(raw)
        title, sep, summary = raw.partition("[pause short]")
        if not sep:
            # Fallback for recovered legacy text: the first sentence is the
            # hook title and the rest is the spoken summary.
            first, _, rest = raw.partition("。")
            title = first + "。" if rest else first
            summary = rest
        previews.append({"title": title.strip(), "summary": summary.strip()})
    return previews


def block_of_segment(seg_id: str) -> set[str]:
    """Map a segment id to the content block(s) it belongs to.

    OPENING / S01 / A-* belong to block A; B* to block B; C-* to C; D-* to D.
    OPENING is a fixed external asset, so it carries no TTS text.
    """
    if seg_id.startswith("A-") or seg_id == "OPENING":
        return {"A"}
    if seg_id.startswith("B"):
        return {"B"}
    if seg_id.startswith("C-"):
        return {"C"}
    if seg_id.startswith("D-"):
        return {"D"}
    return set()


def tts_queue_push(date: str, block: str, blocks_done: set[str]) -> None:
    """Queue a finalized block for TTS and wake the background runner.

    Failure to queue is non-fatal: writing continues, and the final whole-
    manifest dispatch still covers anything that missed the early queue.
    """
    import subprocess as _sp

    issue = issue_dir(date)
    smap_path = issue / "production" / "segment-map.json"
    if not smap_path.is_file():
        print(f"[tts-queue] no segment map yet for {block}; skip early TTS")
        return
    seg_map = json.loads(smap_path.read_text(encoding="utf-8-sig"))
    wanted = [
        seg for seg in seg_map.get("segments", [])
        if block in block_of_segment(str(seg.get("id", "")))
    ]
    if not wanted:
        print(f"[tts-queue] no segments matched for block {block}; skip")
        return
    partial_map = {
        "episode": date,
        "language": seg_map.get("language", "ja-JP"),
        "visual": "partial",
        "voices": seg_map.get("voices", {"default": "xiaomei"}),
        "segments": wanted,
    }
    tmp = smap_path.with_suffix(".ttsqueue.tmp")
    tmp.write_text(json.dumps(partial_map, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    tts_dir = issue / "production" / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    partial_path = tts_dir / f"segment-map.{block}.json"
    tmp.replace(partial_path)

    # Reuse the production prepare_tts to normalize and validate this block.
    # It writes production/tts files for the partial map; those files are the
    # same ones the final whole-manifest dispatch would generate, so nothing
    # is wasted.
    py = sys.executable
    r = _sp.run(
        [py, str(_TOOLS_DIR.parent / "tts" / "prepare_tts.py"), date,
         "--visual", f"production/tts/segment-map.{block}.json",
         "--partial"],
        cwd=str(_US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"[tts-queue] prepare_tts failed for {block}: "
              f"{(r.stderr or r.stdout)[-500:]}")
        return
    manifest = json.loads((tts_dir / "manifest.json").read_text(encoding="utf-8-sig"))
    wanted_ids = {str(seg.get("id", "")) for seg in wanted}
    batch_segs = [
        seg for seg in manifest.get("segments", [])
        if seg.get("type") == "tts" and str(seg.get("id", "")) in wanted_ids
    ]
    if not batch_segs:
        print(f"[tts-queue] no tts segments in prepared manifest for {block}")
        return
    extra = sum(
        1 for seg in manifest.get("segments", [])
        if seg.get("type") == "tts" and str(seg.get("id", "")) not in wanted_ids
    )
    if extra:
        # prepare_tts writes a shared manifest; keep only this block's rows in
        # the queue so a later partial prepare cannot leak past blocks into it.
        print(f"[tts-queue] filtered {extra} out-of-block segments for {block}")

    qpath = tts_dir / "tts-queue.json"
    queue = {"batches": [], "done": False}
    if qpath.is_file():
        try:
            queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            pass
    queue.setdefault("batches", [])
    queue.setdefault("done", False)
    if any(b.get("block") == block for b in queue["batches"]):
        print(f"[tts-queue] block {block} already queued")
        return
    queue["batches"].append({
        "block": block,
        "status": "queued",
        "queued_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "segments": batch_segs,
    })
    with (tts_dir / "tts-queue.lock").open("a+b") as lock_f:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(lock_f.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            if qpath.is_file():
                try:
                    queue = json.loads(qpath.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError):
                    pass
                queue.setdefault("batches", [])
                queue.setdefault("done", False)
            if any(b.get("block") == block for b in queue["batches"]):
                print(f"[tts-queue] block {block} already queued")
                return
            queue["batches"].append({
                "block": block,
                "status": "queued",
                "queued_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "segments": batch_segs,
            })
            tmp = qpath.with_suffix(".tmp")
            tmp.write_text(json.dumps(queue, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
            os.replace(tmp, qpath)
        finally:
            if os.name == "nt":
                import msvcrt
                lock_f.seek(0)
                msvcrt.locking(lock_f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    print(f"[tts-queue] block {block}: {len(batch_segs)} segments queued")

    serve = _TOOLS_DIR / "tts_serve.py"
    _sp.Popen([py, str(serve), date, "--wake"],
              cwd=str(_US_ROOT),
              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Code-orchestrated episode writing")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--only", nargs="+", help="sections to regenerate (A B-1 C D)")
    parser.add_argument("--dry-run", action="store_true", help="show plan without API calls")
    args = parser.parse_args()

    issue = issue_dir(args.issue_date)
    outline_path = issue / OUTLINE_PATH
    if not outline_path.is_file():
        print("[error] outline.json not found; run analyze_topics.py first")
        return 1
    outline = json.loads(outline_path.read_text(encoding="utf-8-sig"))
    adopted = adopted_candidates(outline)
    n = len(adopted)
    if n == 0:
        print("[error] no adopted B candidates in outline.json")
        return 1

    only = set(args.only or [])
    want = lambda s: not only or s in only  # noqa: E731

    print(f"[write] {args.issue_date}: {n} B themes, 8 news, "
          f"{'events' if outline.get('events_d_needed') else 'no events'}")
    if args.dry_run:
        for i, c in enumerate(adopted, 1):
            print(f"  B-{i}: {c.get('title', '')[:60]}")
        return 0

    if not text_llm.is_configured():
        print("[error] text_llm not configured")
        return 1

    opening: dict = {}
    b_texts: dict[int, str] = {}
    news_texts: list[str] = []
    event_texts: list[str] = []

    def refresh_partial_map() -> None:
        """Rebuild segment-map.json from whatever is finalized so far."""
        _, _, smap = build_config_and_script(
            args.issue_date, outline, opening, b_texts,
            news_texts, event_texts, partial=True)
        map_path = issue / "production" / "segment-map.json"
        map_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = map_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(smap, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        tmp.replace(map_path)

    try:
        if want("A"):
            print("[A] opening package...")
            opening = gen_opening_package(args.issue_date, outline)
            refresh_partial_map()
            tts_queue_push(args.issue_date, "A", {"A"})
        if want("C"):
            print("[C] news package...")
            news_texts = gen_news_package(args.issue_date, outline)
            refresh_partial_map()
            tts_queue_push(args.issue_date, "C", {"C"})
        if want("D"):
            print("[D] events package...")
            event_texts = gen_events_package(outline)
            refresh_partial_map()
            tts_queue_push(args.issue_date, "D", {"D"})
        for i, cand in enumerate(adopted, 1):
            if want(f"B-{i}"):
                print(f"[B-{i}] {cand.get('title', '')[:50]}...")
                b_texts[i] = gen_b_theme(args.issue_date, cand, i)
        refresh_partial_map()
        tts_queue_push(args.issue_date, "B", {"B"})
    except Exception as e:
        print(f"[error] generation failed: {e}")
        return 2

    if only:
        old_opening, old_b, old_news, old_events = load_old_sections(args.issue_date, n)
        if not opening and old_opening.get("previews"):
            opening = old_opening
        for i in range(1, n + 1):
            if i not in b_texts and i in old_b:
                b_texts[i] = old_b[i]
        if not news_texts and old_news:
            news_texts = old_news
        if not event_texts and old_events:
            event_texts = old_events

    missing = [f"B-{i}" for i in range(1, n + 1) if i not in b_texts]
    if missing:
        print(f"[error] missing B theme texts: {', '.join(missing)}")
        return 1
    if len(news_texts) != 8:
        print(f"[error] news count={len(news_texts)} (expected 8)")
        return 2

    config, script, segment_map = build_config_and_script(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)
    config_path = issue / CONFIG_PATH
    script_path = issue / SCRIPT_PATH
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    script_path.write_text(
        json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    map_path = issue / "production" / "segment-map.json"
    map_path.write_text(
        json.dumps(segment_map, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    # Per-block early prepares overwrite manifest.json with partial maps, so
    # rebuild the canonical full manifest before queueing B.
    print("[write] rebuilding full TTS manifest...")
    prep = subprocess.run(
        [sys.executable, str(_TOOLS_DIR.parent / "tts" / "prepare_tts.py"),
         args.issue_date],
        cwd=str(_US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    if prep.returncode != 0:
        print(f"[warn] full prepare_tts failed: "
              f"{(prep.stderr or prep.stdout)[-500:]}")
    else:
        print(f"[write] full TTS manifest -> {map_path.parent / 'tts' / 'manifest.json'}")
    print(f"[write] config -> {config_path}")
    print(f"[write] segment-map -> {map_path}")
    print(f"[write] script -> {script_path} ({len(script['blocks'])} blocks)")

    write_draft_markdown(args.issue_date, outline, opening, b_texts,
                         news_texts, event_texts)
    print("[write] draft-{A,B,C,D}.md written")

    brief_path = generate_visual_brief(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)
    visual_path = generate_visual_data(
        args.issue_date, outline, opening, b_texts, news_texts, event_texts)
    print(f"[write] visual-brief -> {brief_path}")
    print(f"[write] visual-data -> {visual_path}")

    print("[validate] running build_pipeline.py validate...")
    ok, output = validate_with_build_pipeline(args.issue_date)
    if not ok:
        print(f"[validate] FAILED:\n{output[-2000:]}")
        return 2

    # Contract repair for adopted themes beyond the legacy B4 limit. The text,
    # TTS queue entries and audio may already exist, but pipeline.mjs can only
    # see draft-B5 after model manual action unless the writer closes the loop.
    cli = _US_ROOT / "tools" / "pipeline" / "pipeline.mjs"
    for i in range(1, len(adopted) + 1):
        item = f"draft-B{i}"
        p = subprocess.run(
            ["node", str(cli), "set", "--date", args.issue_date,
             "--id", item, "--state", "done",
             "--note", "writer final validation passed"],
            cwd=str(_US_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30)
        if p.returncode != 0:
            print(f"[warn] pipeline state update failed for {item}: "
                  f"{(p.stderr or p.stdout)[-300:]}")

    print("[validate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

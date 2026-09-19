"""Two-stage topic selection via LLM API with code-enforced hard gates.

Stage 0 (code, no tokens):   Read manifest, apply hard-gate pre-filters
                             (category weights, min length, duplicate anchors).
Stage 1 (flash API):         Shortlist 15-20 candidates from the filtered manifest.
Stage 2 (pro API):           Score + rank shortlisted candidates using their
                             full text, topic history, and economic calendar.

Usage:
  python analyze_topics.py 2026-09-12
  python analyze_topics.py 2026-09-12 --stage shortlist    # re-run stage 1 only
  python analyze_topics.py 2026-09-12 --stage score        # re-run stage 2 only
  python analyze_topics.py 2026-09-12 --dry-run            # stage 0 only, show counts
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
sys.path.insert(0, str(_TOOLS_DIR))

import text_llm  # noqa: E402


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MANIFEST_PATH = "collection/00-manifest.md"
SHORTLIST_PATH = "production/shortlist.json"
OUTLINE_PATH = "production/outline.json"
TOPIC_HISTORY = _US_ROOT / "db" / "topic-history.md"

# Category weights used by stage 0 pre-filtering (higher = more likely relevant).
CATEGORY_WEIGHTS = {
    "market": 0.9, "macro": 0.9, "earnings": 0.95, "research": 0.85,
    "news": 0.5, "stock": 0.6,
}

# Minimum body length for a candidate to be considered for B themes.
MIN_BODY_CHARS = 800
SHORTLIST_EVIDENCE_CHARS = 700
MAX_ARTICLE_CHARS = 12000

# Stage 1 shortlist target (agent equivalent: scanning the manifest).
SHORTLIST_TARGET = 18

# Stage 2 output schema.
OUTLINE_SCHEMA = {
    "type": "object",
    "required": ["b_candidates", "news_highlights", "events_d_needed"],
    "properties": {
        "b_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["rank", "title", "question_hook", "source_ids",
                             "scores", "total_score", "is_macro", "anchor",
                             "duplicate_check"],
                "properties": {
                    "rank": {"type": "integer", "minimum": 1},
                    "title": {"type": "string"},
                    "question_hook": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "scores": {
                        "type": "object",
                        "required": ["a", "b", "c", "e", "f", "g", "h", "i", "j"],
                        "properties": {
                            k: {"type": "integer", "minimum": 0, "maximum": 3}
                            for k in ("a", "b", "c", "e", "f", "g", "h", "i", "j")
                        },
                    },
                    "total_score": {"type": "number"},
                    "is_macro": {"type": "boolean"},
                    "anchor": {"type": "string"},
                    "duplicate_check": {"type": "string",
                                        "enum": ["new", "continuation", "rejected"]},
                    "continuation_approval": {"type": "string"},
                },
            },
        },
        "news_highlights": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["source_id", "title_ja"],
                "properties": {
                    "source_id": {"type": "string"},
                    "title_ja": {"type": "string"},
                },
            },
        },
        "events_d_needed": {"type": "boolean"},
        "events_d_summary": {"type": "string"},
        "notes": {"type": "string"},
    },
}


def issue_dir(date: str) -> Path:
    d = _US_ROOT / "daily-output" / date
    if not d.is_dir():
        raise SystemExit(f"[error] issue directory not found: {d}")
    return d


# ---------------------------------------------------------------------------
# Stage 0: manifest parsing + hard-gate pre-filter (pure code)
# ---------------------------------------------------------------------------

def parse_manifest(path: Path) -> list[dict]:
    """Parse the markdown manifest table into structured records."""
    rows: list[dict] = []
    header_seen = False
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 10:
            continue
        if cells[0] == "ID":
            header_seen = True
            continue
        if not header_seen or cells[0].startswith("-"):
            continue
        try:
            body_len = int(cells[9])
        except (ValueError, IndexError):
            body_len = 0
        rows.append({
            "id": cells[0],
            "category": cells[1].lower(),
            "title": cells[3],
            "source": cells[4],
            "type": cells[5],
            "body_len": body_len,
        })
    return rows


def load_topic_history(n_recent: int = 3) -> list[dict]:
    """Load the most recent n dates' anchor entries from topic-history.md."""
    if not TOPIC_HISTORY.is_file():
        return []
    entries: list[dict] = []
    for line in TOPIC_HISTORY.read_text(encoding="utf-8-sig").splitlines():
        m = re.match(r"^\|\s*(\d{4}-\d{2}-\d{2})\s*\|\s*(B-\d+)\s*\|\s*(.+?)\s*\|", line)
        if m:
            entries.append({"date": m.group(1), "slot": m.group(2), "anchor": m.group(3)})
    if not entries:
        return []
    dates = sorted({e["date"] for e in entries}, reverse=True)[:n_recent]
    return [e for e in entries if e["date"] in dates]


def _extract_anchor_keywords(anchor: str) -> set[str]:
    """Extract significant tokens from an anchor string for overlap checking."""
    stop = {"の", "と", "に", "を", "は", "が", "へ", "から", "まで", "する",
            "した", "れた", "stock", "market", "us", "株", "市場", "決算",
            "発表", "発表", "ドル", "円", "大型", "大型"}
    words = re.findall(r"[A-Za-z]{3,}|[\u3040-\u9fff]{2,}", anchor)
    return {w.lower() for w in words if w.lower() not in stop}


def hard_gate_filter(items: list[dict], history: list[dict]) -> tuple[list[dict], list[dict]]:
    """Apply code-level pre-filters. Returns (passed, rejected)."""
    history_keywords: list[set[str]] = [
        _extract_anchor_keywords(e["anchor"]) for e in history
    ]
    passed, rejected = [], []
    for item in items:
        weight = CATEGORY_WEIGHTS.get(item["category"], 0.3)
        # Reject items that are too short to support a B theme.
        if item["body_len"] < MIN_BODY_CHARS and item["type"] != "data":
            rejected.append({**item, "reason": f"too short ({item['body_len']} chars)"})
            continue
        # Duplicate anchor check: high keyword overlap with a recent B theme.
        title_words = _extract_anchor_keywords(item["title"])
        dup = False
        for hk in history_keywords:
            if hk and len(title_words & hk) / max(len(title_words), 1) > 0.6:
                dup = True
                break
        if dup:
            rejected.append({**item, "reason": "duplicate anchor in recent 3 episodes"})
            continue
        passed.append({**item, "category_weight": weight})
    return passed, rejected


def read_article_text(issue: Path, item_id: str) -> str:
    """Read a single article's full text from collection/ directory."""
    for pattern in ("*.md", "*.txt"):
        for f in (issue / "collection").glob(pattern):
            if item_id in f.stem or item_id in f.name:
                return f.read_text(encoding="utf-8-sig")[:MAX_ARTICLE_CHARS]
    return ""


def extract_evidence(issue: Path, item_id: str) -> str:
    """Select deterministic high-signal sentences for shortlist review."""
    text = read_article_text(issue, item_id)
    if not text:
        return ""
    if text.startswith("---"):
        text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.DOTALL)
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[#>*`_\[\]()]", " ", text)
    terms = re.compile(
        r"(?i)( Fed |FOMC|PPI|CPI|GDP|AI |data center|power demand|revenue|"
        r"earnings|guidance|margin|yield|inflation|tariff|capex|金利|決算|"
        r"設備投資|債券|原油|半導体|サプライチェーン|株)"
    )
    candidates = []
    for pos, raw in enumerate(re.split(r"(?<=[.。！？!?])\s+|\n+", text)):
        sentence = re.sub(r"\s+", " ", raw).strip()
        if not 30 <= len(sentence) <= 420:
            continue
        score = 1.0
        if re.search(r"\d", sentence):
            score += 1.0
        if terms.search(sentence):
            score += 1.4
        score += max(0.0, 0.8 - pos * 0.005)
        candidates.append((score, pos, sentence))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    chosen = sorted(candidates[:6], key=lambda x: x[1])
    return " ".join(s for _, _, s in chosen)[:SHORTLIST_EVIDENCE_CHARS]


# ---------------------------------------------------------------------------
# Stage 1: shortlist via flash API
# ---------------------------------------------------------------------------

def run_shortlist(date: str, items: list[dict], history: list[dict]) -> list[str]:
    """Ask flash-tier LLM to pick SHORTLIST_TARGET candidates from the manifest."""
    issue = issue_dir(date)
    valid_ids = {it["id"] for it in items}
    manifest_summary = "\n".join(
        f"- {it['id']} [{it['category']}] {it['title']} ({it['body_len']}字)\n"
        f"  要点: {extract_evidence(issue, it['id']) or '（抽出できず）'}"
        for it in items
    )
    history_summary = "\n".join(
        f"  {e['date']} {e['slot']}: {e['anchor']}" for e in history
    ) or "（記録なし）"

    prompt = f"""あなたは米国株投資番組のテーマ選定エディターです。
以下の素材リストから、B（メインテーマ・7-12分の深掘り解説）の候補として有望な
{SHORTLIST_TARGET}件を選んでください。

【選定基準】
1. 米国株への直接的影響（ハードゲート）
2. 情報の非対称価値（リスナーが自分で調べても分からない深掘り材料）
3. 7分以上の解説を支える素材量（タイトルと素材長から推測）
4. 個別企業・産業構造系を優先（マクロ系は上限2件）

【直近3集の放送済みテーマ（これと重複する主題は除外）】
{history_summary}

【素材リスト】
{manifest_summary}

【出力形式】有効な JSON のみ:
{{"selected": ["素材ID1", "素材ID2", ...], "reasons": {{"素材ID": "選定理由の1文"}}}}"""

    schema = json.dumps({
        "type": "object", "required": ["selected"],
        "properties": {"selected": {"type": "array", "items": {"type": "string"}}},
    })
    result = text_llm.generate_json(prompt, tier="flash", schema_hint=schema)
    valid_ids = {it["id"] for it in items}
    selected_ids = [
        x for x in dict.fromkeys(result.get("selected", []))
        if isinstance(x, str) and x in valid_ids
    ]
    if not selected_ids:
        raise RuntimeError("shortlist returned no valid material IDs")
    selected_ids = selected_ids[:SHORTLIST_TARGET]
    reasons = result.get("reasons", {})

    out_path = issue / SHORTLIST_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "date": date, "generated_at": datetime.now().isoformat(timespec="seconds"),
        "stage": "shortlist", "selected": selected_ids, "reasons": reasons,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[shortlist] {len(selected_ids)} candidates -> {out_path}")
    return selected_ids


# ---------------------------------------------------------------------------
# Stage 2: score + rank via pro API
# ---------------------------------------------------------------------------

def run_scoring(date: str, selected_ids: list[dict], history: list[dict]) -> dict:
    """Ask pro-tier LLM to score and rank shortlisted candidates with full text."""
    issue = issue_dir(date)
    articles: list[str] = []
    for sid in selected_ids:
        text = read_article_text(issue, sid)
        if text:
            articles.append(f"=== {sid} ===\n{text}")
    joined_articles = "\n\n".join(articles)

    history_summary = "\n".join(
        f"  {e['date']} {e['slot']}: {e['anchor']}" for e in history
    ) or "（記録なし）"

    rubric = """各候補を以下の軸で0-3点採点し、重み付き合計で順位付け:
  a. 前日メインロジックの深層 (重み1.2)
  b. 将来への重大影響 (重み1.2)
  c. 個人投資家の関心度 (重み1.0)
  e. 情報非対称価値 (重み1.5・最重要)
  f. 深掘り素材の品質 (重み1.2)
  g. 独立性・反直観 (重み1.0)
  h. 可操作性・アクション指針 (重み1.3)
  i. 教学価値 (重み0.8)
  j. 防守視点 (重み0.8)

ハードゲート（コードで事前確認済みだが再確認）:
  - 米国株関連性: 中国語ソースは米国株との高い関連性がある場合のみ
  - 重複排除: 主アンカーが直近3集と一致する場合は継続主題の3条件を確認"""

    prompt = f"""あなたは米国株投資番組（日本語・個人投資家向け・長期安定志向）の
チーフエディターです。以下の候補記事を読み、B（メインテーマ）候補5件を選定・採点し、
C（ニュース8本）とD（イベント予告の要否）も判断してください。

{rubric}

【直近3集の放送済みテーマ（重複排除の照合用）】
{history_summary}

【候補記事の全文】
{joined_articles}

【出力要件】
- b_candidates: 5件、rank順にソート
- 各候補のanchor は「一言で言い表す中心」(企業名・固有イベント・固有データのいずれか)
- duplicate_check: 直近3集との照合結果 ("new" | "continuation" | "rejected")
- "continuation" の場合は continuation_approval に
  「継続主題承認: <前集日> <B枠> → <当日の新事実1文>」を記入
- is_macro: 金利・為替・金融政策・統計・地政学が主軸なら true
- news_highlights: 8本、title_ja は30字以内の結論型
- events_d_needed: 直近3営業日に重要イベントがあれば true"""

    result = text_llm.generate_json(prompt, tier="pro", schema_hint=json.dumps(OUTLINE_SCHEMA, ensure_ascii=False))
    schema_errors = text_llm.validate_schema(result, OUTLINE_SCHEMA)
    if schema_errors:
        repair_prompt = (
            prompt
            + "\n\n【前回の出力検証エラー】"
            + "\n".join(f"- {e}" for e in schema_errors[:20])
            + "\n上記エラーを修正し、有効な JSON のみをもう一度出力してください。"
        )
        print(f"[score] schema repair: {len(schema_errors)} errors", file=sys.stderr)
        result = text_llm.generate_json(
            repair_prompt, tier="pro",
            schema_hint=json.dumps(OUTLINE_SCHEMA, ensure_ascii=False),
            max_retries=1,
        )
        schema_errors = text_llm.validate_schema(result, OUTLINE_SCHEMA)
        if schema_errors:
            raise RuntimeError("outline schema invalid after repair: " + "; ".join(schema_errors[:10]))

    # Hard gate: the LLM must not keep candidates it itself marked rejected.
    # Drop them deterministically instead of failing the whole run, then
    # renumber ranks so downstream stages see a clean ordered list.
    rejected_dropped = [
        c.get("title", "?") for c in result.get("b_candidates", [])
        if c.get("duplicate_check") == "rejected"
    ]
    if rejected_dropped:
        result["b_candidates"] = [
            c for c in result["b_candidates"] if c.get("duplicate_check") != "rejected"
        ]
        for i, c in enumerate(result["b_candidates"], 1):
            c["rank"] = i
        print(f"[score] hard gate: dropped rejected duplicates: {rejected_dropped}", file=sys.stderr)

    # Post-validation in code: structural balance rules from phase1-triage.md
    errors = _validate_balance(result)
    if errors:
        print(f"[warn] structural balance issues: {errors}", file=sys.stderr)
        result["validation_warnings"] = errors

    out_path = issue / OUTLINE_PATH
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result["date"] = date
    result["generated_at"] = datetime.now().isoformat(timespec="seconds")
    result["stage"] = "score"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[score] {len(result.get('b_candidates', []))} candidates -> {out_path}")
    return result


def _validate_balance(outline: dict) -> list[str]:
    """Code-enforced structural balance from phase1-triage.md Gate #1."""
    errors: list[str] = []
    cands = outline.get("b_candidates", [])
    if len(cands) < 3 or len(cands) > 5:
        errors.append(f"b_candidates count={len(cands)} (expected 3-5)")
    macros = [c for c in cands[1:] if c.get("is_macro")]
    if len(macros) > 2:
        errors.append(f"macro candidates={len(macros)} (max 2 excluding B-1)")
    dup_rejected = [c for c in cands if c.get("duplicate_check") == "rejected"]
    if dup_rejected:
        errors.append(f"rejected duplicates in final list: {[c.get('title') for c in dup_rejected]}")
    for c in cands:
        if c.get("duplicate_check") == "continuation" and not c.get("continuation_approval"):
            errors.append(f"continuation without approval: {c.get('title')}")
    news = outline.get("news_highlights", [])
    if len(news) != 8:
        errors.append(f"news_highlights count={len(news)} (expected 8)")
    return errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Two-stage topic selection")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--stage", choices=("shortlist", "score"), help="re-run a single stage")
    parser.add_argument("--dry-run", action="store_true", help="stage 0 only, show counts")
    args = parser.parse_args()

    issue = issue_dir(args.issue_date)
    manifest_path = issue / MANIFEST_PATH
    if not manifest_path.is_file():
        print(f"[error] manifest not found: {manifest_path}")
        return 1

    items = parse_manifest(manifest_path)
    history = load_topic_history(3)
    passed, rejected = hard_gate_filter(items, history)
    print(f"[stage0] {len(items)} items -> {len(passed)} passed, {len(rejected)} rejected by hard gates")
    for r in rejected[:5]:
        print(f"  REJECT {r['id']}: {r['reason']}")
    if len(rejected) > 5:
        print(f"  ... and {len(rejected) - 5} more")

    if args.dry_run:
        return 0

    if not text_llm.is_configured():
        print("[error] text_llm not configured; set GEMINI_API_KEY or OPENAI_COMPAT_* env vars")
        return 1

    shortlist_path = issue / SHORTLIST_PATH
    if args.stage == "score" and shortlist_path.is_file():
        cached = json.loads(shortlist_path.read_text(encoding="utf-8-sig"))
        selected_ids = cached.get("selected", [])
        print(f"[stage1] using cached shortlist ({len(selected_ids)} candidates)")
    elif args.stage == "score":
        print("[error] --stage score requires shortlist.json (run full or --stage shortlist first)")
        return 1
    else:
        selected_ids = run_shortlist(args.issue_date, passed, history)

    if args.stage == "shortlist":
        return 0

    outline = run_scoring(args.issue_date, selected_ids, history)
    warnings = outline.get("validation_warnings", [])
    if warnings:
        for w in warnings:
            print(f"  BALANCE WARN: {w}")
        return 2  # non-zero but recoverable: human review of outline.json
    print("[done] outline.json generated, balance check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

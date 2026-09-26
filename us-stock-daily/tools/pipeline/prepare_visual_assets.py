"""Prepare concrete image files required by visual-data.json.

Naming contract: one issue-root-relative PNG per B narration page
(`assets/b<theme>-<page>.png`), plus the fixed `assets/opening.png` title
background.

2026-09-18 resolution contract:
- B p1 is derived from the whole theme article. p2.. are derived per
  paragraph and reuse p1's image unless the paragraph's main entity deviates.
- Subject/keyword priority: (1) product launch -> product photo -> launch
  event photo; news event -> original news photo. (2) acting subject ->
  company/institution building photo with a clearly visible name, or person
  photo (portrait only for analyst quotes; otherwise on-site scene photo).
  (3) abstract subject (market move, sentiment, macro data) -> generated
  theme illustration via imagegen only; Mac fallback is forbidden.
- Search candidates are re-ranked by the text LLM for quality and topical
  fit; the pipeline falls back to deterministic heuristics without an API.
- Every saved image records a portrait flag. Portraits render as a centered
  circle in the left visual column; all other images fill it full-height.
- Keywords that produced a saved image are counted in db/media-assets.sqlite3.
  Past KEYWORD_PROMOTION_THRESHOLD uses the image is copied to the shared
  assets/media_resources/ directory and reused directly afterwards.

2026-09-24 quality contract (fix list A-F):
- Photo keywords must name a photographable entity; abstract subjects
  (indices, market mood, macro numbers) route to generation or to a
  photographable proxy (visual_quality.py).
- Image search runs WITHOUT a time filter (quality photos live on old
  pages); news collection keeps its own day filter.
- Every candidate is reviewed by a vision LLM before adoption; the
  "largest pixels" fallback and the sticky LLM_DISABLED flag are removed.
- Saved images are pre-cropped to the left-column display aspect (~0.71)
  with the vision-chosen focus point; generated images are 768x1024
  portrait and pass a vision self-check (max 3 attempts).
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import itertools
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import episode_contract  # noqa: E402
import media_asset_db  # noqa: E402
import text_llm  # noqa: E402
import visual_quality  # noqa: E402
from episode_contract import (  # noqa: E402
    OPENING_TEMPLATE_ASSET,
    OPENING_VISUAL_ASSET,
    THEME_PAGE_COUNT,
    theme_base_image_asset,
    theme_image_asset,
)

REPO = Path(__file__).resolve().parents[3]
US_ROOT = REPO / "us-stock-daily"
IMG_RE = re.compile(r"<img[^>]+src=[\"']([^\"']+)[\"']", re.I | re.S)

SUBJECT_TYPES = {
    "product", "event-news", "company", "institution",
    "person-analyst", "person-other", "abstract",
}

# Left display column: 40% of 1920 = 768 px wide, 1080 px tall.
DISPLAY_ASPECT = 768 / 1080
ASPECT_TOLERANCE = 0.08
MIN_LONG_EDGE = 800
MAX_CANDIDATES = 6
MAX_P1_REUSE_PER_THEME = 4

def rel_to(base: Path, target: Path) -> str:
    base = base.resolve()
    target = target.resolve()
    try:
        return target.relative_to(base).as_posix()
    except ValueError:
        parts: list[str] = []
        for parent in base.parents:
            try:
                rel = target.relative_to(parent)
                parts = [".."] * len(base.parents[:base.parents.index(parent) + 1])
                parts.extend(rel.parts)
                break
            except ValueError:
                continue
        if not parts:
            raise ValueError(f"{target} is not relative to {base}")
        return Path(*parts).as_posix()


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid,
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


@contextlib.contextmanager
def single_run_lock(issue: Path):
    """One prepare_visual_assets process per issue; concurrent runs corrupt meta."""
    path = issue / "production" / "visual-assets.lock"
    pid_path = issue / "production" / "visual-assets.pid"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as f:
        # "a+b" starts at EOF on Windows; always lock/unlock byte 0 so the
        # regions match regardless of file content.
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raw = ""
            try:
                raw = pid_path.read_text(encoding="ascii").strip()
            except OSError:
                pass
            other = int(raw) if raw.isdigit() else None
            alive = _pid_alive(other) if other else False
            raise SystemExit(
                "[visual] another prepare_visual_assets run holds the lock"
                + (f" (pid={other}, alive={alive})" if other else "")
                + "; wait for it or investigate before restarting"
            )
        try:
            # Never truncate/rewrite the lock file while holding it: on
            # Windows that can invalidate the locked byte range.
            pid_path.write_text(str(os.getpid()), encoding="ascii")
            yield
        finally:
            f.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def write_progress(date: str, **fields) -> None:
    """Heartbeat file so stalls are observable without guessing from silence."""
    path = US_ROOT / "daily-output" / date / "production" / "visual-progress.json"
    data: dict = {}
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            data = {}
    data.update(fields)
    data["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    os.replace(tmp, path)


def load_rows(date: str) -> list[dict]:
    brief = US_ROOT / "daily-output" / date / "production" / "visual-brief.md"
    rows: list[dict] = []
    for line in brief.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("| s"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 7 or cols[5] == "候補アセット":
            continue
        if not cols[5] or cols[6] == "no-asset":
            continue
        rows.append({
            "slide": cols[0], "block": cols[1], "kind": cols[2],
            "heading": cols[3], "asset_kind": cols[4], "asset": cols[5],
            "status": cols[6],
        })
    if not rows:
        raise RuntimeError(f"no asset rows in {brief}; run write_blocks.py first")
    return rows


def load_brief_data(date: str) -> dict:
    """Machine-readable brief written by write_blocks.py (paragraph texts)."""
    path = US_ROOT / "daily-output" / date / "production" / "visual-brief.json"
    if not path.is_file():
        return {"themes": []}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fix_visual_data_refs(date: str, replacements: dict[str, str]) -> None:
    if not replacements:
        return
    path = US_ROOT / "daily-output" / date / "production" / "visual-data.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    for slide, html in list(data.get("slices", {}).items()):
        updated = html
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        if updated != html:
            data["slices"][slide] = updated
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


PREVIEW_FRAME_RE = re.compile(
    r'(<div class="photo-frame )(preview-photo[^"]*)"'
    r'([^>]*><img src=")(assets/b\d+-1\.png)(")'
)


def apply_preview_portrait_style(date: str, portrait_rels: set[str]) -> None:
    """Sync the s1 carousel portrait style with image-meta portrait flags."""
    path = US_ROOT / "daily-output" / date / "production" / "visual-data.json"
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    html = data.get("slices", {}).get("s1", "")
    if not html:
        return

    def restyle(match: re.Match) -> str:
        rel = match.group(4)
        classes = match.group(2).replace(" portrait", "")
        if rel in portrait_rels:
            classes = "portrait " + classes
        return f'{match.group(1)}{classes}"{match.group(3)}{rel}{match.group(5)}'

    updated = PREVIEW_FRAME_RE.sub(restyle, html)
    if updated != html:
        data["slices"]["s1"] = updated
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )


def update_brief(date: str, statuses: dict[str, tuple[str, str]], out_dir: Path) -> None:
    path = US_ROOT / "daily-output" / date / "production" / "visual-brief.md"
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("| s"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            if cols[0] in statuses:
                status, asset = statuses[cols[0]]
                cols[5], cols[6] = asset, status
                line = "| " + " | ".join(cols) + " |"
        out.append(line)
    out += [
        "",
        "## prepare_visual_assets log",
        "",
        f"- run: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
        f"- manifest: {rel_to(US_ROOT, out_dir / 'manifest.jsonl')}",
    ]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def manifest_entry(
    target: Path,
    assets_dir: Path,
    block: str,
    source: str,
    state: str,
    extra: dict | None = None,
) -> str:
    if not target.is_file():
        raise FileNotFoundError(f"manifest target does not exist: {target}")
    payload = {
        "block": block,
        "asset": rel_to(assets_dir.parent, target),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "source": source,
        "state": state,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    payload.update(extra or {})
    return json.dumps(payload, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Subject derivation and deviation judgment (LLM with heuristic fallback)
# ---------------------------------------------------------------------------

def _llm_json(prompt: str, schema: dict) -> Any | None:
    """One text-LLM JSON call; failures degrade this call only (never the run).

    2026-09-24: the old sticky LLM_DISABLED flag made one API hiccup degrade
    every later decision to largest-pixel heuristics; it is removed by design.
    """
    if not text_llm.is_configured():
        return None
    try:
        return text_llm.generate_json(
            prompt, "flash", schema_hint=json.dumps(schema, ensure_ascii=False),
            max_retries=2,
        )
    except Exception as e:  # noqa: BLE001 - degrade to heuristics
        print(f"[visual] LLM call failed, heuristic fallback for this item: {str(e)[:200]}")
        return None


def _vision_json(prompt: str, images: list[Path], schema: dict) -> Any | None:
    """One vision-LLM JSON call over local images (downscaled to ~512px)."""
    if not text_llm.is_configured() or not images:
        return None
    try:
        return text_llm.generate_json_with_images(
            prompt, images, "pro",
            schema_hint=json.dumps(schema, ensure_ascii=False),
            max_retries=2,
        )
    except Exception as e:  # noqa: BLE001 - degrade to mechanical rules
        print(f"[visual] vision call failed: {str(e)[:200]}")
        return None


def derive_subject(text: str, *, first_page: bool) -> dict:
    """Derive image route/keywords for one article (p1) or paragraph (p2+)."""
    basis = "テーマ記事全体" if first_page else "この段落"
    rules = "\n".join([
        "① 新製品発表: 製品写真 → 発表会・イベント会場写真のキーワード。講話・声明などのニュース事件: 記事配図の元写真に相当するキーワード",
        "② 行動主体（企業・経営者・FRB・大統領/政府高官・政府機関・投資銀行・アナリスト・新製品）: 企業・機関等は社名・機関名が鮮明に写る建物写真。人物はアナリスト見解の引用のみ portrait、それ以外の人物は現場・講演・会見の高解像度写真",
        "③ 抽象主体（市場走势・心理・価格変動・マクロデータ等の具体実体なし）: route=generate（生成テーマ画像）",
    ])
    keyword_rules = "\n".join([
        "【keywords の鉄則（厳守）】",
        "- keywords の各語は必ず「写真に撮れる実体」を含む: 企業名・機関名・人名・製品名・建物名など。",
        "  実体名なしの抽象語（例: S&P 500、NASDAQ、市場心理、利回り、インフレ）だけで検索・生成しないこと。",
        "- 指数・ETF・市況・センチメント・マクロ数値は写真が存在しない抽象対象。subject_type=abstract として",
        "  route=generate にするか、現実の代理実体へ変換する（S&P 500 → NYSE 証券取引所ビル、",
        "  FRB政策 → Eccles Building、ホワイトハウス → 建物外観）。代理実体を使う場合は keywords にその",
        "  代理実体名を明記し、photographable=true とする。",
        "- 有名な指数・政策テーマには標準の撮影可能代理実体がある（S&P500/NYSE=NYSEビル、",
        "  Nasdaq=Nasdaq MarketSite、FRB=Fed本部ビル、国债=財務省ビル、米政府=ホワイトハウス/議会議事堂）。",
        "  これらは route=photo + 代理実体 keyword を優先し、安易に generate にしないこと。",
        "- 親会社と子会社・ブランドは混同しない。本文の行動主体が「SB Energy」なら SoftBank Group でなく",
        "  「SB Energy」という正確な実体名を keyword に使うこと。",
        "- 各 keyword は英語 2〜6 語の検索 suitable 表現（例: \"SB Energy data center\"）。",
    ])
    prompt = "\n".join([
        f"画像取得の主体判定を行ってください。判定対象は{basis}です。",
        "",
        "優先順位（厳守）:",
        rules,
        "",
        keyword_rules,
        "",
        "対象テキスト:",
        text[:4000],
        "",
        "keywords は検索/生成に使う短い実用的キーワード（英語可）優先度順で最大3つ。",
        "photographable は「keywords の主体が現実の写真に撮れる実体か」の判定（抽象指数・市況は false）。",
    ])
    schema = {
        "type": "object",
        "required": ["route", "subject_type", "keywords", "portrait_expected",
                     "photographable"],
        "properties": {
            "route": {"type": "string", "enum": ["photo", "generate"]},
            "subject_type": {"type": "string", "enum": sorted(SUBJECT_TYPES)},
            "keywords": {"type": "array", "items": {"type": "string"},
                         "minItems": 1, "maxItems": 3},
            "portrait_expected": {"type": "boolean"},
            "photographable": {"type": "boolean"},
        },
    }
    result = _llm_json(prompt, schema)
    if isinstance(result, dict):
        keywords = [str(k).strip() for k in result.get("keywords", []) if str(k).strip()]
        subject_type = result.get("subject_type", "")
        if keywords and subject_type in SUBJECT_TYPES:
            route = result.get("route")
            if route not in ("photo", "generate"):
                route = "generate" if subject_type == "abstract" else "photo"
            return _enforce_photographable({
                "route": route,
                "subject_type": subject_type,
                "keywords": keywords[:3],
                "portrait_expected": bool(result.get("portrait_expected", False)),
                "photographable": bool(result.get("photographable", True)),
            })
        print(f"[visual] LLM subject result invalid, using heuristics: {result}")
    return _enforce_photographable(_derive_subject_heuristic(text))


def _enforce_photographable(subject: dict) -> dict:
    """Code-side gate: never let an abstract subject go to photo search.

    The LLM prompt asks for this, but the S&P-500-clipart incident proved a
    hard gate is required: if the keywords name only abstract financial
    concepts, switch route to a photographable proxy query or to generate.
    """
    joined = " ".join(subject.get("keywords", []))
    abstract = visual_quality.is_abstract_subject(joined)
    subject.setdefault("photographable", subject.get("subject_type") != "abstract")
    if subject["route"] == "generate" and abstract:
        proxy = visual_quality.proxy_query(joined)
        if proxy:
            print(f"[visual] abstract '{joined}' has photographable proxy; "
                  f"route=photo '{proxy}'")
            subject["keywords"] = [proxy]
            subject["route"] = "photo"
            subject["subject_type"] = "institution"
            subject["photographable"] = True
            return subject
    if subject["route"] == "photo" and abstract:
        proxy = visual_quality.proxy_query(joined)
        if proxy:
            print(f"[visual] abstract keyword '{joined}' -> proxy photo query '{proxy}'")
            subject["keywords"] = [proxy] + [
                k for k in subject["keywords"]
                if not visual_quality.is_abstract_subject(k)
            ]
            subject["photographable"] = True
        else:
            print(f"[visual] abstract keyword '{joined}' has no proxy; route=generate")
            subject["route"] = "generate"
            subject["subject_type"] = "abstract"
            subject["photographable"] = False
    if subject["route"] == "generate":
        subject["subject_type"] = "abstract"
    return subject


def _latin_tokens(text: str) -> set[str]:
    return {
        tok.lower() for tok in re.findall(r"[A-Za-z][A-Za-z0-9&.%-]{1,}", text)
        if len(tok) >= 2
    }


_LATIN_STOP = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "for", "to", "with",
    "after", "before", "from", "by", "is", "was", "are", "were", "be", "been",
    "new", "its", "his", "her", "their", "this", "that", "these", "those",
    "has", "have", "had", "said", "says", "will", "would", "can", "could",
    "than", "then", "also", "more", "most", "about", "into", "over", "under",
    "between", "during", "because", "while", "when", "where", "which", "who",
    "what", "how", "why", "not", "up", "down", "out", "off", "again", "here",
    "there", "all", "any", "both", "each", "few", "other", "some", "such",
    "only", "own", "same", "so", "too", "very", "just", "now", "january",
    "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


def _entity_tokens(text: str) -> set[str]:
    """Proper-noun proxy for entity deviation (capitalized Latin tokens)."""
    return {
        tok for tok in re.findall(r"[A-Za-z][A-Za-z0-9&.%-]{2,}", text)
        if tok[0].isupper() and tok.lower() not in _LATIN_STOP
    }


def _derive_subject_heuristic(text: str) -> dict:
    entities = sorted(_entity_tokens(text))
    main = max(entities, key=len) if entities else ""
    if not main:
        latin = sorted(_latin_tokens(text), key=len, reverse=True)
        main = latin[0] if latin else ""
    if re.search(r"発表|公開|リリース|unveil|launch", text, re.I) and main:
        return {
            "route": "photo", "subject_type": "product",
            "keywords": [f"{main} product photo", f"{main} launch event"],
            "portrait_expected": False,
        }
    if re.search(r"FRB|連邦準備|大統領|CEO|COO|chair|議長|氏|アナリスト", text):
        analyst = bool(re.search(r"アナリスト|analyst", text, re.I))
        return {
            "route": "photo",
            "subject_type": "person-analyst" if analyst else "person-other",
            "keywords": [f"{main} press conference" if main else "press conference",
                         f"{main} speech" if main else "keynote speech"],
            "portrait_expected": analyst,
        }
    if re.search(r"社|Corp|Inc|銀行|省|省庁|FOMC|IMF|World Bank", text):
        return {
            "route": "photo", "subject_type": "company",
            "keywords": [f"{main} headquarters building" if main else "headquarters building"],
            "portrait_expected": False,
        }
    chunks = [c for c in re.split(r"[\s：、。「」？！・()（）のはがをにでとへも]", text) if len(c) >= 2]
    query = " ".join(chunks[:4]) if chunks else (main or "financial market")
    return {
        "route": "generate", "subject_type": "abstract",
        "keywords": [query[:120]],
        "portrait_expected": False,
    }


def judge_deviation(base_subject: dict, paragraph: str, theme_text: str) -> bool:
    """True when the paragraph's main entity deviates from the theme subject."""
    prompt = "\n".join([
        "テーマの主体と段落の主体を比較してください。",
        "",
        f"テーマ主体: {json.dumps(base_subject, ensure_ascii=False)}",
        "テーマ記事全文（抜粋）:",
        theme_text[:3000],
        "",
        "判定する段落:",
        paragraph[:3000],
        "",
        "段落の行動主体（企業・人物・機関・製品等）がテーマ主体と同じ場合は false、",
        "段落で別の主体・別の実体が主語になっている場合は true。",
    ])
    schema = {
        "type": "object",
        "required": ["deviates"],
        "properties": {"deviates": {"type": "boolean"}},
    }
    result = _llm_json(prompt, schema)
    if isinstance(result, dict) and isinstance(result.get("deviates"), bool):
        return result["deviates"]
    new_entities = _entity_tokens(paragraph) - _entity_tokens(theme_text)
    return len(new_entities) >= 1


# ---------------------------------------------------------------------------
# Search / generation / selection
# ---------------------------------------------------------------------------

def _searxng_images(query: str, engines: str = "") -> list[dict]:
    """One SearXNG image query. NO time filter: photographable quality shots
    live on old pages, and the day filter lets only fresh SEO clipart farms
    survive (2026-09-24 S&P 500 -> flower-'S' incident)."""
    search = US_ROOT / "tools" / "searxng" / "search.ps1"
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
           str(search), query, "-Categories", "images",
           "-TimeRange", "", "-MaxResults", "12", "-Raw"]
    if engines:
        cmd += ["-Engines", engines]
    r = subprocess.run(
        cmd, cwd=str(US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    if r.returncode != 0:
        print(f"[visual] search failed: {query}: {(r.stderr or r.stdout)[-200:]}")
        return []
    try:
        return json.loads(r.stdout).get("results", []) or []
    except json.JSONDecodeError:
        return []


def search_image_results(query: str) -> list[dict]:
    """Merge Wikimedia Commons hits into the SearXNG pool, not instead of it.

    The 2026-09-25 review found the old "Commons-strong => stop" shortcut
    hid SearXNG's top-ranked professional photos (user's Bing/Google manual
    hits) behind 1-2 mediocre Commons files. Both pools are interleaved so
    vision selects from the union. Engine rotation stays as the empty-pool
    fallback for SearXNG's intermittent 0-hit glitches.
    """
    commons = [
        r for r in visual_quality.wikimedia_search(query)
        if visual_quality.entity_overlap(str(r.get("title", "")),
                                         str(r.get("url", "")), query) >= 0.5
    ]
    def _dedup_key(r: dict) -> str:
        return str(r.get("img_src") or r.get("url") or "").split("?")[0]
    seen_urls: set[str] = set()

    def _merge(primary: list[dict], secondary: list[dict]) -> list[dict]:
        merged: list[dict] = []
        for a, b in itertools.zip_longest(primary, secondary):
            for item in (a, b):
                if item is None:
                    continue
                key = _dedup_key(item)
                if key and key not in seen_urls:
                    seen_urls.add(key)
                    merged.append(item)
        return merged

    got = _searxng_images(query, engines="")
    # `commons` is already entity-overlap-filtered; _merge dedups URLs.
    results = _merge(got, commons)
    if results:
        return results
    for attempt, engines in enumerate(("bing images", "duckduckgo images",
                                       "google images"), start=1):
        time.sleep(2 * attempt)
        got = _searxng_images(query, engines=engines)
        if got:
            print(f"[visual] engine fallback '{engines}' returned "
                  f"{len(got)} results for: {query}")
            return _merge(got, commons)
        print(f"[visual] 0 image results via '{engines}': {query}")
    return []


def fetch_image_candidates(query: str, workdir: Path,
                           limit: int = MAX_CANDIDATES) -> list[dict]:
    """Search images and return validated candidates (gates, not best-effort).

    Gates: domain blacklist, thumbnail->full-res URL fixup, Content-Type,
    animated-GIF rejection, long-edge >= MIN_LONG_EDGE, keyword-entity
    overlap (kills the letter-'S' clipart class mechanically).
    Both the article page URL and the actual bytes URL are recorded.
    """
    results = search_image_results(query)
    workdir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    seen_pixels: set[tuple[int, int]] = set()
    for index, result in enumerate(results):
        if len(candidates) >= limit:
            break
        raw_src = (result.get("img_src") or result.get("thumbnail_src")
                   or result.get("url") or "")
        if not raw_src or visual_quality.is_blacklisted(raw_src):
            continue
        url = visual_quality.fullres_url(raw_src)
        # Keyword tokens must appear in title/URL: kills fuzzy-match garbage.
        overlap = visual_quality.entity_overlap(
            str(result.get("title", "")),
            f"{result.get('url', '')} {url}", query,
        )
        if overlap < 0.3:
            print(f"[visual] skip low-overlap ({overlap:.2f}) result: "
                  f"{str(result.get('title', ''))[:60]}")
            continue
        try:
            payload, ctype = visual_quality.download_image(url)
            if ctype and not ctype.startswith("image/"):
                continue
            if len(payload) < 10_000:
                continue
            from PIL import Image, ImageOps
            from PIL import ImageFile
            # Some CDNs end JPEGs a few bytes short; PIL would refuse them.
            ImageFile.LOAD_TRUNCATED_IMAGES = True
            with Image.open(io.BytesIO(payload)) as im:
                im = ImageOps.exif_transpose(im)
                if getattr(im, "n_frames", 1) > 1:
                    continue  # animated GIF/sticker: never usable in slides
                width, height = im.size
                if max(width, height) < MIN_LONG_EDGE:
                    print(f"[visual] skip small ({width}x{height}): {url[:90]}")
                    continue
                key = (width, height)
                if key in seen_pixels:
                    continue
                seen_pixels.add(key)
                out = workdir / f"cand-{len(candidates)}-{index}.png"
                im.convert("RGB").save(out, format="PNG")
            candidates.append({
                "path": out,
                "url": str(result.get("url") or url),
                "bytes_url": url,
                "title": str(result.get("title", ""))[:160],
                "width": width, "height": height,
                "overlap": overlap,
            })
        except Exception as e:  # noqa: BLE001 - try the next result
            print(f"[visual] download failed: {url[:90]}: {e}")
    return candidates


def _mechanical_rank(candidates: list[dict], subject: dict) -> dict | None:
    """Only used when the vision model is unreachable: score by entity
    overlap and resolution *with* the display aspect, never pure largest."""
    scored = []
    for c in candidates:
        aspect = c["width"] / max(c["height"], 1)
        fit = 1.0 / (1.0 + abs(aspect - DISPLAY_ASPECT) * 2.5)
        size = min(1.0, (c["width"] * c["height"]) / (1600 * 1600))
        scored.append((c.get("overlap", 0.5) * 2 + fit + size, c))
    if not scored:
        return None
    chosen = dict(max(scored, key=lambda x: x[0])[1])
    chosen["portrait"] = bool(subject.get("portrait_expected", False))
    chosen["focus"] = (0.5, 0.5)
    chosen["reason"] = "mechanical-rank (vision unavailable)"
    return chosen


def select_candidate(candidates: list[dict], subject: dict, context: str) -> dict | None:
    """Vision LLM reviews the actual candidate images and picks one.

    2026-09-24: the old text-only ranking never saw pixels, so a 7.6MB
    flower-'S' clipart beat real photos on title+size alone. Now every
    candidate thumbnail is shown to the model; all-rejected returns None so
    the caller moves to the next keyword instead of adopting garbage.
    """
    if not candidates:
        return None
    lines = []
    for i, c in enumerate(candidates):
        domain = visual_quality.url_domain(c["url"])
        lines.append(f"{i}: {c['width']}x{c['height']} | {domain} | {c['title']}")
    prompt = "\n".join([
        "画像検索の候補を実際の見本画像として確認し、主題に合う1枚を選んでください。"
        f"画像は {len(candidates)} 枚、index 順に並んでいます。",
        "",
        f"取得主体: {json.dumps(subject, ensure_ascii=False)}",
        f"文脈: {context[:600]}",
        "候補メタ（index | 解像度 | ドメイン | タイトル）:",
        *lines,
        "",
        "select 基準（reject 基準を満たさない候補が複数あれば、この順で優先）:",
        "1. 建物・製品・人など取得主体がはっきり識別でき、かつ社名・機関名の看板やロゴが",
        "   画像内で判読できる高品質な実写写真",
        "2. 画質（解像度・露出・構図）が良い写真。避けたいのは: 逆光で真っ暗、極端な下から",
        "   の見上げ、ブレ、斜め回転（EXIF未補正の回転写真は reject）、社名が読めない遠景のみ",
        "reject 基準（1つでも該当则 acceptable=false）:",
        "- 主題の実体と違う（例: SB Energy のはずが SoftBank Group ロゴ、別人、別建物）",
        "- クリップアート・イラスト・ロゴ単体・GIF風・デコ画像（写真は実写を要求）",
        "- 透かし・大きいコピーライト表記・コラージュ一覧画像",
        "- 極端に低い解像度・ぼやけ・記事サムネイル用トリミングで主体が切れている",
        "- 本文中の人物・企業と無関係な有名人の顔",
        "accept 時: portrait は「顔・胸元の人物プロフィール写真」のみ true。",
        "focus_x/focus_y は左カラム縦位置トリミング時に残すべき主体中心の相対位置(0-1)。",
    ])
    schema = {
        "type": "object",
        "required": ["index", "acceptable", "portrait"],
        "properties": {
            "index": {"type": "integer"},
            "acceptable": {"type": "boolean"},
            "portrait": {"type": "boolean"},
            "focus_x": {"type": "number"},
            "focus_y": {"type": "number"},
            "reason": {"type": "string"},
        },
    }
    images = [c["path"] for c in candidates]
    result = _vision_json(prompt, images, schema)
    if isinstance(result, dict):
        index = result.get("index")
        if (isinstance(index, int) and 0 <= index < len(candidates)
                and result.get("acceptable")):
            chosen = dict(candidates[index])
            chosen["portrait"] = bool(result.get("portrait", False))
            fx = result.get("focus_x")
            fy = result.get("focus_y")
            chosen["focus"] = (
                fx if isinstance(fx, (int, float)) and 0 <= fx <= 1 else 0.5,
                fy if isinstance(fy, (int, float)) and 0 <= fy <= 1 else 0.5,
            )
            chosen["reason"] = str(result.get("reason", ""))[:160]
            return chosen
        if isinstance(result, dict) and not result.get("acceptable"):
            print(f"[visual] vision rejected all candidates: "
                  f"{str(result.get('reason', ''))[:120]}")
            return None
    # Vision unavailable -> mechanical ranking, still gated by overlap sizes.
    return _mechanical_rank(candidates, subject)


GEN_STYLE = (
    "Professional editorial illustration for a premium Japanese financial "
    "news program. Sophisticated mature flat-vector style with subtle depth: "
    "dark navy background palette (#0B1426 #152238) with amber (#FFB300) "
    "and muted gold accents, precise geometry, clean composition, cinematic "
    "lighting, high detail. Absolutely no text, no watermark, no childish "
    "doodles, no simplistic cartoon shapes, no blurry gradient blobs. "
    "Vertical 3:4 portrait composition designed for a tall left column. "
)


def generate_theme_image(prompt: str, target: Path) -> bool:
    imagegen = US_ROOT / "tools" / "imagegen" / "imagegen.py"
    env = os.environ.copy()
    # Mac ComfyUI fallback is forbidden for local Windows runs.
    env["IMG_GENERATION_FALLBACK"] = "0"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(imagegen), prompt, "-o", str(target),
         "--width", "768", "--height", "1024"],
        cwd=str(US_ROOT), capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=420,
    )
    if r.returncode != 0 or not target.is_file() or target.stat().st_size < 10_000:
        print(f"[visual] imagegen failed: {target.name}: {(r.stderr or r.stdout)[-300:]}")
        return False
    return True


def review_generated_image(target: Path, subject: dict) -> str | None:
    """Vision self-check for a generated theme image. None = acceptable."""
    prompt = "\n".join([
        "生成したテーマ挿絵を検査してください。",
        f"本来のテーマ（抽象主体）: {json.dumps(subject, ensure_ascii=False)}",
        "",
        "不合格の条件（1つでも該当なら verdict=reject）:",
        "- 幼稚・単純すぎる（小学生の落書き級）、輪郭不明瞭、ぼやけ、ノイズ",
        "- テーマと無関係な内容、文字・透かし・ロゴの混入",
        "- 単なる抽象グラデーションや幾何色面だけで主題が伝わらない",
        "合格なら verdict=accept。",
    ])
    schema = {
        "type": "object",
        "required": ["verdict"],
        "properties": {
            "verdict": {"type": "string", "enum": ["accept", "reject"]},
            "reason": {"type": "string"},
        },
    }
    result = _vision_json(prompt, [target], schema)
    if isinstance(result, dict) and result.get("verdict") == "reject":
        return str(result.get("reason", "vision self-check rejected"))[:160]
    return None


def crop_to_display_aspect(src: Path, dst: Path, focus: tuple[float, float],
                           aspect: float = DISPLAY_ASPECT) -> bool:
    """Pre-crop an image to the left display column ratio around `focus`.

    Without this, object-fit:cover silently crops up to 60% of landscape
    photos and can amputate the subject (2026-09-24 complaint). The focus
    point (0-1 relative) comes from the vision reviewer; fallback keeps
    horizontal center and biases vertically toward the upper two thirds
    (heads/buildings rarely sit at the very bottom).
    """
    from PIL import Image
    try:
        with Image.open(src) as im:
            if im.mode != "RGB":
                im = im.convert("RGB")
            w, h = im.size
            current = w / max(h, 1)
            if abs(current - aspect) <= ASPECT_TOLERANCE:
                im.save(dst, format="PNG")
                return True
            if current > aspect:  # too wide: crop left/right around focus_x
                new_w = int(round(h * aspect))
                if new_w > w:
                    new_w = w
                fx = min(max(focus[0], 0.0), 1.0)
                max_l = w - new_w
                left = int(round((w * fx) - (new_w / 2)))
                left = max(0, min(max_l, left))
                box = (left, 0, left + new_w, h)
            else:  # too tall: crop top/bottom, bias above center
                new_h = int(round(w / aspect))
                if new_h > h:
                    new_h = h
                fy = min(max(focus[1], 0.0), 1.0)
                max_t = h - new_h
                top = int(round((h * fy) - (new_h * 0.55)))
                top = max(0, min(max_t, top))
                box = (0, top, w, top + new_h)
            im.crop(box).save(dst, format="PNG")
            return True
    except Exception as e:  # noqa: BLE001 - keep the original on failure
        print(f"[visual] crop failed for {src.name}: {e}")
        return False


def _resolve_subject_image(
    subject: dict,
    target: Path,
    context: str,
    workdir: Path,
    conn: sqlite3.Connection | None,
) -> Optional[dict]:
    """Resolve one page image. Returns metadata dict or None when missing."""
    # 1. Shared media asset hit: reuse directly, skip search/generation.
    if conn is not None:
        for keyword in subject["keywords"]:
            hit = media_asset_db.find_media_asset(conn, keyword)
            if not hit:
                continue
            shared = US_ROOT / hit["file_path"]
            if shared.is_file() and shared.stat().st_size > 10_000:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(shared, target)
                return {
                    "state": "media-cache", "source": f"media_resources:{keyword}",
                    "keyword": keyword, "route": "shared",
                    "subject_type": subject["subject_type"],
                    "portrait": bool(hit["portrait"]),
                }

    # 2. Photo route: search by keyword priority, vision-review each set.
    #    All candidates rejected -> next keyword -> finally generation
    #    (the largest-pixel auto-adopt is removed by the 2026-09-24 contract).
    if subject["route"] == "photo":
        for keyword in subject["keywords"]:
            candidates = fetch_image_candidates(keyword, workdir)
            chosen = select_candidate(candidates, subject, context)
            if not chosen:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            focus = chosen.get("focus", (0.5, 0.5))
            cropped = target.parent / f"{target.stem}.crop.png"
            # Portrait faces render inside the centered circle: the file
            # itself must be square or the aspect gate stretches/crops heads.
            want_aspect = 1.0 if chosen["portrait"] else DISPLAY_ASPECT
            if crop_to_display_aspect(
                    chosen["path"], cropped, focus, aspect=want_aspect):
                shutil.move(str(cropped), target)
                if chosen["path"].exists():
                    chosen["path"].unlink()
            else:
                if cropped.exists():
                    cropped.unlink()
                shutil.move(str(chosen["path"]), target)
            if conn is not None:
                media_asset_db.register_use(
                    conn, US_ROOT, keyword, target,
                    portrait=bool(chosen["portrait"]),
                    subject_type=subject["subject_type"],
                    source=chosen.get("bytes_url", chosen["url"]),
                )
            return {
                "state": "fetched", "source": chosen["url"],
                "bytes_url": chosen.get("bytes_url", chosen["url"]),
                "keyword": keyword,
                "route": "photo", "subject_type": subject["subject_type"],
                "portrait": bool(chosen["portrait"]),
                "review": chosen.get("reason", ""),
            }
        print(f"[visual] photo keywords exhausted for '{subject['keywords'][0]}'; "
              "falling back to generation")

    # 3. Generation route (abstract subjects) and photo-search last resort.
    keyword = subject["keywords"][0]
    concept = " ".join(subject["keywords"])[:300]
    attempts = 3
    feedback = ""
    for attempt in range(1, attempts + 1):
        gen_target = workdir / f"gen-{target.stem}-{attempt}.png"
        prompt = GEN_STYLE + "Subject: " + concept
        if feedback:
            prompt += f". Fix: {feedback}"
        if not generate_theme_image(prompt, gen_target):
            continue
        reason = review_generated_image(gen_target, subject)
        if reason is None:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(gen_target), target)
            if conn is not None:
                media_asset_db.register_use(
                    conn, US_ROOT, keyword, target,
                    portrait=False, subject_type=subject["subject_type"],
                    source="tools/imagegen qwen",
                )
            return {
                "state": "generated", "source": "tools/imagegen qwen",
                "keyword": keyword,
                "route": "generate", "subject_type": subject["subject_type"],
                "portrait": False, "gen_attempts": attempt,
            }
        feedback = reason
        print(f"[visual] generated image rejected ({attempt}/{attempts}): {reason}")
        gen_target.unlink(missing_ok=True)
    return None


def run(args: argparse.Namespace) -> int:
    issue = US_ROOT / "daily-output" / args.date
    rows = load_rows(args.date)
    brief_data = load_brief_data(args.date)
    replacements: dict[str, str] = {}
    statuses: dict[str, tuple[str, str]] = {}
    assets_dir = issue / "assets"
    manifest_path = assets_dir / "manifest.jsonl"
    meta_path = assets_dir / "image-meta.json"
    workdir = issue / "production" / "tmp-visual-candidates"
    dry = args.dry_run
    ok = True
    conn = None if dry else media_asset_db.connect(US_ROOT)
    meta: dict[str, dict] = {}
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            meta = {}

    theme_texts: dict[int, dict[int, str]] = {}
    for theme in brief_data.get("themes", []):
        number = int(theme.get("number", 0))
        pages = {int(p["page"]): p.get("text", "") for p in theme.get("pages", [])}
        theme_texts[number] = pages

    theme_rows: dict[int, list[dict]] = {}
    for row in rows:
        match = re.fullmatch(r"B(\d+)-p(\d+)", row["block"])
        if match:
            theme_rows.setdefault(int(match.group(1)), []).append(row)

    page_meta: dict[str, dict] = {}
    base_subjects: dict[int, dict] = {}
    p1_reuse_count: dict[int, int] = {}
    rows_total = sum(len(v) for v in theme_rows.values())
    rows_done = 0
    write_progress(
        args.date, phase="start", rows_total=rows_total, rows_done=0,
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    for theme_number in sorted(theme_rows):
        ordered = sorted(
            theme_rows[theme_number],
            key=lambda r: int(re.search(r"p(\d+)", r["block"]).group(1)),
        )
        for row in ordered:
            match = re.fullmatch(r"B(\d+)-p(\d+)", row["block"])
            page_number = int(match.group(2))
            paragraph = theme_texts.get(theme_number, {}).get(page_number, row["heading"])
            # theme_image_asset() already returns an issue-root-relative path.
            target = issue / theme_image_asset(theme_number, page_number)
            old_asset = row["asset"]
            new_rel = f"assets/{target.name}"

            existing = meta.get(row["block"])
            if existing and target.is_file() and target.stat().st_size > 10_000:
                info = dict(existing)
                info["state"] = "cached"
            else:
                full_text = " ".join(
                    theme_texts.get(theme_number, {}).get(p, "")
                    for p in range(1, THEME_PAGE_COUNT + 1)
                ).strip() or row["heading"]
                if theme_number not in base_subjects:
                    base_subjects[theme_number] = derive_subject(full_text, first_page=True)
                if page_number == 1:
                    subject = base_subjects[theme_number]
                else:
                    deviates = judge_deviation(
                        base_subjects[theme_number], paragraph, full_text,
                    )
                    # Same-image spam cap: p1 reuse maxes out at
                    # MAX_P1_REUSE_PER_THEME pages per theme; beyond that the
                    # paragraph gets its own derived subject and fresh asset.
                    if (not deviates
                            and p1_reuse_count.get(theme_number, 0)
                            < MAX_P1_REUSE_PER_THEME):
                        p1 = issue / theme_base_image_asset(theme_number)
                        if p1.is_file() and p1.stat().st_size > 10_000:
                            if not dry:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(p1, target)
                            p1_reuse_count[theme_number] = (
                                p1_reuse_count.get(theme_number, 0) + 1
                            )
                            info = dict(page_meta.get(
                                f"B{theme_number}-p1", existing or {},
                            ))
                            info.update({
                                "state": "reused", "asset": new_rel,
                                "block": row["block"],
                                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                            })
                            page_meta[row["block"]] = info
                            statuses[row["slide"]] = ("reused", new_rel)
                            if new_rel != old_asset:
                                replacements[old_asset] = new_rel
                            rows_done += 1
                            write_progress(
                                args.date, phase="resolve", slide=row["slide"],
                                block=row["block"], state="reused",
                                rows_done=rows_done, rows_total=rows_total,
                            )
                            print(f"[visual] {row['slide']} {row['block']}: reused -> {new_rel}")
                            continue
                    subject = derive_subject(paragraph, first_page=False)

                if dry:
                    info = {
                        "state": "planned", "source": "",
                        "keyword": subject["keywords"][0],
                        "route": subject["route"],
                        "subject_type": subject["subject_type"],
                        "portrait": bool(subject["portrait_expected"]),
                    }
                else:
                    workdir.mkdir(parents=True, exist_ok=True)
                    resolved = _resolve_subject_image(
                        subject, target, paragraph, workdir, conn,
                    )
                    if resolved is None:
                        info = {
                            "state": "missing", "source": "",
                            "keyword": subject["keywords"][0],
                            "route": subject["route"],
                            "subject_type": subject["subject_type"],
                            "portrait": False,
                        }
                    else:
                        info = resolved

            info.update({
                "block": row["block"], "asset": new_rel,
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            })
            page_meta[row["block"]] = info
            state = info["state"]
            if state == "missing":
                ok = False
            if not dry and state != "missing":
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                with manifest_path.open("a", encoding="utf-8") as fh:
                    fh.write(manifest_entry(
                        target, assets_dir, row["block"],
                        info.get("bytes_url", "") or info.get("source", ""),
                        state,
                        {
                            "keyword": info.get("keyword", ""),
                            "route": info.get("route", ""),
                            "subject_type": info.get("subject_type", ""),
                            "portrait": bool(info.get("portrait", False)),
                            "page_url": info.get("source", ""),
                            "review": info.get("review", ""),
                        },
                    ) + "\n")
            statuses[row["slide"]] = (state, new_rel if state != "missing" else old_asset)
            if new_rel != old_asset:
                replacements[old_asset] = new_rel
            rows_done += 1
            write_progress(
                args.date, phase="resolve", slide=row["slide"],
                block=row["block"], state=state,
                rows_done=rows_done, rows_total=rows_total,
            )
            print(f"[visual] {row['slide']} {row['block']}: {state} -> {new_rel}")

    # Opening stays a fixed template copy.
    opening_row = next((r for r in rows if r["block"] == "OPENING"), None)
    if opening_row:
        target = issue / OPENING_VISUAL_ASSET
        fallback = US_ROOT / OPENING_TEMPLATE_ASSET
        if target.is_file() and target.stat().st_size > 10_000:
            state, source = "cached", "today asset"
        elif fallback.is_file():
            if not dry:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(fallback, target)
            state, source = "copied", "template opening-visual"
        else:
            state, source, ok = "missing", "", False
        if state != "missing":
            statuses[opening_row["slide"]] = (state, OPENING_VISUAL_ASSET)
            if OPENING_VISUAL_ASSET != opening_row["asset"]:
                replacements[opening_row["asset"]] = OPENING_VISUAL_ASSET
            if not dry:
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                with manifest_path.open("a", encoding="utf-8") as fh:
                    fh.write(manifest_entry(
                        target, assets_dir, "OPENING", source, state,
                    ) + "\n")
        print(f"[visual] {opening_row['slide']} OPENING: {state}")
        write_progress(args.date, phase="opening", state=state)

    # Preview-v2 (2026-09-19+): the single s1 preview list page reuses each
    # theme's p1 image and never fetches new assets itself.
    if episode_contract.is_preview_v2(args.date):
        slide = episode_contract.preview_list_slide_id()
        base = issue / theme_base_image_asset(1)
        if base.is_file() and base.stat().st_size > 10_000:
            statuses.setdefault(slide, ("reused", f"assets/{base.name}"))
        else:
            statuses.pop(slide, None)
        print("[visual] s1 preview list reuses B theme p1 images")
        write_progress(args.date, phase="preview", state="reused" if base.is_file() else "missing")

    # Portrait flag drives display style: circle centered vs full-height left.
    for info in page_meta.values():
        rel = info.get("asset", "")
        if not rel or not rel.startswith("assets/b"):
            continue
        plain = f'<div class="photo-frame"><img src="{rel}"'
        circle = f'<div class="photo-frame portrait"><img src="{rel}"'
        if info.get("portrait"):
            replacements[plain] = circle
        else:
            replacements[circle] = plain

    # s1 preview carousel follows the same portrait rule as B pages.
    if episode_contract.is_preview_v2(args.date):
        portrait_rel = {
            info.get("asset", "")
            for info in page_meta.values()
            if info.get("portrait")
            and re.fullmatch(r"assets/b\d+-1\.png", info.get("asset", ""))
        }
        apply_preview_portrait_style(args.date, portrait_rel)

    if dry:
        print("[visual] dry-run complete; no files, DB rows, or references changed")
        return 0 if ok else 2

    assets_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(
        json.dumps(page_meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    if replacements:
        fix_visual_data_refs(args.date, replacements)
    update_brief(args.date, statuses, assets_dir)
    if conn is not None:
        conn.close()
    if workdir.is_dir():
        shutil.rmtree(workdir, ignore_errors=True)

    render = US_ROOT / "tools" / "visual" / "render_visual.py"
    write_progress(args.date, phase="render",
                   render_started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    rr = subprocess.run(
        [sys.executable, "-X", "utf8", str(render), "--date", args.date],
        cwd=str(US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
        timeout=int(os.getenv("VISUAL_RENDER_TIMEOUT", "600")),
    )
    print((rr.stdout or "") + (rr.stderr or ""))
    write_progress(args.date, phase="render-done", render_exit=rr.returncode)
    if rr.returncode != 0:
        ok = False

    # 2026-09-26 QA restructure: the visual gate (mechanical asset checks +
    # real-DOM audit + vision contact sheet + REACQUIRE) runs right after
    # render, while a fix still costs one asset re-fetch instead of a full
    # Remotion re-render. exit 2 = defect -> prepare fails so the caller
    # re-runs this script (rejected assets are already marked missing).
    # exit 3 = environment error (advisory only, never blocks the daily).
    if ok:
        gate = US_ROOT / "tools" / "pipeline" / "visual_qa_gate.py"
        gr = subprocess.run(
            [sys.executable, "-X", "utf8", str(gate), args.date],
            cwd=str(US_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=int(os.getenv("VISUAL_GATE_TIMEOUT", "1800")),
        )
        print((gr.stdout or "") + (gr.stderr or ""))
        if gr.returncode == 2:
            ok = False
            print("[visual] visual gate FAILED: re-run prepare_visual_assets.py "
                  "(it re-acquires the rejected/missing assets, re-renders, "
                  "and re-runs the gate)")
        elif gr.returncode not in (0, 2):
            print(f"[visual] visual gate environment issue (exit "
                  f"{gr.returncode}); continuing -- frame sampling in final QA "
                  "still covers blank slides after render")

    print("[visual] PASS" if ok else "[visual] FAILED: missing assets or render error")
    write_progress(args.date, phase="complete" if ok else "failed")
    return 0 if ok else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    issue = US_ROOT / "daily-output" / args.date
    try:
        with single_run_lock(issue):
            return run(args)
    except SystemExit as e:
        if str(e).startswith("[visual] another prepare_visual_assets"):
            print(str(e))
            return 3
        raise


if __name__ == "__main__":
    sys.exit(main())

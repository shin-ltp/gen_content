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
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))

import episode_contract  # noqa: E402
import media_asset_db  # noqa: E402
import text_llm  # noqa: E402
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
    target: Path, block: str, source: str, state: str, extra: dict | None = None,
) -> str:
    if not target.is_file():
        raise FileNotFoundError(f"manifest target does not exist: {target}")
    payload = {
        "block": block,
        "asset": rel_to(US_ROOT, target),
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

LLM_DISABLED = False


def _llm_json(prompt: str, schema: dict) -> Any | None:
    if not text_llm.is_configured():
        return None
    global LLM_DISABLED
    if LLM_DISABLED:
        return None
    try:
        return text_llm.generate_json(
            prompt, "flash", schema_hint=json.dumps(schema, ensure_ascii=False),
            max_retries=1,
        )
    except Exception as e:  # noqa: BLE001 - degrade to heuristics
        LLM_DISABLED = True
        print(f"[visual] LLM disabled for this run, using heuristics: {str(e)[:200]}")
        return None


def derive_subject(text: str, *, first_page: bool) -> dict:
    """Derive image route/keywords for one article (p1) or paragraph (p2+)."""
    basis = "テーマ記事全体" if first_page else "この段落"
    rules = "\n".join([
        "① 新製品発表: 製品写真 → 発表会・イベント会場写真のキーワード。講話・声明などのニュース事件: 記事配図の元写真に相当するキーワード",
        "② 行動主体（企業・経営者・FRB・大統領/政府高官・政府機関・投資銀行・アナリスト・新製品）: 企業・機関等は社名・機関名が鮮明に写る建物写真。人物はアナリスト見解の引用のみ portrait、それ以外の人物は現場・講演・会見の高解像度写真",
        "③ 抽象主体（市場走势・心理・価格変動・マクロデータ等の具体実体なし）: route=generate（生成テーマ画像）",
    ])
    prompt = "\n".join([
        f"画像取得の主体判定を行ってください。判定対象は{basis}です。",
        "",
        "優先順位（厳守）:",
        rules,
        "",
        "対象テキスト:",
        text[:4000],
        "",
        "keywords は検索/生成に使う短い実用的キーワード（英語可）優先度順で最大3つ。",
    ])
    schema = {
        "type": "object",
        "required": ["route", "subject_type", "keywords", "portrait_expected"],
        "properties": {
            "route": {"type": "string", "enum": ["photo", "generate"]},
            "subject_type": {"type": "string", "enum": sorted(SUBJECT_TYPES)},
            "keywords": {"type": "array", "items": {"type": "string"},
                         "minItems": 1, "maxItems": 3},
            "portrait_expected": {"type": "boolean"},
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
            return {
                "route": route,
                "subject_type": subject_type,
                "keywords": keywords[:3],
                "portrait_expected": bool(result.get("portrait_expected", False)),
            }
        print(f"[visual] LLM subject result invalid, using heuristics: {result}")
    return _derive_subject_heuristic(text)


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

def fetch_image_candidates(query: str, workdir: Path, limit: int = 5) -> list[dict]:
    """Search SearXNG images and return up to `limit` validated candidates."""
    search = US_ROOT / "tools" / "searxng" / "search.ps1"
    r = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(search),
         query, "-Categories", "images", "-MaxResults", "8", "-Raw"],
        cwd=str(US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    if r.returncode != 0:
        print(f"[visual] search failed: {query}: {(r.stderr or r.stdout)[-200:]}")
        return []
    try:
        results = json.loads(r.stdout).get("results", [])
    except json.JSONDecodeError:
        return []

    workdir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    for index, result in enumerate(results):
        if len(candidates) >= limit:
            break
        url = result.get("img_src") or result.get("thumbnail_src") or result.get("url")
        if not url:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                ctype = resp.headers.get("Content-Type", "").split(";")[0]
                if ctype and not ctype.startswith("image/"):
                    continue
                payload = resp.read(20 * 1024 * 1024)
            if len(payload) < 10_000:
                continue
            from PIL import Image
            import io as _io
            with Image.open(_io.BytesIO(payload)) as im:
                width, height = im.size
                out = workdir / f"cand-{len(candidates)}-{index}.png"
                im.convert("RGB").save(out, format="PNG")
            candidates.append({
                "path": out, "url": str(result.get("url") or url),
                "title": str(result.get("title", ""))[:160],
                "width": width, "height": height,
            })
        except Exception as e:  # noqa: BLE001 - try the next result
            print(f"[visual] download failed: {url}: {e}")
    return candidates


def select_candidate(candidates: list[dict], subject: dict, context: str) -> dict | None:
    """LLM re-ranks candidates for quality and topical fit (fallback: largest)."""
    if not candidates:
        return None
    lines = []
    for i, c in enumerate(candidates):
        domain = re.sub(r"^https?://([^/]+).*", r"\1", c["url"])
        lines.append(f"{i}: {c['width']}x{c['height']} | {domain} | {c['title']}")
    prompt = "\n".join([
        "画像検索候補から1枚を選んでください。",
        "",
        f"取得主体: {json.dumps(subject, ensure_ascii=False)}",
        f"文脈: {context[:800]}",
        "候補（index | 解像度 | ドメイン | タイトル）:",
        *lines,
        "",
        "選定基準: 高品質（高解像度・サムネイルでない・ぼやけない）かつ主題に合致すること。",
        "人物の顔・胸元アップの画像は portrait=true、それ以外の写真は portrait=false。",
    ])
    schema = {
        "type": "object",
        "required": ["index", "portrait"],
        "properties": {
            "index": {"type": "integer"},
            "portrait": {"type": "boolean"},
            "reason": {"type": "string"},
        },
    }
    result = _llm_json(prompt, schema)
    if isinstance(result, dict):
        index = result.get("index")
        if isinstance(index, int) and 0 <= index < len(candidates):
            chosen = dict(candidates[index])
            chosen["portrait"] = bool(result.get("portrait", subject["portrait_expected"]))
            return chosen
    chosen = dict(max(candidates, key=lambda c: c["width"] * c["height"]))
    chosen["portrait"] = bool(subject["portrait_expected"])
    return chosen


def generate_theme_image(prompt: str, target: Path) -> bool:
    imagegen = US_ROOT / "tools" / "imagegen" / "imagegen.py"
    env = os.environ.copy()
    # Mac ComfyUI fallback is forbidden for local Windows runs.
    env["IMG_GENERATION_FALLBACK"] = "0"
    r = subprocess.run(
        [sys.executable, "-X", "utf8", str(imagegen), prompt, "-o", str(target),
         "--width", "1024", "--height", "1024"],
        cwd=str(US_ROOT), capture_output=True, text=True, env=env,
        encoding="utf-8", errors="replace", timeout=420,
    )
    if r.returncode != 0 or not target.is_file() or target.stat().st_size < 10_000:
        print(f"[visual] imagegen failed: {target.name}: {(r.stderr or r.stdout)[-300:]}")
        return False
    return True


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

    # 2. Photo route: search by keyword priority, LLM re-ranks candidates.
    if subject["route"] == "photo":
        for keyword in subject["keywords"]:
            candidates = fetch_image_candidates(keyword, workdir)
            chosen = select_candidate(candidates, subject, context)
            if not chosen:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(chosen["path"]), target)
            if conn is not None:
                media_asset_db.register_use(
                    conn, US_ROOT, keyword, target,
                    portrait=bool(chosen["portrait"]),
                    subject_type=subject["subject_type"],
                    source=chosen["url"],
                )
            return {
                "state": "fetched", "source": chosen["url"], "keyword": keyword,
                "route": "photo", "subject_type": subject["subject_type"],
                "portrait": bool(chosen["portrait"]),
            }

    # 3. Generation route (abstract subjects) and photo-search last resort.
    keyword = subject["keywords"][0]
    gen_target = workdir / f"gen-{target.stem}.png"
    prompt = (
        "Financial news theme illustration, clean modern flat design, "
        "no text, no watermark, based on: " + " ".join(subject["keywords"])[:300]
    )
    if generate_theme_image(prompt, gen_target):
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(gen_target), target)
        if conn is not None:
            media_asset_db.register_use(
                conn, US_ROOT, keyword, target,
                portrait=False, subject_type=subject["subject_type"],
                source="tools/imagegen qwen",
            )
        return {
            "state": "generated", "source": "tools/imagegen qwen", "keyword": keyword,
            "route": "generate", "subject_type": subject["subject_type"],
            "portrait": False,
        }
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
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

    for theme_number in sorted(theme_rows):
        ordered = sorted(
            theme_rows[theme_number],
            key=lambda r: int(re.search(r"p(\d+)", r["block"]).group(1)),
        )
        for row in ordered:
            match = re.fullmatch(r"B(\d+)-p(\d+)", row["block"])
            page_number = int(match.group(2))
            paragraph = theme_texts.get(theme_number, {}).get(page_number, row["heading"])
            target = assets_dir / theme_image_asset(theme_number, page_number)
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
                    if not deviates:
                        p1 = assets_dir / theme_base_image_asset(theme_number)
                        if p1.is_file() and p1.stat().st_size > 10_000:
                            if not dry:
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copy2(p1, target)
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
                        target, row["block"], info.get("source", ""), state,
                        {
                            "keyword": info.get("keyword", ""),
                            "route": info.get("route", ""),
                            "subject_type": info.get("subject_type", ""),
                            "portrait": bool(info.get("portrait", False)),
                        },
                    ) + "\n")
            statuses[row["slide"]] = (state, new_rel if state != "missing" else old_asset)
            if new_rel != old_asset:
                replacements[old_asset] = new_rel
            print(f"[visual] {row['slide']} {row['block']}: {state} -> {new_rel}")

    # Opening stays a fixed template copy.
    opening_row = next((r for r in rows if r["block"] == "OPENING"), None)
    if opening_row:
        target = assets_dir / OPENING_VISUAL_ASSET
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
                    fh.write(manifest_entry(target, "OPENING", source, state) + "\n")
        print(f"[visual] {opening_row['slide']} OPENING: {state}")

    # Preview-v2 (2026-09-19+): the single s1 preview list page reuses each
    # theme's p1 image and never fetches new assets itself.
    if episode_contract.is_preview_v2(args.date):
        slide = episode_contract.preview_list_slide_id()
        base = assets_dir / theme_base_image_asset(1)
        if base.is_file() and base.stat().st_size > 10_000:
            statuses.setdefault(slide, ("reused", f"assets/{base.name}"))
        else:
            statuses.pop(slide, None)
        print("[visual] s1 preview list reuses B theme p1 images")

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
    rr = subprocess.run(
        [sys.executable, "-X", "utf8", str(render), "--date", args.date],
        cwd=str(US_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120,
    )
    print((rr.stdout or "") + (rr.stderr or ""))
    if rr.returncode != 0:
        ok = False
    print("[visual] PASS" if ok else "[visual] FAILED: missing assets or render error")
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())

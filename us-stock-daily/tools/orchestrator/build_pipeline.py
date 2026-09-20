#!/usr/bin/env python3
"""Code-owned episode pipeline.

LLMs own language: outline analysis, selected themes, and narration.
Python owns structure: corner order, fixed assets, block ordering, TTS
segment generation, artifact validation, and render command construction.

Usage:
  python build_pipeline.py scaffold --date 2026-09-08
  python build_pipeline.py validate --date 2026-09-08
  python build_pipeline.py build-map --date 2026-09-08
  python build_pipeline.py check-artifacts --date 2026-09-08
  python build_pipeline.py commands --date 2026-09-08 --render
  python build_pipeline.py run --date 2026-09-08 [--render]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from html import unescape
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))

from episode_contract import (  # noqa: E402
    CONTRACT_EFFECTIVE_DATE,
    CONTRACT_NEW_EFFECTIVE_DATE,
    LEGACY_VISUAL_SLIDE_COUNT,
    OPENING_SLIDE_ID,
    PREVIEW_SUMMARY_MAX_CHARS,
    PREVIEW_SUMMARY_MIN_CHARS,
    PREVIEW_TITLE_MAX_CHARS,
    PREVIEW_V2_DATE,
    PREVIEW_MAX_CHARS,
    PREVIEW_MIN_CHARS,
    opening_end_phrase,
    opening_theme_prefix,
    strip_opening_end_phrase,
    strip_opening_theme_prefix,
)


ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
PY = sys.executable
CORNER_ORDER = ("opening", "market", "themes", "news", "events", "ending")
OPENING_NARRATION_ID = "S00-intro"
OBSOLETE_OUTRO_ID = "END-outro"
BLOCK_RANGE = {
    "opening": (0, 99),
    "market": (100, 199),
    "themes": (200, 299),
    "news": (400, 499),
    "events": (500, 599),
    "ending": (800, 899),
}
CONFIG_PATH = Path("production/episode.config.json")
SCRIPT_PATH = Path("production/script.json")
MAP_PATH = Path("production/segment-map.json")
DURATIONS_PATH = Path("production/audio/durations.json")
INPUT_PATH = ROOT / "remotion" / "public" / "remotion_input.json"

MARKET_BLOCK_ID = "A-p1"


def market_block_id(cfg: dict) -> str:
    """Return the opening market-summary block for the episode contract.

    Episodes before 2026-09-17 pair previews with carousel cues and put the
    market summary at A-p1. From 2026-09-17, with N themes the market
    summary is A-p(N+1). The 2026-09-19 preview-v2 contract keeps that
    block layout: A-p1..A-pN are the spoken title+summary previews sharing
    s1, and A-p(N+1) is the market.
    """
    if str(cfg.get("episode", "")) >= CONTRACT_NEW_EFFECTIVE_DATE:
        count = sum(
            1 for block in cfg.get("blocks", [])
            if re.fullmatch(r"A-p[1-9][0-9]*", str(block.get("id", "")))
        )
        # A-p1..A-pN are previews; the market summary is the last
        # consecutive block, A-p(N+1) = A-p{count}.
        return f"A-p{count}"
    return MARKET_BLOCK_ID

class PipelineError(RuntimeError):
    pass


# Same curated set as tools/check_japanese.py: excludes kanji that are
# legitimate in Japanese, so ordinary narration like 市場/指数 is never rejected.
SIMPLIFIED_CHARS = (
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
    "龄马环职肃"
)

def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise PipelineError(f"missing file: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise PipelineError(f"invalid JSON: {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(data, encoding="utf-8")


def issue_dir(date: str) -> Path:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise PipelineError("--date must be YYYY-MM-DD")
    return ROOT / "daily-output" / date


def config_path(date: str) -> Path:
    return issue_dir(date) / CONFIG_PATH


def script_path(date: str) -> Path:
    return issue_dir(date) / SCRIPT_PATH


def map_path(date: str) -> Path:
    return issue_dir(date) / MAP_PATH


def durations_path(date: str) -> Path:
    return issue_dir(date) / DURATIONS_PATH


def require_unique(ids: list[str], label: str) -> None:
    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise PipelineError(f"duplicate {label}: {', '.join(duplicates)}")


def validate_script(
    cfg: dict,
    script: dict,
    partial_ids: set[str] | None = None,
    validate_visual_sync: bool = True,
) -> dict[str, str]:
    if script.get("episode") != cfg.get("episode"):
        raise PipelineError("script episode does not match config")
    items = script.get("blocks")
    if not isinstance(items, list):
        raise PipelineError("script.blocks must be an array")
    expected = {block["id"] for block in cfg["blocks"]}
    actual = []
    result: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            raise PipelineError("script.blocks entries must be objects")
        block_id = item.get("id")
        if not isinstance(block_id, str) or not block_id:
            raise PipelineError("script block id is missing")
        actual.append(block_id)
        if block_id in result:
            raise PipelineError(f"duplicate script block: {block_id}")
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            raise PipelineError(f"script block text is empty: {block_id}")
        result[block_id] = text
    # Partial builds validate only the requested subset so the day can start
    # TTS while other blocks are still missing from script.json.
    required = expected if partial_ids is None else expected & partial_ids
    missing = sorted(required - set(result))
    extra = sorted(set(result) - expected)
    if missing:
        raise PipelineError(f"script is missing blocks: {', '.join(missing)}")
    if extra:
        raise PipelineError(f"script has unknown blocks: {', '.join(extra)}")
    simplified = [char for char in "".join(result.values()) if char in SIMPLIFIED_CHARS]
    if simplified:
        sample = "".join(sorted(set(simplified)))
        offenders = [block_id for block_id, text in result.items()
                     if any(char in text for char in SIMPLIFIED_CHARS)]
        raise PipelineError(
            f"Simplified Chinese found in Japanese narration: {sample}; "
            "blocks: " + ", ".join(offenders)
        )
    result["episode"] = cfg.get("episode", "")
    if partial_ids is None:
        if str(cfg.get("episode", "")) >= CONTRACT_EFFECTIVE_DATE:
            validate_opening_contract(cfg, result)
            if str(cfg.get("episode", "")) < CONTRACT_NEW_EFFECTIVE_DATE:
                _validate_haiku_visual_sync(result)
            if validate_visual_sync:
                _validate_slide_narration_sync(result, cfg)
    return result


def _strip_pause_markers(text: str) -> str:
    """Remove TTS-only directives and whitespace for visual/text comparison."""
    normalized = re.sub(r"\[pause(?:\s+[a-z]+)?\]", " ", text)
    return re.sub(r"\s+", "", normalized)


def _narration_char_count(text: str) -> int:
    stripped = re.sub(r"\[pause(?:\s+[a-z]+)?\]", "", text)
    return len(re.sub(r"\s+", "", stripped))


_FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def _contains_theme_summary_phrase(text: str, expected: int) -> bool:
    text = text.translate(_FULLWIDTH_DIGITS)
    return (
        opening_end_phrase(expected).rstrip("。") in text
    )

def _theme_prefix(expected: int) -> str:
    return opening_theme_prefix(expected)


def _preview_theme_count(cfg: dict) -> int | None:
    """Infer the new-contract theme count from consecutive A-p numbering.

    A-p1..A-pN are numbered consecutively, and the market summary follows at
    N+1, so the theme count is the highest index minus 1. Returning None
    keeps a malformed config from being silently accepted.
    """
    ids = [
        int(re.search(r"A-p(\d+)", str(block.get("id", ""))).group(1))
        for block in cfg.get("blocks", [])
        if re.fullmatch(r"A-p[1-9][0-9]*", str(block.get("id", "")))
    ]
    if not ids or sorted(ids) != list(range(1, max(ids) + 1)):
        return None
    return max(ids) - 1


def _slide_number(slide: object) -> int | None:
    match = re.fullmatch(r"s([0-9]+)", str(slide or ""))
    return int(match.group(1)) if match else None


def _validate_visual_slides(cfg: dict) -> None:
    """Keep slide ownership unique and complete for the active contract.

    Legacy 57-page episodes use the archived s56 layout. The v3 contract owns
    only the slides it references, while render_visual validates that every
    wrapper supplied by visual-data has content.
    """
    block_ids = [
        str(block.get("id", "")) for block in cfg.get("blocks", [])
    ]
    used_slides = [
        str(block.get("slide", "")) for block in cfg.get("blocks", [])
    ] + [str(slot.get("slide", "")) for slot in cfg.get("fixed_slots", [])]
    slide_ids = [slide for slide in used_slides if slide]
    distinct_slides = set(slide_ids)
    numbers = [_slide_number(slide) for slide in slide_ids]
    if any(number is None for number in numbers):
        raise PipelineError("every content and fixed segment must own a slide id")
    if str(cfg.get("episode", "")) < CONTRACT_NEW_EFFECTIVE_DATE:
        expected = {f"s{number}" for number in range(LEGACY_VISUAL_SLIDE_COUNT)}
        missing = sorted(expected - distinct_slides)
        extra = sorted(set(slide_ids) - expected)
        if missing:
            raise PipelineError(
                "legacy visual contract expects 57 slides; missing: "
                + ", ".join(missing)
            )
        if extra:
            raise PipelineError(
                "legacy visual contract only accepts s0..s56; extra: "
                + ", ".join(extra)
            )
        return
    # Multiple C-p* highlight states share one aggregate News page. A page
    # may serve many narration states; each block still owns exactly one page.
    require_unique(
        [str(block.get("id", "")) for block in cfg.get("blocks", [])],
        "block id",
    )
    fixed_slots = {
        str(slot.get("id", "")): str(slot.get("slide", ""))
        for slot in cfg.get("fixed_slots", [])
    }
    if fixed_slots.get("OPENING") != OPENING_SLIDE_ID:
        raise PipelineError(
            "new visual contract requires fixed slot OPENING to own s0 "
            "(the reusable title card); got "
            + (fixed_slots.get("OPENING") or "<missing>")
        )
    require_unique(block_ids, "block id")
    highest = max(number for number in numbers if number is not None)
    expected = {f"s{number}" for number in range(1, highest + 1)}
    missing = sorted(expected - distinct_slides)
    if missing:
        raise PipelineError(
            "new visual contract owns consecutive slides s1..s"
            f"{highest}; missing: " + ", ".join(missing)
        )
    preview_slides = {
        int(re.search(r"A-p(\d+)", str(block.get("id", ""))).group(1)): (
            _slide_number(block.get("slide")),
            str(block.get("cue", "")),
        )
        for block in cfg.get("blocks", [])
        if re.fullmatch(r"A-p[1-9][0-9]*", str(block.get("id", "")))
    }
    expected_count = _preview_theme_count(cfg)
    if expected_count is not None:
        if str(cfg.get("episode", "")) >= PREVIEW_V2_DATE:
            preview_slides = {
                number: value for number, value in preview_slides.items()
                if number <= expected_count
            }
        if str(cfg.get("episode", "")) >= PREVIEW_V2_DATE:
            bad = [
                f"A-p{number}->s{slide}(cue={cue or 'none'})"
                for number, (slide, cue) in preview_slides.items()
                if slide != 1 or cue != f"carousel idx={number - 1}"
            ]
            if bad:
                raise PipelineError(
                    "preview-v2 opening blocks must share s1 with ordered "
                    "carousel cues idx=0..N-1; got " + ", ".join(bad)
                )
        else:
            bad = [
                f"A-p{number}->s{slide}"
                for number, (slide, _cue) in preview_slides.items()
                if slide != number
            ]
            if bad:
                raise PipelineError(
                    "new opening preview slides must own s1..sN in order; got "
                    + ", ".join(bad)
                )


def validate_opening_contract(cfg: dict, narration: dict[str, str]) -> None:
    """Opening narration contract added after the 2026-09-10 review.

    Preview blocks are the A-p blocks paired with carousel cues in
    episode.config.json. A-p1 is the optional prior-market summary and other
    A-p blocks are not part of the theme list.

    From 2026-09-17 the A-p1..A-pN previews own slides s1..sN and the
    market summary owns s(N+1). From 2026-09-19 all previews share the one
    aggregate s1 list and use ordered carousel cues.
    """
    new_contract = str(cfg.get("episode", "")) >= CONTRACT_NEW_EFFECTIVE_DATE
    if new_contract:
        expected_count = _preview_theme_count(cfg)
        if expected_count is None or expected_count < 1:
            raise PipelineError(
                "new opening contract requires consecutive A-p1..A-p(N+1) "
                "blocks; cannot infer the preview count"
            )
        preview_blocks = sorted(
            (block for block in cfg.get("blocks", [])
             if re.fullmatch(r"A-p[1-9][0-9]*", str(block.get("id", "")))
             and int(re.search(r"A-p(\d+)", str(block.get("id", ""))).group(1))
             <= expected_count),
            key=lambda block: block["order"],
        )
    else:
        preview_blocks = sorted(
            (block for block in cfg.get("blocks", [])
             if re.fullmatch(r"A-p([2-9]|[1-9][0-9])", str(block.get("id", "")))
             and str(block.get("cue", "")).startswith("carousel")),
            key=lambda block: block["order"],
        )
    preview_ids = [block["id"] for block in preview_blocks if block["id"] in narration]
    if preview_ids:
        theme_count = len(preview_ids)
        joined = "".join(narration[block_id] for block_id in preview_ids)
        first_text = narration[preview_ids[0]]
        if not _strip_pause_markers(first_text).startswith(
            _theme_prefix(theme_count)
        ):
            raise PipelineError(
                f"A.2 opening fixed phrase is missing or N differs: "
                f"{preview_ids[0]} must start with "
                + opening_theme_prefix(theme_count)
            )
        last_text = narration[preview_ids[-1]]
        if not _contains_theme_summary_phrase(last_text, theme_count):
            raise PipelineError(
                f"A.2 closing fixed phrase is missing or N differs: "
                f"{preview_ids[-1]} must end with "
                + opening_end_phrase(theme_count)
            )
        if _strip_pause_markers(joined).count("今日はこの") != 1:
            raise PipelineError("A.2 closing fixed phrase must occur exactly once")
        preview_v2 = str(cfg.get("episode", "")) >= PREVIEW_V2_DATE
        for block_id in preview_ids:
            text = narration[block_id]
            if block_id == preview_ids[0]:
                text = strip_opening_theme_prefix(text)
            if block_id == preview_ids[-1]:
                text = strip_opening_end_phrase(text)
            if preview_v2:
                title, marker, summary = text.partition("[pause short]")
                if not marker:
                    raise PipelineError(
                        f"A.2 preview must contain one [pause short] between "
                        f"title and summary: {block_id}"
                    )
                title_size = _narration_char_count(title)
                summary_size = _narration_char_count(summary)
                if title_size < 1 or title_size > PREVIEW_TITLE_MAX_CHARS:
                    raise PipelineError(
                        f"A.2 preview title length out of range: {block_id} "
                        f"is {title_size} chars (allowed 1-{PREVIEW_TITLE_MAX_CHARS})"
                    )
                if not (
                    PREVIEW_SUMMARY_MIN_CHARS <= summary_size
                    <= PREVIEW_SUMMARY_MAX_CHARS
                ):
                    raise PipelineError(
                        f"A.2 preview summary length out of range: {block_id} "
                        f"is {summary_size} chars (allowed "
                        f"{PREVIEW_SUMMARY_MIN_CHARS}-{PREVIEW_SUMMARY_MAX_CHARS})"
                    )
                continue
            size = _narration_char_count(text)
            if not PREVIEW_MIN_CHARS <= size <= PREVIEW_MAX_CHARS:
                raise PipelineError(
                    f"A.2 preview length out of range: {block_id} is {size} chars "
                    f"(allowed {PREVIEW_MIN_CHARS}-{PREVIEW_MAX_CHARS})"
                )

    market = narration.get(market_block_id(cfg))
    if market:
        # One index can be an example of a decisive factor; two or more in
        # parallel is the ticker-style reading banned by content-framework A.3.
        index_matches = re.findall(
            r"(S&P500|S&P 500|ナスダック|NASDAQ|ダウ|ダウ工業株30種)", market
        )
        if len(index_matches) >= 2:
            raise PipelineError(
                f"A.3 market summary lists {len(index_matches)} major indexes; "
                "keep at most one and explain the decisive factor instead"
            )



_HTML_TAG_RE = re.compile(r"<[^>]+>")

# Catch whole-page narration/visual mismatches without rejecting condensed
# on-screen titles. B pages are guarded by theme routing; other content pages
# fail only when no content token overlaps at all.
_NO_SLIDE_SEGMENT_IDS = {"OPENING", "END-disclaimer"}
def _opening_no_sync_segment_ids(cfg: dict | None) -> set[str]:
    """Opening pages whose fixed layout defeats text-overlap heuristics."""
    ids = {"END-disclaimer"}
    if not cfg:
        return ids
    if str(cfg.get("episode", "")) >= PREVIEW_V2_DATE:
        count = _preview_theme_count(cfg)
        if count is not None:
            ids.update(f"A-p{i}" for i in range(1, count + 1))
            ids.add(f"A-p{count + 1}")
    elif str(cfg.get("episode", "")) >= CONTRACT_NEW_EFFECTIVE_DATE:
        count = _preview_theme_count(cfg)
        if count is not None:
            ids.add(f"A-p{count + 1}")
    else:
        ids.add("A-p6")
    return ids


def _page_texts(visual_html: str) -> dict[str, tuple[str, str]]:
    """Extract semantic text from each `<div class="swrap" id="sN">` page.

    Returns `(content, semantic)` per page. `content` is the right-side body
    used by B analysis pages; `semantic` excludes fixed chrome and labels and
    is better for pages whose whole slide is one compact content block.
    """
    ranges = list(re.finditer(
        r'<div class="swrap"[^>]*\bid="([^"]+)"[^>]*>', visual_html
    ))
    if not ranges:
        return {}
    pages: dict[str, tuple[str, str]] = {}
    for index, match in enumerate(ranges):
        start = match.end()
        end = ranges[index + 1].start() if index + 1 < len(ranges) else len(visual_html)
        raw = visual_html[start:end]
        # Stop at the next wrapper even if a future renderer nests wrappers.
        stop = raw.find('<div class="swrap"')
        if stop >= 0:
            raw = raw[:stop]

        body = raw
        body_match = re.search(r'<div class="body(?:\s[^"]*)?">', body)
        if body_match:
            body = body[body_match.start():]
        body_text = unescape(_HTML_TAG_RE.sub(" ", body))
        body_text = re.sub(r"\s+", " ", body_text).strip()

        semantic = raw
        for pattern in (
            r'<div class="show-logo">.*?(?=<div class="(?:sec-title|theme-chip|opening|oc|haiku-c|body|content|carousel|visual)|</div>)',
            r'<div class="slabel">.*?</div>',
            r'<div class="chrome">.*?(?=<div class="(?:body|content|carousel|visual))',
        ):
            semantic = re.sub(pattern, " ", semantic, flags=re.DOTALL)
        semantic_text = unescape(_HTML_TAG_RE.sub(" ", semantic))
        semantic_text = re.sub(r"\b(?:Smart Assets|S\d+)[^\w\u3040-\u30ff\u4e00-\u9fff]*", " ", semantic_text)
        semantic_text = re.sub(r"\s+", " ", semantic_text).strip()
        pages[match.group(1)] = (body_text, semantic_text)
    return pages


def _sync_tokens(text: str) -> set[str]:
    text = _strip_pause_markers(text)
    text = re.sub(
        r"[\s.,，。、！？：；・（）\[\]{}「」『』【】\-—ー/%$¥%+'\u00d7\u00f7]",
        " ",
        text,
    )
    # Latin names and Japanese terms need different tokenization: keep short
    # Latin words as anchors, but require slightly larger kana/kanji runs.
    tokens = set()
    for token in re.findall(r"[A-Za-z][A-Za-z0-9&.-]{1,}|[\u3040-\u30ff]|[\u4e00-\u9fff]{2,}", text):
        if len(token) >= 2:
            tokens.add(token.lower())
    return tokens


_SYNC_STOP_TOKENS = {
    "b", "smartassets", "market", "markets", "stock", "stocks",
    "テーマ", "市場", "株", "米国株", "投資", "結論", "行動指針",
    "本日", "今日", "解説", "データ", "現在", "今年",
}


def _theme_corner_slides(cfg: dict | None) -> dict[str, set[str]]:
    if not cfg:
        return {}
    slides: dict[str, set[str]] = {}
    for block in cfg.get("blocks", []):
        corner = str(block.get("corner", ""))
        slide = block.get("slide")
        if re.fullmatch(r"B\d+", corner) and slide:
            slides.setdefault(corner, set()).add(slide)
    return slides


def _validate_slide_narration_sync(
    narration: dict[str, str], cfg: dict | None = None
) -> None:
    """Reject pages whose visible content is unrelated to the narration."""
    episode = narration.get("episode", "")
    legacy_haiku = episode < CONTRACT_NEW_EFFECTIVE_DATE
    visual_path = issue_dir(episode) / "visual.html"
    map_path = issue_dir(episode) / "production" / "segment-map.json"
    if not visual_path.is_file() or not map_path.is_file():
        return
    pages = _page_texts(visual_path.read_text(encoding="utf-8-sig"))
    segments = read_json(map_path).get("segments", [])
    mismatches: list[str] = []
    # Theme pages belong to their own B blocks. A preview and fixed narration
    # may show a B slide, but that does not make the page semantically theirs.
    corner_slides = _theme_corner_slides(cfg)
    for segment in segments:
        if segment.get("type") != "tts":
            continue
        segment_id = segment.get("id", "")
        narration_text = narration.get(segment_id)
        if not narration_text:
            continue
        slide_id = segment.get("slide")
        if not slide_id:
            if segment_id in _NO_SLIDE_SEGMENT_IDS:
                continue
            mismatches.append(f"{segment_id}: missing visual page reference")
            continue
        if slide_id not in pages:
            mismatches.append(f"{segment_id}: missing visual page {slide_id}")
            continue
        if segment_id in _NO_SLIDE_SEGMENT_IDS or segment_id in _opening_no_sync_segment_ids(cfg):
            continue
        if legacy_haiku and segment_id == "S01-haiku":
            continue
        corner_match = re.fullmatch(r"(B\d+)-p\d+", segment_id)
        if corner_match and corner_slides:
            corner = corner_match.group(1)
            if slide_id not in corner_slides.get(corner, set()):
                mismatches.append(
                    f"{segment_id}: page {slide_id} is not assigned to theme {corner}"
                )
                continue
        is_theme = segment_id.startswith("B")
        if not is_theme and any(
            str(item.get("id", "")).startswith("B") and item.get("slide") == slide_id
            for item in segments
        ):
            continue
        body_text, semantic_text = pages[slide_id]
        # A current B page is often a condensed hero/card, so compare against
        # its actual analysis body. Other compact pages use the full semantic
        # content with a looser fallback threshold.
        page_text = body_text if is_theme else semantic_text
        if is_theme:
            # Exact-word overlap is too brittle for condensed analysis cards.
            # Wrong-theme routing above is the reliable whole-page check; QA
            # still reviews unrelated pages inside the assigned theme.
            continue
        tokens = {
            token for token in _sync_tokens(narration_text)
            if token not in _SYNC_STOP_TOKENS
        }
        overlaps = {token for token in tokens if token in page_text}
        if len(tokens) >= 3 and not overlaps:
            mismatches.append(
                f"{segment_id} -> {slide_id}: narration/visual overlap "
                f"0/{len(tokens)} content tokens"
            )
    if mismatches:
        details = "; ".join(mismatches)
        raise PipelineError(
            "visual/audio page mismatch: " + details
        )


def _validate_haiku_visual_sync(narration: dict[str, str]) -> None:
    """The spoken haiku and the rendered haiku must cover the same text."""
    haiku = narration.get("S01-haiku")
    if not haiku:
        return
    issue = issue_dir(narration["episode"])
    visual_path = issue / "visual.html"
    tts_path = issue / "production" / "tts" / "001_S01-haiku.txt"
    if not visual_path.is_file():
        return
    if tts_path.is_file():
        spoken_text = _strip_pause_markers(tts_path.read_text(encoding="utf-8-sig"))
    else:
        spoken_text = _strip_pause_markers(haiku)
    html = visual_path.read_text(encoding="utf-8-sig")
    match = re.search(r'<div class="haiku">(.*?)</div>', html, re.DOTALL)
    if not match:
        raise PipelineError("visual.html s1 has no <div class=\"haiku\"> text")
    screen_text = re.sub(r"\s+", "", re.sub(r"<br\s*/?>", "", match.group(1)))
    if spoken_text != screen_text:
        raise PipelineError(
            "haiku visual/audio mismatch: visual="
            f"{screen_text!r}; spoken={spoken_text!r}"
        )


def fixed_segment(slot: dict, kind: str) -> dict:
    segment = {
        "order": slot["order"],
        "id": slot["id"],
        "slide": slot["slide"],
    }
    if slot.get("visual") == "end-card":
        if kind != "ending":
            raise PipelineError("END-card fixed slot must belong to the ending corner")
        segment.update({"type": "external", "title": "Ending card visual"})
        return segment
    if kind == "opening":
        segment.update(
            {
                "type": "external",
                "title": "Opening fixed asset",
                "asset_hint": slot["source"],
            }
        )
        return segment
    if slot["source"] != "assets/audio/fixed/ending.wav":
        raise PipelineError(f"ending fixed source is invalid: {slot['source']}")
    segment.update(
        {
            "type": "external",
            "title": "Ending fixed visual and audio timeline",
            "asset_hint": slot["source"],
        }
    )
    return segment


def build_segment_map(cfg: dict, narration: dict[str, str]) -> dict:
    corners = {corner["id"]: corner for corner in cfg["corners"]}
    segments = [fixed_segment(slot, corners[slot["corner"]]["kind"])
                for slot in cfg["fixed_slots"]]
    for block in sorted(cfg["blocks"], key=lambda item: item["order"]):
        if block["id"] not in narration:
            continue
        kind = corners[block["corner"]]["kind"]
        if kind == "ending":
            continue
        segments.append(
            {
                "order": block["order"],
                "id": block["id"],
                "slide": block["slide"],
                "type": "tts",
                "voice": block.get("voice", cfg["voices"]["default"]),
                "title": block.get("title", block["id"]),
                "cue": block.get("cue", ""),
                "source": block.get("source", ""),
                "text": narration[block["id"]],
            }
        )
    segments.sort(key=lambda item: item["order"])
    return {
        "episode": cfg["episode"],
        "visual": cfg["visuals"]["html"],
        "voices": cfg["voices"],
        "notes": "Generated by tools/orchestrator/build_pipeline.py; do not hand-edit.",
        "segments": segments,
    }


def validate_config(cfg: dict, date: str) -> None:
    if cfg.get("episode") != date:
        raise PipelineError("config episode does not match --date")
    if cfg.get("language") != "ja-JP":
        raise PipelineError("config language must be ja-JP")
    for key in ("corners", "blocks", "fixed_slots", "canonical_order", "visuals", "voices"):
        if key not in cfg:
            raise PipelineError(f"config is missing {key}")
    corners = cfg["corners"]
    if not isinstance(corners, list) or not corners:
        raise PipelineError("config corners must be a non-empty array")
    corner_ids = [item.get("id") for item in corners]
    require_unique(corner_ids, "corner id")
    for item in corners:
        for key in ("id", "kind", "order", "title"):
            if key not in item:
                raise PipelineError(f"corner is missing {key}: {item.get('id', '?')}")
        if item["kind"] not in CORNER_ORDER:
            raise PipelineError(f"unknown corner kind: {item['kind']}")
    ordered = sorted(corners, key=lambda item: item["order"])
    actual_kinds = [item["kind"] for item in ordered]
    unique_kinds = [kind for index, kind in enumerate(actual_kinds)
                    if index == 0 or kind != actual_kinds[index - 1]]
    if unique_kinds != list(CORNER_ORDER):
        raise PipelineError("corner playback order violates: " + " -> ".join(CORNER_ORDER))
    present = set(actual_kinds)
    missing = set(CORNER_ORDER) - present
    if missing:
        raise PipelineError(f"missing corner kinds: {', '.join(sorted(missing))}")
    blocks = cfg["blocks"]
    corner_by_id = {item["id"]: item for item in corners}
    block_ids = [item.get("id") for item in blocks]
    require_unique(block_ids, "block id")
    corner_for_block = {}
    for block in blocks:
        for key in ("id", "corner", "order", "slide"):
            if key not in block:
                raise PipelineError(f"block is missing {key}: {block.get('id', '?')}")
        if block["corner"] not in corner_by_id:
            raise PipelineError(f"unknown block corner: {block['corner']}")
        corner = corner_by_id[block["corner"]]
        corner_for_block[block["id"]] = corner
        lo, hi = BLOCK_RANGE[corner["kind"]]
        if not isinstance(block["order"], int) or not lo <= block["order"] <= hi:
            raise PipelineError(f"block order outside corner range: {block['id']}")

    canonical = cfg["canonical_order"]
    if not isinstance(canonical, dict):
        raise PipelineError("canonical_order must be an object")
    for kind in CORNER_ORDER:
        expected = canonical.get(kind)
        if not isinstance(expected, list):
            raise PipelineError(f"canonical_order is missing {kind}")
        actual = sorted(
            (block for block in blocks if corner_for_block[block["id"]]["kind"] == kind),
            key=lambda block: (block["order"], block["id"]),
        )
        if [block["id"] for block in actual] != expected:
            raise PipelineError(f"canonical_order does not match blocks in {kind}")

    slots = cfg["fixed_slots"]
    if not isinstance(slots, list):
        raise PipelineError("fixed_slots must be an array")
    require_unique([item.get("id") for item in slots], "fixed slot id")
    expected_slot_count = (
        3 if str(cfg.get("episode", "")) >= CONTRACT_NEW_EFFECTIVE_DATE else 2
    )
    if len(slots) != expected_slot_count:
        raise PipelineError(
            f"{expected_slot_count} fixed slots are required for this episode date"
        )
    roles = {"opening": 0, "ending": 0}
    for slot in slots:
        required = ("id", "corner", "order", "slide")
        if slot.get("visual") != "end-card":
            required += ("source",)
        for key in required:
            if key not in slot:
                raise PipelineError(f"fixed slot is missing {key}: {slot.get('id', '?')}")
        if slot["corner"] not in corner_by_id:
            raise PipelineError(f"unknown fixed-slot corner: {slot['corner']}")
        kind = corner_by_id[slot["corner"]]["kind"]
        if kind not in roles:
            raise PipelineError("fixed slots must belong to opening/ending corners")
        if slot.get("visual") == "end-card":
            if kind != "ending":
                raise PipelineError("END-card fixed slot must belong to the ending corner")
            continue
        roles[kind] += 1
        if slot["source"] not in ("assets/audio/fixed/opening.wav", "assets/audio/fixed/ending.wav"):
            raise PipelineError(f"invalid fixed source: {slot['source']}")
    if roles != {"opening": 1, "ending": 1}:
        raise PipelineError("opening and ending each require one fixed slot")
    helper = next((block for block in blocks if block.get("id") == OBSOLETE_OUTRO_ID), None)
    if helper is not None:
        raise PipelineError("END-outro is obsolete; the fixed ending contains the greeting")
    ending = next(
        slot for slot in slots
        if corner_by_id[slot["corner"]]["kind"] == "ending"
        and slot.get("visual") != "end-card"
    )
    if ending["id"] != "END-disclaimer":
        raise PipelineError("ending slot id must be END-disclaimer")
    if ending["source"] != "assets/audio/fixed/ending.wav":
        raise PipelineError("ending slot source must be the reusable ending wav")
    if ending.get("visual_only") is not True:
        raise PipelineError("ending slot must be visual_only; do not voice the disclaimer")
    if ending.get("text"):
        raise PipelineError("ending slot must not contain narration text")
    if str(cfg.get("episode", "")) >= CONTRACT_NEW_EFFECTIVE_DATE:
        end_card = next((slot for slot in slots if slot.get("id") == "END-card"), None)
        if end_card is None:
            raise PipelineError("new ending contract requires an END-card fixed slot")
        if end_card.get("visual") != "end-card":
            raise PipelineError("END-card fixed slot must use visual=end-card")
    _validate_visual_slides(cfg)
    visuals = cfg["visuals"]
    if visuals.get("html") != "visual.html":
        raise PipelineError("visuals.html must be visual.html")
    voices = cfg["voices"]
    if not isinstance(voices.get("default"), str) or not voices["default"]:
        raise PipelineError("voices.default is required")


def paragraphs_from_text(text: str) -> list[str]:
    paragraphs: list[str] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("#") or not line:
            if current:
                paragraphs.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current))
    return paragraphs


def scaffold_contracts(date: str, from_map: bool) -> None:
    cfg_path = config_path(date)
    smap_path = map_path(date)
    script_file = script_path(date)
    existing_cfg = cfg_path.is_file()
    if existing_cfg:
        cfg = read_json(cfg_path)
        validate_config(cfg, date)
    elif from_map:
        if not smap_path.is_file():
            raise PipelineError(f"cannot scaffold without a map: {smap_path}")
        smap = read_json(smap_path)
        by_id = {}
        for segment in smap.get("segments", []):
            sid = segment.get("id")
            if not isinstance(sid, str) or sid in by_id:
                raise PipelineError(f"segment id is missing or duplicated: {sid}")
            by_id[sid] = segment
        groups: dict[str, list[dict]] = {}
        pattern = re.compile(r"^(A|B[1-9]|C|D)-p\d+$")
        for sid, segment in by_id.items():
            match = pattern.fullmatch(sid)
            if match:
                groups.setdefault(match.group(1), []).append(segment)
        order = {"A": 1, "B1": 2, "B2": 3, "B3": 4, "B4": 5, "C": 6, "D": 7}
        for group in groups.values():
            group.sort(key=lambda segment: (segment["order"], segment["id"]))
        themes = [name for name in sorted(groups, key=lambda name: order.get(name, 99))
                  if name.startswith("B")]
        corners = [
            {"id": "OP", "kind": "opening", "order": 1, "title": "オープニング"},
            {"id": "MKT", "kind": "market", "order": 2, "title": "市場概況"},
            *[{"id": name, "kind": "themes", "order": 3 + index, "title": name}
              for index, name in enumerate(themes)],
            {"id": "NEWS", "kind": "news", "order": 40, "title": "ニュースハイライト"},
            {"id": "EVENTS", "kind": "events", "order": 41, "title": "直近イベント予告"},
            {"id": "ED", "kind": "ending", "order": 50, "title": "エンディング"},
        ]
        corner_kind = {corner["id"]: corner["kind"] for corner in corners}
        running: dict[str, int] = {}
        theme_order = 200
        blocks = []
        canonical: dict[str, list[str]] = {kind: [] for kind in CORNER_ORDER}
        corner_name = {"A": "OP", "C": "NEWS", "D": "EVENTS"}
        corner_base = {"opening": 2, "market": 100, "news": 400, "events": 500, "ending": 800}
        for name in sorted(groups, key=lambda item: order.get(item, 99)):
            corner = corner_name.get(name, name if name.startswith("B") else "OP")
            kind = corner_kind[corner]
            if kind == "themes":
                base = theme_order
            else:
                base = corner_base[kind]
            index = running.get(corner, 0)
            order = base + index
            canonical["themes" if corner.startswith("B") else
                      {"OP": "opening", "NEWS": "news", "EVENTS": "events"}[corner]].extend(
                segment["id"] for segment in groups[name])
            for segment in groups[name]:
                blocks.append({
                    "id": segment["id"], "corner": corner,
                    "order": order, "slide": segment["slide"],
                    "voice": segment.get("voice", "xiaomei"),
                    "title": segment.get("title", segment["id"]),
                    "cue": segment.get("cue", ""),
                    "source": segment.get("source", ""),
                })
                index += 1
                order = base + index
                running[corner] = index
                if kind == "themes":
                    theme_order = order + 1
        if date < CONTRACT_NEW_EFFECTIVE_DATE:
            haiku_id = "S01-haiku"
            blocks.insert(1, {
                "id": haiku_id, "corner": "OP", "order": 1, "slide": "s1",
                "voice": "kyoujyu", "title": "Opening haiku", "cue": "",
                "source": "opening haiku",
            })
            canonical["opening"] = [haiku_id] + canonical["opening"]
        blocks.sort(key=lambda item: (item["order"], item["id"]))
        cfg = {
            "episode": date,
            "language": "ja-JP",
            "corners": corners,
            "blocks": blocks,
            "canonical_order": canonical,
            "fixed_slots": [
                {
                    "id": "OPENING", "corner": "OP", "order": 0, "slide": "s0",
                    "voice": "kyoujyu", "source": "assets/audio/fixed/opening.wav",
                },
                {
                    "id": "END-disclaimer", "corner": "ED", "order": 900, "slide": "s47",
                    "source": "assets/audio/fixed/ending.wav",
                    "visual_only": True,
                },
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
        write_json(cfg_path, cfg)
    else:
        raise PipelineError("no config exists; use --from-map for the first conversion")

    old_script = read_json(script_file) if script_file.is_file() else {"episode": date, "blocks": []}
    existing_script = {item.get("id"): item for item in old_script.get("blocks", [])
                       if isinstance(item, dict)}
    smap = read_json(smap_path) if smap_path.is_file() else None
    segments = {item.get("id"): item for item in (smap or {}).get("segments", [])}
    source = "episode.config.json" if from_map and not smap_path.is_file() else "segment-map.json"
    script_blocks = []
    for block in cfg["blocks"]:
        sid = block["id"]
        if sid in existing_script and isinstance(existing_script[sid].get("text"), str):
            item = existing_script[sid]
            text = item["text"]
            source = "existing script"
        elif sid in segments and isinstance(segments[sid].get("text"), str):
            segment = segments[sid]
            text = segment["text"]
        else:
            text = ""
        script_blocks.append({"id": sid, "text": text})
    script = {"episode": date, "language": "ja-JP", "source": source, "blocks": script_blocks}
    write_json(script_file, script)
    print(f"[scaffold] {'kept' if existing_cfg else 'created'} {cfg_path}")
    print(f"[scaffold] wrote {script_file} ({len(script_blocks)} blocks)")


def build_map_command(cfg: dict, date: str, only: list[str] | None = None) -> dict:
    partial = bool(only)
    cmd: dict = {
        "episode": date,
        "partial": partial,
        "prepare_tts": [
            str(PY), str(ROOT / "tools" / "tts" / "prepare_tts.py"),
            date,
        ],
        "generate_audio": [
            str(PY), str(ROOT / "tools" / "tts" / "generate_audio.py"), date,
        ],
        "prepare_remotion": [
            str(PY), str(ROOT / "tools" / "remotion" / "prepare_remotion.py"),
            "--issue", date,
        ],
        "remotion_render": [
            "npx", "remotion", "render", "src/index.ts", "Episode", "out/episode.mp4",
            "--props=public/remotion_input.json", "--concurrency=16",
        ],
        "render_output": str(issue_dir(date) / "episode.mp4"),
        "remotion_cwd": str(ROOT / "remotion"),
        "episode_dir": str(issue_dir(date)),
    }
    if partial:
        cmd["only"] = sorted(set(only or []))
        cmd["prepare_tts"].append("--partial")
        cmd["generate_audio"].extend(["--only", *cmd["only"]])
    return cmd


def artifact_errors(date: str) -> list[str]:
    errors: list[str] = []
    cfg = read_json(config_path(date))
    validate_config(cfg, date)
    smap = read_json(map_path(date))
    narration = validate_script(cfg, read_json(script_path(date)))
    expected_map = build_segment_map(cfg, narration)

    def segment_key(segment: dict) -> tuple:
        return (
            segment["id"], segment["order"], segment["slide"], segment.get("type"),
            segment.get("voice", cfg["voices"]["default"]), segment.get("text", ""),
        )

    actual = sorted(smap.get("segments", []), key=lambda item: item["order"])
    expected = sorted(expected_map["segments"], key=lambda item: item["order"])
    if [segment_key(item) for item in actual] != [segment_key(item) for item in expected]:
        actual_ids = [item.get("id") for item in actual]
        expected_ids = [item.get("id") for item in expected]
        if actual_ids == expected_ids:
            for left, right in zip(actual, expected):
                if segment_key(left) != segment_key(right):
                    errors.append(f"segment field mismatch: {left.get('id')}")
        else:
            missing = sorted(set(expected_ids) - set(actual_ids))
            extra = sorted(set(actual_ids) - set(expected_ids))
            if missing:
                errors.append("missing segments: " + ", ".join(missing))
            if extra:
                errors.append("unexpected segments: " + ", ".join(extra))
            if not missing and not extra:
                errors.append("segment order differs from config")

    durations = read_json(durations_path(date))
    measured = {item.get("id"): item for item in durations.get("segments", [])}
    stale_paths = []
    for segment in expected:
        if segment["type"] != "tts":
            continue
        tts_file = issue_dir(date) / "production" / "tts" / f"{segment['id']}.txt"
        if not tts_file.is_file():
            continue
        if tts_file.stat().st_mtime_ns < script_file.stat().st_mtime_ns:
            stale_paths.append(str(tts_file.relative_to(issue_dir(date))))
        item = measured.get(segment["id"])
        audio_rel = item.get("file", "") if item else ""
        audio_file = issue_dir(date) / audio_rel if audio_rel else None
        if audio_file and audio_file.is_file() and audio_file.stat().st_mtime_ns < tts_file.stat().st_mtime_ns:
            stale_paths.append(str(audio_file.relative_to(issue_dir(date))))
    if stale_paths:
        errors.append(
            "stale generated artifacts (regenerate audio): "
            + ", ".join(stale_paths)
        )

    for segment in expected:
        if segment["type"] != "tts":
            continue
        item = measured.get(segment["id"])
        if item is None:
            errors.append(f"no measured audio: {segment['id']}")
        elif not (issue_dir(date) / item.get("file", "")).is_file():
            errors.append(f"measured audio file is missing: {segment['id']}")

    if not INPUT_PATH.is_file():
        errors.append(f"missing remotion input: {INPUT_PATH}")
    else:
        rendered = read_json(INPUT_PATH)
        segments = rendered.get("segments", [])
        expected_ids = [item["id"] for item in expected if item["type"] == "tts"]
        if (ROOT / "assets/audio/fixed/opening.wav").is_file():
            # prepare_remotion injects the fixed opening as S00-intro when the
            # map has no opening narration segment.
            expected_ids.insert(0, "S00-intro")
        if (ROOT / "assets/audio/fixed/ending.wav").is_file():
            # The visual-only ending slot carries the reusable fixed ending
            # audio and is always the final Remotion segment.
            expected_ids.append("END-disclaimer")
        rendered_ids = [item.get("id") for item in segments]
        if rendered_ids[:1] != [expected_ids[0]]:
            errors.append("render input does not start with the ending/opening contract segment")
        if rendered_ids[-1:] != [expected_ids[-1]]:
            errors.append("render input does not end with END-disclaimer")
        if set(expected_ids) != set(rendered_ids):
            missing = sorted(set(expected_ids) - set(rendered_ids))
            extra = sorted(set(rendered_ids) - set(expected_ids))
            if missing:
                errors.append("render input missing segments: " + ", ".join(missing))
            if extra:
                errors.append("render input has unexpected segments: " + ", ".join(extra))
    return errors


def resolve_windows_launcher(command: str) -> str:
    """Resolve npm launchers; CreateProcess does not search PATHEXT."""
    if os.name != "nt" or Path(command).suffix or Path(command).is_absolute():
        return command
    return shutil.which(command) or command


def run_checked(args: list[str], cwd: Path | None = None) -> None:
    print("[run] " + " ".join(args))
    args = [resolve_windows_launcher(args[0]), *args[1:]]
    result = subprocess.run(args, cwd=cwd)
    if result.returncode != 0:
        raise PipelineError(f"command failed ({result.returncode}): {' '.join(args)}")


def run_pipeline(date: str, render: bool) -> None:
    cfg = read_json(config_path(date))
    validate_config(cfg, date)
    narration = validate_script(
        cfg, read_json(script_path(date)), validate_visual_sync=False
    )
    write_json(map_path(date), build_segment_map(cfg, narration))
    _validate_slide_narration_sync(narration, cfg)
    commands = build_map_command(cfg, date)
    run_checked(commands["prepare_tts"])
    run_checked(commands["generate_audio"])
    if render:
        run_checked(commands["prepare_remotion"])
        output = Path(commands["render_output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        render_args = commands["remotion_render"]
        # The template output arg is the final archive path; replace it here so
        # the command list stays readable and every date renders in place.
        render_args[5] = str(output)
        run_checked(render_args, cwd=Path(commands["remotion_cwd"]))
        if not output.is_file() or output.stat().st_size == 0:
            raise PipelineError(f"render output is missing or empty: {output}")
    else:
        run_checked(commands["prepare_remotion"] + ["--skip-shots"])
    errors = artifact_errors(date)
    if errors:
        raise PipelineError("artifact validation failed:\n- " + "\n- ".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "validate", "build-map", "check-artifacts", "commands", "run",
        "scaffold", "prepare_tts", "prepare_remotion"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--from-map", action="store_true", help="scaffold script.json from an existing map")
    parser.add_argument("--only", nargs="+", default=None,
                        help="build map/commands for these block ids only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date = args.date
    try:
        if args.command == "scaffold":
            scaffold_contracts(date, args.from_map)
        cfg = read_json(config_path(date))
        validate_config(cfg, date)
        if args.command == "validate":
            validate_script(cfg, read_json(script_path(date)))
        elif args.command == "build-map":
            raw_script = read_json(script_path(date))
            if args.only:
                narration = validate_script(cfg, raw_script, set(args.only))
                unknown = sorted(set(args.only) - set(narration))
                if unknown:
                    raise PipelineError("unknown --only blocks: " + ", ".join(unknown))
                write_json(map_path(date), build_segment_map(cfg, {k: narration[k] for k in args.only}))
                print(f"[done] partial {map_path(date)} ({len(args.only)} blocks)")
            else:
                narration = validate_script(cfg, raw_script, validate_visual_sync=False)
                write_json(map_path(date), build_segment_map(cfg, narration))
                _validate_slide_narration_sync(narration, cfg)
                print(f"[done] {map_path(date)}")
        elif args.command == "check-artifacts":
            errors = artifact_errors(date)
            if errors:
                raise PipelineError("artifact validation failed:\n- " + "\n- ".join(errors))
            print("[ok] artifacts match episode contract")
        elif args.command == "commands":
            print(json.dumps(build_map_command(cfg, date, args.only), ensure_ascii=False, indent=2))
        elif args.command == "run":
            run_pipeline(date, args.render)
        elif args.command == "prepare_tts":
            run_checked(build_map_command(cfg, date, args.only)["prepare_tts"])
            print("[done] prepare_tts")
        elif args.command == "prepare_remotion":
            cmd = build_map_command(cfg, date)["prepare_remotion"]
            if not args.render:
                cmd = cmd + ["--skip-shots"]
            run_checked(cmd)
            print("[done] prepare_remotion")
        return 0
    except PipelineError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[interrupted]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

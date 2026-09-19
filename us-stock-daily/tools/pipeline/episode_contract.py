"""Single source of truth for the episode audio/visual contract.

Pipeline scripts must import these values instead of restating dates,
phrase templates, slide-count limits, or asset paths.
"""
from __future__ import annotations

import re


CONTRACT_EFFECTIVE_DATE = "2026-09-10"
CONTRACT_NEW_EFFECTIVE_DATE = "2026-09-17"
PREVIEW_V2_DATE = "2026-09-19"

PREVIEW_MIN_CHARS = 80
PREVIEW_MAX_CHARS = 120
PREVIEW_TITLE_MAX_CHARS = 20
PREVIEW_SUMMARY_MIN_CHARS = 20
PREVIEW_SUMMARY_MAX_CHARS = 80

OPENING_SLIDE_ID = "s0"
LEGACY_VISUAL_SLIDE_COUNT = 57
LEGACY_ENDING_SLIDE = "s56"
CONTRACT_SKELETON_SLIDES = 60

# News has eight narrated items but shares one aggregate highlight page.
# Narration is per item; visuals are per page.
NEWS_ITEM_COUNT = 8
NEWS_SLIDE_COUNT = 1
EVENT_SLIDE_COUNT = 1
THEME_PAGE_COUNT = 8

# Page layout (2026-09-17 contract): s0 title card, s1..sN previews,
# s(N+1) market, then theme_count * THEME_PAGE_COUNT theme pages.
# Page layout (2026-09-19 preview-v2 contract): s0 title card,
# s1 ONE aggregate preview list, s2 market, then B pages from s3.
MARKET_SLIDE_COUNT = 1

# All per-episode images live in the issue-root assets/ directory.
# File names are block + page: b1-1.png ... b5-8.png, opening.png.
# B p1 is derived from the whole theme article; p2.. are derived per
# paragraph and reuse p1's file unless the paragraph's main entity deviates.
ASSETS_DIR = "assets"
OPENING_VISUAL_ASSET = "assets/opening.png"
OPENING_TEMPLATE_ASSET = "assets/brands/template/opening-visual.png"
THEME_IMAGE_ASSET_TEMPLATE = "assets/b{n}-{page}.png"

# Keyword-counted shared media reuse (2026-09-18 contract). Paths are
# relative to the us-stock-daily/ root, not the daily issue root.
MEDIA_DB_PATH = "db/media-assets.sqlite3"
MEDIA_RESOURCES_DIR = "assets/media_resources"
KEYWORD_PROMOTION_THRESHOLD = 3


def is_new_contract(date: str) -> bool:
    return str(date) >= CONTRACT_NEW_EFFECTIVE_DATE


def is_preview_v2(date: str) -> bool:
    """One spoken title+summary per theme and ONE visual list page."""
    return str(date) >= PREVIEW_V2_DATE


def opening_theme_prefix(theme_count: int) -> str:
    return f"本日、{theme_count}つのテーマを取り上げます。"


def opening_end_phrase(theme_count: int) -> str:
    return (
        f"今日はこの{theme_count}つのテーマについて"
        "とことん解説いたします。"
    )


_THEME_PREFIX_RE = re.compile(
    r"本日、?[0-9一二三四五六七八九十]+つのテーマを取り上げます。?"
)
_END_PHRASE_RE = re.compile(
    r"今日はこの[0-9一二三四五六七八九十]+つのテーマについて"
    r"とことん解説いたします。?"
)


def strip_opening_theme_prefix(text: str) -> str:
    return _THEME_PREFIX_RE.sub("", text, count=1)


def strip_opening_end_phrase(text: str) -> str:
    return _END_PHRASE_RE.sub("", text, count=1)


def theme_image_asset(theme_number: int, page_number: int) -> str:
    """Issue-root-relative image path for one B theme narration page."""
    if theme_number < 1:
        raise ValueError(f"invalid theme number: {theme_number}")
    if page_number < 1 or page_number > THEME_PAGE_COUNT:
        raise ValueError(f"invalid theme page number: {page_number}")
    return THEME_IMAGE_ASSET_TEMPLATE.format(
        n=theme_number, page=page_number
    )


def theme_base_image_asset(theme_number: int) -> str:
    """Return p1, the canonical source image copied to every theme page."""
    return theme_image_asset(theme_number, 1)


def ending_slide_numbers(
    theme_count: int,
    theme_page_count: int,
    date: str = "",
) -> tuple[int, int]:
    """Return END-card and END-disclaimer slide numbers."""
    end_card_number = (
        event_slide_number(theme_count, theme_page_count, date) + 1
    )
    return end_card_number, end_card_number + 1


def ending_slide_ids(
    theme_count: int,
    theme_page_count: int,
    date: str = "",
) -> tuple[str, str]:
    end_card_number, disclaimer_number = ending_slide_numbers(
        theme_count, theme_page_count, date
    )
    return f"s{end_card_number}", f"s{disclaimer_number}"


def preview_block_id(theme_number: int) -> str:
    return f"A-p{theme_number}"


def preview_slide_id(theme_number: int) -> str:
    return f"s{theme_number}"


def preview_list_slide_id() -> str:
    """Aggregate opening list page for the preview-v2 contract."""
    return "s1"


def preview_list_slide_number() -> int:
    """Aggregate opening list page number for the preview-v2 contract."""
    return 1


def preview_block_number(block_id: str) -> int | None:
    match = re.fullmatch(r"A-p([1-9][0-9]*)", str(block_id or ""))
    return int(match.group(1)) if match else None


def news_slide_number(
    theme_count: int,
    theme_page_count: int,
    date: str = "",
) -> int:
    """Return the one aggregate News Highlights page number."""
    if is_preview_v2(date):
        # s1 preview list, s2 market, then B pages start at s3.
        return theme_page_count + 3
    return (
        theme_count
        + theme_page_count
        + MARKET_SLIDE_COUNT
        + 1
    )


def event_slide_number(
    theme_count: int,
    theme_page_count: int,
    date: str = "",
) -> int:
    """Return the fixed event-preview page number."""
    return news_slide_number(theme_count, theme_page_count, date) + 1

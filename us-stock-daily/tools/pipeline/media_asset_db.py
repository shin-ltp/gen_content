# -*- coding: utf-8 -*-
"""Keyword-counted shared media asset cache (two SQLite tables).

2026-09-18 contract:
- candidate_keywords counts how often one keyword produced a saved image.
- Once usage_count exceeds KEYWORD_PROMOTION_THRESHOLD, the image is copied
  into the shared assets/media_resources/ directory and the keyword moves to
  media_assets. Future resolutions check media_assets first and reuse the
  file directly, skipping search/generation entirely.

The sqlite file is derived runtime state (gitignored via db/*); tables are
created on demand so no separate schema bootstrap step is required.
"""
from __future__ import annotations

import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from episode_contract import (
    KEYWORD_PROMOTION_THRESHOLD,
    MEDIA_DB_PATH,
    MEDIA_RESOURCES_DIR,
)


def connect(us_root: Path) -> sqlite3.Connection:
    db_path = us_root / MEDIA_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS candidate_keywords (
            keyword     TEXT PRIMARY KEY,
            usage_count INTEGER NOT NULL DEFAULT 1,
            last_image  TEXT NOT NULL DEFAULT '',
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS media_assets (
            keyword       TEXT PRIMARY KEY,
            file_path     TEXT NOT NULL,
            portrait      INTEGER NOT NULL DEFAULT 0,
            subject_type  TEXT NOT NULL DEFAULT '',
            source        TEXT NOT NULL DEFAULT '',
            usage_count   INTEGER NOT NULL,
            registered_at TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        """
    )
    return conn


def normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", " ", str(keyword or "")).strip().lower()


def slugify_keyword(keyword: str) -> str:
    slug = re.sub(r"[^a-z0-9あ-んァ-ヶ一-龠ー]+", "-", normalize_keyword(keyword))
    return slug.strip("-")[:80] or "keyword"


def find_media_asset(conn: sqlite3.Connection, keyword: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM media_assets WHERE keyword = ?",
        (normalize_keyword(keyword),),
    ).fetchone()
    return dict(row) if row else None


def register_use(
    conn: sqlite3.Connection,
    us_root: Path,
    keyword: str,
    image: Path,
    *,
    portrait: bool,
    subject_type: str,
    source: str,
) -> str:
    """Count one successful search/generation for keyword.

    Returns "registered" while under the promotion threshold, or "promoted"
    when the keyword exceeded it and its image now lives in media_resources.
    """
    key = normalize_keyword(keyword)
    if not key:
        return "registered"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rel_image = str(image).replace("\\", "/")

    existing = conn.execute(
        "SELECT keyword FROM media_assets WHERE keyword = ?", (key,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE media_assets SET usage_count = usage_count + 1, "
            "updated_at = ? WHERE keyword = ?",
            (now, key),
        )
        conn.commit()
        return "promoted"

    row = conn.execute(
        "SELECT usage_count FROM candidate_keywords WHERE keyword = ?", (key,)
    ).fetchone()
    count = (row["usage_count"] if row else 0) + 1
    if count > KEYWORD_PROMOTION_THRESHOLD:
        shared_dir = us_root / MEDIA_RESOURCES_DIR
        shared_dir.mkdir(parents=True, exist_ok=True)
        target = shared_dir / f"{slugify_keyword(key)}.png"
        if image.is_file():
            shutil.copy2(image, target)
        conn.execute(
            "INSERT INTO media_assets (keyword, file_path, portrait, "
            "subject_type, source, usage_count, registered_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(keyword) DO UPDATE SET usage_count = excluded.usage_count, "
            "updated_at = excluded.updated_at",
            (
                key, target.relative_to(us_root).as_posix(),
                int(bool(portrait)), subject_type, source, count, now, now,
            ),
        )
        conn.execute("DELETE FROM candidate_keywords WHERE keyword = ?", (key,))
        state = "promoted"
    else:
        conn.execute(
            "INSERT INTO candidate_keywords (keyword, usage_count, last_image, updated_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(keyword) DO UPDATE SET usage_count = excluded.usage_count, "
            "last_image = excluded.last_image, updated_at = excluded.updated_at",
            (key, count, rel_image, now),
        )
        state = "registered"
    conn.commit()
    return state

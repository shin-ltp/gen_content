"""
X（旧Twitter）向け: 指定号の**各エピソードあたり先頭3記事**（metadata の order 順）について投稿文を生成し、
Playwright（専用プロファイル / headless）でバックグラウンドで UI 自動投稿する。

前提: 初回のみ python x_browser_post.py --login を実行し、開く専用ウィンドウで X にログイン。
普段使いの Chrome には触れず、リモートデバッグの手動有効化も不要。
以降はすべて headless で実行され、他のブラウザ作業を邪魔しない。

- 各エピソード metadata.json の**先頭3記事**（order 昇順）ごとに、日本語タイトル・要約・YouTube URL（t=開始秒）・
  keywords_ja の先頭2件（括弧内の注釈は除去）＋固定タグ #ザ・エコノミスト を組み立てる。
- summary_ja に「日本」が含まれる場合は articles/NNN.md を Gemini に渡し要約を差し替え。
- share/tweets.json に下書き・投稿結果をまとめる（各行に post_completed / tweet_url / posted_at 等）。
  旧名 tweets_draft.json が残っている場合は読み込み時のみフォールバックし、保存は常に tweets.json。
- tweets.json が既にあり、metadata 上の記事並び（エピソード・順序・article_id）と一致する場合は
  Gemini / 本文の再生成をスキップする。要約等を変えたい場合は tweets.json を削除するか別号で出力する。
- 各投稿は最大3回（初回＋リトライ2回）まで試行し、それでも失敗したら終了する。
- 連続投稿間隔は既定 3〜5 分（ランダム）。入力・クリックにもランダム待機を挟む（封号対策）。
- tweets.json を**新規生成**したとき（metadata から下書きを組み立てた直後）、同じく share/note.md を
  他プラットフォーム向け紹介文として出力する（固定ブロック＋Gemini によるハイライト＋章ごと見出し・記事一覧・動画URL）。

使用例:
  python generate_x_share.py --issue 2026-03-21 --dry-run
  python generate_x_share.py --issue 2026-03-21
  python generate_x_share.py --issue 2026-03-21 --reset-progress
  python generate_x_share.py --test-post "テスト投稿"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import text_llm
from config import get_issue_dir
from x_browser_post import (
    delete_tweet_via_browser,
    human_delay,
    post_interval_seconds,
    post_tweet_via_browser,
    ensure_x_session,
)

# X 投稿欄・twitter-text v3 と同じ加重カウント（config/v3.json）
# ・多くのラテン等は weight 100（表示上 1）、CJK・かな・全角句読点等は既定で weight 200（表示上 2）
# ・合計 weight が maxWeightedTweetLength * scale = 280 * 100 を超えないように要約を削る
MAX_X_WEIGHTED_LIMIT = 280 * 100
X_WEIGHT_SCALE = 100
# 短縮後の t.co 相当として URL 1 件あたり 23 * scale
X_URL_WEIGHTED_LEN = 23 * X_WEIGHT_SCALE
_KEYWORDS_FOR_TAGS = 2
# 各エピソードで X 投稿を作る記事数（order 昇順の先頭 N 件）
_MAX_ARTICLES_PER_EPISODE_FOR_X = 3
_FIXED_HASHTAG = "#ザ・エコノミスト"
_X_POST_PREFIX = "[ザ・エコノミスト]"
POST_INTERVAL_SEC_MIN = 180  # 3 分
POST_INTERVAL_SEC_MAX = 300  # 5 分
POST_ATTEMPTS_MAX = 3  # 初回 + リトライ2回
TWEETS_JSON_NAME = "tweets.json"
LEGACY_TWEETS_JSON_NAME = "tweets_draft.json"  # 読み込みフォールバックのみ（保存はしない）
NOTE_MD_NAME = "note.md"

# Economist 英語セクション名 → 日本語表記（note.md 見出し用。未登録は英語のまま）
_SECTION_LABEL_JA: Dict[str, str] = {
    "Business": "ビジネス",
    "Finance & economics": "金融・経済",
    "Leaders": "リーダーズ",
    "Letters": "読者の手紙",
    "United States": "米国",
    "The Americas": "中南米",
    "International": "国際",
    "China": "中国",
    "Science & technology": "科学・技術",
    "Europe": "ヨーロッパ",
    "Politics": "政治",
    "Briefing": "ブリーフィング",
    "Asia": "アジア",
    "Middle East & Africa": "中東・アフリカ",
    "Britain": "英国",
    "By Invitation": "招待論説",
}

# note.com へ貼り付ける用。Markdown の空行（\\n\\n）は貼付時に段落余白が二重になるため使わない。
NOTE_FIXED_INTRO = """\
グローバル・クリップは世界を動かす有力メディアから、今知っておくべき情報のエッセンスだけを厳選してお届けするYoutubeチャンネルです。
通勤や休憩の合間、耳を傾けるだけで視界が広がります。そんな体験を提案致します。
国内のニュースだけでバイアスや閉塞感を感じる方、世界で何が起きているか違う視点から捉えたい方、 是非視聴してみてください。
https://www.youtube.com/@GLOBAL_CLIP-JP"""


def _safe_read_json(path: Path) -> Dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def _load_all_episode_metadata(issue_dir: Path) -> List[Dict[str, Any]]:
    episodes_dir = issue_dir / "episodes"
    if not episodes_dir.exists():
        return []
    metas: List[Dict[str, Any]] = []
    for ep_dir in sorted(episodes_dir.iterdir(), key=lambda p: p.name):
        if not ep_dir.is_dir():
            continue
        meta_path = ep_dir / "metadata.json"
        meta = _safe_read_json(meta_path)
        if meta:
            metas.append(meta)
    return metas


def _youtube_url_with_t(video_url: str, start_sec: float | int) -> str:
    url = (video_url or "").strip()
    if not url:
        return url
    t = max(0, int(round(float(start_sec))))
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={t}"


def _issue_date_japanese(issue_date: str) -> str:
    parts = issue_date.strip().split("-")
    if len(parts) != 3:
        return issue_date.strip()
    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
    return f"{y}年{m}月{d}日"


def _youtube_video_base_url(video_url: str) -> str:
    u = (video_url or "").strip()
    if not u:
        return ""
    return u.split("?", 1)[0].strip()


def _episode_sections_display(sections: Any) -> str:
    if not isinstance(sections, list) or not sections:
        return "エピソード"
    labels = [_SECTION_LABEL_JA.get(str(s).strip(), str(s).strip()) for s in sections]
    return "、".join(labels)


def _catalog_lines_for_note(metas: List[Dict[str, Any]], max_lines: int = 120) -> str:
    lines: List[str] = []
    for meta in sorted(metas, key=lambda x: int(x.get("episode_num") or 0)):
        ep = int(meta.get("episode_num") or 0)
        for art in sorted(meta.get("articles") or [], key=lambda a: int(a.get("order") or 0)):
            title = str(art.get("japanese_title") or "").strip()
            intro = str(art.get("one_line_intro") or "").strip()
            if not intro:
                intro = str(art.get("summary_ja") or "")[:120].strip()
            lines.append(f"[ep{ep:02d}] {title} / {intro}")
            if len(lines) >= max_lines:
                return "\n".join(lines)
    return "\n".join(lines)


def _note_highlight_fallback(issue_date: str, metas: List[Dict[str, Any]]) -> str:
    dj = _issue_date_japanese(issue_date)
    parts: List[str] = []
    for meta in sorted(metas, key=lambda x: int(x.get("episode_num") or 0))[:5]:
        for art in sorted(meta.get("articles") or [], key=lambda a: int(a.get("order") or 0))[
            :_MAX_ARTICLES_PER_EPISODE_FOR_X
        ]:
            o = str(art.get("one_line_intro") or "").strip()
            if o:
                parts.append(o)
    blob = " ".join(parts).replace("\n", " ")
    if len(blob) > 198:
        blob = blob[:197].rstrip() + "…"
    if blob.strip():
        return blob
    return (
        f"『ザ・エコノミスト』{dj}号では、世界経済と地政学の最前線を多角的に追い、"
        "日本の視聴者にも身近な含意が読み取れるよう解説しています。"
    )


def _generate_note_highlight(issue_date: str, metas: List[Dict[str, Any]]) -> str:
    dj = _issue_date_japanese(issue_date)
    catalog = _catalog_lines_for_note(metas)
    if not text_llm.is_configured():
        return _note_highlight_fallback(issue_date, metas)

    prompt = f"""あなたはYoutubeチャンネル「グローバル・クリップ」の紹介文ライターです。

## タスク
『ザ・エコノミスト』{dj}号のポッドキャスト版について、**日本の視聴者**が最も気になりそうな観点を押さえ、
今号全体のハイライトを**1段落・200字以内**（句読点含む。厳守）で書いてください。

## 要件
- 敬体（です・ます）
- 見出し・箇条書き・ハッシュタグ・URL は禁止。本文のみ1段落。
- 世間の関心が高いトピックと、日本の読者が特に追いやすい論点（エネルギー・物価・地政学・AI・金融など）のバランスを意識する。
- 視聴欲が湧くトーンで、誇張はしすぎない。

## 今号の記事リスト（参照）
{catalog}
"""
    try:
        text = text_llm.generate_text(prompt, tier="flash")
        text = re.sub(r"^[\"「]|[\"」]$", "", text).strip()
        text = text.replace("\n", "").strip()
        if len(text) > 200:
            text = text[:199].rstrip("、。 ") + "…"
        return text if text else _note_highlight_fallback(issue_date, metas)
    except Exception as e:
        print(f"    [警告] note.md ハイライト生成失敗: {e}")
        return _note_highlight_fallback(issue_date, metas)


def _build_note_md_body(issue_date: str, metas: List[Dict[str, Any]]) -> str:
    """note.com 貼り付け向けプレーンテキスト（単一改行。Markdown 空行は使わない）。"""
    dj = _issue_date_japanese(issue_date)
    article_count = sum(len(m.get("articles") or []) for m in metas)
    episode_count = len(metas)
    highlight = _generate_note_highlight(issue_date, metas)
    intro = (
        "『ザ・エコノミスト』 イギリスが誇る新聞週刊誌、単なる経済誌の枠を超え、最新AIから国際情勢の裏側まで、"
        "地球の『今』という極上の知性を網羅しています。"
        f"今回は『ザ・エコノミスト』{dj}号、全{article_count}篇の記事を厳選し、{episode_count}本の動画に詰め込んでお届けします。"
        "各記事につき、元記事の論点を整理し、背景から含意まで丁寧に掘り下げた音声解説を収録しています。"
    )
    sections: List[str] = [
        f"ザ・エコノミスト　{dj}号",
        "",
        NOTE_FIXED_INTRO,
        "",
        intro,
        highlight,
    ]
    for meta in sorted(metas, key=lambda x: int(x.get("episode_num") or 0)):
        heading = _episode_sections_display(meta.get("sections"))
        ep_lines = [f"■ {heading} section"]
        for i, art in enumerate(
            sorted(meta.get("articles") or [], key=lambda a: int(a.get("order") or 0)),
            start=1,
        ):
            title = str(art.get("japanese_title") or "").strip()
            ep_lines.append(f"{i}. {title}")
        yt = meta.get("youtube") or {}
        vurl = str(yt.get("video_url") or "").strip()
        ep_lines.append(_youtube_video_base_url(vurl))
        sections.append("")
        sections.append("\n".join(ep_lines))
    return "\n".join(sections).rstrip() + "\n"


def _write_share_note_md(share_dir: Path, issue_dir: Path, issue_date: str) -> None:
    metas = _load_all_episode_metadata(issue_dir)
    if not metas:
        return
    body = _build_note_md_body(issue_date, metas)
    out = share_dir / NOTE_MD_NAME
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    # note.com 貼付時: Windows の CRLF だと 1 行ごとに空行が増えるため LF 固定
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    tmp.replace(out)


# twitter-text v3.json の ranges / transformedURLLength に準拠
_URL_IN_POST_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def _x_codepoint_weight(cp: int) -> int:
    if cp <= 4351:  # U+0000–U+10FF
        return 100
    if 8192 <= cp <= 8205 or 8208 <= cp <= 8223 or 8242 <= cp <= 8247:
        return 100
    return 200


def _x_plain_weighted_length(text: str) -> int:
    return sum(_x_codepoint_weight(ord(c)) for c in text)


def _x_weighted_length(text: str) -> int:
    """twitter-text v3 相当の加重合計（MAX_X_WEIGHTED_LIMIT と比較）。"""
    total = 0
    pos = 0
    for m in _URL_IN_POST_RE.finditer(text):
        total += _x_plain_weighted_length(text[pos : m.start()])
        total += X_URL_WEIGHTED_LEN
        pos = m.end()
    total += _x_plain_weighted_length(text[pos:])
    return total


def _strip_keyword_parenthetical(raw: str) -> str:
    """キーワード内の全角・半角括弧に囲まれた注釈（例: 略称（説明））を除去する。"""
    s = str(raw).strip()
    s = re.sub(r"（[^）]*）", "", s)
    s = re.sub(r"\([^)]*\)", "", s)
    return s.strip()


def _keyword_tags_line(keywords_ja: Any) -> str:
    """先頭から有効なキーワードを最大2件＋固定 #ザ・エコノミスト。"""
    if not isinstance(keywords_ja, list):
        keywords_ja = []
    parts: List[str] = []
    for kw in keywords_ja:
        if len(parts) >= _KEYWORDS_FOR_TAGS:
            break
        cleaned = _strip_keyword_parenthetical(str(kw))
        s = "".join(cleaned.split())
        if not s:
            continue
        if s.startswith("#"):
            parts.append(s)
        else:
            parts.append("#" + s)
    parts.append(_FIXED_HASHTAG)
    return " ".join(parts)


def _load_article_markdown(issue_dir: Path, article_id: int | None) -> str | None:
    if article_id is None:
        return None
    try:
        aid = int(article_id)
    except (TypeError, ValueError):
        return None
    p = issue_dir / "articles" / f"{aid:03d}.md"
    if not p.exists():
        return None
    try:
        return p.read_text(encoding="utf-8")
    except Exception:
        return None


def _rewrite_summary_for_japan_reader(
    summary_ja: str,
    article_markdown: str | None,
    japanese_title: str,
) -> str:
    if not text_llm.is_configured():
        print("    [警告] テキスト生成 API 未設定のため要約の書き換えをスキップします。")
        return summary_ja

    body = (article_markdown or "").strip()
    if len(body) > 15000:
        body = body[:15000] + "\n…（以下省略）"

    prompt = f"""あなたは日本の視聴者向けに、海外ニュース解説YouTubeの「紹介コピー」を書く編集者です。

## タスク
以下の記事要約に「日本」という語が含まれています。記事本文（ポッドキャスト原稿）の内容を踏まえ、
**日本人が最も気になる角度**を押さえて、動画を見たくなる**1本の紹介文**だけを出力してください。

## 制約
- 日本語・敬体（です・ます調）
- **200字以内**（句読点・空白含む。厳守）
- ハッシュタグ・URL・見出し・引用符で囲まない。本文のみ1段落

## 記事タイトル（日本語）
{japanese_title}

## 現在の要約
{summary_ja.strip()}

## 記事本文
{body if body else "（本文なし。要約のみで最善を尽くしてください。）"}
"""
    try:
        text = text_llm.generate_text(prompt, tier="flash")
        text = re.sub(r"^[\"「]|[\"」]$", "", text).strip()
        if len(text) > 200:
            text = text[:199].rstrip() + "…"
        return text if text else summary_ja
    except Exception as e:
        print(f"    [警告] 要約書き換え失敗: {e}")
        return summary_ja


def _ensure_x_post_prefix(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return _X_POST_PREFIX
    if stripped.startswith(_X_POST_PREFIX):
        return stripped
    return f"{_X_POST_PREFIX} {stripped}"


def _fit_x_post(
    title: str,
    summary: str,
    url: str,
    tags_line: str,
    limit: int = MAX_X_WEIGHTED_LIMIT,
) -> tuple[str, str]:
    """タイトル・要約（本文）・URL・タグを結合し、X（twitter-text v3）加重長が limit 以下になるよう要約だけを削る。戻り値は (全文, 投稿に使った要約文)。"""
    title = _ensure_x_post_prefix(title)
    summary = summary.strip()
    url = url.strip()
    tags_line = tags_line.strip()
    suffix = f"\n{url}\n{tags_line}" if tags_line else f"\n{url}"
    prefix = f"{title}\n"
    block = f"{prefix}{summary}{suffix}"
    if _x_weighted_length(block) <= limit:
        return block.strip(), summary

    ell = "…"
    lo, hi = 0, len(summary)
    best_mid = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if mid == 0:
            attempt = ell
        else:
            attempt = summary[:mid].rstrip() + ell
        if _x_weighted_length(prefix + attempt + suffix) <= limit:
            best_mid = mid
            lo = mid + 1
        else:
            hi = mid - 1

    if best_mid == -1:
        if _x_weighted_length(prefix + suffix) <= limit:
            return f"{prefix}{suffix}".strip(), ""
        if _x_weighted_length(prefix + ell + suffix) <= limit:
            return f"{prefix}{ell}{suffix}".strip(), ell
        return f"{prefix}{suffix}".strip(), ""

    body = ell if best_mid == 0 else summary[:best_mid].rstrip() + ell
    return f"{prefix}{body}{suffix}".strip(), body


@dataclass
class ArticleTweetDraft:
    episode_num: int
    order_in_episode: int
    article_id: int | None
    japanese_title: str
    summary_used: str
    summary_original: str
    summary_rewritten: bool
    youtube_url: str
    tags_line: str
    tweet_text: str


def _draft_fingerprint(drafts: List[ArticleTweetDraft]) -> str:
    payload = json.dumps(
        [(d.article_id, d.episode_num, d.order_in_episode, d.tweet_text) for d in drafts],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalize_tweet_row_posting(row: Dict[str, Any]) -> None:
    """tweets.json の1行に投稿状態フィールドが無い場合の既定値（インプレース）。"""
    if row.get("tweet_id") and row.get("post_completed") is None:
        row["post_completed"] = True
    row.setdefault("post_completed", False)
    row.setdefault("tweet_id", None)
    row.setdefault("tweet_url", None)
    row.setdefault("posted_at", None)


def _completed_seqs_from_tweets_doc(doc: Dict[str, Any]) -> Set[int]:
    done: Set[int] = set()
    tweets = doc.get("tweets")
    if not isinstance(tweets, list):
        return done
    for i, row in enumerate(tweets, start=1):
        if not isinstance(row, dict):
            continue
        _normalize_tweet_row_posting(row)
        if row.get("post_completed") is True:
            done.add(i)
    return done


def _build_tweets_document(
    issue_date: str,
    drafts: List[ArticleTweetDraft],
    draft_fingerprint: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    tweets: List[Dict[str, Any]] = []
    for d in drafts:
        row = asdict(d)
        row["post_completed"] = False
        row["tweet_id"] = None
        row["tweet_url"] = None
        row["posted_at"] = None
        tweets.append(row)
    return {
        "issue_date": issue_date,
        "article_count": len(tweets),
        "draft_fingerprint": draft_fingerprint,
        "updated_at": now,
        "tweets": tweets,
    }


def _touch_tweets_document(path: Path, doc: Dict[str, Any]) -> None:
    doc["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(path, doc)


def _expected_article_slots(issue_dir: Path) -> List[Tuple[int, int, int | None]]:
    """metadata から、下書き1件ずつに対応する (episode_num, order_in_episode, article_id) の並びを返す。
    各エピソードは order 昇順の先頭 _MAX_ARTICLES_PER_EPISODE_FOR_X 件のみ。"""
    slots: List[Tuple[int, int, int | None]] = []
    for meta in sorted(
        _load_all_episode_metadata(issue_dir),
        key=lambda x: int(x.get("episode_num") or 0),
    ):
        ep_num = int(meta.get("episode_num") or 0)
        articles: List[Dict[str, Any]] = meta.get("articles") or []
        for art in sorted(articles, key=lambda a: int(a.get("order") or 0))[
            :_MAX_ARTICLES_PER_EPISODE_FOR_X
        ]:
            order = int(art.get("order") or 0)
            aid = art.get("id")
            slots.append((ep_num, order, int(aid) if aid is not None else None))
    return slots


def _try_load_tweets_file(
    path: Path,
    issue_date: str,
    expected_slots: List[Tuple[int, int, int | None]],
) -> Tuple[List[ArticleTweetDraft], Dict[str, Any]] | None:
    """
    tweets.json（または旧 tweets_draft.json）を読み、issue_date・件数・記事スロットが metadata と一致すれば
    (Draft リスト, ルート JSON オブジェクト) を返す。ルートはミュータブルで、そのまま保存に使う。
    """
    raw = _safe_read_json(path)
    if not isinstance(raw, dict) or raw.get("issue_date") != issue_date:
        return None
    tweets = raw.get("tweets")
    if not isinstance(tweets, list):
        return None
    try:
        ac = int(raw.get("article_count", -1))
    except (TypeError, ValueError):
        return None
    if ac != len(tweets) or ac != len(expected_slots):
        return None

    required_keys = (
        "japanese_title",
        "summary_used",
        "summary_original",
        "youtube_url",
        "tags_line",
        "tweet_text",
    )
    drafts: List[ArticleTweetDraft] = []
    slots_from_file: List[Tuple[int, int, int | None]] = []

    for row in tweets:
        if not isinstance(row, dict):
            return None
        for k in required_keys:
            if k not in row:
                return None
        try:
            ep_num = int(row["episode_num"])
            order_in_episode = int(row["order_in_episode"])
        except (KeyError, TypeError, ValueError):
            return None
        aid_raw = row.get("article_id")
        if aid_raw is None or (isinstance(aid_raw, str) and not str(aid_raw).strip()):
            article_id: int | None = None
        else:
            try:
                article_id = int(aid_raw)
            except (TypeError, ValueError):
                return None
        slots_from_file.append((ep_num, order_in_episode, article_id))

        rew = row.get("summary_rewritten", False)
        if not isinstance(rew, bool):
            rew = bool(rew)
        tweet_text = _ensure_x_post_prefix(str(row["tweet_text"] or ""))
        row["tweet_text"] = tweet_text

        drafts.append(
            ArticleTweetDraft(
                episode_num=ep_num,
                order_in_episode=order_in_episode,
                article_id=article_id,
                japanese_title=str(row["japanese_title"] or ""),
                summary_used=str(row["summary_used"] or ""),
                summary_original=str(row["summary_original"] or ""),
                summary_rewritten=rew,
                youtube_url=str(row["youtube_url"] or ""),
                tags_line=str(row["tags_line"] or ""),
                tweet_text=tweet_text,
            )
        )

    if slots_from_file != expected_slots:
        return None
    for row in tweets:
        assert isinstance(row, dict)
        _normalize_tweet_row_posting(row)
    return drafts, raw


def collect_article_tweets(issue_date: str) -> List[ArticleTweetDraft]:
    issue_dir = get_issue_dir(issue_date)
    episode_metas = _load_all_episode_metadata(issue_dir)
    if not episode_metas:
        raise FileNotFoundError(f"エピソードの metadata.json が見つかりません: {issue_dir}")

    drafts: List[ArticleTweetDraft] = []
    for meta in sorted(episode_metas, key=lambda x: int(x.get("episode_num") or 0)):
        ep_num = int(meta.get("episode_num") or 0)
        youtube = meta.get("youtube") or {}
        video_url = str(youtube.get("video_url") or "").strip()
        articles: List[Dict[str, Any]] = meta.get("articles") or []
        for art in sorted(articles, key=lambda a: int(a.get("order") or 0))[
            :_MAX_ARTICLES_PER_EPISODE_FOR_X
        ]:
            order = int(art.get("order") or 0)
            aid = art.get("id")
            title = str(art.get("japanese_title") or "").strip()
            summary_orig = str(art.get("summary_ja") or "").strip()
            rewritten = False
            summary_use = summary_orig
            if "日本" in summary_orig:
                md = _load_article_markdown(issue_dir, int(aid) if aid is not None else None)
                summary_use = _rewrite_summary_for_japan_reader(summary_orig, md, title)
                rewritten = summary_use != summary_orig

            start_sec = art.get("youtube_start_sec")
            if start_sec is None:
                start_sec = 0
            yt_url = _youtube_url_with_t(video_url, start_sec) if video_url else ""
            tags_line = _keyword_tags_line(art.get("keywords_ja"))
            tweet_text, summary_in_post = _fit_x_post(title, summary_use, yt_url, tags_line)

            drafts.append(
                ArticleTweetDraft(
                    episode_num=ep_num,
                    order_in_episode=order,
                    article_id=int(aid) if aid is not None else None,
                    japanese_title=title,
                    summary_used=summary_in_post,
                    summary_original=summary_orig,
                    summary_rewritten=rewritten,
                    youtube_url=yt_url,
                    tags_line=tags_line,
                    tweet_text=tweet_text,
                )
            )
    return drafts


def _post_with_retries(text: str) -> Dict[str, Any]:
    last_err: RuntimeError | None = None
    for attempt in range(POST_ATTEMPTS_MAX):
        try:
            human_delay(0.8, 2.5)
            result = post_tweet_via_browser(text)
            tid = str(result.get("tweet_id") or "").strip()
            url = str(result.get("tweet_url") or "").strip()
            if not tid or not url:
                raise RuntimeError(f"投稿結果が不完全です: {result}")
            return {"data": {"id": tid}, "tweet_url": url}
        except RuntimeError as e:
            last_err = e
            print(f"    [失敗] 試行 {attempt + 1}/{POST_ATTEMPTS_MAX}: {e}")
            if attempt < POST_ATTEMPTS_MAX - 1:
                wait = 2**attempt
                print(f"    {wait} 秒後にリトライします…")
                time.sleep(wait)
    assert last_err is not None
    raise last_err


def run_posting(
    issue_date: str,
    *,
    dry_run: bool,
    interval_sec: int | None,
    reset_progress: bool,
) -> None:
    issue_dir = get_issue_dir(issue_date)
    share_dir = issue_dir / "share"
    share_dir.mkdir(parents=True, exist_ok=True)
    tweets_path = share_dir / TWEETS_JSON_NAME
    legacy_path = share_dir / LEGACY_TWEETS_JSON_NAME
    load_path = tweets_path if tweets_path.exists() else legacy_path

    if not _load_all_episode_metadata(issue_dir):
        raise FileNotFoundError(
            f"エピソードの metadata.json が見つかりません: {issue_dir}"
        )
    expected_slots = _expected_article_slots(issue_dir)
    if not expected_slots:
        raise FileNotFoundError(
            f"エピソード metadata に記事エントリがありません: {issue_dir}"
        )

    if reset_progress and tweets_path.exists():
        doc_reset = _safe_read_json(tweets_path)
        if isinstance(doc_reset, dict):
            for row in doc_reset.get("tweets") or []:
                if isinstance(row, dict):
                    row["post_completed"] = False
                    row["tweet_id"] = None
                    row["tweet_url"] = None
                    row["posted_at"] = None
            doc_reset.pop("last_failed_seq", None)
            doc_reset.pop("last_error", None)
            _touch_tweets_document(tweets_path, doc_reset)
        print(
            f"[X] {tweets_path.name} 内の投稿済みフラグ・tweet_id / tweet_url / posted_at をクリアしました。"
        )

    drafts: List[ArticleTweetDraft] | None = None
    tweets_doc: Dict[str, Any] | None = None

    if load_path.exists():
        loaded = _try_load_tweets_file(load_path, issue_date, expected_slots)
        if loaded is not None:
            drafts, tweets_doc = loaded
            print(
                f"[X] 既存の {load_path.name} を使用します（metadata の記事構成と一致。Gemini・本文再生成はスキップ）。"
            )
            if load_path == legacy_path and not tweets_path.exists():
                _touch_tweets_document(tweets_path, tweets_doc)
                print(f"[X] {LEGACY_TWEETS_JSON_NAME} の内容を {TWEETS_JSON_NAME} にコピーしました。")

    if drafts is None or tweets_doc is None:
        drafts = collect_article_tweets(issue_date)
        fp_new = _draft_fingerprint(drafts)
        existing = _safe_read_json(tweets_path) or _safe_read_json(legacy_path)
        if isinstance(existing, dict) and existing.get("issue_date") == issue_date:
            had_done = _completed_seqs_from_tweets_doc(existing)
            old_fp = str(existing.get("draft_fingerprint") or "")
            if had_done and old_fp and old_fp != fp_new:
                print(
                    "tweets の内容指紋が metadata から再生成した下書きと異なり、投稿済み行があります。\n"
                    f"{TWEETS_JSON_NAME} を退避・削除するか、--reset-progress で投稿状態をクリアしてから再実行してください。",
                    file=sys.stderr,
                )
                raise SystemExit(1)
        tweets_doc = _build_tweets_document(issue_date, drafts, fp_new)
        _touch_tweets_document(tweets_path, tweets_doc)
        print(f"[X] {tweets_path.name} を保存しました（記事数 {len(drafts)}）")
        _write_share_note_md(share_dir, issue_dir, issue_date)
        print(f"[X] {NOTE_MD_NAME} を保存しました（他プラットフォーム向け紹介文）。")

    assert tweets_doc is not None
    fp = _draft_fingerprint(drafts)
    stored_fp = str(tweets_doc.get("draft_fingerprint") or "")
    completed = _completed_seqs_from_tweets_doc(tweets_doc)
    if completed and stored_fp and stored_fp != fp:
        print(
            f"{tweets_path.name} の draft_fingerprint と現在の tweet_text から計算した指紋が一致しません（投稿済みあり）。"
            "ファイルを手動で整合させるか --reset-progress を使用してください。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    if not stored_fp:
        tweets_doc["draft_fingerprint"] = fp
        _touch_tweets_document(tweets_path, tweets_doc)

    if dry_run:
        tw_list = tweets_doc.get("tweets") or []
        for i, d in enumerate(drafts, start=1):
            row = tw_list[i - 1] if i <= len(tw_list) and isinstance(tw_list[i - 1], dict) else {}
            st = "（投稿済み）" if row.get("post_completed") else "（未投稿）"
            print(
                f"\n--- [{i}/{len(drafts)}] ep{d.episode_num:02d} order{d.order_in_episode} id={d.article_id} {st}---"
            )
            print(d.tweet_text)
        print(f"\n[ドライラン] 投稿済みシーケンス: {sorted(completed)}")
        print("[ドライラン] ブラウザ投稿は行っていません。")
        return

    if not ensure_x_session(timeout_sec=600.0):
        raise SystemExit(
            "X のログインが完了していません。"
            " python x_browser_post.py --login で1回ログインしてから再実行してください。"
        )

    tweets_list = tweets_doc.setdefault("tweets", [])
    if not isinstance(tweets_list, list):
        raise SystemExit(1)

    for seq, draft in enumerate(drafts, start=1):
        if seq in completed:
            print(f"\n[X] 投稿 {seq}/{len(drafts)} … 既に成功済みのためスキップ (article_id={draft.article_id})")
            continue

        print(f"\n[X] 投稿 {seq}/{len(drafts)} … (article_id={draft.article_id}) [同一タブ]")
        try:
            data = _post_with_retries(draft.tweet_text)
        except RuntimeError as e:
            print(f"投稿に {POST_ATTEMPTS_MAX} 回失敗したため中断します: {e}", file=sys.stderr)
            tweets_doc["last_failed_seq"] = seq
            tweets_doc["last_error"] = str(e)
            _touch_tweets_document(tweets_path, tweets_doc)
            raise SystemExit(1) from e

        tid = (data.get("data") or {}).get("id") or ""
        if not tid:
            print(f"応答に tweet id がありません: {data}", file=sys.stderr)
            raise SystemExit(1)
        tweet_url = str(data.get("tweet_url") or f"https://x.com/i/web/status/{tid}")
        posted_at = datetime.now(timezone.utc).isoformat()
        row = tweets_list[seq - 1]
        if not isinstance(row, dict):
            print(f"tweets[{seq - 1}] がオブジェクトではありません。", file=sys.stderr)
            raise SystemExit(1)
        row["post_completed"] = True
        row["tweet_id"] = tid
        row["tweet_url"] = tweet_url
        row["posted_at"] = posted_at
        tweets_doc.pop("last_failed_seq", None)
        tweets_doc.pop("last_error", None)
        _touch_tweets_document(tweets_path, tweets_doc)
        print(f"    OK: {tweet_url}")
        print(f"    → {tweets_path.name} を更新しました。")

        completed = _completed_seqs_from_tweets_doc(tweets_doc)

        if seq < len(drafts):
            wait = interval_sec if interval_sec is not None else post_interval_seconds()
            if wait > 0:
                print(f"    次の投稿まで {wait} 秒待機（{wait // 60} 分 {wait % 60} 秒）…")
                time.sleep(wait)

    print(f"\n[X] 全 {len(drafts)} 件の処理が完了しました。")


def run_test_post(text: str, *, delete_after: bool = True) -> None:
    """テスト投稿を1件行い、成功後に削除する（接続確認用）。"""
    if not ensure_x_session(timeout_sec=600.0):
        raise SystemExit(
            "X のログインが完了していません。"
            " python x_browser_post.py --login で1回ログインしてから再実行してください。"
        )
    print(f"[X テスト] 投稿文 ({len(text)} 字):\n{text}\n")
    human_delay(1.0, 2.0)
    result = post_tweet_via_browser(text)
    tweet_url = str(result.get("tweet_url") or "")
    tweet_id = str(result.get("tweet_id") or "")
    print(f"[X テスト] 投稿成功: {tweet_url}")
    if delete_after and tweet_url:
        human_delay(2.0, 4.0)
        delete_tweet_via_browser(tweet_url)
        print(f"[X テスト] 削除完了: {tweet_url}")
    elif tweet_id:
        print(f"[X テスト] tweet_id={tweet_id}（削除スキップ）")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="各エピソード先頭3記事の X 投稿文の生成・ブラウザ自動投稿（中断再開対応）",
    )
    parser.add_argument("--issue", help="出版日 (YYYY-MM-DD)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="ブラウザへは投稿しない。tweets.json が再利用される場合は Gemini もスキップする",
    )
    parser.add_argument(
        "--interval-sec",
        type=int,
        default=None,
        help=f"連続投稿の待機秒数（未指定時は {POST_INTERVAL_SEC_MIN}〜{POST_INTERVAL_SEC_MAX} 秒のランダム）",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help=f"{TWEETS_JSON_NAME} 内の post_completed / tweet_id / tweet_url / posted_at をすべてクリアする",
    )
    parser.add_argument(
        "--test-post",
        metavar="TEXT",
        help="テスト投稿を1件行い、成功後に削除して終了（--issue 不要）",
    )
    args = parser.parse_args()

    if args.test_post:
        run_test_post(args.test_post)
        return

    if not args.issue:
        parser.error("--issue または --test-post が必要です")

    run_posting(
        args.issue,
        dry_run=args.dry_run,
        interval_sec=args.interval_sec,
        reset_progress=args.reset_progress,
    )


if __name__ == "__main__":
    main()

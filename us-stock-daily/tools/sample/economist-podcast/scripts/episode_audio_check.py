"""Episode audio file completeness checks."""
import json
from pathlib import Path


def read_episode_metadata(ep_dir: Path) -> dict:
    p = ep_dir / "metadata.json"
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def episode_article_count(metadata: dict, ep_data: dict | None = None) -> int:
    count = metadata.get("article_count")
    if count:
        return int(count)
    articles = metadata.get("articles")
    if isinstance(articles, list) and articles:
        return len(articles)
    if ep_data:
        ac = ep_data.get("article_count")
        if ac:
            return int(ac)
    return 0


def list_missing_episode_audio(ep_dir: Path, article_count: int) -> list[str]:
    missing: list[str] = []
    ad = ep_dir / "audio"
    expected = ["intro"] + [f"{i:02d}" for i in range(1, article_count + 1)] + ["closing"]
    for stem in expected:
        mp3 = ad / f"{stem}.mp3"
        try:
            if not mp3.is_file() or mp3.stat().st_size == 0:
                missing.append(stem)
        except OSError:
            missing.append(stem)
    return missing


def episode_audio_missing(ep_dir: Path, article_count: int | None = None) -> list[str]:
    if article_count is None:
        metadata = read_episode_metadata(ep_dir)
        article_count = episode_article_count(metadata)
    return list_missing_episode_audio(ep_dir, article_count)


def episode_audio_is_complete(ep_dir: Path, article_count: int | None = None) -> bool:
    return len(episode_audio_missing(ep_dir, article_count)) == 0
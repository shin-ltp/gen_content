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
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
TOOL = Path(__file__).resolve().parent
PY = sys.executable
CORNER_ORDER = ("opening", "market", "themes", "news", "events", "ending")
OPENING_NARRATION_ID = "S00-intro"
HELPER_OUTRO_ID = "END-outro"
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


def write_json_bom(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_bytes(b"\xef\xbb\xbf" + data.encode("utf-8"))


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


def validate_script(cfg: dict, script: dict) -> dict[str, str]:
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
    missing = sorted(expected - set(result))
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
    return result


def fixed_segment(slot: dict, kind: str) -> dict:
    segment = {
        "order": slot["order"],
        "id": slot["id"],
        "slide": slot["slide"],
    }
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
            "type": "tts",
            "voice": slot["voice"],
            "title": "Ending fixed narration",
            "text": slot["text"],
        }
    )
    return segment


def build_segment_map(cfg: dict, narration: dict[str, str]) -> dict:
    corners = {corner["id"]: corner for corner in cfg["corners"]}
    segments = [fixed_segment(slot, corners[slot["corner"]]["kind"])
                for slot in cfg["fixed_slots"]]
    for block in sorted(cfg["blocks"], key=lambda item: item["order"]):
        kind = corners[block["corner"]]["kind"]
        if kind == "ending":
            if block["id"] == HELPER_OUTRO_ID:
                if block.get("source") == "assets/audio/fixed/ending.wav":
                    segments.append(
                        {
                            "order": block["order"],
                            "id": block["id"],
                            "slide": "",
                            "type": "external",
                            "title": block.get("title", "エンディングあいさつ"),
                            "asset_hint": block["source"],
                        }
                    )
                    continue
                segments.append(
                    {
                        "order": block["order"],
                        "id": block["id"],
                        "slide": "",
                        "type": "tts",
                        "voice": block.get("voice", cfg["voices"]["default"]),
                        "title": block.get("title", "エンディングあいさつ"),
                        "cue": "",
                        "source": block.get("source", ""),
                        "text": narration[block["id"]],
                    }
                )
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
    if len(slots) != 2:
        raise PipelineError("exactly two fixed slots are required")
    kinds = {"opening": 0, "ending": 0}
    for slot in slots:
        for key in ("id", "corner", "order", "slide", "voice", "source"):
            if key not in slot:
                raise PipelineError(f"fixed slot is missing {key}: {slot.get('id', '?')}")
        if slot["corner"] not in corner_by_id:
            raise PipelineError(f"unknown fixed-slot corner: {slot['corner']}")
        kind = corner_by_id[slot["corner"]]["kind"]
        if kind not in kinds:
            raise PipelineError("fixed slots must belong to opening/ending corners")
        kinds[kind] += 1
        if slot["source"] not in ("assets/audio/fixed/opening.wav", "assets/audio/fixed/ending.wav"):
            raise PipelineError(f"invalid fixed source: {slot['source']}")
    if any(count != 1 for count in kinds.values()):
        raise PipelineError("opening and ending each require one fixed slot")
    ending_corner_id = next(item["id"] for item in corners if item["kind"] == "ending")
    helper = next((block for block in blocks if block.get("id") == HELPER_OUTRO_ID), None)
    if helper is not None and helper["corner"] != ending_corner_id:
        raise PipelineError(f"{HELPER_OUTRO_ID} must belong to the ending corner")
    ending = next(slot for slot in slots if corner_by_id[slot["corner"]]["kind"] == "ending")
    if ending["id"] != "END-disclaimer":
        raise PipelineError("ending slot id must be END-disclaimer")
    if ending["source"] != "assets/audio/fixed/ending.wav":
        raise PipelineError("ending slot source must be the reusable ending wav")
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
        haiku_id = "S01-haiku"
        blocks.insert(1, {
            "id": haiku_id, "corner": "OP", "order": 1, "slide": "s1",
            "voice": "kyoujyu", "title": "Opening haiku", "cue": "", "source": "opening haiku",
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
                    "voice": "kyoujyu", "source": "assets/audio/fixed/ending.wav",
                    "text": "免責事項を含む固定エンディング",
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
        write_json_bom(cfg_path, cfg)
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
    write_json_bom(script_file, script)
    print(f"[scaffold] {'kept' if existing_cfg else 'created'} {cfg_path}")
    print(f"[scaffold] wrote {script_file} ({len(script_blocks)} blocks)")


def build_map_command(cfg: dict, date: str) -> dict:
    return {
        "episode": date,
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
        expected_ids = [
            item["id"] for item in expected if item["type"] == "tts"
            and item["id"] != HELPER_OUTRO_ID
        ]
        if (ROOT / "assets/audio/fixed/opening.wav").is_file():
            expected_ids.insert(0, OPENING_NARRATION_ID)
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


def run_checked(args: list[str], cwd: Path | None = None) -> None:
    print("[run] " + " ".join(args))
    result = subprocess.run(args, cwd=cwd)
    if result.returncode != 0:
        raise PipelineError(f"command failed ({result.returncode}): {' '.join(args)}")


def run_pipeline(date: str, render: bool) -> None:
    cfg = read_json(config_path(date))
    validate_config(cfg, date)
    narration = validate_script(cfg, read_json(script_path(date)))
    write_json_bom(map_path(date), build_segment_map(cfg, narration))
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
    parser.add_argument("command", choices=("validate", "build-map", "check-artifacts", "commands", "run", "scaffold"))
    parser.add_argument("--date", required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--from-map", action="store_true", help="scaffold script.json from an existing map")
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
            write_json_bom(map_path(date), build_segment_map(cfg, validate_script(cfg, read_json(script_path(date)))))
            print(f"[done] {map_path(date)}")
        elif args.command == "check-artifacts":
            errors = artifact_errors(date)
            if errors:
                raise PipelineError("artifact validation failed:\n- " + "\n- ".join(errors))
            print("[ok] artifacts match episode contract")
        elif args.command == "commands":
            print(json.dumps(build_map_command(cfg, date), ensure_ascii=False, indent=2))
        elif args.command == "run":
            run_pipeline(date, args.render)
        return 0
    except PipelineError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("[interrupted]", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

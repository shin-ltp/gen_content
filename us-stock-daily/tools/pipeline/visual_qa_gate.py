"""Post-render visual gate: every image/layout check that belongs right after
visual.html is generated (2026-09-25 QA restructure, extracted from final_qa).

Catching a bad asset or a broken s1 layout HERE costs one asset re-fetch;
catching it after Remotion costs a full re-render (9/24 s1 layout incident).
prepare_visual_assets.py auto-runs this gate after render_visual succeeds.

Checks (all before any TTS/render budget is committed to visuals):
  1. mechanical: visual_asset_refs / visual_image_meta / preview_list_s1 /
     visual_aspect_ratio   (moved verbatim from final_qa.run_mechanical)
  2. real-DOM audit via node visual_dom_audit.mjs (slide rect, broken img,
     horizontal escape, portrait circle, carousel/news state switching)
  3. vision contact sheet per theme (moved from final_qa.run_visual_contact_sheet).
     Real rejects trigger REACQUIRE: the page's meta row is marked missing and
     the asset file is unlinked so the next prepare_visual_assets run re-resolves
     it through the normal asset->shared DB->SearXNG->imagegen order.

Usage:
  python visual_qa_gate.py 2026-09-25 [--skip-vision]
Exit codes: 0 = pass, 2 = fail (fix assets and re-run prepare_visual_assets),
3 = environment error (node/vision unavailable -> advisory, pipeline continues).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = sys.stdout.__class__(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = sys.stderr.__class__(sys.stderr.buffer, encoding="utf-8", errors="replace")

_TOOLS_DIR = Path(__file__).resolve().parent
_US_ROOT = _TOOLS_DIR.parents[1]
_REPO_ROOT = _US_ROOT.parent
sys.path.insert(0, str(_TOOLS_DIR))


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def run_mechanical_visual(date: str) -> list[dict]:
    """The four mechanical visual checks, moved from final_qa verbatim."""
    issue = _US_ROOT / "daily-output" / date
    checks: list[dict] = []

    def _add(name: str, passed: bool, output: str) -> None:
        checks.append({"check": name, "passed": passed, "output": output[-2000:]})
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
        if not passed:
            for line in output.strip().splitlines()[-5:]:
                print(f"         {line}")

    visual_data = issue / "production" / "visual-data.json"

    # Visual references are not just a render concern: a stale path can become
    # a blank frame even when the HTML file itself exists.
    if visual_data.is_file():
        data = json.loads(visual_data.read_text(encoding="utf-8-sig"))
        missing_imgs = []
        for slide_id, html in sorted(data.get("slices", {}).items()):
            for src in re.findall(
                    r"<img[^>]+src=[\"']([^\"']+)[\"']", html, re.I):
                if "logo.png" in src or src.startswith("data:"):
                    continue
                p = issue / src
                if not p.is_file() or p.stat().st_size < 10_000:
                    missing_imgs.append(f"{slide_id}: {src}")
        passed = not missing_imgs
        out = "all referenced visual assets exist" if passed else "\n".join(missing_imgs)
        _add("visual_asset_refs", passed, out)

    # Portrait metadata must exist for every B page image and stay in sync
    # with the slice HTML class (portrait circle vs full-height photo).
    meta_path = issue / "assets" / "image-meta.json"
    brief_path = issue / "production" / "visual-brief.md"
    if meta_path.is_file() and visual_data.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        data = json.loads(visual_data.read_text(encoding="utf-8-sig"))
        all_html = "\n".join(data.get("slices", {}).values())
        errors: list[str] = []
        if brief_path.is_file():
            for line in brief_path.read_text(encoding="utf-8-sig").splitlines():
                if not line.startswith("| s"):
                    continue
                cols = [c.strip() for c in line.strip("|").split("|")]
                if len(cols) >= 7 and re.fullmatch(r"B\d+-p\d+", cols[1]):
                    if cols[1] not in meta:
                        errors.append(f"{cols[1]}: no image-meta entry")
        for block, info in sorted(meta.items()):
            asset = info.get("asset", "")
            if not (issue / asset).is_file() or (issue / asset).stat().st_size < 10_000:
                errors.append(f"{block}: meta asset missing: {asset}")
            if not info.get("keyword"):
                errors.append(f"{block}: keyword not recorded")
            if not isinstance(info.get("portrait"), bool):
                errors.append(f"{block}: portrait flag not boolean")
            plain = f'<div class="photo-frame"><img src="{asset}"'
            circle = f'<div class="photo-frame portrait"><img src="{asset}"'
            if info.get("portrait") and plain in all_html and circle not in all_html:
                errors.append(f"{block}: portrait image rendered without circle class")
            if not info.get("portrait") and circle in all_html:
                errors.append(f"{block}: non-portrait image rendered as circle")
        passed = not errors
        out = "image metadata and portrait styles consistent" if passed else "\n".join(errors)
        _add("visual_image_meta", passed, out)

    # Preview-v2 (2026-09-19+): s1 is the single preview list page. It must
    # show only titles, cycle every theme's p1 photo, and omit summaries.
    if str(date) >= "2026-09-19" and visual_data.is_file():
        data = json.loads(visual_data.read_text(encoding="utf-8-sig"))
        brief_json = issue / "production" / "visual-brief.json"
        preview = {}
        themes = []
        if brief_json.is_file():
            brief = json.loads(brief_json.read_text(encoding="utf-8-sig"))
            preview = brief.get("preview", {})
            themes = brief.get("themes", [])
        count = len(preview.get("items", []))
        html = data.get("slices", {}).get("s1", "")
        errors = []
        if count and not html:
            errors.append("s1: preview list page missing")
        else:
            title_items = re.findall(
                r'<div class="topic-item[^"]*"[^>]*><div class="topic-number">\d+</div>'
                r'<div class="topic-title">([^<]*)</div></div>',
                html,
            )
            if count and len(title_items) != count:
                errors.append(
                    f"s1: expected {count} title items, found {len(title_items)}"
                )
            if count and [re.sub(r"\s+", "", item) for item in title_items] != [
                re.sub(r"\s+", "", str(preview_item.get("title", "")))
                for preview_item in preview.get("items", [])
            ]:
                errors.append(
                    "s1: preview title order/content does not match visual-brief.json"
                )
            summaries = [t.get("summary", "") for t in themes]
            for summary in summaries:
                clean = re.sub(r"\[pause[^\]]*\]", "", summary)
                clean = re.sub(r"\s+", "", clean)
                if clean and clean[:10] in re.sub(r"\s+", "", html):
                    errors.append("s1: summary text must not be rendered on screen")
                    break
            for i in range(1, count + 1):
                if f"assets/b{i}-1.png" not in html:
                    errors.append(f"s1: missing theme photo assets/b{i}-1.png")
        passed = not errors
        out = "s1 preview list shows titles only with every theme photo" \
            if passed else "\n".join(errors)
        _add("preview_list_s1", passed, out)

    # Aspect gate (2026-09-24): left-column images must already match the
    # display ratio (~0.71 portrait) or the 1:1 portrait circle; otherwise
    # object-fit cover silently amputates subjects or CSS stretches them.
    if meta_path.is_file() and visual_data.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
        errors = []
        for block, info in sorted(meta.items()):
            asset = issue / info.get("asset", "")
            if not info.get("asset") or not asset.is_file():
                continue
            if not str(block).startswith("B"):
                continue
            try:
                from PIL import Image
                with Image.open(asset) as im:
                    ratio = im.width / max(im.height, 1)
            except Exception:  # noqa: BLE001 - unreadable file fails anyway
                errors.append(f"{block}: unreadable image")
                continue
            want = 1.0 if info.get("portrait") else 768 / 1080
            if abs(ratio - want) > 0.12:
                errors.append(
                    f"{block}: display ratio {ratio:.2f} far from target "
                    f"{want:.2f} (subject will be cropped/stretched)"
                )
        passed = not errors
        out = "all B images match the display aspect" if passed else "\n".join(errors)
        _add("visual_aspect_ratio", passed, out)

    return checks


def run_dom_audit(date: str) -> dict:
    """Real-Chromium DOM audit of the issue visual.html (node subprocess)."""
    import shutil

    script = _TOOLS_DIR / "visual_dom_audit.mjs"
    node = shutil.which("node") or "node"
    try:
        r = subprocess.run(
            [node, str(script), date], cwd=str(_REPO_ROOT),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300)
    except subprocess.TimeoutExpired:
        return {"available": False, "failures": [], "notes": [],
                "error": "dom audit timed out after 300s"}
    except FileNotFoundError as e:
        return {"available": False, "failures": [], "notes": [],
                "error": f"node not found: {e}"}
    try:
        data = json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"available": False, "failures": [], "notes": [],
                "error": f"bad audit output: {(r.stderr or r.stdout)[-300:]}"}
    return {"available": True,
            "failures": data.get("failures", []),
            "notes": data.get("notes", [])}


def run_vision_sheet(date: str) -> dict | None:
    """Per-theme vision contact sheet review (moved from final_qa).

    Returns {"problems": [{block, reason}], "notes": [...]} or None when
    unavailable (skips are advisory; only explicit problems matter).
    """
    import text_llm

    issue = _US_ROOT / "daily-output" / date
    meta_path = issue / "assets" / "image-meta.json"
    brief_path = issue / "production" / "visual-brief.json"
    if not meta_path.is_file() or not brief_path.is_file():
        return None
    if not text_llm.is_configured():
        print("  [SKIP] visual_contact_sheet (text_llm not configured)")
        return {"problems": [], "notes": ["skipped: no LLM"]}
    import tempfile

    from PIL import Image, ImageDraw

    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    brief = json.loads(brief_path.read_text(encoding="utf-8-sig"))
    theme_titles = {}
    for theme in brief.get("themes", []):
        theme_titles[int(theme.get("number", 0))] = str(
            theme.get("title", ""))[:120]
    tile = 480
    tmpdir = Path(tempfile.mkdtemp(prefix="visual-gate-"))
    sheets: list[Path] = []
    labels: list[str] = []
    for number in sorted(theme_titles):
        blocks = sorted(
            (b for b in meta if b.startswith(f"B{number}-p")),
            key=lambda b: int(b.split("-p")[1]),
        )
        files = [issue / meta[b]["asset"] for b in blocks]
        files = [f for f in files if f.is_file()]
        if not files:
            continue
        cols = 4
        rows = (len(files) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * (tile + 8) + 8,
                                  rows * (tile + 8) + 8), (20, 23, 31))
        draw = ImageDraw.Draw(sheet)
        for idx, f in enumerate(files):
            with Image.open(f) as im:
                im.thumbnail((tile, tile))
                x = 8 + (idx % cols) * (tile + 8)
                y = 8 + (idx // cols) * (tile + 8)
                sheet.paste(im, (x, y))
                draw.text((x + 4, y + 4),
                          blocks[idx].replace("B", ""), fill=(255, 220, 120))
        out = tmpdir / f"theme{number}.png"
        sheet.save(out)
        sheets.append(out)
        labels.append(f"{number}: {theme_titles[number]}")
    if not sheets:
        return None
    problems: list[dict] = []
    notes_total: list[str] = []
    errors: list[str] = []
    for sheet, label in zip(sheets, labels):
        number = int(label.split(":", 1)[0])
        blocks = sorted(
            (b for b in meta if b.startswith(f"B{number}-p")),
            key=lambda b: int(b.split("-p")[1]),
        )
        prompt = "\n".join([
            f"テーマ「{label}」の各ページ配图（左上の数字 = ページ番号）を審査してください。",
            "各マスのページ状態: " + ", ".join(
                f"{blocks[i].split('-p')[1]}="
                f"{'生成品' if meta[blocks[i]].get('state') == 'generated' else '実写写真'}"
                for i in range(len(blocks))
            ) + "。",
            "各マスの取得キーワード（=その段落の期待主体）: " + ", ".join(
                f"{blocks[i].split('-p')[1]}={meta[blocks[i]].get('keyword', '?')}"
                for i in range(len(blocks))
            ) + "。",
            "判定は各マスに付した取得キーワードを正とする。テーマ名や他ページのキーワードと一致しないことを",
            "理由にした reject は無効。",
            "",
            "reject 条件（実写写真マス）: 主題と無関係/誤った実体（別会社・別人・他社のロゴや看板が主役）、",
            "記事動画のスクリーンショットやテロップ・字幕が焼き込まれた画像、透かし、",
            "極端に低品質・ピントぼけ・主体が意味不明に切れている。",
            "reject 条件（生成品マス）: 主題と無関係、幼稚で番組に使えない品質、画像内の日本語/英語テキストが乱れている。",
            "生成品マスは編集イラストであること自体は契約上許可されており、イラストという理由では reject しない。",
            "fab・工場・研究施設・データセンターの外観写真は、ロゴや看板が矛盾する確証がない限り、",
            "本社ビル風の外観という理由だけでは reject しない。",
            "",
            "注意: 同じ写真が複数ページに再利用されているのは正常。顔人物の同一性は確証があるときのみ reject し、",
            "縮小による判別困難を理由に reject しない。問題のあるページのみ page_rejects に列挙。",
            "不確実な推測（〜の可能性がある、判別が難しい、品質は微妙だが使用可能）は page_rejects に入れず、",
            "notes に 1 行で記録する。page_rejects には明確な契約違反のみ列挙する。",
        ])
        schema = {
            "type": "object",
            "required": ["page_rejects"],
            "properties": {
                "page_rejects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["page", "reason"],
                        "properties": {
                            "page": {"type": "integer"},
                            "reason": {"type": "string"},
                        },
                    },
                },
                "notes": {"type": "array", "items": {"type": "string"}},
            },
        }
        try:
            result = text_llm.generate_json_with_images(
                prompt, [sheet], "pro",
                schema_hint=json.dumps(schema, ensure_ascii=False),
                max_retries=1,
            )
        except Exception as e:  # noqa: BLE001 - advisory on call failure
            errors.append(f"theme{number}: vision call failed: {str(e)[:120]}")
            continue
        notes = [str(note)[:200] for note in (result or {}).get("notes", [])
                 if str(note).strip()]
        notes_total.extend(f"theme{number}: {note}" for note in notes)
        for item in (result or {}).get("page_rejects", []):
            page = item.get("page")
            if isinstance(page, int) and 1 <= page <= len(blocks):
                reason = str(item.get("reason", ""))[:160]
                compacted = "".join(reason.split()).lower()
                # Vision responses sometimes put an all-clear verdict in the
                # reject field; that caused false-positive loops (9/24-9/25).
                affirmative = (
                    compacted.startswith("問題なし")
                    or compacted.startswith("問題は見当た")
                    or compacted.startswith("問題は確認でき")
                    or compacted.startswith("特に問題なし")
                    or compacted.startswith("特に問題は")
                    or compacted in {"なし", "無し", "問題なし。"}
                )
                if affirmative:
                    notes_total.append(f"theme{number}: ignored all-clear reject: {reason}")
                    continue
                if any(marker in compacted for marker in
                       ("可能性が高い", "可能性がある", "判別が難しい", "確証がない")):
                    notes_total.append(f"theme{number}: ambiguous note: {reason}")
                    continue
                problems.append({"block": blocks[page - 1], "reason": reason})
    return {"problems": problems, "notes": notes_total,
            "call_errors": errors, "themes": len(sheets)}


def reacquire(date: str, problems: list[dict]) -> list[str]:
    """Mark rejected pages missing so the next prepare run re-resolves them."""
    issue = _US_ROOT / "daily-output" / date
    meta_path = issue / "assets" / "image-meta.json"
    meta = _read_json(meta_path)
    if meta is None:
        return []
    actions: list[str] = []
    changed = False
    for problem in problems:
        block = problem.get("block", "")
        info = meta.get(block)
        if not info:
            continue
        asset = issue / info.get("asset", "")
        if info.get("state") != "missing":
            info["state"] = "missing"
            info["rejected_reason"] = problem.get("reason", "")
            changed = True
        if asset.is_file():
            try:
                asset.unlink()
                actions.append(f"{block}: unlinked {info.get('asset')}")
            except OSError as e:
                actions.append(f"{block}: unlink failed: {e}")
        else:
            actions.append(f"{block}: asset already absent")
    if changed:
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8")
    return actions


def _history_path(date: str) -> Path:
    return _US_ROOT / "daily-output" / date / "review" / "visual-gate-history.json"


# Max REACQUIRE cycles per date. Vision verdicts oscillate across runs
# (9/24-9/25 precedent) and can flag a new block every pass, so a per-block
# cap alone never converges and keeps unlinking good cached assets.
MAX_REACQUIRE_CYCLES = 2


def split_rejects(date: str, problems: list[dict]) -> tuple[list[dict], list[dict]]:
    """Cap the vision reject loop per block (max 1 re-acquire) and per date.

    Vision verdicts oscillate across runs (9/24-9/25 precedent), and a
    re-acquired block often resolves to the same shared-DB image. Without a
    cap the prepare<->gate loop unlinks good cached assets forever. First
    reject of a block (while the date still has cycle budget) -> REACQUIRE;
    any repeat reject, or anything after the budget is spent -> advisory
    only, asset stays.
    """
    path = _history_path(date)
    history = _read_json(path) or {}
    cycles = int(history.get("_cycles", 0))
    budget_left = cycles < MAX_REACQUIRE_CYCLES
    fresh: list[dict] = []
    repeat: list[dict] = []
    for problem in problems:
        block = str(problem.get("block", ""))
        if not budget_left or int(history.get(block, 0)) >= 1:
            repeat.append(problem)
        else:
            history[block] = int(history.get(block, 0)) + 1
            fresh.append(problem)
    if fresh:
        history["_cycles"] = cycles + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return fresh, repeat


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-render visual gate")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--skip-vision", action="store_true",
                        help="mechanical + real-DOM checks only (cheap recheck)")
    args = parser.parse_args()

    date = args.issue_date
    issue = _US_ROOT / "daily-output" / date
    if not issue.is_dir():
        print(f"[error] issue directory not found: {issue}")
        return 3

    print(f"[visual-gate] {date}")
    report: dict = {"date": date,
                    "generated_at": datetime.now().isoformat(timespec="seconds")}

    print("  --- mechanical visual checks ---")
    checks = run_mechanical_visual(date)
    report["mechanical"] = checks
    mech_failed = [c for c in checks if not c["passed"]]

    print("  --- real-DOM audit (visual.html) ---")
    dom = run_dom_audit(date)
    report["dom"] = dom
    if not dom["available"]:
        # Node/browser unavailable: do not block the pipeline; final QA frame
        # sampling still catches fully blank slides after render.
        print(f"  [SKIP] dom audit: {dom.get('error', 'unavailable')}")
        report["dom"]["advisory"] = True
    else:
        icon = "PASS" if not dom["failures"] else "FAIL"
        print(f"  [{icon}] dom_audit ({len(dom['failures'])} failures, "
              f"{len(dom['notes'])} notes)")
        for f in dom["failures"][:10]:
            print(f"         {f[:200]}")
        for n in dom["notes"][:10]:
            print(f"         note: {n[:160]}")

    vision = None
    if not args.skip_vision:
        print("  --- vision contact sheet ---")
        try:
            vision = run_vision_sheet(date)
        except Exception as e:  # noqa: BLE001 - env issues stay advisory
            print(f"  [SKIP] vision sheet failed: {str(e)[:160]}")
            vision = {"problems": [], "notes": [f"call failed: {e}"]}
        report["vision"] = vision
        if vision is None:
            print("  [SKIP] vision sheet (assets or brief missing)")
        else:
            probs = vision.get("problems", [])
            print(f"  [{'PASS' if not probs else 'FAIL'}] visual_contact_sheet "
                  f"({len(probs)} reject(s))")
            for note in vision.get("notes", [])[:8]:
                print(f"         note: {str(note)[:160]}")

    report_path = issue / "review" / "visual-gate.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(f"[visual-gate] report -> {report_path}")

    failed = bool(mech_failed) or bool(dom.get("failures"))
    if failed:
        print("[visual-gate] FAILED: fix assets/references, then re-run "
              "prepare_visual_assets.py (render + this gate rerun automatically)")
        return 2
    if vision is not None and vision.get("problems"):
        fresh, repeat = split_rejects(date, vision["problems"])
        if fresh:
            actions = reacquire(date, fresh)
            for line in actions:
                print(f"[visual-gate] REACQUIRE {line}")
            for problem in fresh:
                if not any(problem.get("block", "") in a for a in actions):
                    print(f"[visual-gate] REACQUIRE {problem.get('block')}: "
                          f"{problem.get('reason')} (manual asset swap needed)")
            print("[visual-gate] vision rejects -> re-run "
                  "prepare_visual_assets.py to re-acquire")
            return 2
        print("[visual-gate] advisory: repeat vision rejects after "
              "re-acquisition (verdict oscillation, 9/24-9/25 precedent) -- "
              "assets kept:")
        for problem in repeat:
            print(f"         {problem.get('block')}: {problem.get('reason', '')[:120]}")
    print("[visual-gate] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

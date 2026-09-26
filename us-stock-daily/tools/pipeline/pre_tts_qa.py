"""Pre-TTS narration gate: every text check that must run BEFORE synthesis.

Restructured out of final_qa (2026-09-25): wording/disclaimer/simplified-char
defects found after TTS force a resynth + full re-render loop (9/24 柴油,
9/25 wording). This gate runs on the prepared narration text so a failure
costs one block regeneration instead of a post-render rework.

Modes:
  Full gate (authoritative, after write_blocks finishes):
    python pre_tts_qa.py 2026-09-25
    1. check_japanese.py over all text artifacts (drafts/outline/map/html/tts txt)
    2. check_draft_length.py
    3. disclaimer contract scan (script.json + production/tts/*.txt + drafts)
    4. script.json ids == segment-map tts ids (paragraph-number consistency)
    5. prepared tts txt == script.json text after normalization

  Block gate (called by write_blocks before enqueuing a block for TTS):
    python pre_tts_qa.py 2026-09-25 --map production/tts/segment-map.A.json
    1. language lint over the just-prepared tts txt of that map only
    2. disclaimer scan over the map text + its tts txt
    3. tts txt == map segment text after normalization

  Semantic advisory (optional, one pro API call, run BEFORE Step 4 TTS):
    python pre_tts_qa.py 2026-09-25 --semantic
    Compliance/actionability/depth review over script.json. Findings are
    printed and saved to review/pre-tts-qa-semantic.json but NEVER change the
    exit code (9/16-9/25 precedent: semantic false positives are common; this
    moved out of final_qa so wording fixes happen before synthesis cost).

Exit codes: 0 = pass, 1 = usage/env error, 2 = gate failure.
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
sys.path.insert(0, str(_TOOLS_DIR))
sys.path.insert(0, str(_US_ROOT / "tools"))

import episode_contract  # noqa: E402

PAUSE_RE = re.compile(r"\[pause (?:long|short)\]")


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _normalize():
    sys.path.insert(0, str(_US_ROOT / "tools" / "tts"))
    from ja_tts_normalize import normalize_for_tts  # noqa: E402
    return normalize_for_tts


def _disclaimer_errors(texts: list[tuple[str, str]]) -> list[str]:
    errors: list[str] = []
    for name, text in texts:
        hits = episode_contract.disclaimer_hits(text)
        if hits:
            errors.append(f"{name}: 免責文混入 -> " + "、".join(hits))
    return errors


def run_block_gate(date: str, map_rel: str) -> int:
    """Gate one prepared partial/full segment-map before it may be synthesized."""
    issue = _US_ROOT / "daily-output" / date
    map_path = issue / map_rel
    smap = _read_json(map_path)
    if smap is None:
        print(f"[pre-TTS QA] [error] cannot read {map_rel}")
        return 1
    normalize = _normalize()
    import check_japanese

    failures: list[str] = []
    tts_dir = issue / "production" / "tts"
    seg_texts: list[tuple[str, str]] = []
    for seg in smap.get("segments", []):
        if seg.get("type", "tts") != "tts":
            continue
        seg_id = str(seg.get("id", ""))
        text = str(seg.get("text", ""))
        seg_texts.append((f"{map_rel}:{seg_id}", text))
        txt = tts_dir / f"{int(seg.get('order', 0)):03d}_{seg_id}.txt"
        if not txt.is_file():
            failures.append(f"{seg_id}: prepared txt missing ({txt.name})")
            continue
        got = txt.read_text(encoding="utf-8-sig")
        seg_texts.append((f"tts/{txt.name}", got))
        if PAUSE_RE.sub("", got) != PAUSE_RE.sub("", normalize(text)):
            failures.append(f"{seg_id}: tts txt does not equal segment text")

    lint_errors: list[str] = []
    for name, text in seg_texts:
        errors, _warns = check_japanese.check_text(name, text)
        lint_errors.extend(errors)
    if lint_errors:
        failures.append("language lint:\n  " + "\n  ".join(lint_errors))

    dis_errors = _disclaimer_errors(seg_texts)
    if dis_errors:
        failures.append("disclaimer contract:\n  " + "\n  ".join(dis_errors))

    report = {
        "date": date, "mode": "block", "map": map_rel,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "failures": failures,
    }
    report_path = issue / "review" / "pre-tts-qa.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")
    if failures:
        print(f"[pre-TTS QA] FAILED block gate ({map_rel}):")
        for f in failures:
            for line in f.splitlines():
                print(f"  {line}")
        print("[pre-TTS QA] NOT queued for TTS; fix with "
              "write_blocks.py --only <block> then re-check")
        return 2
    n = len(seg_texts) // 2
    print(f"[pre-TTS QA] PASS block gate ({map_rel}, {n} segments)")
    return 0


def run_full_gate(date: str) -> int:
    issue = _US_ROOT / "daily-output" / date
    prod = issue / "production"
    py = sys.executable
    checks: list[dict] = []
    hints: list[str] = []

    def _add(name: str, passed: bool, output: str) -> None:
        checks.append({"check": name, "passed": passed, "output": output[-2000:]})
        icon = "PASS" if passed else "FAIL"
        print(f"  [{icon}] {name}")
        if not passed:
            for line in output.strip().splitlines()[-6:]:
                print(f"         {line}")

    def _run(args: list[str], label: str) -> tuple[bool, str]:
        try:
            r = subprocess.run(args, cwd=str(_US_ROOT), capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=180)
            return r.returncode == 0, ((r.stdout or "") + (r.stderr or ""))
        except subprocess.TimeoutExpired:
            return False, f"{label}: timed out after 180s"
        except FileNotFoundError as e:
            return False, f"{label}: command not found: {e}"

    # 1. Language lint over every text artifact, including prepared tts txt.
    passed, out = _run([py, str(_US_ROOT / "tools" / "check_japanese.py"), date],
                       "check_japanese")
    _add("japanese_vocab_and_simplified", passed, out)
    if not passed:
        hints.append("影響ブロックを write_blocks.py --only <block> で再生成")

    # 2. Draft length bands.
    passed, out = _run([py, str(_US_ROOT / "tools" / "check_draft_length.py"), date],
                       "check_draft_length")
    _add("draft_length", passed, out)
    if not passed:
        hints.append("超過セクションを write_blocks.py --only <block> で圧縮再生成")

    # 3. Disclaimer contract over all narration artifacts.
    dis_texts: list[tuple[str, str]] = []
    script = _read_json(prod / "script.json")
    if script:
        for b in script.get("blocks", []):
            dis_texts.append((f"script.json:{b.get('id')}",
                              str(b.get("text", ""))))
    tts_dir = prod / "tts"
    if tts_dir.is_dir():
        for txt in sorted(tts_dir.glob("*.txt")):
            dis_texts.append((f"tts/{txt.name}",
                              txt.read_text(encoding="utf-8-sig")))
    for draft in sorted(prod.glob("draft-*.md")):
        dis_texts.append((draft.name, draft.read_text(encoding="utf-8-sig")))
    dis_errors = _disclaimer_errors(dis_texts)
    _add("disclaimer_contract", not dis_errors,
         "no disclaimer fragments in narration artifacts"
         if not dis_errors else "\n".join(dis_errors))
    if dis_errors:
        hints.append("免責はEND静止画のみ。該当ブロック再生成→prepare_tts 再実行")

    # 4. script.json block ids == segment-map tts ids (paragraph consistency).
    smap = _read_json(prod / "segment-map.json")
    if script and smap:
        script_ids = {str(b.get("id")) for b in script.get("blocks", [])
                      if isinstance(b, dict)}
        map_ids = {str(s.get("id")) for s in smap.get("segments", [])
                   if s.get("type", "tts") == "tts"}
        only_script = sorted(script_ids - map_ids)
        only_map = sorted(map_ids - script_ids)
        ok = not only_script and not only_map
        detail = f"script={len(script_ids)} map_tts={len(map_ids)}"
        if not ok:
            detail += f"\nscript only: {only_script}\nmap only: {only_map}"
        _add("segment_map_consistency", ok, detail)
        if not ok:
            hints.append("prepare_tts.py / build-map を再実行して同期")
    else:
        _add("segment_map_consistency", False,
             "script.json or segment-map.json missing")
        hints.append("write_blocks.py 未完了: Step 3 を確認")

    # 5. Prepared tts txt == script.json (full manifest equality).
    mismatches: list[str] = []
    if script and tts_dir.is_dir():
        normalize = _normalize()
        text_by_id = {str(b.get("id")): str(b.get("text", ""))
                      for b in script.get("blocks", []) if isinstance(b, dict)}
        manifest = _read_json(tts_dir / "manifest.json") or {}
        for seg in manifest.get("segments", []):
            if seg.get("type") != "tts":
                continue
            seg_id = str(seg.get("id", ""))
            want = text_by_id.get(seg_id)
            f = issue / "production" / seg.get("file", "")
            if want is None:
                mismatches.append(f"{seg_id}: not in script.json")
                continue
            if not f.is_file():
                mismatches.append(f"{seg_id}: txt missing ({f.name})")
                continue
            got = f.read_text(encoding="utf-8-sig")
            if PAUSE_RE.sub("", got) != PAUSE_RE.sub("", normalize(want)):
                mismatches.append(f"{seg_id}: txt != script.json")
        _add("tts_txt_matches_script", not mismatches,
             "prepared narration txt equals script.json"
             if not mismatches else "\n".join(mismatches))
        if mismatches:
            hints.append("prepare_tts.py を再実行して tts txt を再生成")

    failed = [c for c in checks if not c["passed"]]
    report_path = issue / "review" / "pre-tts-qa.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "date": date, "mode": "full",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks, "repair_hints": hints,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2)
                           + "\n", encoding="utf-8")
    if failed:
        print(f"[pre-TTS QA] FAILED ({len(failed)}/{len(checks)}): "
              + ", ".join(c["check"] for c in failed))
        for h in hints:
            print(f"  hint: {h}")
        print(f"  report -> {report_path}")
        return 2
    print(f"[pre-TTS QA] PASS ({len(checks)} checks) -> {report_path}")
    return 0


def run_semantic_review(date: str) -> int:
    """Advisory one-call LLM review of narration wording, BEFORE TTS.

    Moved out of final_qa (2026-09-25 restructure): findings here can still be
    fixed with a cheap write_blocks --only + partial resynth, instead of a
    post-render rework loop. Vision findings were historically unstable
    (9/16-9/25 false positives), so this NEVER fails the pipeline: exit 0
    always, unless script.json is missing.
    """
    import text_llm

    issue = _US_ROOT / "daily-output" / date
    script_path = issue / "production" / "script.json"
    if not script_path.is_file():
        print(f"[error] script.json not found: {script_path}")
        return 1
    if not text_llm.is_configured():
        print("[pre-TTS QA] [SKIP] semantic advisory (text_llm not configured)")
        return 0

    script = _read_json(script_path) or {}
    full_text = "\n\n".join(
        f"== {b.get('id', '?')} ==\n{b.get('text', '')}"
        for b in script.get("blocks", []) if isinstance(b, dict)
    )
    if len(full_text) > 40000:
        full_text = full_text[:40000] + "\n... (truncated)"

    prompt = f"""あなたは日本の証券・資産運用業界のコンプライアンス担当であり、
投資番組の最終品質チェックを担当しています。以下の放送台本を審査し、
問題があれば JSON で報告してください。

【チェック項目】
1. コンプライアンス: 直接的な売買推奨がないか（「私ならこう動きます」形式は OK）
2. コンプライアンス: 収益率の保証がないか
3. コンプライアンス: ナレーション本文に免責事項が含まれていないか
   （免責は番組末尾のEND静止画でのみ表示する。台本テキストに
   「投資判断を助ける情報提供」等の免責文があればエラーとする）
4. アクション指針（鉄則二）: 個別株/セクターに大手目標株価＋アクション価格があるか
5. 情報源: 主要な数字に出所が明記されているか
6. 深度: 表面的なニュース羅列でなく、因果・構造・リスクの分析があるか
7. 日本語: 不自然な直訳や簡体字の残りがないか

【放送台本】
{full_text}

【出力形式】有効な JSON のみ:
{{
  "passed": true/false,
  "errors": ["具体的な問題の説明（block ID と行内容を引用）"],
  "warnings": ["警告レベルの指摘"],
  "compliance_ok": true/false,
  "actionability_ok": true/false,
  "depth_ok": true/false
}}"""

    schema = json.dumps({
        "type": "object",
        "required": ["passed", "errors"],
        "properties": {
            "passed": {"type": "boolean"},
            "errors": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    })
    try:
        result = text_llm.generate_json(prompt, tier="pro", schema_hint=schema)
    except Exception as e:  # noqa: BLE001 - advisory only
        print(f"[pre-TTS QA] [WARN] semantic review API call failed: {e}")
        return 0

    report_path = issue / "review" / "pre-tts-qa-semantic.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps({"date": date,
                    "generated_at": datetime.now().isoformat(timespec="seconds"),
                    "review": result}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    icon = "PASS" if result.get("passed") else "FLAG"
    print(f"[pre-TTS QA] [{icon}] semantic advisory -> {report_path}")
    for e in result.get("errors", [])[:8]:
        print(f"         ERROR: {e}")
    for w in result.get("warnings", [])[:4]:
        print(f"         WARN: {w}")
    print("[pre-TTS QA] advisory only: verify each item against the source "
          "cards; fix real ones with write_blocks.py --only <block> BEFORE "
          "Step 4. Numbers/outlet identity must be re-checked against "
          "collection originals (9/25 lesson) before patching.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-TTS narration gate (kanji/disclaimer/consistency)")
    parser.add_argument("issue_date", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--map", dest="seg_map", default=None,
                        help="block mode: gate this segment-map json "
                             "(issue-relative path) before TTS synthesis")
    parser.add_argument("--semantic", action="store_true",
                        help="advisory LLM review of script.json wording "
                             "(compliance/depth). Never affects exit code.")
    args = parser.parse_args()

    issue = _US_ROOT / "daily-output" / args.issue_date
    if not issue.is_dir():
        print(f"[error] issue directory not found: {issue}")
        return 1
    if args.seg_map:
        return run_block_gate(args.issue_date, args.seg_map)
    if args.semantic:
        return run_semantic_review(args.issue_date)
    return run_full_gate(args.issue_date)


if __name__ == "__main__":
    raise SystemExit(main())

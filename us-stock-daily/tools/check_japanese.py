"""Japanese language lint for all narration/output text of an episode.

Checks (per 2026-08-29 language gate revision):
  1. ERROR: Chinese-only vocabulary that must not appear in Japanese output
     (e.g. 指引 -> ガイダンス). One entry = one term; context is not judged.
  2. WARN : words that are legitimate Japanese but frequently misused for
     finance jargon in this project (e.g. 収入 for revenue -> 売上高).
  3. ERROR: simplified Chinese characters remaining anywhere.
  4. ERROR: stray English editorial words that should be Japanese.

Scans an episode's outline, drafts, visual brief, segment map and visual HTML.
Exit 1 on any ERROR; WARN must be manually confirmed and is reported.

Usage:
  python tools/check_japanese.py 2026-08-28
  python tools/check_japanese.py 2026-08-28 --file production/outline.md
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

US_STOCK_DAILY = Path(__file__).resolve().parent.parent

# Chinese finance/marketing vocabulary that has leaked into Japanese output before.
# value = the correct Japanese rendering (shown in reports).
ERROR_VOCAB = {
    "指引": "ガイダンス／業績見通し",
    "財報": "決算",
    "财报": "決算",
    "網安": "サイバーセキュリティ",
    "网安": "サイバーセキュリティ",
    "大摩": "モルガン・スタンレー",
    "小摩": "モルガン・スタンレー",
    "大行": "大手銀行",
    "市值": "時価総額",
    "市盈率": "PER",
    "目标价": "目標株価",
    "目標價": "目標株価",
    "兑现": "実現",
    "落地": "実装・実施",
    "复盘": "総括・検証",
    "口径": "定義・ベース",
    "净值": "純資産",
    "纯利": "純利益",
    "淨利": "純利益",
    "营收": "売上高",
    "賽道": "市場・業界",
    "赛道": "市場・業界",
    "护城河式": "護城河のような",
    "牛市": "強気相場／上昇相場／株高",
    "熊市": "弱気相場／下落相場",
    "長債": "長期債／長期国債",
    "多头": "買い方",
    "空头": "売り方",
}

# Legitimate Japanese words that are wrong for this project's finance usage.
# These require human confirmation of context (WARN, not ERROR).
WARN_VOCAB = {
    "収入": "売上高／収益（revenue の意味では「収入」を使わない）",
    "予約": "受注（bookings の意味では「予約」を使わない）",
    "口座": "アカウント（顧客アカウントの意味では「口座」を使わない）",
    "席位": "シート（SaaSの席課金は「シート課金」）",
    "席課金": "シート課金",
    "閉鎖": "完了（M&Aクロージングの意味では「閉鎖」を使わない）",
    "触媒": "カタリスト（株価材料の意味では片仮名が一般的）",
    "牛熊": "ブル・アンド・ベア（Bull & Bear の定訳）",
    "上振れ幅": "上方修正幅",
}

# Frequent simplified-only characters (curated: excludes kanji that are
# legitimate Japanese such as 現地共用文字 算/好/与/境/称/里/随/翻/灯/拟/融/越).
_SIMPLIFIED_CHARS = (
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
_SIMPLIFIED_RE = re.compile("[" + "".join(sorted(set(_SIMPLIFIED_CHARS))) + "]")

_TAG_RE = re.compile(r"<[^>]+>")
_FY_RE = re.compile(r"(?<![A-Za-z])FY\s*(?:[0-9０-９]{2,4}|二千)", re.IGNORECASE)


def strip_html(text: str) -> str:
    return _TAG_RE.sub(" ", text)


def check_text(name: str, text: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warns: list[str] = []
    for term, correct in ERROR_VOCAB.items():
        for m in re.finditer(re.escape(term), text):
            snippet = text[max(0, m.start() - 12) : m.end() + 12].replace("\n", " ")
            errors.append(f"{name}: 「{term}」→{correct} …{snippet}")
    for term, correct in WARN_VOCAB.items():
        for m in re.finditer(re.escape(term), text):
            snippet = text[max(0, m.start() - 12) : m.end() + 12].replace("\n", " ")
            warns.append(f"{name}: 「{term}」（{correct}）を確認 …{snippet}")
    for m in _SIMPLIFIED_RE.finditer(text):
        snippet = text[max(0, m.start() - 12) : m.end() + 12].replace("\n", " ")
        errors.append(f"{name}: 簡体字「{m.group(0)}」が残留 …{snippet}")
    for m in _FY_RE.finditer(text):
        snippet = text[max(0, m.start() - 12) : m.end() + 12].replace("\n", " ")
        errors.append(
            f"{name}: 「{m.group(0)}」→「2028年度」等の日本語年度表記（ナレーションでは FY を使わない）"
        )
    return errors, warns


def episode_targets(issue_date: str) -> list[tuple[str, Path]]:
    day = US_STOCK_DAILY / "daily-output" / issue_date
    prod = day / "production"
    targets: list[tuple[str, Path]] = [
        ("outline.md", prod / "outline.md"),
        ("draft-A.md", prod / "draft-A.md"),
        ("draft-B.md", prod / "draft-B.md"),
        ("draft-C.md", prod / "draft-C.md"),
        ("draft-D.md", prod / "draft-D.md"),
        ("visual-brief.md", prod / "visual-brief.md"),
        ("segment-map.json", prod / "segment-map.json"),
    ]
    for html in sorted(day.glob("visual*.html")):
        targets.append((html.name, html))
    tts_dir = prod / "tts"
    if tts_dir.is_dir():
        for tts_file in sorted(tts_dir.glob("*.txt")):
            targets.append((f"tts/{tts_file.name}", tts_file))
    return [(n, p) for n, p in targets if p.is_file()]


def main() -> int:
    parser = argparse.ArgumentParser(description="Japanese language lint for episode text outputs")
    parser.add_argument("issue_date", nargs="?", help="episode date (YYYY-MM-DD)")
    parser.add_argument("--file", default=None, help="check a single file instead of an episode")
    args = parser.parse_args()

    if args.file:
        p = Path(args.file)
        if not p.is_absolute():
            p = US_STOCK_DAILY / "daily-output" / args.issue_date / args.file if args.issue_date else Path(args.file)
        targets = [(p.name, p)]
    elif args.issue_date:
        targets = episode_targets(args.issue_date)
    else:
        parser.error("issue_date or --file required")
        return 2

    if not targets:
        print("[error] no target files found")
        return 2

    all_errors: list[str] = []
    all_warns: list[str] = []
    for name, path in targets:
        raw = path.read_text(encoding="utf-8-sig")
        if path.suffix == ".html":
            raw = strip_html(raw)
        elif path.suffix == ".json":
            try:
                data = json.loads(raw)
                raw = json.dumps(data, ensure_ascii=False)
            except json.JSONDecodeError:
                pass  # fall back to raw scan
        e, w = check_text(name, raw)
        all_errors.extend(e)
        all_warns.extend(w)
        print(f"[scan] {name}: error={len(e)} warn={len(w)}")

    if all_warns:
        print(f"\n[warn] 文脈確認が必要な語（{len(all_warns)}件）:")
        for w in all_warns:
            print(f"  - {w}")
    if all_errors:
        print(f"\n[error] 修正必須の語彙（{len(all_errors)}件）:")
        for e in all_errors:
            print(f"  - {e}")
        print("\n[result] FAIL")
        return 1
    print("\n[result] PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

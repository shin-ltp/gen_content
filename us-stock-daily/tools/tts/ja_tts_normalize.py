"""Japanese TTS text normalization for Fish Audio.

Converts narration-layer drafts into TTS-safe Japanese:
- strip inline citation markers
- katakana-ize Latin finance acronyms / company names Fish tends to misspell
- convert dates, years, percentages, dollar amounts, decimals and plain
  integers into kanji readings (Fish misreads Arabic numerals in Japanese)
- normalize whitespace and ensure sentence-final punctuation
"""
from __future__ import annotations

import re

_GLOSSARY_PAIRS = [
    ("S&P500", "エス・アンド・ピー五百"),
    ("SKハイニックス", "エスケーハイニックス"),
    ("HOMEエクイティローン", "ホームエクイティローン"),
    ("OpenAI", "オープンエーアイ"),
    ("CoreWeave", "コアウィーブ"),
    ("Cerebras", "セレブラス"),
    ("Anthropic", "アンソロピック"),
    ("Blackwell", "ブラックウェル"),
    ("Vera Rubin", "ベラ・ルービン"),
    ("Trainium", "トレイニウム"),
    ("SB Energy", "エスビーエナジー"),
    ("State Street", "ステート・ストリート"),
    ("Ross Stores", "ロス・ストアーズ"),
    ("Walmart", "ウォルマート"),
    ("Kioxia", "キオクシア"),
    ("Peloton", "ペルトン"),
    ("Airbnb", "エアビーアンドビー"),
    ("FOMC", "エフオーエムシー"),
    ("FRB", "エフアールビー"),
    ("NVDA", "エヌビディア"),
    ("TSMC", "ティーエスエムシー"),
    ("AMD", "エーエムディー"),
    ("CPI", "シーピーアイ"),
    ("VIX", "ヴィックス"),
    ("WTI", "ダブリューティーアイ"),
    ("EPS", "イーピーエス"),
    ("PER", "ピーイーアール"),
    ("ETF", "イーティーエフ"),
    ("IPO", "アイピーオー"),
    ("FCF", "エフシーエフ"),
    ("CEO", "シーイーオー"),
    ("CFO", "シーエフオー"),
    ("TPU", "ティーピーユー"),
    ("GPU", "ジーピーユー"),
    ("TJX", "ティージーエックス"),
    ("ADI", "エーディーアイ"),
    ("AI", "エーアイ"),
    ("K型", "ケー型"),
    ("Meta", "メタ"),
]
_GLOSSARY = sorted(_GLOSSARY_PAIRS, key=lambda kv: -len(kv[0]))

_CITATION_RE = re.compile(r"【(?:出所|当番組の見解)[^】]*】")

_K_DIGITS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]


def _four_digits(n: int) -> str:
    """Read 1..9999 positionally (千/百/十)."""
    if n <= 0 or n >= 10000:
        raise ValueError(n)
    out = []
    thousands, n = divmod(n, 1000)
    if thousands:
        out.append((_K_DIGITS[thousands] if thousands > 1 else "") + "千")
    hundreds, n = divmod(n, 100)
    if hundreds:
        out.append((_K_DIGITS[hundreds] if hundreds > 1 else "") + "百")
    tens, ones = divmod(n, 10)
    if tens:
        out.append((_K_DIGITS[tens] if tens > 1 else "") + "十")
    if ones:
        out.append(_K_DIGITS[ones])
    return "".join(out) or "零"


def int_to_kanji(n: int) -> str:
    """Read a non-negative integer in Japanese (万/億/兆 units)."""
    if n < 0:
        return str(n)
    if n == 0:
        return "零"
    units = [("兆", 10**12), ("億", 10**8), ("万", 10**4)]
    parts: list[str] = []
    rest = n
    for unit_name, unit_val in units:
        q, rest = divmod(rest, unit_val)
        if q == 0:
            continue
        # 1万 / 1億 / 1兆 keep the 一; other prefixes read positionally.
        parts.append(("一" if q == 1 else _four_digits(q)) + unit_name)
    if rest or not parts:
        parts.append(_four_digits(rest))
    return "".join(parts)


def _read_decimal(int_part: str, frac: str) -> str:
    frac = frac.rstrip("0") or "0"
    head = int_to_kanji(int(int_part)) if int_part else "零"
    tail = "".join(_K_DIGITS[int(c)] for c in frac)
    return f"{head}点{tail}"


def _read_number(num: str) -> str:
    """Read a comma-grouped integer or decimal string."""
    num = num.replace(",", "")
    if "." in num:
        head, _, tail = num.partition(".")
        return _read_decimal(head or "0", tail)
    return int_to_kanji(int(num))


def _sign_word(sign: str) -> str:
    if sign == "+":
        return "プラス"
    if sign == "-":
        return "マイナス"
    return ""


def _convert_money(m: re.Match) -> str:
    num, unit = m.group(1), m.group(2)
    if unit:
        return _read_number(num) + unit + "ドル"
    if "." in num:
        frac = num.partition(".")[2]
        if len(frac) <= 2:
            total_cents = round(float(num) * 100)
            cents = total_cents % 100
            dollars = int(total_cents // 100)
            if dollars and cents:
                return f"{int_to_kanji(dollars)}ドル{int_to_kanji(cents)}セント"
            if dollars:
                return f"{int_to_kanji(dollars)}ドル"
            return f"{int_to_kanji(cents)}セント"
    return _read_number(num) + "ドル"


_SLASH_DATE_RE = re.compile(r"(?<![\d.])(\d{1,2})/(\d{1,2})(?![\d/])")
_YEAR_RE = re.compile(r"(?<![\d.])(\d{4})年")
_PERCENT_RE = re.compile(r"(?<![\d.])([+-]?)\s?([\d,]+(?:\.\d+)?)\s?%")
_DOLLAR_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)(兆|億|万)?")
_DATE_RE = re.compile(r"(?<![\d.])(\d{1,2})月(\d{1,2})日")
_DECIMAL_RE = re.compile(r"(?<![\d.])(\d+)\.(\d+)(?![\d.])")
_COMMA_INT_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:,\d{3})+)(?![\d.])")
_INT_RE = re.compile(r"(?<![\d.])(\d+)(?![\d.%])")


def normalize_for_tts(text: str) -> str:
    """Apply all TTS-safe normalizations to Japanese narration text."""
    if not text:
        return text

    text = _CITATION_RE.sub("", text)

    for src, dst in _GLOSSARY:
        text = text.replace(src, dst)

    def slash_date(m: re.Match) -> str:
        return f"{int_to_kanji(int(m.group(1)))}月{int_to_kanji(int(m.group(2)))}日"

    text = _SLASH_DATE_RE.sub(slash_date, text)
    text = _YEAR_RE.sub(lambda m: int_to_kanji(int(m.group(1))) + "年", text)
    text = _PERCENT_RE.sub(
        lambda m: _sign_word(m.group(1)) + _read_number(m.group(2)) + "パーセント",
        text,
    )
    text = _DOLLAR_RE.sub(_convert_money, text)
    text = _DATE_RE.sub(
        lambda m: f"{int_to_kanji(int(m.group(1)))}月{int_to_kanji(int(m.group(2)))}日",
        text,
    )
    text = _DECIMAL_RE.sub(lambda m: _read_decimal(m.group(1), m.group(2)), text)
    text = _COMMA_INT_RE.sub(lambda m: _read_number(m.group(1)), text)
    # Last pass: bare integers (5年先 / 9対3 / 第2四半期 ...).
    text = _INT_RE.sub(lambda m: int_to_kanji(int(m.group(1))), text)

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if text and text[-1] not in ("。", "？", "！", "…"):
        text += "。"
    return text

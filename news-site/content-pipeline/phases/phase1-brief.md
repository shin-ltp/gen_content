# Phase 1 — 每日简报生成（brief）

## 目的

从 draft-A（市况）+ draft-C（News 列表）+ outline 要点，生成一篇 800〜1200 字的日语快读简报。

## 结构（模板 [../templates/brief-template.md](../templates/brief-template.md)）

1. タイトル: 「YYYY年M月D日（曜）米国市場デイリーブリーフィング」
2. 市況サマリ: 3〜5 行（指数涨跌、主なイベント、工业材料/通貨等）
3. 本日のポイント: 3 点（每个 2〜3 句，从 outline 的 B 主题各取一句核心结论）
4. ニュースリンク集: 5〜8 条标题（来自 draft-C），文末统一列出来源名。
5. 次号予告 / CTA: YouTube 当日节目链接 + 会员注册引导（一句话）。

## 写作规则

- 语体: だ・である調（与 YouTube 节目一致）。
- 免责: 文末固定一行（沿用 us-stock-daily/spec/compliance.md）。
- 数字必须与 draft-A 原文一致，不得重新计算或四舍五入成模糊表述。
- 不新增 draft 里没有的事实；可以压缩、合并、换措辞。
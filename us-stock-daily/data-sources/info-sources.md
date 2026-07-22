# 情報源一覧とツールチェーン

> 旧 PLAN.md 第七章。Phase 0（収集）の核心依存先と、インストール済みツール。アカウント登録状況は [account-checklist.md](./account-checklist.md)。

---

## 無料情報源（Phase 0 収集の核心依存）

| カテゴリ | 情報源 | 用途 |
|----------|--------|------|
| 相場データ | Finviz, TradingView, Yahoo Finance | リアルタイム相場、ヒートマップ |
| マクロ経済 | FRED, BLS, BEA, Treasury.gov | 経済データ |
| 経済カレンダー | Investing.com | 指標発表時刻（網羅性検査の基準） |
| 金利予想 | CME FedWatch | 利下げ確率 |
| 企業決算 | SEC EDGAR, 各社IRページ | 10-K, 10-Q, 8-K |
| ニュース | Reuters, CNBC, AP | リアルタイムニュース |
| 朝のメール | Bloomberg/WSJ/Yahoo | 毎日精選 |
| 投資哲学 | Howard Marks, Buffett Letters | 投資思想 |
| 業界リサーチ | SemiAnalysis, a16z | テック業界深掘り |
| アナリスト追跡 | TipRanks, WallStreetZen | アナリスト勝率 |
| 大手リサーチ | Goldman Sachs Research, JPM Insights | 機関の見解 |

> **DB 連携マーク（[../infra/database-layer.md](../infra/database-layer.md) 参照）** — 以下は定期更新データ（Tier B）の供給源となり、毎日クロールせず DB にキャッシュする:
> - **マクロ経済**（FRED／BLS／BEA／Treasury.gov）→ `macro_indicators`
> - **経済カレンダー**（Investing.com）→ `economic_calendar`
> - **企業決算**（SEC EDGAR／各社 IR）→ `company_financials`・`tickers.next_earnings_date`
> - **アナリスト追跡／大手リサーチ**（TipRanks／Goldman／JPM 等）→ `analyst_consensus`
>
> 上記は Phase 0 開始前の定期バッチ（`db/refresh.py`）または能動更新（`db/db_access.py`）で DB に入れる。**相場データ・ニュース・朝のメール・リサーチ本文**は日次変動（Tier A）のため引き続き毎日収集する。

---

## おすすめ有料情報源

| 情報源 | 費用 | 価値 | 優先度 |
|--------|------|------|--------|
| Seeking Alpha Premium | $239/年 | レーティング集計＋独立分析 | ★★★★★ |
| TipRanks Pro | $29.99/月 | アナリスト勝率の完全データ | ★★★★ |
| Simply Wall St | $10-20/月 | スノーフレーク可視化 | ★★★ |

---

## インストール済みツールチェーン

- **市場データ**: longbridge-market-data / -research / -fundamentals / -earnings / -value-investing
- **深層分析**: valuation-analysis / competitive-position / moat-analysis / growth-analysis / peer-comparison / analyst-estimates / risk-assessment
- **リサーチ**: research-deep
- **クロール（Phase 3 用）**: Web リーダー／クローラーツール（採用素材の画像・チャート取得）

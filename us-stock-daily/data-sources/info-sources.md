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

- **市場データ**: longbridge-market-data / -research / -fundamentals / -earnings / -value-investing（スキル）。実動バックエンドは **longbridge CLI**（下記注記）
- **深層分析**: valuation-analysis / competitive-position / moat-analysis / growth-analysis / peer-comparison / analyst-estimates / risk-assessment
- **リサーチ**: research-deep
- **クロール（Phase 3 用）**: Web リーダー／クローラーツール（採用素材の画像・チャート取得）

> ⚠ **実用性注記（2026-08-04 試跑・P1 対応で確認）**
>
> **longbridge CLI（市場データの実動バックエンド）**
> - インストール済み: `../tools/bin/longbridge.exe`（v0.26.0、SHA256 検証済み。再インストールは `../tools/install-longbridge.ps1`）
> - **ログイン必須**: スキル文書の「行情コマンドはログイン不要」は実態と異なる。`longbridge quote` 等も認証が必要。
> - ログイン方法: `longbridge auth login`（Device Flow — 表示される URL をブラウザで開き Longbridge アカウントで承認）。
>   トークンは `~/.longbridge/openapi/tokens/` に保存され以後自動利用。エージェント完結型は
>   `https://open.longbridge.com/connect` で発行したコードを `longbridge auth login --auth-code <CODE>`。
> - 前提: **Longbridge 証券アカウント**が必要（US 口座は longbridge.com 側で発行。中国大陆からの場合は `LONGBRIDGE_REGION=global`）。
> - **状態: ✅ ログイン済み・検証済み（2026-08-04）**。検証済みコマンド:
>   `quote`（個別株＋指数 `.SPX.US`/`.IXIC.US`/`.DJI.US`/`.VIX.US`、プレ/アフター/オーバーナイト各セッション付き）、
>   `kline`（日足 OHLCV）、`exchange-rate`（為替マトリクス）、`market-temp`（市場温度・バリュエーション・センチメント 0-100）。
> - ⚠ 既知の制限: `BTCUSD.HAS`（暗号）は本アカウントでは利用不可（アカウントタイプの制限）。
>   `auth status` はトークンを見つけられないと表示するが実動には問題なし（v0.26.0 のトークンは `~/.longbridge/openapi/cli-auth`）。
> - 収集開始前のヘルスチェック: `longbridge quote .SPX.US --format json` が返れば OK。失敗ならフォールバック経路へ。
>
> **Web 検索チャネル**
> - プライマリ: **SearXNG セルフホスト**（JSON API `/search?format=json`、レート制限なし・生URL取得可）
>   — **✅ 本机 Docker で運用中・検証済み（2026-08-06）**。`http://127.0.0.1:8888`（本机専用・認証なし）。
>   設定は `.env` の `SEARXNG_BASE_URL`（USER/PASSWORD は本机運用のため空）。
>   デプロイ構成と呼び出し規約: `../tools/searxng/`（ラッパースクリプト `search.ps1` 推奨、
>   健康チェックは `search.ps1 -Check` = Phase 0 Step -1）。
>   ホワイトリスト5エンジン: google / bing / bing news / duckduckgo / duckduckgo news
>   （2026-08-06 家庭 IP で再検証済み、`language=ja-JP` の日文検索も可）。
>   ⚠ 履歴: GCP データセンター IP（2026-08-05）では google系空結果・ddg CAPTCHA で bing 系のみ可だった。
>   出口 IP が変わったら README「引擎可用性重测」の手順で再検証すること。
> - フォールバック: Codex ランタイム内蔵 `web_search`（要約＋出所を返す。約3クエリ/回のレート制限あり。生URLの網羅性に難）
> - フォールバック時は Gate #0 の数量基準（30件）への到達性が下がるため、6カテゴリのカバレッジと
>   核心話題の深度を優先する。詳細: 初回試跑報告 `../daily-output/2026-08-04/review/trial-report.md` §二 P1/P3。

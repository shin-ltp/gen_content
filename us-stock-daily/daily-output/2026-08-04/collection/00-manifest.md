# 2026-08-04 収集素材マスター索引（試跑）

> 収集エージェント: collector-agent | 収集日時: 2026-08-04 11:20〜12:15（JST）
> 合計: **18 件**（MKT: 1 / MAC: 2 / RES: 2 / STK: 3 / ERN: 5 / NWS: 5）
> ⚠ 試跑注記: 収集チャネルは web_search のみ。longbridge 系ツールは現コンテキストで利用不可。
> 数量基準（Gate #0 の30件目安）は未達 → 詳細は review/trial-report.md。

## 索引
| ID | カテゴリ | 銘柄 | タイトル | 情報源 | タイプ | 優先度 | 画像要 | 状態 |
|----|----------|------|----------|--------|--------|--------|--------|------|
| MKT-20260804-001 | market | — | 主要指数・為替・金利・商品・暗号スナップ（8/3クロージング） | Investing.com 他 | data | TBD | no | raw |
| MAC-20260804-001 | macro | — | 今週の経済カレンダー（8/4貿易収支・8/5 ISM・8/6失業保険） | FXEmpire | data | TBD | no | raw |
| MAC-20260804-002 | macro | — | CME FedWatch: 9月FOMC 据え置き44%・利上げ51%・利下げ4% | CME FedWatch | data | TBD | no | raw |
| RES-20260804-001 | research | FLUT | ウェルズ・ファーゴ目標株価161→168ドル（EW継続） | Wells Fargo | research | TBD | logo | raw |
| RES-20260804-002 | research | PLTR | 目標株価総覧: コンセンサス約182ドル、レンジ70〜255ドル | TipRanks 他 | research | TBD | logo,table | raw |
| STK-20260804-001 | stocks | CVX | エネルギー株下落主導 — CVX/XOMがS&Pの重し、原油3週安値 | Reuters/Yahoo | media | TBD | logo | raw |
| STK-20260804-002 | stocks | NVDA | 半導体がナスダック上昇主導 — NVDA時価総額約4.7兆ドル | CNBC 他 | media | TBD | logo | raw |
| STK-20260804-003 | stocks | — | 日経平均 64,141円（+1.96%）史上最高値、円安156円台 | Nikkei Asia | media | TBD | no | raw |
| ERN-20260804-001 | earnings | PLTR | Q2: 売上+93%・EPS0.41上振れ・通期81.5億ドルへ引き上げ | Investing.com/StockTitan | official | TBD | logo,table | raw |
| ERN-20260804-002 | earnings | BRK.B | バークシャーQ2は未発表（カレンダー誤報、8/5に一次確認済み） | Berkshire IR / EDGAR | official | TBD | logo | verified |
| ERN-20260804-003 | earnings | AMD | 本日引後決算プレビュー: ガイダンス112億 vs 予想113億 | StreetInsider/Yahoo | media | TBD | logo | raw |
| ERN-20260804-004 | earnings | DIS | FY26 Q3 決算は8/5発表予定 | GlobeNewswire | media | TBD | logo | raw |
| ERN-20260804-005 | earnings | RARE | その他の8/3引後決算（AMRZ/AESI/NVTS/RARE） | MarketBeat | media | TBD | no | raw |
| NWS-20260804-001 | news | — | トランプ氏、イラン攻撃中止し外交優先 — ホルムズ再開が第一目標 | AP | media | TBD | no | raw |
| NWS-20260804-002 | news | — | イランは直接交渉を否定 — オマーン経由の暫定回廊交渉と主張 | Guardian | media | TBD | no | raw |
| NWS-20260804-003 | news | — | 原油急落の構造 — 3月来のホルムズ封鎖が緩和局面へ、ドーハ交渉 | Yahoo Finance | media | TBD | no | raw |
| NWS-20260804-004 | news | — | ダウ史上最高値・3指数3日続伸 — 原油安と金利低下が主因 | MarketWatch | media | TBD | no | raw |
| NWS-20260804-005 | news | FLUT | ロンドン証取上場廃止、NYSE単独上場へ | Reuters | media | TBD | logo | raw |

## 収集カバレッジ（Gate #0 用）
- [x] 市場データ（指数・為替・債券・商品・暗号）— MKT-001。VIX/Fear&Greed は未取得（ギャップ）
- [x] マクロ（経済カレンダー・FedWatch）— MAC-001/002。ISM予想値・前回値は未取得（ギャップ）
- [x] 大手レーティング変更 — RES-001/002（件数は限定的）
- [x] 個別株・セクター — STK-001〜003（エネルギー・半導体・日本株連関）
- [x] 決算 — ERN-001〜005（PLTR詳細あり、BRK数値未確認）
- [x] ニュース速報 — NWS-001〜005（地政学・市況・企業アクション）
- [ ] 固定放送資産の網羅 — 恐怖・強欲指数、セクター別騰落の詳細は未取得（ギャップ）
- [ ] DB 鮮度検査 — **DB未実装のため適用不能**（試跑最大の構造ギャップ）

## 事後検証ログ（8/5 追記）
- C-5（バークシャーQ2）: 一次確認の結果「未発表」と判明し素材を修正済み（ERN-20260804-002）。
  決算カレンダー（MarketBeat）の誤報が原因。教訓は同素材の備考に記録。
- B-3（FedWatch）: 方向性の確認済み — 原油下落（$78割れ・3日続落）と中東交渉進展を受け
  9月利上げ織り込みは後退（Invezz 8/5 "September Fed odds fall"、金先物は$4,224まで上昇）。
  8/3時点の数値（据え置き44%/利上げ51%/利下げ4%）は引用元（FXEmpire 経由 CME FedWatch）のまま有効。
- 新規確認事実（8/5）: 金スポット$4,200超え（1カ月ぶり高値）／S&P500時価総額が史上初の70兆ドル突破（8/4）／
  ホルムズ海峡再開の合意は早ければ8/5(水)にも（Trump 発言、HuffPost）。

## 再収集素材（8/5 重跑追加・5件）

| ID | カテゴリ | 銘柄 | タイトル | 情報源 | 状態 |
|----|----------|------|----------|--------|------|
| MAC-20260805-001 | macro | — | 米日共同の円買い介入（8/3）— 円は40年安値圏、ベセント「whatever it takes」 | NHK/毎日/Nikkei Asia 他 | verified |
| STK-20260805-001 | stocks | — | 市場コンテキスト修正 — 7月AIクラッシュと急反発（日経誤報の訂正） | Seeking Alpha/Invezz/ダイヤモンドZAi | verified |
| STK-20260805-002 | stocks | PLTR | 深層素材 — FDE普及・コンサル競合・強弱両論・AI ROI 接続 | Mint/Seeking Alpha/TMCnet | verified |
| STK-20260805-003 | stocks | AMD | 深層素材 — Helios/MI400・決算結果・capex 懸念 | Forbes/SiliconANGLE/AOL | verified |
| NWS-20260805-001 | news | — | 市場中心テーマ「AIは報いるのか」— バリー警告〜経営層91%リスク意識 | Seeking Alpha/Yahoo/TMCnet | verified |

> 合計: 18件（8/4）＋ 5件（8/5 再収集）＝ 23件。詳細な根因分析は ../review/retry-comparison.md。

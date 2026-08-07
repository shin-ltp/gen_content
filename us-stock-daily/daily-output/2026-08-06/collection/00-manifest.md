# 2026-08-06 収集素材マスター索引

> 収集エージェント: collector-agent | 収集日時: 2026-08-06 09:20〜11:10（JST）
> 合計: **11 件**（MKT: 1 / MAC: 3 / RES: 1 / STK: 1 / ERN: 3 / NWS: 2）
> チャネル注記: SearXNG 不通のため **web_search フォールバック＋longbridge CLI** で収集
> （Step -1 工具链健康チェックの結果を status.md に記録済み）。
> 数量基準（30件）は未達だが、6カテゴリのカバレッジと核心話題の深度を優先（README の運用ルール）。

## 索引
| ID | カテゴリ | 銘柄 | タイトル | 情報源 | タイプ | 優先度 | 状態 |
|----|----------|------|----------|--------|--------|--------|------|
| MKT-20260806-001 | market | — | 主要指数・注目銘柄・為替・金利・原油スナップ（8/5クロージング） | longbridge/CNBC | data | TBD | verified |
| MAC-20260806-001 | macro | — | ISM非製造業 54.5へ加速、物価65.5で粘着 | MNI/Reuters | data | TBD | raw |
| MAC-20260806-002 | macro | — | FRB織り込み転換: 利上げ懸念→据え置き51%/利下げ49%のコイントス | FXEmpire/TradingView | data | TBD | raw |
| MAC-20260806-003 | macro | — | 介入後の円: ドル円155.42、植田総裁は利上げ強調へ | Nikkei Asia/longbridge | media | TBD | raw |
| RES-20260806-001 | research | AMD | 目標株価総覧: Bernstein 610 vs Citi 230（2.6倍の割れ） | Reuters/Investing.com | research | TBD | verified |
| STK-20260806-001 | stocks | — | 日経平均 67,445円（+0.6%）6日続伸・決算主導の選別物色 | Nikkei Asia/kabutan | media | TBD | verified |
| ERN-20260806-001 | earnings | AMD | 急落の全貌: DC売上2倍でもQ4ガイダンス未達、大手3行目標引下げ | Reuters/Investing.com | media | TBD | verified |
| ERN-20260806-002 | earnings | QCOM | 決算beat＋DC120億ドル投資 — AI capex 懸念への反証シグナル | Reuters/Yahoo | media | TBD | verified |
| ERN-20260806-003 | earnings | DIS | EPS 1.66でbeat・売上+6.7%・株価+7%（純利益-13%は注記必須） | MarketBeat | media | TBD | raw |
| NWS-20260806-001 | news | — | ホルムズ「枠組み合意」報道 — 詳細不明瞭、原油4日続落で71-74ドル | Yahoo/Barron's/Guardian | media | TBD | raw |
| NWS-20260806-002 | news | — | その他: エリリリー減量薬／エヌビディア増産報道／8-6決算予定 | Barron's/Yahoo/MarketBeat | media | TBD | raw |

## 収集カバレッジ（Gate #0 用）
- [x] 市場データ（指数・為替・金利・商品・心理）— MKT-001（longbridge 一次データで検証済み）
- [x] マクロ（経済カレンダー・FedWatch・為替政策）— MAC-001/002/003（ISM・Fed織り込み・介入後フォロー）
- [x] 大手レーティング変更 — RES-001（AMD 目標株価の引き下げ/引き上げラッシュ）
- [x] 個別株・セクター — STK-001（日経・日本株の選別物色）
- [x] 決算 — ERN-001/002/003（AMD・QCOM・DIS）
- [x] ニュース速報 — NWS-001/002（ホルムズ・その他）
- [x] **為替政策・協調介入の当日ニュース**（固定スキャン項目・8/5追加）— MAC-003 でフォロー
- [x] **米債・資金フロー**（固定スキャン項目）— 10年債 約4.23%（+0.8bp）を MKT-001 に記録
- [ ] DB 鮮度検査 — DB未実装のため適用不能（継続ギャップ）
- [ ] VIX・Fear&Greed の詳細 — VIX 15.81（-4.18%）は longbridge で取得済み、Fear&Greed は未取得

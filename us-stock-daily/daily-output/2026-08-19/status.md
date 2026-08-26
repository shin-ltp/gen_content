# 2026-08-19 収集状態

| Phase | 状態 | 備考 |
|-------|------|------|
| Phase 0 収集 | ✅ 完了 (Gate #0 PASS) | 合計 147 件 |
| → longbridge | ⏭ SKIP | 0 ファイル (user-skip) |
| → market | ✅ | 0 ファイル (ok) |
| → rss | ⏭ SKIP | 0 ファイル (user-skip) |
| → wscn | ⏭ SKIP | 0 ファイル (user-skip) |
| → 36kr | ⏭ SKIP | 0 ファイル (user-skip) |
| → insights | ⏭ SKIP | 0 ファイル (user-skip) |
| → email | ⏭ SKIP | 0 ファイル (user-skip) |

## Phase 進行

| Phase | 状態 | 担当 | 開始 | 完了 | Gate | 備考 |
|-------|------|------|------|------|------|------|
| 0 情報収集 | ✅done | collector | — | 2026-08-19T04:41 | PASS(#0) | 素材147件 |
| 1 テーマ選定 | ✅done | triage | 2026-08-19 | 2026-08-19 | PASS(#1) | `production/outline.md` |
| 2 スクリプト | ✅done | scriptwriter | 2026-08-19 | 2026-08-19 | 自己点検PASS(#2) | draft-A/B/C/D 完成。正式検査は Phase 4 |
| 3 視覚素材 | ✅done | asset-fetcher | 2026-08-19 | 2026-08-23 | 自己点検PASS(#3) | 写真ファースト改訂版。下記サマリー参照 |
| 4 品質検査 | ⬜todo | — | — | — | — | — |
| 5 統合 | ⬜todo | — | — | — | — | — |

## Phase 1 選定結果サマリー

- 採用話題（B構成・Phase 2検証後）: ①30年債19年ぶり高値と半導体急落の連鎖 ②AI資金調達の構造転換（NVDA×鉄道泡沫類推） ③分裂するFRB ④K型消費と小売決算（Home Depot・目標株価370ドル）
- C. News Highlights: 8本選定済み（TSMC売上／CoreWeave／Cerebras／Anthropic収益／Meta裁判／ペルトン／バークシャー／Airbnb。基準=株価・市場への直接影響＋同一事実の重複のみ排除）
- D（直近イベント予告）: 実施（8/19 FOMC議事録・Target・Lowe's・TJX・ADI、8/20 Walmart・Ross・新規失業保険申請）
- Gate #1: PASS（採点・核心予告4話題・B核心割当・サスペンスフック・C速報8本・D要否すべて確認済み）

## 差戻しログ

- 2026-08-19 Phase 2 選題検証パス: 元B-4「宇樹科技IPO」を米国株関連性ゲート不通過で除外（一涨一跌の表面的対比で内在的繋がりなし）。K型消費・小売決算をB-4へ昇格、`outline.md` 修正済み。C-6 アント分社→ペルトンへ差し替え。規範側にもハードゲート追加（phase1/phase2）。
- 2026-08-19 Phase 2 事実確認: D表の決算日付誤りを修正（Lowe's/TJX/ADI/FOMC議事録は8/19、Walmart/Ross/失業保険申請は8/20）。
- 2026-08-19 Phase 2 言語品質ゲート追加: 中国語素材起因の簡体字残留・直訳表現・中国語企業名/媒体名を禁止し、中国企業名は正式英語名（出所表示は WallstreetCN/36Kr 等）へ統一。draft-B の「华尔街见闻」残留を修正。

## Phase 2 完了サマリー

- draft-A: 四問予告（先頭・快テンポ）→ 前日市況総括（三指数／値上がり・値下がりブロック／その他市場バー／要点の固定カード版式に対応）。シーン6個
- draft-B: B-1長期金利と半導体急落／B-2 AI資金調達／B-3分裂FRB／B-4 K型消費と小売決算（目標株価370ドル）。シーン19個（旧B-0はA-2へ統合）
- draft-C: News Highlights 8本（タイトル中心）。シーン8個
- draft-D: 直近イベント予告（8/19 FOMC議事録・4社決算、8/20 Walmart・Ross・失業保険）。シーン3個
- Gate #2 自己点検: データ密度・出所表示・鉄則二（HD 370ドル）・言語品質スキャン（簡体字残留なし）確認済み
- Phase 3 トリガ: シーン表の必要アセット計10種（nvidia/anthropic/coreweave/cerebras/tsmc/federal-reserve/meta/berkshire/home-depot/target/walmart）
- 2026-08-19 A構成改訂: 予告→総括の順に変更、セクター動向（値上がり・値下がり筆頭）とその他市場（米債・金・BTC・WTI）を総括へ追加。固定カード版式を `daily-template.md`／`content-framework.md`／`vision-design.md` §3 へ定義済み。
- 2026-08-19 B-0廃止: 市場構造の前提をA-2市況総括の後半（分析パート）へ統合し、A→B の接続を連続化。B は B-1 から直接開始。
- 2026-08-20 A-1冒頭文の自然化: 「本日の目玉、四つの問いです。」→「本日は以下4つのテーマを取り上げます。」に変更。冒頭・締めフレーズを `content-framework.md` A.② に固定句として定義。

## Gate #0 評価

- [✓] カテゴリカバレッジ（6種） — MKT=1 MAC=1 RES=36 STK=15 ERN=31 NWS=63
- [✓] 素材数（基準≥30） — total=147
- [✓] 全素材URL完備 — url欠落=0 / 擬似URL=
- [✓] 全素材body非空 — body空=0
- [✓] 長文密度（≥500字が過半） — ≥500字=138/147
- [✓] 記録外ファイルなし — 不正=0 
- [ ] 仕事が1つ以上（警告） — longbridge(skip),market,rss(skip),wscn(skip),36kr(skip),insights(skip),email(skip)
- [✓] 収集チャネル健康（通知のみ・合否には影響しない） — 全OK
- ⚠️ 警告: 仕事が1つ以上（警告） — longbridge(skip),market,rss(skip),wscn(skip),36kr(skip),insights(skip),email(skip)


## Gate #0 独立再評価（ファイルシステム実体）

- [x] 独立再評価 (verify-collection): PASS

## Phase 3 完了サマリー（2026-08-23 完了）

- 設計原則改訂（2026-08-23）: メインビジュアルにロゴを据えない「実写写真ファースト」を適用（`spec/vision-design.md` §0.8）。シーン表の `logo:*` トリガに対し、単独表示は本社実写写真、人物論点は本人写真、抽象概念は文生图で対応。ロゴは補助要素として保持。
- 本社実写写真 12点（`assets/photos/`・brandsキャッシュ `assets/brands/companies/` にも保管）: nvidia/apple/microsoft/hd/tsmc/meta/berkshire/federal-reserve/target/walmart/anthropic/coreweave（出所: Wikimedia Commons / SearXNG画像検索、`_sources.log` 参照）
- 人物写真 2点（`assets/people/`）: jim-cramer.jpg（CNBC公式CDN）／ben-thompson.jpg（Stratechery公式ポートレート）
- 文生图概念図 5点（`assets/concepts/`・qwen-image-3.0-pro・1600x900）: opening-visual／discount-rate／bubble-history／capital-curve／k-shaped-consumption
- ロゴ 9点（補助・`assets/brands/companies/`）: nvidia/aapl/microsoft/tsmc/meta/brk/federal-reserve/anthropic/cerebras（Wikimedia Commons）。hd/target/walmart/coreweave のロゴは未取得（写真ファーストのため非ブロッキング）
- 検索レイヤ: 429発生時は SearXNG 自部署（`tools/searxng/search.ps1`）を優先使用（`phases/phase3-asset-fetching.md` 改訂済み）
- 全アセットを `assets/brands/manifest.md` に登記済み（29行追記）
- シーン表との不一致: なし（シーン表の必要アセットは全て写真/概念図/ロゴのいずれかで充足）

### Gate #3 自己点検

- [x] 採用素材の必要画像が漏れなく取得されている（シーン表36シーン全てに対応アセット割当済み）
- [x] 本社実写（単独用）・ロゴ（補助）・人物・概念図が揃い、manifest.md に追記済み
- [x] 取得画像は全て PIL/ヘッダ検証済み（破損なし）
- [x] Stage S2（画面HTML）完了: `visual.html` 作成（39画面・45画像参照・検証済み）

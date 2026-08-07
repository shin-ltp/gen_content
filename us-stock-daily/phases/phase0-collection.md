# Phase 0：情報収集（collector-agent）

> 旧 PLAN.md 第三章（3.1〜3.8）。DB 層との統合は [../infra/database-layer.md](../infra/database-layer.md)、ロゴキャッシュは [../infra/brand-asset-cache.md](../infra/brand-asset-cache.md)。状態: ✅ 定義済み。

---

## 目的と収集原則

> **収集の鉄則：宁可多取、不可漏掉（多く取り過ぎてもよいが、絶対に漏らさない）**
>
> 収集エージェントの役割は「幅広く集めること」であって「絞り込むこと」ではない。
> - 米国株に関連する情報は**可能な限りすべて**収集する。重複・些末は気にしない（後段の Phase 1 が選別する）。
> - 取捨選択は collector の仕事ではない。**質の判断・優先度付けは triage-agent（Phase 1）に委ねる。**
> - 「これは使うか不明」でも残す。使わなかった素材が残るのは正しい状態。

> **収集前の前提: データの鮮度階層（[database-layer.md](../infra/database-layer.md) §2）**
> 「多く取る」のは**変動データ（Tier A）**について。決算財務・マクロ指標・経済カレンダー・目標株価などの**定期更新データ（Tier B）**は毎日再取得せず、**ローカル DB から読む**。DB 上で FRESH なら再取得を省き、当日素材の `key_data` に DB 値を転記すればよい。

---

## 遅延取得戦略（テキスト＋URL 先行、画像は後で）

重い取得処理（Web ページのスクロール・画像保存・チャート抽出）は Phase 0 では**一切行わない**。

| 何を | Phase 0（今） | Phase 3（後で） |
|------|--------------|----------------|
| 本文テキスト・要点 | ✅ 保存 | — |
| ソース URL | ✅ 保存 | — |
| 核心データ（数値） | ✅ 抽出して保存 | — |
| 出所・時刻 | ✅ 保存 | — |
| スクリーンショット | ❌ 取得せず、`assets_needed` でフラグだけ | ✅ 採用時にクロール |
| 記事内チャート・画像 | ❌ 取得せず、フラグだけ | ✅ 採用時にクロール |
| 企業ロゴ・概念図 | ❌ | ✅ 必要時に取得（ロゴは `assets/brands/` 共有キャッシュ優先） |

> Phase 2 で素材がスクリプトに採用された瞬間、当該素材の `adopted` を `true` にし、Phase 3 の asset-fetcher-agent が `url` を読んで詳細を取得し `assets/` に保存する。ロゴは例外で回限定ではなく全日共有キャッシュから。

---

## 収集対象カテゴリと情報源マップ

収集は以下6カテゴリで行う。各情報源は [../data-sources/info-sources.md](../data-sources/info-sources.md) 参照。

| カテゴリ | ID 接頭辞 | 収集内容 | 主情報源 |
|----------|-----------|----------|----------|
| 市場データ | `MKT-` | 指数・為替（ドル円含む）・債券利回り・コモディティ・暗号・心理指標 | Finviz, TradingView, Yahoo, CNN Fear&Greed |
| マクロ経済 | `MAC-` | 経済指標・FRB・財政・金利予想・**為替政策・国際協調介入・米債需給・資金フロー**（2026-08-05 追加） | Investing.com, CME FedWatch, FRED, BLS, BEA, 財務省, 日本財務省・日銀 |
| 大手リサーチ | `RES-` | 投資銀行レポート・アナリストレーティング変更・目標株価 | Goldman/JPM Research, TipRanks, Seeking Alpha |
| 個別株・セクター | `STK-` | 決算以外の個別株・セクター動向・バリュエーション材料 | SEC EDGAR, 各社IR, SemiAnalysis, 媒体 |
| 決算 | `ERN-` | 決算発表・ガイダンス（決算シーズン中心） | SEC EDGAR, 各社IR, Reuters |
| ニュース速報 | `NWS-` | 当日の速報ニュース（M&A・規制・地政学等） | Bloomberg/WSJ メール, CNBC, Reuters, AP |

---

## 素材ファイル標準フォーマット

素材1件＝1ファイル。カテゴリ別フォルダに `{ID}.md` として保存。フロントマターでメタを管理する。

```markdown
---
id: STK-20260714-007              # {CAT}-{YYYYMMDD}-{連番}  一意ID
category: stocks                   # market|macro|research|stocks|earnings|news
ticker: NVDA                       # 該当銘柄（なければ空）
title: エヌビディア、需要見通しでGS目標株価引き上げ
source: Goldman Sachs Research     # 情報源名
source_type: research              # official|research|media|social|data
url: https://www.gs.com/...        # ソースURL（必須）
relevance: us-stock                # 米株関連（基本 us-stock）
collected_at: 2026-07-14T06:32     # 収集日時
collector: collector-agent         # 収集エージェント名
priority: TBD                      # A|B|C|TBD（Phase 1 が後で付与。収集時は TBD 可）
key_data:                          # 抽出した核心データ（リスト）
  - "目標株価 190ドル（+22%）"
  - "レーティング 買い継続"
assets_needed: [chart, table_image] # 後期取得したい画像種別（なければ []）
assets_status: none                 # none|pending|fetched（Phase 3 が更新）
adopted: false                     # スクリプト採用フラグ（Phase 2 が true に）
status: raw                        # raw|verified|adopted|dropped
---

## 概要
（本文テキスト・要点を簡潔に）

## 原文抜粋
（必要に応じて引用テキスト。長すぎる場合は要点のみ）

## 備考
（関連リンク・クロスチェック元・収集時の所感など）
```

**フォーマット規約:**
- `id` は カテゴリ接頭辞 + 日付 + 3桁連番。同日内で一意。
- `url` は**必須**。URLなき情報は原則採録しない（出所追跡不能のため）。
- `key_data` は後段のデータ密度チェックの原料。具体的な数値を入れる。
- 収集時点では `priority=TBD` `adopted=false` `status=raw` でよい。

---

## 素材マスター索引（manifest）フォーマット

`collection/00-manifest.md` に全素材の索引を1表で保持。Gate #0 の検査対象かつ、後段エージェントの「素材一覧」になる。

```markdown
# YYYY-MM-DD 収集素材マスター索引

> 収集エージェント: collector-agent | 収集日時: 2026-07-14 06:00〜06:50
> 合計: XX 件（MKT: / MAC: / RES: / STK: / ERN: / NWS: ）

## 索引
| ID | カテゴリ | 銘柄 | タイトル | 情報源 | タイプ | 優先度 | 画像要 | 状態 |
|----|----------|------|----------|--------|--------|--------|--------|------|
| MKT-20260714-001 | market | — | 主要指数・為替スナップ | Finviz | data | TBD | no | raw |
| MAC-20260714-002 | macro | — | CPI 予想上回る | BLS | official | TBD | chart | raw |
| STK-20260714-007 | stocks | NVDA | GS目標株価190へ引き上げ | Goldman | research | TBD | table | raw |
| ... | | | | | | | | |

## 収集カバレッジ（Gate #0 用）
- [x] 市場データ（指数・為替・債券・心理）
- [x] マクロ（経済カレンダーの当日イベント網羅）
- [ ] 大手レーティング変更（要確認）
- ...
```

---

## 収集サブワークフロー（手順）

collector-agent は以下を順に実行する。各ステップで取得した素材を即座にファイル化する（メモリに貯めない）。

```
-1. ツールチェーン・ヘルスチェック（必須・2026-08-05 追加 / 2026-08-06 自己修復強化）
   - 検索チャネル: `powershell tools/searxng/search.ps1 -Check`（exit 0 で合格）。
     本机 SearXNG が未起動ならスクリプトが自動で `docker compose up -d` する（localhost 限定・自己修復、実測済み）。
     起動不可（Docker Desktop 未起動等）なら内蔵 `web_search` へフォールバック。
   - 行情データ: `tools/bin/longbridge.exe quote .SPX.US --format json`
     （「not authenticated」なら `longbridge auth login`＝Device Flow で再ログイン。
      復旧不能なら行情データを Web 検索源へ切替）
   - どちらかが不合格 → status.md に記録し、フォールバックへ切替。
     不合格を記録せずに収集へ進んではならない（試跑 P1 の教訓）。
   - 両チャネルの判定結果を status.md の備考欄に書く（例: 「検索: SearXNG自動起動OK / 行情: longbridge OK」）。
0. ワークスペース初期化
   - daily-output/YYYY-MM-DD/{collection,assets,production,review}/ を作成
   - status.md を todo で初期化
0.5. DB ヘルスチェック（定期更新データ層 — [database-layer.md](../infra/database-layer.md)）
   - db/refresh.py を実行し、effective_until <= now の定期データを一括更新（定期更新）
   - data_catalog の次回予定日を確認し、当日のマクロ発表イベントを把握
   - 以降のステップで Tier B データは DB 経由で取得（FRESH なら再取得しない／STALE なら能動更新）
1. 市場データ収集（MKT）
   - 指数/為替/債券/コモディティ/暗号/心理 を網羅
2. マクロ収集（MAC）
   - 経済カレンダーの当日イベントを漏れなく拾う（予想・前回値付き）
3. レーティング・リサーチ収集（RES）
   - 当日の主要レーティング変更・目標株価改定を幅広く
4. 個別株・セクター収集（STK / ERN）
   - 当日の注目銘柄・セクター動向、決算シーズンは ERN を厚く
5. ニュース収集（NWS）
   - 朝のメール・リアルタイム・ソーシャルを幅広く
5.5. ターゲット深度収集（Phase 1 の選題後にループで実行・2026-08-05 追加）
   - Phase 1 が選定した各核心話題（特に個別株）に対し、以下を補収集する:
     a) 競争力の源泉・護城河（経営陣の差別化主張の一次ソース含む）
     b) 競争格局（主要競合・業界標準化の動向）
     c) 市場規模・業界調査（TAM・企業支出調査）
     d) 市場の当下的関心との接続材料（当該局面の中心テーマ）
   - 収集→選題は一方通行ではなく、選題後に収集へ戻るループを許容する
     （DAG 注記: Phase 1 → 5.5 → Phase 2）
6. 索引作成
   - 00-manifest.md を生成（カバレッジチェック付き）
7. Gate #0 自己点検 → status.md に PASS/FAIL を記録
```

---

## Phase 0 品質ゲート（Gate #0 検査基準）

Gate #0 は collector-agent の自己点検＋スケジューラの承認で構成。**すべて合格で Phase 1 へ**。

| # | 検査項目 | 基準 | 不合格時の対応 |
|---|----------|------|----------------|
| 1 | **カバレッジ** | 6カテゴリすべてに素材 ≥1件。情報源チェックリストの「必須源」を網羅 | 不足カテゴリを追加収集 |
| 2 | **定量** | 1日あたり素材 ≥ 30件（決算/FOMC週は ≥ 50件）を目安 | 追加収集 |
| 3 | **関連性** | 全素材 `relevance=us-stock`。米株無関係は除外 | 除去 |
| 4 | **網羅性（最重要）** | 「固定放送資産」と「当日の経済カレンダーイベント」に**漏れがないこと**。固定放送資産には以下を含む: 指数スナップ／心理指標／経済カレンダー／**為替政策・協調介入の当日ニュース**／**米債・資金フローの大きな動き**（2026-08-05 追加。再試跑で米日共同介入を完全に見落とした教訓） | 漏れを補収集 |
| 5 | **URL 完備** | 全素材に `url` あり | URL を補完、不可なら除外 |
| 6 | **重複** | 同一ニュースの重複なし（要約統合可） | 統合 |
| 7 | **索引完全性** | `00-manifest.md` の行数 ＝ `collection/` 内の素材ファイル数 | 整合 |
| 8 | **DB 定期データの鮮度** | 当日参照する Tier B が DB 上で FRESH（`now < effective_until`）。STALE/欠損は能動更新で解消 | 該当データを能動更新 |

> 「宁可多取」原則により、**量の超過は不合格理由にならない**。不合格は「漏れ」または「形式不備」のみ。ただし Tier B データは DB キャッシュで供給するため、検査8 は「当日分として fresh か」のみを問う。

---

## 収集作業ディレクトリ構造

```
daily-output/YYYY-MM-DD/
└── collection/
    ├── 00-manifest.md                  # 素材マスター索引＋カバレッジ（Gate #0 対象）
    ├── 01-market.md                    # 市場データ（1ファイルにスナップまとめる可）
    ├── 02-macro/                       # マクロ経済（1素材1ファイル）
    │   ├── MAC-YYYYMMDD-001.md
    │   └── MAC-YYYYMMDD-002.md
    ├── 03-research/                    # 大手リサーチ
    │   └── RES-YYYYMMDD-001.md
    ├── 04-stocks/                      # 個別株・セクター（銘柄別サブフォルダ可）
    │   ├── NVDA/
    │   │   └── STK-YYYYMMDD-007.md
    │   └── TSLA/
    ├── 05-earnings/                    # 決算（シーズン中のみ）
    └── 06-news/                        # ニュース速報
        └── NWS-YYYYMMDD-001.md
```

- `01-market.md` はスナップショット性が高いので1ファイル集約可。それ以外は原則 **1素材1ファイル**（並列収集・個別資産取得しやすさのため）。
- 銘柄別サブフォルダ（`04-stocks/NVDA/`）は同一銘柄の素材が複数ある時に使用。1件でも平置きで可。
- 画像等は Phase 3 までこのディレクトリには置かない（`../assets/` に格納）。

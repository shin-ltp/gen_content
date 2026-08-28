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

> Phase 2 で素材がスクリプトに採用された時点で `adopted` を `true` に更新する。画像取得は Phase 2 終選後の
> **視覚設計ブリーフ** が正式トリガとなり、Phase 3 がブリーフの候補アセット一覧をもとに取得して `assets/` に
> 保存する（2026-08-28 改訂）。ロゴは例外で回限定ではなく全日共有キャッシュから。

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
6. 索引作成 + Gate #0 自動検査（2026-08-18 自動化）
   - `node tools/collect/collect-all.mjs` が 00-manifest.md 生成と Gate #0 評価を自動実行する
   - Gate #0 不合格時は **exit code 2** を返し、後段 Phase 1 へ進めない（スケジューラはこの終了コードを確認する）
   - 各検査項目の結果は status.md と 00-manifest.md に記録される
   - `--no-gate` は記録のみ・ブロックしない明示的な逃生口（デバッグ用）
   - **Gate 判定方針（2026-08-19 改定）**: Gate #0 の合否は「集まったコンテンツの品質」のみで判定する。
     6カテゴリカバー・素材数・長文密度・URL・body・索引整合のいずれかが欠ければ FAIL とする。
     一方で「特定チャネルが全て成功したこと」は Gate の条件にしない（警告・通知扱い）。
     収集チャネルに失敗が出ても、他源でカテゴリと深さが揃っていれば Phase 1 に進める。
   - **異常メール通知（2026-08-19 追加）**: 最終検査後に以下の場合、`.env` の
     `NOTIFY_EMAIL`（既定: choshin.ltp@gmail.com）へ Gmail SMTP で通知する:
       1. 1つ以上の信源が異常終了・タイムアウトで取得失敗した場合
       2. Gate #0 の内容判定が不合格（`exit 2`）になった場合
     - ユーザー指定の `--skip` および API key 未設定などによる明示的 SKIP は「異常」とみなさない
     - 手動確認用: `node --use-system-ca tools/collect/notify-email.mjs --test`
   - **独立再評価（2026-08-19 追加）**: `collect-all.mjs` は最後にソースファイル実体に基づく
     `verify-collection.mjs` を再実行し、メモリ上の結果と二重で検証する。索引未生成・0バイト
     ファイル・一時ファイル残存などの「見た目だけ合格」をブロックする。
   - **実行方法（重要・2026-08-19 実測）**: リポジトリルート（`C:\my_project\gen-contents`）から
     `node --use-system-ca us-stock-daily/tools/collect/collect-all.mjs --date YYYY-MM-DD` で実行する。
     - `--use-system-ca` は必須。Codex 沙箱の Node は既定でシステムCAを使わず、Gmail IMAP 等 TLS 検証に失敗する
     - `us-stock-daily/tools/collect` 内（pnpm junction 配下）を作業ディレクトリにして実行すると、
       沙箱が実パスを `.pnpm-store` に解決し、子プロセスから `daily-output` への書き込みが
       EPERM で全滅する。**必ずリポジトリルートから実行すること**
   - **収集器構成メモ（2026-08-19）**:
     - `market`（Yahoo Finance 公共API・認証不要）: MKT スナップ + MAC（米10年/2年金利）+ STK（主要銘柄）を供給
     - `email`（Gmail IMAP・アプリパスワード認証）: Bloomberg / WSJ / Yahoo / Reuters / SemiAnalysis の朝報
     - `rss` の CNBC Earnings フィード（`cnbc-biz`）は **ERN カテゴリ**として収集（Gate #0 の決算カバレッジ源）
     - WSCN / 36kr は反爬対策として記事間 2.5〜4秒のランダム間隔＋連続失敗時のクールダウン／打ち切り。
       **本文取得に失敗した記事はファイルを保存しない**（失敗素材による汚染防止。次回実行で自動再試行）
```

---

## Phase 0 品質ゲート（Gate #0 検査基準）

Gate #0 は `collect-all.mjs` による自動評価＋スケジューラの承認で構成。**すべて合格で Phase 1 へ**。
不合格時は exit code 2 を返し、後段 Phase 1 は開始しない（集めた素材は残るので、補収集後の再実行で再評価できる）。
（2026-08-18 自動化: 旧「条件PASS」運用は廃止。数量・長文密度もハード不合格項目に変更済み。）

| # | 検査項目 | 基準 | 不合格時の対応 |
|---|----------|------|----------------|
| 1 | **カバレッジ** | 6カテゴリすべてに素材 ≥1件。**どの信源由来かは問わない**（内容で判定） | 不足カテゴリを追加収集 |
| 2 | **定量** | 1日あたり素材 ≥ 30件（ハード／環境変数 `GATE0_MIN` で調整可） | 追加収集して再実行 |
| 3 | **関連性** | 全素材 `relevance=us-stock`。米株無関係は除外 | 除去 |
| 4 | **網羅性（最重要）** | 「固定放送資産」と「当日の経済カレンダーイベント」に**漏れがないこと**。固定放送資産には以下を含む: 指数スナップ／心理指標／経済カレンダー／**為替政策・協調介入の当日ニュース**／**米債・資金フローの大きな動き**（2026-08-05 追加。再試跑で米日共同介入を完全に見落とした教訓） | 漏れを補収集 |
| 5 | **URL 完備** | 全素材に `url` あり | URL を補完、不可なら除外 |
| 5.5 | **本文完備** | 全素材 body 非空。素材の過半が ≥500字（ハード） | 全文取得し直して再実行 |
| 6 | **重複** | 同一ニュースの重複なし（要約統合可） | 統合 |
| 7 | **索引完全性** | `00-manifest.md` の行数 ＝ `collection/` 内の素材ファイル数 | 整合 |
| 8 | **DB 定期データの鮮度** | 当日参照する Tier B が DB 上で FRESH（`now < effective_until`）。STALE/欠損は能動更新で解消 | 該当データを能動更新 |
| 9 | **チャネル健康（警告）** | 収集チャネルに異常終了・タイムアウトがないこと。**Gate 合否には影響しない** | 失敗チャネルを個別に再実行し、`NOTIFY_EMAIL` へ通知 |
| 10 | **コレクター動作（警告）** | 1 つ以上のコレクターが成功していること。**Gate 合否には影響しない** | 全失敗原因を調査 |

> 「宁可多取」原則により、**量の超過は不合格理由にならない**。不合格は「漏れ」または「形式不備」のみ。ただし Tier B データは DB キャッシュで供給するため、検査8 は「当日分として fresh か」のみを問う。
>
> 自動検査の実装上は「素材数（検査2）」「長文密度（検査5.5）」「body非空（検査5.5）」「URL完備（検査5）」「カテゴリカバレッジ（検査1）」「記録外ファイルなし（検査7に相当）」を `collect-all.mjs` が Gate 合格条件として評価する。「チャネル健康（検査9）」「仕事が1つ以上（検査10）」は警告・メール通知用の記録であり、Gate 合否には影響しない。評価結果と不合格項目は `status.md`・`00-manifest.md` に書き出される。

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

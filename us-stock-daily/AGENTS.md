# Smart Assets米国株投資チャンネル — エージェント作業ガイド

## プロジェクト概要
本プロジェクトは毎日更新される米国株式市場分析番組の制作システムです。
毎回30-40分、個人投資家向け、長期・安定志向スタイル。

**出力言語: 日本語** | **ターゲット: 日本の個人投資家**

> 全体地図は [README.md](./README.md)。マスター計画は [PLAN.md](./PLAN.md)。

## 制作ワークフロー（マルチエージェント・多段階）

制作は単一エージェントへの丸投げではなく、**Phase 0〜5 の多段階ワークフロー**で進行します。
各 Phase の定義・DAG・品質ゲート・`status.md` 運用は **[phases/overview.md](./phases/overview.md)** を、各 Phase の詳細仕様は `phases/phaseN-*.md` を参照。

| Phase | 名称 | 担当エージェント | 主出力 | 仕様 |
|-------|------|------------------|--------|------|
| 0 | 情報収集 | collector-agent | `collection/` | [phase0](./phases/phase0-collection.md) |
| 1 | テーマ選定・構成 | triage-agent | `production/outline.md` | [phase1](./phases/phase1-triage.md) |
| 2 | スクリプト制作 | scriptwriter-agent | `production/draft-*.md` | [phase2](./phases/phase2-scriptwriting.md) |
| 3 | 視覚素材取得（遅延クロール） | asset-fetcher-agent | `assets/` | [phase3](./phases/phase3-asset-fetching.md) |
| 4 | 品質検査 | qa-agent | `review/qa-report.md` | [phase4](./phases/phase4-qa.md) |
| 5 | 統合・最終化 | integrator-agent | `YYYY-MM-DD.md` | [phase5](./phases/phase5-integration.md) |

> 各 Phase は品質ゲート（Gate #0〜#4）を通過しない限り次へ進みません。進行状況は各日の `status.md` で一元管理します。

## 番組構成（A → B → C → D）

線形の4ブロック＋免責。**内容の唯一の情報源は [spec/content-framework.md](./spec/content-framework.md)**、**視覚仕様は [spec/vision-design.md](./spec/vision-design.md)**（テンプレート各部と1対1）、**完成スクリプトのひな形は [templates/daily-template.md](./templates/daily-template.md)**。

| コーナー | 時間 | 核心定位 |
|---|---|---|
| **A. オープニング** | 2-3分 | 前日市況を自然言語で総括 → 3-5話題を各1文で予告 → サスペンス。俳句は任意の表現形式 |
| **B. メインテーマ** | 25-40分・核心 | 候補5テーマを各7-12分で執筆→B合計25-40分で終選（3-5テーマ）。昨日注目セクター・個別株深層分析（必須・先頭）→ 行動結論 |
| **C. News Highlights** | 2-3分 | 8本の精選ニュース・タイトル中心 |
| **D. 直近イベント予告** | 0-2分・非固定 | 直近3営業日の重要イベント。該当なければスキップ |
| 免責事項 | — | 学習目的・投資助言ではない旨 |
| エンディング挨拶 | 約30秒 | 固定文言（高評価・登録依頼＋更新リズム＋次回休場なら休場予告） |

## ファイル構造

```
us-stock-daily/
├── README.md                       全体地図・索引
├── PLAN.md                         マスター計画書・タスクスケジューラ（核心参照）
├── AGENTS.md                       本ファイル
├── BENCHMARK_ANALYSIS.md           ベンチマークチャンネルの方法論分析
├── spec/                           番組仕様（内容・視覚・コンプラ・バリュエ）
│   ├── content-framework.md          内容フレームワーク（A/B/C/D・鉄律）★唯一の情報源
│   ├── vision-design.md              視覚デザイン仕様
│   ├── compliance.md                 コンプライアンス・免責事項
│   └── valuation.md                  バリュエーション＋アクション指針
├── phases/                         各 Phase 詳細仕様
│   ├── overview.md                   Phase一覧・DAG・品質ゲート・status形式
│   └── phase0〜5-*.md                Phase 0〜5 各詳細
├── infra/                          インフラ層
│   ├── database-layer.md             ローカルDB層（定期更新データ）
│   └── brand-asset-cache.md          ブランドロゴ共有キャッシュ
├── templates/                      各種テンプレート
│   ├── daily-template.md             完成スクリプトのひな形
│   └── daily-workflow-checklist.md   毎日制作チェックリスト（人間用）
├── data-sources/                   情報源メタ・バリュエーションガイド
│   ├── info-sources.md               情報源一覧＋ツールチェーン
│   ├── account-checklist.md          情報源登録チェックリスト
│   └── sector-valuation-guide.md     セクター別バリュエーション早見表
├── db/                             定期更新データ層（詳細は infra/database-layer.md）
├── assets/brands/                  ブランドロゴ共有キャッシュ（詳細は infra/brand-asset-cache.md）
└── daily-output/YYYY-MM-DD/        1日＝1ディレクトリ（ワークスペース）
    ├── status.md                     Phase 進行状況・品質ゲート結果
    ├── YYYY-MM-DD.md                 Phase 5 最終完成スクリプト
    ├── collection/                   Phase 0 成果物（素材＋索引）
    ├── assets/                       Phase 3 遅延取得画像・チャート
    ├── production/                   Phase 1-2 中間成果物
    └── review/                       Phase 4 品質ゲート検査レポート
```

## コンテンツ制作規範

### 言語
- 全コンテンツは日本語で執筆
- 専門用語は初出時に英語原文を併記
- データ引用は出所と時刻を明記

### 制作不変原則（二つの鉄律）
詳細は [spec/content-framework.md §1](./spec/content-framework.md)。要点：
- **鉄則一**: オープニング（A）は指数の羅列（流水帳）で終わらせない。自然言語で前日市況を総括し、3-5話題を各1文で予告してサスペンスを作る。
- **鉄則二**: 個別株／セクター分析には大手目標株価＋具体的アクション価格を必ず示す（[spec/valuation.md](./spec/valuation.md)）。

### オープニング俳句
- A の冒頭のフック（任意の表現形式）。当日の核心を5-7-5音の俳句で（1-3句）。
- 内容が凝縮できる時のみ採用。制作は全コーナー完成後に実施（Phase 5）。
- 視覚仕様（浮世絵富嶽三十六景背景・行書フォント）は [spec/vision-design.md §1](./spec/vision-design.md)。

### コンプライアンス要件
- 直接的な買い／売り推奨は絶対に行わない（「私ならこう動きます」形式）
- いかなる収益率も約束しない
- 冒頭と末尾に免責事項を必ず含める
- A の最も冒頭に固定の番組紹介、末尾免責の直後にエンディング挨拶（固定文言）を置く（[spec/content-framework.md](./spec/content-framework.md)）
- データは必ず出所を明記
- 日本の金融商品取引法上の「投資助言業」ではない（情報提供・学習目的）旨を明示
- 詳細は [spec/compliance.md](./spec/compliance.md)

### バリュエーション方法
- 業界によりバリュエーション手法を使い分ける（[data-sources/sector-valuation-guide.md](./data-sources/sector-valuation-guide.md)／[spec/valuation.md](./spec/valuation.md) 参照）
- 最低2-3の手法で交差検証
- 精度の高い単一値ではなく **レンジ** で示す

### 情報収集（Phase 0 の原則）
- 無料情報源を優先。モーニングレターは既に選別済みのメール購読を優先
- **多く取り過ぎてもよいが、絶対に漏らさない**：収集段階では幅広く集め、絞り込みは Phase 1（triage-agent）に委ねる
- 収集時は **テキスト＋URLのみ保存**、画像・チャートは採用後に遅延取得（Phase 3）
- **定期更新データ（Tier B）はローカル DB 経由で取得**：決算財務・マクロ指標・経済カレンダー・目標株価は毎日再取得せず `db/` の SQLite から読む。詳細は [infra/database-layer.md](./infra/database-layer.md)

## インストール済みツール（Skills）

[data-sources/info-sources.md](./data-sources/info-sources.md)「ツールチェーン」を参照。

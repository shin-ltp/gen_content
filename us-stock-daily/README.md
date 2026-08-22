# 米国株式デイリー深層分析 — プロジェクト入口

毎日更新される米国株式市場分析番組の制作システム。毎回30-40分、個人投資家向け、長期・安定志向スタイル。**出力言語: 日本語** | **ターゲット: 日本の個人投資家**。

本READMEはプロジェクト全体の地図です。目的別に対応ドキュメントへ進んでください。

---

## クイックナビゲーション（目的別）

| 読みたいこと | 行き先 |
|---|---|
| 番組の全体構成（何を・どの順で話すか） | [spec/content-framework.md](./spec/content-framework.md) |
| 画面の見せ方（色・レイアウト・アニメ・画像） | [spec/vision-design.md](./spec/vision-design.md) |
| 完成スクリプトのひな形（埋める枠） | [templates/daily-template.md](./templates/daily-template.md) |
| 制作工程（Phase 0〜5・品質ゲート） | [phases/overview.md](./phases/overview.md) |
| マスター計画書・スケジューラ | [PLAN.md](./PLAN.md) |
| コンプラ・免責 | [spec/compliance.md](./spec/compliance.md) |
| バリュエーション＋アクション指針 | [spec/valuation.md](./spec/valuation.md) |
| 情報源・ツール | [data-sources/info-sources.md](./data-sources/info-sources.md) |
| ベンチマーク（美投侃新聞）の方法論 | [BENCHMARK_ANALYSIS.md](./BENCHMARK_ANALYSIS.md) |

---

## 番組構成（A → B → C → D）

線形の4ブロック＋免責。B が核心。詳細は [content-framework.md](./spec/content-framework.md)。

| 放送順 | コーナー | 時間 | 一言 |
|---|---|---|---|
| A | オープニング | 2-3分 | 前日市況の自然言語総括＋3-5話題予告＋（任意）俳句 |
| **B** | **メインテーマ** | **約30分** | 昨日注目セクター/個別株深層分析（先頭）→3-5記事解説→行動結論 |
| C | News Highlights | 2-3分 | 8本・タイトル中心 |
| D | 直近イベント予告 | 0-2分 | 直近3営業日（非固定） |
| — | 免責事項 | — | 学習目的・投資助言ではない |

---

## ドキュメント一覧（全体構造）

```
us-stock-daily/
├── README.md                       本ファイル（全体地図・索引）
├── PLAN.md                         マスター計画書・タスクスケジューラ（薄型）
├── AGENTS.md                       エージェント作業ガイド
├── BENCHMARK_ANALYSIS.md           ベンチマークチャンネルの方法論分析（参照資料）
│
├── spec/                           番組仕様書群
│   ├── content-framework.md          内容フレームワーク（A/B/C/D・二つの鉄律）★唯一の情報源
│   ├── vision-design.md              視覚デザイン仕様（色・レイアウト・アニメ・画像）
│   ├── compliance.md                 コンプライアンス・免責事項
│   └── valuation.md                  バリュエーション＋アクション指針規範
│
├── phases/                         各 Phase 詳細仕様
│   ├── overview.md                   Phase一覧・DAG・品質ゲート・status.md形式
│   ├── phase0-collection.md          情報収集 ✅定義済み
│   ├── phase1-triage.md              テーマ選定・構成
│   ├── phase2-scriptwriting.md       スクリプト制作
│   ├── phase3-asset-fetching.md      視覚素材取得
│   ├── phase4-qa.md                  品質検査
│   └── phase5-integration.md         統合・最終化
│
├── infra/                          インフラ層仕様
│   ├── database-layer.md             ローカルDB層（定期更新データ）
│   └── brand-asset-cache.md          ブランドロゴ共有キャッシュ
│
├── templates/
│   ├── daily-template.md             完成スクリプトのひな形
│   └── daily-workflow-checklist.md   毎日制作チェックリスト（人間用）
│
├── data-sources/
│   ├── info-sources.md               情報源一覧＋ツールチェーン
│   ├── account-checklist.md          情報源登録チェックリスト
│   └── sector-valuation-guide.md     セクター別バリュエーション早見表
│
├── db/                             定期更新データ層（market-data.sqlite3 他・将来実装）
├── assets/brands/                  ブランドロゴ共有キャッシュ（manifest.md）
└── daily-output/YYYY-MM-DD/        1日＝1ディレクトリ（ワークスペース）
```

---

## ドキュメント間の関係

- **内容（何を話すか）** = [content-framework.md](./spec/content-framework.md)（唯一の情報源）→ [daily-template.md](./templates/daily-template.md) がその埋め込み枠
- **視覚（どう見せるか）** = [vision-design.md](./spec/vision-design.md)（テンプレート各部と §1〜§7 で1対1）
- **工程（どう作るか）** = [phases/](./phases/) → [PLAN.md](./PLAN.md) がスケジューラ
- **インフラ（何をキャッシュするか）** = [infra/](./infra/)

---

## メモ

- **エンコーディング**: 既存ファイルは UTF-8（BOMなし）。新規ファイルもこれに合わせる（ルート `../AGENTS.md` の「BOM付き」規則は実態と乖離しているため、混在を避け BOMなしで統一）。
- エージェント中心の制作ワークフロー（Phase 0〜5）と、人間用チェックリスト（[templates/daily-workflow-checklist.md](./templates/daily-workflow-checklist.md)）は並存。後者の「フェーズ1/2/3」は概ね Phase 0 / Phase 1-2 / Phase 4-5 に対応する。

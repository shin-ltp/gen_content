# 米国株式デイリー深層分析 — 番組制作計画書

> バージョン: v5.1 | 更新日: 2026-08-04
> 番組定位: 毎日30-40分 | 個人投資家向け | 長期投資＋実践的アクション指針
> **出力言語: 日本語** | **ターゲット: 日本の個人投資家**
> ベンチマーク: [美投侃新聞チャンネルの方法論](./BENCHMARK_ANALYSIS.md)

---

> **本書の役割**: 本書は「**マスター計画書兼タスクスケジューラ**」です。番組定位・ワークフロー設計思想・Phase モデル概観・品質ゲート一覧・日次ワークスペース構造のみを記述し、**詳細仕様は各ドキュメントへ委譲**します。全体地図は [README.md](./README.md)。

---

## ドキュメント構成（詳細は各ファイルへ）

| 関心 | ドキュメント |
|------|--------------|
| 全体地図・索引 | [README.md](./README.md) |
| 内容フレームワーク（A/B/C/D・鉄律） | [spec/content-framework.md](./spec/content-framework.md) |
| 視覚デザイン仕様 | [spec/vision-design.md](./spec/vision-design.md) |
| コンプライアンス・免責 | [spec/compliance.md](./spec/compliance.md) |
| バリュエーション＋アクション指針 | [spec/valuation.md](./spec/valuation.md) |
| Phase 概観・DAG・ゲート・status形式 | [phases/overview.md](./phases/overview.md) |
| Phase 0〜5 各詳細 | [phases/phase0-collection.md](./phases/phase0-collection.md) 〜 [phase5-integration.md](./phases/phase5-integration.md) |
| ローカルDB層（定期データ） | [infra/database-layer.md](./infra/database-layer.md) |
| ブランドロゴキャッシュ | [infra/brand-asset-cache.md](./infra/brand-asset-cache.md) |
| 情報源一覧・ツールチェーン | [data-sources/info-sources.md](./data-sources/info-sources.md) |
| 完成スクリプトひな形 | [templates/daily-template.md](./templates/daily-template.md) |

---

## 一、番組定位

毎日30-40分の米国株深層分析番組。日本の個人投資家向け。単なるニュース読み上げではなく：

- **専門情報提供者** — 複数の権威ある情報源を集約し、専門的で深い解説を提供する
- **実践的アクション指導者** — 実行可能な価格水準とポジションサイズの目安を示す
- **長期投資の提唱者にして個人の守り手** — リスナーの分散投資・適正ポジション管理・リスク管理への意識を高め、長期投資の理念で「個人がウォール街に勝つ」ことを目指す

詳細は [spec/content-framework.md §0](./spec/content-framework.md)。

---

## 二、マルチエージェント・ワークフロー全体設計

制作は単一エージェントへの丸投げではなく、**複数サブエージェント×多段階フェーズ**のワークフロー。設計思想（工程の分割・責任の局所化・成果物の永続化・段階的品質ゲート・遅延取得）と Phase モデル・DAG・品質ゲート・日次ワークスペース管理は [phases/overview.md](./phases/overview.md) に集約。

### Phase モデル概観

| Phase | 名称 | 担当エージェント | 主出力 | 仕様 | 状態 |
|-------|------|------------------|--------|------|------|
| **0** | 情報収集 | `collector-agent` | `collection/` | [phase0](./phases/phase0-collection.md) | ✅ 定義済み |
| **1** | テーマ選定・構成 | `triage-agent` | `production/outline.md` | [phase1](./phases/phase1-triage.md) | 🚧 補完 |
| **2** | スクリプト制作 | `scriptwriter-agent` | `production/draft-*.md` | [phase2](./phases/phase2-scriptwriting.md) | 🚧 補完 |
| **3** | 視覚素材取得 | `asset-fetcher-agent` | `assets/` | [phase3](./phases/phase3-asset-fetching.md) | 🚧 補完 |
| **4** | 品質検査 | `qa-agent` | `review/qa-report.md` | [phase4](./phases/phase4-qa.md) | 🚧 補完 |
| **5** | 統合・最終化 | `integrator-agent` | `YYYY-MM-DD.md` | [phase5](./phases/phase5-integration.md) | 🚧 補完 |

### 品質ゲート一覧（要点）

| Gate | 対象 Phase | 合格で進む先 |
|------|-----------|--------------|
| #0 | 情報収集 | Phase 1 |
| #1 | テーマ選定 | Phase 2 |
| #2 | スクリプト | Phase 4（+ Phase 3 並行） |
| #3 | 視覚素材 | Phase 4 |
| #4 | 品質検査（不合格→Phase 2 差戻し） | Phase 5 |

各 Gate の検査基準の詳細は対応 Phase ファイルと [phase4-qa.md](./phases/phase4-qa.md) 参照。進行状況は各日の `status.md` で一元管理（形式は [phases/overview.md](./phases/overview.md)）。

---

## 三、日次ワークスペースとファイル構造

```
us-stock-daily/
├── README.md / PLAN.md / AGENTS.md / BENCHMARK_ANALYSIS.md
├── spec/                      # 番組仕様（内容・視覚・コンプラ・バリュエ）
├── phases/                    # 各 Phase 詳細仕様
├── infra/                     # DB層・ロゴキャッシュ
├── templates/                 # 完成スクリプトひな形・制作チェックリスト
├── data-sources/              # 情報源メタ・バリュエーション早見表
├── db/                        # 定期更新データ層（派生データ・gitignore）
├── assets/brands/             # ブランドロゴ共有キャッシュ
└── daily-output/YYYY-MM-DD/   # 1日＝1ワークスペース
    ├── status.md              # Phase 進行状況・品質ゲート結果
    ├── YYYY-MM-DD.md          # Phase 5 最終完成スクリプト
    ├── collection/            # Phase 0 成果物
    ├── assets/                # Phase 3 遅延取得画像
    ├── production/            # Phase 1-2 中間成果物
    └── review/                # Phase 4 品質ゲート検査レポート
```

---

## 四、コンプライアンス要件（要点）

- 直接的な買い／売り推奨は絶対に行わない（「私ならこう動きます」形式）
- いかなる収益率も約束しない
- 冒頭と末尾に免責事項を必ず含める
- データは必ず出所を明記
- 日本の金融商品取引法上の「投資助言業」ではない（情報提供・学習目的）旨を明示

詳細は [spec/compliance.md](./spec/compliance.md)。

---

## 五、当前阶段：试跑（Trial Run）〔2026-08-04 起〕

> 现状：信息源整理（`data-sources/`）与节目大纲设计（`spec/`・`phases/`・`templates/`）**已基本完成，但仍停留在构想阶段，全流程从未实际试跑**；`db/` 定期数据层与 Phase 3 素材抓取均未实现。
>
> 本阶段目标：**用一次真实试跑打通"收集 → 整理 → 基础文字输出"链路**，通过试跑结果暴露问题与不足，确认输出的基础内容足够翔实后，再规划设计后继的生产环节（Stage S）。

### 试跑步骤（Stage T）

| 步骤 | 内容 | 产出（daily-output/2026-08-04/ 下） | 状态 |
|------|------|--------------------------------------|------|
| T1 | 试跑 Phase 0：6 类素材收集（MKT/MAC/RES/STK/ERN/NWS） | `collection/`（素材＋`00-manifest.md`） | ✅ 见 `status.md` |
| T2 | 试跑 Phase 1：选题评分与构成 | `production/outline.md` | ✅ 见 `status.md` |
| T3 | 试跑 Phase 2：基础文字内容输出（非播音稿，先验证内容翔实度） | `production/draft-*.md` | ✅ 见 `status.md` |
| T4 | 试跑复盘：问题与不足清单、规范修正项 | `review/trial-report.md` | ✅ |
| T5 | 内容翔实度确认（能否支撑后继内容生成） | `review/trial-report.md` 结论 | ✅ |

### 后继路线（Stage S：试跑通过后启动）

| 步骤 | 内容 | 说明 | 依赖 |
|------|------|------|------|
| S1 | 播音稿件转换 | 基础文字内容 → 口语化播音稿：全文口语化润色、时长估算与分段、语气/停顿标注 | T5 通过 |
| S2 | 视觉模板设计与视觉画面输出 | 将 `spec/vision-design.md` §1〜§7 落地为可复用的视觉模板组件，并按当日内容产出各画面 | S1 |
| S3 | Remotion 脚本编写 | 用 Remotion 编排语音与视觉画面的同步（时间轴对齐、字幕同步、动画节奏） | S1 + S2 |
| S4 | 合成试产（延伸） | TTS 语音合成 ＋ Remotion 渲染样片，端到端验证成片 | S3 |

> Stage S 各步骤的详细规格在试跑复盘通过后另行成文（预计置于 `phases/` 或新建 `production-pipeline/`）。

> **进度（2026-08-05）**: **S1 播音稿件转换已完成** — 输出 `daily-output/2026-08-04/production/broadcast-script.md`
> （基于 v2 重跑成果；实测约9,600字、含停顿约33〜35分，落于验收区间）。S2/S3 未开始。
>
> **S1 固定规范补充（TTS 适配）**: TTS 数字朗读能力弱，播音稿中**所有数值一律以汉字读音表记**
> （指数/金额/百分比/日期/年份/型号；范围写作「XからY」；正文不使用 %・〜・- 等符号与 Markdown 记号）。
> 此规则适用于此后每期 S1 输出。

---

## 改訂履歴

- **v5.1（2026-08-04）**: 进入试跑阶段。新增「五、当前阶段：试跑（Trial Run）」，定义 Stage T（T1〜T5：收集/选题/基础文字输出/复盘/翔实度确认）与 Stage S 后继路线（S1 播音稿件转换・S2 视觉模板与画面输出・S3 Remotion 音画同步・S4 合成试产）。首次实际试跑使用 `daily-output/2026-08-04/` 工作区。
- **v5.0（2026-07-23）**: ドキュメント構造を完全階層化へ再整理。PLAN.md を薄いマスター計画書にSlim化し、内容/視覚/コンプラ/バリュエ→`spec/`、Phase詳細→`phases/`、DB/ロゴ→`infra/`、情報源→`data-sources/` へ分割。コーナー構成を **線形 A→B→C→D** に再構築（`spec/content-framework.md` が唯一の情報源）。視覚仕様を `spec/vision-design.md` に一元化し `templates/daily-template.md` と1対1対応。`templates/daily-template.md` を純粋なひな形化（インライン視覚指示を排除）。
- **v4.3**: コーナー構成を2層モデル（固定フレーム＋主内容ブロック）へ。Phase 1 に選題原則・順位付けモデルを定義。← *v5.0 で線形 A/B/C/D モデルへ置換*
- **v4.2**: ブランドロゴ資産キャッシュ追加。
- **v4.1**: Phase 0 にローカルDB層（定期更新データの最適化）を追加。
- **v4.0**: マスター計画書兼タスクスケジューラへ再構築。Phase 0 完全定義。

# Phase 3：視覚素材取得・遅延クロール（asset-fetcher-agent）

> 旧 PLAN.md 第四章 Phase 3。状態: 🚧 補完（骨子）。ロゴキャッシュは [../infra/brand-asset-cache.md](../infra/brand-asset-cache.md)、DB層は [../infra/database-layer.md](../infra/database-layer.md)、視覚仕様は [../spec/vision-design.md](../spec/vision-design.md)。

- **入力**: ①`production/visual-brief.md` の **候補アセット一覧**（必要アセットの正式な一覧。`logo:nvidia` 形式。
  2026-08-28 にシーン表から移行）＋ ②`adopted=true` かつ `assets_status≠fetched` の素材（frontmatter の `assets_needed` を読む）
- **出力**: `assets/{screenshots,charts,logos}/...`（各日）＋ `assets/brands/`（共有キャッシュ）
- **動作**: 採用された素材から**必要な画像だけ**クロール取得。取得後 `assets_status=fetched` に更新。

> ブリーフと frontmatter の `assets_needed` が不一致の場合は **ブリーフを優先** し、不一致を
> `status.md` のメモに記録する。概念図・色ブロック・段階リストは Stage S2 が自作するため取得対象外。
> 取得対象はロゴ・スクリーンショット・写真＋（§0.6 の4场景のみ）チャート。

---

## 企業・メディア表示画像の取得（ロゴ＋本社実写）

企業・メディアの画像は都度検索せず **`assets/brands/` を先に参照**する（[brand-asset-cache.md](../infra/brand-asset-cache.md)）。表示コンテキストに応じて **2種類を使い分ける**（美投侃新聞の手法を参考）：

| 表示場面 | 使う画像 | 用途 |
|---|---|---|
| **単独表示**（1社/1媒体をクローズアップ） | **本社大楼や标志性建築物など、社名・媒体名が入った実写写真** | リアリティ・説得力を高める。B の個別株深層分析等 |
| **多品牌列挙**（一覧・比較・出所羅列） | **シンプルなロゴ**（背景透過 PNG／SVG） | 視認性・統一感。A.②目玉予告・Cニュース速報・セクター一覧等 |

### 取得フロー（実写写真ファースト・2026-08-23 改訂）

> **設計原則**: メインビジュアルにロゴを据えない。単独クローズアップは**実写建築写真**、人物の論点は**本人・報道写真**、抽象論は**文生图**（[../spec/vision-design.md §0.8](../spec/vision-design.md)）。ロゴは補助のみ。

```
画像が必要になった時（種別 = building | person | logo | concept）:
1. assets/brands/{companies,media}/<slug>[-hq].<ext> の存在確認
   - あり → 再利用（キャッシュ命中）★
   - なし → 手順2へ
2. 検索・ダウンロード（優先順）
   - building（単独用・最優先）: 公式IR／ニュースルームの高解像度本社・施設写真 → Wikipedia（企業記事のインフォボックス画像）→ SearXNG 画像検索（「{社名} headquarters」「{社名} 本社」）。社名・媒体名が写り込んだ标志性建築物を優先
   - person（人物の論点用）: 当該発言に紐づく報道記事の写真（会見・イベント）→ 本人の高解像度ポートレート（Wikipedia → SearXNG 画像検索）
   - logo（列挙用・補助のみ）: 公式ブランドアセット → Wikipedia → ロゴ検索（背景透過PNG/SVG優先）
   - concept（抽象概念）: tools/imagegen（qwen-image-3.0-pro）で生成。ロゴや写真で表現できない論理構造を可視化
3. 所定パスへ保存 → manifest.md に1行追記（種別 building/person/logo/concept を明記）
4. 保存したファイルを使用
```

### 検索レイヤの優先順（429 対策・2026-08-23 追加）

外部サービスのレート制限（429）に当たった場合の検索レイヤ：

1. **SearXNG 自部署**（`tools/searxng/search.ps1`）を最優先で使用する。画像検索は `-Categories images`、例:
   ```powershell
   .\tools\searxng\search.ps1 "NVIDIA headquarters building" -Categories images -TimeRange "" -Raw
   ```
2. Wikimedia Commons API（画像ファイルが確実に存在する既知ブランド用）
3. 組み込み `web_search` は最後のフォールバック

> 命名：ロゴは `<slug>.png`（例 `nvda.png`）。本社実写は `<slug>-hq.jpg`（例 `nvda-hq.jpg`）。詳細は [brand-asset-cache.md §3](../infra/brand-asset-cache.md)。
>
> チャート／スクリーンショットは回限定で各日 `assets/` へ。

### チャートの能動取得（2026-08-28 改訂・条件付き）

[vision-design.md §0.6](../spec/vision-design.md) の **4场景**（① 長期トレンド ② 周期性・規則性 ③ 歴史イベント対照 ④ 複数指数・指標の相互作用）でチャートが必要と**視覚設計ブリーフに記載された場合のみ**、Phase 3 が能動的に検索・収集する。Phase 0 ではチャートを収集しない（従来どおり記事内チャートはフラグのみ）。

```
チャートが必要になった時（ブリーフのチャート候補に chart:<指標>_<期間> 記載時）:
1. 履歴データを取得して自作（優先・出所と期間を正確に制御できる）
   - Stooq CSV（指数・個別株の長期日次データ。認証不要）
   - FRED（金利・マクロ系列。API キーは .env で管理）
   - Yahoo Finance 履歴ページ
   → 軸・単位・期間・出所を明記した PNG/SVG を生成
2. 既製チャートの高解像度スクリーンショット（公式 IR・信頼できる金融メディア）
   - 出所明記必須。ライセンスに注意（報道引用の範囲で使用）
3. assets/charts/<slug>_<period>.<png|svg> へ保存
   → manifest.md に1行追記（種別 chart、指標・期間・出所を明記）
```

**鉄則**: 系列は2〜3本まで／1画面1メッセージ（結論を右テキストで近接提示）／1920×1080 で鮮明な解像度／軸・単位・期間の表示必須。

それ以外の场景（スナップショット値・単純比較・論理展開・分類・短期変動）は引き続き **純数字＋色ブロック＋段階リストで Stage S2 が自作**（チャート取得対象外）。画像・図表は概念図・企業実写・ロゴ・色ブロック分類が中心。

---

## Gate #3（完了定義）

- [ ] ブリーフの候補アセット一覧が漏れなく取得されている（frontmatter の `assets_needed` は補助参照）
- [ ] ロゴ（列挙用）・本社実写（単独用）は brands キャッシュまたは新規取得で揃っている（manifest.md に追記済み）
- [ ] チャート要求场景（§0.6 の4场景）は、指標・期間・出所が揃い manifest.md に記録済み
- [ ] 全取得素材の `assets_status=fetched` 更新済み

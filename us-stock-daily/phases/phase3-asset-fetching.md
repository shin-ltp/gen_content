# Phase 3：視覚素材取得・遅延クロール（asset-fetcher-agent）

> 旧 PLAN.md 第四章 Phase 3。状態: 🚧 補完（骨子）。ロゴキャッシュは [../infra/brand-asset-cache.md](../infra/brand-asset-cache.md)、DB層は [../infra/database-layer.md](../infra/database-layer.md)、視覚仕様は [../spec/vision-design.md](../spec/vision-design.md)。

- **入力**: `adopted=true` かつ `assets_status≠fetched` の素材（`url` と `assets_needed` を読む）
- **出力**: `assets/{screenshots,charts,logos}/...`（各日）＋ `assets/brands/`（共有キャッシュ）
- **動作**: 採用された素材から**必要な画像だけ**クロール取得。取得後 `assets_status=fetched` に更新。

---

## 企業・メディア表示画像の取得（ロゴ＋本社実写）

企業・メディアの画像は都度検索せず **`assets/brands/` を先に参照**する（[brand-asset-cache.md](../infra/brand-asset-cache.md)）。表示コンテキストに応じて **2種類を使い分ける**（美投侃新聞の手法を参考）：

| 表示場面 | 使う画像 | 用途 |
|---|---|---|
| **単独表示**（1社/1媒体をクローズアップ） | **本社大楼や标志性建築物など、社名・媒体名が入った実写写真** | リアリティ・説得力を高める。B の個別株深層分析等 |
| **多品牌列挙**（一覧・比較・出所羅列） | **シンプルなロゴ**（背景透過 PNG／SVG） | 視認性・統一感。A.②目玉予告・Cニュース速報・セクター一覧等 |

### 取得フロー（両方ともキャッシュ優先）

```
画像が必要になった時（種別 = logo または building）:
1. assets/brands/{companies,media}/<slug>[-hq].<ext> の存在確認
   - あり → 再利用（キャッシュ命中）★
   - なし → 手順2へ
2. 検索・ダウンロード
   - logo（列挙用）: 公式IR／プレスキット／ブランドアセット → Wikipedia → ロゴ検索（背景透過PNG/SVG優先）
   - building（単独用）: 公式IR／ニュースルームの高解像度本社・施設写真 → Wikipedia（企業記事のインフォボックス画像）→ 画像検索（「{社名} headquarters」「{社名} 本社」）。社名・媒体名が写り込んだ标志性建築物を優先
3. 所定パスへ保存 → manifest.md に1行追記（種別 logo/building を明記）
4. 保存したファイルを使用
```

> 命名：ロゴは `<slug>.png`（例 `nvda.png`）。本社実写は `<slug>-hq.jpg`（例 `nvda-hq.jpg`）。詳細は [brand-asset-cache.md §3](../infra/brand-asset-cache.md)。
>
> チャート／スクリーンショットは回限定で各日 `assets/` へ。

> **チャート不使用ルール**: [vision-design.md §0.6](../spec/vision-design.md) に従い、伝統的チャートは取得・使用せず、純数字＋色ブロック＋段階リストで表現する。画像・図表は概念図・企業実写・ロゴ・色ブロック分類が中心。

---

## Gate #3（完了定義）

- [ ] 採用素材（`adopted=true`）の必要画像（`assets_needed`）が漏れなく取得されている
- [ ] ロゴ（列挙用）・本社実写（単独用）は brands キャッシュまたは新規取得で揃っている（manifest.md に追記済み）
- [ ] 全取得素材の `assets_status=fetched` 更新済み

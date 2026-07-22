# Phase 3：視覚素材取得・遅延クロール（asset-fetcher-agent）

> 旧 PLAN.md 第四章 Phase 3。状態: 🚧 補完（骨子）。ロゴキャッシュは [../infra/brand-asset-cache.md](../infra/brand-asset-cache.md)、DB層は [../infra/database-layer.md](../infra/database-layer.md)、視覚仕様は [../spec/vision-design.md](../spec/vision-design.md)。

- **入力**: `adopted=true` かつ `assets_status≠fetched` の素材（`url` と `assets_needed` を読む）
- **出力**: `assets/{screenshots,charts,logos}/...`（各日）＋ `assets/brands/`（共有キャッシュ）
- **動作**: 採用された素材から**必要な画像だけ**クロール取得。取得後 `assets_status=fetched` に更新。

---

## ロゴの取り扱い（[brand-asset-cache.md](../infra/brand-asset-cache.md)）

企業・メディアロゴは都度検索せず **`assets/brands/` を先に参照**する：

1. `assets/brands/{companies,media}/<slug>.png` の存在確認
2. あり → 再利用（キャッシュ命中）／ なし → 検索DL → 同ディレクトリへ保存 → `manifest.md` に1行追記

チャート／スクリーンショットは回限定で各日 `assets/` へ。

> **チャート不使用ルール**: [vision-design.md §0.6](../spec/vision-design.md) に従い、伝統的チャートは取得・使用せず、純数字＋色ブロック＋段階リストで表現する。画像・図表は概念図・ロゴ・色ブロック分類が中心。

---

## Gate #3（完了定義）

- [ ] 採用素材（`adopted=true`）の必要画像（`assets_needed`）が漏れなく取得されている
- [ ] ロゴは brands キャッシュまたは新規取得で揃っている（manifest.md に追記済み）
- [ ] 全取得素材の `assets_status=fetched` 更新済み

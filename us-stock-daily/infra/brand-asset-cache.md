# ブランドロゴ資産キャッシュ（assets/brands）

> 旧 PLAN.md 3.10 節。同じ企業ロゴ・メディアロゴを毎日検索・DL する無駄を排除するため、**取得1回・キャッシュ再利用**する全日共有キャッシュ。
> 画像版の [database-layer.md](./database-layer.md)。鮮度期限は持たず**ファイルの存在だけで判定**する（バイナリを DB に抱えず、ファイル＋マニフェストで管理）。
> 関連：[../phases/phase3-asset-fetching.md](../phases/phase3-asset-fetching.md)／[../assets/brands/manifest.md](../assets/brands/manifest.md)。

---

## 1. 課題と原則

毎日の番組で同じ企業ロゴ・メディアロゴ（Bloomberg, WSJ, Goldman Sachs, NVDA …）を何度も検索・ダウンロードするのは無駄である。ロゴはブランド刷新時以外は**ほぼ不変**（[database-layer.md](./database-layer.md) §2 の Tier C 参照）。したがって定期データ層と同じ「**取得1回・キャッシュ再利用**」原則を適用する。

> **核心フロー**: ロゴが必要 → [`assets/brands/`](../assets/brands/) を確認 → **あれば再利用（再取得しない）／なければ検索DL → 保存 → 次回からキャッシュ命中**。

---

## 2. ディレクトリ構成（プロジェクト直下・全日共有）

```
us-stock-daily/assets/brands/        # 日次ワークスペースの外・全エピソードで共有
├── companies/                        # 企業ロゴ（ticker 別）
│   ├── nvda.png
│   ├── aapl.png
│   └── ...
├── media/                            # メディア・情報源ロゴ（出所表示用）
│   ├── bloomberg.png
│   ├── wsj.png
│   ├── goldman-sachs.png
│   └── ...
├── template/                         # 番組で使う固定画像素材（浮世絵等）
│   └── The_Great_Wave_off_Kanagawa.jpg
└── manifest.md                       # キャッシュ一覧＋取得元URL＋ライセンス/使用条件
```

> **`assets/` の2系統に注意**: 本ディレクトリ `assets/brands/` は**プロジェクト直下の共有キャッシュ**（ロゴ等の不変資産）。各日の `daily-output/YYYY-MM-DD/assets/` は**その回限定**のスクリーンショット／チャート（Phase 3 が都度取得）。混同しないこと。

---

## 3. 命名規約

- ファイル名 = 正規化スラッグ（小文字・ハイフン区切り）。企業は ticker 小文字（`nvda.png`）、メディアはケバムケース（`goldman-sachs.png`）。
- 形式は **背景透過 PNG／SVG** を優先（番組のカラーコード背景に重ねるため）。同名で PNG と SVG が両方ある場合は PNG を標準とし SVG を併存可。

---

## 4. 取得フロー（Phase 3 asset-fetcher が実装）

```
ロゴが必要になった時:
1. assets/brands/{companies,media}/<slug>.png の存在確認
   - あり → そのまま使用（再取得しない）★ キャッシュ命中
   - なし → 手順2へ
2. 検索・ダウンロード（優先順: 公式IR／プレスキット／ブランドアセットページ → Wikipedia → ロゴ検索）
3. 所定パスへ保存 → manifest.md に1行追記（slug / 種別 / 取得元URL / 取得日 / 使用条件）
4. 保存したファイルを使用
```

---

## 5. マニフェスト（manifest.md）

キャッシュ一覧と出所の透明性を保つ。Gate 検査・ライセンス確認・「どこから取ったか」追跡の原料。**保存時の1行追記を必須**とする（追記なきキャッシュ追加は禁止）。実体は [../assets/brands/manifest.md](../assets/brands/manifest.md)。

```markdown
| slug | 種別 | 取得元URL | 取得日 | 形式 | 備考（ライセンス／使用条件） |
|------|------|-----------|--------|------|------|
| nvda | company | https://nvidianews.nvidia.com/... | 2026-07-14 | PNG | IRページ、ブランドガイドライン準拠 |
| bloomberg | media | https://bloomberg.com/... | 2026-07-14 | PNG | 出所表示用、改変禁止 |
```

---

## 6. 既存設計との統合

- **遅延取得戦略（Phase 0）**: 「企業ロゴ」は Phase 3 で取得するが、取得先は都度 Web ではなく **`assets/brands/` キャッシュを優先**（キャッシュミス時のみ検索DL）。
- **Phase 3 asset-fetcher**: 入力判定に「brands キャッシュ参照」ステップを追加。チャート／スクリーンショット（回限定・Tier A）は引き続き各日 `assets/` へ。
- **視覚表現規範**: 出所表示・企業ロゴ表示の素材は `assets/brands/` から取得する旨を [../spec/vision-design.md](../spec/vision-design.md) に明記。
- **バージョン管理**: 不変資産かつ再現性が重要なので基本コミット対象。容量が大きくなった場合は Git LFS を検討。

---

## 7. DB 層との対比（同じ原則・異なる実装）

| | [database-layer.md](./database-layer.md) 定期データ DB | 本章 ブランドロゴキャッシュ |
|--|------------------|-----------------------------|
| 対象 | 財務・マクロ・目標株価（構造化数値） | 企業・メディアロゴ（画像バイナリ） |
| 鮮度 | Tier B（定期更新・`effective_until` で管理） | Tier C（ほぼ不変・存在ベースで判定） |
| 実装 | SQLite + 鮮度API | ファイル + manifest.md |
| 更新 | 定期バッチ＋能動更新 | キャッシュミス時のみ取得 |
| 共通点 | **プロジェクト直下・全日共有・取得1回で再利用** | 同左 |

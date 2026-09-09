# ブランド資産キャッシュ（assets/brands）

> 旧 PLAN.md 3.10 節。同じ企業・メディアの画像を毎日検索・DL する無駄を排除するため、**取得1回・キャッシュ再利用**する全日共有キャッシュ。
> 画像版の [database-layer.md](./database-layer.md)。鮮度期限は持たず**ファイルの存在だけで判定**する（バイナリを DB に抱えず、ファイル＋マニフェストで管理）。
> 関連：[../phases/phase3-asset-fetching.md](../phases/phase3-asset-fetching.md)／[../assets/brands/manifest.md](../assets/brands/manifest.md)。

---

## 1. 課題と原則

毎日の番組で同じ企業・メディアの画像（Bloomberg, WSJ, Goldman Sachs, NVDA …）を何度も検索・ダウンロードするのは無駄である。これらはブランド刷新時以外は**ほぼ不変**（[database-layer.md](./database-layer.md) §2 の Tier C 参照）。したがって定期データ層と同じ「**取得1回・キャッシュ再利用**」原則を適用する。

キャッシュする企業・メディア・人物画像は **4種類**（表示コンテキストで使い分け・美投侃新聞の手法を参考）：

| 種類 | 内容 | 使う場面 |
|---|---|---|
| **logo** | シンプルなロゴ（背景透過 PNG／SVG） | 多ブランド列挙（一覧・比較・出所羅列）。A.②目玉予告・Cニュース速報・セクター一覧 |
| **building** | 本社ビル・代表的な建築物など**社名・媒体名が入った実写写真** | 単独表示（1社/1媒体のクローズアップ）。B の個別株深層分析等。リアリティ・説得力を高める |
| **person** | 人物の高解像度ポートレート・報道写真（CEO・議長・アナリスト等） | 発言・見解の解説ページ。「誰が言っているか」を即座に伝える（2026-08-29 追加） |
| **object** | 物理的オブジェクトの実写（半導体チップ・データセンター・ロケット・小売店頭・製油所等） | 技術・施設・製品の説明ページ。具体性と情報量を高める（2026-08-29 追加） |

### バージョン管理（3バージョン制・2026-08-29 追加）

**常用する实体（人物・企業）** は **3バージョン** の高品質画像をキャッシュし、日替わりでローテーション使用する。単一バージョンでは毎回同じ顔・同じ建物になり、番組の変化に欠けるため。

- 命名: `<slug>-person-v1.jpg` / `<slug>-person-v2.jpg` / `<slug>-person-v3.jpg`（person の場合）
- 命名: `<slug>-hq-v1.jpg` / `<slug>-hq-v2.jpg` / `<slug>-hq-v3.jpg`（building の場合・既存の `<slug>-hq.jpg` は v1 として扱う）
- **取得タイミング**: 初回取得時に3枚をまとめて検索・保存（1枚ずつ日を分けない）
- **使用ルール**: 日付やテーマに応じて選択。同一エピソード内では同一人物は同一バージョンで統一
- 対象: 頻出する人物（クレイマー・ウォーシュ・フアン等）と企業（NVDA・Salesforce・FRB等）

### 人物写真の品質基準（2026-08-29 追加）

- **優先: 講演・会見・イベント現場写真** — ステージ・演台・パネルディスカッションなど、人物と文脈が同時に写る報道写真。解像度 1200px 以上
- **可能な限り回避: 単独ポートレート（大头照）** — 背景なし・顔のみの写真はアナリスト発言の引用以外で使わない
- **Wikimedia Commons の注意点**: サムネイル URL（`/thumb/` パス）は圧縮されており 1920px でも実質解像度が低い場合がある。**オリジナル URL**（`/commons/` 直下）からダウンロードするか、解像度を `imageinfo` API の `width`/`height` で確認してから保存する

> **核心フロー**: 画像が必要 → [`assets/brands/`](../assets/brands/) を確認 → **あれば再利用（再取得しない）／なければ検索DL → 保存 → 次回からキャッシュ命中**。

---

## 2. ディレクトリ構成（プロジェクト直下・全日共有）

```
us-stock-daily/assets/brands/        # 日次ワークスペースの外・全エピソードで共有
├── companies/                        # 企業画像（ticker 別）
│   ├── nvda.png                      #   ロゴ（列挙用）
│   ├── nvda-hq.jpg                   #   本社実写（単独用）
│   ├── aapl.png
│   └── ...
├── media/                            # メディア・情報源画像（出所表示用）
│   ├── bloomberg.png
│   ├── bloomberg-hq.jpg
│   ├── goldman-sachs.png
│   └── ...
├── template/                         # 番組で使う固定画像素材（浮世絵等）
│   ├── The_Great_Wave_off_Kanagawa.jpg
│   └── opening-visual.png            # S0 オープニング固定背景（ウォール街の夜景、全エピソード共通）
└── manifest.md                       # キャッシュ一覧＋取得元URL＋ライセンス/使用条件
```

> **`assets/` の2系統に注意**: 本ディレクトリ `assets/brands/` は**プロジェクト直下の共有キャッシュ**（ロゴ等の不変資産）。各日の `daily-output/YYYY-MM-DD/assets/` は**その回限定**のスクリーンショット／チャート（Phase 3 が都度取得）。混同しないこと。

---

## 3. 命名規約

- ファイル名 = 正規化スラッグ（小文字・ハイフン区切り）。企業は ticker 小文字（`nvda.png`）、メディアはケバムケース（`goldman-sachs.png`）。
- **logo（列挙用）**: `<slug>.png`。形式は **背景透過 PNG／SVG** を優先（番組のカラーコード背景に重ねるため）。同名で PNG と SVG が両方ある場合は PNG を標準とし SVG を併存可。
- **building（単独用）**: `<slug>-hq.<ext>`（例 `nvda-hq.jpg`）。形式は **JPG 写真**（実写）。社名・媒体名が写り込んだ代表的な建築物（本社等）を優先。

---

## 4. 取得フロー（Phase 3 asset-fetcher が実装）

```
画像が必要になった時（種別 = logo または building を判定）:
1. assets/brands/{companies,media}/<slug>[-hq].<ext> の存在確認
   - あり → そのまま使用（再取得しない）★ キャッシュ命中
   - なし → 手順2へ
2. 検索・ダウンロード（種別別の優先順）
   - logo: 公式IR／プレスキット／ブランドアセットページ → Wikipedia → ロゴ検索（背景透過PNG/SVG優先）
   - building: 公式IR／ニュースルームの高解像度本社・施設写真 → Wikipedia（企業記事のインフォボックス画像）→ 画像検索（「{社名} headquarters」「{社名} 本社」）。社名・媒体名が写り込んだ代表的な建築物を優先
3. 所定パスへ保存 → manifest.md に1行追記（slug / 種別(company|media) / 種類(logo|building) / 取得元URL / 取得日 / 使用条件）
4. 保存したファイルを使用
```

> どちらの種類を使うかは表示コンテキストで決まる（[../spec/vision-design.md](../spec/vision-design.md)・[../phases/phase3-asset-fetching.md](../phases/phase3-asset-fetching.md)）。同一銘柄で logo と building の両方が必要になることがある。

---

## 5. マニフェスト（manifest.md）

キャッシュ一覧と出所の透明性を保つ。Gate 検査・ライセンス確認・「どこから取ったか」追跡の原料。**保存時の1行追記を必須**とする（追記なきキャッシュ追加は禁止）。実体は [../assets/brands/manifest.md](../assets/brands/manifest.md)。

```markdown
| slug | 種別 | 種類 | パス | 取得元URL | 取得日 | 形式 | 備考（ライセンス／使用条件） |
|------|------|------|------|-----------|--------|------|------|
| nvda | company | logo | companies/nvda.png | https://nvidianews.nvidia.com/... | 2026-07-14 | PNG | IRページ、ブランドガイドライン準拠 |
| nvda | company | building | companies/nvda-hq.jpg | https://en.wikipedia.org/... | 2026-07-14 | JPG | 本社タワー、Wikipedia（単独表示用） |
| bloomberg | media | logo | media/bloomberg.png | https://bloomberg.com/... | 2026-07-14 | PNG | 出所表示用、改変禁止 |
```

---

## 6. 既存設計との統合

- **遅延取得戦略（Phase 0）**: 「企業・メディア画像（logo／building）」は Phase 3 で取得するが、取得先は都度 Web ではなく **`assets/brands/` キャッシュを優先**（キャッシュミス時のみ検索DL）。
- **Phase 3 asset-fetcher**: 入力判定に「brands キャッシュ参照」ステップを追加。チャート／スクリーンショット（回限定・Tier A）は引き続き各日 `assets/` へ。
- **視覚表現規範**: 出所表示・企業画像表示の素材と、単独表示（building）／列挙表示（logo）の使い分けを [../spec/vision-design.md](../spec/vision-design.md) に明記。
- **バージョン管理**: 不変資産かつ再現性が重要なので基本コミット対象。容量が大きくなった場合は Git LFS を検討。

---

## 7. DB 層との対比（同じ原則・異なる実装）

| | [database-layer.md](./database-layer.md) 定期データ DB | 本章 ブランド資産キャッシュ |
|--|------------------|-----------------------------|
| 対象 | 財務・マクロ・目標株価（構造化数値） | 企業・メディア画像（logo／building） |
| 鮮度 | Tier B（定期更新・`effective_until` で管理） | Tier C（ほぼ不変・存在ベースで判定） |
| 実装 | SQLite + 鮮度API | ファイル + manifest.md |
| 更新 | 定期バッチ＋能動更新 | キャッシュミス時のみ取得 |
| 共通点 | **プロジェクト直下・全日共有・取得1回で再利用** | 同左 |

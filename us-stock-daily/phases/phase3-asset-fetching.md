# Phase 3：視覚素材取得・遅延クロール（asset-fetcher-agent）

> 旧 PLAN.md 第四章 Phase 3。状態: 🚧 補完（骨子）。ロゴキャッシュは [../infra/brand-asset-cache.md](../infra/brand-asset-cache.md)、DB層は [../infra/database-layer.md](../infra/database-layer.md)、視覚仕様は [../spec/vision-design.md](../spec/vision-design.md)。

- **入力**: ①`production/visual-brief.md` の **Slide単位の候補アセット一覧**（必要アセットの正式な一覧。
  `logo:nvidia` 形式。2026-09-17 以降は write_blocks.py が台本と同時に生成する。
  2026-08-28 にシーン表から移行）＋ ②`adopted=true` かつ `assets_status≠fetched` の素材（frontmatter の `assets_needed` を読む）
- **出力**: `assets/{screenshots,charts,logos}/...`（各日）＋ `assets/brands/`（共有キャッシュ）
- **動作**: 採用された素材から**必要な画像だけ**クロール取得。取得後 `assets_status=fetched` に更新。

> ブリーフと frontmatter の `assets_needed` が不一致の場合は **ブリーフを優先** し、不一致を
> `status.md` のメモに記録する。テーマ画像の**取得・生成は Phase 3 の責務**（SearXNG / tools/imagegen で実行）。
> 2026-09-17 以降、Stage S2 相当の `production/visual-data.json` は write_blocks.py が作成する。
> Phase 3 は取得・生成済み素材の実パスを反映するだけで、素材自体を作らない。
> 取得・生成対象はロゴ・スクリーンショット・写真・テーマ画像＋（§0.6 の4场景のみ）チャート。

---

## 企業・メディア表示画像の取得（ロゴ＋本社実写）

企業・メディアの画像は都度検索せず **`assets/brands/` を先に参照**する（[brand-asset-cache.md](../infra/brand-asset-cache.md)）。表示コンテキストに応じて **2種類を使い分ける**（美投侃新聞の手法を参考）：

| 表示場面 | 使う画像 | 用途 |
|---|---|---|
| **単独表示**（1社/1媒体をクローズアップ） | **本社ビルや代表的な建築物など、社名・媒体名が入った実写写真** | リアリティ・説得力を高める。B の個別株深層分析等 |
| **多品牌列挙**（一覧・比較・出所羅列） | **シンプルなロゴ**（背景透過 PNG／SVG） | 視認性・統一感。A 予告・Cニュース速報・セクター一覧等 |

### Top slide・素材採用の確定ルール（2026-09-08 新設）

**構成（2026-09-18 改訂）**: B セクション各テーマは **各ページ（p1..p8）に 1 枚のテーマ画像** を持つ。p1 は**記事全体**を基準に取得し、p2..p8 は**対応段落**を基準に判定する。段落の行動主体がテーマ主体から逸脱しない限り p1 の画像ファイルを再利用し、**主体が逸脱した場合のみその段落に対する新規検索・生成**を行う。A-p1..A-pN は対応テーマの p1 画像を巡回使用する（テーマごとに追加画像を作らない）。**新品発表・イベント主題**: 製品写真・会場写真を優先し、関係者のポートレート単独を使わない（[vision-design.md §0.8](../spec/vision-design.md)）。

**採用原則**: 実物・実在機関・実在人物が存在する題材は**必ず画像検索の結果を採用**する。高品質素材が得られない場合はキーワードを調整して再検索し、それでも得られない場合のみ最終手段として生成を検討する。市場の動き・センチメント・マクロ指標の変化など実体の存在しない題材のみ生成画像を許可する。主体別の指定（官僚会見写真・社名入り建物写真・創業者講演写真・アナリスト頭部写真・名称確認可能な標的画像等）の詳細は [../spec/vision-design.md §0.8](../spec/vision-design.md) を参照。

### 出所表示ルール（2026-09-03 改訂）

- 本文・データカード・注釈には**出所行を出力しない**。
- 出所は**外部取得の画像・チャート**に限り、画像内下部キャプションへ表示する。
- 当番組自作のテーマ画像・図には**「出所: 当番組」等を出さない**。
- **WallstreetCN 等の中国語ソースは、画像・チャート由来の場合も含めて一律非表示**とする。

### 取得フロー（実写写真ファースト・2026-08-23 改訂）

> **設計原則**: メインビジュアルにロゴを据えない。単独クローズアップは**実写建築写真**、人物の論点は**本人・報道写真**、抽象論は**テキストからの画像生成**（[../spec/vision-design.md §0.8](../spec/vision-design.md)）。ロゴは補助のみ。

```
画像が必要になった時（種別 = building | person | logo | theme-image）:
1. 当日 `daily-output/{date}/assets/b{n}-{p}.png`（テーマ画像）・`assets/brands/{companies,media}/<slug>[-hq].<ext>`（ロゴ・実写）の存在確認
   - あり → 再利用（キャッシュ命中）★
   - なし → 手順2へ
2. 検索・ダウンロード（優先順）
   - building（単独用・最優先）: 公式IR／ニュースルームの高解像度本社・施設写真 → Wikipedia（企業記事のインフォボックス画像）→ SearXNG 画像検索（「{社名} headquarters」「{社名} 本社」）。社名・媒体名が写り込んだ代表的な建築物を優先
   - person（人物の論点用）: 当該発言に紐づく報道記事の写真（会見・イベント）→ 本人の高解像度ポートレート（Wikipedia → SearXNG 画像検索）
   - logo（列挙用・補助のみ）: 公式ブランドアセット → Wikipedia → ロゴ検索（背景透過PNG/SVG優先）
   - theme-image（テーマ画像・2026-09-18 改訂）: 判定単位はテーマではなく**ページ**。p1 は記事全体、p2.. は段落から行動主体を判定し、キーワード優先順位（①製品/ニュース事件 → ②行動主体 → ③抽象）に従う。①②は SearXNG images で検索して LLM が品質・主題適合で選図し、③と検索全滅時のみ tools/imagegen（qwen-image-3.0-pro）で生成する（Mac fallback 禁止）。採用画像は `assets/b{n}-{p}.png` へ保存し、`assets/image-meta.json` に keyword / route / subject_type / **portrait（人物肖像）フラグ** を記録する。`assets/concepts/` ディレクトリは廃止。
3. 所定パスへ保存 → `assets/manifest.jsonl` に1行追記（種別 building/person/logo/theme-image・使用キーワード・portrait フラグ・出所・取得日時を明記）
4. 保存したファイルを使用
```

### キーワード資産DBと共有再利用（2026-09-18 新設）

`us-stock-daily/db/media-assets.sqlite3`（SQLite・2テーブル・実行時データのため gitignore 対象、[episode_contract.py](../tools/pipeline/episode_contract.py) の定数が単一定義点）で、検索・生成に使ったキーワードを管理する。

- `candidate_keywords`: 検索または生成で結果画像が確定保存されるたび、**使用したキーワード**の使用回数を +1 する。
- `media_assets`: 使用回数が 3 を超えたキーワードは、該当画像を共有 `assets/media_resources/` へコピーして**キーワードごとこちらへ移動**する。
- 次回以降の検索・生成は先に `media_assets` を照会し、**ヒットしたら共有ファイルを当日 assets へコピーして直接利用し、検索・生成を丸ごとスキップ**する（[media_asset_db.py](../tools/pipeline/media_asset_db.py) 参照）。

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

### Gate #3：素材トレーサビリティ検査（2026-08-31 新設・ハードゲート）

Phase 3 の完了判定は「キャッシュに画像があった」では不十分。次の全条件を満たさない限り Gate #3 は PASS しない：

1. **全素材参照の出所明示** — 当日 `production/visual-data.json` とレンダ後 `visual.html` 内の全 `src` 参照（`https?` 除く）を列挙し、各参照を次のいずれかに分類する：
   - `fetched`: 当日 `assets/` 配下に実在し、当日 `assets/manifest.jsonl` に取得記録（種別・出所 URL・キーワード・portrait・取得日時）がある
   - `cached`: 共有キャッシュ `assets/brands/` 等に実在し、`status.md` メモに「キャッシュ命中」と「再利用理由」（同一主体・同一文脈で品質十分等）を記録
   - いずれにも該当しない参照が 1 件でもあれば FAIL
2. **ブリーフ網羅チェック** — `visual-brief.md` の候補アセット一覧の全項目が `fetched` / `cached` / 「ブリーフから意図的に除外（理由記録）」のいずれかになっていること
3. **レイアウト整合** — §0.8 の A/B/C パターンに対し、ニュース配図・講演・会見などの人物実写=split 全高・portrait=true の肖像=**左側円形（上下中央）**・それ以外のテーマ画像=split 全高の対応が取れていること（画面種別ではなく素材種別で判定する。Stage S2 完了定義と共通）
4. **新品発表素材の優先（2026-09-10 追加）** — 新品発表・イベント主題の Top slide および A-p1..A-pN の予告画像は、取得可能なら製品写真・会場写真・記事配図を使い、人物ポートレート単独で代用していないこと。人物ポートレートは語りの主語がその人物自体のページに限定する
5. **記録** — 上記 1-4 の分類表を `status.md`（または `review/`）に残す。口頭判断のみで PASS としない

> 補助（2026-09-17 追加）: `prepare_remotion.py` は screenshot 前に `visual.html` の全ローカル画像参照を検査し、
> 共有キャッシュ `assets/` にある同名素材を当日ディレクトリへ自動コピーする。キャッシュにも無い参照は
> 明示エラーで停止する（FAIL の握りつぶし防止）。この自動補完は作業ミスの安全網であり、Gate #3 の
> 分類・記録義務を免除しない。

> この検査は「到 TTS まで」など部分再実行時も省略しない。再実行範囲に Phase 2 以降が含まれる場合、
> Phase 3 は必ず再評価対象である（[overview.md](./overview.md) の再実行範囲定義参照）。

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
   → manifest.jsonl に1行追記（種別 chart、指標・期間・出所を明記）
```

**鉄則**: 系列は2〜3本まで／1画面1メッセージ（結論を右テキストで近接提示）／1920×1080 で鮮明な解像度／軸・単位・期間の表示必須。

それ以外の场景（スナップショット値・単純比較・論理展開・分類・短期変動）は引き続き **純数字＋色ブロック＋段階リストで Stage S2 が自作**（チャート取得対象外）。画像・図表はテーマ画像・企業実写・ロゴ・色ブロック分類が中心。

---

## Gate #3（完了定義）

- [ ] ブリーフの候補アセット一覧が漏れなく取得されている（frontmatter の `assets_needed` は補助参照）
- [ ] ロゴ（列挙用）・本社実写（単独用）は brands キャッシュまたは新規取得で揃っている（共有は `assets/brands/manifest.md`、当日は `assets/manifest.jsonl` に追記済み）。単独クローズアップ画像は**社名・ロゴが視認可能**であること
- [ ] 出所表示は新ルール準拠：本文出所なし／自作図出所なし／外部画像・チャートのみ出所あり／中国語ソースは非表示
- [ ] チャート要求场景（§0.6 の4场景）は、指標・期間・出所が揃い manifest.jsonl に記録済み
- [ ] B各ページの画像に `assets/image-meta.json` の keyword・portrait 記録があり、**肖像=左円形・それ以外=左全高**で表示されている（visual_qa_gate の `visual_image_meta` が PASS。prepare_visual_assets.py が render 後に自動実行）
- [ ] 全取得素材の `assets_status=fetched` 更新済み

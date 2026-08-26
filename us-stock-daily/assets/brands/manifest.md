# ブランドアセットキャッシュ一覧

> 企業・メディア画像（logo／building）の全日共有キャッシュ。[../../infra/brand-asset-cache.md](../../infra/brand-asset-cache.md) 参照。
> **原則**: 必要になった時、まずここを確認 → あれば再利用（再取得しない）／ なければ検索DL → 保存 → **下表に必ず1行追記**する。

## 2種類の使い分け（美投侃新聞スタイル）

| 種類 | 内容 | 使う場面 |
|---|---|---|
| **logo** | シンプルなロゴ（背景透過 PNG／SVG）。列挙表示用 | 多品牌列挙（目玉予告・ニュース速報・一覧） |
| **building** | 本社大楼・标志性建築物など社名・媒体名が入った実写写真。単独表示用 | 1社/1媒体のクローズアップ（個別株深層分析等） |

## 取得フロー

```
1. assets/brands/{companies,media}/<slug>[-hq].<ext> を確認
   - あり → 再利用（キャッシュ命中）
   - なし → 手順2へ
2. 検索・ダウンロード
   - logo: 公式IR／プレスキット／ブランドアセット → Wikipedia → ロゴ検索（背景透過PNG/SVG優先）
   - building: 公式IR／ニュースルームの高解像度本社写真 → Wikipedia（インフォボックス画像）→ 画像検索（「{社名} headquarters」）。社名の入った标志性建築物を優先
3. 所定パスへ保存（logo=背景透過PNG/SVG、building=JPG写真）
4. 下表に1行追記（slug / 種別 / 種類 / パス / 取得元URL / 取得日 / 形式 / 使用条件）
5. 保存したファイルを使用
```

## 命名規約

- 企業: ticker 小文字（`nvda.png`／`nvda-hq.jpg`）。メディア: ケバムケース（`goldman-sachs.png`／`goldman-sachs-hq.jpg`）。
- logo は PNG 標準（SVG 併存可）。building は `-hq` 接尾辞・JPG。

## キャッシュ一覧

| slug | 種別 | 種類 | パス | 取得元URL | 取得日 | 形式 | 備考（ライセンス／使用条件） |
|------|------|------|------|-----------|--------|------|------------------------------|
| _(例) nvda_ | _(例) company_ | _(例) logo_ | _(例) companies/nvda.png_ | _(例) https://nvidianews.nvidia.com/..._ | _(例) 2026-07-14_ | _(例) PNG_ | _(例) IRページ・ガイドライン準拠_ |
| _(例) nvda_ | _(例) company_ | _(例) building_ | _(例) companies/nvda-hq.jpg_ | _(例) https://en.wikipedia.org/..._ | _(例) 2026-07-14_ | _(例) JPG_ | _(例) 本社タワー・Wikipedia（単独表示用）_ |

| nvidia | company | building | companies/nvidia-hq.jpg | https://upload.wikimedia.org/wikipedia/commons/d/d3/Nvidia_campus_aerial.jpg | 2026-08-23 | JPG | 本社キャンパス空撮・Wikimedia Commons（単独表示用） |
| apple | company | building | companies/apple-hq.jpg | https://static1.thetravelimages.com/wordpress/wp-content/uploads/2023/04/exterior-view-of-apple-park-visitor-center.jpg | 2026-08-23 | JPG | Apple Parkビジターセンター外観・SearXNG画像検索（単独表示用） |
| microsoft | company | building | companies/microsoft-hq.jpg | https://cdn.geekwire.com/wp-content/uploads/2025/05/Microsoft-East-Campus-Aerial-Photo.jpg | 2026-08-23 | JPG | レドモンドイーストキャンパス空撮・GeekWire（単独表示用） |
| hd | company | building | companies/hd-hq.jpg | https://d1xchyov513y0i.cloudfront.net/wp-content/uploads/2023/03/23162712/the-home-depot-PEMB-construction.jpg | 2026-08-23 | JPG | 店舗外観実写・SearXNG画像検索（単独表示用） |
| tsmc | company | building | companies/tsmc-hq.jpg | https://assets.bwbx.io/images/users/iqjWHBFdfxIU/idCM_YLjrTmc/v1/-1x-1.webp | 2026-08-23 | JPG | 新竹本社・Bloomberg報道写真（単独表示用） |
| meta | company | building | companies/meta-hq.jpg | https://www.green.earth/hs-fs/hubfs/Meta%E2%80%99s%20recent%20advancements_The%20headquarters%20of%20Meta%20Platforms%2C%20Inc.%2C%20known%20as%20Menlo%20Park_visual%201.png | 2026-08-23 | JPG | メンロパーク本社・SearXNG画像検索（単独表示用） |
| berkshire | company | building | companies/berkshire-hq.jpg | https://mcgillbrothers.com/wp-content/uploads/2020/06/20200506_cc_4830-2000x1333.jpg | 2026-08-23 | JPG | キーウィットプラザ（オマハ本社）・SearXNG画像検索（単独表示用） |
| federal-reserve | company | building | companies/federal-reserve-hq.jpg | https://www.encirclephotos.com/wp-content/uploads/Washington-DC-Eccles-Building-Federal-Reserve-1200x630.jpg | 2026-08-23 | JPG | エクルズビルディング・SearXNG画像検索（単独表示用） |
| target | company | building | companies/target-hq.jpg | https://dfisolutions.com/wp-content/uploads/2022/06/Target-Headquarters-Image-6.jpg | 2026-08-23 | JPG | ミネアポリス本社・SearXNG画像検索（単独表示用） |
| walmart | company | building | companies/walmart-hq.jpg | https://k5e2h2j6.delivery.rocketcdn.me/wp-content/uploads/2023/04/23-03-18-PD_12-Ext_47-a0b31f1474221f41c46a2153a9fa4878-1024x767.jpeg | 2026-08-23 | JPG | ベントンビル本社・SearXNG画像検索（単独表示用） |
| anthropic | company | building | companies/anthropic-hq.jpg | https://s.hdnux.com/photos/01/54/47/63/28474594/6/ratio3x2_960.jpg | 2026-08-23 | JPG | サンフランシスコオフィス・SearXNG画像検索（単独表示用） |
| coreweave | company | building | companies/coreweave-hq.jpg | https://www.scottarchlighting.com/wp-content/uploads/2026/02/HLW-Coreweave-knk03-800x525.jpg | 2026-08-23 | JPG | 本社ビル（HLW設計）・SearXNG画像検索（単独表示用） |
| nvidia | company | logo | companies/nvidia.png | https://commons.wikimedia.org/wiki/File:NVIDIA_logo.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| aapl | company | logo | companies/aapl.png | https://commons.wikimedia.org/wiki/File:Apple_logo_black.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| microsoft | company | logo | companies/microsoft.png | https://commons.wikimedia.org/wiki/File:Microsoft_logo_(2012).svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| tsmc | company | logo | companies/tsmc.png | https://commons.wikimedia.org/wiki/File:TSMC_wordmark.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| meta | company | logo | companies/meta.png | https://commons.wikimedia.org/wiki/File:Meta_Platforms_Inc._logo.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| brk | company | logo | companies/brk.png | https://commons.wikimedia.org/wiki/File:Berkshire_Hathaway.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| federal-reserve | company | logo | companies/federal-reserve.png | https://commons.wikimedia.org/wiki/File:Seal_of_the_United_States_Federal_Reserve_System.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| anthropic | company | logo | companies/anthropic.png | https://commons.wikimedia.org/wiki/File:Anthropic_logo.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| cerebras | company | logo | companies/cerebras.png | https://commons.wikimedia.org/wiki/File:Cerebras_logo.svg | 2026-08-23 | PNG | Wikimedia Commons 400px（補助・列挙用） |
| great-wave | art | template | template/The_Great_Wave_off_Kanagawa.jpg | https://commons.wikimedia.org/wiki/File:Tsunami_by_hokusai_19th_century.jpg | 2026-08-23 | JPG | 葛飾北斎「神奈川沖浪裏」俳句背景・パブリックドメイン（既存アセットを登記） |
| jim-cramer | person | person | daily-output/2026-08-19/assets/people/jim-cramer.jpg | https://image.cnbcfm.com/api/v1/image/104573616-IMG_3283-jim-cramer.jpg | 2026-08-23 | JPG | CNBC公式写真（Mad Money）・鉄則二解説用（各日保管） |
| ben-thompson | person | person | daily-output/2026-08-19/assets/people/ben-thompson.jpg | https://stratechery.com/wp-content/uploads/2015/05/BenPortrait-medium-1.jpg | 2026-08-23 | JPG | Stratechery公式ポートレート・B-2構造論用（各日保管） |
| discount-rate | concept | concept | daily-output/2026-08-19/assets/concepts/discount-rate.png | tools/imagegen: qwen-image-3.0-pro | 2026-08-23 | PNG | 割引率の概念図 1600x900（各日保管） |
| bubble-history | concept | concept | daily-output/2026-08-19/assets/concepts/bubble-history.png | tools/imagegen: qwen-image-3.0-pro | 2026-08-23 | PNG | バブル史観の概念図 1600x900（各日保管） |
| capital-curve | concept | concept | daily-output/2026-08-19/assets/concepts/capital-curve.png | tools/imagegen: qwen-image-3.0-pro | 2026-08-23 | PNG | 資本曲線の概念図 1600x900（各日保管） |
| k-shaped-consumption | concept | concept | daily-output/2026-08-19/assets/concepts/k-shaped-consumption.png | tools/imagegen: qwen-image-3.0-pro | 2026-08-23 | PNG | K型消費の概念図 1600x900（各日保管） |
| opening-visual | concept | concept | daily-output/2026-08-19/assets/concepts/opening-visual.png | tools/imagegen: qwen-image-3.0-pro | 2026-08-23 | PNG | オープニングテーマ画像 1600x900（各日保管） |

<!-- 上の例行を参考に、取得の都度1行ずつ追記してください。追記なきキャッシュ追加は禁止。 -->

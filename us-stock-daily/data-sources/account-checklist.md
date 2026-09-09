# 情報源アカウント登録リスト

## 登録が必要な無料サービス

### 優先度1 - 毎日必須
- [x] TradingView (tradingview.com) - Googleログイン済み、OpenCLI経由でアクセス確認済み
- [x] Seeking Alpha (seekingalpha.com) - 登録済み。OpenCLIブラウザコマンド経由でアクセス成功（スクレイピング対策回避）
- [x] Simply Wall St (simplywall.st) - 登録済み。OpenCLIブラウザコマンド経由でアクセス成功（Dashboard正常表示）
- [x] Finviz (finviz.com) - 登録済み。カスタムScreenerを保存
- [x] Investing.com (investing.com) - 登録済み。経済カレンダーのフィルタを保存

### 優先度2 - メール購読
- [x] Bloomberg "Five Things to Start Your Day" - 購読済み、毎日受信（日本語版：1日を始める前に読んでおきたいニュース5本）
- [x] WSJ "Markets A.M." / "Technology" / "AI & Business" - 購読済み、毎日受信
- [x] Yahoo Finance Morning Brief - 購読済み、毎日受信
- [x] Reuters Morning Wire - 購読済み、確認メールをクリックして認証完了が必要（7月3日に確認メール送信）
- [x] SemiAnalysis Newsletter - 購読済み、Welcomeメール受信（7月4日）

### 優先度3 - 必要に応じて使用
- [x] TipRanks (tipranks.com) - 登録済み、ウェルカムメール受信
- [x] WallStreetZen (wallstreetzen.com) - 登録済み、ウェルカムメール受信
- [x] FRED (fred.stlouisfed.org) - 登録済み（メール認証不要の可能性）
- [x] MacroMicro (en.macromicro.me) - 登録済み（英語版）/ macromicro.me（中国語版）

### 優先度4 - 深層分析情報源（登録不要）
- [x] 華爾街見聞 (wallstreetcn.com/news/us-stock) - 中国語圏の米国株メディア。深層分析が豊富、登録不要
  - 注意: `/news/global` パスは404、正しいパスは `/news/us-stock`
  - カバー: 米国株、半導体、AI、マクロ、企業深層分析
  - SemiAnalysis等の機関コンテンツの翻訳を含む、Dセクター深層分析素材に適する
  - **コンテンツフィルタ基準**: 有名大手投資銀行（Goldman/Morgan Stanley/JPMorgan等）のアナリストレポートを引用したコンテンツのみ

- [x] 36氪 (36kr.com) - テクノロジー産業の深層報道
  - **注力領域**:
    - AI/ソフトウェア/半導体/ハイテク産業
    - 大手テック7社(Mag7)、OpenAI、Anthropic等の注目企業
    - 投資対効果、競争環境、業界動向分析
    - 国産半導体、AI企業の動向
    - 米中AI競争環境の新動向
  - **コンテンツフィルタ基準**: 産業の深層分析、一般ニュース速報は除く
  - **適合セクター**: Dセクター深層分析素材

### 優先度5 - 大手投資銀行公開リサーチレポート（登録不要）
- [x] Goldman Sachs Insights (goldmansachs.com/insights) - ✅ テスト済み
  - HTTP 200 OK、OpenCLIブラウザアクセス正常
  - 内容が豊富: Top of Mind, GS Research, The Markets, Exchanges (ポッドキャスト), Talks at GS
  - カバー: AI/テクノロジー、マクロ経済、資産配分、データセンター、半導体等
  - **PDFリサーチレポートダウンロード可能**: 実検証で "An AI Job Apocalypse?" (26ページ, 1.3MB) のダウンロードに成功
  - **PDF抽出テスト**: opendataloader-pdf でMarkdownへの抽出に成功（2385行）、内容完全・構造明確
  - PDF URL形式: `/pdfs/insights/goldman-sachs-research/<slug>/report.pdf`
  - ダウンロード方法: curl + ブラウザUA + Referer で可能（cookies不要）

- [x] Morgan Stanley Insights (morganstanley.com/insights) - ✅ テスト済み
  - HTTP 200 OK（/ideas → 301 → /insights）、OpenCLIブラウザアクセス正常
  - 注意: 正しいURLは morganstanley.com/insights（/ideas ではない）
  - 内容が豊富: Market Trends, Technology & Disruption, Sustainability, Institute
  - カバー: AI経済、エネルギートランジション、グローバル市場、金融サービス
  - ポッドキャスト "Thoughts on the Market"、Newsletter "Five Ideas" あり
  - **読み取り方法**: OpenCLI browser でHTMLコンテンツを読み取り

- [x] JPMorgan Insights (jpmorgan.com/insights) - ✅ テスト済み
  - HTTP 200 OK、OpenCLIブラウザアクセス正常
  - 注意: 入口は jpmorgan.com/insights（/markets は機関取引プラットフォーム）
  - 内容が豊富: Global Research, Markets and Economy, Technology, 2026 Outlooks
  - カバー: グローバルリサーチ、市場動向、テクノロジー業界、投資展望
  - Newsletter購読入口あり (/newsletters)
  - **読み取り方法**: OpenCLI browser でHTMLコンテンツを読み取り

- [x] BlackRock Investment Institute (blackrock.com/corporate/insights/blackrock-investment-institute) - ✅ テスト済み
  - HTTP 200 OK、OpenCLIブラウザアクセス正常
  - 注意: 元のURL `/corporate/investor-resources` は404を返す、正しいURLは `/corporate/insights/blackrock-investment-institute`
  - 内容: Investment Outlook, Weekly Commentary, Mega Forces, Portfolio Research
  - **読み取り方法**: OpenCLI browser でPDFをダウンロード → opendataloader-pdf でコンテンツを抽出
  - PDFダウンロード: ブラウザ内で `fetch()` + `<a>.click()` を実行し ~/Downloads/ にダウンロード
  - PDF URL: `/corporate/literature/whitepaper/bii-midyear-outlook-2026.pdf`

### コンテンツフィルタ原則
- ✅ 有名大手投資銀行のアナリストレポートのみ（二次引用可）
- ✅ コアとなる観点と論拠が完全
- ✅ 一次情報源まで追跡可能であればなお良い
- ❌ 陰謀論、過激な観点、信頼できる背景のない記事を除外
- ❌ ZeroHedge、Wolf Street等の過激な情報源を除外

## おすすめ有料サービス（優先度順）

### 強く推奨
- [ ] Seeking Alpha Premium - $239/年
  - 価値: 大手投資銀行レーティングのリアルタイム要約 + 独立アナリストの深層分析
  - 代替コスト: 同等のカバー範囲を実現できる無料代替品なし

### 推奨
- [ ] TipRanks Pro - $34.99/月
  - 価値: 完全なアナリスト勝率データ
  - 代替: 無料版は回数制限あり

### オプション
- [ ] Simply Wall St Premium - $20-60/月
  - 価値: 番組表示用のスノーフレーク図
  - 代替: Excelで類似グラフを自作可能

- [ ] MacroMicro 基礎会員 - 約$10/月
  - 価値: マクロ経済チャートの可視化
  - 代替: FREDデータで自作グラフ可能

## 無料 API（技術統合用）

| API | URL | 用途 | 制限 |
|-----|-----|------|------|
| FRED API | api.stlouisfed.org | マクロ経済データ | 無料、key登録必要 |
| SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 企業財務報告 | 無料、10 req/s |
| Yahoo Finance API | 非公式 | 相場データ | 無料、不安定 |
| Alpha Vantage | alphavantage.co | 相場データ+ファンダメンタルズ | 無料25回/日 |

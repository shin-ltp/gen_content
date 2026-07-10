# 信源账号注册清单

## 需要注册的免费服务

### 优先级1 - 每日必用
- [x] TradingView (tradingview.com) - Google登录済み、OpenCLI経由でアクセス確認済み
- [x] Seeking Alpha (seekingalpha.com) - 已注册。通过OpenCLI浏览器命令访问成功（绕过反爬）
- [x] Simply Wall St (simplywall.st) - 已注册。通过OpenCLI浏览器命令访问成功（Dashboard正常显示）
- [x] Finviz (finviz.com) - 已注册。保存自定义Screener
- [x] Investing.com (investing.com) - 已注册。保存经济日历筛选

### 优先级2 - 邮件订阅
- [x] Bloomberg "Five Things to Start Your Day" - 已订阅，每日收到（日文版：1日を始める前に読んでおきたいニュース5本）
- [x] WSJ "Markets A.M." / "Technology" / "AI & Business" - 已订阅，每日收到
- [x] Yahoo Finance Morning Brief - 已订阅，每日收到
- [x] Reuters Morning Wire - 已订阅，但需点击确认邮件完成验证（7月3日发送确认邮件）
- [x] SemiAnalysis Newsletter - 已订阅，收到Welcome邮件（7月4日）

### 优先级3 - 按需使用
- [x] TipRanks (tipranks.com) - 已注册，收到欢迎邮件
- [x] WallStreetZen (wallstreetzen.com) - 已注册，收到欢迎邮件
- [x] FRED (fred.stlouisfed.org) - 已注册（可能无需邮件确认）
- [x] MacroMicro (en.macromicro.me) - 已注册（英文版）/ macromicro.me（中文版）

### 优先级4 - 深度分析信源（免注册）
- [x] 华尔街见闻 (wallstreetcn.com/news/us-stock) - 美股深度分析，免注册，内容丰富
  - 注意: `/news/global` 路径已404，正确路径为 `/news/us-stock`
  - 覆盖: 美股、半导体、AI、宏观、公司深度
  - 含SemiAnalysis等机构内容翻译，适合D板块深度分析素材
  - **内容筛选标准**: 仅限引用知名大行(Goldman/Morgan Stanley/JPMorgan等)分析师报告的内容

- [x] 36氪 (36kr.com) - 科技产业深度报道
  - **聚焦领域**:
    - AI/软件/半导体/高科技产业
    - 七巨头(Mag7)、OpenAI、Anthropic等明星公司
    - 投入产出、竞争环境、行业态势分析
    - 国产半导体、AI公司动态
    - 中美AI竞争格局新动向
  - **内容筛选标准**: 产业深度分析，非一般新闻快讯
  - **适合板块**: D板块深度分析素材

### 优先级5 - 大行公开研报（免注册）
- [x] Goldman Sachs Insights (goldmansachs.com/insights) - ✅ 已测试
  - HTTP 200 OK，OpenCLI浏览器访问正常
  - 内容丰富: Top of Mind, GS Research, The Markets, Exchanges (播客), Talks at GS
  - 覆盖: AI/科技、宏观经济、资产配置、数据中心、半导体等
  - **PDF研报可下载**: 实测成功下载 "An AI Job Apocalypse?" (26页, 1.3MB)
  - **PDF提取测试**: opendataloader-pdf 成功提取为Markdown（2385行），内容完整、结构清晰
  - PDF URL格式: `/pdfs/insights/goldman-sachs-research/<slug>/report.pdf`
  - 下载方式: curl + 浏览器UA + Referer 即可（无需cookies）

- [x] Morgan Stanley Insights (morganstanley.com/insights) - ✅ 已测试
  - HTTP 200 OK（/ideas → 301 → /insights），OpenCLI浏览器访问正常
  - 注意: 正确URL为 morganstanley.com/insights（非/ideas）
  - 内容丰富: Market Trends, Technology & Disruption, Sustainability, Institute
  - 覆盖: AI经济、能源转型、全球市场、金融服务
  - 有播客 "Thoughts on the Market"、Newsletter "Five Ideas"
  - **读取方式**: OpenCLI browser 读取HTML内容

- [x] JPMorgan Insights (jpmorgan.com/insights) - ✅ 已测试
  - HTTP 200 OK，OpenCLI浏览器访问正常
  - 注意: 入口为 jpmorgan.com/insights（/markets 为机构交易平台）
  - 内容丰富: Global Research, Markets and Economy, Technology, 2026 Outlooks
  - 覆盖: 全球研究、市场趋势、科技行业、投资展望
  - 有Newsletter订阅入口 (/newsletters)
  - **读取方式**: OpenCLI browser 读取HTML内容

- [x] BlackRock Investment Institute (blackrock.com/corporate/insights/blackrock-investment-institute) - ✅ 已测试
  - HTTP 200 OK，OpenCLI浏览器访问正常
  - 注意: 原URL `/corporate/investor-resources` 返回404，正确URL为 `/corporate/insights/blackrock-investment-institute`
  - 内容: Investment Outlook, Weekly Commentary, Mega Forces, Portfolio Research
  - **读取方式**: OpenCLI browser 下载PDF → opendataloader-pdf 提取内容
  - PDF下载: 浏览器内执行 `fetch()` + `<a>.click()` 下载到 ~/Downloads/
  - PDF URL: `/corporate/literature/whitepaper/bii-midyear-outlook-2026.pdf`

### 内容筛选原则
- ✅ 仅限知名大行分析师报告（可二手引用）
- ✅ 核心观点和论据完整
- ✅ 可追溯至第一手信源更佳
- ❌ 排除阴谋论、激进观点、无可靠背景的文章
- ❌ 排除ZeroHedge、Wolf Street等激进信源

## 建议付费服务 (按优先级排序)

### 强烈推荐
- [ ] Seeking Alpha Premium - $239/年
  - 价值: 大行评级即时摘要 + 独立分析师深度
  - 替代成本: 无免费替代品能达到同等覆盖面

### 推荐
- [ ] TipRanks Pro - $34.99/月
  - 价值: 完整分析师胜率数据
  - 替代: 免费版有次数限制

### 可选
- [ ] Simply Wall St Premium - $20-60/月
  - 价值: 节目展示用的雪花图
  - 替代: 可自行用Excel制作类似图表

- [ ] MacroMicro 基础会员 - 约$10/月
  - 价值: 宏观经济图表可视化
  - 替代: FRED数据可自行制图

## 免费 API (技术集成用)

| API | URL | 用途 | 限制 |
|-----|-----|------|------|
| FRED API | api.stlouisfed.org | 宏观经济数据 | 免费，需注册key |
| SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 公司财报 | 免费，10 req/s |
| Yahoo Finance API | 非官方 | 行情数据 | 免费，不稳定 |
| Alpha Vantage | alphavantage.co | 行情+基本面 | 免费25次/天 |
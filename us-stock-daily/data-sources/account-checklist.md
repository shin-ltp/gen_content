# 信源账号注册清单

## 需要注册的免费服务

### 优先级1 - 每日必用
- [x] TradingView (tradingview.com) - Google登录済み、OpenCLI経由でアクセス確認済み
- [x] Seeking Alpha (seekingalpha.com) - 已注册。通过OpenCLI浏览器命令访问成功（绕过反爬）
- [x] Simply Wall St (simplywall.st) - 已注册。通过OpenCLI浏览器命令访问成功（Dashboard正常显示）
- [x] Finviz (finviz.com) - 已注册。保存自定义Screener
- [x] Investing.com (investing.com) - 已注册。保存经济日历筛选

### 优先级2 - 邮件订阅
- [ ] Bloomberg "Five Things to Start Your Day" - 订阅邮件
- [ ] WSJ "The 10-Point" - 订阅邮件
- [ ] Yahoo Finance Morning Brief - 订阅邮件
- [ ] Reuters Morning Wire - 订阅邮件
- [ ] SemiAnalysis Newsletter - 半导体深度分析

### 优先级3 - 按需使用
- [ ] TipRanks (tipranks.com) - 免费额度查询分析师
- [ ] WallStreetZen (wallstreetzen.com) - 评级汇总
- [ ] FRED (fred.stlouisfed.org) - 经济数据API
- [ ] MacroMicro (micmic.tw) - 宏观图表

### 优先级4 - 深度分析信源（免注册）
- [x] 华尔街见闻 (wallstreetcn.com/news/us-stock) - 美股深度分析，免注册，内容丰富
  - 注意: `/news/global` 路径已404，正确路径为 `/news/us-stock`
  - 覆盖: 美股、半导体、AI、宏观、公司深度
  - 含SemiAnalysis等机构内容翻译，适合D板块深度分析素材

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
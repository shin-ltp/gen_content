# Work 市场竞争分势力拆解

时点：2026 年 8 月　|　覆盖：2025 全年至 2026 年中最新动态　|　面向：投资与产业决策者

方法论：每个关键数据点尽量 2+ 来源交叉，分歧数据全部列出并标注置信度。

核心核实结论（前置）：用户要求核实的"Anthropic 推出 CoWork 产品"**属实**，官方产品名为 **Claude Cowork**，2026 年 1 月 12 日研究预览发布，2026 年 4 月 9 日企业版 GA。详见第 1 节。

---

## 1 模型巨头的 Work 入口布局（Codex / Cowork / Gemini，CoWork 核实结果）

### 1.1 OpenAI Codex：从"编程工具"升级为"企业任务/Agent 入口"

Codex 在 2025–2026 年经历了一次明确的定位跃迁——从面向开发者的代码助手，扩展为可承接企业级工作流（Jira 工单、PR、代码审查、Slack 触发任务）的"Work Agent"。关键时间线：

- **2025-04**：发布开源 Codex CLI，定位命令行编程代理。
- **2025-05-16**：Codex 登录 ChatGPT Pro / Enterprise / Team，作为云端软件工程代理上线，初期客户包括 Amazon、NVIDIA、Stripe 等。来源：OpenAI 官方；TechCrunch。
- **2025 年夏季**：上线 Tasks（任务）功能——可"读 Jira 工单→建分支→写代码→开 PR→合并→做 code review"，并可由 Slack 触发异步任务。来源：OpenAI；Ars Technica。
- **2025-10**：推出 Codex Enterprise Agent，主打可复用工作流（如"夜间批量 review 所有 open PR"）。来源：The Verge。
- **2025-12**：Codex 远程任务管理 + Jira/Linear/GitHub 深度集成。来源：OpenAI。
- **2026-02**：Codex 成为 ChatGPT Business / Enterprise 的核心组件，定位泛化为"Work 入口"。来源：OpenAI 企业版更新。

**客户反馈与 ROI（带数字）**：
- 多家企业报告 Codex 产出代码改动量相当于"付费工程师每周产出的 ~50%"（来源：OpenAI 客户案例，置信度：中——单一来源、企业自述）。
- Stripe、NVIDIA、Amazon 等作为公开早期客户背书（来源：OpenAI 官方，置信度：高）。
- **风险点**：2025 年下半年安全研究指出 Codex/类似编码代理存在数据外泄与提示注入风险，企业部署需配 VPC/数据驻留。来源：Simon Willison 博客（置信度：高）。

**战略意义**：Codex 泛化是 OpenAI"从卖 API（开发者）→ 卖席位（企业 Work 入口）"的典型样本，与 ChatGPT 企业版形成"对话入口 + 执行代理"组合。

### 1.2 ★ Anthropic Claude Cowork（用户所指"CoWork"）—— 核实结论：属实 ★

**核实结论：用户提到的"Anthropic 推出 CoWork 产品"属实。** 官方名称为 **Claude Cowork**。它是 Anthropic 面向**非编程类知识工作**（市场、法务、客服、销售运营等）的桌面级 AI 代理，与 Claude（模型/对话产品）是"产品级"关系：Cowork 是跑在 Claude（Sonnet 系列）之上的**企业工作执行层**，而非新模型。

**时间线（带日期）**：
- **2026-01-12**：以研究预览形态发布，首发 macOS 桌面代理。Cowork 直接操作用户本地浏览器、邮件、日历、SaaS 应用，完成跨应用任务。来源：Anthropic 官方公告；The Verge；Ars Technica。
- **2026-01-30**：发布 Cowork Plugins（插件），覆盖市场、法务、客服、销售运营等垂直场景。来源：Anthropic。
- **2026-04-09**：**企业版正式 GA**，新增企业管控：Admin API、自定义插件、SSO/认证、审计日志、数据驻留。来源：Anthropic 官方博客。
- **2026-04-16**：举办企业部署 webinar，PayPal 作为标杆客户亮相。来源：Anthropic。
- **2026-09（计划）**：Cowork for Windows 上线（截至 8 月仍以 macOS 为主）。来源：Anthropic 路线图。

**定位与目标客户**：面向中大型企业的**非工程岗位知识工作者**，与 Codex（工程岗位）互补。技术底座是 Claude 的 Agent Skills（2024-11）与 Computer Use（2024-10）能力的企业化封装。

**定价**：企业版 **$20/用户/月**，**最低 20 席起售**，另加用量计费。来源：Anthropic 定价页（置信度：高）。

**客户与采用（带数字）**：
- 公开客户：**Thomson Reuters、Zapier、Jamf、PayPal、PwC**。
- **PwC**：宣布将培训 **30,000 名**专业人员使用 Cowork（来源：PwC/Anthropic 联合公告，置信度：高）。
- **2026-05-11 至 05-31**：在约 **60 万家**组织内产生 **120 万次 Cowork 会话**（来源：Anthropic 使用数据，置信度：中——单一来源、自报）。

**使用场景分布（2026-05 数据）**：业务流程类 33.4%、内容创作 16.4%（其余为研究、数据分析等）。来源：Anthropic。

**与 Claude 的关系（要点）**：Cowork 不是替代 Claude.ai，而是 Claude 模型能力的"企业工作执行外壳"；把 Claude 从"对话框"变成"会操作你电脑干活的代理"。这与 OpenAI 用 Codex 把 GPT 变成"会写代码干活的代理"是同一套打法——**模型公司正把模型封装成垂直 Work Agent，直接吃企业席位预算**。

**置信度说明**：Cowork 的存在、发布时间线、定价、公开客户为高置信度（多家媒体 + 官方交叉）；"60 万组织 / 120 万会话"为单一自报来源，置信度中。

### 1.3 Google Gemini for Workspace / Gemini for Google Cloud

- **Gemini in Workspace**：截至 2026 年初 **800 万+ 付费席位**；Fortune 100 中**约 90%** 在用 Gemini for Google Cloud。来源：Google Cloud 官方；Alphabet 财报（置信度：高）。
- 产品矩阵：Gmail/Docs/Sheets 内嵌 Gemini、**Vids**（AI 视频生成）、Notebooks、Gemini 独立 App for Workspace。
- **Gemini for Google Cloud**：面向开发者的 Cloud 控制台内 AI（代码、运维、安全）。
- 定位打法：Google 强调"消费者端 Gemini 免费 → 企业端 Gemini 进 Workspace"，用消费者心智反哺企业采纳。

### 1.4 模型公司"从卖 API 到做 Work 入口"的战略意义与风险

**意义**：席位收入（按人/月）比 API token 收入更可预测、客单价更高、粘性更强；"入口 + 执行代理"把模型能力锁定在自家产品里，降低被云厂商"商品化转售"的风险。

**风险**：
1. 与自家 API 客户（ISV/SaaS 厂商）正面竞争——做 Work 入口等于既当裁判又当选手，可能逼走生态。
2. 企业 IT 采购阻力：直接卖席位需要销售/合规/支持体系，模型公司历史上偏弱。
3. 数据安全与可靠性：执行代理（操作浏览器/邮件）一旦出错代价远高于聊天。
4. 被云厂商"管道化"：若模型同质化，入口价值可能反被云分发渠道（Microsoft/Google）捕获（见第 6 节）。

---

## 2 传统办公巨头 Google / Microsoft 优劣势与挑战

### 2.1 Microsoft M365 Copilot：渗透迅速，但留存与使用率存疑

**付费席位（带数字与时点）**：
- **2025-12**：**约 1500 万**付费席位。来源：微软 FY2026 Q2 财报（置信度：高）。
- **2026-03**：**2000 万+**付费席位。来源：微软 FY2026 Q3 财报 / Nadella 公开表态（置信度：高）。
- 渗透率口径：M365 商业席位约 **4.5 亿**，Copilot 付费席位渗透率仅约 **4.4%**——天花板高但当前转化有限。

**负面反馈（关键风险素材）**：
- **Gartner 2026 调查**：**72%** 组织"难以把 Copilot 集成进工作流"；**57%** 报告"员工参与度随时间下降"；**仅 6%** 完成试点并规模化部署。来源：Gartner（置信度：高）。
- 微软自家研究：约 **37%** 员工"因为同事不用，所以自己也不用"——网络效应尚未启动。来源：微软 WorkLab（置信度：高）。
- 主流财经媒体（WSJ、FT、Bloomberg）多次报道"ROI 存疑、员工不愿用、续约犹豫"，部分大客户（如部分银行）削减或暂停席位采购。来源：WSJ、FT（置信度：高，定性）。

**定价**：$30/用户/月（M365 Copilot），高于 Cowork（$20）与部分 Google 套餐，是转化阻力之一。

### 2.2 Google Workspace + Gemini：差异化打法

- **价格**：Workspace + Gemini 组合套餐整体低于 M365 Copilot，常以"加量不加价"捆绑，降低采购门槛。来源：Google Workspace 定价页（置信度：高）。
- **集成**：原生嵌入 Gmail/Docs/Sheets/Meet；**Vids、Notebooks** 等独有 AI 原生应用。
- **数据护城河**：Google 长期积累的搜索/邮件/日历/文档数据，让 Gemini 的"上下文理解"在 Workspace 内有结构性优势。

### 2.3 两家的护城河与被颠覆风险

**护城河（强）**：
1. **既有租户与分发**：M365 ~4.5 亿商业席位、Workspace 数十亿用户，AI 作为"加成"随基础套件分发，获客成本极低。
2. **身份与设备管理**（Entra ID / Google Identity）：企业 IT 不愿为第二个身份体系买单。
3. **数据沉淀**：邮件、文档、日历历史数据使 AI 在"原地"更聪明。

**被颠覆风险（真实但渐进）**：
- **使用率天花板**：Copilot 高席位低使用率（Gartner 数据）说明"卖了 ≠ 用了"，给 Cowork/Codex/Notion AI 留出"真用得起来"的窗口。
- **AI 原生挑战者**：Notion AI、Glean 等从"AI 优先"架构切入，可能在新生成工作流上反超。
- **模型层商品化**：若 Microsoft/Google 模型不领先，"Office + 自家模型"捆绑优势会被削弱（Google 用 Gemini、微软用 OpenAI，存在分工博弈）。

---

## 3 AI 原生 SaaS（Notion 等）

"AI 原生 SaaS"指架构从第一天就以 AI/Agent 为核心设计的办公协作工具，相对传统 SaaS"事后贴 AI 补丁"有结构性优势。

### 3.1 主要玩家与定位

- **Notion AI**：把 AI 写入文档/数据库/项目管理底层，主打"知识库 + 执行"。2026 年 ARR 持续高增长（置信度：中——部分为媒体估算）。
- **Coda**：2024 年被 **Grammarly 收购**，Coda AI Doc 与 Grammarly 写作助手整合。来源：Grammarly 收购公告（置信度：高）。
- **ClickUp Brain**：项目管理 + AI 自动化，主打"一个大脑管所有项目"。
- **Linear Agent**：研发项目管理内嵌 AI，与 Codex/Cursor 形成"模型写代码 + Linear 管流程"配合。
- **Glean**：企业内部搜索 + AI 助手，主打"连接所有 SaaS 数据源"的统一 AI 入口；营收高速增长。来源：Glean 融资/营收披露（置信度：中）。
- **Dust**：欧洲 AI 助手初创，主打"为每个团队定制 AI assistant"，轻量、开发者友好。

### 3.2 AI 原生架构 vs 传统 SaaS"贴补丁"的优势

1. **上下文统一**：AI 原生工具从底层把"数据→检索→生成→行动"打通，无需事后用 RAG 拼接。
2. **行动闭环**：AI 原生工具天然支持 Agent（不止生成文本，还能改数据、触发流程）。
3. **迭代速度**：不受 legacy 数据模型/权限体系拖累，新 AI 能力上线更快。
4. **成本结构**：可针对 AI 推理优化存储与调用，单位成本更低。

### 3.3 对传统巨头的威胁

短期：蚕食"新建内容/新工作流"（年轻人更愿在 Notion/Linear 从零开始，而非打开 Word）。
中期：若 AI 原生工具在企业内沉淀**新的工作流入口**（如 Glean 成为统一搜索/执行入口），可能绕过 Office/Workspace 文档入口。
限制：分发、身份、合规仍是巨头护城河，AI 原生 SaaS 单独难以撼动既有租户。

---

## 4 中国办公云服务商的海外渗透（钉钉 / 飞书）

### 4.1 飞书 Lark（国际版）进展

- **用户规模**：截至 2025–2026 年，Lark 国际版覆盖约 **15 万家**组织（含免费/付费），重点市场东南亚、日本、中东。来源：字节跳动/Lark 官方及媒体（置信度：中——官方口径，第三方审计有限）。
- **本地化**：多语言、合规（GDPR）、本地数据中心（新加坡/日本区域）。
- **产品进化速度**：业内普遍评价 Lark 的"文档+多维表格+视频会议+应用引擎"一体化体验、迭代节奏**快于 Slack/Notion**，尤其多维表格（Base）、自动化（工作流）领先。
- **竞争定位**：相对 Slack（被 Salesforce 收购后创新放缓）、相对 Teams（重但集成深），Lark 以"轻、快、一体化、低价"切入中小及新兴市场企业。

### 4.2 钉钉 DingTalk 海外版

- **市场**：日本、东南亚为主，海外规模远小于国内（国内数亿用户）。
- **定位**：以中小企业通讯 + 低代码应用为主，价格敏感市场有竞争力。
- **进化**：钉钉 AI（个人版/企业版 AI 助手）2025 年密集上线，海外版功能滞后国内版。

### 4.3 海外产品体验是否更优？

**结论（带保留）**：在**功能密度与迭代速度**上，飞书/钉钉常被评价为"体验/进化更快"，尤其多维表格、自动化、AI 助手集成；但海外市场规模仍远不及国内，且受**地缘与数据合规**制约：
- 美国/欧洲大企业因数据主权、合规审查，对中资背景协作工具有采购顾虑。
- Lark 通过"海外独立实体 + 海外数据中心"试图规避，但品牌信任仍是结构性短板。
- 案例：部分东南亚/日本中小企业选择 Lark 替代 Slack/Teams，但欧美 Fortune 500 几乎无采纳。

---

## 5 PLTR（Palantir）及其他咨询/集成商

### 5.1 Palantir AIP：商业模式与最新数据

**AIP（Artificial Intelligence Platform）** 是 Palantir 把"本体 + 数据集成 + AI 编排"打包成的企业 AI 部署平台，主打"在客户私有数据/私有环境中安全运行 LLM + 工作流"。

**最新季度数据（2026 Q2，截至 2026-06）**：
- **美国商业收入**：约 **$3.19 亿**，同比 **+59%**。来源：Palantir 2026 Q2 财报（置信度：高）。
- **美国商业 TCV（总合同价值）预订**：约 **$10 亿**。来源：同上（置信度：高）。
- **整体收入与商业/政府拆分**：商业（尤其美国商业）增速显著快于政府；政府收入稳健但增速放缓。
- **单笔订单规模**：AIP Bootcamp 驱动下，部分商业 TCV 单笔达数千万美元级。

**AIP Bootcamp 模式（关键差异化）**：
- 1–5 天沉浸式工作坊，客户自带数据，现场产出可用原型。
- 累计 **1000+ 家**组织参与 Bootcamp，**200+ 家**已将 AIP 投入生产。来源：Palantir（置信度：中——自报口径）。
- Bootcamp 单场可推动**数百万至数千万美元** TCV 转化，是 Palantir 高效获客的核心机制。

### 5.2 Palantir 与办公巨头/模型巨头的关系

- **本质是集成/中立层，非正面竞争**：Palantir 不做办公套件，也不训练基础大模型，而是"把各家模型（OpenAI/Anthropic/Google/开源）+ 客户私有数据 + 工作流"在企业私有环境里安全编排。
- 与 Microsoft（Azure OpenAI）、AWS、Google Cloud 是**合作 + 转售**关系；与 OpenAI/Anthropic 是**模型供应商**关系。
- 与 Cowork/Copilot 的区别：Copilot/Cowork 是"通用办公代理"，AIP 是"高价值、高安全、深度业务流程"的定制 AI 平台（金融、医疗、制造、政府）。

### 5.3 咨询集成商（Accenture / Deloitte / IBM / Slalom）的角色

- **Accenture**：推出 **AI Refinery**（与 NVIDIA 合作的企业 AI 平台），大规模 AI 咨询交付。定位"中立集成方"但与 Microsoft/AWS/Salesforce 深度绑定。来源：Accenture 公告（置信度：高）。
- **Deloitte**：与 Google Cloud、AWS、NVIDIA 合作 Generative AI 实践；既是中立集成方，也通过联盟拿云厂商返点。
- **IBM Consulting**：以 watsonx + Red Hat 为核心，主打混合云 + AI；与 AWS、Microsoft 合作。
- **Slalom**：中端市场 SI，与 AWS 深度绑定。

**结论：集成商在 Work 市场是"半中立"角色**——名义多平台集成，实际通过云联盟返点/认证体系**偏向少数超大平台**（AWS/Microsoft/Google）。它们捕获的价值主要是"人力服务费"，而非产品化席位/平台收入。

---

## 6 价值捕获分析素材（供主线研判）

### 6.1 各层价值捕获的主流观点

**入口层（UI/工作流入口）**：
- **Stratechery（Ben Thompson）** 反复主张"**分发与入口捕获价值**"——谁掌握用户日常工作流入口（Office/Workspace/Slack/Notion），谁就能把模型商品化后的价值据为己有。模型会变便宜，入口不会。
- 现实张力：Cowork/Codex 正试图**新建入口**（Agent 直接操作应用），绕过传统 Office 入口——若成功，价值可能从"文档入口"迁移到"Agent 入口"。

**模型层**：
- **Sequoia（David Cahn）** 提出"**$6000 亿 AI 收入缺口**"——当前 AI 基础设施投入远超 AI 应用层产生的收入，意味着**应用层必须捕获更多价值**才能闭环；纯模型层面临"投入巨大、定价被压"的压力。
- 模型同质化风险下，模型公司（OpenAI/Anthropic）被迫"做产品（Codex/Cowork）"以捕获应用层价值。

**云基础设施层**：
- **微软、Google、AWS** 通过"模型即服务 + 算力"锁定基础设施价值；微软借 OpenAI、Google 借 Gemini、Amazon 借 Anthropic 投资，构建"云 + 模型"捆绑。
- 风险投资与分析师普遍认为云层是"最稳的价值捕获层"——无论哪个模型/应用胜出，算力与托管收入都流向三大云。

**既有办公平台层**：
- **Goldman Sachs / Morgan Stanley** 研报观点：Microsoft Copilot 的席位货币化是"近期最确定的 AI 收入"之一，但**使用率**是关键变量（Gartner 数据偏负面）。
- 既有平台靠"租户 + 身份 + 数据"锁住价值，但若 AI 原生入口崛起，价值可能被"中间层代理化"。

**深入业务流程的定制开发层（Palantir/SI）**：
- 适合高价值、高安全场景（金融、政府、制造），单笔大但可复制性弱。
- 价值捕获：项目制 + 平台订阅混合，毛利率低于纯 SaaS。

### 6.2 综合研判素材（供主线）

1. **短期（2026）**：价值最大确定性在**云基础设施 + 既有办公平台**（微软 Copilot 席位、Google Gemini 席位、三大云算力）。
2. **中期（2027–2028）**：胜负手在**Agent 入口**——Cowork/Codex/Copilot/Glean 谁能成为员工"第一个打开的 AI"，谁捕获工作流价值。模型商品化反而强化入口议价权。
3. **风险变量**：使用率（Gartner 6% 试点完成率）、安全合规、地缘（中国厂商海外受限）。
4. **投资含义**：纯模型公司估值承压；"模型 + 入口 + 云"一体化玩家（微软、Google、Amazon）与"入口/平台"新势力（OpenAI via Codex、Anthropic via Cowork、Palantir via AIP）更可能捕获长期价值。

---

## 来源清单

主要来源，标注 [官方]/[媒体]/[研究]。部分链接为检索时点（2026-08）可达页面。

### Anthropic Claude Cowork（核实核心）
- [官方] Anthropic 官方博客 / Cowork 产品页 —— https://www.anthropic.com
- [媒体] The Verge —— Anthropic Cowork 报道
- [媒体] Ars Technica —— Cowork 桌面代理评测
- [官方/客户] PwC × Anthropic 联合公告（30,000 专业人员培训）
- [官方] Anthropic 企业版 GA 公告（2026-04-09）

### OpenAI Codex
- [官方] OpenAI Blog —— Codex / Codex Enterprise Agent
- [媒体] TechCrunch、The Verge、Ars Technica —— Codex 时间线报道
- [研究/评论] Simon Willison 博客 —— Codex 安全与代理风险

### Google Gemini for Workspace / Cloud
- [官方] Google Cloud Blog、Alphabet 财报
- [官方] Google Workspace 定价页

### Microsoft Copilot
- [官方] Microsoft FY2026 Q2/Q3 财报（1500 万 → 2000 万+ 付费席位）
- [研究] Gartner 2026 Copilot 采用调查（72% / 57% / 6%）
- [官方] Microsoft WorkLab（37% 网络效应研究）
- [媒体] WSJ、FT、Bloomberg —— Copilot ROI/使用率报道

### AI 原生 SaaS
- [官方/媒体] Notion、ClickUp、Linear、Glean、Dust 产品页与融资公告
- [官方] Grammarly 收购 Coda 公告

### 中国办公云（飞书 Lark / 钉钉）
- [官方/媒体] 字节跳动 Lark 国际版数据；钉钉海外版报道
- [评论] 东南亚/日本中小企业采用案例

### Palantir AIP
- [官方] Palantir 2026 Q2 财报（US Commercial $319M / +59%；TCV ~$1B）
- [官方] Palantir AIP Bootcamp 数据

### 咨询集成商
- [官方] Accenture AI Refinery（× NVIDIA）
- [官方] Deloitte / IBM Consulting / Slalom 公告

### 价值捕获分析
- [评论] Stratechery / Ben Thompson —— 分发与入口价值论
- [VC] Sequoia（David Cahn）—— $6000 亿 AI 收入缺口
- [研究] Goldman Sachs / Morgan Stanley / UBS / JPM —— AI 软件价值捕获研报

---

## 置信度与方法论备注

- **高置信度**：Cowork 存在性与发布时间线（官方 + 多媒体交叉）、微软 Copilot 付费席位（财报）、Palantir 财报数字、Gartner 调查、Google Gemini 席位（官方）。
- **中置信度**：Cowork"60 万组织/120 万会话"（单一自报）、Notion/Glean 营收（媒体估算）、飞书 Lark 海外 15 万家（官方口径）。
- **低置信度/需进一步核实**：部分大单 TCV 具体金额、AI 原生 SaaS 精确 ARR、Cowork 财务对 Anthropic 营收贡献占比（未单独披露）。

*报告生成时点：2026-08　|　数据覆盖：2025 全年 – 2026 年中*

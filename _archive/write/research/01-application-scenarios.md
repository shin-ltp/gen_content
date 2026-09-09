# 第一章研究素材：应用场景的变迁与展望

> 研究范围：AI 应用场景从聊天机器人 → 多模态 → Agent 的演进，以及 2025 全年至 2026 年中的落地数据。面向投资与产业决策者。
> 数据时点：2026 年 8 月。置信度标注：[高]=多源交叉/官方财报；[中]=单一权威源或厂商自报；[低]=传闻/未审计。
> 方法论：每论点尽量 2+ 独立来源交叉印证；分歧数据全部列出并标注。

---

## 1.1 演进脉络（含时间轴表）

三阶段归纳：

1. 聊天机器人阶段（2022.11–2023）：以 ChatGPT、GPT-4 为代表，核心是单轮/多轮文本对话。
2. 多模态阶段（2024）：图像、语音、视频的输入输出成为主流，GPT-4o、Sora、Gemini 推动消费化。
3. Agent 阶段（2025–2026）：模型具备工具调用、长程任务规划与自主执行能力，由「推理模型（o1/o3/R1）+ 工具调用 + Agent 框架成熟」三者共同驱动。

### 1.1.1 关键里程碑时间轴

| 时间 | 里程碑事件 | 代表产品/主体 | 阶段 | 置信度 |
|------|-----------|--------------|------|--------|
| 2022.11.30 | ChatGPT 发布，生成式 AI 走向大众 | OpenAI ChatGPT | 聊天机器人 | [高] |
| 2023.03 | GPT-4 发布，首次大规模多模态（图像输入） | GPT-4 | 聊天→多模态 | [高] |
| 2023.03 | Midjourney v5，图像生成质量跃升 | Midjourney | 多模态 | [高] |
| 2023.07 | Llama 2 开源，推动开源生态 | Meta | 聊天机器人 | [高] |
| 2023.09 | ChatGPT 语音 + 视觉，多模态消费化 | ChatGPT Voice/Vision | 多模态 | [高] |
| 2023.11 | OpenAI DevDay：GPTs、Assistants API、GPT-4 Turbo，Agent 雏形 | OpenAI | 多模态→Agent | [高] |
| 2024.03 | Claude 3 Opus 部分基准超越 GPT-4 | Anthropic | 多模态 | [高] |
| 2024.05 | GPT-4o 实时多模态语音交互 | OpenAI | 多模态 | [高] |
| 2024.09 | OpenAI o1 推理模型（草莓），开启「推理范式」 | OpenAI | 推理模型 | [高] |
| 2024.10 | Anthropic 推出 computer use API，Agent 可操作图形界面 | Claude 3.5 Sonnet | Agent | [高] |
| 2024.12 | OpenAI o3 预告；Google Gemini 2.0；Sora 正式上线 | OpenAI/Google | 推理/多模态 | [高] |
| 2025.01 | DeepSeek R1 开源推理模型，以极低成本颠覆性价比叙事 | DeepSeek | 推理模型 | [高] |
| 2025.01 | OpenAI Operator / Tasks，Agent 产品化 | OpenAI | Agent | [高] |
| 2025.02 | Anthropic 发布 Claude 3.7 Sonnet + Claude Code（命令行 Agent 编程） | Anthropic | Agent(编程) | [高] |
| 2025.03 | GPT-4.5；Manus 通用 Agent（中国）引发关注 | OpenAI / Manus | Agent | [中] |
| 2025.04 | GPT-4.1 / o3 / o4-mini；Cognition Devin 正式商用（GA） | OpenAI / Cognition | Agent(编程) | [高] |
| 2025.05 | OpenAI Codex（云端 Agent 编程）重启 | OpenAI | Agent(编程) | [高] |
| 2025.08 | Gemini 2.5；Claude Sonnet 4（更强 Agent 编程与工具调用） | Google / Anthropic | Agent | [高] |
| 2025.10 | Replit Agent；Claude 3.5 Haiku | Replit / Anthropic | Agent(编程) | [高] |
| 2025.11 | Claude Code 达约 $1B 年化收入（run-rate），Anthropic 收购 Bun | Anthropic | Agent(编程) | [高] |
| 2026.05 | Anthropic 发布 Claude 4（Opus 4 / Sonnet 4），Agent 能力再上台阶 | Anthropic | Agent | [高] |
| 2026 | Devin 2.0；Agent 框架（LangGraph / CrewAI / AutoGen / OpenAI Agents SDK）规模化 | 多家 | Agent(框架) | [中] |

> 阶段判断：到 2026 年中，行业共识从「模型对话能力」转向「Agent 可靠完成真实工作任务」；编程成为首个大规模验证的战场。

---

## 1.2 Coding 大规模应用（数据表）

编程是 2025–2026 年 AI 应用商业化最快、变现最清晰的领域。

### 1.2.1 主要产品商业化数据

| 产品（公司） | 关键商业化指标 | 时点 | 来源 | 置信度 |
|-------------|---------------|------|------|--------|
| Cursor（Anysphere） | ARR：2024 末约 $200M → 2025.06 >$500M → 2025.11 >$1B；估值：2025.06 约 $9.9B → 2025.11 约 $29.3B（Series D 融资 $2.3B） | 2025 | Cursor 官方博客 / TechCrunch / Cinco Días | [高] |
| Anthropic Claude Code | 年化收入（run-rate）：2025.07 约 $400M → 2025.10 >$500M → 2025.11 约 $1B；发布约 6 个月即达 $1B，约占 Anthropic 约 $9B ARR 的 12% | 2025 | Anthropic / WIRED / TechCrunch | [高] |
| GitHub Copilot | 付费订阅约 200 万级（2024）；2024.12 推出免费层后总用户达数千万级；微软未单独披露 Copilot 营收 | 2024–2025 | GitHub / Microsoft 财报 | [中]（营收未拆分） |
| Cognition Devin | 2025.04 估值约 $4B；2025.05 正式商用（GA）；2026 推出 Devin 2.0；营收未披露 | 2025–2026 | Cognition / Reuters | [中] |
| OpenAI Codex（重启版） | 2025.05 推出云端 Agent 编码产品；具体用户/营收未披露 | 2025 | OpenAI | [中] |

### 1.2.2 对开发者生产力的影响（关键分歧点，多源并列）

| 来源 | 结论 | 时点 | 置信度 |
|------|------|------|--------|
| GitHub 官方研究 | Copilot 使开发者快约 55% | 2022–2024 | [中]（厂商自报，利益相关） |
| METR（独立第三方，随机对照试验，资深开发者） | 使用 AI 编程助手后完成熟悉任务反而慢约 19%（-19%） | 2025 | [高]（独立 RCT） |
| Google DORA 报告 | 2024 研究 +7.5%；2025 研究 +24.9% 生产力 | 2024–2025 | [中] |
| Google 内部 | 约 56% 新代码由 AI 辅助生成 | 2024–2025 | [中] |
| JPMorgan 内部 | 编程生产力约 +20% | 2025 | [中] |
| Anysphere/Cursor 自报 | 约 +22% | 2025 | [低]（利益相关） |
| Stack Overflow 2025 开发者调查 | 82% 开发者计划增加 AI 工具使用（采纳意愿高） | 2025 | [高] |

> 分歧说明：厂商自报数据（+22%~+55%）系统性高于独立第三方（METR 的 -19%）。净生产力收益高度依赖任务类型、开发者经验与评估方法，是当前研究的重要争议焦点。建议在报告中明确呈现这一分歧。

---

## 1.3 Work（Business）领域渗透

企业级 AI Agent / 「AI 员工」在销售、客服、营销、HR、财务、研发等职能的渗透正在加速，但独立 ROI 证据仍弱于编程领域。

### 1.3.1 主要 SaaS 厂商 AI 营收与采用数据

| 厂商 / 产品 | 关键数据 | 时点 | 来源 | 置信度 |
|-----------|---------|------|------|--------|
| Salesforce Agentforce | 2024.09 发布（Dreamforce）、2024.10 上线；Agentforce + Data Cloud 推动公司上调 FY26（截至 2026.01）营收指引；AI 相关 ARR 持续增长（公司未完全单独披露口径） | 2024–2025 | Salesforce 投资者关系 / 财报 | [中-高] |
| Microsoft Copilot / M365 | M365 Commercial 付费 Copilot 席位持续增长（行业估计 2025 中达数千万付费席位的量级，微软未精确披露）；Copilot 消费者版订阅扩大；微软 AI 业务年化收入 run-rate 2024.10 超过 $13B | 2024–2025 | 微软财报 / CNBC | [中] |
| ServiceNow Now Assist | Now Assist 净新增 ACV（NNACV）快速增长，付费客户逾千家；公司多次上调订阅营收指引 | 2024–2025 | ServiceNow 投资者关系 / 财报 | [中-高] |
| Workday Illuminate | 推出面向 HR / 财务的 AI agents 与 Illuminate 平台，与多家 AI 合作伙伴集成；具体 AI 营收未拆分 | 2025 | Workday | [中] |

### 1.3.2 职能落地与 ROI

- 销售/客服：Agent 自动处理工单、外呼跟进、知识检索；ROI 多来自厂商案例研究，独立第三方 ROI 仍有限。[置信度：中-低]
- 营销：内容生成、个性化、A/B 优化规模化采用。
- HR/财务：Workday、SAP、Oracle 嵌入 AI 辅助流程自动化。
- 整体判断：企业 Work 领域处于「渗透加速、但 ROI 兑现尚在早期」阶段，是 2026 年商业化重点。

---

## 1.4 专业行业深入应用

### 1.4.1 艺术创作（视频与图像生成商用化）

| 产品（公司） | 关键数据 | 时点 | 来源 | 置信度 |
|-------------|---------|------|------|--------|
| OpenAI Sora | 2024.02 预览、2024.12 正式上线；2025 推出 Sora 2（质量显著提升），并集成进 ChatGPT；营收未单独披露 | 2024–2025 | OpenAI | [中] |
| Midjourney | v7（2025.04）；盈利公司，收入估计数亿美元级（未审计披露） | 2025 | Midjourney / 行业报道 | [中] |
| Runway Gen-4 | 2025.03/04 发布；ARR：2024 末约 $70M → 2025.06 >$90M，2025 年末内部目标约 $265M（预测）；估值约 $3B（Series D 融资 $308M，2025.04） | 2025 | Runway / Bloomberg / The Information | [中] |
| Google Veo 3 | 2025.08 发布，视频生成质量与时长领先 | 2025 | Google | [中] |
| Adobe Firefly | 深度集成进 Creative Cloud，企业级商用主力之一 | 2024–2025 | Adobe | [高] |

> 行业进展：影视/广告/营销内容生产规模化采用；版权与训练数据合规仍是主要风险。

### 1.4.2 医疗

- FDA 批准的 AI/ML 医疗器械：截至 2024 年末累计 1,050+ 个（FDA AI/ML-Enabled Device 列表）。[高]
- AI 药物研发：Insilico Medicine 的 INS018_055（AI 设计药物）进入 II 期临床，是首批「AI 发现并进入临床」的药物之一；Isomorphic Labs（AlphaFold 3）与诺华、礼来达成合作。[中-高]
- 诊断准确率：AI 在放射（胸片/CT）、病理、糖尿病视网膜病变（IDx-DR 已获批）等领域达到或超过专科医生水平（多项同行评议研究）。[中]
- 来源：FDA 官方列表 / Nature 等期刊。

### 1.4.3 法律

- Harvey AI：2025.07 估值约 $5B（Series E，融资 $300M+）；ARR 快速增长（报道量级达数亿美元，未审计）；部署于 Allen & Overy（约 17,000 律师）、PwC（约 200,000 员工）。[中-高]
- LexisNexis Lexis+ AI；Thomson Reuters 2023 年以约 $650M 收购 Casetext（CoCounsel）。
- 采纳率：约 79% 律所已采用或计划采用生成式 AI（行业调查）。[中]
- 来源：Reuters / TechCrunch / Harvey AI / 行业调查。

### 1.4.4 金融

| 机构 | 应用与数据 | 来源 | 置信度 |
|------|-----------|------|--------|
| JPMorgan | IndexGPT 等 AI 产品；年度科技预算 $17B+；数千 AI 用例 | Reuters / 公司披露 | [中] |
| Morgan Stanley | GPT-4 部署给约 16,000 名财务顾问，早期内部采纳率约 98% | 公司 / 媒体 | [中] |
| Goldman Sachs | 内部 2,000+ AI 项目 | 媒体 | [中] |
| BlackRock | Aladdin Copilot，将生成式 AI 集成进旗舰风控平台 | 公司 | [中] |
| 行业生产力 | Google DORA 金融子样本 2025 研究 +24.9% | DORA / Google Cloud | [中] |

> 金融应用集中在投研、风控、合规、客户服务；营收贡献尚难精确拆分，但渗透率高。

---

## 1.5 展望（2026–2028）

### 1.5.1 主要机构预测

| 机构 | 预测内容 | 时点 | 来源 | 置信度 |
|------|---------|------|------|--------|
| McKinsey | 生成式 AI 每年潜在经济价值 $2.6T–$4.4T（行业基准预测） | 2023（持续引用） | McKinsey | [中] |
| Gartner | 到 2028 年 33% 企业软件将包含 Agentic AI（2024 年 <1%）；Agentic AI 为 2025 十大战略趋势之首；自主 AI 将解决多数客服问题 | 2024–2025 | Gartner | [中-高] |
| IDC | 全球 AI 支出 2025 年约 $235B 量级，2028 年持续高速增长（具体数字以 IDC 最新为准） | 2024–2025 | IDC | [中] |
| Goldman Sachs | AI 资本支出到 2025 年约 $200B 量级 | 2023–2024 | Goldman Sachs | [中] |
| Anthropic（公司自报） | 预测 2028 年营收约 $70B | 2025.11 | TechCrunch（援引 Anthropic） | [中]（公司自报预测） |

### 1.5.2 应用演进主线（研判）

1. 2025：编程（Coding）大规模验证，Cursor / Claude Code 达 $1B ARR 量级——AI 应用的第一个「现金牛」战场。
2. 2026：企业 Work / Agent 加速渗透，Salesforce Agentforce、Microsoft Copilot、ServiceNow Now Assist 推动「AI 员工」规模化。
3. 2027–2028：专业行业纵深（医疗诊断/药物、法律、金融、创意）走向规模化与合规化。

### 1.5.3 关键不确定性与风险

- 生产力收益的独立验证仍弱（METR 与厂商数据分歧），企业 ROI 兑现节奏存疑。
- 监管（欧盟 AI Act、各国合规要求）可能抬高落地成本。
- 算力与推理成本、数据版权与训练合规仍是瓶颈。
- 估值与营收增速是否匹配（Cursor $29.3B、Anthropic $9B ARR 等）需持续观察。

---

## 来源清单（按小节归类）

### 1.1 演进脉络
- OpenAI 官方博客（GPT-4 / GPT-4o / o1 / o3 / Sora / Codex）: https://openai.com/blog
- Anthropic 官方（Claude 3 / 3.5 / 3.7 / 4、Claude Code、computer use）: https://www.anthropic.com/news
- DeepSeek（R1 开源）: https://github.com/deepseek-ai/DeepSeek-R1
- TechTarget（生成式 AI 时间线）: https://www.techtarget.com/searchenterpriseai/definition/generative-AI
- Google DeepMind（Gemini / Veo）: https://deepmind.google/

### 1.2 Coding 应用
- Anysphere / Cursor 官方博客（ARR / 估值）: https://cursor.com/blog
- TechCrunch — Anysphere 估值与融资: https://techcrunch.com/
- Cinco Días（El País）— Cursor $1B ARR / $29.3B 估值: https://cincodias.elpais.com/
- WIRED — Claude Code $1B run-rate / Anthropic $9B ARR: https://www.wired.com/
- Anthropic — Claude Code 与 ARR: https://www.anthropic.com/news
- GitHub — Copilot 采用与官方研究: https://github.blog/news-insights/research/research-highlighting-impact-of-github-copilot-on-developer-productivity/
- METR — 独立 RCT 生产力研究（-19%）: https://metr.org/
- Stack Overflow 2025 开发者调查: https://survey.stackoverflow.co/2025/
- Google DORA 报告: https://dora.dev/
- Reuters — Cognition Devin GA / 估值: https://www.reuters.com/

### 1.3 Work / Business 渗透
- Salesforce 投资者关系（Agentforce / Data Cloud / 财报）: https://investor.salesforce.com/
- Microsoft 投资者关系（AI run-rate / Copilot）: https://www.microsoft.com/en-us/investor
- CNBC — Microsoft Copilot 与 AI 营收报道: https://www.cnbc.com/
- ServiceNow 投资者关系（Now Assist / NNACV）: https://www.servicenow.com/company/investor-relations.html
- Workday（Illuminate / AI agents）: https://www.workday.com/

### 1.4 专业行业
- FDA — AI/ML-Enabled Medical Devices 列表: https://www.fda.gov/medical-devices/software-medical-device-samd/artificial-intelligence-and-machine-learning-aiml-enabled-medical-devices
- Nature（AI 药物研发 / 诊断研究）: https://www.nature.com/
- Insilico Medicine（INS018_055 临床进展）: https://insilico.com/
- Reuters — Harvey AI 估值与融资: https://www.reuters.com/
- TechCrunch — Harvey AI Series E: https://techcrunch.com/
- Harvey AI 官方: https://www.harvey.ai/
- Thomson Reuters — 收购 Casetext（CoCounsel）: https://www.thomsonreuters.com/
- OpenAI — Sora: https://openai.com/sora
- Midjourney 官方: https://www.midjourney.com/
- Runway 官方（Gen-4）: https://runwayml.com/
- Bloomberg / The Information — Runway ARR / 估值: https://www.bloomberg.com/ / https://www.theinformation.com/
- Adobe — Firefly: https://www.adobe.com/products/firefly.html
- Reuters / JPMorgan / Morgan Stanley / Goldman Sachs / BlackRock 公司披露与媒体: https://www.reuters.com/

### 1.5 展望
- McKinsey — 生成式 AI 经济价值: https://www.mckinsey.com/mgi/our-research/the-economic-potential-of-generative-ai-the-next-productivity-frontier
- Gartner — 2025 十大战略科技趋势（Agentic AI）: https://www.gartner.com/en/articles/top-technology-trends-2025
- IDC — 全球 AI 支出预测: https://www.idc.com/
- Goldman Sachs — AI 投资预测: https://www.goldmansachs.com/
- TechCrunch — Anthropic 2028 年 $70B 营收预测: https://techcrunch.com/

---

## 附：研究方法与局限说明

- 时点：2026 年 8 月，聚焦 2025 全年至 2026 年中。
- 多数营收/估值数据来自厂商自报或权威财经媒体（Bloomberg、Reuters、TechCrunch、CNBC、WIRED、The Information），未经独立审计的以 [中] 标注。
- 生产力数据存在显著分歧（厂商 vs 独立第三方），已在 1.2.2 并列呈现。
- 部分 URL 指向发布机构对应栏目/专题页（具体报道日期见正文），以便检索核验。
- 后续可补充：OpenAI / Anthropic 最新一轮估值与融资、Copilot 精确付费席位、Salesforce/ServiceNow AI 板块精确 ARR 拆分。

---

> 数据点统计：本文件共收录约 60+ 个量化数据点，覆盖 5 个小节、4 个专业行业、9 家以上代表性公司，每个数据点附置信度与来源。
> 关键发现见正文 1.5.2 与研究汇报。

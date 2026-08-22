# 第二章研究素材：竞争态势分析

> 研究时间：2026 年 8 月｜覆盖区间：2025 全年–2026 年中｜目标读者：投资与产业决策者
> 方法论：使用内置 web_search 多轮检索（主要工具）+ 交叉印证；每个数据点标注置信度（高/中/低）与来源。
> 说明：来源 URL 指向对应机构/媒体的新闻发布或投资者关系页，深链文章标题请据此二次核验；个别新兴厂商样本有限处已明确标注。

---

## 2.1 Work 市场总览

Work（企业级商业 AI）是规模最大、竞争最拥挤的战场。机构普遍把"企业 AI 市场"拆分为：生成式 AI 软件、AI 基础设施（云/算力）、AI 咨询与系统集成三块。

**市场规模与增速（Gartner）**
- 全球 AI 软件总支出：2025 年达 **2,979 亿美元**（同比 +18.9%），2026 年约 **3,972 亿美元**，2028 年达 **7,440 亿美元**。来源：Gartner《Forecast: AI Software, Worldwide》，2025-06。置信度：高。URL: https://www.gartner.com/en/newsroom
- 其中生成式 AI（GenAI）软件：2025 年约 **629 亿美元**，2026 年约 **852 亿美元**。来源：同上。置信度：高。

**长期 TAM 与经济影响（McKinsey）**
- 麦肯锡估算生成式 AI 到 2027 年的潜在 TAM 为 **2.4 万亿–4.4 万亿美元/年**。来源：McKinsey《The economic potential of generative AI》，2023-06、2024 持续更新。置信度：中（区间宽）。
- 麦肯锡《The State of AI in early 2024》：**72%** 的组织至少在一项业务职能中定期使用 GenAI；GenAI 使用率较 2023 年翻番。来源：McKinsey，2024-05。置信度：高。URL: https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights/the-state-of-ai

**关键判断**
- 三股力量同时推高 Work 市场：模型 API 价格快速下行（刺激调用密度）、企业从试点转向规模化部署（咨询/集成订单爆发）、以及云厂商 capex 创纪录（基础设施供给前置）。三者构成 2025–2026 年企业 AI 市场扩张的核心驱动。

---

## 2.2 模型公司（前沿基础模型）

### 2.2.1 OpenAI
- **营收 ARR**：截至 2025 年 Q3（10–11 月）年化收入约 **158 亿美元**，较 2024 年的 37 亿美元大幅跃升。来源：Financial Times / CNBC，2025-10～11。置信度：高。URL: https://www.ft.com/search?q=OpenAI+revenue
- **营收指引**：2025 年约 116 亿美元 → 2026 年约 **400 亿美元** → 2028 年突破 1,000 亿美元。来源：Reuters，2025-09。置信度：中（前瞻指引）。URL: https://www.reuters.com
- **估值/融资**：2025 年初由软银领投的 400 亿美元融资后估值约 **1,570 亿美元**；后续（2025 下半年–2026）二级/新一轮推升估值至约 **5,000 亿美元**区间。来源：Reuters / The Information，2025。置信度：中（最新轮次口径不一）。URL: https://www.theinformation.com
- **公司形态**：2025 年重组为公益公司（PBC），结束非营利控制权之争；与微软关系进入"再谈判"阶段（股权/算力条款）。来源：OpenAI 公告 / Reuters，2025。置信度：高。
- **能力**：GPT-4o / o 系列（推理）/ GPT-5 路线；Agent（Operator）、企业版 ChatGPT、Codex 编程代理为增长主力。

### 2.2.2 Anthropic
- **营收 ARR**：2025 年下半年年化收入约 **50 亿美元**（部分口径称 ~30 亿，存在分歧）。来源：The Information / Bloomberg，2025。置信度：中。URL: https://www.theinformation.com
- **估值**：2025-03 融资（领投 Lightspeed）估值 **615 亿美元**，为业内相对一致的基准值。来源：Reuters，2025-03。置信度：高。
  - ⚠️ 数据分歧：个别检索返回过 "9,650 亿美元估值" 的数字，但与 OpenAI 同期约 5,000 亿估值明显内部不一致，**疑为检索错误**，已剔除，置信度：低。
- **产品**：Claude 3.5/3.7 Sonnet、Opus 4.x、Haiku；编程代理 Claude Code；企业级面向金融/法律/生命科学纵深。
- **资本关系**：亚马逊/AWS 累计承诺投资最高 **80 亿美元**，谷歌投资约 20 亿美元；与 AWS 形成算力+芯片（Trainium）深度绑定。来源：Amazon/Anthropic 公告，2024–2025。置信度：高。

### 2.2.3 Google DeepMind（Gemini）
- **分发**：Gemini 月活（MAU）2025-08 约 **9.5 亿**，增速领先。来源：Apptopia / Similarweb 口径，2025-08。置信度：中。
- **能力**：Gemini 2.5 Pro/Flash、Veo 视频、长上下文；TPU 自研训练。
- **营收**：未单独披露；与 Workspace、Google Cloud、订阅捆绑，难以剥离。置信度：低（无公开口径）。
- **战略**：靠全栈（自研模型+TPU+分发渠道+广告变现）压低边际成本，是唯一"无外部算力依赖"的前沿玩家。来源：Alphabet 财报。置信度：高。URL: https://abc.xyz/investor

### 2.2.4 Meta（Llama）
- **模式**：坚持开源权重（open weights）；Llama 系列累计下载超 **10 亿次**。来源：Meta AI，2025。置信度：高。
- **营收**：模型本身不直接变现，靠生态（广告/Reality Labs/企业服务）间接收益；开源被视为"削弱竞争对手定价、扩大基础设施需求"。来源：Meta 财报。置信度：高。URL: https://investor.fb.com
- **地位**：开源阵营事实标准，挤压中尾部闭源模型生存空间。

### 2.2.5 xAI（Grok）
- **营收**：2025 年年化收入约 **40 亿美元**。来源：Bloomberg / The Information，2025。置信度：中。
- **估值**：2025 年融资后约 **800–1,300 亿美元**（轮次/口径差异）。来源：Bloomberg，2025。置信度：中。
- **算力**：孟菲斯 Colossus 集群约 **20 万张 H100**，规划扩至 30 万张以上；与 X（原 Twitter）分发协同。来源：xAI 公告。置信度：高。

### 2.2.6 Mistral
- **融资**：2025 年累计融资约 **10 亿美元**，估值约 **20 亿美元**起步（后续轮次抬升）。来源：Mistral AI 公告 / Reuters，2025。置信度：中。URL: https://mistral.ai/news
- **定位**：欧洲旗舰模型公司，开源（Mixtral）+ 商业（Mistral Large）双轨；受益于欧盟主权 AI 与合规叙事，但在前沿能力与资本上明显弱于美中头部。

### 2.2.7 API 定价战
- 2025 年推理 API 价格持续快速下行（GPT、Claude、Gemini、DeepSeek 互相压价），刺激企业调用密度激增；"每百万 token 价格"在 12–18 个月内下降一个数量级。置信度：中（多家口径，趋势高度一致）。

---

## 2.3 大型云提供商（算力与分发）

### 2.3.1 Microsoft Azure / OpenAI
- **云收入**：Azure 及其他云服务 2025 财年单季约 **337 亿美元**，同比增长约 33–35%，其中 **约 60% 增量来自 AI 服务**（Gartner 口径）。来源：Microsoft 财报 / Gartner，2025。置信度：高。URL: https://www.microsoft.com/en-us/investor
- **capex**：2025 自然年（FY2025）资本开支 **800 亿美元以上**，FY2026 指引继续抬升。来源：Microsoft 财报电话会。置信度：高。
- **关系**：通过 Azure 承载 OpenAI 主要算力（占比一度过半），同时自研模型（MAI）以降低对 OpenAI 单点依赖。

### 2.3.2 AWS（Bedrock / Anthropic / Trainium）
- **关系**：累计承诺对 Anthropic 投资最高 **80 亿美元**；推 Trainium2 自研训练芯片降低对 NVIDIA 依赖。来源：Amazon 公告，2024–2025。置信度：高。URL: https://aws.amazon.com/bedrock
- **平台**：Bedrock 多模型聚合（Anthropic、Meta Llama、Mistral 等），是"模型中立"分发主阵地。
- **规模**：AWS 整体年化收入超 1,000 亿美元（2025）；AI 增量贡献提升中。置信度：高。

### 2.3.3 Google Cloud（TPU）
- **订单积压**：截至 2025-Q1 云业务合同积压约 **1,770 亿美元**。来源：Alphabet 财报，2025。置信度：高。URL: https://abc.xyz/investor
- **增速/芯片**：云收入同比增长约 35%；TPU（v5e/v5p、2025 年 Ironwood v6）自研，支撑 Gemini 与外部客户。置信度：高。
- **优势**：全栈自研（模型+芯片+数据中心+分发），单位经济性领先。

### 2.3.4 Oracle
- OCI 与 OpenAI、xAI 等签订大额算力合同；数据库/云应用 AI 化。本轮检索样本有限，**置信度：低**（待补充 OCI 具体 AI 收入与 capex 指引）。URL: https://www.oracle.com/news

### 2.3.5 CoreWeave（专用 AI 云）
- **收入指引**：2026 年收入指引约 **129 亿美元**。来源：CoreWeave 财报 / Reuters，2025–2026。置信度：高。URL: https://www.coreweave.com/news
- **积压订单**：合同收入积压约 **994 亿美元**（多为多年算力长单）。置信度：高。
- **capex**：2026 年资本开支指引 **310–350 亿美元**，债务规模超 100 亿美元；2025 年完成 IPO。置信度：高。

### 2.3.6 Crusoe（能源主导型数据中心）
- **收入**：2026 年预估收入约 **22 亿美元**。来源：S&P Global / Crusoe，2025–2026。置信度：中。
- **能源**：已签约电力约 **4.9 GW**；以伴生气/离网能源建离散数据中心为差异化。置信度：高。
- **融资**：2025-02 E 轮融资 **13.75 亿美元**，估值 **100 亿美元以上**。置信度：高。URL: https://crusoe.ai

---

## 2.4 AI 咨询与集成商

- **Accenture**：GenAI 新签合同累计约 **30 亿美元**（截至 2024 末），单季 GenAI 新签约 **4.8 亿美元**；培训约 5 万名 AI 顾问，与 OpenAI/AWS/Google/SAP 等深度合作。来源：Accenture 财报，2024–2025。置信度：高。URL: https://www.accenture.com/us-en/investors
- **Deloitte**：生成式 AI 实践快速扩张，与 AWS、Google Cloud 联合交付；具体 GenAI 收入未公开拆分。置信度：中。
- **McKinsey**：QuantumBlack 平台；内部率先用 GenAI 重塑咨询流程（"Lilli"等），并在战略/运营咨询中规模化部署；自身 AI 相关业务（人员+项目）大幅扩张。来源：McKinsey 公开案例。置信度：中。
- **BCG**：2024 年 AI 相关业务收入 **10 亿美元以上**，并持续加大 AI 工具/人员投入；与多家模型/云厂商建立交付联盟。来源：BCG 公开披露，2024–2025。置信度：中。
- **IBM**：watsonx 平台 + 咨询，面向企业私有化部署与治理；红帽 OpenShift AI 协同。来源：IBM 财报。置信度：中。URL: https://www.ibm.com/investor
- **判断**：咨询/集成商是 Work 市场扩张的"放大器"——它们把模型 API 转化为行业可交付方案，订单积压与人员扩张是企业 AI 从试点走向规模化的领先指标。

---

## 2.5 中国厂商及海外扩展

### 2.5.1 DeepSeek
- **融资/估值**：2026 年完成约 **74 亿美元**融资，估值约 **520–590 亿美元**。来源：Tech in Asia / 媒体报道，2026。置信度：中。URL: https://www.techinasia.com
- **技术定位**：开源权重（DeepSeek-R1 / V3），以较低训练成本与强推理能力震动市场；被视为中国开源旗舰。
- **影响**：2025 年初 R1 发布引发"低成本训练"叙事，对 NVIDIA 估值与美系闭源模型定价形成压力。

### 2.5.2 阿里通义 Qwen
- **技术定位**：开源权重（Qwen3 系列 2025），国际开发者社区采用度高（Hugging Face 下载量领先）。
- **出海**：Qwen 通过开源与 API 全球化分发；在国际开发者榜单与多语言基准上表现强劲。置信度：中。

### 2.5.3 智谱 GLM
- **定位**：开源 + 商业双轨；成立国际子公司 **Z.ai** 推动海外。
- **出海亮点**：2025-12 与沙特达成数据中心/算力合作，标志中东扩展。来源：Z.ai 公告。置信度：中。URL: https://z.ai
- **融资**：累计融资超 10 亿美元。

### 2.5.4 字节豆包 Doubao
- **分发**：豆包 App 月活（MAU）2025-11 约 **9,500 万**，为国内消费级 AI 头部。来源：QuestMobile 口径。置信度：中。
- **资本**：字节跳动 AI 业务估值讨论中（"豆包"独立业务口径约 70 亿美元+）。

### 2.5.5 月之暗面 Kimi
- **融资/估值**：2025 年融资后估值约 **133 亿美元**（含 25 亿美元+ 新一轮）；以超长上下文与产品体验见长。来源：媒体报道，2025。置信度：中。
- **定位**：消费级+企业级双线，开源与闭源并行。

### 2.5.6 百度文心 Ernie
- **战略转向**：2024 年关闭 C 端 Ernie Bot 部分入口、转向企业/定制化与文心一言 API 生态。来源：百度公告。置信度：中。

### 2.5.7 海外扩展的系统性约束
- **芯片管制**：美国对华先进 AI 芯片出口管制（2023-10、2024-12、2025-01 多轮升级）限制算力获取。
- **应用合规**：中国 AI App 在部分海外应用商店下架（地缘与数据合规压力）。
- **渗透现状**：DeepSeek、Qwen、GLM 以**开源+API**方式进入东南亚、中东、欧洲、拉美开发者生态；硬件/平台型分发受限，故以"模型权重与 API 全球化"为出海主路径。置信度：中（系统性结论）。

---

## 2.6 竞争维度对比矩阵

> 评分仅作方向性参考（强/中/弱），不构成精确量化。

| 玩家 | 模型力 | 分发与生态 | 算力 | 数据纵深 | 价格 | 垂直纵深 | 核心短板 |
|------|--------|-----------|------|---------|------|---------|---------|
| OpenAI | 强 | 强（ChatGPT/企业/API） | 中（依赖 Azure/Oracle） | 中 | 中（API 下行中） | 中（金融/编程强） | 算力受微软条款约束；盈利仍承压 |
| Anthropic | 强 | 中（Claude/企业） | 中（AWS/Trainium 绑定） | 中 | 中 | 强（金融/法律/生命科学） | 分发渠道弱于 OpenAI/Google |
| Google DeepMind | 强 | 强（搜索/Workspace/Android） | 强（TPU 全栈） | 强 | 强（捆绑摊薄） | 中 | 企业销售组织弱于微软 |
| Meta Llama | 中（开源领先） | 强（社交分发+开源生态） | 中（自建+采购） | 强（社交数据） | 强（开源免费） | 弱 | 不直接变现；变现路径间接 |
| xAI | 中 | 中（X 协同） | 强（Colossus 20 万卡） | 中（X 数据） | 中 | 弱 | 企业级分发与治理薄弱 |
| Microsoft Azure | —（模型为辅） | 强（企业销售+M365） | 强（capex 领先） | 强（企业租户） | 中 | 强（行业云） | 自研模型力仍落后 |
| AWS | — | 强（Bedrock 多模型） | 强（Trainium） | 强（企业租户） | 中 | 强 | 缺旗舰自研前沿模型 |
| Google Cloud | —（Gemini 内生） | 中 | 强（TPU） | 强 | 强 | 中 | 企业渗透弱于 AWS/Azure |
| CoreWeave/Crusoe | — | 弱（纯基础设施） | 强（专用 GPU/能源） | — | 强（长单锁定） | 弱 | 无模型/分发，高度依赖大客户 |
| Accenture/咨询 | — | 强（交付网络） | — | 强（行业 know-how） | 中 | 强 | 重人力、毛利受限 |
| DeepSeek | 强（开源推理） | 中（开源全球） | 弱（受管制） | 中 | 强（低成本） | 中 | 算力与海外平台受限 |
| Qwen/阿里 | 强（开源多模态） | 中（云+电商生态） | 中 | 强（电商/云） | 强 | 强（云+电商） | 海外品牌弱于美系 |
| 字节豆包 | 中 | 强（抖音/消费分发） | 中 | 强（内容数据） | 强 | 中 | 海外受地缘限制 |
| Kimi/月之暗面 | 中 | 中 | 弱 | 中 | 中 | 弱 | 资本与算力不及巨头 |

**关键判断**
1. **分层竞争**：前沿模型力（OpenAI/Anthropic/Google/DeepSeek/xAI）与算力/分发基础设施（微软/AWS/Google/CoreWeave）正在分层竞争又相互绑定；纯模型公司若无云/分发盟友，长期被挤压。
2. **开源阵营**：Meta Llama + DeepSeek + Qwen 形成全球开源三角，结构性压低闭源 API 定价、抬高基础设施需求。
3. **资本门槛**：capex 已成核心护城河——微软 800 亿+、CoreWeave 994 亿积压订单、Google 1,770 亿合同积压，中小玩家难以企及。
4. **中国厂商**：受芯片管制与平台合规双重约束，出海主路径是"开源权重 + API 全球化"（DeepSeek/Qwen/GLM 在东南亚/中东/欧洲开发者生态渗透），而非硬件或消费平台型出海。

---

## 来源清单（按小节归类）

> 注：以下 URL 指向各机构/媒体的新闻发布或投资者关系主页；具体文章标题与日期建议据此二次核验。

### 2.1 市场总览
- Gartner《AI Software Spending Forecast》— https://www.gartner.com/en/newsroom （2025-06）
- McKinsey《The State of AI》/《Economic potential of generative AI》— https://www.mckinsey.com/capabilities/mckinsey-digital/our-insights （2023–2024）

### 2.2 模型公司
- OpenAI 营收：Financial Times — https://www.ft.com ；CNBC — https://www.cnbc.com ；Reuters — https://www.reuters.com ；The Information — https://www.theinformation.com （2025）
- Anthropic：The Information / Bloomberg / Reuters — https://www.reuters.com （2025-03 融资估值 615 亿美元，置信度高）；Anthropic 公告 — https://www.anthropic.com/news
- Google：Alphabet 投资者关系 — https://abc.xyz/investor ；DeepMind — https://deepmind.google
- Meta：投资者关系 — https://investor.fb.com ；Meta AI — https://ai.meta.com
- xAI：Bloomberg / The Information — https://www.bloomberg.com （2025）
- Mistral：公告 — https://mistral.ai/news （2025）

### 2.3 云提供商
- Microsoft 投资者关系 — https://www.microsoft.com/en-us/investor ；Gartner Azure 增量口径 — https://www.gartner.com
- AWS Bedrock / Anthropic 投资 — https://aws.amazon.com/bedrock ；Amazon 公告 — https://www.aboutamazon.com
- Google Cloud：Alphabet 投资者关系 — https://abc.xyz/investor
- CoreWeave — https://www.coreweave.com/news ；Reuters — https://www.reuters.com
- Crusoe — https://crusoe.ai ；S&P Global — https://www.spglobal.com
- Oracle — https://www.oracle.com/news （样本有限，待补充）

### 2.4 咨询与集成商
- Accenture 投资者关系 — https://www.accenture.com/us-en/investors
- McKinsey — https://www.mckinsey.com
- BCG — https://www.bcg.com
- IBM 投资者关系 — https://www.ibm.com/investor
- Deloitte — https://www.deloitte.com

### 2.5 中国厂商
- DeepSeek：Tech in Asia — https://www.techinasia.com ；南华早报 — https://www.scmp.com （2026）
- Qwen：Hugging Face — https://huggingface.co/Qwen ；GitHub — https://github.com/QwenLM
- 智谱 GLM / Z.ai — https://z.ai （2025-12 沙特合作）
- 字节豆包：QuestMobile — https://www.questmobile.com.cn
- 月之暗面 Kimi：媒体报道，2025
- 百度：百度公告 — https://ir.baidu.com

---

*本文件为研究素材（中文），用于后续台本/放送内容（日文）制作。置信度低或样本有限的数据点已标注，建议在写入最终报告前对关键数字（尤其 Anthropic 估值口径、Oracle OCI、中国厂商融资轮次）做二次核验。*
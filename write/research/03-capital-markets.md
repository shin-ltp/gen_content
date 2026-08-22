# 第三章研究素材：资本市场分析

> 研究时间窗：2025 全年至 2026 年中（截至 2026-08）。
> 方法论：以 web 搜索为主工具，关键数据尽量 2+ 独立来源交叉印证，标注置信度（高/中/低）与来源。
>
> **透明度声明（务必先读）**：本次研究在 web 搜索工具的"单回合配额"内只完成约 2 组关键查询（企业采用率、OpenAI/Copilot 营收），其余章节基于研究员知识库撰写，并明确标注 `[知识库]` 与置信度。凡标 `[Web验证]` 者为本轮搜索直接获得、附原始 URL；标 `[知识库]` 者为既有可靠来源但未在本轮重新联网核验，**落地定稿前建议复核最新 10-Q / 官方报告**。所有金额均为区间或近似值（USD）。

## 3.1 需求真实性与早期特征

### 3.1.1 需求真实性证据

**采用率（置信度：高，[Web验证]）**
- McKinsey《State of AI 2025》：**88%** 受访企业已在至少一个业务功能中常规使用 AI；但仅约 **1/3** 进入企业级规模化。
  来源：https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai （2025）
- McKinsey 2026 运营调研：约 **90%** 企业至少在试验 AI，但仅 **7%** 实现全企业规模化。
  来源：https://www.mckinsey.com/capabilities/operations/our-insights/putting-ai-to-work-the-operational-excellence-imperative （2026）
- Gartner：**42%** CIO 预期 12 个月内部署 AI Agent；预测 2026 底约 **30%** 企业使用智能自动化；同时预测 **60%** AI 项目将因"数据未就绪"而被放弃。
  来源：https://www.gartner.com/en/documents/6877266 （2025-2026）

**营收（置信度：高-中，[Web验证] + [知识库]）**
- OpenAI ARR：**2025-06 ~$10B**（CNBC，https://www.cnbc.com/2025/06/09/openai-hits-10-billion-in-annualized-revenue-fueled-by-chatgpt-growth.html ）；**2025 年底 ~$20B+**，Altman 同时披露约 **$1.4T 数据中心承诺**（TechCrunch，https://techcrunch.com/2025/11/06/sam-altman-says-openai-has-20b-arr-and-about-1-4-trillion-in-data-center-commitments/ ，2025-11-06）。`[Web验证, 高]`
- ChatGPT Enterprise：2024-09 约 **$300M ARR**（The Information）；2025 单独 ARR 未披露。`[知识库, 中]`
- Microsoft 365 Copilot：FY2025 商业+消费合计 **1 亿+ MAU**，营收未单独披露；M365 商业总收入 FY2025 **$87.8B**（MSFT 10-K，sec.gov）。`[Web验证, 高]`
- GitHub Copilot：ARR **>$100M**（The Information）。`[Web验证, 中]`
- Anthropic ARR：**~$1B（2024 末）→ 2025 年中多家报道 ~$4B**。`[知识库, 中-低，需复核]`
- 行业层面：GenAI 软件市场，IDC/Gartner 2025 预测达 **数百亿美元**量级并快速增长。`[知识库, 中]`

**企业预算（置信度：中，[知识库]）**
- 多份 CIO 调研（Gartner CIO Agenda、Deloitte Tech Trends、Morgan Stanley CIO Survey）显示 2025-2026 企业 AI 预算占 IT 预算比例上升；部分为其他类别"再分配"而非净新增。中位数等精确数字建议复核原文。

### 3.1.2 "早期阶段"特征信号

**盈利模式尚未跑通（高）**
- OpenAI 2024 年据报道亏损约 **$5B**（The Information / 路透）；推理毛利率为负或薄；多数模型公司未盈利。`[知识库, 中-高]`
- 价格战压低毛利：2025 年中 Google Gemini Flash、OpenAI GPT-4o mini 等大幅降价。

**推理成本仍高但快速下降（中-高）**
- Token 价格自 2023 年 GPT-4 上市以来下降约 **80-90%+**（输入价 GPT-4 $36/M → 2025 年便宜模型数美元/M 量级）。`[知识库, 中]`
- 但前沿推理（o1/o3 类长思维链、Agent 多步调用）单任务算力成本仍高，呈现"token 便宜但用量爆炸"。

**杀手级应用仍在形成（中）**
- 最接近杀手级：编程助手（GitHub Copilot、Cursor）、消费级 ChatGPT、客服自动化。
- 企业级杀手应用尚无共识；Copilot 生产率收益研究分歧（部分显示双位数 % 提升，部分显示有限）。`[知识库, 中]`
- Agent（2025 热点）仍处早期，规模化案例少。

**采纳"最后一公里"墙（高，[Web验证]）**
- 88% 试验 vs 7% 全企业规模化的鸿沟，凸显组织变革、数据治理、人才、信任与合规的阻力。

## 3.2 算力供需失衡研判（2025-2028）

### 3.2.1 需求侧

**训练算力（中-高，[知识库]）**
- Epoch AI：前沿模型训练算力约每 **~6 个月** 翻倍（2010-2024 趋势）；2024-2025 单个前沿模型训练已达 **10^26 FLOPs** 量级（GPT-4 类约 10^25-26）。来源：https://epoch.ai/ 。`[高，方向]`
- 训练需求持续上行：多模态、长上下文、合成数据放大算力。

**推理算力占比上升（中，[知识库]）**
- 共识：随应用部署，推理算力占比从早期 <30% 升至 2025-2026 **>50%** 并继续上行。各投行与 HBM 厂以此论证需求可持续。具体数字分歧大，建议复核 SemiAnalysis（Dylan Patel）报告。来源：https://www.semianalysis.com/

**机构需求预测（中，[知识库]）**
- SemiAnalysis、Epoch AI、Goldman Sachs、Morgan Stanley 对 2025-2028 AI 加速器需求预测区间差异大（年需求从数百万到上千万 H100 当量）。
- 方向一致：高速增长；分歧在斜率与峰值时间。

### 3.2.2 供给侧

**Nvidia GPU 路线图（高，[知识库]）**
- Hopper（H100/H200）：2024 主力、2025 仍主力之一；累计出货数百万级。
- Blackwell（B100/B200/GB200 NVL72）：2024 末发布、2025 大规模放量；GB200 机架级系统。
- Rubin（GPU + CPU Vera）：2025 宣布，预计 2026 量产，下一代。
- Nvidia 数据中心收入：FY2025（截至 2025-01）约 **$115B**，FY2026 显著更高。来源：https://investor.nvidia.com/ 。`[高，方向；具体额复核 10-K]`

**台积电 CoWoS（高）**
- CoWoS（含 Blackwell 用 CoWoS-L）为 2024-2025 关键瓶颈；产能 2024→2025 大幅扩产（约翻倍），2026 续扩。`[中-高]`
- CoWoS 仍是 H100/H200/Blackwell 出货上限的主要约束之一。

**先进 HBM（高）**
- SK Hynix、Micron、Samsung 供应 HBM3/HBM3e；2024-2025 产能被预订一空；HBM 占内存厂利润大头。`[高]`
- 每颗 Blackwell 搭载多层 HBM3e，HBM 产能与 CoWoS 同为瓶颈。

**自研加速器（中-高，[知识库]）**
- Google TPU：Trillium（v6，2024 量产）、后续 Ironwood（2025）；自用 + GCP。
- AWS Trainium2（2024-2025），Anthropic "Project Rainier" 超大集群。
- Meta MTIA v2；Microsoft Maia 100；中国华为昇腾 910B/910C（出口管制下国产替代）。
- 自研芯片缓解对 Nvidia 依赖，但短期内 Nvidia 仍占主导。

### 3.2.3 电力瓶颈（本轮重点）

**数据中心耗电预测（高-中，[知识库]）**
- IEA《Electricity 2024 / Energy and AI》：全球数据中心用电 2022 约 **460 TWh**，基准情景 2026 可能 **~1000 TWh**（约翻倍）。来源：https://www.iea.org/ 。`[高]`
- LBNL《2024 United States Data Center Energy Usage Report》：美国数据中心 2023 约 **176 TWh（约占全美用电 4.4%）**；2028 情景 **~325-580 TWh（6.7%-12%）**。来源：https://eta.lbl.gov/ 。`[高]`
- 电网互联排队：美国并网队列长达数年，数千 GW 在队（LBNL 数据）。`[中-高]`

**核电/SMR 合作（高，[知识库]）**
- Microsoft-Constellation：2024-09，20 年协议重启三里岛 1 号机组（**835 MW**），约 **$1.6B**。
- AWS-Talen Energy：Susquehanna 核电为数据中心直供电；经 FERC 争议后调整。
- Meta：2024 核电招标失败后 2025 签新 PPA。
- Google-Kairos Power：2024-10 SMR 采购协议（2030 起）。
- Amazon（X-energy）：投资 SMR；Oracle、Blue Owl、Crusoe 等亦布局。
- 共识：核电重启/SMR 对 2030+ 供电关键，但 2025-2028 短期贡献有限（建设周期长）。

**燃气轮机（高，[知识库]）**
- GE Vernova：燃气轮机订单创纪录，**~2028 前基本售罄**；订单簿达数十 GW。
- Siemens Energy：燃机订单同样创纪录。
- 燃气轮机成为 2025-2028 数据中心供电的"过渡主力"。

### 3.2.4 供需缺口方向性判断（2025-2028）

- **2025-2026（紧平衡/局部短缺，高）**：电力、CoWoS、HBM 为硬约束；GPU 本身产能爬坡中；推理需求上行 -> 偏紧。Nadella、Zuckerberg 等公开称电力为头号瓶颈。
- **2027-2028（分歧，中）**：
  - "短缺派"（SemiAnalysis / 部分投行 / 超算厂）：推理需求爆炸 + 电力延迟 -> 持续偏紧。
  - "过剩派"（基于 Sequoia 营收缺口逻辑 + 部分分析师）：若应用营收证伪，capex 投产将导致 2027+ 供过于求。
- **方向性结论**：短期由"电力/CoWoS 物理瓶颈"主导偏紧；中期风险由"营收能否兑现"决定 —— 这是本报告核心分歧点。

## 3.3 资金持续性与断链风险

### 3.3.1 四大云厂商 capex（中，[知识库] — 需以最新 10-Q 复核）

2025 年（指南/实际，单位 USD）：

| 公司 | 2024 capex | 2025 指南/实际 | 备注 |
|---|---|---|---|
| Amazon | ~$83B | ~$100B+ | AWS 多次上调 |
| Alphabet/Google | ~$52B | ~$75B | Pichai 公开 |
| Meta | ~$39B | ~$60-72B（多次上调） | 一年内上调数次 |
| Microsoft（7 月财年） | FY2024 ~$44B | FY2025 ~$75-80B；FY2026 更高 | 季度披露 |

- **四大合计 2025 ≈ $320-370B**（同比约 +40-50%）。`[中]`
- **2026**：各公司继续上调，合计有望 **~$450-500B+**（含 Oracle 等"第二梯队"更多）。`[低-中，待官方]`
- 累计：2024-2026 三年全球 AI capex 累计有望达 **~$1T+**（含四大云 + Oracle + 主权/国家 + 初创）。`[中]`

### 3.3.2 累计 capex 与 Sequoia "$600B 问题"

- Sequoia（David Cahn）：
  - 2023-09《The $200B Question》
  - 2024-06《The $600B Question》：要"填满"已部署 GPU 算力，AI 行业需 **$600B 营收**。来源：https://www.sequoiacap.com/article/llms-the-600-billion-question/ （2024-06）。`[高]`
- 逻辑：capex 远超应用层营收 -> 巨大回收缺口。随 2025 capex 升至 ~$300-400B/年，"所需营收"被推高至 **$1T+** 区间。`[中]`
- 营收侧现实：OpenAI ~$20B ARR + Anthropic ~$4B + 其他 -> 行业应用层营收量级 **~$50-100B**，与年 capex **$300-400B** 形成 **3-5x 缺口**，回收期多年。`[中-高]`

### 3.3.3 融资环境（中，[知识库]）

- 利率：美联储 2024 年 9/11/12 月累计降息约 100bps，2025 续降后于 2025-2026 维持中性偏高（非零利率），但资金仍大量涌入 AI。`[中]`
- 私募市场：2024-2025 AI VC 融资创纪录。
  - OpenAI：2024-10 估值 **$157B**；2025 进一步融资传闻更高。
  - xAI：**$50B+**；Anthropic **$60B+**；Mistral、Perplexity 等数十亿级。`[中]`
- IPO 窗口：2025 偏紧，AI 独角兽多留私募；CoreWeave 等基建型公司受关注；2026 窗口预期改善但不确定。`[低-中]`

### 3.3.4 资金断链潜在触发点（中-高）

1. **营收证伪**：若杀手级应用迟迟不现、企业 ROI 不及预期 -> capex 削减（最先砍长尾项目）。
2. **DeepSeek 时刻类冲击**：2025-01-27 DeepSeek-V3/R1 以极低训练成本冲击市场，Nvidia 单日市值蒸发约 **$600B**（史上最大单日跌幅之一）。显示"成本曲线下行 + 开源冲击"可瞬间重估 capex 合理性。`[高]`
3. **利率上升 / 资本成本回升**：高 capex + 高杠杆（CoreWeave 等靠债务融资）对利率敏感。
4. **电力/许可延迟**：capex 已投但 IDC 无法通电 -> 资产搁浅、回报延后。
5. **模型商品化**：开源（Llama、DeepSeek、Qwen）压低模型层价格 -> 价格战 -> 毛利崩塌，弱者出局。

## 3.4 错配规模量化

| 错配维度 | 量化（区间，置信度中） | 解读 |
|---|---|---|
| **算力错配** | 2025-2026 偏紧（电力/CoWoS/HBM 瓶颈）；2027-2028 可能过剩（若营收证伪） | 时间错配：短期物理短缺 vs 中期潜在过剩 |
| **资金错配（投入 vs 回收）** | 年 capex ~$300-400B vs 应用层年营收 ~$50-100B -> **3-5x 缺口**，回收期多年 | Sequoia $600B -> $1T+ 逻辑 |
| **估值错配** | 基建/模型层（Nvidia 市值 ~$3-4T、超大规模云厂高估值）vs 应用层营收稀薄 | "卖铲人" vs "淘金者"价值倒挂 |

- 累计维度：2024-2026 三年全球 AI capex 累计有望达 **~$1T+**（含四大云 + Oracle + 主权/国家 + 初创）。`[中]`

## 3.5 终极原因：三层速度差

核心论点：**资本投入速度 > 技术发展速度 > 人类社会采纳速度**

**1. 资本投入速度（最快）**
- 四大云 capex 同比约 +40-50%/年，三年累计逼近 $1T；叠加主权基金、私募、债务融资。
- 资本能瞬间调动（融资轮、capex 指南），远快于物理建设。

**2. 技术发展速度（居中）**
- 模型能力快速提升，但**物理基础设施（电力、芯片、CoWoS、HBM）建设周期以年计**，跟不上资本部署节奏。
- 模型本身也存在能力 plateau 风险与"幻觉/可靠性"瓶颈。

**3. 社会采纳速度（最慢，[Web验证 + 知识库]）**
- 88% 试验 vs 7% 全企业规模化（McKinsey 2026）= 采纳"最后一公里"墙。`[Web验证, 高]`
- 组织变革、数据治理、流程重构、人才、监管、信任与安全顾虑构成摩擦。
- 企业 AI ROI 研究分歧：部分显示双位数生产率提升，部分显示有限或难以货币化。`[知识库, 中]`

**支持与反驳**
- 支持：McKinsey 采纳鸿沟、ROI 不确定性、DeepSeek 成本冲击、组织变革阻力。
- 反驳：消费级采纳极快（ChatGPT 数亿用户）；编程、客服等场景已规模化；若 Agent 成熟，采纳曲线可能加速。
- 结论：三层速度差是当前"需求真实但早期 + 多维错配"的根因；断链风险主要来自最快层（资本）与最慢层（采纳）之间的剪刀差。

## 来源清单（按小节归类）

### 3.1 需求真实性与早期特征
- McKinsey《State of AI 2025》：https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-state-of-ai （2025）
- McKinsey《Putting AI to work》（2026 运营调研）：https://www.mckinsey.com/capabilities/operations/our-insights/putting-ai-to-work-the-operational-excellence-imperative （2026）
- Gartner Benchmark Enterprise Deployment Plans：https://www.gartner.com/en/documents/6877266 （2025-2026）
- CNBC — OpenAI $10B ARR：https://www.cnbc.com/2025/06/09/openai-hits-10-billion-in-annualized-revenue-fueled-by-chatgpt-growth.html （2025-06-09）
- TechCrunch — OpenAI $20B ARR / $1.4T commitments：https://techcrunch.com/2025/11/06/sam-altman-says-openai-has-20b-arr-and-about-1-4-trillion-in-data-center-commitments/ （2025-11-06）
- The Information — OpenAI / GitHub Copilot ARR（2024-2025）
- Microsoft FY2025 10-K / Q4 财报：https://www.sec.gov/Archives/edgar/data/789019/000095017025100235/msft-20250630.htm ；https://www.microsoft.com/en-us/investor/events/fy-2025/earnings-fy-2025-q4

### 3.2 算力供需
- IEA《Electricity 2024》/《Energy and AI》：https://www.iea.org/
- LBNL《2024 US Data Center Energy Usage Report》：https://eta.lbl.gov/
- Epoch AI：https://epoch.ai/
- SemiAnalysis：https://www.semianalysis.com/
- Nvidia 投资者关系 / 10-K：https://investor.nvidia.com/
- TSMC CoWoS 法说会；HBM 三厂（SK Hynix/Micron/Samsung）
- GE Vernova / Siemens Energy 投资者材料
- Microsoft-Constellation 三里岛（2024-09）；AWS-Talen；Google-Kairos（2024-10）

### 3.3 资金持续性
- Sequoia（David Cahn）《The $600B Question》：https://www.sequoiacap.com/article/llms-the-600-billion-question/ （2024-06）
- Amazon / Alphabet / Meta / Microsoft 各季度财报与 capex 指南（SEC EDGAR）
- DeepSeek 冲击（2025-01-27，Nvidia 单日约 $600B 市值下跌）

### 3.4 错配量化
- 综合 Sequoia、四大云 capex、OpenAI/Anthropic ARR（详见各小节）

### 3.5 终极原因
- McKinsey 2025/2026 采纳数据（见 3.1）
- 企业 AI ROI 研究（BCG、Microsoft WorkLab 等，[知识库]，定稿前建议精确引用）

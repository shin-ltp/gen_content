# -*- coding: utf-8 -*-
import sys, os
import numpy as np
sys.path.insert(0, r"D:\work\gen_content\write")
from chart_theme import *

# 1. 编程类 AI 产品 ARR 增长
fig, ax = plt.subplots(figsize=(9.2, 4.8))
times = ["2024 末", "2025 年中", "2025 末"]
cursor = [200, 500, 1000]
claude = [0, 400, 1000]
x = np.arange(len(times))
ax.plot(x, cursor, color=ACCENT, lw=2.8, marker="o", ms=7, label="Cursor (Anysphere)", zorder=3)
ax.plot(x, claude, color=WARM, lw=2.8, marker="s", ms=7, label="Claude Code (Anthropic)", zorder=3)
for xi, v in zip(x, cursor):
    ax.annotate("${}M".format(v), (xi, v), textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9, color=INK, fontweight="bold")
for xi, v in zip(x, claude):
    ax.annotate("${}M".format(v) if v else "未发布", (xi, v), textcoords="offset points", xytext=(0, -16), ha="center", fontsize=9, color=INK, fontweight="bold")
ax.set_xticks(x); ax.set_xticklabels(times)
ax.set_ylim(-100, 1220); ax.set_ylabel("年化收入 ARR（百万美元）")
ax.set_title("图1　编程类 AI 产品 ARR 增长：一年内冲过 $10 亿")
ax.legend(loc="upper left")
_annotate_source(ax, "Anysphere/TechCrunch、Anthropic/WIRED（2024–2025）；估值：Cursor 2025.11 约 $293 亿")
save(fig, "chart-coding-arr.png")

# 2. 企业 AI 渗透
fig, ax = plt.subplots(figsize=(9.0, 4.6))
labels = ["至少试验 AI\n（McKinsey 2026）", "至少一个职能\n常规使用（2025）", "部署 AI Agent\n（Gartner 12 个月）", "全企业规模化\n（McKinsey 2026）"]
vals = [90, 88, 42, 7]
cols = [ACCENT, ACCENT, ACCENT2, WARN]
ax.bar(np.arange(len(labels)), vals, color=cols, width=0.6, zorder=3)
ax.set_xticks(np.arange(len(labels))); ax.set_xticklabels(labels, fontsize=9)
ax.set_ylim(0, 108); ax.set_ylabel("企业占比 (%)")
ax.set_title("图2　企业 AI 渗透：88% 在用，仅 7% 规模化")
for i, v in enumerate(vals):
    ax.text(i, v+2, "{}%".format(v), ha="center", fontsize=12, color=INK, fontweight="bold")
ax.annotate("", xy=(3, 12), xytext=(0, 92), arrowprops=dict(arrowstyle="->", color=WARN, lw=1.6, connectionstyle="arc3,rad=-0.25"))
ax.text(1.5, 70, "采纳\"最后一公里墙\"", ha="center", color=WARN, fontsize=10, fontweight="bold")
_annotate_source(ax, "McKinsey《State of AI 2025》《Putting AI to Work 2026》；Gartner CIO Survey 2025")
save(fig, "chart-adoption-gap.png")

# 3. 全球 AI 软件市场预测（Gartner）
fig = bar_v(["2025", "2026", "2028"],
            [[297.9, 397.2, 744.0], [62.9, 85.2, 147.0]],
            "图3　全球 AI 软件市场预测（Gartner，十亿美元）",
            "Gartner《Forecast: AI Software, Worldwide》2025-06；2028 GenAI 为推算",
            series_labels=["AI 软件总支出", "其中生成式 AI 软件"])
save(fig, "chart-ai-market.png")

# 4. 前沿模型公司 ARR 对比
fig = bar_h(["xAI (2025)", "Anthropic\n(2025 末)", "OpenAI\n(2025 末)"],
            [40, 90, 200],
            "图4　前沿模型公司 ARR 对比（2025，十亿美元）",
            "Bloomberg/The Information、Anthropic/Reuters、OpenAI CFO(Friar)/FT（2025–2026.01）",
            colors=[ACCENT2, WARM, ACCENT],
            fmt="{:,.0f}", suffix=" 亿$")
save(fig, "chart-model-arr.png")

# 5. 四大云 + 专用 AI 云 capex
fig, ax = plt.subplots(figsize=(9.6, 5.0))
groups = ["Microsoft", "Alphabet", "Amazon", "Meta", "CoreWeave"]
v2025 = [118, 91.4, 128.3, 72.2, None]
v2026 = [190, 185, 200, 137.5, 33.0]
xs = np.arange(len(groups)); w = 0.38
b1 = [v if v is not None else 0 for v in v2025]
ax.bar(xs - w/2, b1, width=w, color=SEQ[3], label="2025（实际/估）", zorder=3)
ax.bar(xs + w/2, v2026, width=w, color=SEQ[0], label="2026（指引）", zorder=3)
for i, v in enumerate(v2025):
    if v is not None:
        ax.text(xs[i]-w/2, v+3, "{}".format(v), ha="center", fontsize=8.5, color=INK, fontweight="bold")
    else:
        ax.text(xs[i]-w/2, 3, "n/a", ha="center", fontsize=8.5, color=MUTED)
for i, v in enumerate(v2026):
    ax.text(xs[i]+w/2, v+3, "{}".format(v), ha="center", fontsize=8.5, color=INK, fontweight="bold")
ax.set_xticks(xs); ax.set_xticklabels(groups)
ax.set_ylim(0, 228); ax.set_ylabel("资本开支 capex（十亿美元，自然年）")
ax.set_title("图5　四大云 + 专用 AI 云 capex：2025 vs 2026 指引")
ax.legend(loc="upper right")
_annotate_source(ax, "公司财报/投资者关系；Microsoft FY25→自然年口径换算；CoreWeave 2026 指引；Platformonomics CAPEX Scoreboard（含融资租赁）")
save(fig, "chart-capex.png")

# 6. 全球数据中心电力需求（统一数值坐标）
fig, ax = plt.subplots(figsize=(9.0, 4.8))
yr_idx = [0, 1, 2]
yr_lab = ["2023", "2025", "2030"]
global_v = [415, 485, 945]
us_mid = [None, 176, 452]
ax.plot(yr_idx, global_v, color=ACCENT, lw=2.8, marker="o", ms=7, label="全球数据中心（IEA）", zorder=3)
ax.plot([1, 2], [176, 452], color=WARM, lw=2.4, marker="s", ms=6, ls="--", label="美国数据中心中位（LBNL）", zorder=3)
ax.fill_between([1, 2], [176, 325], [176, 580], color=WARM, alpha=0.20, label="美国区间（LBNL 2028：325–580）")
for xi, v in zip(yr_idx, global_v):
    ax.annotate("{} TWh".format(v), (xi, v), textcoords="offset points", xytext=(0, 10), ha="center", fontsize=9.5, color=INK, fontweight="bold")
ax.annotate("", xy=(2, 980), xytext=(1, 500), arrowprops=dict(arrowstyle="->", color=WARN, lw=1.8))
ax.text(1.5, 760, "约翻倍", ha="center", fontsize=12, color=WARN, fontweight="bold")
ax.set_xticks(yr_idx); ax.set_xticklabels(yr_lab)
ax.set_ylim(0, 1080); ax.set_ylabel("年用电量（TWh）")
ax.set_title("图6　数据中心电力需求：瓶颈不在芯片，在电力")
ax.legend(loc="upper left")
_annotate_source(ax, "IEA《Energy and AI》2025–2026；LBNL《2024 United States Data Center Energy Usage Report》")
save(fig, "chart-power.png")

# 7. AI 基建投入 vs 应用层营收（缺口）
fig, ax = plt.subplots(figsize=(9.2, 5.0))
cats = ["应用层\n年化营收", "四大云\ncapex", "全行业 AI\n基建 capex"]
vals = [100, 700, 800]
cols = [GOOD, ACCENT, WARN]
ax.bar(np.arange(3), vals, color=cols, width=0.55, zorder=3)
ax.set_xticks(np.arange(3)); ax.set_xticklabels(cats, fontsize=10)
ax.set_ylim(0, 960); ax.set_ylabel("2026 年规模（十亿美元）")
for i, v in enumerate(vals):
    ax.text(i, v+12, "${}B".format(v), ha="center", fontsize=13, color=INK, fontweight="bold")
ax.annotate("", xy=(2, 855), xytext=(0, 130), arrowprops=dict(arrowstyle="<->", color=WARN, lw=1.8))
ax.text(1, 560, "缺口\n6–10x", ha="center", color=WARN, fontsize=14, fontweight="bold",
        bbox=dict(boxstyle="round,pad=0.4", fc="#FFF4F4", ec=WARN))
ax.set_title("图7　2026 年 AI 基建投入 vs 应用层营收：缺口 6–10 倍")
_annotate_source(ax, "公司财报/OpenAI/Anthropic ARR；Sequoia \"$600B Question\" 升级为 \"$700–800B Question\"（2026）")
save(fig, "chart-funding-gap.png")

print("ALL 7 charts generated OK")
import glob
for p in sorted(glob.glob(os.path.join(ASSETS, "*.png"))):
    print("  ", os.path.basename(p), "{} KB".format(os.path.getsize(p)//1024))
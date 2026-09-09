# -*- coding: utf-8 -*-
"""AI 行业报告 - 统一风格图表工具模块。
所有数据图共享同一调色板、字体、网格风格，保证 HTML 报告视觉统一。"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import os

# ---- 中文字体 ----
for f in ["Microsoft YaHei", "Noto Sans SC", "SimHei"]:
    try:
        font_manager.findfont(f, fallback_to_default=False)
        plt.rcParams["font.family"] = f
        break
    except Exception:
        continue
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["text.parse_math"] = False

# ---- 统一调色板（深色底 + 高对比强调色）----
INK     = "#0F1B2D"   # 主文字 / 深背景
INK2    = "#1E2B40"
PAPER   = "#FFFFFF"
GRID    = "#E3E8EF"
MUTED   = "#6B7785"
ACCENT  = "#2E6BE6"   # 主蓝
ACCENT2 = "#00A3A3"   # 青
WARM    = "#E8833A"   # 橙
WARN    = "#D7263D"   # 红（风险/错配）
GOOD    = "#2BAE66"   # 绿
PURPLE  = "#7C5CFF"
SEQ = [ACCENT, ACCENT2, WARM, PURPLE, GOOD, WARN, "#B983FF", "#FFB703"]

plt.rcParams.update({
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "axes.edgecolor": GRID,
    "axes.labelcolor": INK,
    "axes.titlecolor": INK,
    "axes.titleweight": "bold",
    "axes.titlesize": 15,
    "axes.titlepad": 14,
    "axes.labelsize": 11,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "axes.grid": True,
    "grid.color": GRID,
    "grid.linewidth": 0.8,
    "grid.alpha": 0.7,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "legend.frameon": False,
    "legend.fontsize": 10,
    "savefig.dpi": 150,
    "savefig.bbox": "tight",
    "savefig.facecolor": PAPER,
})

ASSETS = r"D:\work\gen_content\write\report\assets"
os.makedirs(ASSETS, exist_ok=True)

def _annotate_source(ax, text, y=-0.18):
    ax.figure.text(0.012, y, text, fontsize=7.5, color=MUTED, ha="left", va="top")

def save(fig, name):
    path = os.path.join(ASSETS, name)
    fig.savefig(path)
    plt.close(fig)
    return path

def bar_h(labels, values, title, source, colors=None, fmt="{:,.0f}", suffix=""):
    fig, ax = plt.subplots(figsize=(8.6, max(3.0, 0.55*len(labels)+1.2)))
    y = np.arange(len(labels))[::-1]
    cols = colors or [ACCENT]*len(labels)
    bars = ax.barh(y, values, color=cols, height=0.62, zorder=3)
    ax.set_yticks(y); ax.set_yticklabels(labels)
    ax.set_title(title)
    vmax = max(values) if values else 1
    ax.set_xlim(0, vmax*1.18)
    for yi, v in zip(y, values):
        ax.text(v + vmax*0.015, yi, fmt.format(v)+suffix, va="center", fontsize=9.5, color=INK, fontweight="bold")
    ax.set_axisbelow(True)
    _annotate_source(ax, "来源：" + source)
    return fig

def bar_v(labels, series, title, source, series_labels=None, fmt="{:,.0f}", suffix=""):
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    x = np.arange(len(labels)); n = len(series); w = 0.78/n
    for i, s in enumerate(series):
        off = (i - (n-1)/2)*w
        ax.bar(x+off, s, width=w, color=SEQ[i % len(SEQ)], label=(series_labels[i] if series_labels else None), zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_title(title)
    ax.legend(loc="upper left", bbox_to_anchor=(0.0, 1.0))
    flat = [v for s in series for v in s]
    vmax = max(flat) if flat else 1
    ax.set_ylim(0, vmax*1.2)
    _annotate_source(ax, "来源：" + source)
    return fig

def line(x, series, title, source, series_labels=None, fmt_y="{:,.0f}", markers=True, area=False):
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    for i, s in enumerate(series):
        c = SEQ[i % len(SEQ)]
        ax.plot(x, s, color=c, linewidth=2.6, marker=("o" if markers else None), markersize=5,
                label=(series_labels[i] if series_labels else None), zorder=3)
        if area:
            ax.fill_between(x, s, color=c, alpha=0.10)
    ax.set_title(title)
    ax.legend(loc="best")
    _annotate_source(ax, "来源：" + source)
    return fig

def waterfall(categories, values, labels, title, source):
    """values: 浮点；最后若干项为合计柱（用 None 占位由 labels 指定）。"""
    fig, ax = plt.subplots(figsize=(9.0, 4.8))
    cumulative = 0; bases = []; heights = []; cols = []
    for i, v in enumerate(values):
        if v is None:
            bases.append(0); heights.append(cumulative); cols.append(INK)
        else:
            if v >= 0:
                bases.append(cumulative); heights.append(v); cols.append(GOOD)
            else:
                bases.append(cumulative+v); heights.append(-v); cols.append(WARM)
            cumulative += v
    x = np.arange(len(categories))
    ax.bar(x, heights, bottom=bases, color=cols, width=0.6, zorder=3)
    for xi, b, h in zip(x, bases, heights):
        ax.text(xi, b+h+ (max(cumulative,1)*0.015), labels[list(values).index(values[xi])] if values[xi] is not None else f"{cumulative:,.0f}",
                ha="center", fontsize=9, color=INK, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(categories)
    ax.set_title(title)
    _annotate_source(ax, "来源：" + source)
    return fig

if __name__ == "__main__":
    print("chart theme module OK; assets dir:", ASSETS)
__all__ = [n for n in dir() if not n.startswith('__')]
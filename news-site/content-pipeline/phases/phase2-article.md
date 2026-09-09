# Phase 2 — 深度文章生成（article）

## 目的

把 draft-B*.md（YouTube 口播稿，7〜12 分钟/篇）改写成书面日语深度文章，2500〜4000 字。

## 改写原则

1. **口语→书面**: 去掉「ですよね」「〜というわけです」等口播语气，改为である調分析文体。
2. **结构化**: 原稿线性叙事改为 H2 小节（背景→数据→分析→投資戦略），每节 400〜800 字。
3. **图表引用**: draft 里「（図表1）」等占位保留，文章发布时换成 Ghost 图片或省略。
4. **引用完整**: 所有数据出处（URL、机构名）原样保留；改写时不得删来源。
5. **付费墙切分点**: 在「投資戦略」小节前切成免费部分（背景+数据），付费部分（分析+投資戦略）。

## 文章 frontmatter

```yaml
---
title: （文章标题）
slug: us-stock-YYYYMMDD-<topic-slug>
date: YYYY-MM-DD
tags: [米国株, <主题>, Smart Assets]
access: paid        # paid | members | public
excerpt: （120 字以内摘要，列表页用）
---
```

## 模板

[../templates/article-template.md](../templates/article-template.md)
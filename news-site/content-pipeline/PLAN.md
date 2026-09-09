# content-pipeline — 二次加工管线设计

## 目标

复用 `us-stock-daily` 每日管线的中间产物（collection、outline、draft-*、episode），在不增加大量新采集的前提下，产出两种发布物：

| 发布物 | 用途 | 更新频率 |
|-------|------|---------|
| **每日简报 brief** | 免费引流内容，轻量、快读 | 每日 1 篇 |
| **深度文章 article** | 部分付费（members only），从 draft-B* 系列改写 | 每日 1〜3 篇 |

## 输入 / 输出

```
输入: us-stock-daily/daily-output/YYYY-MM-DD/
  ├── collection/*.md         原始素材（已含 url/body）
  ├── production/outline.md   选题与结构
  ├── production/draft-B*.md  深度分析草稿（文章化主素材）
  ├── production/draft-A.md   市况总结（简报素材）
  └── production/draft-C.md   News 列表（简报链接区素材）

输出: news-site/content-pipeline/output/YYYY-MM-DD/
  ├── brief-YYYY-MM-DD.md         简报（日语，待发布）
  ├── article-YYYY-MM-DD-<slug>.md 深度文章（日语，待发布）
  └── publish-log.json             发布状态记录
```

## Phase 模型

| Phase | 名称 | 输入 | 输出 | 规格 |
|-------|------|------|------|------|
| 0 | 素材盘点 | daily-output 当日目录 | inventory.json | [phases/phase0-inventory.md](phases/phase0-inventory.md) |
| 1 | 简报生成 | inventory + draft-A + draft-C | brief-*.md | [phases/phase1-brief.md](phases/phase1-brief.md) |
| 2 | 文章生成 | inventory + draft-B* | article-*.md | [phases/phase2-article.md](phases/phase2-article.md) |
| 3 | 发布 | 确认后的 md | Ghost Admin API | [phases/phase3-publish.md](phases/phase3-publish.md) |

Phase 0→1→2 可当日串联；Phase 3 人工确认后执行（先半自动，跑稳后再考虑自动化）。

## 质量原则

- 简报 800〜1200 字（日语），5 分钟读完；文章 2500〜4000 字。
- 所有数字、事实必须有出处（draft 中已带引用，改写时不得删引用）。
- 付费文章在免费部分末尾加「続きはメンバーシップで」引导，用 Ghost 的 members-only 分段实现。
- 日语行文规范沿用 `us-stock-daily/spec/content-framework.md` 与 `templates/daily-template.md` 的语体。
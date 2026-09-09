# news-site — Smart Assets 资讯网站

与 `us-stock-daily`（YouTube 节目管线）联动的资讯网站项目。

## 架构

| 层 | 技术 | 部署位置 |
|---|------|---------|
| CMS / 会员系统 | Ghost（自托管，headless 模式） | VPS |
| 前端 | Astro（静态生成） | Cloudflare Pages |
| 内容管线 | Node.js 脚本（复用 YouTube 管线中间产物） | 本地 |

```
us-stock-daily/daily-output/YYYY-MM-DD/   ← YouTube 管线产物（drafts / outline / episode）
        │
        ▼
news-site/content-pipeline/               ← 二次加工管线
        │  brief（每日简报）＋ article（深度文章）
        ▼
Ghost Admin API  ──▶  VPS 上的 Ghost
        │
        ▼
Astro 构建时通过 Ghost Content API 拉取文章  ──▶  Cloudflare Pages 发布
```

## 目录结构

```
news-site/
├── README.md                  本文件
├── docs/
│   ├── ghost-setup.md         Ghost VPS 部署手顺
│   └── astro-setup.md         Astro 本地开发 + Cloudflare Pages 部署手顺
├── content-pipeline/          二次加工管线
│   ├── PLAN.md                管线设计文档
│   ├── phases/                Phase 0〜3 详细规格
│   ├── templates/             简报 / 深度文章模板（日语）
│   └── tools/                 发布脚本等
├── astro/                     Astro 前端骨架
└── ghost/                     Ghost VPS 部署配置样例
```

## 着手顺序

1. `content-pipeline/` 先跑通：从 YouTube 管线产物本地生成简报和文章（不依赖 Ghost）。
2. Ghost VPS 部署（`docs/ghost-setup.md`），拿到 Content API Key 和 Admin API Key。
3. Astro 本地连接 Ghost 确认文章能拉取（`docs/astro-setup.md`）。
4. Cloudflare Pages 绑定 GitHub 仓库自动部署。
5. 会员体系：Ghost 原生 Members + Stripe（付费内容分发）。
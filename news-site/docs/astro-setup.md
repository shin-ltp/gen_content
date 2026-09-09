# Astro 开发 + Cloudflare Pages 部署手顺

## 1. 本地安装与启动

```powershell
cd news-site\astro
pnpm install
Copy-Item .env.example .env    # 填入 GHOST_CONTENT_API_URL / GHOST_CONTENT_API_KEY
pnpm dev                       # http://localhost:4321
```

未配置环境变量时，首页会显示占位内容（不报错），方便先跑通前端骨架。

## 2. Ghost 内容拉取

`src/pages/index.astro` 通过 Ghost Content API 拉取最新文章列表。
后续页面规划：

- `/` 最新文章 + 每日简报列表
- `/brief/[slug]` 每日简报详情
- `/article/[slug]` 深度文章详情
- `/membership` 会员引导（指向 Ghost Portal）

页面开发时用 Ghost 的数据结构（`title / html / excerpt / tags / published_at`）。

## 3. Cloudflare Pages 部署

1. 把仓库推到 GitHub。
2. Cloudflare Dashboard → Workers & Pages → Create → Pages → Connect to Git。
3. 构建配置：
   - 构建命令：`pnpm build`
   - 输出目录：`dist`
   - 根目录：`news-site/astro`
4. 环境变量（Production 和 Preview 都配）：
   - `GHOST_CONTENT_API_URL`
   - `GHOST_CONTENT_API_KEY`
5. 部署后绑定自定义域名。

之后每次 push 自动构建发布。

## 4. 验证清单

- [ ] `pnpm dev` 本地能显示 Ghost 文章列表
- [ ] 文章详情页正常渲染（HTML 内容 + 图片）
- [ ] `pnpm build` 无错误
- [ ] Cloudflare Pages 部署成功且自定义域名可访问
- [ ] Ghost Portal 弹窗在 Astro 页面上正常唤起（会员注册/付费流程）
# Phase 3 — Ghost 发布（publish）

## 目的

把确认后的 brief / article md 通过 Ghost Admin API 发布。

## 方式

`tools/publish.mjs`（待实现）:

1. 读取 `output/YYYY-MM-DD/*.md`，解析 frontmatter。
2. Markdown → Ghost 接受的 mobiledoc 或 html（先用 `marked` 转 html，Ghost 原生支持 html 字段）。
3. 调 Admin API `POST /admin/posts/`:
   - `title`, `slug`, `html`, `published_at`, `tags`, `excerpt`
   - `visibility`: `public` | `members` | `paid`
   - 简报固定 `public`；深度文章按 frontmatter `access` 映射。
4. 发布成功后写 `publish-log.json`（slug + ghost url + 时间戳）。

## 认证

Admin API Key 格式 `id:secret`，环境变量 `GHOST_ADMIN_API_KEY` + `GHOST_ADMIN_API_URL`。
JWT 签名用 `@tryghost/admin-api` 库（npm 包已封装）。

## 人工确认步骤

- [ ] 简报里数字与当日 draft-A 一致
- [ ] 文章引用无缺失
- [ ] 付费切分位置合理（免费部分足够引流，付费部分有独立价值）
- [ ] 内链: 文章内至少 1 处指向当日简报或 YouTube
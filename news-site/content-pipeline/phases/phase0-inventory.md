# Phase 0 — 素材盘点（inventory）

## 目的

当日 `us-stock-daily/daily-output/YYYY-MM-DD/` 里有什么可用素材，先清点再开工。

## 输入

- `daily-output/YYYY-MM-DD/production/outline.md`（当日选题）
- `daily-output/YYYY-MM-DD/production/draft-*.md`（各稿）
- `daily-output/YYYY-MM-DD/collection/00-manifest.md`（素材索引）

## 输出

`output/YYYY-MM-DD/inventory.json`：

```json
{
  "date": "YYYY-MM-DD",
  "topics": [
    { "slot": "B1", "title": "...", "draft": "draft-B1.md", "words": 3200, "sources": 8 }
  ],
  "brief_materials": { "draftA": true, "draftC": true, "news_count": 8 },
  "ready": true
}
```

## 规则

- 任一 `draft-B*.md` 缺失时该主题文章跳过，不阻塞简报。
- `draft-A` 或 `draft-C` 缺失时简报仍可生成，但对应板块留空并在 publish-log 里标记。
- `ready` 只有在简报素材至少一项存在时才为 true。
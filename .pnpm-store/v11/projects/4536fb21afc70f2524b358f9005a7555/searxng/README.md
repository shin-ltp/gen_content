# SearXNG 本机部署与调用规范（us-stock-daily 搜索层）

定位：Phase 0 收集的**主力搜索通道**。本机 Docker 运行、仅绑定 127.0.0.1、无外部访问、无认证层。
内置 `web_search` 降为 fallback。行情数字不走搜索（用 longbridge CLI），
EDGAR/FRED 等有官方 API 的直接调 API。

## 启动 / 停止

```powershell
cd us-stock-daily/tools/searxng
docker compose up -d        # 首次会拉取 searxng/searxng 镜像
docker compose down         # 停止
.\search.ps1 -Check         # 健康检查（healthz + 带结果的实际查询）
```

访问地址：`http://127.0.0.1:8888`（Web UI 可直接浏览器打开调试）。

## 配置说明

- [docker-compose.yaml](./docker-compose.yaml)：端口**仅绑 127.0.0.1**（不要改）。
- [searxng/settings.yml](./searxng/settings.yml)：引擎白名单（`keep_only`）聚焦财经收集需求——
  英文网页（google/bing/ddg/brave/mojeek）、英文新闻（google news/bing news/yahoo news/ddg news）、
  日文（yahoo，配合请求级 `language=ja-JP`）。`formats` 含 `json`，`limiter: false`。
- secret_key 已内嵌（本机实例，仅用于 Cookie/CSRF 签名，不是访问凭据）。

## 调用约定（collector-agent 用）

推荐直接用 [search.ps1](./search.ps1)（读取 `../../.env` 的 `SEARXNG_*` 配置；本机无认证时凭据留空即可）：

```powershell
.\search.ps1 "Nvidia AI chip"                                  # 默认 news/day
.\search.ps1 "ISM services PMI" -Categories general,news -TimeRange week
.\search.ps1 "日経平均 最高値" -Language ja-JP
.\search.ps1 "Palantir" -Raw                                   # 原始 JSON
.\search.ps1 "Berkshire Q2" -OutFile results.json              # 保存 UTF-8 JSON
```

原生端点：`http://127.0.0.1:8888/search`，必传 `format=json`。参数：

| 参数 | 取值 | 说明 |
|------|------|------|
| `q` | 关键词 | 支持 `site:` 限定（如 `site:reuters.com`） |
| `categories` | `general` / `news` / `general,news` | 深度文章用 general，速报用 news |
| `time_range` | `day` / `week` / `month` | 当日收集默认 `day`，背景资料放宽 |
| `language` | `en-US` / `ja-JP` | 日文源用 `ja-JP` |
| `pageno` | 1,2,... | 翻页 |

### 与 Phase 0 六类素材的对应查询模式

| 素材类别 | 查询例 | 参数 |
|----------|--------|------|
| MKT（背景解读，数字走 CLI） | `"stock market close" S&P 500 Dow Nasdaq` | `categories=news&time_range=day&language=en-US` |
| MAC | `ISM services PMI July Fed rate odds` | `categories=general,news&time_range=week` |
| RES | `Palantir price target upgrade downgrade` | `categories=news&time_range=day` |
| STK | `Nvidia AI chip demand` | `categories=general,news&time_range=week` |
| ERN | `Berkshire Hathaway Q2 operating earnings cash` | `categories=news&time_range=day` |
| NWS | `Strait of Hormuz Iran talks oil` | `categories=news&time_range=day` |
| 日文源 | `日経平均 最高値 円安` | `categories=news&time_range=day&language=ja-JP` |

### 结果取舍

- JSON 的 `results[]` 含 `title` / `url` / `content` / `publishedDate`（news 类）。
- 素材落盘时 `url` 取 `results[].url`，`content` 作为摘要初稿（仍需在 Phase 1/2 核对原文）。
- 同一事件多引擎重复命中属正常，按 URL 去重（Phase 0 Gate #0 检查项 6）。

## 运维注意

- 一次查询 = 白名单内全部引擎的并行上游请求，按需查询、避免循环轰炸
  （30 件素材/天 ≈ 40-60 次查询，属低强度）。
- 引擎健康度看 `http://127.0.0.1:8888/stats`；持续失败的引擎从 settings.yml 白名单移除。
- 升级镜像（`docker compose pull && docker compose up -d`）后先跑 `search.ps1 -Check`，
  确认 `formats` 里仍有 `json`。
- ⚠ 如需把本实例暴露到局域网/公网，必须先加认证网关并开启 limiter，当前配置不允许直接对外。

## 引擎可用性重测

引擎可用性与**出口 IP** 强相关（数据中心 IP 普遍被上游引擎封锁，家庭 IP 宽松得多）。
更换网络环境、或怀疑结果质量下降时，按以下步骤重测并收敛白名单：

1. 把候选引擎临时加入 `searxng/settings.yml` 的 `keep_only`，`docker compose restart`。
2. 逐引擎实测（`engines=` 参数指定单引擎）：
   ```powershell
   $engines = @("google","google news","bing","bing news","duckduckgo","duckduckgo news","brave","mojeek","qwant","yahoo","yahoo news")
   foreach ($e in $engines) {
       $enc = [uri]::EscapeDataString($e)
       try {
           $r = Invoke-RestMethod "http://127.0.0.1:8888/search?q=stock+market&format=json&engines=$enc" -TimeoutSec 45
           "$e -> results=$(@($r.results).Count)"
       } catch { "$e -> ERR" }
   }
   ```
3. 日文检索验证（对可用引擎追加测试）：
   ```powershell
   Invoke-RestMethod "http://127.0.0.1:8888/search?q=$([uri]::EscapeDataString('日経平均'))&format=json&engines=google&language=ja-JP"
   ```
4. 把 `keep_only` 收敛为有结果的引擎，重启，更新 settings.yml 内的实测记录注释。

实测记录：2026-08-05 GCP IP 仅 bing/bing news 可用；2026-08-06 家庭 IP 重测，
google / bing / bing news / duckduckgo / duckduckgo news 共 5 引擎可用（含 ja-JP），详见 settings.yml 注释。

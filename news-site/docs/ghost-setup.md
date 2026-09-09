# Ghost VPS 部署手顺

推荐 Docker Compose 方式部署，便于升级和备份。

## 前置条件

- 一台 VPS（Ubuntu 22.04/24.04，1GB 内存以上）
- 一个域名（例如 `news.smart-assets.example`），A 记录指向 VPS
- VPS 已安装 Docker 和 Docker Compose plugin

## 1. 目录准备

```bash
sudo mkdir -p /opt/ghost && cd /opt/ghost
# 把 news-site/ghost/ 下的 docker-compose.yml 和 Caddyfile 上传到这里
```

## 2. 配置

编辑 `docker-compose.yml` 中的环境变量：

- `url`: 正式域名（`https://...`）
- `database__connection__password`: 强密码
- `mail__*`: SMTP 参数（会员验证邮件必须，推荐 Mailgun 或 Resend）

## 3. 启动

```bash
sudo docker compose up -d
```

首次访问 `https://<域名>/ghost` 创建管理员账号。

## 4. API Key 创建

Ghost 后台 → Settings → Integrations → Add custom integration：

- **Content API Key**：给 Astro 前端拉取公开文章用（只读，可暴露在构建环境）。
- **Admin API Key**：给本地管线发布文章用（`id:secret` 格式，绝对不能进 git）。

## 5. 会员 / 付费体系

Ghost 自带 Members 功能：

1. Settings → Membership → 打开注册，选择「Paid members only」或分层。
2. 连接 Stripe 账户（Ghost 后台向导直接授权）。
3. 配置门户（Portal）样式与付费层级。
4. 文章访问级别按篇设置：Public / Members only / Paid members only。

## 6. 备份

```bash
# 内容导出（Ghost 后台 Labs → Export 亦可）
sudo docker compose exec ghost node -e "..."   # 或定期用 ghost backup 镜像
# 数据库
sudo docker compose exec db mysqldump -u root -p<password> ghost > backup-$(date +%F).sql
```

至少把 `backup-*.sql` 和 Ghost 导出 JSON 定期拉回本地。
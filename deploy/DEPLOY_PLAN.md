# hkins 部署计划（中文逐步版）

> 适用：Ubuntu 22.04 / 24.04，Django + gunicorn + systemd + Celery + nginx + PostgreSQL + Redis
> 项目目录：`/home/hkai/app`　运行用户：`hkai`　域名：`hkai.favor100.site`
>
> 上线前逐项勾选：[GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md)

---

## 0. 部署拓扑

```text
浏览器
  │  HTTPS 443
  ▼
nginx（静态前端 web/dist + /api 反代 + /static 静态文件）
  │  HTTP 127.0.0.1:8010
  ▼
gunicorn（hkins-web.service，Django ASGI/WSGI）
  │
  ├── PostgreSQL      127.0.0.1:5432（数据库 hkins）
  └── Redis           127.0.0.1:6379（缓存 + Celery broker/result）
        │
        └── Celery workers（systemd 模板，按队列拆分）
            default / funds / news / fund-analysis
            cards / cards-io / proposal / docai
```

只需要对公网开放：**22 / 80 / 443**。
PostgreSQL、Redis、gunicorn(8010) 均只监听本机或内网。

---

## 1. 前置条件

- 域名 `hkai.favor100.site` 已解析到服务器公网 IP（A 记录）
- 服务器可访问：DeepSeek、SiliconFlow、PocketBase、腾讯 COS、SMTP
- 腾讯云安全组只放行 22 / 80 / 443
- 建议至少 4 核 8G（Playwright + 多个 worker 同时跑时内存占用较高）
- 磁盘：项目 + Rag 数据 + Playwright 浏览器约 2GB 起，建议 40GB+

### 1.1 如果和 pronotify 在同一台服务器

`/home/hkai/app` 与 pronotify 目录互不影响，但下面几项要错开：

```bash
ss -ltnp | grep ':8010 '      # 8010 应空闲；若被占用，安装时用 WEB_PORT=8011
```

1. **gunicorn 端口**：本项目默认监听 `127.0.0.1:8010`（pronotify 占用 8000）。
   若 8010 也被占用，安装时指定 `WEB_PORT=8011`，并让 nginx 的 `proxy_pass` 同步修改。
2. **Redis DB 编号**：本项目使用 DB **5**（缓存）、**6**（Celery broker）、**7**（结果）。
   不要使用 pronotify 已占用的 DB（当前 db3 有 3 个 Celery key）。
3. **PostgreSQL**：本项目数据库名固定为 `hkins`，不要覆盖 pronotify 的库。
4. **nginx**：给 `hkai.favor100.site` 单独一个 server block，不要改 pronotify 的配置。
5. **systemd / cron**：服务名 `hkins-*`、cron 文件 `/etc/cron.d/hkins` 均独立。

### 1.2 目录权限（nginx 必须能读）

`/home` 下的目录默认可能只有属主可进入，nginx(www-data) 会 403：

```bash
sudo chmod o+x /home/hkai
sudo chmod -R a+rX /home/hkai/app/web/dist
sudo chmod -R a+rX /home/hkai/app/backend/staticfiles
```

---

## 2. 服务器初始化

```bash
sudo apt update
sudo apt install -y \
  python3.12 python3.12-venv python3-pip \
  nginx postgresql redis-server \
  build-essential libpq-dev \
  fonts-noto-cjk fonts-noto-cjk-extra \
  git rsync curl
```

设置时区（cron 依赖）：

```bash
sudo timedatectl set-timezone Asia/Hong_Kong
timedatectl
```

创建运行用户：

```bash
sudo useradd -r -m -d /home/hkai -s /bin/bash hkai || true
sudo mkdir -p /home/hkai/app
sudo chown -R hkai:hkai /home/hkai/app
```

---

## 3. 数据库与 Redis

### 3.1 PostgreSQL

```bash
sudo -u postgres psql
```

```sql
CREATE USER hkins WITH PASSWORD 'CHANGE_ME_DB_PASSWORD';
CREATE DATABASE hkins OWNER hkins;
GRANT ALL PRIVILEGES ON DATABASE hkins TO hkins;
\q
```

### 3.2 Redis

编辑 `/etc/redis/redis.conf`：

```conf
requirepass CHANGE_ME_REDIS_PASSWORD
bind 127.0.0.1
```

```bash
sudo systemctl enable --now redis-server
redis-cli -a 'CHANGE_ME_REDIS_PASSWORD' ping   # PONG
```

> 如果使用腾讯云托管 PostgreSQL / Redis，只保留上面的 `CREATE DATABASE`，
> 后续在 `backend/conf/env.py` 里填写托管地址即可。

---

## 4. 同步代码

只同步源码，**不要**带上本机的运行数据：

```text
venv/
web/node_modules/
web/dist/
backend/staticfiles/
backend/media/                         # 用 COS 时可不传
backend/proposal_data/.browser_profile/  # 含以色列门户登录态，禁止上传
backend/docai_data/                    # 用户上传文件，禁止上传
backend/card_data/                     # 生成的测试产物
backend/news_data/                     # 测试生成的 HTML
backend/fund_reports/                  # 测试生成的报告
```

需要带上：

```text
backend/rag_data/                      # 知识库索引 + 产品资料，必须
```

示例：

```bash
rsync -avz --progress \
  --exclude 'venv' \
  --exclude 'web/node_modules' \
  --exclude 'web/dist' \
  --exclude 'backend/staticfiles' \
  --exclude 'backend/media' \
  --exclude 'backend/proposal_data/.browser_profile' \
  --exclude 'backend/docai_data' \
  --exclude 'backend/card_data' \
  --exclude 'backend/news_data' \
  --exclude 'backend/fund_reports' \
  ./hkins/ hkai@<SERVER_IP>:/home/hkai/app/

sudo chown -R hkai:hkai /home/hkai/app
```

---

## 5. Python 依赖 + Playwright

```bash
cd /home/hkai/app
sudo -u hkai python3.12 -m venv venv
sudo -u hkai /home/hkai/app/venv/bin/pip install -U pip
sudo -u hkai /home/hkai/app/venv/bin/pip install \
  -r /home/hkai/app/backend/req_nodb.txt psycopg2-binary
```

> 必须用 `req_nodb.txt`（不含 `mysqlclient`），再单独装 `psycopg2-binary`。

安装 Chromium（计划书生成 / 图文卡渲染）：

```bash
sudo /home/hkai/app/venv/bin/python -m playwright install-deps chromium
sudo -u hkai /home/hkai/app/venv/bin/python -m playwright install chromium
fc-list | grep -i "Noto Sans CJK"   # 必须有输出
```

---

## 6. 生产配置

```bash
sudo -u hkai cp /home/hkai/app/backend/conf/env_server.py \
  /home/hkai/app/backend/conf/env.py
sudo -u hkai nano /home/hkai/app/backend/conf/env.py
```

### 6.1 必改项

| 配置 | 说明 / 示例 |
|---|---|
| `DATABASE_ENGINE` | 默认 PostgreSQL |
| `DATABASE_NAME` | `hkins` |
| `DATABASE_HOST` / `PORT` | `127.0.0.1` / `5432` |
| `DATABASE_USER` / `PASSWORD` | `hkins` / 强密码 |
| `REDIS_HOST` / `REDIS_PASSWORD` | `127.0.0.1` / 强密码 |
| `PUBLIC_BASE` | `https://hkai.favor100.site` |
| `ALLOWED_HOSTS` | `hkai.favor100.site` |
| `FRONTEND_BASE` | 自动等于 `PUBLIC_BASE` |
| `NEWS_HTML_BASE` | 自动等于 `PUBLIC_BASE` |
| `SMTP_HOST/PORT/USER/PASS` | 企业邮箱 |
| `COS_SECRET_ID/KEY/REGION/BUCKET` | 腾讯 COS |
| `COS_PUBLIC_BASE` | 有 CDN/CNAME 时填，否则留空（后端直出 HTML） |
| `DEEPSEEK_API_KEY/BASE/MODEL` | 文本 LLM |
| `VLLM_API_KEY/BASE/MODEL` | 图片识别 / 提交前核对 |
| `PI_API_KEY/BASE/MODEL` | RAG 知识库 |
| `HKFUND_PB_URL/EMAIL/PASSWORD` | 基金数据源 |
| `QVERIS_API_KEY` | 若使用 QVeris 直连 |
| `PROPOSAL_HEADLESS` | 服务器必须为 `'on'` |

### 6.2 推荐用环境变量注入敏感信息

```bash
sudo nano /etc/hkins/hkins.env
```

```ini
DJANGO_SECRET_KEY=CHANGE_ME_64_CHARS_RANDOM
ALLOWED_HOSTS=hkai.favor100.site
PUBLIC_BASE=https://hkai.favor100.site
```

并在 systemd 服务里加载（`hkins-web.service` 与 `hkins-worker@.service`）：

```ini
EnvironmentFile=-/etc/hkins/hkins.env
```

或者省事一点：直接把值写进 `env.py`（上线前注意轮换与权限）。

### 6.3 HTTPS 未开通时

`env_server.py` 默认开启强制 HTTPS。若先用 HTTP 调试，注释掉 `env.py` 末尾：

```python
# SECURE_SSL_REDIRECT = True
# SESSION_COOKIE_SECURE = True
# CSRF_COOKIE_SECURE = True
# SECURE_HSTS_SECONDS = 31536000
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True
```

证书配置完成后再恢复。

### 6.4 配置自检

```bash
cd /home/hkai/app/backend
sudo -u hkai /home/hkai/app/venv/bin/python manage.py check --deploy
```

期望：`System check identified no issues`。

---

## 7. 初始化数据库 / 静态文件 / 菜单

```bash
cd /home/hkai/app/backend

sudo -u hkai /home/hkai/app/venv/bin/python manage.py migrate
sudo -u hkai /home/hkai/app/venv/bin/python manage.py collectstatic --noinput
```

### 7.1 全新数据库才执行

> ⚠️ 已有生产数据时**不要**执行 `init -y`（会重置种子数据）。

```bash
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init -y
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_tenant_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_property_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_notify_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_changelog_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_broadcast_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_workspace_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_internal_role
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_proposal_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_card_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_fund_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_news_sources
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_card_companies
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_docai_menu
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_tenant_roles
sudo -u hkai /home/hkai/app/venv/bin/python manage.py init_tenant_menus
```

> 初始超管：`superadmin / admin123456`（以 `backend/dvadmin/system/fixtures/init_users.json` 为准）。
> 首次登录后立即修改密码。

---

## 8. 构建前端

```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install -y nodejs
node -v    # v22.x
```

```bash
cd /home/hkai/app/web
sudo -u hkai npm ci --legacy-peer-deps
sudo -u hkai npm run build
```

确认：

```bash
grep '<title>' dist/index.html                 # <title>DayBetter</title>
grep -r '127.0.0.1:8000' dist/assets | wc -l   # 必须是 0
du -sh dist                                    # 约 13MB
```

> 关键：`web/.env.production` 必须是 `VITE_API_URL = '/'`。
> 填 `/api` 会让所有请求变成 `/api/api/...`，生产直接 404。

---

## 9. 启动 gunicorn + Celery

```bash
cd /home/hkai/app/deploy
sudo APP_DIR=/home/hkai/app APP_USER=hkai ./install.sh
```

会安装/启动：

| 服务 | 作用 |
|---|---|
| `hkins-web.service` | gunicorn 127.0.0.1:8010 |
| `hkins-worker@default` | RAG 建索引等默认队列任务 |
| `hkins-worker@funds` | 基金汇总推送 |
| `hkins-worker@fund-analysis` | 单基金深度分析 |
| `hkins-worker@news` | 新闻简报 |
| `hkins-worker@cards` | 图文卡渲染 |
| `hkins-worker@cards-io` | COS 归档（并发 2） |
| `hkins-worker@proposal` | 计划书生成（Playwright） |
| `hkins-worker@docai` | AI 文件分析 |

检查：

```bash
sudo systemctl status hkins-web --no-pager
sudo systemctl list-units 'hkins-*' --no-pager

cd /home/hkai/app/backend
sudo -u hkai /home/hkai/app/venv/bin/celery -A application inspect active_queues
```

`active_queues` 必须能看到上面 8 个队列。

日志：

```bash
journalctl -u hkins-web -f
journalctl -u hkins-worker@funds -f
journalctl -u hkins-worker@cards -f
journalctl -u hkins-worker@docai -f
```

---

## 10. 定时任务

`install.sh` 已安装 `/etc/cron.d/hkins`：

| 时间（Asia/Hong_Kong） | 命令 | 队列 |
|---|---|---|
| 周一~周五 08:30 | `funds_daily` | funds |
| 周一~周五 08:45 | `funds_analysis` | fund-analysis |
| 每天 08:45 | `news_daily --edition morning` | news |
| 每天 15:45 | `news_daily --edition afternoon` | news |

检查：

```bash
cat /etc/cron.d/hkins
sudo systemctl status cron --no-pager
```

> cron 只负责“入队”，真正发送靠常驻 Celery worker。
> 服务器时区必须是 `Asia/Hong_Kong`。

手动测试（可选，会真实入队/发送，注意别重复群发）：

```bash
cd /home/hkai/app/deploy
sudo -u hkai ./scripts/run_manage.sh funds_daily --weekday 0
sudo -u hkai ./scripts/run_manage.sh news_daily --edition morning
```

---

## 11. Nginx + HTTPS

### 11.1 先建 HTTP 站点

```bash
sudo nano /etc/nginx/sites-available/hkins
```

```nginx
server {
    listen 80;
    server_name hkai.favor100.site;

    root /home/hkai/app/web/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /home/hkai/app/backend/staticfiles/;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/hkins /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 11.2 申请证书

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d hkai.favor100.site --redirect
```

完成后：

- 恢复 `env.py` 的 6 行 HTTPS 安全配置
- `sudo systemctl restart hkins-web`

> nginx 必须传 `X-Forwarded-Proto`，否则 Django 的 `SECURE_SSL_REDIRECT`
> 会误判为 HTTP 并无限重定向。

---

## 12. 上线验证

### 12.1 命令行

```bash
curl -I https://hkai.favor100.site/                          # 200
curl -s https://hkai.favor100.site/api/captcha/ | head -c 80 # code 2000
curl -I https://hkai.favor100.site/static/clause/privacy.css  # 200
```

### 12.2 浏览器

1. 登录超管，概览页正常
2. 渠道管理 / 渠道审核正常
3. 知识库管理：产品列表、搜索正常
4. AI 文件分析：上传 PDF → 完成 → **查看报告**能打开
5. 保险图文卡：上传计划书 → 识别 → 生成
6. 计划书生成：先用「仅演练」跑一次，确认门户登录/核对正常
7. 飞书群推送：先「生成预览」，确认无误再推送
8. 渠道用户登录：首页 / AI 知识库 / 图文卡 / 文件分析 / 个人中心无 404

### 12.3 服务检查

```bash
sudo systemctl status hkins-web --no-pager
sudo systemctl list-units 'hkins-*' --no-pager
cd /home/hkai/app/backend
sudo -u hkai /home/hkai/app/venv/bin/celery -A application inspect active_queues
```

---

## 13. 从开发环境迁移数据（可选）

```bash
# 开发机导出
pg_dump -h 127.0.0.1 -p 5433 -U postgres -d hkins -Fc -f /tmp/hkins.dump

# 上传到服务器后恢复
sudo -u postgres pg_restore -d hkins --clean --if-exists /tmp/hkins.dump
```

同时复制：

```text
backend/rag_data/     # 必须
backend/media/        # 如果未使用 COS
```

**禁止复制**：

```text
backend/proposal_data/.browser_profile/   # 含门户登录 Cookie/会话
backend/docai_data/                       # 含用户上传文件
```

迁移后建议：

- 重新登录一次保险公司门户，让服务器生成新的浏览器 profile
- 检查飞书群 webhook 是否仍有效
- 检查 `PUBLIC_BASE` 相关链接（新闻/基金报告）是否能打开

---

## 14. 日常更新发布流程

```bash
# 1) 备份数据库
sudo -u postgres pg_dump -Fc hkins > /var/backups/hkins-$(date +%F-%H%M).dump

# 2) 同步代码（排除运行数据）
rsync -avz --exclude 'venv' --exclude 'web/node_modules' --exclude 'web/dist' \
  --exclude 'backend/staticfiles' --exclude 'backend/docai_data' \
  --exclude 'backend/proposal_data/.browser_profile' \
  ./hkins/ hkai@<SERVER_IP>:/home/hkai/app/

# 3) 依赖（如有变化）
sudo -u hkai /home/hkai/app/venv/bin/pip install -r /home/hkai/app/backend/req_nodb.txt psycopg2-binary

# 4) 数据库 + 静态文件
cd /home/hkai/app/backend
sudo -u hkai /home/hkai/app/venv/bin/python manage.py migrate
sudo -u hkai /home/hkai/app/venv/bin/python manage.py collectstatic --noinput

# 5) 前端
cd /home/hkai/app/web
sudo -u hkai npm ci --legacy-peer-deps
sudo -u hkai npm run build

# 6) 重启
sudo systemctl restart hkins-web
sudo systemctl restart \
  hkins-worker@default hkins-worker@funds hkins-worker@news \
  hkins-worker@fund-analysis hkins-worker@cards hkins-worker@cards-io \
  hkins-worker@proposal hkins-worker@docai
```

> 改了 `tasks.py` / `schedule.py` / `news.py` / `analysis.py` / `cards` 技能脚本后，
> **必须重启对应 worker**，否则仍跑旧代码。

---

## 15. 回滚

```bash
sudo systemctl stop hkins-web

# 恢复上一版代码（建议每次发布打 tar 包留档）
# 恢复数据库备份
sudo -u postgres pg_restore -d hkins --clean --if-exists /var/backups/xxx.dump

sudo systemctl start hkins-web
sudo systemctl restart \
  hkins-worker@default hkins-worker@funds hkins-worker@news \
  hkins-worker@fund-analysis hkins-worker@cards hkins-worker@cards-io \
  hkins-worker@proposal hkins-worker@docai
```

发布前建议打包留档：

```bash
sudo tar czf /var/backups/hkins-code-$(date +%F-%H%M).tar.gz \
  --exclude='venv' --exclude='web/node_modules' --exclude='web/dist' \
  -C /home/hkai app
```

---

## 16. 安全清单

- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` 只包含真实域名
- [ ] `DJANGO_SECRET_KEY` 为强随机值，或通过环境变量注入
- [ ] `LOGIN_NO_CAPTCHA_AUTH=False`（生产已默认）
- [ ] `/apiLogin/` 在 `DEBUG=False` 下已禁用
- [ ] 修改 superadmin 密码，删除/停用 `admin`、`test`
- [ ] 轮换所有曾提交在 `conf/env.py` 的密钥
  （DB / Redis / SMTP / COS / DeepSeek / VLLM / PI / HKFUND / QVeris）
- [ ] 数据库、Redis 不监听公网
- [ ] 只有 22/80/443 对外
- [ ] HTTPS 已启用，证书自动续期
- [ ] 每日数据库备份 + 定期恢复演练
- [ ] 确认不复制 `proposal_data/.browser_profile` 到服务器

---

## 附录 A：端口与路径

| 项目 | 值 |
|---|---|
| 前端 dist | `/home/hkai/app/web/dist` |
| Django | `/home/hkai/app/backend` |
| 静态文件 | `/home/hkai/app/backend/staticfiles` |
| 知识库数据 | `/home/hkai/app/backend/rag_data` |
| 计划书数据 | `/home/hkai/app/backend/proposal_data` |
| 图文卡工作区 | `/home/hkai/app/backend/card_data` |
| 文件分析数据 | `/home/hkai/app/backend/docai_data` |
| 新闻 HTML | `/home/hkai/app/backend/news_data` |
| 基金报告 | `/home/hkai/app/backend/fund_reports` |
| gunicorn | `127.0.0.1:8010` |
| Celery broker | Redis DB 6 |
| Celery result | Redis DB 7 |
| 缓存 | Redis DB 5 |

## 附录 B：常见问题

**1) 前端所有接口 404，路径出现 `/api/api/...`**
→ `.env.production` 的 `VITE_API_URL` 被改成了 `/api`，必须是 `/`，然后重新 `npm run build`。

**2) 所有 HTTP 都 301 到 HTTPS / 无限重定向**
→ 证书没配好，或 nginx 没传 `X-Forwarded-Proto`，或临时注释 `env.py` 的 6 行安全配置。

**3) 渠道用户除了首页都 404**
→ 菜单没初始化，执行第 7 节的 `init_*` 命令；渠道用户需重新登录。

**4) 计划书/图文卡任务一直 queued**
→ 对应 worker（proposal/cards/docai）没启动，或改了代码没重启 worker。

**5) RAG「新增产品」一直排队**
→ `default` 队列 worker 没启动（`hkins-worker@default`）。

**6) 飞书卡片里的链接打不开**
→ `PUBLIC_BASE` 不是公网地址，或 nginx 没有反代 `/api/`。

**7) 图片/卡片中文变方块**
→ 服务器没装 `fonts-noto-cjk`，安装后重启 cards worker 并重新生成。

**8) 上传文件成功但分析报 400**
→ 检查前端请求是否为 `multipart/form-data`（docai 已修复），以及 nginx 的 `client_max_body_size`：

```nginx
client_max_body_size 50m;
```

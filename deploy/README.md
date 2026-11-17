# hkins deploy (Ubuntu)

> 中文逐步部署指南（推荐先看）: **[DEPLOY_PLAN.md](DEPLOY_PLAN.md)**
> 上线当天检查清单: **[GO_LIVE_CHECKLIST.md](GO_LIVE_CHECKLIST.md)**

Files:

```
deploy/
  DEPLOY_PLAN.md                 # 中文逐步部署指南
  GO_LIVE_CHECKLIST.md           # 上线检查清单
  install.sh                     # install systemd units + /etc/cron.d/hkins
  systemd/hkins-worker@.service  # one template, %i = queue name
  systemd/hkins-web.service      # gunicorn (Django API)
  cron/hkins.cron                # scheduled pushes (enqueue only)
  scripts/run_manage.sh          # manual helper: ./run_manage.sh funds_daily
```

## 0. Prerequisites

- Ubuntu 22.04/24.04, project at `/home/hkai/app` (backend in `/home/hkai/app/backend`)
- PostgreSQL + Redis reachable (the compose file or managed services)
- Python venv at `/home/hkai/app/venv` with `backend/req_nodb.txt` installed
- A Linux user that owns the project, e.g. `hkai`
- Timezone: **`sudo timedatectl set-timezone Asia/Hong_Kong`** (Debian cron has no `CRON_TZ`)

## 1. One-time install

```bash
sudo useradd -r -m -d /home/hkai -s /bin/bash hkai || true
sudo mkdir -p /home/hkai/app
sudo chown -R hkai:hkai /home/hkai/app

# venv + deps
sudo -u hkai /home/hkai/app/venv/bin/pip install -r /home/hkai/app/backend/req_nodb.txt

# config (settings.py imports conf.env directly)
sudo -u hkai cp /home/hkai/app/backend/conf/env_server.py /home/hkai/app/backend/conf/env.py
# env_server.py is now a full production mirror of the dev env (DEBUG=False,
# CORS off, secure cookies/HSTS on). Edit /home/hkai/app/backend/conf/env.py:
#   DATABASE_*, REDIS_*, COS_*, DEEPSEEK_*, VLLM_*, PI_*, HKFUND_*, QVERIS_*,
#   SMTP_*, ...
# Public URLs: set ONE value (or export the env vars before starting services):
#   PUBLIC_BASE       e.g. https://hkai.favor100.site  (drives FRONTEND_BASE + NEWS_HTML_BASE)
#   ALLOWED_HOSTS     comma separated, default "hkai.favor100.site"
#   DJANGO_SECRET_KEY strong random string (env_server.py ships a generated one)
#   COS_PUBLIC_BASE   optional COS/CDN domain for HTML (otherwise backend serves it)
# If you test over plain HTTP first, temporarily comment out the 6
# SECURE_SSL_REDIRECT / *_COOKIE_SECURE / SECURE_HSTS_* lines at the bottom.

sudo -u hkai /home/hkai/app/venv/bin/python /home/hkai/app/backend/manage.py migrate
sudo -u hkai /home/hkai/app/venv/bin/python /home/hkai/app/backend/manage.py collectstatic --noinput
sudo -u hkai /home/hkai/app/venv/bin/python /home/hkai/app/backend/manage.py init_docai_menu   # idempotent
sudo -u hkai /home/hkai/app/venv/bin/python /home/hkai/app/backend/manage.py init_tenant_menus  # grant /docai to every tenant role
```

Frontend: `cd /home/hkai/app/web && npm ci && npm run build` → serve `web/dist` with nginx.
`web/.npmrc` sets `legacy-peer-deps=true`; if it is missing use `npm ci --legacy-peer-deps`.
Poppins is self-hosted under `src/assets/fonts/poppins/` (no Google Fonts request).
`.env.production` must keep **`VITE_API_URL = '/'`** (request paths already start with
`/api/`; using `/api` produces `/api/api/...`). Nginx proxies `/api/` to `127.0.0.1:8010`.

**Nginx must have gzip enabled** for `application/javascript` and `text/css` (see the sample
below). Without it the JS/CSS are served uncompressed (~2.4 MB first load).

Because the app lives under `/home/hkai`, nginx needs traversal permission:

```bash
sudo chmod o+x /home/hkai
sudo chmod -R a+rX /home/hkai/app/web/dist /home/hkai/app/backend/staticfiles
```

Minimal nginx server block:

```nginx
server {
    listen 443 ssl http2;
    server_name hkai.favor100.site;
    root /home/hkai/app/web/dist;
    index index.html;

    # 压缩 (若 nginx 编译了 ngx_brotli, 可再加 brotli on; brotli_types ...;)
    gzip on;
    gzip_vary on;
    gzip_comp_level 6;
    gzip_min_length 1024;
    gzip_types text/css application/javascript application/json image/svg+xml application/wasm;

    # 带 hash 的静态资源长期缓存; index.html 不缓存
    location /assets/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }
    location = /index.html {
        add_header Cache-Control "no-cache";
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8010;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;   # required (SECURE_SSL_REDIRECT)
        proxy_read_timeout 300s;                      # RAG SSE / report downloads
    }
    location /static/ { alias /home/hkai/app/backend/staticfiles/; }
    location / { try_files $uri $uri/ /index.html; }  # hash router, safe fallback
}
```

## 2. Install services + cron

```bash
cd /home/hkai/app/deploy
sudo APP_DIR=/home/hkai/app APP_USER=hkai ./install.sh
```

This will:
- render/install `hkins-worker@.service` + `hkins-web.service`
- create `/etc/hkins/worker-cards-io.env` (`CONCURRENCY=2`)
- enable + start workers for queues:
  `default`, `funds`, `news`, `fund-analysis`, `cards`, `cards-io`, `proposal`, `docai`
  (`default` is required: RAG indexing and a few legacy tasks use `.delay()` without a queue)
- enable `hkins-web.service` if gunicorn is installed
- install `/etc/cron.d/hkins`

Check:

```bash
systemctl status hkins-worker@funds
systemctl status hkins-worker@fund-analysis
systemctl status hkins-worker@news
systemctl status hkins-worker@docai
journalctl -u hkins-worker@funds -f
```

## 3. Schedule (Asia/Hong_Kong)

| time | command | queue | what |
|---|---|---|---|
| Mon–Fri 08:30 | `manage.py funds_daily` | `funds` | 基金榜单汇总卡 |
| Mon–Fri 08:45 | `manage.py funds_analysis` | `fund-analysis` | 逐只基金深度分析卡（QVeris，较慢） |
| daily 08:45 | `manage.py news_daily --edition morning` | `news` | 早间新闻简报 |
| daily 15:45 | `manage.py news_daily --edition afternoon` | `news` | 午间新闻简报 |

Cron only **enqueues**; the workers send. Weekend is skipped automatically by the commands.

## 4. Manual tests

```bash
cd /home/hkai/app/deploy
sudo -u hkai ./scripts/run_manage.sh funds_daily --weekday 0
sudo -u hkai ./scripts/run_manage.sh news_daily --edition morning
sudo -u hkai ./scripts/run_manage.sh funds_analysis --weekday 0
tail -f /var/log/hkins/cron.log
```

## 5. Notes / gotchas

- **If pronotify shares this server**: hkins defaults to gunicorn `127.0.0.1:8010`
  (`ss -ltnp | grep ':8010 '`; override with `WEB_PORT=8011`). This app uses Redis DB
  **5/6/7** (cache/broker/result) — do not reuse pronotify's DB (currently db3).
  PostgreSQL database name is `hkins`; never overwrite the pronotify DB.
- **After changing `tasks.py` / `schedule.py` / `news.py` / `analysis.py`, restart the related worker:**
  `sudo systemctl restart hkins-worker@funds` (or `@news`, `@fund-analysis`, `@cards`, `@docai`, …).
- If a worker starts before a task is defined, its banner task list won't include it; restarting fixes it.
- Report/HTML pages (`/api/funds/news/html/…`, `/api/funds/report/…`) are served by Django; make sure
  nginx proxies `/api/` and `NEWS_HTML_BASE` is publicly reachable (do **not** use `localhost` in production).
- Tencent COS default domains force-download HTML (`x-cos-force-download`); that's why the backend serves
  these pages and uses COS only as an archive (or bind a COS custom domain and set `COS_PUBLIC_BASE`).
- AI prompts are editable at 超级管理 → AI 提示词 (DB-backed, applies on next run; no restart needed).
- Database/Redis/COS/DeepSeek/QVeris secrets live in `backend/conf/env.py`; keep it out of git.
- **Do not copy runtime data from a dev machine**: `backend/proposal_data/.browser_profile`
  contains a logged-in insurer portal session, `docai_data/` contains user documents, and
  `card_data/` / `fund_reports/` / `news_data/` are generated artifacts. Deploy `rag_data/`
  (index + catalog) only. Let the server create the rest on first use.
- **Do not use the root `docker-compose.yml`** — it is the original template (MySQL + old
  nginx/celery images) and does not match this project. Deploy with gunicorn + systemd + nginx.
- `manage.py check --deploy` should be clean when running with the production `env.py`.
  Run `manage.py collectstatic --noinput` after every deploy (WhiteNoise serves `/static/`).

# hkins 上线检查清单（Go-Live Checklist）

> 部署步骤见 [DEPLOY_PLAN.md](DEPLOY_PLAN.md)。上线当天按本清单逐项勾选。

日期：____________　域名：`hkai.favor100.site`　目录：`/home/hkai/app`　用户：`hkai`

---

## A. 代码与配置

- [ ] 代码已同步到 `/home/hkai/app`，运行用户为 `hkai`
- [ ] `/home/hkai` 可被 nginx 进入（`chmod o+x /home/hkai`）
- [ ] 若 pronotify 同机：hkins gunicorn 用 8010，Redis 用 DB 5/6/7（不占用 db3）
- [ ] `backend/conf/env.py` 由 `env_server.py` 生成
- [ ] `DEBUG=False`
- [ ] `ALLOWED_HOSTS` 已填真实域名（不含 `*`）
- [ ] `PUBLIC_BASE=https://<域名>`
- [ ] `FRONTEND_BASE` / `NEWS_HTML_BASE` 等于 `PUBLIC_BASE`
- [ ] `DJANGO_SECRET_KEY` 为强随机值（非 `django-insecure-*`）
- [ ] 数据库 / Redis 连接信息正确
- [ ] SMTP / COS / DeepSeek / VLLM / PI / HKFUND / QVeris 密钥已配置
- [ ] `LOGIN_NO_CAPTCHA_AUTH=False`
- [ ] `web/.env.production` 为 `VITE_API_URL = '/'`
- [ ] 未复制 `backend/proposal_data/.browser_profile/`
- [ ] 未复制 `backend/docai_data/`

## B. 依赖与初始化

- [ ] Python 3.12 venv 已创建
- [ ] `pip install -r req_nodb.txt psycopg2-binary` 成功
- [ ] `playwright install chromium` 成功
- [ ] `playwright install-deps chromium` 成功
- [ ] `fonts-noto-cjk` 已安装（`fc-list` 有输出）
- [ ] Node 22 已安装
- [ ] `npm ci --legacy-peer-deps` 成功
- [ ] `npm run build` 成功
- [ ] `migrate` 成功，无未应用迁移
- [ ] `collectstatic --noinput` 成功
- [ ] 菜单初始化命令已执行（fresh DB: `init -y` 等）
- [ ] `manage.py check --deploy` → 0 issues

## C. 服务

- [ ] `hkins-web.service` active
- [ ] `hkins-worker@default` active
- [ ] `hkins-worker@funds` active
- [ ] `hkins-worker@news` active
- [ ] `hkins-worker@fund-analysis` active
- [ ] `hkins-worker@cards` active
- [ ] `hkins-worker@cards-io` active
- [ ] `hkins-worker@proposal` active
- [ ] `hkins-worker@docai` active
- [ ] `celery inspect active_queues` 显示 8 个队列
- [ ] `/etc/cron.d/hkins` 已安装
- [ ] 服务器时区为 `Asia/Hong_Kong`

## D. Nginx / HTTPS

- [ ] nginx 配置通过 `nginx -t`
- [ ] 前端 `web/dist` 可访问
- [ ] `/api/` 反向代理到 `127.0.0.1:8010`
- [ ] `/static/` 指向 `backend/staticfiles/`
- [ ] 未设置 `client_max_body_size` 时上传大文件会 413（建议 50m）
- [ ] 已传 `X-Forwarded-Proto`
- [ ] 证书已签发，HTTP 自动跳转 HTTPS
- [ ] 证书自动续期（`certbot renew --dry-run`）

## E. 功能验证

- [ ] 超管登录成功，强制改密完成
- [ ] 概览页数据正常
- [ ] 渠道管理 / 渠道审核正常
- [ ] 知识库管理：列表 / 搜索正常
- [ ] AI 文件分析：上传 PDF → 完成 → 查看报告可打开
- [ ] 保险图文卡：上传计划书 → 识别正常
- [ ] 图文卡生成任务能完成（worker 正常）
- [ ] 计划书生成：演练模式跑通
- [ ] 飞书群推送：预览正常
- [ ] 渠道用户登录：首页 / RAG / 图文卡 / 文件分析 / 个人中心无 404
- [ ] 内部用户：计划书 / 卡片模板 / 公司管理正常
- [ ] 新闻/基金公开 HTML 链接可匿名访问
- [ ] 控制台 / 浏览器无 4xx/5xx 接口错误

## F. 安全

- [ ] 修改 superadmin 密码
- [ ] 删除 / 停用 `admin`、`test` 等初始账号
- [ ] 轮换所有曾提交的密钥
- [ ] 数据库 / Redis 不监听公网
- [ ] 安全组只开放 22/80/443
- [ ] `captcha_state=true`（登录验证码开启）
- [ ] 每日数据库备份已配置
- [ ] 备份恢复演练至少一次

## G. 收尾

- [ ] 发布代码包已留档（tar.gz）
- [ ] 数据库备份文件已留档
- [ ] `deploy/DEPLOY_PLAN.md` 中的路径/域名已按实际修改
- [ ] 监控 / 日志查看方式已交接（`journalctl`、`/var/log/hkins/`）
- [ ] 回滚步骤已确认（恢复代码 + 恢复 DB + 重启服务）

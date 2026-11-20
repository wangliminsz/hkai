# hkins · 移动版前端（web_mobile）

港险 AI 智慧系统的手机端工作台。独立 Vite + Vue 3 技术栈构建，**复用同一个 Django 后端**，
通过新域名 `mhkai.favor100.site` 访问；桌面端仍为 `hkai.favor100.site`（`web/`）。

> 后端接口、数据库、Celery 任务均**无需改动**。移动端只是另一个前端产物 + 一个 nginx server block。

---

## 1. 已实现功能

| 页面 | 路由 | 说明 |
|---|---|---|
| 登录 | `/login` | 账号 / 邮箱 / 手机号 + 密码 + SVG 验证码；MD5 密码；首次登录强制改密 |
| 工作台 | `/home` | 问候语、渠道信息、按角色显示的快捷入口 |
| AI 知识库 | `/rag` | 公司/产品筛选、产品文件下载、SSE 流式问答、页码引用、复制、大白话、术语解释 |
| 保险图文卡 | `/cards` | 上传计划书 PDF → 自动识别 → 编辑文案 → 生成 → 预览 / 下载 ZIP / 历史 |
| AI 文件分析 | `/docai` | 上传 PDF/图片 + 邮箱 + Prompt → 轮询状态 → 查看报告 / 历史 |
| 计划书生成 | `/proposal` | 仅内部用户；保险公司选择、可生成产品列表、仅演练开关、日志、PDF 下载 |
| 个人中心 | `/profile` | 资料、邮箱/手机/部门、修改密码、退出登录 |
| 个人资料 | `/profile/edit` | 姓名、邮箱、手机、性别 |
| 电脑版提示 | `/desktop` | 组织架构、飞书群推送、图文卡模板/公司等复杂功能引导到电脑版 |

权限规则与桌面端一致：`internal` 角色才显示计划书生成；`tenant_manager` 才显示飞书群推送/组织架构；
AI 文件分析按后端 `/api/docai/access/` 的返回值显示。

---

## 2. 技术栈

- Vue 3 + Vite 5 + TypeScript
- Vue Router（hash 模式，`/#/home`）
- Pinia
- Vant 4（移动端 UI，深色主题）
- Axios + `ts-md5`

目录：

```text
web_mobile/
  src/
    api/          # auth / rag / cards / docai / proposal / user / app
    components/   # AppNav / StatusBadge / EmptyState
    router/       # 路由 + 登录守卫
    stores/       # auth / app(品牌)
    styles/       # 全局深色主题 & Vant 变量
    utils/        # http / storage / url / md5
    views/        # 页面
  public/         # db_trans.png / favicon.ico
  deploy/nginx-mhkai.conf.example
```

---

## 3. 本地开发

前置：Node.js ≥ 18，Django 后端运行在 `http://127.0.0.1:8000`。

```bash
cd web_mobile
npm install
npm run dev
# http://localhost:8090
```

开发环境不跨域：`vite.config.ts` 已把 `/api`、`/static` 代理到 `127.0.0.1:8000`，
所以 `.env.development` 中 `VITE_API_URL=''` 即可。

生产构建：

```bash
npm run build       # 产物在 web_mobile/dist
npm run preview     # 本地预览 dist（可选）
```

---

## 4. 部署到 mhkai.favor100.site（后端不改）

### 4.1 DNS + 构建

1. 在 DNS 添加 `mhkai.favor100.site` 的 A 记录，指向服务器公网 IP。
2. 在服务器构建：

```bash
cd /home/hkai/app/web_mobile
sudo -u hkai npm ci
sudo -u hkai npm run build
sudo chown -R hkai:hkai dist
sudo chmod -R a+rX dist
```

> 如果服务器 `/home` 权限较严，nginx 需要能进入目录：
> `sudo chmod o+x /home/hkai`

### 4.2 nginx

复制并启用示例配置：

```bash
sudo cp /home/hkai/app/web_mobile/deploy/nginx-mhkai.conf.example \
        /etc/nginx/sites-available/hkins-mobile
sudo ln -sf /etc/nginx/sites-available/hkins-mobile /etc/nginx/sites-enabled/hkins-mobile
sudo nginx -t && sudo systemctl reload nginx
```

关键点（详见示例文件）：

- `root /home/hkai/app/web_mobile/dist`
- `/api/`、`/static/`、`/media/` 反代/别名到现有后端
- `/api/rag/` 关闭 `proxy_buffering`，否则流式回答会一次性吐出
- `client_max_body_size 50m`（上传 PDF / 图片）
- `proxy_read_timeout 600s`（计划书生成、文件分析、报告下载）
- **为了不改后端 `ALLOWED_HOSTS`**：`proxy_set_header Host hkai.favor100.site;`
  - 若你愿意改后端配置，也可以把 `mhkai.favor100.site` 加入 `backend/conf/env.py` 的
    `ALLOWED_HOSTS`，然后改成 `proxy_set_header Host $host;`（更规范）。
- 必须传 `X-Forwarded-Proto $scheme`，否则后端 `SECURE_SSL_REDIRECT` 会误判。

### 4.3 HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d mhkai.favor100.site --redirect
```

完成后 `https://mhkai.favor100.site` 应能打开登录页。

### 4.4 验证

```bash
curl -I https://mhkai.favor100.site/                      # 200
curl -s https://mhkai.favor100.site/api/init/settings/ | head -c 120
curl -s https://mhkai.favor100.site/api/captcha/ | head -c 120
```

浏览器验证：

1. 手机打开 `https://mhkai.favor100.site` → 登录页显示 Logo / 标题 / 验证码
2. 渠道用户登录 → 首页快捷入口、AI 知识库问答流式输出
3. 上传计划书 → 图文卡生成 → 预览 / 下载 ZIP
4. AI 文件分析 → 提交 → 报告链接可打开
5. 内部用户 → 计划书生成 → 下载 PDF
6. 「我的」→ 修改资料 / 修改密码 / 退出登录

---

## 5. 可选：手机访问桌面域名自动跳转

若不希望用户记住新域名，可在 `hkai.favor100.site` 的 server block 内加：

```nginx
map $http_user_agent $is_mobile {
    default 0;
    ~*iphone|ipad|ipod|android|mobile 1;
}

server {
    # ... existing hkai config ...
    if ($is_mobile) {
        return 302 https://mhkai.favor100.site$request_uri;
    }
}
```

注意：`map` 必须放在 `http {}` 层级（`/etc/nginx/conf.d/` 或 `nginx.conf`），
不要放进 `server {}`。平板/微信内置浏览器也会命中 `mobile`，按需调整正则。

---

## 6. 环境变量

| 变量 | 开发 | 生产 | 说明 |
|---|---|---|---|
| `VITE_API_URL` | `''` | `''` | 留空表示同源，`/api` 由 proxy/nginx 转发；**不要写 `/api`** |
| `VITE_APP_TITLE` | `Hongkong HK · 移动版` | 同左 | 后端品牌设置优先（`/api/init/settings/`） |
| `VITE_APP_LOGO` | `/db_trans.png` | 同左 | 后端 Logo 优先 |
| `VITE_SIGN_IN_TEXT` | `港险 AI 智慧系统` | 同左 | 登录页主标题 |
| `VITE_DESKTOP_URL` | `http://localhost:8080` | `https://hkai.favor100.site` | “电脑版”跳转地址 |

品牌（标题 / Logo / Favicon）会在启动时读取后端 `/api/init/settings/`，
与桌面端共用同一个「品牌设置」，无需在移动端重复配置。

---

## 7. 与桌面端共用后端的说明

- 登录：`POST /api/login/`，密码先做 MD5；token 放在 `Authorization: JWT <token>`。
- 首次登录：`pwd_change_count === 0` → `POST /api/system/user/login_change_password/`（密码 MD5）。
- 普通改密：`PUT /api/system/user/change_password/`（明文旧/新密码，后端自行校验）。
- 用户信息：`GET /api/system/user/user_info/`。
- RAG：`GET /api/rag/products/`、`POST /api/rag/chat/stream/`（SSE）、`POST /api/rag/explain/`。
- 图文卡：`/api/cards/...`；文件分析：`/api/docai/...`；计划书：`/api/proposal/...`。

移动端与桌面端可以同时登录同一账号，互不影响（JWT 各自存本域 `localStorage`）。

---

## 8. 已知范围 / 后续可扩展

- 组织架构、飞书群推送、图文卡模板/公司维护等复杂管理功能当前引导到电脑版。
- 若需要移动端管理功能，可复用 `api/` 与 `views/` 的模式继续加页面。
- UI 文案当前为繁体中文；如需多语言，可引入 `vue-i18n` 并复用桌面端语言包。

# Emoera 项目接手文档

> 本文档面向**接手该项目继续开发/部署的开发者**，独立于 README（README 偏对外展示），记录架构、运行方式、配置、数据存储、安全设计、已知限制与常见操作，全部内容对照当前代码实际核对过。

- 仓库：`qifalab/emoera-tutorials`
- 技术栈：FastAPI（后端） + 原生 JS 单页（前端，零构建）
- 一句话定位：多渠道（社交媒体 / GitHub / 邮箱 RSS）消息聚合 + AI 每日速报 + 教程资源广场

---

## 1. 目录结构

```
emoera-daily-automation-aggregator/
├── backend/
│   ├── app/
│   │   ├── main.py                  # 应用入口：生命周期、CORS、限流、路由挂载、/uploads 下载
│   │   ├── config.py                # 全局配置（pydantic-settings，EMOERA_ 前缀）
│   │   ├── adapters/                # 渠道适配器（注册表 + 各类源）
│   │   │   ├── base.py              # 适配器基类
│   │   │   ├── registry.py          # 适配器注册表
│   │   │   ├── github.py            # GitHub 动态
│   │   │   ├── email_imap.py        # 邮箱 IMAP
│   │   │   └── social/              # 社交媒体（需 playwright）
│   │   │       ├── weibo.py
│   │   │       ├── xiaohongshu.py
│   │   │       ├── douyin.py
│   │   │       └── browser_adapter.py
│   │   ├── api/v1/                  # 路由层（详见第 8 节）
│   │   │   ├── auth.py              # 注册/登录/登出/me
│   │   │   ├── news.py              # 每日速报
│   │   │   ├── messages.py          # 消息聚合
│   │   │   ├── tasks.py             # 平台任务执行
│   │   │   ├── ai_router.py         # AI 模型榜单
│   │   │   ├── resources.py         # 教程资源（上传/列表/详情/编辑/下载计数）
│   │   │   ├── admin_resources.py   # 管理员审核
│   │   │   └── settings.py          # AI 设置读写/测试
│   │   ├── schemas/                 # Pydantic 模型
│   │   └── services/                # 业务逻辑
│   │       ├── ai_client.py         # OpenAI 兼容调用 + SSRF 校验（validate_base_url）
│   │       ├── link_safety.py       # 外链安全校验
│   │       ├── rate_limit.py        # 滑动窗口限流（按真实 IP）
│   │       ├── message_aggregator.py# 消息聚合（含 demo 数据）
│   │       ├── daily_brief.py       # AI 每日速报生成
│   │       ├── rss_fetcher.py       # RSS 抓取（依赖 feedparser）
│   │       ├── ai_model_fetcher.py  # AI 模型榜单抓取
│   │       ├── auth.py              # 账号系统（PBKDF2 密码哈希、令牌）
│   │       ├── store.py             # 内存存储（消息、任务记录）
│   │       ├── resource_store.py    # 资源元信息 + 附件落盘
│   │       ├── settings_store.py    # AI 设置 JSON 持久化
│   │       ├── scheduler.py         # APScheduler 定时任务
│   │       └── task_runner.py       # 任务执行器
│   │   └── data/                    # 运行时数据（已 gitignore，见第 6 节）
│   ├── Dockerfile                   # 生产镜像（含 playwright chromium）
│   ├── pyproject.toml               # 依赖/工具配置
│   └── .env                         # 本地配置（gitignore，不提交）
├── frontend/
│   ├── index.html                   # 单页入口
│   ├── main.js                      # 全部逻辑（hash 路由 + 视图渲染）
│   ├── styles.css
│   ├── assets/logo.svg
│   └── vendor/                      # 本地 vendored 依赖（不依赖 CDN）
│       ├── marked.min.js            # Markdown 解析
│       ├── purify.min.js            # DOMPurify XSS 过滤
│       ├── highlight.min.js         # 代码高亮
│       └── github(.dark).min.css    # 代码高亮主题
├── HANDOVER.md                      # 本文档
├── README.md                        # 对外展示
├── LICENSE                          # Apache 2.0
└── .gitignore
```

---

## 2. 快速启动

### 2.1 环境要求

- Python >= 3.11（当前用 3.13.12 的隔离 venv）
- 无需 Node；前端是纯静态文件，用任意静态服务器即可

### 2.2 安装依赖

```bash
# 1) 建 venv
python -m venv .venv
# Windows: .venv\Scripts\activate     Linux/macOS: source .venv/bin/activate

# 2) 安装
pip install -e "backend/.[dev]"   # 含 fastapi/uvicorn/httpx/apscheduler/playwright + dev(rff/pytest)
```

> ⚠️ **pyproject.toml 里漏了两个运行时依赖，必须手动补装**（否则启动会报错）：
>
> ```bash
> pip install feedparser python-multipart
> ```
>
> - `feedparser`：`rss_fetcher.py` 用到
> - `python-multipart`：`/api/v1/resources` 的 multipart 表单上传用到
>
> `playwright` 是**懒加载**（仅在社交媒体适配器函数内 import），demo 模式不装也能启动；真要用社交媒体需 `playwright install chromium`。

### 2.3 启动后端

> ⚠️ **务必带 `--no-proxy-headers`**。uvicorn 默认 `proxy_headers=True` 会信任 `X-Forwarded-For`，污染 `request.client.host`，导致限流可按伪造 XFF 头绕过。README 与 Dockerfile 均已内置该参数。

```bash
cd backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

### 2.4 启动前端

```bash
cd frontend
python -m http.server 8080 --bind 127.0.0.1
```

前端通过 `http://127.0.0.1:8000`（`main.js` 顶部 `API_BASE`）调后端；后端 CORS 已允许 `127.0.0.1:8080` / `localhost:8080` 等。

### 2.5 本地实际运行过的记录（备忘）

- venv 曾建在 `C:\Users\Kikiler\.workbuddy\binaries\python\envs\default`（隔离环境）
- 健康检查：`curl http://127.0.0.1:8000/api/health` → `{"status":"ok",...}`
- 交互式接口文档（自动生成）：`http://127.0.0.1:8000/docs`

---

## 3. 配置项（backend/.env，EMOERA_ 前缀）

完整清单见 `backend/.env.example`。关键项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `EMOERA_ENVIRONMENT` | development | 环境标识 |
| `EMOERA_CORS_ORIGINS` | 5173/8080/3000 | 逗号分隔的允许源 |
| `EMOERA_ENABLE_SCHEDULER` | false | 是否启用定时任务（APScheduler） |
| `EMOERA_DAILY_TASK_HOUR/MINUTE` | 9/0 | 定时任务触发时刻 |
| `EMOERA_AI_BASE_URL` | 空 | OpenAI 兼容接口（如 DeepSeek `https://api.deepseek.com/v1`） |
| `EMOERA_AI_MODEL` | gpt-4o-mini | 模型名 |
| `EMOERA_AI_API_KEY` | 空 | API key（**空则速报不可用**，其余功能不受影响） |
| `EMOERA_ADMIN_TOKEN` | 空 | 管理令牌（**公网部署必配**，保护 settings 写接口） |
| `EMOERA_ADMIN_INVITE_CODE` | 空 | 注册时填此码成为管理员；**留空则平台无管理员入口** |
| `EMOERA_ALLOW_PRIVATE` | false | 放行内网 base_url（本地 Ollama 调试用，默认禁内网防 SSRF） |
| `EMOERA_ENABLE_RATE_LIMIT` | true | 是否启用写操作限流 |
| `EMOERA_RATE_LIMIT_BURST` | 120 | 写操作每分钟每 IP 上限 |
| `EMOERA_MAX_BODY_BYTES` | 16777216 | 请求体大小上限（16MB；附件上传豁免） |
| `EMOERA_TRUST_PROXY` | false | 是否信任 XFF（仅可信反代后方才设为 true） |
| `EMOERA_WEIBO_*` 等 | 空 | 社交媒体凭据，留空 = demo 模式 |
| `EMOERA_GITHUB_TOKEN` | 空 | GitHub PAT，留空 = demo 数据 |
| `EMOERA_EMAIL_*` | 空 | IMAP 配置，留空 = demo 数据 |

**配置读取方式**：`pydantic-settings` 统一从 `EMOERA_` 前缀读取；运行时 AI 设置（base_url/model/api_key）可在网站「设置」页修改，**持久化到 `data/ai_settings.json`**（不是写回 .env），启动时自动加载进运行时。

---

## 4. 账号与权限模型

- **注册/登录**：`services/auth.py` + `api/v1/auth.py`，本地账号体系。
- **密码**：PBKDF2-HMAC-SHA256，120k 次迭代 + 每用户随机盐（`hashlib.pbkdf2_hmac`），不存明文。
- **管理员授予**：仅当注册时 `invite_code` 精确等于 `EMOERA_ADMIN_INVITE_CODE` 才设为 `admin`；未配置邀请码则**永远无法产生管理员**（安全默认）。⚠️ 注释里旧的「首个注册自动管理员」已废除，以代码为准。
- **令牌**：随机 hex（`secrets.token_hex(24)`），存 `data/tokens.json`（`{token: user_id}`），后端重启不失效；登出时删除。
- **登录防爆破**：按用户名内存限速，5 次失败锁 60 秒。

---

## 5. 数据存储（重要：哪些会丢，哪些不会）

| 数据 | 存储位置 | 持久化？ | 说明 |
|---|---|---|---|
| 消息聚合结果 / 任务记录 | `services/store.py` 内存字典 | ❌ 进程重启丢失 | 脚手架用内存存即可 |
| 用户 | `data/users.json` | ✅ | 已 gitignore |
| 登录令牌 | `data/tokens.json` | ✅ | 已 gitignore |
| 教程资源元信息 | `data/resources.json` | ✅ | 已 gitignore |
| 点赞/收藏/评论 | `data/interactions.json` | ✅ | 已 gitignore |
| AI 设置 | `data/ai_settings.json` | ✅ | 已 gitignore |
| 上传附件 | `data/uploads/` | ✅ | 已 gitignore，UUID 重命名 |

- 所有 JSON 写入均用「写临时文件 + `os.replace`」保证原子性。
- `store.py` 头部注释明确：若要持久化/多实例，可平滑替换为 SQLite（aiosqlite）或 Redis，接口不变。

---

## 6. 安全设计（不要回退的点）

1. **SSRF 防护**：`services/ai_client.py` 的 `validate_base_url` 做了多层校验——畸形 IP（`127.1`、`2130706433`、`0x7f000001`、`::ffff:127.0.0.1`）、保留段/未指定段、DNS 解析后地址、云元数据地址等；`link_safety.py` 复用同一套规则校验外链。
2. **外链安全**：`link_safety.py` 仅允许 http/https，拒绝 `javascript:`/`data:`/`file:`，拒绝 `.exe/.msi/.bat/.js` 等可执行/脚本下载后缀。
3. **限流**：`rate_limit.py` 滑动窗口，**默认只认真实 socket IP**，不信任 XFF（除非 `trust_proxy=true`）；配合 `--no-proxy-headers` 启动，杜绝 XFF 伪造绕过。
4. **请求体大小限制**：`main.py` 的 `BodySizeLimitMiddleware`，16MB 上限；`/api/v1/resources`（multipart 上传）豁免，文件大小由 `resource_store.MAX_FILE_SIZE`（200MB）独立校验。
5. **XSS**：前端 Markdown 渲染走 `marked → DOMPurify.sanitize() → innerHTML`；上传附件强制 `Content-Disposition: attachment` 下载（不内联渲染）；附件扩展名白名单**不含** `.svg/.html/.js/.xml`（防存储型 XSS）。
6. **路径穿越防护**：`/uploads/{filename}` 用白名单正则校验文件名；附件用 UUID 重命名。
7. **上传/编辑资源需要登录**；审核/触发任务等敏感操作需要 `admin` 角色。

### ⚠️ 已知安全弱点（接手者应尽快处理）

1. **令牌存 localStorage**（`main.js` 的 `TOKEN_KEY`/`setSession`），存在 XSS 被读风险。建议改为 **httpOnly Cookie**，并从后端 `set_cookie(..., httponly=True)`。
2. **`renderMarkdown` 的兜底路径未净化**：当 `window.marked` 未加载时退回 `linkify(md)`，该路径产出不经过 DOMPurify 就直接插入 DOM（`main.js` 约 92/99 行）。
3. **登录/令牌为明文 HTTP**：部署公网前**必须**套 HTTPS 反向代理（nginx/caddy），并保持 `trust_proxy=false` + `--no-proxy-headers` 的默认安全组合，除非确认在可信反代后方。

---

## 7. 前端架构

- 单文件 `main.js`，hash 路由 `#/{board}/{page}`，两大板块：
  - `daily`：每日速报，首页 `#/daily/home`，频道含 news / world / meme / github / ai_cloud / ai_models 等（`NAV.daily` / `HOME_ENTRIES` 定义）。
  - `tutorial`：教程平台，`platform / resources / upload / favorites / my_resources / login / profile / admin / edit / resource(detail)` 等页面。
- 路由处理：`parseHash()` 解析 → `route()` 分发 → 各 `render*` 视图函数。
- 依赖全部本地 vendor，不依赖 CDN（`index.html` 直接引 `vendor/*.js`）。
- 代码高亮主题 github.min.css / github-dark.min.css 按明暗主题用 JS 切换。
- API 基址：`main.js` 顶部 `API_BASE = http://127.0.0.1:8000`。

---

## 8. 后端 API 端点清单

所有路由挂载在 `/api/v1` 前缀下。

- **`/auth`**：`POST /register`、`POST /login`、`POST /logout`、`GET /me`
- **`/news`**：`GET /brief`、`POST /brief/refresh`、`GET /section/{category}`、`POST /section/{category}/refresh`
- **`/messages`**：`GET ""`、`POST ""`、`POST /refresh`（`/refresh` 需 admin）
- **`/tasks`**：`GET /config`、`POST /run`（需 admin）、`GET /runs/{run_id}`
- **`/ai-models`**：`GET ""`、`POST /refresh`、`GET /section/{category}`、`POST /section/{category}/refresh`
- **`/settings`**：`GET /providers`、`GET /ai`、`POST /ai`、`POST /ai/test`、`POST /ai/models`
- **`/resources`**：`GET ""`、`GET /categories`、`GET /favorites`、`GET /mine`、`GET /{id}`、`POST ""`（multipart 上传）、`PUT /{id}`（作者编辑，重置为待审）、`POST /{id}/download`
- **`/admin/resources`**：`GET /stats`、`GET /pending`、`POST /{id}/review`（approve/reject）
- **`/api/health`**：健康检查（不在 v1 前缀下）

资源上传为 **multipart 表单**，字段为 `title / description(Markdown 正文) / category / tags(逗号分隔) / link / image_url / file`（无独立的 `content` 字段，Markdown 正文放 `description`）。编辑接口 `PUT /{id}` 则是 JSON body，对应 `ResourceUpdate` schema（`tags` 为数组）。

---

## 9. 常见操作速查

- **查看全部真实路由**：`curl http://127.0.0.1:8000/openapi.json` 或直接打开 `/docs`。
- **注册管理员**：先在 `.env` 配 `EMOERA_ADMIN_INVITE_CODE=xxx`，再注册时填该邀请码。
- **上传资源后审核发布**：资源默认 `pending`，管理员 `POST /api/v1/admin/resources/{id}/review` `{"action":"approve"}` 后公开。
- **触发每日任务/刷新消息**：需 admin 令牌（`Authorization: Bearer <token>`）。

---

## 10. 部署要点（Docker + 生产）

- 后端已提供 `backend/Dockerfile`（python:3.12-slim + playwright chromium + `--no-proxy-headers`）。
- 构建镜像后，`uvicorn` 监听 `0.0.0.0:8000`。
- **必须**在镜像前方加 HTTPS 反向代理（nginx/caddy），否则登录与令牌明文传输。
- 生产环境务必设置：`EMOERA_ADMIN_TOKEN`、`EMOERA_ADMIN_INVITE_CODE`、`EMOERA_AI_API_KEY`。
- 反代时若用 XFF 且确认安全，才设 `EMOERA_TRUST_PROXY=true`；否则保持默认 `false`。
- 前端 `frontend/` 为纯静态，可直接由 nginx 托管，或将 `API_BASE` 改为反代后的域名。

---

## 11. 测试

- 测试用例位于 `backend/tests/`，用 `pytest` 运行：

```bash
cd backend && pytest
```

（历史上以 `asyncio_mode = "auto"` 跑通 3 个核心用例；改动后建议回归一遍。）

---

## 12. 已知限制 / 待办

1. **AI 速报依赖外部 AI 服务**：`EMOERA_AI_BASE_URL/API_KEY` 不配或不可达时，`/news/brief`、`/ai-models` 等接口会超时/失败（其余功能不受影响）。默认 base_url 是 `aiapi.emoera.com`（代码默认值），本机开发环境曾 502。
2. 前端令牌存 localStorage（安全弱点，见第 6 节），建议改 httpOnly Cookie。
3. `renderMarkdown` 无 marked 时的兜底路径未净化。
4. `pyproject.toml` 缺 `feedparser`、`python-multipart` 两个运行时依赖，建议补进 `dependencies`。
5. 消息与任务记录为内存态（进程重启丢失），多实例/持久化需替换 `store.py`。
6. 社交媒体渠道（微博/小红书/抖音）走 playwright 浏览器自动化，需账号凭据 + 已装 chromium，且平台改版后适配器可能失效。

---

*文档最后更新：对照当前代码核对，启动命令 / 配置 / 端点 / 存储 / 安全点均与代码一致。*

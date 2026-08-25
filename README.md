# Emoera Tutorials

Emoera Tutorials 是一个「能上传、能审核、能共享」的教程资源平台，同时内置 **AI 每日速报**——聚合时事 / 世界 / 新梗 / 云 / AI 模型等多频道资讯，并由 AI 自动生成摘要。

- 教程平台：用户上传教程 / 模型 / 资料 → 管理员审核 → 公开共享，带点赞 / 收藏 / 评论（楼中楼）/ 个人中心 / 管理后台。
- AI 每日速报：7 大频道 RSS 聚合 + AI 摘要，分国内 / 国外源。
- 富文本：Markdown 编辑器 + 代码高亮（自动识别语言，可手动切换）+ 图片插入 + 封面图。

目标开源仓库：[github.com/qifalab/emoera-tutorials](https://github.com/qifalab/emoera-tutorials)

## 功能特性

- **教程平台**：资源上传、管理员审核、公开共享，支持分类筛选、关键词搜索、多种排序（最新 / 最热 / 最多下载 / 最多点赞）。
- **账号体系**：本地注册 / 登录，PBKDF2 加盐哈希密码，令牌持久化（重启不掉线）；注册时携带邀请码即可成为管理员。
- **互动**：点赞、收藏、评论（支持楼中楼回复）、下载计数，全部实时统计。
- **管理后台**：数据仪表盘（用户 / 资源状态 / 互动总量 / 分类分布 / 下载排行）+ 待审核队列，一键通过 / 驳回。
- **Markdown 富文本**：正文支持标题 / 加粗 / 引用 / 列表 / 表格 / 图片 / 链接 / 代码块；上传与编辑页内置工具栏 + 实时预览。
- **代码块高亮**：highlight.js 自动识别语言，未指定时自动识别；渲染后可手动切换高亮语言，一键复制。
- **AI 每日速报**：时事 / 世界 / 新梗 / 云厂商 / 云原生 / AI 上云 / AI 模型推荐 7 大频道，RSS 抓取 + AI 摘要，未配 Key 自动回落原文模式。
- **明暗主题**：一键切换，代码高亮主题随明暗联动。
- **安全设计**：外链 SSRF 校验、上传文件白名单、XSS 过滤、请求限流、请求体上限（详见 [安全设计要点](#安全设计要点)）。

## 技术栈

- [FastAPI](https://fastapi.tiangolo.com/) + Pydantic v2 + pydantic-settings
- 前端：原生 HTML + JavaScript 单页应用（无框架、无构建步骤）
- [httpx](https://www.python-httpx.org/)（出站请求）
- [APScheduler](https://apscheduler.readthedocs.io/)（定时任务，默认关闭）
- [marked](https://marked.js.org/) + [highlight.js](https://highlightjs.org/) + [DOMPurify](https://github.com/cure53/DOMPurify)（Markdown 渲染三件套，本地 vendor）
- 存储：JSON 文件落盘（`backend/app/data/`），无数据库依赖

## 本地开发

### 环境要求

- Python 3.11 或更高版本
- 浏览器（可选，仅社交媒体适配器使用 Playwright）

### 安装依赖

```bash
cd backend
python -m pip install "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic-settings>=2.3" "httpx>=0.27" "apscheduler>=3.10"
```

### 配置环境变量

复制示例文件并按实际情况修改：

```bash
cp backend/.env.example backend/.env
```

必填变量（可选，不填则进入 demo 模式）：

- `EMOERA_AI_BASE_URL` / `EMOERA_AI_MODEL` / `EMOERA_AI_API_KEY`：AI 接口（OpenAI 兼容），不配 Key 则速报回落到原文模式
- `EMOERA_ADMIN_INVITE_CODE`：管理员邀请码，注册时填此码即成为管理员
- `EMOERA_GITHUB_TOKEN` / `EMOERA_EMAIL_IMAP_*` / `EMOERA_WEIBO_*` 等：各平台凭据，不配则 demo 模式

> 不要提交 `.env`、`backend/.env` 或任何包含真实密钥的环境文件。

### 启动后端

```bash
cd backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers
```

> ⚠️ 务必带 `--no-proxy-headers`：uvicorn 默认信任 `X-Forwarded-For`，否则攻击者伪造该头即可绕过限流。

健康检查：`http://127.0.0.1:8000/api/health` → `{"status":"ok",...}`

### 启动前端

```bash
cd frontend
python -m http.server 8080 --bind 127.0.0.1
```

打开 [http://127.0.0.1:8080](http://127.0.0.1:8080) 查看应用（默认进入速报首页，顶栏胶囊切换「AI 每日速报 / 教程平台」）。

### 运行测试

```bash
cd backend
python -m pytest tests/ -q
```

## 首次使用（管理员）流程

1. 在 `backend/.env` 设置 `EMOERA_ADMIN_INVITE_CODE=你的邀请码`。
2. 启动后端 + 前端，访问 `http://127.0.0.1:8080/index.html#/tutorial/login`。
3. 注册账号时填入邀请码 → 成为管理员。
4. 访问 `#/tutorial/admin`：上方是数据仪表盘，下面是审核队列。
5. 普通用户注册（不填邀请码）→ 上传资源 → 待审核 → 管理员通过 → 资源中心公开可见。

## 目录结构

```
emoera-tutorials/
├── README.md
├── .gitignore
├── backend/
│   ├── pyproject.toml             # 依赖声明
│   ├── .env.example               # 环境变量示例（无真实密钥）
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                # FastAPI 入口：CORS、限流、请求体上限、路由挂载
│   │   ├── config.py              # Settings：EMOERA_ 前缀环境变量 → 单例 settings
│   │   ├── adapters/              # 平台适配器（社交媒体/GitHub/邮件，demo 模式兜底）
│   │   ├── api/v1/                # 全部路由
│   │   │   ├── auth.py            #   注册/登录/登出/me
│   │   │   ├── resources.py       #   资源：上传/列表/详情/编辑/点赞/收藏/评论/下载
│   │   │   ├── admin_resources.py #   管理后台：统计/审核队列/审核
│   │   │   ├── news.py            #   速报：/brief、/section/{category}
│   │   │   ├── ai_router.py       #   AI 模型推荐
│   │   │   ├── settings.py        #   AI 设置 + 管理令牌鉴权
│   │   │   ├── tasks.py           #   每日任务
│   │   │   └── messages.py        #   消息汇总
│   │   ├── schemas/               # Pydantic 模型
│   │   ├── services/              # 业务逻辑（auth/resource_store/ai_client/rate_limit/...）
│   │   └── data/                  # 运行时数据（全部 gitignore）
│   └── tests/                     # pytest
└── frontend/                      # 纯静态站点
    ├── index.html                 # 应用壳
    ├── main.js                    # hash 路由 + 全部视图逻辑
    ├── styles.css                 # 设计系统
    └── vendor/                    # marked/highlight.js/DOMPurify（本地化）
```

## 后端 API 一览

所有接口前缀 `/api/v1`。完整表格见下方。

### 账号 `/auth`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/auth/register` | 注册（username/password/invite_code），返回 token+user |
| POST | `/auth/login` | 登录，返回 token+user |
| POST | `/auth/logout` | 登出（需 Bearer） |
| GET | `/auth/me` | 当前用户（需 Bearer） |

### 资源 `/resources`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/resources` | 上传（multipart，需登录） |
| GET | `/resources` | 公开列表 `?category=&q=&sort=` |
| GET | `/resources/categories` | 分类计数 |
| GET | `/resources/favorites` | 我的收藏（需登录） |
| GET | `/resources/mine` | 我的上传（需登录） |
| GET | `/resources/{id}` | 详情（含评论 + 点赞/收藏态） |
| PUT | `/resources/{id}` | 编辑（仅作者本人，重置为待审核） |
| POST | `/resources/{id}/download` | 下载计数 +1 |
| POST | `/resources/{id}/like` · `/favorite` | 切换点赞/收藏（需登录） |
| GET/POST | `/resources/{id}/comments` | 评论列表 / 发表评论（楼中楼） |

### 管理后台 `/admin/resources`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/admin/resources/stats` | 仪表盘统计（需管理员） |
| GET | `/admin/resources/pending` | 待审核+已驳回（需管理员） |
| POST | `/admin/resources/{id}/review` | 审核 `{action: approve\|reject, note}` |

### 其他

- 速报：`GET /news/brief`、`GET /news/section/{category}`（refresh=true 强制重抓）
- AI 模型：`GET /ai-models`、`GET /ai-models/section/{category}`
- 设置：`GET/POST /settings/ai`、`POST /settings/ai/test`、`POST /settings/ai/models`、`GET /settings/providers`
- 任务：`GET /tasks/config`、`POST /tasks/run`（需管理员）、`GET /tasks/runs/{id}`（需管理员）
- 消息：`GET /messages`、`POST /messages/refresh`（需管理员）
- 文件：`GET /uploads/{filename}`（强制 attachment + 文件名白名单）

## 环境变量

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `EMOERA_AI_BASE_URL` | AI 接口地址（OpenAI 兼容） | 空 |
| `EMOERA_AI_MODEL` | 模型名 | `gpt-4o-mini` |
| `EMOERA_AI_API_KEY` | AI API Key | 空 |
| `EMOERA_ADMIN_INVITE_CODE` | 管理员邀请码 | 空（空则无法创建管理员） |
| `EMOERA_ADMIN_TOKEN` | 设置接口管理令牌 | 空（空则放行） |
| `EMOERA_ALLOW_PRIVATE` | 放行内网 base_url（本地调试） | `false` |
| `EMOERA_TRUST_PROXY` | 信任 X-Forwarded-For（仅在可信反代后开启） | `false` |
| `EMOERA_ENABLE_RATE_LIMIT` | 启用写操作限流 | `true` |
| `EMOERA_RATE_LIMIT_BURST` | 写操作每分钟每 IP 上限 | `120` |
| `EMOERA_MAX_BODY_BYTES` | 请求体大小上限（字节） | `16777216`（16MB） |
| `EMOERA_ENABLE_SCHEDULER` | 启用定时任务 | `false` |
| `EMOERA_DAILY_TASK_HOUR/MINUTE` | 定时任务触发时刻 | 9:00 |
| `EMOERA_GITHUB_TOKEN` | GitHub 通知 token | 空（demo 模式） |
| `EMOERA_WEIBO_*` / `EMOERA_XIAOHONGSHU_*` / `EMOERA_DOUYIN_*` | 社交媒体凭据 | 空（demo 模式） |
| `EMOERA_EMAIL_IMAP_*` | IMAP 邮箱凭据 | 空（demo 模式） |

> ⚠️ 所有 `EMOERA_` 前缀变量必须通过 pydantic-settings 的 `settings` 对象读取（`config.py`），不要用 `os.getenv("EMOERA_*")`——后者读不到 `.env` 文件内容。

## 安全设计要点

1. **密码**：PBKDF2-HMAC-SHA256 加盐哈希（120k 迭代），不存明文；登录按用户名限速（5 次失败锁 60s）。
2. **管理员**：仅注册时携带 `EMOERA_ADMIN_INVITE_CODE` 才成为 admin；未配置则无管理员入口（无"首个注册即管理员"提权回退）。
3. **上传文件安全**：扩展名白名单（不含 svg/html/xml/js 等脚本类型）；文件名 UUID 重命名；流式分块落盘（不整读内存）；下载强制 `Content-Disposition: attachment`；路径穿越防护。
4. **SSRF 防护**：禁止内网/环回/链路本地/云元数据/保留地址，并拦截短式/十进制/十六进制/IPv4-mapped 等伪装 IP（`127.1`、`2130706433`、`0x7f000001`、`::ffff:127.0.0.1`）。
5. **API Key 脱敏**：设置接口只回显 `前4...后4`。
6. **XSS 防护**：用户内容转义渲染；Markdown 走 `marked → highlight.js → DOMPurify` 三道过滤。
7. **限流防绕过**：写操作按 IP 限流，登录/注册更严；必须用 `--no-proxy-headers` 启动（详见上文）。
8. **请求体上限**：默认 16MB，附件上传接口豁免（文件大小独立校验）。

## License

[Apache License 2.0](LICENSE)

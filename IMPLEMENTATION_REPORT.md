# Emoera 安全修复与功能升级报告

> 完成时间：2026-08-28 · 范围：安全漏洞修复 + 前端 UI 优化 + 评论/通知/搜索/分类/权限等全量改造

---

## 一、安全修复（最高优先级）

| 问题 | 修复方案 | 涉及文件 |
|------|---------|---------|
| 令牌存 localStorage，XSS 可窃取 | 改 **httpOnly Cookie**（`emoera_token`），前端不再存 token，fetch 统一 `credentials:include` | `backend/app/api/v1/auth.py`、`frontend/main.js` |
| 令牌永不过期 | 加 **TTL（默认 168 小时）**，`EMOERA_TOKEN_TTL_HOURS` 可调，0=永久；tokens.json 升级为 `{token:{uid,ts}}` 并兼容旧格式 | `backend/app/services/auth.py`、`config.py` |
| 令牌解析身份错乱（cookie 优先于 Bearer 头） | `_resolve_token` 改为 **Authorization 头优先** | `backend/app/api/v1/auth.py` |
| `renderMarkdown` 兜底路径未净化 | marked/DOMPurify 任一缺失即退回纯文本链接化，绝不注入原始 HTML | `frontend/main.js` |
| 依赖缺失 | 补 `python-multipart`、`feedparser` | `backend/pyproject.toml` |

## 二、教程页图片显示失败修复

根因：正文/封面图用相对路径 `/uploads/xxx` 指向后端，前端零构建跨端口时 404。

- 后端新增 `/uploads/inline/{filename}`：仅位图（png/jpg/jpeg/gif/webp/bmp）内联预览，SVG/HTML 等仍强制 attachment 下载（防存储型 XSS）。
- 前端 `resolveMediaUrl` / `absolutizeImages` 把相对路径补全为后端地址，并加 `referrerpolicy="no-referrer"` 破部分图床防盗链。

## 三、功能清单

### 1. 评论系统增强
- 评论**点赞**（`comment_likes`）+ 按**时间/热度**排序
- 显示评论者**头像**（哈希色块）
- 点击名字/头像跳转**个人主页**
- 评论者本人 + 管理员可**删评**（级联删回复）
- **屏蔽发言者**：双方互相无法评论、看主页、私信

### 2. 个人主页
- `#/tutorial/user?id=xx` 公开主页：资料、签名、上传/获赞/被收藏/评论统计
- 私信、屏蔽入口

### 3. 通知中心 + 私信 + 通知设置
- 头像左侧通知按钮 + **未读角标**（轮询）
- `#/tutorial/notifications`：全部/未读/私信/屏蔽名单/通知设置
- 通知类型：`xxx 赞了你的评论`、`xxx 回复了你的评论/帖子`、管理员删帖系统通知（含原因）
- 私信会话列表 + 聊天窗

### 4. 删帖权限
- 作者本人 + 管理员可删帖
- **管理员删帖带原因 → 系统通知作者**

### 5. 资源分类系统
- 上传/编辑资源分类改**固定下拉选项**（默认：教程/模型/资料/工具/数据集）
- 管理员后台可**增删分类**（`admin/resources/categories`），上传时后端兜底校验

### 6. 搜索功能
- 顶栏**全局搜索**（输入防抖 + 建议下拉，回车跳全站搜索页）
- `#/tutorial/search`：关键词 + 分类 + 四种排序（最新/最热/最多下载/最多点赞）

### 7. 设置页分栏
- `#/tutorial/settings`：AI 设置 / 隐私设置 / 通知偏好 / 账户设置 四栏
- AI 配置从弹窗改为内嵌面板（保留原测试/获取模型/保存逻辑）

### 8. UI 导航重构
- 大按钮改**方形紧凑按钮置顶**（图标+文字）
- 当前展示页对应按钮**变蓝**（Bilibili `bg-primary` 风）
- 个人页移至**右上角**（通知按钮在其左）

## 四、验证结果

- 后端全部 `py_compile` 通过，前端 `node --check` 通过。
- TestClient 端到端 **8 项全部 PASS**：身份解析、评论创建、评论通知、点赞通知、热度排序、屏蔽私信拦截(403)、屏蔽主页拦截(403)、作者删帖。
- 补装依赖 `python-multipart`、`feedparser` 到隔离 venv 验证可用。

## 五、后续建议

1. 公网部署务必配置 `EMOERA_ADMIN_INVITE_CODE`（否则无管理员入口）与 `EMOERA_ADMIN_TOKEN`（保护 AI 设置接口）。
2. 建议配 HTTPS 反代，生产环境 `trust_proxy=True` 需仅在可信反代后开启。
3. 数据文件（users/tokens/resources/interactions/notifications/categories）位于 `backend/app/data/`，已被 gitignore。

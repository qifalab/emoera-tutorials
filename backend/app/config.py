"""应用配置（基于 pydantic-settings，统一从 EMOERA_ 前缀的环境变量读取）。

为什么集中在这里：
- 所有平台凭据只通过环境变量注入，仓库内不保留任何明文账号密码；
- 没有凭据时，各适配器自动进入 demo 模式，保证脚手架开箱即跑。
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置。默认值即可让项目在 demo 模式下运行。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="EMOERA_",
        extra="ignore",
    )

    # 通用
    app_name: str = "Emoera Daily Automation Aggregator"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080,http://localhost:3000,http://127.0.0.1:3000"

    # 定时任务（默认关闭，避免无感知地在后台执行）
    enable_scheduler: bool = False
    daily_task_hour: int = 9
    daily_task_minute: int = 0

    # 社交媒体（浏览器自动化，留空 = demo 模式）
    weibo_username: str = ""
    weibo_password: str = ""
    xiaohongshu_username: str = ""
    xiaohongshu_password: str = ""
    douyin_username: str = ""
    douyin_password: str = ""

    # GitHub（官方 API，推荐用 token）
    github_token: str = ""

    # AI 每日速报（OpenAI 兼容接口）
    ai_base_url: str = ""
    ai_model: str = "gpt-4o-mini"
    ai_api_key: str = ""

    # 安全：设置管理令牌（公网部署时建议配置，保护设置接口）
    admin_token: str = ""

    # 安全：设为 True 放行内网 base_url（本地调试 Ollama 用，默认禁止内网防 SSRF）
    allow_private: bool = False

    # 安全：管理员邀请码（注册时携带此码即成为管理员；留空则无法创建管理员）
    admin_invite_code: str = ""

    # 安全：登录令牌有效期（小时）。0 = 永不过期（不推荐公网开启）。
    # 令牌默认 7 天过期一次，过期后用户需重新登录，避免令牌泄露被长期滥用。
    token_ttl_hours: int = 168

    # 安全：基础抗 DDoS / 滥用
    # 每个客户端 IP 在窗口期内的最大请求数（写操作路径，如登录/注册/上传/评论）
    rate_limit_per_minute: int = 60
    rate_limit_burst: int = 120
    # 是否启用全局限流（关掉可完全旁路）
    enable_rate_limit: bool = True
    # 请求体大小上限（字节，默认 16MB；上传附件走 streaming，不受此限）
    max_body_bytes: int = 16 * 1024 * 1024
    # 是否信任 X-Forwarded-For 头（仅部署在可信反向代理后方时开启）。
    # 默认关闭：否则攻击者伪造 XFF 可完全绕过限流并造成内存泄漏。
    trust_proxy: bool = False

    # 邮件（IMAP）
    email_imap_host: str = ""
    email_imap_port: int = 993
    email_username: str = ""
    email_password: str = ""
    email_mailbox: str = "INBOX"
    email_max: int = 20


@lru_cache
def get_settings() -> Settings:
    """返回单例配置（避免重复解析环境变量）。"""
    return Settings()


settings = get_settings()

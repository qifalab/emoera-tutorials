"""每日速报相关数据结构。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NewsItem(BaseModel):
    """一条新闻/动态/新梗条目（来自 RSS 或摘要）。"""

    title: str
    summary: str = ""        # RSS 原文摘要（回落用）
    summary_ai: str = ""     # 逐条 AI 总结（未配置 Key / 模型拒答时为空）
    url: Optional[str] = None
    source: str = ""
    published_at: Optional[datetime] = None
    category: str = "news"  # news / world / meme
    tags: list[str] = Field(default_factory=list)


class BriefSection(BaseModel):
    """速报的一个板块：时事 / 世界动态 / 近日新梗。"""

    key: str  # news / world / meme
    title: str
    summary: str = ""  # AI 生成的板块总结
    items: list[NewsItem] = Field(default_factory=list)
    ai_comment: str = ""  # AI 对板块的点评


class DailyBrief(BaseModel):
    """一次完整的每日速报。"""

    generated_at: datetime = Field(default_factory=datetime.now)
    title: str = "今日速报"
    overview: str = ""  # AI 生成的整体导语
    sections: list[BriefSection] = Field(default_factory=list)
    using_ai: bool = False
    ai_note: str = ""  # AI 使用说明（如未配置 key 时提示）


class AiSettings(BaseModel):
    """AI 配置（对外展示用，key 已脱敏）。"""

    base_url: str
    model: str
    api_key_set: bool = False
    api_key_masked: str = ""
    admin_token_required: bool = False  # 是否已启用管理令牌鉴权


class AiSettingsInput(BaseModel):
    """AI 配置的写入请求。

    base_url / model / api_key 用 None 表示"不修改"，用 "" 表示"清空"。
    """

    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    admin_token: str = ""  # 管理令牌，修改配置时必填（若后端已启用）


class AiTestResult(BaseModel):
    """测试 AI 连接的结果。"""

    ok: bool
    message: str
    model: str = ""


class AiModelsResult(BaseModel):
    """自动获取的模型列表。"""

    ok: bool
    models: list[str] = Field(default_factory=list)
    message: str = ""

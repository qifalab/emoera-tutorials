"""消息相关数据结构。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    """一条聚合后的消息，来源可能是社交媒体站内信 / GitHub 通知 / 邮件。"""

    id: str
    source: str  # weibo / xiaohongshu / douyin / github / email
    title: str
    body: str = ""
    url: Optional[str] = None
    author: Optional[str] = None
    priority: int = Field(default=3, ge=1, le=5)  # 1 最低，5 最高
    received_at: datetime
    tags: list[str] = Field(default_factory=list)
    # 跨来源去重时使用的稳定键（同一平台内用 id，跨平台用内容哈希）
    dedupe_key: Optional[str] = None

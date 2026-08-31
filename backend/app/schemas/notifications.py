"""通知 / 私信 / 用户关系（屏蔽）相关数据结构。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class NotificationItem(BaseModel):
    """一条系统/互动通知。"""

    id: str
    type: str = "system"           # like_comment / reply_comment / like_post / reply_post / system
    actor_id: str = ""
    actor_name: str = ""
    target_id: str = ""
    content: str = ""
    link: str = ""
    is_read: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class NotificationList(BaseModel):
    notifications: list[NotificationItem] = Field(default_factory=list)
    unread: int = 0


class MessageItem(BaseModel):
    """一条私信。"""

    id: str
    from_id: str = ""
    from_name: str = ""
    to_id: str = ""
    to_name: str = ""
    content: str = ""
    is_read: bool = False
    created_at: datetime = Field(default_factory=datetime.now)


class MessageSend(BaseModel):
    """发送私信。"""

    to_id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=2000)


class ConversationPeer(BaseModel):
    """私信会话方摘要。"""

    peer_id: str
    peer_name: str
    unread: int = 0
    last_content: str = ""
    last_at: Optional[datetime] = None


class UserRelation(BaseModel):
    """用户关系（是否屏蔽中）。"""

    blocked: bool = False


class BlockRequest(BaseModel):
    """屏蔽 / 取消屏蔽请求。"""

    user_id: str = Field(min_length=1)

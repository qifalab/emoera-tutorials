"""消息汇总相关接口。"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.v1.auth import get_admin_user
from app.schemas.messages import Message
from app.schemas.tutorial import UserPublic
from app.services.message_aggregator import aggregate
from app.services.store import store

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("", response_model=list[Message])
async def list_messages(source: Optional[str] = Query(None)) -> list[Message]:
    """返回已聚合（去重+排序）的消息，可按来源过滤。"""
    messages = store.get_messages()
    if source:
        messages = [m for m in messages if m.source == source]
    return messages


@router.post("", response_model=list[Message])
@router.post("/refresh", response_model=list[Message])
async def refresh_messages(
    user: UserPublic = Depends(get_admin_user),
) -> list[Message]:
    """重新从各平台拉取并聚合并返回最新消息。仅管理员可触发（消耗抓取资源）。"""
    return await aggregate(refresh=True)

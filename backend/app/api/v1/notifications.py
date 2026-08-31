"""通知中心 + 私信 + 用户关系（屏蔽）路由。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.schemas.notifications import (
    BlockRequest,
    ConversationPeer,
    MessageItem,
    MessageSend,
    NotificationItem,
    NotificationList,
)
from app.schemas.tutorial import UserPublic
from app.services import auth as auth_service
from app.services import notifications as notif
from app.services import user_service

router = APIRouter(prefix="/notifications", tags=["notifications"])
router_user = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# 通知
# ---------------------------------------------------------------------------
@router.get("", response_model=NotificationList)
async def list_notifications(
    unread: str = "",
    user: UserPublic = Depends(get_current_user),
) -> NotificationList:
    """我的通知列表。?unread=1 只看未读。"""
    items = notif.list_notifications(user.id, unread_only=(unread == "1"))
    return NotificationList(
        notifications=[NotificationItem(**n) for n in items],
        unread=notif.unread_count(user.id),
    )


@router.post("/read")
async def read_all(user: UserPublic = Depends(get_current_user)):
    """全部标记已读。"""
    notif.mark_all_read(user.id)
    return {"ok": True, "unread": notif.unread_count(user.id)}


@router.post("/read/{notif_id}")
async def read_one(notif_id: str, user: UserPublic = Depends(get_current_user)):
    """单条标记已读。"""
    notif.mark_read(user.id, notif_id)
    return {"ok": True}


@router.get("/unread-count")
async def unread_count(user: UserPublic = Depends(get_current_user)):
    """未读通知 + 私信总数（角标轮询用）。"""
    return {"unread": notif.unread_count(user.id)}


# ---------------------------------------------------------------------------
# 私信
# ---------------------------------------------------------------------------
@router.get("/messages/peers", response_model=list[ConversationPeer])
async def list_peers(user: UserPublic = Depends(get_current_user)):
    """私信会话方列表。"""
    peers = notif.conversation_peers(user.id)
    out = []
    for p in peers:
        msgs = [
            m for m in notif.list_messages(user.id)
            if (m["from_id"] == p["peer_id"] and m["to_id"] == user.id) or
               (m["from_id"] == user.id and m["to_id"] == p["peer_id"])
        ]
        unread = sum(1 for m in msgs if m["to_id"] == user.id and not m["is_read"])
        last = msgs[-1] if msgs else None
        out.append(ConversationPeer(
            peer_id=p["peer_id"],
            peer_name=p["peer_name"],
            unread=unread,
            last_content=(last or {}).get("content", ""),
            last_at=(last or {}).get("created_at"),
        ))
    out.sort(key=lambda x: x.last_at or "", reverse=True)
    # 复合对象转 dict 返回（FastAPI 自动处理）
    return out


@router.get("/messages/{peer_id}", response_model=list[MessageItem])
async def list_messages_with(peer_id: str, user: UserPublic = Depends(get_current_user)):
    """与某人的全部私信。"""
    notif.mark_messages_read(user.id, peer_id)
    msgs = [
        m for m in notif.list_messages(user.id)
        if (m["from_id"] == peer_id and m["to_id"] == user.id) or
           (m["from_id"] == user.id and m["to_id"] == peer_id)
    ]
    return [MessageItem(**m) for m in msgs]


@router.post("/messages", response_model=MessageItem)
async def send_message(body: MessageSend, user: UserPublic = Depends(get_current_user)):
    """发私信。"""
    target = auth_service.get_user_by_id(body.to_id)
    if not target:
        raise HTTPException(status_code=404, detail="对方用户不存在")
    result = notif.send_message(
        from_id=user.id, from_name=user.username,
        to_id=target["id"], to_name=target["username"],
        content=body.content.strip(),
    )
    if result.get("error"):
        raise HTTPException(status_code=403, detail=result["error"])
    return MessageItem(**result["message"])


# ---------------------------------------------------------------------------
# 屏蔽
# ---------------------------------------------------------------------------
@router.post("/blocks", response_model=dict)
async def block_user(body: BlockRequest, user: UserPublic = Depends(get_current_user)):
    """屏蔽用户。"""
    notif.block_user(user.id, body.user_id)
    return {"ok": True, "blocked": True}


@router.delete("/blocks/{blocked_id}")
async def unblock_user(blocked_id: str, user: UserPublic = Depends(get_current_user)):
    """取消屏蔽。"""
    notif.unblock_user(user.id, blocked_id)
    return {"ok": True, "blocked": False}


@router.get("/blocks", response_model=list)
async def list_blocks(user: UserPublic = Depends(get_current_user)):
    """我屏蔽的用户列表。"""
    return [{"user_id": u, "username": auth_service.get_username(u)} for u in notif.list_blocks(user.id)]


@router.get("/relation/{other_id}", response_model=dict)
async def relation(other_id: str, user: UserPublic = Depends(get_current_user)):
    """查询我与某人的屏蔽关系。"""
    return {"blocked": notif.is_blocked_either(user.id, other_id)}


# ---------------------------------------------------------------------------
# 用户主页
# ---------------------------------------------------------------------------
@router_user.get("/{user_id}/profile")
async def user_profile(user_id: str, me: UserPublic | None = Depends(get_current_user_optional)):
    """公开用户主页：资料 + 统计。被屏蔽则拒看（非管理员）。"""
    prof = user_service.get_profile(user_id)
    if not prof:
        raise HTTPException(status_code=404, detail="用户不存在")
    if me and notif.is_blocked_either(me.id, user_id):
        raise HTTPException(status_code=403, detail="你与对方已互相屏蔽，无法查看主页")
    stats = user_service.user_stats(user_id)
    return {
        "user": prof,
        "stats": stats,
        "blocked_by_me": bool(me and user_id in notif.list_blocks(me.id)),
    }


@router_user.patch("/me/profile")
async def update_my_profile(body: dict, user: UserPublic = Depends(get_current_user)):
    """更新我的资料（bio / 隐私与通知偏好）。"""
    prof = user_service.update_profile(user.id, body)
    return {"profile": prof}


@router_user.get("/me/profile")
async def get_my_profile(user: UserPublic = Depends(get_current_user)):
    """我的完整资料。"""
    return {"user": user_service.get_profile(user.id)}

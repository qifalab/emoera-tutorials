"""通知 + 私信系统：持久化到 notifications.json。

数据模型：
- notifications.json 结构：
    {
      "notifications": [ {id, user_id, type, actor_id, actor_name, target_id,
                          content, link, is_read, created_at}, ... ],
      "messages": [ {id, thread_id, from_id, from_name, to_id, to_name,
                     content, is_read, created_at}, ... ],
      "blocks": [ {blocker_id, blocked_id}, ... ]  # 双向屏蔽关系
    }

通知类型 type：
- like_post / reply_post（别人赞/回复了我的帖子？资源无帖子概念，此处资源即"帖子"）
- like_comment / reply_comment（别人赞/回复了我的评论）
- system（管理员删帖通知，带原因）

屏蔽规则：A 屏蔽 B 后，A 与 B 互相不能评论对方的帖子、查看对方个人页、互发私信。
"""

import json
import os
import secrets
import threading
from datetime import datetime
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
FILE = os.path.join(DATA_DIR, "notifications.json")

_LOCK = threading.Lock()


def _load() -> dict:
    try:
        with open(FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"notifications": [], "messages": [], "blocks": []}


def _save(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FILE)


def _now() -> str:
    return datetime.now().isoformat()


# ---------------------------------------------------------------------------
# 通知
# ---------------------------------------------------------------------------
def notify(
    *,
    user_id: str,
    type_: str,
    actor_id: str = "",
    actor_name: str = "",
    target_id: str = "",
    content: str = "",
    link: str = "",
) -> None:
    """给 user_id 发一条通知（本人不给自己发）。"""
    if not user_id or user_id == actor_id:
        return
    with _LOCK:
        data = _load()
        data.setdefault("notifications", []).append({
            "id": secrets.token_hex(8),
            "user_id": user_id,
            "type": type_,
            "actor_id": actor_id,
            "actor_name": actor_name,
            "target_id": target_id,
            "content": content,
            "link": link,
            "is_read": False,
            "created_at": _now(),
        })
        _save(data)


def list_notifications(user_id: str, unread_only: bool = False) -> list:
    with _LOCK:
        data = _load()
    out = [n for n in data.get("notifications", []) if n.get("user_id") == user_id]
    if unread_only:
        out = [n for n in out if not n.get("is_read")]
    out.sort(key=lambda n: n.get("created_at", ""), reverse=True)
    return out


def unread_count(user_id: str) -> int:
    with _LOCK:
        data = _load()
    return sum(
        1 for n in data.get("notifications", [])
        if n.get("user_id") == user_id and not n.get("is_read")
    ) + sum(
        1 for m in data.get("messages", [])
        if m.get("to_id") == user_id and not m.get("is_read")
    )


def mark_all_read(user_id: str) -> None:
    with _LOCK:
        data = _load()
        for n in data.get("notifications", []):
            if n.get("user_id") == user_id:
                n["is_read"] = True
        _save(data)


def mark_read(user_id: str, notif_id: str) -> None:
    with _LOCK:
        data = _load()
        for n in data.get("notifications", []):
            if n.get("id") == notif_id and n.get("user_id") == user_id:
                n["is_read"] = True
        _save(data)


# ---------------------------------------------------------------------------
# 私信
# ---------------------------------------------------------------------------
def send_message(from_id: str, from_name: str, to_id: str, to_name: str, content: str) -> dict:
    """发送私信。被屏蔽则拒绝（返回 error）。"""
    if is_blocked_either(from_id, to_id):
        return {"error": "你与对方已互相屏蔽，无法私信"}
    with _LOCK:
        data = _load()
        msg = {
            "id": secrets.token_hex(8),
            "from_id": from_id,
            "from_name": from_name,
            "to_id": to_id,
            "to_name": to_name,
            "content": content,
            "is_read": False,
            "created_at": _now(),
        }
        data.setdefault("messages", []).append(msg)
        _save(data)
    return {"message": msg}


def list_messages(user_id: str) -> list:
    """返回与 user_id 相关的全部私信（按时间正序，含双方）。"""
    with _LOCK:
        data = _load()
    out = [
        m for m in data.get("messages", [])
        if m.get("from_id") == user_id or m.get("to_id") == user_id
    ]
    out.sort(key=lambda m: m.get("created_at", ""))
    return out


def mark_messages_read(user_id: str, peer_id: str) -> None:
    """把某对话方发给我的消息标记为已读。"""
    with _LOCK:
        data = _load()
        for m in data.get("messages", []):
            if m.get("from_id") == peer_id and m.get("to_id") == user_id:
                m["is_read"] = True
        _save(data)


def conversation_peers(user_id: str) -> list[dict]:
    """返回与我私信过的所有对话方 + 最后一条消息摘要（供私信列表）。"""
    msgs = list_messages(user_id)
    peers: dict[str, dict] = {}
    for m in msgs:
        peer = m["to_id"] if m["from_id"] == user_id else m["from_id"]
        peer_name = m["to_name"] if m["from_id"] == user_id else m["from_name"]
        peers.setdefault(peer, {"peer_id": peer, "peer_name": peer_name, "last": None})
        peers[peer]["last"] = m
    out = list(peers.values())
    out.sort(key=lambda p: p["last"].get("created_at", "") if p["last"] else "", reverse=True)
    return out


# ---------------------------------------------------------------------------
# 屏蔽
# ---------------------------------------------------------------------------
def block_user(blocker_id: str, blocked_id: str) -> None:
    if blocker_id == blocked_id:
        return
    with _LOCK:
        data = _load()
        blocks = data.get("blocks", [])
        if not any(b.get("blocker_id") == blocker_id and b.get("blocked_id") == blocked_id for b in blocks):
            blocks.append({"blocker_id": blocker_id, "blocked_id": blocked_id})
        data["blocks"] = blocks
        _save(data)


def unblock_user(blocker_id: str, blocked_id: str) -> None:
    with _LOCK:
        data = _load()
        data["blocks"] = [
            b for b in data.get("blocks", [])
            if not (b.get("blocker_id") == blocker_id and b.get("blocked_id") == blocked_id)
        ]
        _save(data)


def _blocked_pairs() -> set:
    with _LOCK:
        data = _load()
    return {
        (b.get("blocker_id"), b.get("blocked_id"))
        for b in data.get("blocks", [])
    }


def is_blocked_either(a_id: str, b_id: str) -> bool:
    """A 屏蔽 B 或 B 屏蔽 A，任一方向即视为互相屏蔽。"""
    if not a_id or not b_id:
        return False
    pairs = _blocked_pairs()
    return (a_id, b_id) in pairs or (b_id, a_id) in pairs


def list_blocks(user_id: str) -> list:
    """我屏蔽的所有用户。"""
    with _LOCK:
        data = _load()
    return [b.get("blocked_id") for b in data.get("blocks", []) if b.get("blocker_id") == user_id]


def remove_block(blocker_id: str, blocked_id: str) -> None:
    unblock_user(blocker_id, blocked_id)

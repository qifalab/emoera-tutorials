"""用户服务：个人主页数据聚合、个人资料（签名/隐私设置）。

用户资料字段持久化到 users.json 的 profile 子字段：
    profile: {bio: str, show_email: bool, show_favorites: bool, notify_like: bool, notify_reply: bool}
"""

import json
import os
import threading
from datetime import datetime
from typing import Optional

from app.services import auth as auth_service

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

_LOCK = threading.Lock()


def _load_users() -> dict:
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save_users(users: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = USERS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)
    os.replace(tmp, USERS_FILE)


def get_profile(user_id: str) -> dict:
    """获取某用户的资料（附加账号信息）。"""
    users = _load_users()
    for u in users.values():
        if u.get("id") == user_id:
            prof = u.get("profile") or {}
            return {
                "id": u["id"],
                "username": u["username"],
                "role": u.get("role", "user"),
                "created_at": u.get("created_at", ""),
                "profile": prof,
            }
    return {}


def get_profile_by_username(username: str) -> Optional[dict]:
    users = _load_users()
    for u in users.values():
        if u.get("username") == username:
            prof = u.get("profile") or {}
            return {
                "id": u["id"],
                "username": u["username"],
                "role": u.get("role", "user"),
                "created_at": u.get("created_at", ""),
                "profile": prof,
            }
    return None


def update_profile(user_id: str, updates: dict) -> Optional[dict]:
    """更新 profile 字段（白名单）。返回更新后的 profile。"""
    allowed = {"bio", "show_email", "show_favorites", "notify_like", "notify_reply"}
    with _LOCK:
        users = _load_users()
        for u in users.values():
            if u.get("id") == user_id:
                prof = dict(u.get("profile") or {})
                for k, v in updates.items():
                    if k in allowed:
                        prof[k] = v
                u["profile"] = prof
                _save_users(users)
                return prof
    return None


def user_stats(user_id: str) -> dict:
    """聚合某用户的公开统计：上传数、获赞数、被收藏数、评论数。"""
    from app.services import resource_store

    resources = resource_store.list_by_author_raw(user_id)
    inter = resource_store._load_interactions_raw()

    uploads = len(resources)
    approved = sum(1 for r in resources if r.get("status") == "approved")
    likes_map = inter.get("likes", {})
    favorites_map = inter.get("favorites", {})
    likes_received = sum(len(likes_map.get(r["id"], [])) for r in resources)
    favorites_received = sum(len(favorites_map.get(r["id"], [])) for r in resources)
    comments_made = sum(1 for c in inter.get("comments", []) if c.get("author_id") == user_id)

    return {
        "uploads": uploads,
        "approved": approved,
        "likes_received": likes_received,
        "favorites_received": favorites_received,
        "comments_made": comments_made,
    }

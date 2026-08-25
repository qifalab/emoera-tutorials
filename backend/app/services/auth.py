"""教程平台账号系统：本地注册/登录、令牌签发、角色管理。

设计：
- 密码使用 PBKDF2-HMAC-SHA256 加盐哈希（标准库 hashlib.pbkdf2_hmac），不存明文；
- 用户持久化到 backend/app/data/users.json（与 ai_settings.json 同级，已 gitignore）；
- 登录令牌为随机 hex，存于内存 dict（进程重启后需重新登录，足够内网使用）；
- 管理员授予：仅当注册时携带 EMOERA_ADMIN_INVITE_CODE 配置的邀请码才成为 admin；
  未配置邀请码时，平台无管理员入口（安全默认，公网部署务必配置邀请码）。

安全：
- 登录按用户名做内存限速，防暴力破解；
- 密码哈希 PBKDF2 迭代 120k 次，加随机盐。
"""

import hashlib
import json
import os
import secrets
import threading
import time
from datetime import datetime
from typing import Optional

from app.config import settings
from app.schemas.tutorial import UserPublic

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
TOKENS_FILE = os.path.join(DATA_DIR, "tokens.json")

_LOCK = threading.Lock()

# 登录令牌：持久化到 tokens.json，后端重启后登录态依然有效。
# 结构：{token: user_id}
_tokens: dict[str, str] = {}


def _load_tokens() -> dict:
    try:
        with open(TOKENS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save_tokens(tokens: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = TOKENS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOKENS_FILE)

# 登录限速：username -> (失败次数, 最早失败时间)
_LOGIN_ATTEMPTS: dict[str, tuple[int, float]] = {}
MAX_FAILED = 5
LOCKOUT_SECONDS = 60


def _admin_invite_code() -> str:
    # 经 pydantic-settings 读取 .env（os.getenv 不会加载 .env 文件）
    return settings.admin_invite_code.strip()


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


def _hash_password(password: str, salt: str) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return dk.hex()


def register(username: str, password: str, invite_code: Optional[str] = None) -> tuple[Optional[UserPublic], Optional[str]]:
    """注册用户。返回 (user, error)。

    管理员授予规则（安全优先，无任何"首个注册即管理员"的提权回退）：
    - 配置了 EMOERA_ADMIN_INVITE_CODE：仅当 invite_code 完全正确时成为 admin；
    - 未配置邀请码：一律注册为普通 user，平台无管理员入口（安全默认）。
    """
    username = username.strip()
    if not username:
        return None, "用户名不能为空"
    with _LOCK:
        users = _load_users()
        if username in users:
            return None, "用户名已存在"
        expected_invite = _admin_invite_code()
        if expected_invite:
            role = "admin" if invite_code == expected_invite else "user"
        else:
            role = "user"
        salt = secrets.token_hex(16)
        user = {
            "id": secrets.token_hex(8),
            "username": username,
            "salt": salt,
            "password_hash": _hash_password(password, salt),
            "role": role,
            "created_at": datetime.now().isoformat(),
        }
        users[username] = user
        _save_users(users)
    return UserPublic(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        created_at=datetime.fromisoformat(user["created_at"]),
    ), None


def _check_lockout(username: str) -> Optional[str]:
    """检查是否处于限速锁定。返回 None 表示放行，否则返回错误信息。"""
    with _LOCK:
        rec = _LOGIN_ATTEMPTS.get(username)
    if not rec:
        return None
    fails, first = rec
    if fails >= MAX_FAILED and (time.time() - first) < LOCKOUT_SECONDS:
        return f"登录失败次数过多，请 {int(LOCKOUT_SECONDS - (time.time() - first))} 秒后再试"
    return None


def _record_failure(username: str) -> None:
    with _LOCK:
        fails, first = _LOGIN_ATTEMPTS.get(username, (0, time.time()))
        if time.time() - first >= LOCKOUT_SECONDS:
            fails, first = 0, time.time()
        _LOGIN_ATTEMPTS[username] = (fails + 1, first)


def _clear_failures(username: str) -> None:
    with _LOCK:
        _LOGIN_ATTEMPTS.pop(username, None)


def login(username: str, password: str) -> tuple[Optional[str], Optional[UserPublic], Optional[str]]:
    """登录。返回 (token, user, error)。含失败限速。"""
    username = username.strip()
    if err := _check_lockout(username):
        return None, None, err
    with _LOCK:
        users = _load_users()
        user = users.get(username)
    if not user or _hash_password(password, user["salt"]) != user["password_hash"]:
        _record_failure(username)
        return None, None, "用户名或密码错误"
    _clear_failures(username)
    token = secrets.token_hex(24)
    with _LOCK:
        tokens = _load_tokens()
        tokens[token] = user["id"]
        _save_tokens(tokens)
        _tokens[token] = user["id"]
    return token, UserPublic(
        id=user["id"],
        username=user["username"],
        role=user["role"],
        created_at=datetime.fromisoformat(user["created_at"]),
    ), None


def user_counts() -> dict:
    """统计用户总数与管理员数量，供管理后台仪表盘使用。"""
    users = _load_users()
    return {
        "total": len(users),
        "admins": sum(1 for u in users.values() if u.get("role") == "admin"),
    }


def get_user_by_token(token: str) -> Optional[UserPublic]:
    """由令牌解析用户。无效返回 None。"""
    user_id = _tokens.get(token)
    if not user_id:
        # 内存未命中时从磁盘兜底（进程重启后 _tokens 为空）
        try:
            user_id = _load_tokens().get(token)
        except Exception:  # noqa: BLE001
            user_id = None
        if not user_id:
            return None
    users = _load_users()
    for u in users.values():
        if u["id"] == user_id:
            return UserPublic(
                id=u["id"],
                username=u["username"],
                role=u["role"],
                created_at=datetime.fromisoformat(u["created_at"]),
            )
    return None


def logout(token: str) -> None:
    _tokens.pop(token, None)
    with _LOCK:
        tokens = _load_tokens()
        tokens.pop(token, None)
        _save_tokens(tokens)

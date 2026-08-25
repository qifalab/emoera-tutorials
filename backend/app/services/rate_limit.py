"""轻量级请求限流（防 DDoS / 暴力刷接口）。

实现：滑动窗口计数器（按客户端 IP 分桶），内存态、线程安全。
- 全局限流：对所有写操作（POST/PUT/DELETE）按 IP 计数；
- 登录接口单独更严格限流（防暴力破解）。
数据量级为个人/小团队部署，内存态足够；多实例部署需替换为 Redis。

对外：`rate_limit_dependency` 可作为 FastAPI 依赖直接使用。
"""

import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.config import settings

# 写操作方法
_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

_LOCK = threading.Lock()
_hits: dict[str, deque] = {}  # key -> 时间戳队列


def _record(key: str, limit: int, window: float) -> bool:
    """记录一次请求，返回是否超限。"""
    now = time.monotonic()
    with _LOCK:
        q = _hits.setdefault(key, deque())
        # 清理窗口外的旧记录
        while q and now - q[0] > window:
            q.popleft()
        if len(q) >= limit:
            return True
        q.append(now)
        return False


def _client_key(request: Request) -> str:
    """客户端标识。

    默认使用真实 socket IP（request.client.host），**不信任** X-Forwarded-For
    ——否则攻击者伪造 XFF 头即可任意更换标识，完全绕过限流并造成内存无限增长。
    仅当显式配置 settings.trust_proxy=True（部署在可信反代后方）时才读 XFF。
    """
    if settings.trust_proxy:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def rate_limit_dependency(request: Request) -> None:
    """全局限流依赖：对写操作按 IP 限流，读操作放行。"""
    if not settings.enable_rate_limit:
        return
    if request.method not in _WRITE_METHODS:
        return

    key = f"w:{_client_key(request)}"
    if _record(key, settings.rate_limit_burst, 60.0):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


async def login_rate_limit(request: Request) -> None:
    """登录/注册接口的严格限流（防暴力破解与注册轰炸）。"""
    if not settings.enable_rate_limit:
        return
    key = f"login:{_client_key(request)}"
    # 更严格：每分钟 20 次
    if _record(key, 20, 60.0):
        raise HTTPException(status_code=429, detail="尝试次数过多，请 1 分钟后再试")

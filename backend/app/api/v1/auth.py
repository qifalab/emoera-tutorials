"""账号相关路由：注册 / 登录 / 登出 / 当前用户。"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from app.config import settings
from app.schemas.tutorial import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)
from app.services import auth as auth_service
from app.services.rate_limit import login_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])

# httpOnly Cookie 名（前后端分离时前端 JS 读不到 token，防 XSS 窃取）
TOKEN_COOKIE = "emoera_token"
# 与后端令牌 TTL 一致；0 = 会话结束即失效
COOKIE_MAX_AGE = settings.token_ttl_hours * 3600 if settings.token_ttl_hours > 0 else None


def _set_token_cookie(response: Response, token: str) -> None:
    """把令牌写入 httpOnly Cookie（SameSite=Lax，默认 Path=/）。"""
    response.set_cookie(
        key=TOKEN_COOKIE,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        path="/",
    )


def _clear_token_cookie(response: Response) -> None:
    response.delete_cookie(key=TOKEN_COOKIE, path="/")


def _resolve_token(authorization: str, request: Request) -> str:
    """解析令牌：显式 Authorization 头优先，其次回退 httpOnly Cookie。

    注意：必须让 Authorization 优先——否则客户端同源下 cookie 与显式 Bearer
    头不一致时会静默用错身份（TestClient/跨客户端场景尤甚）。
    """
    if authorization.startswith("Bearer "):
        return authorization[len("Bearer "):].strip()
    return request.cookies.get(TOKEN_COOKIE) or ""


def get_current_user(authorization: str = Header(default=""), request: Request = None) -> UserPublic:
    """从 httpOnly Cookie（或 Authorization 头）解析当前用户。"""
    token = _resolve_token(authorization, request)
    if not token:
        raise HTTPException(status_code=401, detail="未登录或令牌格式错误")
    user = auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return user


def get_current_user_optional(
    authorization: str = Header(default=""),
    request: Request = None,
) -> Optional[UserPublic]:
    """可选登录：未登录返回 None（不抛 401），用于详情页展示点赞/收藏状态。"""
    token = _resolve_token(authorization, request)
    if not token:
        return None
    return auth_service.get_user_by_token(token)


def get_admin_user(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, request: Request, response: Response):
    await login_rate_limit(request)
    user, err = auth_service.register(req.username, req.password, req.invite_code)
    if err:
        raise HTTPException(status_code=400, detail=err)
    # 注册成功后自动登录：令牌写入 httpOnly Cookie，同时返回 token（旧前端兼容）
    token, _, _ = auth_service.login(req.username, req.password)
    _set_token_cookie(response, token)
    return AuthResponse(token=token, user=user)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request, response: Response):
    await login_rate_limit(request)
    token, user, err = auth_service.login(req.username, req.password)
    if err:
        raise HTTPException(status_code=401, detail=err)
    _set_token_cookie(response, token)
    return AuthResponse(token=token, user=user)


@router.post("/logout")
async def logout(authorization: str = Header(default=""), request: Request = None, response: Response = None):
    token = _resolve_token(authorization, request)
    if token:
        auth_service.logout(token)
    if response is not None:
        _clear_token_cookie(response)
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def get_me(user: UserPublic = Depends(get_current_user)):
    return user

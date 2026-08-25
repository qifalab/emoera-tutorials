"""账号相关路由：注册 / 登录 / 登出 / 当前用户。"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.schemas.tutorial import (
    AuthResponse,
    LoginRequest,
    RegisterRequest,
    UserPublic,
)
from app.services import auth as auth_service
from app.services.rate_limit import login_rate_limit

router = APIRouter(prefix="/auth", tags=["auth"])


def get_current_user(authorization: str = Header(default="")) -> UserPublic:
    """从 Authorization: Bearer <token> 解析当前用户。"""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录或令牌格式错误")
    token = authorization[len("Bearer "):].strip()
    user = auth_service.get_user_by_token(token)
    if not user:
        raise HTTPException(status_code=401, detail="令牌无效或已过期")
    return user


def get_current_user_optional(
    authorization: str = Header(default=""),
) -> Optional[UserPublic]:
    """可选登录：未登录返回 None（不抛 401），用于详情页展示点赞/收藏状态。"""
    if not authorization.startswith("Bearer "):
        return None
    token = authorization[len("Bearer "):].strip()
    return auth_service.get_user_by_token(token)


def get_admin_user(user: UserPublic = Depends(get_current_user)) -> UserPublic:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest, request: Request):
    await login_rate_limit(request)
    user, err = auth_service.register(req.username, req.password, req.invite_code)
    if err:
        raise HTTPException(status_code=400, detail=err)
    # 注册成功后自动登录，返回令牌
    token, _, _ = auth_service.login(req.username, req.password)
    return AuthResponse(token=token, user=user)


@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest, request: Request):
    await login_rate_limit(request)
    token, user, err = auth_service.login(req.username, req.password)
    if err:
        raise HTTPException(status_code=401, detail=err)
    return AuthResponse(token=token, user=user)


@router.post("/logout")
async def logout(authorization: str = Header(default="")):
    if authorization.startswith("Bearer "):
        auth_service.logout(authorization[len("Bearer "):].strip())
    return {"ok": True}


@router.get("/me", response_model=UserPublic)
async def get_me(user: UserPublic = Depends(get_current_user)):
    return user

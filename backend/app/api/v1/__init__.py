"""API v1：聚合各资源路由。"""

from fastapi import APIRouter

from app.api.v1 import (
    admin_resources,
    ai_router,
    auth,
    messages,
    news,
    notifications,
    resources,
    settings,
    tasks,
)

router = APIRouter()
router.include_router(tasks.router)
router.include_router(messages.router)
router.include_router(news.router)
router.include_router(settings.router)
router.include_router(ai_router.router)
router.include_router(auth.router)
router.include_router(resources.router)
router.include_router(admin_resources.router)
router.include_router(notifications.router)
router.include_router(notifications.router_user)

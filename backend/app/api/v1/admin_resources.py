"""管理员审核路由：查看待审列表、通过 / 驳回资源。需管理员权限。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.v1.auth import get_admin_user
from app.schemas.tutorial import ResourceItem, ResourceReview, UserPublic
from app.services import resource_store

router = APIRouter(prefix="/admin/resources", tags=["admin-resources"])


@router.get("/stats")
async def stats(user: UserPublic = Depends(get_admin_user)):
    """管理后台仪表盘统计：用户 / 资源状态分布 / 互动总量 / 分类 / 排行，需管理员权限。"""
    return resource_store.get_stats()


@router.get("/pending", response_model=list[ResourceItem])
async def pending(user: UserPublic = Depends(get_admin_user)):
    """待审核 + 已驳回列表，供管理后台展示。"""
    return [ResourceItem(**r) for r in resource_store.list_pending()]


@router.post("/{res_id}/review", response_model=ResourceItem)
async def review(
    res_id: str,
    body: ResourceReview,
    user: UserPublic = Depends(get_admin_user),
):
    """审核一条资源：action=approve 通过，action=reject 驳回（可附 note）。"""
    status = "approved" if body.action == "approve" else "rejected"
    rec = resource_store.update_status(res_id, status, body.note)
    if not rec:
        raise HTTPException(status_code=404, detail="资源不存在")
    return ResourceItem(**rec)

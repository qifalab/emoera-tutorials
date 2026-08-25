"""资源相关路由：上传（需登录）、公开列表（分类/搜索/排序）、详情、编辑、点赞/收藏/评论、我的资源、下载计数。"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.api.v1.auth import get_current_user, get_current_user_optional
from app.schemas.tutorial import (
    CommentCreate,
    CommentItem,
    ResourceDetail,
    ResourceItem,
    ResourceUpdate,
    UserPublic,
)
from app.services import resource_store
from app.services.link_safety import validate_external_link

router = APIRouter(prefix="/resources", tags=["resources"])

SORT_CHOICES = {"latest", "hottest", "downloads", "likes"}


def _require_approved(res_id: str) -> dict:
    """取资源并确保已通过审核。"""
    rec = resource_store.get_resource(res_id)
    if not rec or rec["status"] != "approved":
        raise HTTPException(status_code=404, detail="资源不存在或未通过审核")
    return rec


def _check_link(link: str) -> None:
    """外链安全校验（协议 / 内网 / 高危下载后缀）。"""
    err = validate_external_link(link)
    if err:
        raise HTTPException(status_code=400, detail=err)


@router.post("", response_model=ResourceItem)
async def upload_resource(
    title: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default="教程"),
    tags: str = Form(default=""),
    link: str = Form(default=""),
    image_url: str = Form(default=""),
    file: UploadFile | None = None,
    user: UserPublic = Depends(get_current_user),
):
    """上传资源（图文 + 可选附件）。上传后为待审核状态，管理员通过后才公开。"""
    if not title.strip():
        raise HTTPException(status_code=400, detail="标题不能为空")

    _check_link(link)
    if image_url.strip():
        _check_link(image_url)

    tag_list = [t.strip() for t in tags.split(",") if t.strip()]

    file_name = file_path = ""
    file_size = 0
    file_type = ""
    if file is not None and file.filename:
        try:
            # 流式落盘：避免大文件一次性读入内存
            file_name, file_path, file_size, file_type = await resource_store.save_file_stream(
                file, file.filename
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    rec = resource_store.add_resource(
        title=title.strip(),
        description=description,
        category=category,
        tags=tag_list,
        link=link,
        image_url=image_url.strip(),
        author_id=user.id,
        author_name=user.username,
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
        file_type=file_type,
    )
    return ResourceItem(**rec)


@router.get("", response_model=list[ResourceItem])
async def list_public(
    category: str = "",
    q: str = "",
    sort: str = "latest",
):
    """公开可见资源（仅已通过审核）。

    支持 ?category=分类、?q=关键词、?sort=latest|hottest|downloads|likes。
    """
    if sort not in SORT_CHOICES:
        sort = "latest"
    return [
        ResourceItem(**r)
        for r in resource_store.list_approved(
            category=category or None,
            q=q or None,
            sort=sort,
        )
    ]


@router.get("/categories")
async def list_resource_categories():
    """公开资源的分类及计数（供资源中心侧栏筛选）。"""
    return {"categories": resource_store.list_categories()}


@router.get("/favorites", response_model=list[ResourceItem])
async def list_my_favorites(user: UserPublic = Depends(get_current_user)):
    """当前用户收藏的资源列表。"""
    return [ResourceItem(**r) for r in resource_store.list_favorites(user.id)]


@router.get("/mine", response_model=list[ResourceItem])
async def list_mine(user: UserPublic = Depends(get_current_user)):
    """当前用户发布的全部资源（含待审/驳回，可看驳回原因）。"""
    return [ResourceItem(**r) for r in resource_store.list_by_author(user.id)]


@router.get("/{res_id}", response_model=ResourceDetail)
async def get_resource_detail(
    res_id: str,
    user: UserPublic | None = Depends(get_current_user_optional),
):
    """资源详情：含评论列表 + 当前用户点赞/收藏状态。"""
    rec = _require_approved(res_id)
    comments = [CommentItem(**c) for c in resource_store.list_comments(res_id)]
    liked = False
    favorited = False
    if user is not None:
        liked = resource_store.liked_by(res_id, user.id)
        favorited = resource_store.favorited_by(res_id, user.id)
    return ResourceDetail(
        resource=ResourceItem(**rec),
        comments=comments,
        liked=liked,
        favorited=favorited,
    )


@router.put("/{res_id}", response_model=ResourceItem)
async def edit_resource(
    res_id: str,
    body: ResourceUpdate,
    user: UserPublic = Depends(get_current_user),
):
    """编辑资源（仅作者本人）。编辑后重置为待审核状态，需重新通过审核。"""
    rec = resource_store.get_resource(res_id)
    if not rec:
        raise HTTPException(status_code=404, detail="资源不存在")
    if rec["author_id"] != user.id:
        raise HTTPException(status_code=403, detail="只能编辑自己上传的资源")

    _check_link(body.link)
    if body.image_url.strip():
        _check_link(body.image_url)

    updated = resource_store.update_resource(
        res_id,
        title=body.title,
        description=body.description,
        category=body.category,
        tags=body.tags,
        link=body.link,
        image_url=body.image_url.strip(),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="资源不存在")
    return ResourceItem(**updated)


@router.post("/{res_id}/download")
async def bump_download(res_id: str):
    """下载计数 +1（前端点击下载/查看时调用）。"""
    rec = _require_approved(res_id)
    resource_store.increment_downloads(res_id)
    return {"ok": True, "downloads": rec["downloads"] + 1}


@router.post("/{res_id}/like")
async def toggle_like(res_id: str, user: UserPublic = Depends(get_current_user)):
    """切换点赞（需登录）。"""
    _require_approved(res_id)
    return resource_store.toggle_like(res_id, user.id)


@router.post("/{res_id}/favorite")
async def toggle_favorite(res_id: str, user: UserPublic = Depends(get_current_user)):
    """切换收藏（需登录）。"""
    _require_approved(res_id)
    return resource_store.toggle_favorite(res_id, user.id)


@router.get("/{res_id}/comments", response_model=list[CommentItem])
async def list_comments(res_id: str):
    """某资源的评论列表。"""
    _require_approved(res_id)
    return [CommentItem(**c) for c in resource_store.list_comments(res_id)]


@router.post("/{res_id}/comments", response_model=CommentItem)
async def create_comment(
    res_id: str,
    body: CommentCreate,
    user: UserPublic = Depends(get_current_user),
):
    """发表评论（可带 parent_id 楼中楼回复，需登录）。"""
    _require_approved(res_id)
    comment = resource_store.add_comment(
        res_id=res_id,
        author_id=user.id,
        author_name=user.username,
        content=body.content.strip(),
        parent_id=body.parent_id,
    )
    return CommentItem(**comment)

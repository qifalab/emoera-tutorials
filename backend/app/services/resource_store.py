"""教程平台资源存储：资源元信息持久化 + 附件落盘。

设计：
- 资源元信息存 backend/app/data/resources.json（与 users.json 同级，已 gitignore）；
- 上传文件落盘到 backend/app/data/uploads/，统一用 UUID 重命名，避免文件名冲突与注入；
- 文件类型白名单 + 大小上限（默认 200MB，兼容视频）：超限或非法类型直接拒绝；
- 资源状态：pending / approved / rejected。
"""

import json
import os
import secrets
import threading
from datetime import datetime
from typing import Optional

from app.services import auth as auth_service

# 允许的文件扩展名（小写，含点）
# 安全注意：不含 .svg / .html / .htm / .xml / .js 等可携带脚本或触发内联渲染的类型，
# 防止存储型 XSS（SVG 内嵌 <script>、HTML 加载即执行）。
ALLOWED_EXT = {
    # 图片（仅位图，无脚本能力）
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp",
    # 文档
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx", ".txt", ".md",
    # 压缩包
    ".zip", ".rar", ".7z", ".tar", ".gz",
    # 音视频
    ".mp4", ".webm", ".mov", ".avi", ".mkv", ".mp3", ".wav", ".flac", ".ogg",
    # 代码/其它（不含可执行/脚本类型）
    ".py", ".json", ".ipynb", ".csv",
}

# 单文件大小上限：200MB
MAX_FILE_SIZE = 200 * 1024 * 1024

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
RESOURCES_FILE = os.path.join(DATA_DIR, "resources.json")
INTERACTIONS_FILE = os.path.join(DATA_DIR, "interactions.json")

_LOCK = threading.Lock()


def _load() -> list:
    try:
        with open(RESOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return []


def _save(resources: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = RESOURCES_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(resources, f, ensure_ascii=False, indent=2)
    os.replace(tmp, RESOURCES_FILE)


def _load_interactions() -> dict:
    """加载互动数据：{likes: {res_id: [user_id]}, favorites: {...}, comments: [...], comment_likes: {comment_id: [user_id]}}"""
    try:
        with open(INTERACTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"likes": {}, "favorites": {}, "comments": [], "comment_likes": {}}


def _load_interactions_raw() -> dict:
    """加载互动数据原始结构（不补默认值）。"""
    try:
        with open(INTERACTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {"likes": {}, "favorites": {}, "comments": [], "comment_likes": {}}


def _save_interactions(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = INTERACTIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, INTERACTIONS_FILE)


def _ext_of(filename: str) -> str:
    return os.path.splitext(filename)[1].lower()


async def save_file_stream(
    upload_file,
    original_name: str,
    chunk_size: int = 1024 * 1024,
) -> tuple[str, str, int, str]:
    """分块流式落盘上传文件，避免一次性读入内存。

    upload_file 为 Starlette UploadFile（支持 await read(chunk_size)），返回
    (原始文件名, 相对路径 /uploads/xxx, 大小, 扩展名)。超过大小上限抛 ValueError。
    """
    ext = _ext_of(original_name)
    if ext not in ALLOWED_EXT:
        raise ValueError(f"不支持的文件类型：{ext or '未知'}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    stored = secrets.token_hex(16) + ext
    path = os.path.join(UPLOAD_DIR, stored)

    total = 0
    with open(path, "wb") as f:
        while True:
            chunk = await upload_file.read(chunk_size)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_SIZE:
                f.close()
                os.remove(path)
                raise ValueError(f"文件过大（上限 {MAX_FILE_SIZE // 1024 // 1024}MB）")
            f.write(chunk)
    return original_name, f"/uploads/{stored}", total, ext


def add_resource(
    *,
    title: str,
    description: str,
    category: str,
    tags: list[str],
    link: str,
    author_id: str,
    author_name: str,
    image_url: str = "",
    file_name: str = "",
    file_path: str = "",
    file_size: int = 0,
    file_type: str = "",
) -> dict:
    """新增一条待审核资源。返回完整记录 dict。"""
    res = {
        "id": secrets.token_hex(8),
        "title": title,
        "description": description,
        "category": category,
        "tags": tags,
        "link": link,
        "image_url": image_url,
        "file_name": file_name,
        "file_path": file_path,
        "file_size": file_size,
        "file_type": file_type,
        "status": "pending",
        "author_id": author_id,
        "author_name": author_name,
        "created_at": datetime.now().isoformat(),
        "reviewed_at": None,
        "review_note": "",
        "downloads": 0,
    }
    with _LOCK:
        resources = _load()
        resources.append(res)
        _save(resources)
    return res


def _with_counts(r: dict, inter: dict) -> dict:
    """给资源 dict 注入点赞/收藏/评论计数（用于对外返回）。"""
    r = dict(r)
    r["likes"] = len(inter.get("likes", {}).get(r["id"], []))
    r["favorites"] = len(inter.get("favorites", {}).get(r["id"], []))
    r["comment_count"] = sum(
        1 for c in inter.get("comments", []) if c.get("resource_id") == r["id"]
    )
    return r


def list_approved(
    category: Optional[str] = None,
    q: Optional[str] = None,
    sort: str = "latest",
) -> list:
    """公开可见资源（已通过审核），支持按分类 / 关键词过滤 + 排序，带互动计数。

    - category：精确匹配分类名（前端分类标签点击传入）
    - q：关键词，模糊匹配标题 / 简介 / 标签 / 作者
    - sort：latest（最新，默认）/ hottest（最热=下载+点赞+收藏加权）/ downloads / likes
    """
    with _LOCK:
        resources = _load()
        inter = _load_interactions()
    out = [r for r in resources if r["status"] == "approved"]
    if category:
        out = [r for r in out if r.get("category", "") == category]
    if q:
        ql = q.strip().lower()
        if ql:
            def _hit(r: dict) -> bool:
                hay = " ".join([
                    r.get("title", ""),
                    r.get("description", ""),
                    " ".join(r.get("tags", [])),
                    r.get("author_name", ""),
                ]).lower()
                return ql in hay
            out = [r for r in out if _hit(r)]
    out = [_with_counts(r, inter) for r in out]

    if sort == "downloads":
        out.sort(key=lambda r: (r.get("downloads", 0), r.get("created_at", "")), reverse=True)
    elif sort == "likes":
        out.sort(key=lambda r: (r.get("likes", 0), r.get("created_at", "")), reverse=True)
    elif sort == "hottest":
        out.sort(
            key=lambda r: (
                r.get("downloads", 0) * 3 + r.get("likes", 0) * 2 + r.get("favorites", 0) * 5,
                r.get("created_at", ""),
            ),
            reverse=True,
        )
    else:  # latest
        out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return out


def list_categories() -> list[dict]:
    """返回公开资源的分类及计数（按资源数降序，同数按名称升序）。"""
    with _LOCK:
        resources = _load()
    approved = [r for r in resources if r["status"] == "approved"]
    counts: dict[str, int] = {}
    for r in approved:
        cat = r.get("category", "未分类") or "未分类"
        counts[cat] = counts.get(cat, 0) + 1
    items = [{"name": k, "count": v} for k, v in counts.items()]
    items.sort(key=lambda x: (-x["count"], x["name"]))
    return items


def get_stats() -> dict:
    """管理后台仪表盘聚合统计。

    返回：用户数/管理员数、资源状态分布、互动总量（下载/点赞/收藏/评论）、
    分类分布、下载排行 Top5、最近上传 Top5。所有计数实时从 JSON 派生，保证一致。
    """
    with _LOCK:
        resources = _load()
        inter = _load_interactions()

    by_status = {"pending": 0, "approved": 0, "rejected": 0}
    total_downloads = 0
    for r in resources:
        s = r.get("status", "pending")
        by_status[s] = by_status.get(s, 0) + 1
        total_downloads += r.get("downloads", 0)

    likes_map = inter.get("likes", {})
    favs_map = inter.get("favorites", {})
    comments = inter.get("comments", [])
    total_likes = sum(len(v) for v in likes_map.values())
    total_favorites = sum(len(v) for v in favs_map.values())
    total_comments = len(comments)

    # 分类分布（仅已通过资源）
    cat_counts: dict[str, int] = {}
    for r in resources:
        if r.get("status") == "approved":
            cat = r.get("category", "未分类") or "未分类"
            cat_counts[cat] = cat_counts.get(cat, 0) + 1
    categories = [
        {"name": k, "count": v}
        for k, v in sorted(cat_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    indexed = [_with_counts(r, inter) for r in resources]
    top_resources = sorted(indexed, key=lambda r: r.get("downloads", 0), reverse=True)[:5]
    recent = sorted(indexed, key=lambda r: r.get("created_at", ""), reverse=True)[:5]

    return {
        "users": auth_service.user_counts(),
        "resources": {
            "total": len(resources),
            "pending": by_status.get("pending", 0),
            "approved": by_status.get("approved", 0),
            "rejected": by_status.get("rejected", 0),
        },
        "interactions": {
            "downloads": total_downloads,
            "likes": total_likes,
            "favorites": total_favorites,
            "comments": total_comments,
        },
        "categories": categories,
        "top_resources": top_resources,
        "recent": recent,
    }


def list_pending() -> list:
    """待审核 + 已驳回（管理后台用），按创建时间倒序。"""
    with _LOCK:
        resources = _load()
        inter = _load_interactions()
    out = [r for r in resources if r["status"] in ("pending", "rejected")]
    out = [_with_counts(r, inter) for r in out]
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


def list_by_author(author_id: str) -> list:
    """某用户发布的全部资源（含待审/驳回），用于「我的资源」。"""
    with _LOCK:
        resources = _load()
        inter = _load_interactions()
    out = [r for r in resources if r["author_id"] == author_id]
    out = [_with_counts(r, inter) for r in out]
    out.sort(key=lambda r: r["created_at"], reverse=True)
    return out


def list_by_author_raw(author_id: str) -> list:
    """某用户发布的全部资源原样记录（不含互动计数），供统计聚合。"""
    with _LOCK:
        resources = _load()
    return [r for r in resources if r["author_id"] == author_id]


def update_status(res_id: str, status: str, note: str = "") -> Optional[dict]:
    """更新资源审核状态。返回更新后的记录，未找到返回 None。"""
    with _LOCK:
        resources = _load()
        for r in resources:
            if r["id"] == res_id:
                r["status"] = status
                r["review_note"] = note
                r["reviewed_at"] = datetime.now().isoformat()
                _save(resources)
                return r
    return None


def update_resource(
    res_id: str,
    *,
    title: str,
    description: str,
    category: str,
    tags: list[str],
    link: str,
    image_url: str = "",
) -> Optional[dict]:
    """编辑资源（仅作者本人调用）。编辑后重置为待审核，清空驳回原因。

    不修改附件（file_name/file_path/file_size/file_type），
    附件如需更换请重新上传一条新资源。
    """
    with _LOCK:
        resources = _load()
        for r in resources:
            if r["id"] == res_id:
                r["title"] = title.strip()
                r["description"] = description
                r["category"] = category or "教程"
                r["tags"] = tags
                r["link"] = link
                r["image_url"] = image_url
                r["status"] = "pending"
                r["review_note"] = ""
                r["reviewed_at"] = None
                _save(resources)
                return r
    return None


def get_resource(res_id: str) -> Optional[dict]:
    with _LOCK:
        resources = _load()
        inter = _load_interactions()
    for r in resources:
        if r["id"] == res_id:
            return _with_counts(r, inter)
    return None


def increment_downloads(res_id: str) -> None:
    with _LOCK:
        resources = _load()
        for r in resources:
            if r["id"] == res_id:
                r["downloads"] += 1
                _save(resources)
                return


# ---------------------------------------------------------------------------
# 互动：点赞 / 收藏 / 评论
# ---------------------------------------------------------------------------
def toggle_like(res_id: str, user_id: str) -> dict:
    """切换点赞状态。返回 {liked: bool, likes: int}。"""
    with _LOCK:
        inter = _load_interactions()
        likes = inter.setdefault("likes", {}).setdefault(res_id, [])
        if user_id in likes:
            likes.remove(user_id)
            liked = False
        else:
            likes.append(user_id)
            liked = True
        _save_interactions(inter)
    return {"liked": liked, "likes": len(likes)}


def toggle_favorite(res_id: str, user_id: str) -> dict:
    """切换收藏状态。返回 {favorited: bool, favorites: int}。"""
    with _LOCK:
        inter = _load_interactions()
        favs = inter.setdefault("favorites", {}).setdefault(res_id, [])
        if user_id in favs:
            favs.remove(user_id)
            favorited = False
        else:
            favs.append(user_id)
            favorited = True
        _save_interactions(inter)
    return {"favorited": favorited, "favorites": len(favs)}


def add_comment(
    res_id: str,
    author_id: str,
    author_name: str,
    content: str,
    parent_id: Optional[str] = None,
) -> dict:
    """新增一条评论。返回完整评论 dict。"""
    comment = {
        "id": secrets.token_hex(8),
        "resource_id": res_id,
        "content": content,
        "author_id": author_id,
        "author_name": author_name,
        "parent_id": parent_id,
        "created_at": datetime.now().isoformat(),
    }
    with _LOCK:
        inter = _load_interactions()
        inter.setdefault("comments", []).append(comment)
        _save_interactions(inter)
    return comment


def list_comments(res_id: str) -> list:
    """返回某资源的所有评论（按时间正序，楼中楼靠 parent_id 关联）。"""
    with _LOCK:
        inter = _load_interactions()
    comments = [
        _with_comment_meta(c, inter, "")
        for c in inter.get("comments", [])
        if c.get("resource_id") == res_id
    ]
    comments.sort(key=lambda c: c.get("created_at", ""))
    return comments


def list_comments_sorted(res_id: str, viewer_id: str = "", sort: str = "time") -> list:
    """返回某资源的评论，支持排序（time 时间正序 / hot 热度=点赞数降序）。"""
    with _LOCK:
        inter = _load_interactions()
    comments = [
        _with_comment_meta(c, inter, viewer_id)
        for c in inter.get("comments", [])
        if c.get("resource_id") == res_id
    ]
    if sort == "hot":
        comments.sort(key=lambda c: (-c.get("likes", 0), c.get("created_at", "")))
    else:
        comments.sort(key=lambda c: c.get("created_at", ""))
    return comments


def _with_comment_meta(c: dict, inter: dict, viewer_id: str) -> dict:
    """给评论注入点赞数 / 是否已赞 / 被回复人昵称。"""
    c = dict(c)
    c["likes"] = len(inter.get("comment_likes", {}).get(c["id"], []))
    c["liked"] = viewer_id in inter.get("comment_likes", {}).get(c["id"], []) if viewer_id else False
    # 补被回复人昵称
    if c.get("parent_id") and not c.get("reply_to_name"):
        parent = next((x for x in inter.get("comments", []) if x.get("id") == c["parent_id"]), None)
        c["reply_to_name"] = parent.get("author_name", "") if parent else ""
    return c


def toggle_comment_like(comment_id: str, user_id: str) -> dict:
    """切换评论点赞。返回 {liked, likes}。若评论不存在返回 None。"""
    with _LOCK:
        inter = _load_interactions()
        exists = any(c.get("id") == comment_id for c in inter.get("comments", []))
        if not exists:
            return None
        likes = inter.setdefault("comment_likes", {}).setdefault(comment_id, [])
        if user_id in likes:
            likes.remove(user_id)
            liked = False
        else:
            likes.append(user_id)
            liked = True
        _save_interactions(inter)
    return {"liked": liked, "likes": len(likes)}


def get_comment(comment_id: str) -> Optional[dict]:
    """按 id 取单条评论（含互动元信息）。"""
    with _LOCK:
        inter = _load_interactions()
    for c in inter.get("comments", []):
        if c.get("id") == comment_id:
            return _with_comment_meta(c, inter, "")
    return None


def delete_comment(comment_id: str) -> Optional[dict]:
    """删除评论（本人或管理员）。返回被删评论，不存在返回 None。"""
    with _LOCK:
        inter = _load_interactions()
        comments = inter.get("comments", [])
        target = next((c for c in comments if c.get("id") == comment_id), None)
        if not target:
            return None
        inter["comments"] = [c for c in comments if c.get("id") != comment_id and c.get("parent_id") != comment_id]
        inter.setdefault("comment_likes", {}).pop(comment_id, None)
        _save_interactions(inter)
    return target


def delete_resource(res_id: str) -> Optional[dict]:
    """删除资源（作者或管理员）。级联清理其点赞/收藏/评论，并删除附件。"""
    with _LOCK:
        resources = _load()
        target = next((r for r in resources if r["id"] == res_id), None)
        if not target:
            return None
        resources = [r for r in resources if r["id"] != res_id]
        _save(resources)

        inter = _load_interactions()
        inter.get("likes", {}).pop(res_id, None)
        inter.get("favorites", {}).pop(res_id, None)
        # 级联删除该资源所有评论及其点赞
        cids = {c["id"] for c in inter.get("comments", []) if c.get("resource_id") == res_id}
        inter["comments"] = [c for c in inter.get("comments", []) if c.get("resource_id") != res_id]
        for cid in cids:
            inter.get("comment_likes", {}).pop(cid, None)
        _save_interactions(inter)
    # 删除物理附件（尽力而为）
    fp = target.get("file_path", "")
    if fp.startswith("/uploads/"):
        abs_path = os.path.join(UPLOAD_DIR, os.path.basename(fp))
        try:
            if os.path.isfile(abs_path):
                os.remove(abs_path)
        except OSError:
            pass
    return target


def get_author(res_id: str) -> Optional[str]:
    """返回资源作者 user_id。"""
    with _LOCK:
        resources = _load()
    for r in resources:
        if r["id"] == res_id:
            return r.get("author_id")
    return None


def liked_by(res_id: str, user_id: str) -> bool:
    with _LOCK:
        inter = _load_interactions()
    return user_id in inter.get("likes", {}).get(res_id, [])


def favorited_by(res_id: str, user_id: str) -> bool:
    with _LOCK:
        inter = _load_interactions()
    return user_id in inter.get("favorites", {}).get(res_id, [])


def list_favorites(user_id: str) -> list:
    """某用户收藏的全部资源（已通过审核的），带计数。"""
    with _LOCK:
        resources = _load()
        inter = _load_interactions()
    fav_ids = [
        rid for rid, users in inter.get("favorites", {}).items()
        if user_id in users
    ]
    out = [r for r in resources if r["id"] in fav_ids and r["status"] == "approved"]
    out = [_with_counts(r, inter) for r in out]
    out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return out


def search_all(q: str, sort: str = "latest", limit: int = 50) -> list:
    """全站搜索：匹配标题/简介/标签/作者（已通过资源），按 sort 排序。"""
    return list_approved(q=q, sort=sort)[:limit]

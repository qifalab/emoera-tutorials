"""教程平台（资源上传 + 管理员审核）相关数据结构。

账号体系：本地账号，密码用 PBKDF2 加盐哈希存储；首个注册用户自动成为管理员。
资源状态流转：pending（待审核） -> approved（已通过） / rejected（已驳回）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 账号
# ---------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    username: str = Field(min_length=2, max_length=32)
    password: str = Field(min_length=6, max_length=128)
    # 首个注册用户可指定成为管理员；后端强制仅首位注册者生效
    invite_code: Optional[str] = None


class LoginRequest(BaseModel):
    username: str
    password: str


class UserPublic(BaseModel):
    id: str
    username: str
    role: str = "user"  # user / admin
    created_at: datetime


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


# ---------------------------------------------------------------------------
# 资源
# ---------------------------------------------------------------------------
class ResourceUpload(BaseModel):
    """表单字段（文件走 multipart 的 file 字段，其余字段同表）。"""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=50000)  # Markdown 正文
    category: str = Field(default="教程", max_length=40)
    tags: str = Field(default="", max_length=200)  # 逗号分隔，后端拆分
    link: str = Field(default="", max_length=2000)  # 可选外链
    image_url: str = Field(default="", max_length=2000)  # 可选封面图 URL


class ResourceItem(BaseModel):
    """一条资源（对外展示）。"""

    id: str
    title: str
    description: str = ""               # Markdown 正文
    category: str = "教程"
    tags: list[str] = Field(default_factory=list)
    link: str = ""                      # 可选外链
    image_url: str = ""                 # 封面图 URL（列表卡片展示用）
    file_name: str = ""                 # 原始文件名（有附件时）
    file_path: str = ""                 # 服务器相对路径 /uploads/xxx
    file_size: int = 0
    file_type: str = ""                 # 文件扩展名/分类
    status: str = "pending"             # pending / approved / rejected
    author_id: str = ""
    author_name: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    reviewed_at: Optional[datetime] = None
    review_note: str = ""               # 驳回原因等
    downloads: int = 0
    likes: int = 0                      # 点赞数
    favorites: int = 0                  # 收藏数
    comment_count: int = 0              # 评论数


class ResourceUpdate(BaseModel):
    """编辑资源（作者本人）。编辑后重置为待审核。"""

    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=50000)
    category: str = Field(default="教程", max_length=40)
    tags: list[str] = Field(default_factory=list)
    link: str = Field(default="", max_length=2000)
    image_url: str = Field(default="", max_length=2000)


class ResourceReview(BaseModel):
    """管理员审核操作。"""

    action: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=500)


class CommentCreate(BaseModel):
    """发表评论（可楼中楼回复）。"""

    content: str = Field(min_length=1, max_length=1000)
    parent_id: Optional[str] = None     # 回复某条评论时填其 id


class CommentItem(BaseModel):
    """一条评论（对外展示）。"""

    id: str
    resource_id: str
    content: str
    author_id: str = ""
    author_name: str = ""
    parent_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    likes: int = 0                      # 点赞数
    liked: bool = False                 # 当前用户是否已点赞
    # 回复时展示被回复人
    reply_to_name: str = ""             # 被回复用户的用户名（parent 的作者）


class CommentSort(BaseModel):
    """评论排序请求（time 时间 / hot 热度）。"""

    sort: str = Field(default="time", pattern="^(time|hot)$")


class ResourceDetail(BaseModel):
    """资源详情（含评论列表 + 当前用户的点赞/收藏状态）。"""

    resource: ResourceItem
    comments: list[CommentItem] = Field(default_factory=list)
    liked: bool = False                 # 当前用户是否已点赞
    favorited: bool = False             # 当前用户是否已收藏

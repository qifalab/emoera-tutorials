"""每日任务相关数据结构。"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class PlatformTaskConfig(BaseModel):
    """一个平台的任务配置（用于前端展示开关状态）。"""

    platform: str
    display_name: str
    enabled: bool = True
    method: str  # playwright / api / imap
    description: str = ""


class PlatformRunResult(BaseModel):
    """单个平台本次执行的明细结果。"""

    platform: str
    status: str  # success / demo / skipped / failed
    items_processed: int = 0
    message: str = ""
    detail: Optional[str] = None


class TaskRunRequest(BaseModel):
    """触发每日任务的请求体。"""

    platforms: Optional[list[str]] = None  # 为 None 时运行全部平台


class TaskRunResult(BaseModel):
    """一次「每日任务」的整体执行结果。"""

    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str = "running"  # running / success / partial / failed
    per_platform: dict[str, PlatformRunResult] = Field(default_factory=dict)

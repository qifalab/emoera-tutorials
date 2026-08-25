"""每日任务相关接口。"""

from fastapi import APIRouter, Depends, HTTPException

from app.adapters.registry import get_task_adapters
from app.api.v1.auth import get_admin_user
from app.schemas.tasks import PlatformTaskConfig, TaskRunRequest, TaskRunResult
from app.schemas.tutorial import UserPublic
from app.services.store import store
from app.services.task_runner import run_daily_tasks

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/config", response_model=list[PlatformTaskConfig])
async def list_config() -> list[PlatformTaskConfig]:
    """列出所有已接入平台及其任务方式（供前端展示）。"""
    return [
        PlatformTaskConfig(
            platform=adapter.name,
            display_name=adapter.display_name,
            enabled=True,
            method=adapter.method,
        )
        for adapter in get_task_adapters()
    ]


@router.post("/run", response_model=TaskRunResult)
async def run_tasks(
    req: TaskRunRequest,
    user: UserPublic = Depends(get_admin_user),
) -> TaskRunResult:
    """触发一次每日任务，可指定平台（不指定则全部）。仅管理员可触发。"""
    return await run_daily_tasks(req.platforms)


@router.get("/runs/{run_id}", response_model=TaskRunResult)
async def get_run(
    run_id: str,
    user: UserPublic = Depends(get_admin_user),
) -> TaskRunResult:
    """查询某次任务执行的结果。仅管理员可查。"""
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run

"""每日任务编排：依次调用各适配器的 run_daily_task，并汇总整体状态。"""

import uuid
from datetime import datetime
from typing import Optional

from app.adapters.registry import get_task_adapters
from app.schemas.tasks import PlatformRunResult, TaskRunResult
from app.services.store import store


def _overall_status(per_platform: dict[str, PlatformRunResult]) -> str:
    """根据各平台结果推导整体状态。demo 视为已跑通（success）。"""
    statuses = {r.status for r in per_platform.values()}
    if not statuses:
        return "success"
    if statuses <= {"success", "demo"}:
        return "success"
    if "failed" in statuses and ("success" in statuses or "demo" in statuses):
        return "partial"
    if statuses <= {"failed"}:
        return "failed"
    return "partial"


async def run_daily_tasks(platforms: Optional[list[str]] = None) -> TaskRunResult:
    """运行每日任务。platforms 为 None 时运行全部平台。"""
    adapters = get_task_adapters()
    if platforms:
        adapters = [a for a in adapters if a.name in platforms]

    run = TaskRunResult(
        run_id=uuid.uuid4().hex,
        started_at=datetime.now(),
        status="running",
    )
    store.add_run(run)

    for adapter in adapters:
        try:
            result = await adapter.run_daily_task()
        except Exception as exc:  # noqa: BLE001 - 兜底，避免单平台异常中断整体
            result = PlatformRunResult(
                platform=adapter.name,
                status="failed",
                message="适配器执行异常",
                detail=str(exc),
            )
        run.per_platform[adapter.name] = result

    run.status = _overall_status(run.per_platform)
    run.finished_at = datetime.now()
    store.add_run(run)
    return run

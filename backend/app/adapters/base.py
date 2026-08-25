"""所有平台适配器的抽象基类。

统一两个能力：
- run_daily_task：完成该平台的一类「每日任务」；
- fetch_messages：拉取该平台的消息/通知，用于汇总。

服务层（task_runner / message_aggregator）只依赖这个接口，
新增平台只需继承并实现这两个方法即可，无需改动上层逻辑。
"""

from abc import ABC, abstractmethod

from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class BaseAdapter(ABC):
    """平台适配器基类。子类必须设置 name / display_name / method。"""

    name: str = "base"
    display_name: str = "Base"
    method: str = "unknown"  # playwright / api / imap

    @abstractmethod
    async def run_daily_task(self) -> PlatformRunResult:
        """执行该平台的每日自动化任务，返回执行明细。"""
        raise NotImplementedError

    @abstractmethod
    async def fetch_messages(self) -> tuple[list[Message], PlatformRunResult]:
        """拉取消息，返回 (消息列表, 拉取明细)。"""
        raise NotImplementedError

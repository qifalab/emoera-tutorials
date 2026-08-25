"""极简内存存储。

说明：脚手架阶段用进程内字典即可满足演示；若要持久化/多实例，
可平滑替换为 SQLite（aiosqlite）或 Redis，接口保持一致即可。
"""

from typing import Optional

from app.schemas.messages import Message
from app.schemas.tasks import TaskRunResult


class Store:
    """保存最近一次消息汇总与历史任务执行记录。"""

    def __init__(self) -> None:
        self.messages: list[Message] = []
        self.runs: dict[str, TaskRunResult] = {}

    def set_messages(self, messages: list[Message]) -> None:
        self.messages = messages

    def get_messages(self) -> list[Message]:
        return self.messages

    def add_run(self, run: TaskRunResult) -> None:
        self.runs[run.run_id] = run

    def get_run(self, run_id: str) -> Optional[TaskRunResult]:
        return self.runs.get(run_id)


store = Store()

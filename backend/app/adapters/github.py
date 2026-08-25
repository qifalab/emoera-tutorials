"""GitHub 适配器（官方 REST API）。

为什么用 API 而非浏览器自动化：GitHub 官方 API 稳定、合规、无需模拟登录，
且通知接口能直接拿到结构化数据。只需在环境变量配置 EMOERA_GITHUB_TOKEN。
未配置 token 时同样走 demo 模式。
"""

from datetime import datetime

import httpx

from app.adapters.base import BaseAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class GitHubAdapter(BaseAdapter):
    name = "github"
    display_name = "GitHub"
    method = "api"

    async def run_daily_task(self) -> PlatformRunResult:
        # GitHub 没有“每日任务”概念，这里以“获取通知数”作为就绪检查。
        if not settings.github_token:
            return PlatformRunResult(
                platform="github", status="demo",
                items_processed=0, message="demo 模式：未配置 GITHUB_TOKEN",
            )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.github.com/notifications",
                    headers={
                        "Authorization": f"Bearer {settings.github_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                r.raise_for_status()
                count = len(r.json())
            return PlatformRunResult(
                platform="github", status="success",
                items_processed=count, message=f"已获取 {count} 条通知",
            )
        except Exception as exc:  # noqa: BLE001
            return PlatformRunResult(
                platform="github", status="failed",
                message="GitHub API 调用失败", detail=str(exc),
            )

    async def fetch_messages(self) -> tuple[list[Message], PlatformRunResult]:
        if not settings.github_token:
            now = datetime.now()
            demo = [
                Message(
                    id="gh-demo", source="github", title="[demo] PR 评论提醒",
                    body="your-pr 收到一条新评论（demo 数据）", url="https://github.com",
                    priority=4, received_at=now, tags=["demo"],
                )
            ]
            return demo, PlatformRunResult(
                platform="github", status="demo",
                items_processed=1, message="demo 模式：未配置 GITHUB_TOKEN",
            )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(
                    "https://api.github.com/notifications",
                    params={"all": "false"},
                    headers={
                        "Authorization": f"Bearer {settings.github_token}",
                        "Accept": "application/vnd.github+json",
                    },
                )
                r.raise_for_status()
                data = r.json()
            messages: list[Message] = []
            for n in data:
                subject = n.get("subject", {})
                repo = n.get("repository", {}).get("full_name", "")
                try:
                    updated = datetime.fromisoformat(
                        n["updated_at"].replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except Exception:  # noqa: BLE001
                    updated = datetime.now()
                messages.append(
                    Message(
                        id=f"github-{n.get('id')}",
                        source="github",
                        title=subject.get("title", "(无标题)"),
                        body=f"[{subject.get('type', '')}] {repo}",
                        url=subject.get("url"),
                        priority=4 if not n.get("read") else 2,
                        received_at=updated,
                        tags=["github", subject.get("type", "").lower()],
                    )
                )
            return messages, PlatformRunResult(
                platform="github", status="success",
                items_processed=len(messages), message="已拉取 GitHub 通知",
            )
        except Exception as exc:  # noqa: BLE001
            return [], PlatformRunResult(
                platform="github", status="failed",
                message="拉取 GitHub 通知失败", detail=str(exc),
            )

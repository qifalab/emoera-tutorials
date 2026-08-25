"""小红书适配器（浏览器自动化）。"""

from datetime import datetime, timedelta

from app.adapters.social.browser_adapter import BrowserAutomationAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class XiaohongshuAdapter(BrowserAutomationAdapter):
    name = "xiaohongshu"
    display_name = "小红书"
    method = "playwright"
    login_url = "https://www.xiaohongshu.com/login"
    username = settings.xiaohongshu_username
    password = settings.xiaohongshu_password

    async def login(self, page, username: str, password: str) -> None:
        # ⚠️ 占位 selector：小红书登录多为二维码/手机号，需按实际流程校准。
        await page.click('text=密码登录')
        await page.fill('input[placeholder="手机号或邮箱"]', username)
        await page.fill('input[placeholder="密码"]', password)
        await page.click('button:has-text("登录")')
        await page.wait_for_timeout(3000)

    def demo_messages(self) -> list[Message]:
        now = datetime.now()
        return [
            Message(
                id="xhs-1", source="xiaohongshu", title="笔记新增 12 个赞",
                body="你的笔记《demo 的一天》获得 12 个赞", url="https://www.xiaohongshu.com",
                priority=3, received_at=now - timedelta(minutes=25), tags=["互动"],
            ),
            Message(
                id="xhs-2", source="xiaohongshu", title="1 条新私信",
                body="用户发来一条合作咨询私信", url="https://www.xiaohongshu.com",
                priority=4, received_at=now - timedelta(minutes=60), tags=["私信"],
            ),
        ]

    def demo_task_result(self) -> PlatformRunResult:
        return PlatformRunResult(
            platform="xiaohongshu", status="demo",
            items_processed=0, message="demo 模式：模拟完成每日互动",
        )

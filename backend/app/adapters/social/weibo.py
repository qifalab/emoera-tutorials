"""微博适配器（浏览器自动化）。"""

from datetime import datetime, timedelta

from app.adapters.social.browser_adapter import BrowserAutomationAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class WeiboAdapter(BrowserAutomationAdapter):
    name = "weibo"
    display_name = "微博"
    method = "playwright"
    login_url = "https://weibo.com/login.php"
    username = settings.weibo_username
    password = settings.weibo_password

    async def login(self, page, username: str, password: str) -> None:
        # ⚠️ 占位 selector：微博 DOM 会改版，上线前需按实际元素校准。
        await page.fill('input[name="username"]', username)
        await page.fill('input[name="password"]', password)
        await page.click('a[action-type="btn_submit"]')
        await page.wait_for_timeout(3000)

    def demo_messages(self) -> list[Message]:
        now = datetime.now()
        return [
            Message(
                id="weibo-1", source="weibo", title="新增 3 条评论",
                body="你的微博收到了 3 条新评论", url="https://weibo.com",
                priority=3, received_at=now - timedelta(minutes=10), tags=["互动"],
            ),
            Message(
                id="weibo-2", source="weibo", title="@你的提醒",
                body="用户 @demo 在微博中提到了你", url="https://weibo.com",
                priority=4, received_at=now - timedelta(minutes=40), tags=["提及"],
            ),
        ]

    def demo_task_result(self) -> PlatformRunResult:
        return PlatformRunResult(
            platform="weibo", status="demo",
            items_processed=0, message="demo 模式：模拟完成每日互动",
        )

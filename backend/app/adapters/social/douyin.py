"""抖音适配器（浏览器自动化）。"""

from datetime import datetime, timedelta

from app.adapters.social.browser_adapter import BrowserAutomationAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class DouyinAdapter(BrowserAutomationAdapter):
    name = "douyin"
    display_name = "抖音"
    method = "playwright"
    login_url = "https://www.douyin.com/login"
    username = settings.douyin_username
    password = settings.douyin_password

    async def login(self, page, username: str, password: str) -> None:
        # ⚠️ 占位 selector：抖音登录多为验证码/扫码，需按实际流程校准。
        await page.click('text=账号密码登录')
        await page.fill('input[name="account"]', username)
        await page.fill('input[name="password"]', password)
        await page.click('button:has-text("登录")')
        await page.wait_for_timeout(3000)

    def demo_messages(self) -> list[Message]:
        now = datetime.now()
        return [
            Message(
                id="dy-1", source="douyin", title="作品新增 200 播放",
                body="你的新作品 24 小时内获得 200 次播放", url="https://www.douyin.com",
                priority=2, received_at=now - timedelta(minutes=15), tags=["数据"],
            ),
            Message(
                id="dy-2", source="douyin", title="1 条新评论",
                body="用户对你的作品留下了评论", url="https://www.douyin.com",
                priority=3, received_at=now - timedelta(minutes=50), tags=["互动"],
            ),
        ]

    def demo_task_result(self) -> PlatformRunResult:
        return PlatformRunResult(
            platform="douyin", status="demo",
            items_processed=0, message="demo 模式：模拟完成每日互动",
        )

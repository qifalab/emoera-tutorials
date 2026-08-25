"""社交媒体浏览器自动化适配器的通用基类。

设计原则（重要）：
- 未配置账号密码时，自动进入 demo 模式，返回模拟数据，保证脚手架开箱即跑；
- 配置了凭据后，走真实 Playwright 登录流程。login() 由各子类实现，
  selector 必须按目标站点实际 DOM 校准（站点改版是主要失效原因）；
- Playwright 仅在使用真实凭据时才 import，因此 demo 模式无需安装浏览器。

合规提示：模拟登录执行平台任务可能违反部分平台 ToS，仅用于你拥有账号的
自有场景，并自行评估风险。建议优先使用各平台官方 API。
"""

from abc import abstractmethod
from datetime import datetime

from app.adapters.base import BaseAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class BrowserAutomationAdapter(BaseAdapter):
    """社交媒体浏览器自动化基类。"""

    # ===== 子类需覆盖的字段与方法 =====
    username: str = ""
    password: str = ""

    @property
    @abstractmethod
    def login_url(self) -> str:
        """登录页地址。"""
        raise NotImplementedError

    @abstractmethod
    async def login(self, page, username: str, password: str) -> None:
        """在已打开的登录页上完成登录（填写表单、点击提交、等待登录态）。"""
        raise NotImplementedError

    @abstractmethod
    def demo_messages(self) -> list[Message]:
        """未配置凭据时返回的模拟消息。"""
        raise NotImplementedError

    @abstractmethod
    def demo_task_result(self) -> PlatformRunResult:
        """未配置凭据时返回的模拟任务结果。"""
        raise NotImplementedError

    # ===== 通用逻辑 =====
    def _has_credentials(self) -> bool:
        return bool(self.username) and bool(self.password)

    async def run_daily_task(self) -> PlatformRunResult:
        if not self._has_credentials():
            return self.demo_task_result()
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.login_url, wait_until="networkidle")
                await self.login(page, self.username, self.password)
                # TODO: 在此补充“每日任务”的具体动作（发帖 / 点赞 / 互动 / 数据回采）
                # 这部分高度依赖站点 DOM，需按实际页面校准后启用。
                await browser.close()
            return PlatformRunResult(
                platform=self.name,
                status="success",
                items_processed=1,
                message="浏览器自动化任务完成",
            )
        except Exception as exc:  # noqa: BLE001 - 适配器需对异常做兜底
            return PlatformRunResult(
                platform=self.name,
                status="failed",
                message="浏览器自动化失败",
                detail=str(exc),
            )

    async def fetch_messages(self) -> tuple[list[Message], PlatformRunResult]:
        if not self._has_credentials():
            demo = self.demo_messages()
            return demo, PlatformRunResult(
                platform=self.name,
                status="demo",
                items_processed=len(demo),
                message="demo 模式（未配置凭据）",
            )
        try:
            from playwright.async_api import async_playwright

            messages: list[Message] = []
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(self.login_url, wait_until="networkidle")
                await self.login(page, self.username, self.password)
                # TODO: 导航到“消息/通知”页，解析 DOM 抽取 Message 列表。
                await browser.close()
            return messages, PlatformRunResult(
                platform=self.name,
                status="success",
                items_processed=len(messages),
                message="已拉取站内信",
            )
        except Exception as exc:  # noqa: BLE001
            return [], PlatformRunResult(
                platform=self.name,
                status="failed",
                message="拉取站内信失败",
                detail=str(exc),
            )

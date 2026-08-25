"""邮件适配器（IMAP，拉取未读邮件）。

使用标准库 imaplib（在异步上下文中通过 asyncio.to_thread 调用，避免阻塞事件循环）。
未配置邮箱凭据时走 demo 模式。注意：很多邮箱需要「授权码」而非登录密码（如 QQ 邮箱）。
"""

import asyncio
import email
import imaplib
from datetime import datetime
from email.header import decode_header

from app.adapters.base import BaseAdapter
from app.config import settings
from app.schemas.messages import Message
from app.schemas.tasks import PlatformRunResult


class EmailImapAdapter(BaseAdapter):
    name = "email"
    display_name = "邮件(IMAP)"
    method = "imap"

    @staticmethod
    def _decode(value: str | None) -> str:
        """解码邮件头中的 RFC2047 编码（如中文主题/发件人）。"""
        parts = decode_header(value or "")
        out = ""
        for raw, enc in parts:
            if isinstance(raw, bytes):
                out += raw.decode(enc or "utf-8", errors="ignore")
            else:
                out += raw
        return out

    def _fetch(self) -> list[Message]:
        """同步拉取未读邮件（在 to_thread 中执行，不阻塞事件循环）。"""
        mail = imaplib.IMAP4_SSL(settings.email_imap_host, settings.email_imap_port)
        try:
            mail.login(settings.email_username, settings.email_password)
            mail.select(settings.email_mailbox)
            _status, data = mail.search(None, "UNSEEN")
            ids = (data[0].split() or [])[-settings.email_max:]
            messages: list[Message] = []
            for mid in ids:
                _status, raw = mail.fetch(mid, "(RFC822)")
                msg = email.message_from_bytes(raw[0][1])
                subject = self._decode(msg.get("Subject", ""))
                from_ = self._decode(msg.get("From", ""))
                try:
                    dt = datetime.strptime(
                        msg.get("Date", ""), "%a, %d %b %Y %H:%M:%S %z"
                    ).replace(tzinfo=None)
                except Exception:  # noqa: BLE001
                    dt = datetime.now()
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            payload = part.get_payload(decode=True)
                            if payload:
                                body = payload.decode(errors="ignore")
                                break
                else:
                    payload = msg.get_payload(decode=True)
                    if payload:
                        body = payload.decode(errors="ignore")
                messages.append(
                    Message(
                        id=f"email-{mid.decode()}",
                        source="email",
                        title=subject or "(无主题)",
                        body=body[:500],
                        author=from_,
                        priority=3,
                        received_at=dt,
                        tags=["email"],
                    )
                )
            return messages
        finally:
            try:
                mail.logout()
            except Exception:  # noqa: BLE001
                pass

    async def run_daily_task(self) -> PlatformRunResult:
        # 邮件没有“每日任务”，这里返回就绪状态。
        if not settings.email_username:
            return PlatformRunResult(
                platform="email", status="demo",
                items_processed=0, message="demo 模式：未配置邮箱凭据",
            )
        return PlatformRunResult(
            platform="email", status="success",
            items_processed=0, message="邮件通道就绪",
        )

    async def fetch_messages(self) -> tuple[list[Message], PlatformRunResult]:
        if not settings.email_username:
            now = datetime.now()
            demo = [
                Message(
                    id="email-demo", source="email", title="[demo] 新邮件：周报",
                    body="这是一封演示邮件（demo 数据）", author="demo@emoera.dev",
                    priority=3, received_at=now, tags=["demo"],
                )
            ]
            return demo, PlatformRunResult(
                platform="email", status="demo",
                items_processed=1, message="demo 模式：未配置邮箱凭据",
            )
        try:
            messages = await asyncio.to_thread(self._fetch)
            return messages, PlatformRunResult(
                platform="email", status="success",
                items_processed=len(messages), message=f"已拉取 {len(messages)} 封未读邮件",
            )
        except Exception as exc:  # noqa: BLE001
            return [], PlatformRunResult(
                platform="email", status="failed",
                message="IMAP 拉取失败", detail=str(exc),
            )

"""消息聚合：多渠道拉取 + 去重 + 排序。

去重策略：
1. 同来源用 id 精确去重；
2. 跨来源用「标题+正文」的内容哈希去重（避免不同平台出现相同内容）；
排序策略：优先级降序，时间倒序。
"""

import hashlib
from datetime import datetime

from app.adapters.registry import get_message_adapters
from app.schemas.messages import Message
from app.services.store import store


def _content_hash(message: Message) -> str:
    """对标题+正文做哈希，用于跨来源去重。"""
    payload = f"{message.title}|{message.body}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def dedupe_and_sort(messages: list[Message]) -> list[Message]:
    """去重并排序，返回新的列表（不修改入参）。"""
    seen_keys: set[str] = set()
    seen_hashes: set[str] = set()
    unique: list[Message] = []
    for message in messages:
        key = message.dedupe_key or f"{message.source}:{message.id}"
        digest = _content_hash(message)
        if key in seen_keys or digest in seen_hashes:
            continue
        seen_keys.add(key)
        seen_hashes.add(digest)
        unique.append(message)
    # 优先级高在前；同优先级时，时间新在前
    unique.sort(key=lambda m: (m.priority, m.received_at), reverse=True)
    return unique


async def aggregate(refresh: bool = False) -> list[Message]:
    """从所有消息适配器拉取消息并聚合（去重+排序），结果写入 store。"""
    adapters = get_message_adapters()
    collected: list[Message] = []
    for adapter in adapters:
        try:
            messages, _result = await adapter.fetch_messages()
            collected.extend(messages)
        except Exception:  # noqa: BLE001 - 单来源失败不应拖垮整体
            continue

    unique = dedupe_and_sort(collected)
    store.set_messages(unique)
    return unique

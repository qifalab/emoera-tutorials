"""消息聚合的去重与排序逻辑单元测试（不依赖网络）。"""

from datetime import datetime, timedelta

from app.schemas.messages import Message
from app.services.message_aggregator import dedupe_and_sort


def _mk(
    msg_id: str, source: str, title: str, body: str, priority: int = 3, minutes: int = 0
) -> Message:
    return Message(
        id=msg_id,
        source=source,
        title=title,
        body=body,
        priority=priority,
        received_at=datetime.now() - timedelta(minutes=minutes),
    )


def test_dedup_by_source_id():
    msgs = [_mk("a", "weibo", "t", "b"), _mk("a", "weibo", "t", "b")]
    assert len(dedupe_and_sort(msgs)) == 1


def test_dedup_by_content_hash_across_source():
    msgs = [
        _mk("1", "weibo", "同标题", "同内容"),
        _mk("2", "email", "同标题", "同内容"),
    ]
    assert len(dedupe_and_sort(msgs)) == 1


def test_sort_priority_then_time():
    msgs = [
        _mk("1", "weibo", "低", "x", priority=2, minutes=1),
        _mk("2", "weibo", "高", "x", priority=5, minutes=5),
        _mk("3", "weibo", "中", "x", priority=3, minutes=0),
    ]
    out = dedupe_and_sort(msgs)
    assert out[0].id == "2"
    assert out[-1].id == "1"

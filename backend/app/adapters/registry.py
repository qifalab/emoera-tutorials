"""适配器注册表：服务层从这里拿到所有已接入的平台适配器。

新增平台：在 adapters/ 下新建一个继承 BaseAdapter 的类，然后在此处实例化加入即可。
"""

from app.adapters.base import BaseAdapter
from app.adapters.email_imap import EmailImapAdapter
from app.adapters.github import GitHubAdapter
from app.adapters.social.douyin import DouyinAdapter
from app.adapters.social.weibo import WeiboAdapter
from app.adapters.social.xiaohongshu import XiaohongshuAdapter


def get_task_adapters() -> list[BaseAdapter]:
    """返回参与「每日任务」的所有适配器（含社交媒体、GitHub、邮件）。"""
    return [
        WeiboAdapter(),
        XiaohongshuAdapter(),
        DouyinAdapter(),
        GitHubAdapter(),
        EmailImapAdapter(),
    ]


def get_message_adapters() -> list[BaseAdapter]:
    """返回参与「消息汇总」的所有适配器（站内信 + GitHub 通知 + 邮件）。"""
    return [
        WeiboAdapter(),
        XiaohongshuAdapter(),
        DouyinAdapter(),
        GitHubAdapter(),
        EmailImapAdapter(),
    ]

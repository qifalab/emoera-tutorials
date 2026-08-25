"""RSS 聚合抓取：为「时事新闻 / 世界动态 / 近日新梗（国内 + 国外）」提供数据。

设计：
- 每个类别配置一组 RSS 源（类别内并联抓取，单个源失败不影响其它）；
- 抓取结果统一转成 NewsItem，按发布时间倒序，并做简单去重；
- 未联网或全部失败时，回落内置示例数据，保证页面始终有内容可看。

类别划分：
- news       今日时事
- world      世界动态
- meme_cn    国内新梗
- meme_global 国外新梗
"""

import asyncio
import re
from datetime import datetime
from typing import Optional

import feedparser

from app.schemas.news import NewsItem

# 类别定义：key -> (标题, [RSS 源])
# 注意：「近日新梗」拆为「国内新梗」与「国外新梗」两个独立类别。
CATEGORIES: dict[str, tuple[str, list[str]]] = {
    "news": (
        "今日时事",
        [
            "https://feedx.net/rss/zhihu.xml",          # 知乎日报
            "https://feedx.net/rss/36kr.xml",           # 36氪（科技商业）
            "https://feedx.net/rss/thepaper.xml",       # 澎湃新闻
            "https://www.thepaper.cn/rss_news.xml",     # 澎湃新闻（官方备用）
            "https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",  # Google 新闻中文
        ],
    ),
    "world": (
        "世界动态",
        [
            "https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en",   # Google News (EN)
            "https://feeds.bbci.co.uk/news/world/rss.xml",             # BBC World
            "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",  # NYT World
            "https://feeds.reuters.com/reuters/worldNews",             # Reuters World
        ],
    ),
    "meme_cn": (
        "国内新梗",
        [
            "https://www.zhihu.com/rss",                     # 知乎热榜（综合/国内）
            "https://www.douban.com/feed/review",            # 豆瓣（文化娱乐）
            "https://sspai.com/feed",                        # 少数派（国内科技生活）
            "https://www.reddit.com/r/China_irl/.rss",       # 中文社区
        ],
    ),
    "meme_global": (
        "国外新梗",
        [
            "https://www.reddit.com/r/memes/.rss",           # Reddit memes
            "https://www.reddit.com/r/funny/.rss",           # Reddit funny
            "https://9gag.com/rss",                          # 9GAG
        ],
    ),
    # ===== 云相关板块（新增）=====
    "cloud_vendor": (
        "云服务厂商日报",
        [
            "https://aws.amazon.com/about-aws/whats-new/recent/feed/",   # AWS What's New
            "https://azure.microsoft.com/en-us/updates/feed/",           # Azure Updates
            "https://cloud.google.com/feeds/gcp-release-notes.xml",      # Google Cloud Release Notes
            "https://blog.cloudflare.com/rss/",                          # Cloudflare Blog
            "https://www.digitalocean.com/blog/feed/",                   # DigitalOcean Blog
            "https://developer.aliyun.com/feed",                         # 阿里云开发者社区
        ],
    ),
    "cloud_native": (
        "云原生 & 开源热榜",
        [
            "https://www.cncf.io/blog/feed/",                  # CNCF Blog
            "https://kubernetes.io/feed.xml",                 # Kubernetes Blog
            "https://www.cncf.io/announcements/feed/",        # CNCF Announcements
            "https://thenewstack.io/feed/",                   # The New Stack
            "https://www.infoq.cn/feed",                      # InfoQ 中文
        ],
    ),
    "ai_cloud": (
        "AI 上云动态",
        [
            "https://openai.com/blog/rss.xml",                # OpenAI Blog
            "https://huggingface.co/blog/feed.xml",          # Hugging Face Blog
            "https://blog.google/technology/ai/rss/",         # Google AI Blog
            "https://www.jiqizhixin.com/rss",                 # 机器之心
            "https://mistral.ai/news/rss.xml",                # Mistral AI
        ],
    ),
}

MAX_PER_SOURCE = 8
MAX_PER_SECTION = 15


def _published(dt: Optional[datetime], entry: dict) -> datetime:
    """从 feedparser entry 提取发布时间，失败则回落当前时间。"""
    if dt:
        return dt
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return datetime(*parsed[:6])
            except Exception:  # noqa: BLE001
                continue
    return datetime.now()


async def fetch_feed(url: str, category: str) -> list[NewsItem]:
    """抓取单个 RSS 源并转成 NewsItem（同步库放到线程池，避免阻塞）。"""
    def _load() -> list[NewsItem]:
        items: list[NewsItem] = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_PER_SOURCE]:
                title = getattr(entry, "title", "").strip()
                if not title:
                    continue
                summary = getattr(entry, "summary", "") or ""
                # 去掉 HTML 标签，保留纯文本
                summary = re.sub(r"<[^>]+>", "", summary).strip()
                items.append(
                    NewsItem(
                        title=title,
                        summary=summary[:280],
                        url=getattr(entry, "link", None),
                        source=feed.feed.get("title", "") if hasattr(feed, "feed") else "",
                        published_at=_published(None, entry),
                        category=category,
                    )
                )
        except Exception:  # noqa: BLE001
            return []
        return items

    return await asyncio.to_thread(_load)


async def fetch_section(key: str) -> list[NewsItem]:
    """抓取某类别下所有 RSS 源，合并去重并按时间倒序。"""
    _title, sources = CATEGORIES.get(key, ("", []))
    results = await asyncio.gather(
        *(fetch_feed(url, key) for url in sources),
        return_exceptions=True,
    )
    merged: list[NewsItem] = []
    seen: set[str] = set()
    for res in results:
        if isinstance(res, Exception):
            continue
        for item in res:
            if item.title in seen:
                continue
            seen.add(item.title)
            merged.append(item)
    merged.sort(key=lambda i: i.published_at or datetime.min, reverse=True)
    return merged[:MAX_PER_SECTION]


def demo_items(key: str) -> list[NewsItem]:
    """内置示例数据（离线/未配置时保证页面有内容）。"""
    demos = {
        "news": [
            NewsItem(
                title="AI 大模型进入应用爆发期：多行业落地加速",
                summary="从办公、设计到金融，大模型正快速渗透各行业工作流，应用侧竞争日趋激烈。",
                url="https://example.com/news/ai-apps",
                source="示例·时事",
                category="news",
            ),
            NewsItem(
                title="新能源车 7 月销量再创新高，渗透率持续攀升",
                summary="多家车企公布月度销量数据，行业整体保持高速增长态势。",
                source="示例·时事",
                category="news",
            ),
            NewsItem(
                title="多地优化营商环境，民营经济迎利好政策",
                summary="近期多部门密集出台支持举措，为市场主体注入信心。",
                source="示例·时事",
                category="news",
            ),
        ],
        "world": [
            NewsItem(
                title="Global Markets React to Latest Central Bank Signals",
                summary="Investors weigh inflation data as major economies signal policy direction.",
                url="https://example.com/world/markets",
                source="示例·世界",
                category="world",
            ),
            NewsItem(
                title="International Climate Talks Reach New Agreement",
                summary="Nations commit to updated emissions targets in latest round of negotiations.",
                source="示例·世界",
                category="world",
            ),
        ],
        "meme_cn": [
            NewsItem(
                title="「遥遥领先」式玩梗出圈，网友二创不断",
                summary="一个热梗的诞生：从一句台词到全网表情包与二创视频。",
                url="https://example.com/meme/yaoyaolingxian",
                source="示例·国内新梗",
                category="meme_cn",
            ),
            NewsItem(
                title="「City 不 City」之后，年轻人又有了新口头禅",
                summary="网络热词迭代加快，语言梗成为社交货币的一部分。",
                source="示例·国内新梗",
                category="meme_cn",
            ),
            NewsItem(
                title="「班味」成社交热词，打工人集体共鸣",
                summary="职场梗频频出圈，折射出当下年轻人的工作与精神状态。",
                source="示例·国内新梗",
                category="meme_cn",
            ),
        ],
        "meme_global": [
            NewsItem(
                title="\"Skibidi\" 席卷短视频，成为年度现象级梗",
                summary="从 YouTube 到 TikTok，一个无厘头意象演化成全球通用的网络语言。",
                url="https://example.com/meme/skibidi",
                source="示例·国外新梗",
                category="meme_global",
            ),
            NewsItem(
                title="\"Brain Rot\" 当选年度词汇，网络迷因文化被正名",
                summary="词典机构将这股短视频时代的注意力现象收录，引发广泛讨论。",
                source="示例·国外新梗",
                category="meme_global",
            ),
            NewsItem(
                title="Reddit 上的 \"POV\" 梗又进化了",
                summary="第一人称视角叙事梗持续变形，成为跨平台的内容模板。",
                source="示例·国外新梗",
                category="meme_global",
            ),
        ],
        "cloud_vendor": [
            NewsItem(
                title="AWS 推出新一代 Serverless 容器服务，冷启动降至毫秒级",
                summary="新服务进一步简化容器化部署，按用量计费，适合突发流量场景。",
                url="https://example.com/cloud/aws-serverless",
                source="示例·云服务",
                category="cloud_vendor",
            ),
            NewsItem(
                title="阿里云宣布对象存储降价，进一步拉低企业上云成本",
                summary="多家云厂商近期密集调整价格，存储与带宽成为竞争焦点。",
                url="https://example.com/cloud/aliyun-price",
                source="示例·云服务",
                category="cloud_vendor",
            ),
            NewsItem(
                title="Azure 新增多区域合规中心，满足数据驻留要求",
                summary="面向金融与政务客户，强化数据主权与合规能力。",
                url="https://example.com/cloud/azure-compliance",
                source="示例·云服务",
                category="cloud_vendor",
            ),
        ],
        "cloud_native": [
            NewsItem(
                title="Kubernetes 1.33 发布：引入更细粒度的调度优先级",
                summary="新版本在调度器与可观测性上做了多项改进，运维更省心。",
                url="https://example.com/cn/k8s-1-33",
                source="示例·云原生",
                category="cloud_native",
            ),
            NewsItem(
                title="CNCF 新增毕业级项目，服务网格生态再扩容",
                summary="云原生版图持续扩张，可观测性与安全成为新热点。",
                url="https://example.com/cn/cncf-graduation",
                source="示例·云原生",
                category="cloud_native",
            ),
            NewsItem(
                title="eBPF 在可观测性场景加速落地，替代部分 Sidecar",
                summary="内核级数据采集降低开销，成为云原生监控新范式。",
                url="https://example.com/cn/ebpf-observability",
                source="示例·云原生",
                category="cloud_native",
            ),
        ],
        "ai_cloud": [
            NewsItem(
                title="OpenAI 发布新模型并下调 API 价格，推理成本再降",
                summary="新模型在长上下文与工具调用上增强，开发者可更低成本接入。",
                url="https://example.com/ai/openai-new",
                source="示例·AI上云",
                category="ai_cloud",
            ),
            NewsItem(
                title="通义千问开源新版本，云端推理服务同步上线",
                summary="国产大模型持续开源，配套云端部署方案降低使用门槛。",
                url="https://example.com/ai/qwen-open",
                source="示例·AI上云",
                category="ai_cloud",
            ),
            NewsItem(
                title="Hugging Face 推出 Serverless 推理，按 token 计费",
                summary="模型即服务进一步普及，小团队也能零运维跑大模型。",
                url="https://example.com/ai/hf-serverless",
                source="示例·AI上云",
                category="ai_cloud",
            ),
        ],
    }
    return demos.get(key, [])


async def fetch_all_sections() -> dict[str, list[NewsItem]]:
    """抓取全部类别，返回 {key: [items]}。若某类别为空则回落示例数据。"""
    keys = list(CATEGORIES.keys())
    tasks = {k: fetch_section(k) for k in keys}
    result: dict[str, list[NewsItem]] = {}
    for k, task in tasks.items():
        try:
            items = await task
        except Exception:  # noqa: BLE001
            items = []
        result[k] = items or demo_items(k)
    return result

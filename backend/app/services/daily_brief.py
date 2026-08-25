"""每日速报生成：抓取 RSS -> 交给 AI 总结 -> 返回结构化速报。

流程：
1. 从 RSS 拉取各个类别（时事/世界/国内新梗/国外新梗）；
2. 若配置了 AI key，对每个类别做 AI 摘要 + 生成整体导语；
3. 未配置 AI 时，直接返回原文标题（附提示语），保证可用性。

对外提供两个粒度：
- generate_brief()：一次性生成全部类别（聚合页/速览用）；
- generate_section(category)：仅生成单个类别（独立页面按需加载用）。
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional

from app.schemas.news import BriefSection, DailyBrief
from app.services import rss_fetcher
from app.services.ai_client import get_ai_client

# 类别顺序与标题（meme 拆为国内/国外；新增云相关三类）
CATEGORY_KEYS = ["news", "world", "meme_cn", "meme_global", "cloud_vendor", "cloud_native", "ai_cloud"]
CATEGORY_TITLES = {
    "news": "今日时事",
    "world": "世界动态",
    "meme_cn": "国内新梗",
    "meme_global": "国外新梗",
    "cloud_vendor": "云服务厂商日报",
    "cloud_native": "云原生 & 开源热榜",
    "ai_cloud": "AI 上云动态",
}

# 并发上限：同一时刻最多跑 2 个 AI 请求，避免拖慢响应
_AI_SEM = asyncio.Semaphore(2)
# 逐条总结时放宽到 4 个并发
_AI_SEM_ITEM = asyncio.Semaphore(4)

# 模型拒答特征词（用于把"无法回答"的回帖降级，避免把拒答当总结展示）
_REFUSAL_HINTS = (
    "抱歉，我", "抱歉，作为", "无法回答", "无法提供", "无法为您", "不能提供", "不能回答",
    "作为人工智能", "作为AI", "作为人工智能助手", "涉及政治", "涉及敏感", "涉及违法违规",
    "我无法提供", "我无法回答", "我不能提供", "我不能回答", "不宜回答", "不方便回答",
)


def _fmt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%m-%d %H:%M")


def _build_section_prompt(key: str, items) -> str:
    """把一个类别的条目拼成给 AI 的文本。"""
    lines = []
    for i, it in enumerate(items[:8], 1):
        time_str = _fmt_dt(it.published_at) if it.published_at else ""
        src = f"[{it.source}]" if it.source else ""
        lines.append(f"{i}. {it.title} {src}（{time_str}）")
        if it.summary:
            lines.append(f"   {it.summary[:120]}")
    header = CATEGORY_TITLES.get(key, key)
    return f"以下是「{header}」的原始条目列表：\n" + "\n".join(lines)


async def _ai_summarize_section(key: str, items) -> str:
    """调用 AI 生成类别总结；失败返回空串，由上层回落。"""
    client = get_ai_client()
    if not client.has_key():
        return ""
    prompt = _build_section_prompt(key, items)
    messages = [
        {
            "role": "system",
            "content": "你是一个资深新闻编辑。请用中文把下面这些条目整合成一段 120 字以内的"
            "「板块速览」，点出最重要的发展脉络与看点，语气凝练、有洞察，不要罗列条目本身。",
        },
        {"role": "user", "content": prompt},
    ]
    async with _AI_SEM:
        return (await client.chat(messages, temperature=0.5, max_tokens=400)) or ""


async def _ai_overview(sections: list[BriefSection]) -> str:
    """用 AI 生成整份速报的开篇导语。"""
    client = get_ai_client()
    if not client.has_key():
        return ""
    lines = []
    for sec in sections:
        top = sec.items[0].title if sec.items else ""
        lines.append(f"- {sec.title}：{top}")
    messages = [
        {
            "role": "system",
            "content": "你是每日资讯主编。请用中文写一句 60 字以内的导语，点出今天最值得关注的"
            "几条动态及其背后的趋势，语气克制有深度。直接输出导语，不要加标题。",
        },
        {"role": "user", "content": "今天各板块要点如下：\n" + "\n".join(lines)},
    ]
    async with _AI_SEM:
        return (await client.chat(messages, temperature=0.6, max_tokens=200)) or ""


def _looks_like_refusal(text: str) -> bool:
    """判断模型回帖是否像拒答（避免把拒答当总结展示）。"""
    t = (text or "").strip()
    if not t or len(t) < 6:
        return True
    return any(h in t for h in _REFUSAL_HINTS)


async def _ai_summarize_item(item, title_hint: str = "") -> Optional[str]:
    """对单条资讯生成一句话客观总结。

    提示词采用中性、事实提炼口径，不夹带任何绕过安全护栏的指令。
    模型拒答 / 失败时返回 None，由上层回落到 RSS 原文摘要（优雅降级）。
    """
    client = get_ai_client()
    if not client.has_key():
        return None
    body = (item.summary or "").strip()[:300]
    prompt = (
        "请用一句中文（不超过 40 字）客观提炼这条资讯的核心事实要点，"
        "只陈述事实，不做主观评价：\n"
        f"标题：{item.title or ''}\n正文：{body}"
    )
    messages = [
        {
            "role": "system",
            "content": "你是严谨的中文资讯编辑，负责对单条资讯做客观的事实提炼，不输出主观评价与延伸判断。",
        },
        {"role": "user", "content": prompt},
    ]
    async with _AI_SEM_ITEM:
        try:
            out = await client.chat(messages, temperature=0.3, max_tokens=80)
        except Exception:  # noqa: BLE001 - 上层负责展示
            return None
    if not out or _looks_like_refusal(out):
        return None
    return out.strip()


async def _enrich_items_with_ai(items) -> None:
    """为条目列表逐条补充 AI 总结（就地写入 NewsItem.summary_ai）。"""
    if not items:
        return
    results = await asyncio.gather(*(_ai_summarize_item(it) for it in items))
    for it, s in zip(items, results):
        if s:
            it.summary_ai = s


async def generate_section(category: str, enrich: bool = True) -> BriefSection:
    """生成单个类别的板块（抓取 + 可选 AI 总结 + 可选逐条总结）。"""
    items = await rss_fetcher.fetch_section(category)
    if not items:
        items = rss_fetcher.demo_items(category)
    client = get_ai_client()
    using_ai = client.has_key()
    summary = await _ai_summarize_section(category, items) if using_ai else ""
    # 逐条 AI 总结：仅对单页按需加载开启；聚合速览(generate_brief)为控速默认关闭
    if using_ai and enrich:
        await _enrich_items_with_ai(items)
    return BriefSection(
        key=category,
        title=CATEGORY_TITLES.get(category, category),
        summary=summary,
        items=items,
    )


async def generate_brief() -> DailyBrief:
    """生成完整速报（全部类别）。"""
    sections: list[BriefSection] = []
    for key in CATEGORY_KEYS:
        # 聚合速览关闭逐条总结以控制耗时，逐条总结由各独立页面按需开启
        sections.append(await generate_section(key, enrich=False))

    client = get_ai_client()
    using_ai = client.has_key()

    overview = await _ai_overview(sections) if using_ai else ""
    ai_note = (
        ""
        if using_ai
        else "未配置 AI Key，当前为原文列表模式；在「设置」中填入 Key 后即可获得 AI 总结。"
    )
    return DailyBrief(
        title="今日速报",
        overview=overview,
        sections=sections,
        using_ai=using_ai,
        ai_note=ai_note,
    )

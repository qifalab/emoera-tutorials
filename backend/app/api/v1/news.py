"""每日速报相关接口。

提供两种粒度：
- /brief：一次性返回全部类别（聚合速览）；
- /section/{category}：仅返回单个类别，供各独立页面按需加载。
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.schemas.news import BriefSection, DailyBrief
from app.services.daily_brief import generate_brief, generate_section

router = APIRouter(prefix="/news", tags=["news"])

CACHE_TTL = timedelta(minutes=30)

# 整份速报缓存
_brief_cache: Optional[DailyBrief] = None
_brief_cache_at: Optional[datetime] = None

# 单类别缓存
_section_cache: dict[str, BriefSection] = {}
_section_cache_at: dict[str, datetime] = {}

VALID_CATEGORIES = {"news", "world", "meme_cn", "meme_global", "cloud_vendor", "cloud_native", "ai_cloud"}


def _brief_fresh() -> bool:
    return (
        _brief_cache is not None
        and _brief_cache_at is not None
        and datetime.now() - _brief_cache_at < CACHE_TTL
    )


def _section_fresh(category: str) -> bool:
    cached_at = _section_cache_at.get(category)
    return cached_at is not None and datetime.now() - cached_at < CACHE_TTL


@router.get("/brief", response_model=DailyBrief)
async def get_brief(refresh: bool = False) -> DailyBrief:
    """获取今日速报；refresh=true 时强制重新生成。"""
    global _brief_cache, _brief_cache_at
    if not refresh and _brief_fresh():
        return _brief_cache  # type: ignore[return-value]
    brief = await generate_brief()
    _brief_cache = brief
    _brief_cache_at = datetime.now()
    return brief


@router.post("/brief/refresh", response_model=DailyBrief)
async def refresh_brief() -> DailyBrief:
    """强制重新生成一次速报（抓取最新 + 重新 AI 总结）。"""
    return await get_brief(refresh=True)


@router.get("/section/{category}", response_model=BriefSection)
async def get_section(category: str, refresh: bool = False) -> BriefSection:
    """获取单个类别的板块（news / world / meme_cn / meme_global）。"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"未知类别：{category}")
    if not refresh and _section_fresh(category):
        return _section_cache[category]
    sec = await generate_section(category)
    _section_cache[category] = sec
    _section_cache_at[category] = datetime.now()
    return sec


@router.post("/section/{category}/refresh", response_model=BriefSection)
async def refresh_section(category: str) -> BriefSection:
    """强制重新抓取并生成单个类别的板块。"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"未知类别：{category}")
    sec = await generate_section(category)
    _section_cache[category] = sec
    _section_cache_at[category] = datetime.now()
    return sec

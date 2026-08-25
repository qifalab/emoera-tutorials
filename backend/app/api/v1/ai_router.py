"""AI 模型推荐相关接口。

提供两种粒度（对齐 news 模块）：
- /ai-models：一次性返回全部板块（civitai / hf_text / hf_llm / resources）；
- /ai-models/section/{category}：仅返回单个板块，供独立页面按需加载。
均带 10 分钟缓存，refresh=true 时强制重新抓取。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException

from app.schemas.ai_models import AiModelSection, AiModelsResponse
from app.services.ai_model_fetcher import generate_ai_models, generate_ai_models_section

router = APIRouter(prefix="/ai-models", tags=["ai-models"])

CACHE_TTL = timedelta(minutes=10)

_brief_cache: AiModelsResponse | None = None
_brief_cache_at: datetime | None = None
_section_cache: dict[str, AiModelSection] = {}
_section_cache_at: dict[str, datetime] = {}

VALID_CATEGORIES = {"civitai", "hf_text", "hf_llm", "resources"}


def _brief_fresh() -> bool:
    return (
        _brief_cache is not None
        and _brief_cache_at is not None
        and datetime.now() - _brief_cache_at < CACHE_TTL
    )


def _section_fresh(category: str) -> bool:
    cached_at = _section_cache_at.get(category)
    return cached_at is not None and datetime.now() - cached_at < CACHE_TTL


@router.get("", response_model=AiModelsResponse)
async def get_ai_models(refresh: bool = False) -> AiModelsResponse:
    """获取 AI 模型推荐；refresh=true 时强制重新抓取。"""
    global _brief_cache, _brief_cache_at
    if not refresh and _brief_fresh():
        return _brief_cache  # type: ignore[return-value]
    resp = await generate_ai_models()
    _brief_cache = resp
    _brief_cache_at = datetime.now()
    return resp


@router.post("/refresh", response_model=AiModelsResponse)
async def refresh_ai_models() -> AiModelsResponse:
    """强制重新抓取并生成一次。"""
    return await get_ai_models(refresh=True)


@router.get("/section/{category}", response_model=AiModelSection)
async def get_section(category: str, refresh: bool = False) -> AiModelSection:
    """获取单个板块（civitai / hf_text / hf_llm / resources）。"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"未知类别：{category}")
    if not refresh and _section_fresh(category):
        return _section_cache[category]
    sec = await generate_ai_models_section(category)
    _section_cache[category] = sec
    _section_cache_at[category] = datetime.now()
    return sec


@router.post("/section/{category}/refresh", response_model=AiModelSection)
async def refresh_section(category: str) -> AiModelSection:
    """强制重新抓取并生成单个板块。"""
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=404, detail=f"未知类别：{category}")
    sec = await generate_ai_models_section(category)
    _section_cache[category] = sec
    _section_cache_at[category] = datetime.now()
    return sec

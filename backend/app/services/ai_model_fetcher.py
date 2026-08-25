"""AI 模型推荐抓取：CivitAI（生图模型）+ Hugging Face（文字 / 大模型）。

设计（对齐 rss_fetcher 的「实时优先 + demo 兜底」思路）：
- CivitAI：公开 API，按下载量取最火生图模型（Checkpoint / LoRA 等）；
- Hugging Face：公开 API，按下载量取文字/对话模型，按点赞取近期最火大模型；
- 任一源联网失败都回落内置示例，保证页面始终有内容；
- resources（各种资源推荐）为精选站点的固定推荐，无需联网。

对外：
- generate_ai_models()：一次性返回全部板块（聚合页用）；
- generate_ai_models_section(category)：仅返回单个板块（独立页面按需加载用）。
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import Optional

import httpx

from app.schemas.ai_models import AiModelItem, AiModelSection, AiModelsResponse

HTTP_TIMEOUT = 15
UA = {"User-Agent": "Mozilla/5.0 (compatible; EmoeraBot/1.0)"}

# 板块定义：key -> (标题, 说明)
SECTIONS = {
    "civitai": ("CivitAI · 今日最火生图模型", "Stable Diffusion / FLUX / LoRA 等，按下载量排序"),
    "hf_text": ("Hugging Face · 热门文字 / 对话模型", "text-generation 类，按下载量排序（你想下载的文字 AI）"),
    "hf_llm": ("Hugging Face · 大模型推荐", "近期点赞最高的开源大模型（LLM）"),
    "resources": ("各种 AI 资源推荐", "模型 / 数据集 / 社区一站式下载站"),
}

MAX_PER_SECTION = 20


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _fmt_dt(iso: Optional[str]) -> Optional[str]:
    """把 ISO 时间转成简洁展示串（MM-DD HH:MM），失败返回 None。"""
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# CivitAI（生图模型）
# ---------------------------------------------------------------------------
async def fetch_civitai() -> list[AiModelItem]:
    # 注意：CivitAI 新版 API 不再接受逗号分隔的 types（会返回 ZodError 400），
    # 故不传 types，直接按下载量取全部最火模型（均为生图类）。
    url = "https://civitai.com/api/v1/models"
    params = {"sort": "Most Downloaded", "limit": MAX_PER_SECTION}
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=UA) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:  # noqa: BLE001
        return []

    items: list[AiModelItem] = []
    for m in data.get("items", []):
        versions = m.get("modelVersions") or []
        image_url = None
        for v in versions:
            imgs = v.get("images") or []
            if imgs and imgs[0].get("url"):
                image_url = imgs[0]["url"]
                break
        stats = m.get("stats") or {}
        # CivitAI 真实字段为 downloadCount / thumbsUpCount（非 downloads/favorites）
        raw_tags = m.get("tags") or []
        tags = [t for t in raw_tags if isinstance(t, str) and t][:6]
        items.append(AiModelItem(
            name=m.get("name", "未命名模型"),
            description=_strip_html(m.get("description", ""))[:200],
            url=f"https://civitai.com/models/{m.get('id')}",
            source="CivitAI",
            image_url=image_url,
            downloads=int(stats.get("downloadCount", 0) or 0),
            likes=int(stats.get("thumbsUpCount", 0) or 0),
            tags=tags[:6],
            updated_at=_fmt_dt(m.get("updatedAt")),
            category="civitai",
        ))
    return items


# ---------------------------------------------------------------------------
# Hugging Face（文字 / 大模型）
# ---------------------------------------------------------------------------
async def _fetch_hf(sort_key: str, category: str) -> list[AiModelItem]:
    url = "https://huggingface.co/api/models"
    params = {
        "sort": sort_key,
        "direction": "-1",
        "limit": MAX_PER_SECTION,
        "pipeline_tag": "text-generation",
    }
    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, headers=UA) as client:
            r = await client.get(url, params=params)
            r.raise_for_status()
            data = r.json()
    except Exception:  # noqa: BLE001
        return []

    items: list[AiModelItem] = []
    for m in data:
        model_id = m.get("id", "")
        if not model_id:
            continue
        tags = [t for t in (m.get("tags") or []) if t not in ("transformers", "safetensors")]
        items.append(AiModelItem(
            name=model_id,
            description=m.get("pipeline_tag", "text-generation"),
            url=f"https://huggingface.co/{model_id}",
            source="Hugging Face",
            downloads=int(m.get("downloads", 0) or 0),
            likes=int(m.get("likes", 0) or 0),
            tags=tags[:5],
            updated_at=_fmt_dt(m.get("lastModified") or m.get("createdAt")),
            category=category,
        ))
    return items


async def fetch_hf_text() -> list[AiModelItem]:
    return await _fetch_hf("downloads", "hf_text")


async def fetch_hf_llm() -> list[AiModelItem]:
    return await _fetch_hf("likes", "hf_llm")


# ---------------------------------------------------------------------------
# 各种资源推荐（精选，固定内容，无需联网）
# ---------------------------------------------------------------------------
def curated_resources() -> list[AiModelItem]:
    data = [
        ("Hugging Face", "全球最大的开源模型 / 数据集 / Spaces 社区，一站式下载与在线体验。",
         "https://huggingface.co/models", ["模型", "数据集", "Spaces"]),
        ("Civitai", "最火的 AI 生图模型社区，SD / FLUX / LoRA 模型直接下载与在线生图。",
         "https://civitai.com/models", ["生图", "LoRA", "社区"]),
        ("Ollama", "本地一键拉取并运行大模型（Llama / Qwen / DeepSeek 等），隐私友好。",
         "https://ollama.com/library", ["本地", "LLM", "开源"]),
        ("ModelScope 魔搭", "阿里达摩院开源社区，国内访问快，覆盖大模型与数据集。",
         "https://modelscope.cn", ["国内", "大模型", "数据集"]),
        ("LiblibAI 哩布哩布", "国内领先的 AI 绘画模型分享社区，海量 LoRA / 工作流。",
         "https://www.liblib.art", ["生图", "LoRA", "国内"]),
        ("Kaggle Models", "Kaggle 提供的模型库，覆盖 CV / NLP / 表格，可直接 Notebooks 调用。",
         "https://www.kaggle.com/models", ["数据集", "CV", "NLP"]),
        ("Papers with Code", "追踪 SOTA 论文与对应开源实现，找前沿模型与基准。",
         "https://paperswithcode.com", ["论文", "SOTA", "代码"]),
        ("Replicate", "云端按需调用上千个开源模型（文生图 / 语音 / 大模型），API 友好。",
         "https://replicate.com/explore", ["API", "云端", "多模态"]),
    ]
    return [
        AiModelItem(
            name=n, description=d, url=u, source="精选",
            tags=tags, category="resources",
        )
        for n, d, u, tags in data
    ]


# ---------------------------------------------------------------------------
# demo 兜底
# ---------------------------------------------------------------------------
def demo_items(key: str) -> list[AiModelItem]:
    demos = {
        "civitai": [
            AiModelItem(name="FLUX.1 [dev]", description="Black Forest Labs 开源的旗舰级文生图基座，画质与提示词遵循俱佳。",
                        url="https://civitai.com/models/726909", source="CivitAI",
                        downloads=120000, likes=8500, tags=["FLUX", "文生图", "SD3"], category="civitai",
                        updated_at="08-15 10:20"),
            AiModelItem(name="Realistic Vision V6.0", description="老牌写实风 Checkpoint，人物与皮肤质感表现稳定。",
                        url="https://civitai.com/models/4201", source="CivitAI",
                        downloads=980000, likes=12000, tags=["写实", "Checkpoint"], category="civitai",
                        updated_at="08-14 09:05"),
            AiModelItem(name="DreamShaper XL", description="通用风格化 SDXL 模型，动漫 / 写实皆宜，社区用量极大。",
                        url="https://civitai.com/models/112902", source="CivitAI",
                        downloads=760000, likes=9100, tags=["SDXL", "通用"], category="civitai",
                        updated_at="08-13 22:40"),
        ],
        "hf_text": [
            AiModelItem(name="Qwen/Qwen3-0.6B", description="通义千问 3 代小模型，轻量可本地部署。",
                        url="https://huggingface.co/Qwen/Qwen3-0.6B", source="Hugging Face",
                        downloads=29244641, likes=1514, tags=["qwen3", "text-generation"], category="hf_text",
                        updated_at="08-15 03:40"),
            AiModelItem(name="meta-llama/Llama-3.2-3B", description="Llama 3.2 轻量指令模型，多语言能力强。",
                        url="https://huggingface.co/meta-llama/Llama-3.2-3B", source="Hugging Face",
                        downloads=5100000, likes=920, tags=["llama", "instruction"], category="hf_text",
                        updated_at="08-14 12:00"),
            AiModelItem(name="Google/gemma-2-9b", description="Gemma 2 开源大模型，9B 规模性价比突出。",
                        url="https://huggingface.co/google/gemma-2-9b", source="Hugging Face",
                        downloads=4300000, likes=780, tags=["gemma", "open"], category="hf_text",
                        updated_at="08-13 18:30"),
        ],
        "hf_llm": [
            AiModelItem(name="deepseek-ai/DeepSeek-V3", description="深度求索开源 MoE 大模型，推理与代码能力领先。",
                        url="https://huggingface.co/deepseek-ai/DeepSeek-V3", source="Hugging Face",
                        downloads=3800000, likes=3200, tags=["MoE", "推理"], category="hf_llm",
                        updated_at="08-15 08:10"),
            AiModelItem(name="Qwen/Qwen3-235B-A22B", description="通义千问 3 代超大 MoE，激活 22B 即可对标旗舰。",
                        url="https://huggingface.co/Qwen/Qwen3-235B-A22B", source="Hugging Face",
                        downloads=2100000, likes=2800, tags=["MoE", "超大模型"], category="hf_llm",
                        updated_at="08-14 20:00"),
            AiModelItem(name="mistralai/Mixtral-8x7B", description="经典开源 MoE，8x7B 高效推理广受好评。",
                        url="https://huggingface.co/mistralai/Mixtral-8x7B", source="Hugging Face",
                        downloads=6700000, likes=2100, tags=["MoE", "欧洲"], category="hf_llm",
                        updated_at="08-13 11:25"),
        ],
    }
    return demos.get(key, [])


_FETCHERS = {
    "civitai": fetch_civitai,
    "hf_text": fetch_hf_text,
    "hf_llm": fetch_hf_llm,
    "resources": None,  # resources 为精选固定内容
}


async def generate_ai_models_section(category: str) -> AiModelSection:
    title, summary = SECTIONS.get(category, (category, ""))
    if category == "resources":
        items = curated_resources()
    else:
        fetcher = _FETCHERS.get(category)
        items = await fetcher() if fetcher else []
        if not items:
            items = demo_items(category)
    return AiModelSection(key=category, title=title, summary=summary, items=items[:MAX_PER_SECTION])


async def generate_ai_models() -> AiModelsResponse:
    sections: list[AiModelSection] = []
    live_flags: list[bool] = []
    for key in SECTIONS:
        if key == "resources":
            sec = await generate_ai_models_section(key)
            live_flags.append(True)  # 精选内容恒为「有内容」
        else:
            fetcher = _FETCHERS[key]
            items = await fetcher()
            live = bool(items)
            live_flags.append(live)
            sec = AiModelSection(
                key=key, title=SECTIONS[key][0], summary=SECTIONS[key][1],
                items=(items or demo_items(key))[:MAX_PER_SECTION],
            )
        sections.append(sec)

    any_live = any(live_flags)
    note = "" if any_live else "未联网获取实时数据，当前为内置示例；联网后将自动展示今日最火模型。"
    return AiModelsResponse(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        sections=sections,
        live=any_live,
        note=note,
    )

"""AI 模型推荐相关数据结构。

板块（section）与「每日速报」的 BriefSection 平级，但条目使用更贴合
模型下载站（CivitAI / Hugging Face）的字段：预览图、下载量、点赞、标签等。
"""

from typing import Optional

from pydantic import BaseModel, Field


class AiModelItem(BaseModel):
    """一个 AI 模型 / 资源条目（来自 CivitAI、Hugging Face 或精选推荐）。"""

    name: str
    description: str = ""      # 模型简介（回落用原文）
    url: Optional[str] = None
    source: str = ""           # civitai / huggingface / 精选
    image_url: Optional[str] = None  # 预览图（CivitAI 生图模型有）
    downloads: int = 0
    likes: int = 0
    tags: list[str] = Field(default_factory=list)
    updated_at: Optional[str] = None  # ISO 字符串，仅用于展示（如更新时间）


class AiModelSection(BaseModel):
    """AI 模型推荐的一个板块：生图模型 / 文字模型 / 大模型 / 资源。"""

    key: str                  # civitai / hf_text / hf_llm / resources
    title: str
    summary: str = ""         # 板块说明
    items: list[AiModelItem] = Field(default_factory=list)


class AiModelsResponse(BaseModel):
    """一次完整的 AI 模型推荐响应。"""

    generated_at: str = ""
    sections: list[AiModelSection] = Field(default_factory=list)
    live: bool = True         # 是否取到真实数据（全 demo 时为 False）
    note: str = ""            # 说明（如未联网 / 全 demo 时的提示）

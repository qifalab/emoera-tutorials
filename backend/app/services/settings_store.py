"""AI 设置的持久化存储（JSON 文件，位于 backend/app/data/）。

为什么不用 .env：运行时写入 .env 容易破坏格式、且 key 属于敏感信息。
这里单独存一个 gitignore 的 JSON，读写简单、可控、可脱敏展示。

「清除」语义：传入的字段用 None 表示"不修改"，用显式空字符串 "" 表示"清空/删除"，
避免调用方无法删除已保存的配置。
"""

import json
import os
from typing import Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "ai_settings.json")


def _load() -> dict:
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def _save(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SETTINGS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, SETTINGS_FILE)


def get_ai_setting(key: str, default: str = "") -> str:
    """读取单个设置项。"""
    data = _load()
    return data.get(key, default)


def set_ai_settings(
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict:
    """更新 AI 设置（None 表示不修改该字段；"" 表示清空该字段）。"""
    data = _load()
    if base_url is not None:
        if base_url.strip():
            data["base_url"] = base_url.strip()
        else:
            data.pop("base_url", None)
    if model is not None:
        if model.strip():
            data["model"] = model.strip()
        else:
            data.pop("model", None)
    if api_key is not None:
        if api_key.strip():
            data["api_key"] = api_key.strip()
        else:
            data.pop("api_key", None)
    _save(data)
    return data


def load_ai_runtime_from_store() -> None:
    """把持久化的设置加载进 ai_client 的运行时配置（启动时调用）。

    优先级：持久化文件（网站「设置」页保存的内容）> 环境变量（含 .env）> 默认值。
    """
    from app.config import settings as cfg

    from app.services.ai_client import ai_runtime

    data = _load()
    ai_runtime.base_url = (
        data.get("base_url") or cfg.ai_base_url or ""
    )
    ai_runtime.model = (
        data.get("model") or cfg.ai_model or ""
    )
    ai_runtime.api_key = (
        data.get("api_key") or cfg.ai_api_key or ""
    )

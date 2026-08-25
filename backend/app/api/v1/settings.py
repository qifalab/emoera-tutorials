"""AI 设置管理接口：读写 base_url / model / api_key（脱敏展示）+ 测试连接 + 模型列表。

安全说明：
- 配置类接口要求携带管理令牌（后端通过 EMOERA_ADMIN_TOKEN 设置）；未设置时默认放行
  （便于本地/内网使用），设置后即强制校验，防止公网下配置被篡改、API Key 被窃取。
- 所有出站 base_url 均经过 SSRF 校验（仅公网 http/https，禁止内网/保留地址）。
"""

import hmac
from typing import Optional

from fastapi import APIRouter, Header, HTTPException

from app.config import settings
from app.schemas.news import (
    AiModelsResult,
    AiSettings,
    AiSettingsInput,
    AiTestResult,
)
from app.services import settings_store
from app.services.ai_client import (
    AiClient,
    AiRuntimeConfig,
    ai_runtime,
    get_ai_client,
    mask_key,
    validate_base_url,
)

router = APIRouter(prefix="/settings", tags=["settings"])

# 预置的常用服务商模板（前端"自动获取模型"前方便选择）
KNOWN_PROVIDERS = {
    "openai": ("https://api.openai.com/v1", "OpenAI"),
    "deepseek": ("https://api.deepseek.com/v1", "DeepSeek"),
    "dashscope": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "阿里云·通义千问"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "智谱 AI"),
    "moonshot": ("https://api.moonshot.cn/v1", "月之暗面 Kimi"),
    "siliconflow": ("https://api.siliconflow.cn/v1", "硅基流动"),
}


def _admin_token() -> str:
    """返回后端配置的管理令牌（环境变量）。"""
    return settings.admin_token.strip()


def _require_admin_token(provided: str) -> None:
    """若启用了管理令牌，则校验；未启用则放行。"""
    expected = _admin_token()
    if not expected:
        return  # 未启用鉴权，放行（本地/内网场景）
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="管理令牌错误或无权限")


def _effective_key() -> str:
    """运行时 key 优先，其次环境变量。"""
    if ai_runtime.api_key:
        return ai_runtime.api_key
    return settings.ai_api_key


def _effective_base_url() -> str:
    if ai_runtime.base_url:
        return ai_runtime.base_url
    return settings.ai_base_url


def _effective_model() -> str:
    if ai_runtime.model:
        return ai_runtime.model
    return settings.ai_model


def _build_test_client(base_url: Optional[str], model: Optional[str], api_key: Optional[str]) -> AiClient:
    """按"入参 > 运行时 > 环境变量"优先级组装一个用于测试/列表的客户端。"""
    return AiClient(
        config=AiRuntimeConfig(
            base_url=base_url or _effective_base_url(),
            model=model or _effective_model(),
            api_key=api_key or _effective_key(),
        )
    )


def _guard_base_url(base_url: str, is_save: bool = False) -> None:
    """校验 base_url 安全性；非法时抛 400。"""
    if not base_url:
        return
    err = validate_base_url(base_url)
    if err:
        detail = err if not is_save else f"拒绝保存：{err}"
        raise HTTPException(status_code=400, detail=detail)


@router.get("/providers", response_model=dict)
async def list_providers() -> dict:
    """返回预置服务商模板（供前端下拉）。"""
    return {"providers": [{"key": k, "name": n, "base_url": u} for k, (u, n) in KNOWN_PROVIDERS.items()]}


@router.get("/ai", response_model=AiSettings)
async def get_ai_settings() -> AiSettings:
    """返回当前 AI 配置（key 脱敏）。"""
    key = _effective_key()
    return AiSettings(
        base_url=_effective_base_url(),
        model=_effective_model(),
        api_key_set=bool(key),
        api_key_masked=mask_key(key) if key else "",
        admin_token_required=bool(_admin_token()),
    )


@router.post("/ai", response_model=AiSettings)
async def update_ai_settings(
    payload: AiSettingsInput,
    x_admin_token: Optional[str] = Header(default=None),
) -> AiSettings:
    """更新 AI 配置。字段 None=不修改，""=清空。需管理令牌（若启用）。"""
    _require_admin_token(payload.admin_token or x_admin_token or "")

    # 保存前校验 base_url 安全
    if payload.base_url is not None and payload.base_url.strip():
        _guard_base_url(payload.base_url, is_save=True)

    settings_store.set_ai_settings(
        base_url=payload.base_url,
        model=payload.model,
        api_key=payload.api_key,
    )
    settings_store.load_ai_runtime_from_store()
    return await get_ai_settings()


@router.post("/ai/test", response_model=AiTestResult)
async def test_ai_connection(payload: AiSettingsInput) -> AiTestResult:
    """用给定（或当前）配置测试一次极简对话，验证 key/base_url/model 是否可用。"""
    _require_admin_token(payload.admin_token or "")
    base_url = payload.base_url or _effective_base_url()
    model = payload.model or _effective_model()
    api_key = payload.api_key or _effective_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key")
    if base_url:
        _guard_base_url(base_url)

    client = _build_test_client(payload.base_url, payload.model, payload.api_key)
    reply = await client.chat(
        [{"role": "user", "content": "回复“连接成功”四个字即可"}],
        temperature=0,
        max_tokens=10,
    )
    if reply is None:
        raise HTTPException(status_code=502, detail="AI 服务连接失败，请检查 base_url / model / api_key")
    return AiTestResult(ok=True, message="连接成功", model=model or client.default_model)


@router.post("/ai/models", response_model=AiModelsResult)
async def fetch_models(payload: AiSettingsInput) -> AiModelsResult:
    """自动从当前（或给定）配置的服务商拉取可用模型列表。"""
    _require_admin_token(payload.admin_token or "")
    base_url = payload.base_url or _effective_base_url()
    api_key = payload.api_key or _effective_key()
    if not api_key:
        raise HTTPException(status_code=400, detail="请先填写 API Key 才能获取模型列表")
    if base_url:
        _guard_base_url(base_url)

    client = _build_test_client(payload.base_url, payload.model, payload.api_key)
    models = await client.list_models()
    if not models:
        raise HTTPException(status_code=502, detail="无法获取模型列表，请检查 base_url 与 API Key")
    return AiModelsResult(ok=True, models=models, message=f"共获取 {len(models)} 个模型")

"""OpenAI 兼容的 LLM 客户端。

设计要点：
- 兼容任意 OpenAI 风格接口（DeepSeek / OpenAI / 通义 / 月之暗面 / 智谱等），
  通过 base_url + model + api_key 三件套驱动，全部可在运行时动态配置；
- api_key 优先取运行时设置（内存 / 本地文件），否则回落环境变量；
- 未配置 key 时返回 None，让上层决定降级策略（如直接返回原文摘要）。

安全：
- 严格校验 base_url 仅允许 http/https，且目标必须是公网可访问域名或受信白名单，
  禁止内网/环回/链路本地/保留地址（防止 SSRF 与 API Key 泄露给恶意第三方）。
"""

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

# 允许的协议
_ALLOWED_SCHEMES = {"http", "https"}

# 明确禁止的网段（私有/环回/链路本地/云元数据/保留地址等）
_BLOCKED_NETWORKS = [
    ip_network("0.0.0.0/8"),        # 本网络
    ip_network("10.0.0.0/8"),       # 私有
    ip_network("100.64.0.0/10"),    # CGNAT
    ip_network("127.0.0.0/8"),      # 环回
    ip_network("169.254.0.0/16"),   # 链路本地（含云元数据 169.254.169.254）
    ip_network("172.16.0.0/12"),    # 私有
    ip_network("192.0.0.0/24"),     # IETF 协议分配
    ip_network("192.168.0.0/16"),   # 私有
    ip_network("198.18.0.0/15"),    # RFC2544 基准测试保留段（字面 IP 输入时拒绝）
    ip_network("224.0.0.0/4"),      # 组播
    ip_network("240.0.0.0/4"),      # 保留
    ip_network("::1/128"),          # IPv6 环回
    ip_network("fc00::/7"),         # IPv6 ULA
    ip_network("fe80::/10"),        # IPv6 链路本地
]

# DNS 解析结果放行的额外网段：代理软件（Clash 等）常用 198.18/15 做 fake-ip，
# 把公网域名解析到该段；若字面输入该段 IP 仍拒绝，但域名解析到该段时放行。
_DNS_ALLOWED_NETWORKS = [ip_network("198.18.0.0/15")]


def validate_base_url(base_url: str) -> Optional[str]:
    """校验 base_url 安全性。合法返回 None，非法返回错误信息。

    默认禁止内网/保留地址（防 SSRF）。若显式设置环境变量
    EMOERA_ALLOW_PRIVATE=1（例如本地调试 Ollama / LM Studio），则放行内网地址。
    """
    raw = (base_url or "").strip()
    if not raw:
        return None  # 空则走默认值

    allow_private = settings.allow_private

    try:
        parsed = urlparse(raw)
    except Exception:  # noqa: BLE001
        return "URL 格式不合法"
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return "仅允许 http/https 协议"
    if not parsed.hostname:
        return "缺少主机名"

    host = parsed.hostname
    # 处理带端口 / IPv6 字面量
    if ":" in host and not host.startswith("["):
        host = host.split(":")[0]
    host = host.strip("[]").lower()

    # 字面 IP（含 IPv6、IPv4-mapped IPv6）直接检查
    try:
        return _check_ip(ip_address(host)) if not allow_private else None
    except ValueError:
        pass  # 非标准字面 IP，继续下面判断

    # 短式/十进制/十六进制 IP（如 127.1、2130706433、0x7f000001）：
    # 主机名全由数字/点/0x 前缀构成时，视为"伪装的 IP 字面量"，解析后按 IP 检查，
    # 防止 getaddrinfo 把它们解析成内网地址绕过黑名单。
    if re.fullmatch(r"(0x[0-9a-fA-F]+|\d+(\.\d+){0,3})", host):
        try:
            infos = __import__("socket").getaddrinfo(host, None)
            if infos:
                ip = ip_address(infos[0][4][0].split("%")[0])
                return _check_ip(ip) if not allow_private else None
        except Exception:  # noqa: BLE001
            return "无法解析主机名"

    # 常规域名：解析 DNS 检查所有 A/AAAA 记录是否指向内网（防 DNS rebinding）
    try:
        infos = __import__("socket").getaddrinfo(host, None)
    except Exception:  # noqa: BLE001 - DNS 解析失败交给调用方处理
        return "无法解析主机名"

    for info in infos:
        try:
            ip = ip_address(info[4][0].split("%")[0])
        except ValueError:
            continue
        # DNS 解析到 fake-ip 网段（代理环境）时放行；其余仍按黑名单检查
        if any(ip in net for net in _DNS_ALLOWED_NETWORKS):
            continue
        err = _check_ip(ip)
        if err and not allow_private:
            return err

    return None


def _check_ip(ip) -> Optional[str]:
    """检查单个 IP 是否命中禁止网段。"""
    if (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_multicast or ip.is_reserved or ip.is_unspecified
    ):
        return "目标地址为内网/保留地址，已阻止（防 SSRF）"
    for net in _BLOCKED_NETWORKS:
        if ip in net:
            return "目标地址为内网/保留地址，已阻止（防 SSRF）"
    return None


@dataclass
class AiRuntimeConfig:
    """运行时可写的 AI 配置（内存态）。"""

    base_url: str = ""
    model: str = ""
    api_key: str = ""


@dataclass
class AiClient:
    """轻量 OpenAI 兼容客户端，聚焦文本补全。"""

    config: AiRuntimeConfig
    default_base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    timeout: float = 60.0

    def resolve(self) -> tuple[str, str, str]:
        """返回 (base_url, model, api_key)，按 运行时配置 -> 默认 回落。"""
        base = self.config.base_url.strip() or self.default_base_url
        model = self.config.model.strip() or self.default_model
        key = self.config.api_key.strip()
        return base, model, key

    def has_key(self) -> bool:
        return bool(self.config.api_key.strip())

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 1500,
    ) -> Optional[str]:
        """调用 chat/completions，返回首个补全文本；失败或未配置时返回 None。"""
        base, model, key = self.resolve()
        if not key:
            return None
        # 安全校验：base_url 不合法直接失败（防止 SSRF / Key 泄露）
        err = validate_base_url(base)
        if err:
            return None

        url = f"{base.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            return data["choices"][0]["message"]["content"]
        except Exception:  # noqa: BLE001 - 上层负责展示错误
            return None

    async def list_models(self) -> Optional[list[str]]:
        """拉取可用模型列表（GET /models），失败或未配置时返回 None。"""
        base, _model, key = self.resolve()
        if not key:
            return None
        err = validate_base_url(base)
        if err:
            return None

        url = f"{base.rstrip('/')}/models"
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            ids = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
            return sorted(ids)
        except Exception:  # noqa: BLE001
            return None


# 全局单例（进程内存态），API 设置端点通过它读写。
ai_runtime = AiRuntimeConfig()


def get_ai_client() -> AiClient:
    """构造带当前运行时配置的客户端（环境变量由调用方合并）。"""
    return AiClient(config=ai_runtime)


def mask_key(key: str) -> str:
    """对 api key 脱敏：只保留前 4 后 4。"""
    if not key:
        return ""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}...{key[-4:]}"

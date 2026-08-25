"""外链安全校验：上传/编辑资源时校验外部链接。

要点：
- 仅允许 http / https，禁止 javascript:、data:、file: 等危险协议（防 XSS / 恶意跳转）；
- 复用 ai_client 的 SSRF 校验，禁止内网 / 环回 / 链路本地 / 云元数据地址，
  避免外链把用户引到内网，或被当作 SSRF 探测跳板；
- 拒绝指向可执行 / 脚本类下载后缀的链接（.exe/.msi/.bat/.js/.vbs/.scr 等），
  降低「点开即下载病毒」的风险。
"""

import re
from typing import Optional
from urllib.parse import urlparse

from app.services.ai_client import validate_base_url

# 高危下载后缀：这些链接点击后浏览器可能直接下载并执行，风险高，一律拒绝
DANGEROUS_PATH_EXT = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".pif", ".cpl",
    ".js", ".jse", ".vbs", ".vbe", ".wsf", ".wsh", ".ps1", ".hta",
    ".jar", ".dll", ".reg", ".lnk", ".apk",
}

# 允许的协议
_ALLOWED_SCHEMES = {"http", "https"}


def validate_external_link(link: str) -> Optional[str]:
    """校验外链。合法返回 None，非法返回错误信息。

    与 ai_client.validate_base_url 共用同一套 SSRF 规则；
    额外拒绝危险协议与高危下载后缀。
    """
    raw = (link or "").strip()
    if not raw:
        return None  # 空链接合法（外链为可选字段）

    if len(raw) > 2000:
        return "链接过长"

    try:
        parsed = urlparse(raw)
    except Exception:  # noqa: BLE001
        return "链接格式不合法"

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        return "仅允许 http / https 链接"
    if not parsed.hostname:
        return "链接缺少有效主机名"

    # SSRF / 内网地址校验（含 DNS 解析检查）
    err = validate_base_url(raw)
    if err:
        return err

    # 高危下载后缀：拒绝可执行 / 脚本类文件
    path = parsed.path or ""
    m = re.search(r"\.([A-Za-z0-9]+)(?:[/?#]|$)", path)
    if m and ("." + m.group(1).lower()) in DANGEROUS_PATH_EXT:
        return "该链接指向可执行/脚本类文件（可能含病毒），已拒绝"

    return None

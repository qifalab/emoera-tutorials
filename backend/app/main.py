"""FastAPI 应用入口：生命周期管理、CORS、限流、路由挂载。"""

import os
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import router as v1_router
from app.config import settings
from app.services import settings_store
from app.services.message_aggregator import aggregate
from app.services.rate_limit import _record
from app.services.resource_store import UPLOAD_DIR
from app.services.scheduler import create_scheduler


class RateLimitMiddleware(BaseHTTPMiddleware):
    """写操作按 IP 限流（防 DDoS / 刷接口）。读操作直接放行。"""

    async def dispatch(self, request: Request, call_next):
        if settings.enable_rate_limit and request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            # 默认信任真实 socket IP；仅 trust_proxy=True 时才读 X-Forwarded-For，
            # 防止伪造 XFF 头绕过限流。
            host = None
            if settings.trust_proxy:
                fwd = request.headers.get("x-forwarded-for", "")
                if fwd:
                    host = fwd.split(",")[0].strip()
            if not host:
                host = request.client.host if request.client else "unknown"
            if _record(f"w:{host}", settings.rate_limit_burst, 60.0):
                return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后再试"})
        return await call_next(request)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """限制 JSON/表单请求体大小（防超大数据包拖垮服务）。

    注意：附件上传接口 /api/v1/resources 走 multipart，Content-Length 会包含文件
    大小，不应被此上限拦截——文件大小由 resource_store.MAX_FILE_SIZE 独立校验。
    """

    # 放行路径前缀（multipart 文件上传）
    _SKIP_PREFIXES = ("/api/v1/resources",)

    async def dispatch(self, request: Request, call_next):
        cl = request.headers.get("content-length", "")
        if cl.isdigit() and int(cl) > settings.max_body_bytes:
            path = request.url.path
            if not any(path.startswith(p) for p in self._SKIP_PREFIXES):
                return JSONResponse(status_code=413, content={"detail": "请求体过大"})
        return await call_next(request)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动即加载 AI 设置并做一次消息聚合；按需启动定时调度器。"""
    # 加载持久化的 AI 配置（base_url / model / api_key）到运行时
    settings_store.load_ai_runtime_from_store()
    try:
        await aggregate()
    except Exception:
        # demo 模式下即使失败也不阻塞启动
        pass

    scheduler = None
    if settings.enable_scheduler:
        scheduler = create_scheduler()
        scheduler.start()

    yield

    if scheduler is not None:
        scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)

# 顺序：BodySize -> RateLimit -> CORS（CORS 放最后，保证预检请求正常）
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")

# 上传的资源文件：强制以附件方式下载（Content-Disposition: attachment），
# 而非让浏览器内联渲染，从根本上防止任何存储型 XSS / 内容嗅探攻击。
os.makedirs(UPLOAD_DIR, exist_ok=True)


@app.get("/uploads/{filename}")
async def download_upload(filename: str):
    """安全下载上传的附件：只允许纯字母数字/点/横线文件名，防止路径穿越。"""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", filename) or ".." in filename:
        raise HTTPException(status_code=400, detail="非法文件名")
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="文件不存在")
    return FileResponse(
        file_path,
        filename=filename,
        content_disposition_type="attachment",
    )


@app.get("/api/health")
async def health() -> dict:
    """健康检查端点，供前端/探针使用。"""
    return {"status": "ok", "app": settings.app_name}

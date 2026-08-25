FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
# 让 playwright 在无头环境能找到依赖
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# 系统依赖（Playwright chromium 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" pydantic-settings httpx apscheduler playwright && \
    playwright install --with-deps chromium

COPY app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

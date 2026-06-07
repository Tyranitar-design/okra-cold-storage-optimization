# ============================================================
# 秋葵冷库优化 MIS — FastAPI 后端镜像
# 仅提供 API + MIS 静态文件服务；Gurobi 求解在本地宿主机运行
#
# 构建：docker build -t okra-mis:latest .
# 运行：docker compose up  (推荐，自动注入 .env)
# ============================================================

# ── Stage 1: 前端构建 ─────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend-vue

# 先复制 package 文件，利用 Docker 层缓存
COPY frontend-vue/package*.json ./
RUN npm ci --prefer-offline

# 复制前端源码并构建
COPY frontend-vue/ ./
RUN npm run build
# 产物在 /app/frontend-vue/dist

# ── Stage 2: Python 依赖层 ────────────────────────────────────
FROM python:3.11-slim AS python-deps

WORKDIR /deps

# 系统依赖：psycopg binary 需要 libpq；matplotlib 需要 libjpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    libjpeg-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-api.txt ./
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir \
       --extra-index-url https://download.pytorch.org/whl/cpu \
       -r requirements-api.txt

# ── Stage 3: 运行时镜像 ───────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="okra-cold-storage-project"
LABEL description="秋葵冷库优化 MIS — FastAPI + Vue + PostgreSQL"

# 系统运行时库
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libgomp1 \
    libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

# 非 root 用户运行（安全最佳实践）
RUN useradd -m -u 1000 okra
WORKDIR /app

# 从前两个 stage 复制产物
COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin
COPY --from=frontend-builder /app/frontend-vue/dist /app/frontend-vue/dist

# 复制项目代码
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY docs/ ./docs/
COPY results/ ./results/
COPY experiments/ ./experiments/
COPY database/ ./database/

# 确保 logs / results 目录存在且可写
RUN mkdir -p /app/logs /app/results && \
    chown -R okra:okra /app

USER okra

# 健康检查（不依赖 curl；直接用 Python 访问 /health）
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request; port = os.environ.get('API_PORT', '8014'); urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=5).read()" || exit 1

EXPOSE 8014

# 启动 FastAPI（通过环境变量控制 host/port）
CMD ["sh", "-c", \
     "uvicorn src.api.main:app \
      --host ${API_HOST:-0.0.0.0} \
      --port ${API_PORT:-8014} \
      --workers 2 \
      --log-level info"]

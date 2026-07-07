# =============================================================================
# Stage 1: 前端构建
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

# 安装依赖（利用 Docker 缓存）
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# 构建前端
COPY frontend/ ./
RUN npm run build


# =============================================================================
# Stage 2: Python 后端运行环境
# =============================================================================
FROM python:3.12-slim

# 安装系统依赖（pandoc 用于 docx 转换）
RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制 Python 项目配置
COPY pyproject.toml ./
COPY src/ src/
COPY scripts/ scripts/
COPY configs/ configs/
COPY prompts/ prompts/
COPY alembic.ini ./
COPY migrations/ migrations/
COPY docs/ docs/

# 安装 Python 依赖（仅生产核心依赖，不含 mineru 本地 SDK（torch等2GB+）
# mineru.mode: "online" 使用线上 API，无需本地 SDK
RUN pip install --no-cache-dir -e "."

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist frontend/dist/

EXPOSE 8000

CMD ["python", "-m", "scripts.run_server", "--port", "8000"]

"""FastAPI 应用入口

企业级国标文档排版智能体 REST API 服务。
"""

from __future__ import annotations

import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers import (
    auth_router,
    chat_router,
    config_router,
    formatters_router,
    kb_router,
    tasks_router,
    templates_router,
    upload_router,
)
from src.db.database import init_db
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化
    setup_logging()
    init_db()  # 初始化数据库表
    logger.info("文档排版智能体 API 服务启动")
    yield
    # 关闭时清理
    logger.info("文档排版智能体 API 服务关闭")


# 创建 FastAPI 应用
app = FastAPI(
    title="文档排版智能体 API",
    description="企业级国标文档结构化与排版智能体 REST API",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# CORS 配置（生产环境限制为前端域名）
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# 限流中间件（用户级 by Authorization header，回退 IP 级）
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 100  # requests
RATE_WINDOW = 60  # seconds


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """用户级限流（基于 JWT），回退 IP 级，防止恶意请求"""
    # 优先从 Authorization header 提取用户标识
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        client_key = "user:" + auth_header[:80]  # 截断 token 前缀作为 key
    else:
        client_key = "ip:" + (request.client.host if request.client else "unknown")
    now = time.time()
    window = _rate_limit_store[client_key]
    _rate_limit_store[client_key] = [t for t in window if now - t < RATE_WINDOW]
    if len(_rate_limit_store[client_key]) >= RATE_LIMIT:
        return JSONResponse(status_code=429, content={"code": 429, "message": "请求过于频繁"})
    _rate_limit_store[client_key].append(now)
    return await call_next(request)


# 前端路径
_frontend_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

# 挂载前端静态文件（仅 /assets 目录）
if _frontend_path.exists():
    assets_path = _frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="frontend-assets")
    logger.info("前端静态文件已挂载: %s", _frontend_path)


# 注册 API 路由（auth 路由在最前，公开端点优先匹配）
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(tasks_router)
app.include_router(kb_router)
app.include_router(config_router)
app.include_router(templates_router)
app.include_router(chat_router)
app.include_router(formatters_router)


# 全局异常处理
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """捕获未处理的异常，统一返回 500 响应"""
    logger.exception("未捕获异常: %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": f"服务器内部错误: {type(exc).__name__}", "detail": str(exc)},
    )


# 健康检查
@app.get("/api/health", tags=["健康"])
async def health_check() -> dict:
    """健康检查接口"""
    return {"status": "ok", "version": "0.1.0"}


# 根路径（有前端时服务前端，无前端时返回 API 信息）
@app.get("/", tags=["根路径"], response_model=None)
async def root():
    """根路径"""
    if _frontend_path.exists():
        return FileResponse(_frontend_path / "index.html")
    return {
        "name": "文档排版智能体 API",
        "version": "0.1.0",
        "docs": "/api/docs",
        "health": "/api/health",
    }


# SPA 前端路由回退 —— 捕获所有非 API 的 404 请求
@app.exception_handler(404)
async def spa_fallback_handler(request: Request, exc: Exception):
    """对非 API 路径返回前端 index.html（SPA fallback）"""
    if _frontend_path.exists() and not request.url.path.startswith("/api/"):
        return FileResponse(_frontend_path / "index.html")
    return JSONResponse(status_code=404, content={"code": 404, "message": "Not Found"})

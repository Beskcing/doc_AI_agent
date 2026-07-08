"""FastAPI 应用入口

企业级国标文档排版智能体 REST API 服务。
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers import (
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

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为前端域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 限流中间件（IP 级，100 请求/分钟）
_rate_limit_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 100  # requests
RATE_WINDOW = 60  # seconds


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """IP 级基本限流，防止恶意请求"""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = _rate_limit_store[client_ip]
    # 清理过期记录
    _rate_limit_store[client_ip] = [t for t in window if now - t < RATE_WINDOW]
    if len(_rate_limit_store[client_ip]) >= RATE_LIMIT:
        return JSONResponse(status_code=429, content={"code": 429, "message": "请求过于频繁"})
    _rate_limit_store[client_ip].append(now)
    return await call_next(request)


# 注册路由
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
_frontend_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


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


# 挂载前端静态文件（生产模式）—— 必须放在所有 API 路由之后，避免拦截 API 请求
if _frontend_path.exists():
    assets_path = _frontend_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="frontend-assets")

    @app.get("/{full_path:path}")
    async def _serve_frontend(full_path: str):
        """SPA 前端路由回退 —— 仅对未被 API 路由匹配的路径生效"""
        target = _frontend_path / full_path
        if target.is_file():
            return FileResponse(target)
        return FileResponse(_frontend_path / "index.html")

    logger.info("前端静态文件已挂载: %s", _frontend_path)

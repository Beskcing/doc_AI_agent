"""FastAPI 应用入口

企业级国标文档排版智能体 REST API 服务。
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.api.routers import chat_router, config_router, kb_router, tasks_router, templates_router, upload_router
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

# 注册路由
app.include_router(upload_router)
app.include_router(tasks_router)
app.include_router(kb_router)
app.include_router(config_router)
app.include_router(templates_router)
app.include_router(chat_router)


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


# 根路径重定向到前端
@app.get("/", tags=["根路径"])
async def root() -> dict:
    """根路径"""
    return {
        "name": "文档排版智能体 API",
        "version": "0.1.0",
        "docs": "/api/docs",
        "health": "/api/health",
    }

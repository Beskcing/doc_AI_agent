"""API 路由入口"""

from src.api.routers.admin import router as admin_router
from src.api.routers.auth import router as auth_router
from src.api.routers.chat import router as chat_router
from src.api.routers.config import router as config_router
from src.api.routers.formatters import router as formatters_router
from src.api.routers.kb import router as kb_router
from src.api.routers.review import router as review_router
from src.api.routers.tasks import router as tasks_router
from src.api.routers.templates import router as templates_router
from src.api.routers.upload import router as upload_router

__all__ = [
    "admin_router",
    "auth_router",
    "upload_router",
    "tasks_router",
    "kb_router",
    "config_router",
    "templates_router",
    "chat_router",
    "formatters_router",
    "review_router",
]

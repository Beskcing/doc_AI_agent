"""Formatter 模块

启动时自动扫描 formatters/ 目录，加载所有 Formatter 模块以触发注册。
用户只需将新的 Formatter 脚本放入此目录即可自动注册。
"""

from __future__ import annotations

from src.tools.formatters.base import BaseDocxFormatter
from src.tools.formatters.registry import (
    FORMATTER_REGISTRY,
    get_formatter,
    is_registered,
    list_formatters,
    register_formatter,
)

__all__ = [
    "BaseDocxFormatter",
    "FORMATTER_REGISTRY",
    "register_formatter",
    "get_formatter",
    "list_formatters",
    "is_registered",
]

# 首次导入时触发自动发现
# 后续调用 get_formatter/list_formatters/is_registered 也会触发
from src.tools.formatters.registry import _ensure_discovered  # noqa: F401

_ensure_discovered()

"""Formatter 注册表

全局注册表，管理所有已注册的文档格式修正器。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.tools.formatters.base import BaseDocxFormatter

_discovered = False

# 全局注册表：standard_id → Formatter 类
FORMATTER_REGISTRY: dict[str, type[BaseDocxFormatter]] = {}


def register_formatter(cls: type[BaseDocxFormatter]) -> type[BaseDocxFormatter]:
    """装饰器：将 Formatter 类注册到全局注册表

    用法：
        @register_formatter
        class GbtDocxFormatter(BaseDocxFormatter):
            standard_id = "gbt_1.1"
            display_name = "GB/T 1.1 标准化工作导则"
            ...
    """
    if not cls.standard_id:
        raise ValueError(f"Formatter {cls.__name__} 必须定义 standard_id")
    if cls.standard_id in FORMATTER_REGISTRY:
        existing = FORMATTER_REGISTRY[cls.standard_id].__name__
        raise ValueError(f"standard_id '{cls.standard_id}' 已被 {existing} 注册，{cls.__name__} 无法重复注册")
    FORMATTER_REGISTRY[cls.standard_id] = cls
    return cls


def _ensure_discovered() -> None:
    """首次调用时自动扫描 formatters/ 目录，加载所有 Formatter 模块"""
    global _discovered
    if _discovered:
        return
    _discovered = True

    import importlib
    import pkgutil
    from pathlib import Path

    formatters_dir = Path(__file__).parent
    for _, name, _ in pkgutil.iter_modules([str(formatters_dir)]):
        if name.startswith("_") or name.startswith("test_"):
            continue
        try:
            importlib.import_module(f"src.tools.formatters.{name}")
        except ImportError as e:
            import logging

            logging.getLogger(__name__).debug("跳过 formatter 模块 %s: %s", name, e)


def get_formatter(standard_id: str) -> type[BaseDocxFormatter] | None:
    """根据标准标识符获取 Formatter 类

    Args:
        standard_id: 标准标识符，如 "gbt_1.1"

    Returns:
        Formatter 类，未注册时返回 None
    """
    _ensure_discovered()
    return FORMATTER_REGISTRY.get(standard_id)


def list_formatters() -> list[dict[str, str]]:
    """列出所有已注册的 Formatter

    Returns:
        [{"id": "gbt_1.1", "name": "GB/T 1.1 标准化工作导则"}, ...]
    """
    _ensure_discovered()
    return [{"id": k, "name": v.display_name} for k, v in FORMATTER_REGISTRY.items()]


def is_registered(standard_id: str) -> bool:
    """检查指定标准是否已注册 Formatter"""
    _ensure_discovered()
    return standard_id in FORMATTER_REGISTRY

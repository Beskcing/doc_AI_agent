"""Formatter 注册表查询路由

提供已注册的格式修正器列表，供前端展示"内置格式规范"。
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.models import ResponseModel
from src.tools.formatters.registry import list_formatters

router = APIRouter(prefix="/api/formatters", tags=["格式修正器"])


@router.get("", response_model=ResponseModel)
async def get_formatters() -> ResponseModel:
    """获取所有已注册的 Formatter 列表

    Returns:
        [{"id": "gbt_1.1", "name": "GB/T 1.1 标准化工作导则"}, ...]
    """
    formatters = list_formatters()
    return ResponseModel(data={"formatters": formatters, "total": len(formatters)})

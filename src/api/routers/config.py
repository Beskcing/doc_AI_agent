"""系统配置路由"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.models import ResponseModel, SystemConfig, UpdateConfigRequest
from src.db.crud import SystemConfigCRUD
from src.db.session import get_db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/config", tags=["配置"])


def _config_to_dict(config) -> dict:
    """将数据库配置对象转换为字典"""
    return {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "rag_bm25_weight": config.rag_bm25_weight,
        "rag_vector_weight": config.rag_vector_weight,
        "rag_top_k": config.rag_top_k,
        "pandoc_path": config.pandoc_path,
        "output_dir": config.output_dir,
        "max_file_size_mb": config.max_file_size_mb,
        "supported_formats": config.supported_formats.split(",") if config.supported_formats else [],
    }


@router.get("", response_model=ResponseModel)
async def get_config() -> ResponseModel:
    """获取系统配置"""
    with get_db_session() as db:
        config = SystemConfigCRUD.get_or_create(db)
        return ResponseModel(data=_config_to_dict(config))


@router.put("", response_model=ResponseModel)
async def update_config(request: UpdateConfigRequest) -> ResponseModel:
    """更新系统配置"""
    with get_db_session() as db:
        config = SystemConfigCRUD.update(db, **request.model_dump(exclude_none=True))
        return ResponseModel(data=_config_to_dict(config))


@router.get("/supported-standards", response_model=ResponseModel)
async def get_supported_standards() -> ResponseModel:
    """获取支持的排版规范列表"""
    return ResponseModel(
        data=[
            {"value": "GB/T 9704", "label": "党政机关公文格式"},
            {"value": "GB/T 7713", "label": "科技报告编写格式"},
            {"value": "custom", "label": "自定义规范"},
        ],
    )


@router.get("/llm-models", response_model=ResponseModel)
async def get_llm_models() -> ResponseModel:
    """获取支持的 LLM 模型列表"""
    return ResponseModel(
        data=[
            {"value": "qwen-plus", "label": "通义千问 Plus"},
            {"value": "qwen-max", "label": "通义千问 Max"},
            {"value": "glm-4", "label": "智谱 GLM-4"},
            {"value": "glm-4-plus", "label": "智谱 GLM-4 Plus"},
        ],
    )

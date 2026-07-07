"""样式模板管理路由"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from src.api.models import (
    ResponseModel,
    SaveTemplateRequest,
    StyleTemplateInfo,
    StyleTemplateListResponse,
    UpdateTemplateRequest,
)
from src.db.crud import StyleTemplateCRUD
from src.db.session import get_db_session
from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/templates", tags=["样式模板"])

# 模板 DOCX 存储目录
TEMPLATE_DIR = Path("data/templates")
ensure_dir(TEMPLATE_DIR)


def _template_to_info(template) -> StyleTemplateInfo:
    """将 ORM 模型转换为 API 响应"""
    return StyleTemplateInfo(
        id=template.id,
        name=template.name,
        description=template.description,
        style_config=template.style_config,
        source_docx_path=template.source_docx_path,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.post("/upload", response_model=ResponseModel)
async def upload_template(file: UploadFile = File(...)) -> ResponseModel:
    """上传 Word 模板文件，提取排版格式

    接收 .docx 文件，使用 DocxStyleExtractor 提取样式配置。
    不保存模板，仅返回提取的 style_config 供前端预览和编辑。
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext != ".docx":
        return ResponseModel(code=400, message=f"仅支持 .docx 格式，收到: {ext}")

    upload_id = str(uuid.uuid4())
    file_path = TEMPLATE_DIR / f"{upload_id}.docx"

    try:
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        file_size = os.path.getsize(file_path)

        # 提取样式
        from src.tools.docx_style_extractor import DocxStyleExtractor

        extractor = DocxStyleExtractor()
        style_config = extractor.extract(file_path)

        logger.info("模板样式提取成功: %s (%.2f KB)", file.filename, file_size / 1024)

        return ResponseModel(data={
            "style_config": style_config,
            "source_docx_path": str(file_path),
            "filename": file.filename,
            "file_size": file_size,
        })
    except Exception as e:
        logger.exception("模板上传/提取失败: %s", file.filename)
        return ResponseModel(code=500, message=f"模板提取失败: {e}")


@router.post("", response_model=ResponseModel)
async def save_template(request: SaveTemplateRequest) -> ResponseModel:
    """保存样式模板"""
    with get_db_session() as db:
        try:
            template = StyleTemplateCRUD.create(
                db,
                name=request.name,
                style_config=request.style_config,
                description=request.description,
                source_docx_path=request.source_docx_path,
            )
            logger.info("样式模板已保存: %s (%s)", template.name, template.id)
            return ResponseModel(data=_template_to_info(template).model_dump())
        except Exception as e:
            logger.exception("保存模板失败")
            return ResponseModel(code=500, message=f"保存模板失败: {e}")


@router.get("", response_model=ResponseModel)
async def list_templates(
    page: int = 1,
    page_size: int = 50,
) -> ResponseModel:
    """获取样式模板列表"""
    with get_db_session() as db:
        templates, total = StyleTemplateCRUD.list_templates(db, page=page, page_size=page_size)
        return ResponseModel(data=StyleTemplateListResponse(
            total=total,
            page=page,
            page_size=page_size,
            items=[_template_to_info(t) for t in templates],
        ))


@router.get("/{template_id}", response_model=ResponseModel)
async def get_template(template_id: str) -> ResponseModel:
    """获取模板详情"""
    with get_db_session() as db:
        template = StyleTemplateCRUD.get(db, template_id)
        if not template:
            return ResponseModel(code=404, message="模板不存在")
        return ResponseModel(data=_template_to_info(template).model_dump())


@router.put("/{template_id}", response_model=ResponseModel)
async def update_template(template_id: str, request: UpdateTemplateRequest) -> ResponseModel:
    """更新模板"""
    with get_db_session() as db:
        try:
            template = StyleTemplateCRUD.update(
                db, template_id,
                name=request.name,
                style_config=request.style_config,
                description=request.description,
            )
            if not template:
                return ResponseModel(code=404, message="模板不存在")
            return ResponseModel(data=_template_to_info(template).model_dump())
        except Exception as e:
            logger.exception("更新模板失败")
            return ResponseModel(code=500, message=f"更新模板失败: {e}")


@router.delete("/{template_id}", response_model=ResponseModel)
async def delete_template(template_id: str) -> ResponseModel:
    """删除模板"""
    with get_db_session() as db:
        if StyleTemplateCRUD.delete(db, template_id):
            return ResponseModel(data={"deleted": True})
        return ResponseModel(code=404, message="模板不存在")

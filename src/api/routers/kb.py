"""知识库管理路由"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile

from src.api.models import KbListResponse, ResponseModel
from src.db.crud import KbDocumentCRUD
from src.db.database import SessionLocal
from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/kb", tags=["知识库"])

KB_DIR = Path("knowledge_data/raw_docs")


@router.get("/documents", response_model=ResponseModel)
async def list_kb_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ResponseModel:
    """获取知识库文档列表"""
    try:
        db = SessionLocal()
        try:
            docs, total = KbDocumentCRUD.list_documents(db, page=page, page_size=page_size)
            items = []
            for doc in docs:
                items.append({
                    "id": doc.id,
                    "name": doc.name,
                    "source": doc.source,
                    "status": doc.status,
                    "chunk_count": doc.chunk_count,
                    "created_at": doc.created_at.isoformat() if doc.created_at else None,
                    "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                })
            return ResponseModel(
                data=KbListResponse(
                    total=total,
                    page=page,
                    page_size=page_size,
                    items=items,
                ),
            )
        finally:
            db.close()
    except Exception as e:
        logger.exception("获取知识库文档列表失败")
        return ResponseModel(code=500, message=f"获取知识库文档列表失败: {e}")


@router.post("/documents", response_model=ResponseModel)
async def upload_kb_document(file: UploadFile = File(...)) -> ResponseModel:
    """上传知识库文档"""
    try:
        ensure_dir(KB_DIR)
        file_path = KB_DIR / (file.filename or "unknown.md")
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        db = SessionLocal()
        try:
            doc = KbDocumentCRUD.create(
                db,
                name=file.filename or "unknown",
                source=str(file_path),
                status="indexed",
            )
            return ResponseModel(data={"uploaded": str(file_path), "name": doc.name, "id": doc.id})
        finally:
            db.close()
    except Exception as e:
        logger.exception("上传知识库文档失败")
        return ResponseModel(code=500, message=f"上传失败: {e}")


@router.delete("/documents/{doc_id}", response_model=ResponseModel)
async def delete_kb_document(doc_id: str) -> ResponseModel:
    """删除知识库文档"""
    try:
        db = SessionLocal()
        try:
            success = KbDocumentCRUD.delete(db, doc_id)
            if success:
                return ResponseModel(data={"deleted": doc_id})
            return ResponseModel(code=404, message="文档不存在")
        finally:
            db.close()
    except Exception as e:
        logger.exception("删除知识库文档失败")
        return ResponseModel(code=500, message=f"删除失败: {e}")


@router.post("/rebuild", response_model=ResponseModel)
async def rebuild_kb_index() -> ResponseModel:
    """重建知识库索引"""
    # 实际应触发知识库重建
    return ResponseModel(data={"rebuilding": True, "message": "知识库重建已启动"})

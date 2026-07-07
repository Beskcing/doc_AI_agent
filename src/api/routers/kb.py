"""知识库管理路由"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, Query, UploadFile

from src.api.models import KbListResponse, KbSearchRequest, ResponseModel
from src.db.crud import KbDocumentCRUD
from src.db.session import get_db_session
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
        with get_db_session() as db:
            docs, total = KbDocumentCRUD.list_documents(db, page=page, page_size=page_size)
            items = []
            for doc in docs:
                items.append(
                    {
                        "id": doc.id,
                        "name": doc.name,
                        "source": doc.source,
                        "status": doc.status,
                        "chunk_count": doc.chunk_count,
                        "created_at": doc.created_at.isoformat() if doc.created_at else None,
                        "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
                    }
                )
            return ResponseModel(
                data=KbListResponse(
                    total=total,
                    page=page,
                    page_size=page_size,
                    items=items,
                ),
            )
    except Exception as e:
        logger.exception("获取知识库文档列表失败")
        return ResponseModel(code=500, message=f"获取知识库文档列表失败: {e}")


@router.post("/documents", response_model=ResponseModel)
async def upload_kb_document(file: UploadFile = File(...)) -> ResponseModel:
    """上传知识库文档

    Bug#2 修复：使用 UUID 命名存储文件，避免同名文件覆盖。
    原始文件名保存在 DB 的 name 字段中。
    """
    try:
        ensure_dir(KB_DIR)
        original_name = file.filename or "unknown.md"
        ext = Path(original_name).suffix.lower() or ".md"
        stored_filename = f"{uuid.uuid4()}{ext}"
        file_path = KB_DIR / stored_filename
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        with get_db_session() as db:
            # BUG 修复：上传时状态为 pending，需重建索引后才会变为 indexed
            doc = KbDocumentCRUD.create(
                db,
                name=original_name,
                source=str(file_path),
                status="pending",
            )
            return ResponseModel(data={"uploaded": str(file_path), "name": doc.name, "id": doc.id, "status": "pending"})
    except Exception as e:
        logger.exception("上传知识库文档失败")
        return ResponseModel(code=500, message=f"上传失败: {e}")


@router.delete("/documents/{doc_id}", response_model=ResponseModel)
async def delete_kb_document(doc_id: str) -> ResponseModel:
    """删除知识库文档

    Bug#3 修复：同时删除物理文件，避免残留。
    """
    try:
        with get_db_session() as db:
            # 先获取文档记录以拿到文件路径
            doc = KbDocumentCRUD.get(db, doc_id)
            if not doc:
                return ResponseModel(code=404, message="文档不存在")

            # 删除物理文件
            if doc.source:
                file_path = Path(doc.source)
                if file_path.exists():
                    try:
                        file_path.unlink()
                        logger.info("已删除知识库文件: %s", file_path)
                    except OSError as e:
                        logger.warning("删除知识库文件失败: %s (%s)", file_path, e)

            success = KbDocumentCRUD.delete(db, doc_id)
            if success:
                return ResponseModel(data={"deleted": doc_id})
            return ResponseModel(code=404, message="文档不存在")
    except Exception as e:
        logger.exception("删除知识库文档失败")
        return ResponseModel(code=500, message=f"删除失败: {e}")


@router.post("/rebuild", response_model=ResponseModel)
async def rebuild_kb_index() -> ResponseModel:
    """重建知识库索引

    Bug#4 修复：实际执行知识库重建，扫描 raw_docs 目录并重新索引。
    """
    try:
        from src.config import AppConfig
        from src.rag.knowledge_base_config import KnowledgeBaseManager

        config = AppConfig.load()
        kb_manager = KnowledgeBaseManager(config.rag)
        kb_manager.initialize()

        # 统计结果
        retriever = kb_manager.get_retriever()
        doc_count = len(retriever.documents) if hasattr(retriever, "documents") else 0

        # 同步 DB 记录：确保 raw_docs 中的文件都有 DB 记录，并更新 chunk_count
        with get_db_session() as db:
            from src.db.models import KbDocumentModel

            raw_dir = Path(config.paths.raw_docs_dir)
            if raw_dir.exists():
                # 统计每个文件的 chunk 数量
                chunk_map = {}
                if hasattr(retriever, "documents"):
                    for doc in retriever.documents:
                        # Document 对象的 source 在 metadata 中
                        src = doc.metadata.get("source", "") if hasattr(doc, "metadata") else ""
                        if src:
                            # 从 source 路径提取文件名
                            src_name = Path(src).name
                            chunk_map[src_name] = chunk_map.get(src_name, 0) + 1

                for f in raw_dir.glob("*.md"):
                    existing = db.query(KbDocumentModel).filter(KbDocumentModel.source == str(f)).first()
                    chunk_count = chunk_map.get(f.name, 0)
                    if not existing:
                        new_doc = KbDocumentModel(
                            name=f.name,
                            source=str(f),
                            status="indexed",
                            chunk_count=chunk_count,
                        )
                        db.add(new_doc)
                    else:
                        # BUG 修复：更新已有文档的 chunk_count
                        existing.chunk_count = chunk_count
                        existing.status = "indexed"
                db.commit()

        logger.info("知识库重建完成: %d 个文档片段", doc_count)
        return ResponseModel(
            data={
                "rebuilding": True,
                "message": f"知识库重建完成，共 {doc_count} 个文档片段",
                "doc_count": doc_count,
            }
        )
    except Exception as e:
        logger.exception("知识库重建失败")
        return ResponseModel(code=500, message=f"知识库重建失败: {e}")


@router.get("/stats", response_model=ResponseModel)
async def get_kb_stats() -> ResponseModel:
    """获取知识库统计信息

    返回文档总数、已索引数、待索引数、总 chunk 数等。
    """
    try:
        with get_db_session() as db:
            from src.db.models import KbDocumentModel

            total_docs = db.query(KbDocumentModel).count()
            indexed_docs = db.query(KbDocumentModel).filter(KbDocumentModel.status == "indexed").count()
            pending_docs = db.query(KbDocumentModel).filter(KbDocumentModel.status == "pending").count()
            total_chunks = sum(doc.chunk_count or 0 for doc in db.query(KbDocumentModel).all())

            return ResponseModel(
                data={
                    "total_docs": total_docs,
                    "indexed_docs": indexed_docs,
                    "pending_docs": pending_docs,
                    "total_chunks": total_chunks,
                }
            )
    except Exception as e:
        logger.exception("获取知识库统计失败")
        return ResponseModel(code=500, message=f"获取统计失败: {e}")


@router.post("/search", response_model=ResponseModel)
async def search_kb(request: KbSearchRequest) -> ResponseModel:
    """知识库检索

    使用混合检索（BM25 + 向量）在知识库中查找相关文档片段。
    """
    try:
        query = request.query
        top_k = request.top_k

        if not query:
            return ResponseModel(code=400, message="query 不能为空")

        from src.config import AppConfig
        from src.rag.knowledge_base_config import KnowledgeBaseManager

        config = AppConfig.load()
        kb_manager = KnowledgeBaseManager(config.rag)
        kb_manager.initialize()
        retriever = kb_manager.get_retriever()

        results = retriever.retrieve(query)
        items = []
        for r in results[:top_k]:
            items.append(
                {
                    "content": r.content,
                    "source": r.source,
                    "section": r.section,
                    "score": getattr(r, "score", None),
                }
            )

        return ResponseModel(
            data={
                "results": items,
                "total": len(items),
            }
        )
    except Exception as e:
        logger.exception("知识库检索失败")
        return ResponseModel(code=500, message=f"检索失败: {e}")

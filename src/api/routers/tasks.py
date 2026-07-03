"""任务管理路由"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from src.api.models import (
    CreateTaskRequest,
    ResponseModel,
    TaskListResponse,
    TaskStatus,
)
from src.api.services.task_manager import task_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 上传文件存储目录
UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/output")

router = APIRouter(prefix="/api/tasks", tags=["任务"])


@router.post("", response_model=ResponseModel)
async def create_task(request: CreateTaskRequest) -> ResponseModel:
    """创建排版任务"""
    try:
        # 查找上传的文件
        upload_id = request.upload_id
        file_path = None
        filename = upload_id
        for ext in (".pdf", ".md", ".txt"):
            candidate = UPLOAD_DIR / f"{upload_id}{ext}"
            if candidate.exists():
                file_path = str(candidate)
                filename = candidate.name
                break

        task = task_manager.create_task(
            upload_id=upload_id,
            filename=filename,
            standard=request.standard,
            use_rag=request.use_rag,
            llm_model=request.llm_model,
            custom_config={
                **(request.custom_config or {}),
                "file_path": file_path,
            },
        )
        # 提交异步处理
        task_manager.submit_task(task.id)
        return ResponseModel(data=task_manager.to_info_dict(task))
    except Exception as e:
        logger.exception("创建任务失败")
        return ResponseModel(code=500, message=f"创建任务失败: {e}")


@router.get("/stats", response_model=ResponseModel)
async def get_task_stats() -> ResponseModel:
    """获取任务统计信息（Dashboard 用）"""
    try:
        stats = task_manager.get_stats()
        recent = task_manager.get_recent_tasks(limit=5)
        return ResponseModel(data={
            "stats": stats,
            "recent_tasks": [task_manager.to_info_dict(t) for t in recent],
        })
    except Exception as e:
        logger.exception("获取统计失败")
        return ResponseModel(code=500, message=f"获取统计失败: {e}")


@router.get("", response_model=ResponseModel)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
) -> ResponseModel:
    """获取任务列表"""
    try:
        tasks, total = task_manager.list_tasks(
            page=page, page_size=page_size, status=status.value if status else None
        )
        return ResponseModel(
            data=TaskListResponse(
                total=total,
                page=page,
                page_size=page_size,
                items=[task_manager.to_info_dict(t) for t in tasks],
            ),
        )
    except Exception as e:
        logger.exception("获取任务列表失败")
        return ResponseModel(code=500, message=f"获取任务列表失败: {e}")


@router.get("/{task_id}", response_model=ResponseModel)
async def get_task(task_id: str) -> ResponseModel:
    """获取任务详情"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    return ResponseModel(data=task_manager.to_detail_dict(task))


@router.get("/{task_id}/status", response_model=ResponseModel)
async def get_task_status(task_id: str) -> ResponseModel:
    """获取任务状态（SSE 轮询用）"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    return ResponseModel(data=task_manager.to_info_dict(task))


@router.post("/{task_id}/cancel", response_model=ResponseModel)
async def cancel_task(task_id: str) -> ResponseModel:
    """取消任务"""
    if task_manager.cancel_task(task_id):
        return ResponseModel(data={"cancelled": True})
    return ResponseModel(code=400, message="任务不存在或已完成/失败")


@router.post("/{task_id}/retry", response_model=ResponseModel)
async def retry_task(task_id: str) -> ResponseModel:
    """重试失败/取消的任务"""
    try:
        task = task_manager.retry_task(task_id)
        if not task:
            return ResponseModel(code=400, message="任务不存在或状态不允许重试")
        task_manager.submit_task(task_id)
        return ResponseModel(data=task_manager.to_info_dict(task))
    except Exception as e:
        logger.exception("重试任务失败")
        return ResponseModel(code=500, message=f"重试失败: {e}")


@router.delete("/{task_id}", response_model=ResponseModel)
async def delete_task(task_id: str) -> ResponseModel:
    """删除任务"""
    if task_manager.delete_task(task_id):
        return ResponseModel(data={"deleted": True})
    return ResponseModel(code=400, message="任务不存在或正在处理中，无法删除")


@router.get("/{task_id}/download", response_model=ResponseModel)
async def download_result(task_id: str) -> ResponseModel:
    """获取下载信息"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    if task.status != "completed":
        return ResponseModel(code=400, message="任务尚未完成")
    return ResponseModel(
        data={
            "download_url": f"/api/tasks/{task_id}/download/file",
            "filename": task.filename,
            "result_path": task.result_path,
        },
    )


@router.get("/{task_id}/download/file")
async def download_file(task_id: str):
    """下载结果文件"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    # 查找结果文件
    result_path = None
    if task.result_path and Path(task.result_path).exists():
        result_path = Path(task.result_path)
    else:
        # 在 output 目录中查找
        task_output_dir = OUTPUT_DIR / task_id
        if task_output_dir.exists():
            # 查找 .docx 或 .md 文件
            for pattern in ("*.docx", "*.md"):
                files = list(task_output_dir.glob(pattern))
                if files:
                    result_path = files[0]
                    break

    if not result_path or not result_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    return FileResponse(
        path=str(result_path),
        filename=result_path.name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{task_id}/download/mineru-docx")
async def download_mineru_docx(task_id: str):
    """下载 MinerU 提供的原始 DOCX 文件

    MinerU 线上 API 支持 extra_formats=["docx"] 时，
    会在解析结果 ZIP 中包含原始排版 DOCX 文件。
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    docx_path = task_manager.get_mineru_docx_path(task_id)
    if not docx_path:
        raise HTTPException(status_code=404, detail="MinerU 未提供 DOCX 文件或文件已不存在")

    docx_file = Path(docx_path)
    # 使用原文件名，格式化为 <原始PDF名>_MinerU.docx
    original_stem = Path(task.filename).stem
    download_name = f"{original_stem}_MinerU.docx"

    return FileResponse(
        path=str(docx_file),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{task_id}/preview", response_model=ResponseModel)
async def preview_result(task_id: str) -> ResponseModel:
    """预览任务结果"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")

    markdown_preview = task.cleaned_markdown_preview

    # 降级逻辑：如果数据库中的预览内容过短（旧任务被截断），
    # 尝试从输出目录的 cleaned.md 文件读取完整内容
    if not markdown_preview or len(markdown_preview) <= 2000:
        cleaned_md_path = Path("data/output") / task_id / "cleaned.md"
        if cleaned_md_path.exists():
            markdown_preview = cleaned_md_path.read_text(encoding="utf-8")
            # 同步更新数据库
            task.cleaned_markdown_preview = markdown_preview
            from src.db.database import SessionLocal
            db = SessionLocal()
            try:
                from src.db.crud import TaskCRUD
                TaskCRUD.update_status(db, task_id)  # 触发更新
                t = TaskCRUD.get(db, task_id)
                if t:
                    t.cleaned_markdown_preview = markdown_preview
                    db.commit()
            finally:
                db.close()

    return ResponseModel(
        data={
            "markdown_preview": markdown_preview,
            "style_config": task.style_config_preview,
        },
    )


@router.get("/{task_id}/preview/docx")
async def preview_docx(task_id: str):
    """预览 Word 文档（返回 HTML）"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    html = task_manager.get_docx_html_preview(task_id)
    if not html:
        raise HTTPException(status_code=404, detail="Word 文件不存在或转换失败")

    return HTMLResponse(content=html)

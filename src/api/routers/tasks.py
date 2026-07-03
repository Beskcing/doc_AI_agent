"""任务管理路由"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

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


@router.get("/{task_id}/preview", response_model=ResponseModel)
async def preview_result(task_id: str) -> ResponseModel:
    """预览任务结果"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    return ResponseModel(
        data={
            "markdown_preview": task.cleaned_markdown_preview,
            "style_config": task.style_config_preview,
        },
    )

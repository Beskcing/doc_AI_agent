"""任务管理路由"""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.api.models import (
    CreateTaskRequest,
    ResponseModel,
    TaskListResponse,
    TaskStatus,
)
from src.api.services.task_manager import task_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["任务"])


@router.post("", response_model=ResponseModel)
async def create_task(request: CreateTaskRequest) -> ResponseModel:
    """创建排版任务"""
    try:
        task = task_manager.create_task(
            upload_id=request.upload_id,
            filename=request.upload_id,
            standard=request.standard,
            use_rag=request.use_rag,
            llm_model=request.llm_model,
            custom_config=request.custom_config or {},
        )
        # 提交异步处理
        task_manager.submit_task(task.id)
        return ResponseModel(data=task_manager.to_info_dict(task))
    except Exception as e:
        logger.exception("创建任务失败")
        return ResponseModel(code=500, message=f"创建任务失败: {e}")


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


@router.get("/{task_id}/download", response_model=ResponseModel)
async def download_result(task_id: str) -> ResponseModel:
    """下载结果文件"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    if task.status != "completed":
        return ResponseModel(code=400, message="任务尚未完成")
    return ResponseModel(
        data={
            "download_url": f"/api/tasks/{task_id}/download/file",
            "filename": task.filename,
        },
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

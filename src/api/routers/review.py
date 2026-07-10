"""文档审查路由

提供排版后文档质量审查的 API：
- GET  /api/tasks/{task_id}/review — 获取审查结果
- POST /api/tasks/{task_id}/review/deep — 触发深度审查
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from src.api.middleware.auth import get_current_user
from src.api.models import (
    ResponseModel,
    ReviewIssue,
    ReviewResponse,
    ReviewSummary,
    TriggerDeepReviewResponse,
)
from src.api.services.docx_review_service import DocxReviewService
from src.config import AppConfig
from src.db.crud import TaskCRUD, TaskReviewCRUD
from src.db.models import TaskReviewModel, UserModel
from src.db.session import get_db_session
from src.llm_client import LLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/tasks", tags=["文档审查"])


def _get_review_service() -> DocxReviewService:
    """创建审查服务实例"""
    config = AppConfig.load()
    review_prompt = ""
    try:
        prompt_path = Path(config.paths.prompts_dir) / "docx_review_prompt.md"
        if prompt_path.exists():
            review_prompt = prompt_path.read_text(encoding="utf-8")
    except Exception:
        pass

    def _get_llm():
        try:
            return LLMClient(config.llm)
        except Exception:
            return None

    return DocxReviewService(
        config=config,
        get_llm_client=_get_llm,
        review_prompt_template=review_prompt,
    )


def _review_to_response(review: TaskReviewModel) -> ReviewResponse:
    """将数据库模型转为响应模型"""
    issues_data = review.issues or {}
    issue_list = issues_data.get("issues", [])
    summary_data = issues_data.get("summary")

    return ReviewResponse(
        review_id=review.id,
        task_id=review.task_id,
        review_type=review.review_type,
        status=review.status,
        progress=review.progress,
        current_chunk=review.current_chunk,
        total_chunks=review.total_chunks,
        issues=[ReviewIssue(**i) for i in issue_list],
        summary=ReviewSummary(**summary_data) if summary_data else None,
        error_message=review.error_message,
        created_at=review.created_at,
        completed_at=review.completed_at,
    )


@router.get("/{task_id}/review", response_model=ResponseModel)
async def get_review(
    task_id: str,
    review_type: str | None = None,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """获取任务的最新审查结果

    Args:
        task_id: 任务 ID
        review_type: 可选，筛选审查类型 (quick / deep)
    """
    with get_db_session() as db:
        # 校验任务存在且属于当前用户
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")

        review = TaskReviewCRUD.get_by_task(db, task_id, review_type=review_type)
        if not review:
            return ResponseModel(code=404, message="暂无审查结果")

        return ResponseModel(data=_review_to_response(review).model_dump())


@router.post("/{task_id}/review/deep", response_model=ResponseModel)
async def trigger_deep_review(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """触发深度审查（异步执行）

    深度审查使用 LLM 按章节分块检查全文，耗时较长。
    调用后立即返回审查记录 ID，前端通过轮询 GET 接口获取进度和结果。
    """
    with get_db_session() as db:
        # 校验任务存在且属于当前用户
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")

        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成，请等待排版完成后再审查")

        if not task.result_path:
            return ResponseModel(code=400, message="任务无输出文件，无法审查")

        # 检查是否已有运行中的深度审查
        existing = TaskReviewCRUD.get_by_task(db, task_id, review_type="deep")
        if existing and existing.status == "running":
            return ResponseModel(
                data=TriggerDeepReviewResponse(
                    review_id=existing.id,
                    status=existing.status,
                    message="深度审查正在进行中",
                ).model_dump(),
            )

    # 后台异步执行深度审查（不阻塞请求响应）
    import asyncio

    review_service = _get_review_service()

    async def _run_deep_review():
        try:
            await run_in_threadpool(review_service.deep_review, task_id)
        except Exception as e:
            logger.exception("深度审查后台执行失败: %s", e)

    asyncio.create_task(_run_deep_review())

    return ResponseModel(
        data=TriggerDeepReviewResponse(
            review_id="",
            status="pending",
            message="深度审查已启动，请通过 GET 接口轮询进度和结果",
        ).model_dump(),
    )


@router.get("/{task_id}/reviews", response_model=ResponseModel)
async def list_reviews(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """获取任务的所有审查记录"""
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")

        reviews = TaskReviewCRUD.list_by_task(db, task_id)
        return ResponseModel(
            data={"reviews": [_review_to_response(r).model_dump() for r in reviews]},
        )

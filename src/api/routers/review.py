"""文档审查路由

提供排版后文档质量审查的 API：
- GET  /api/tasks/{task_id}/review — 获取审查结果
- POST /api/tasks/{task_id}/review/deep — 触发深度审查
- POST /api/tasks/{task_id}/review/mark — 生成标记版 DOCX
- GET  /api/tasks/{task_id}/review/marked-docx — 下载标记版 DOCX
- GET  /api/tasks/{task_id}/review/marked-preview — HTML 标记预览
- POST /api/tasks/{task_id}/review/fix — 单条修正
- POST /api/tasks/{task_id}/review/fix-batch — 批量修正
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from src.api.middleware.auth import get_current_user
from src.api.models import (
    BatchFixRequest,
    FixIssueRequest,
    FixIssueResponse,
    MarkDocxResponse,
    MarkedPreviewResponse,
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


# ==================== 审查标记与修正 API ====================


@router.post("/{task_id}/review/mark", response_model=ResponseModel)
async def mark_docx(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """生成标记版 DOCX（黄色高亮 + 批注）

    在排版完成的 DOCX 中为审查发现的问题添加标记。
    返回标记版 DOCX 的路径和统计信息。
    """
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成")
        if not task.result_path:
            return ResponseModel(code=400, message="任务无输出文件")

    review_service = _get_review_service()
    result = await run_in_threadpool(review_service.generate_marked_docx, task_id)

    if result is None:
        return ResponseModel(code=500, message="生成标记版 DOCX 失败")

    return ResponseModel(data=MarkDocxResponse(**result).model_dump())


@router.get("/{task_id}/review/marked-docx", response_model=None)
async def download_marked_docx(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
):
    """下载标记版 DOCX 文件"""
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if not task.result_path:
            return ResponseModel(code=404, message="输出文件不存在")

    result_dir = Path(task.result_path).parent
    marked_path = result_dir / "review_marked.docx"

    if not marked_path.exists():
        # 首次访问时自动生成
        review_service = _get_review_service()
        result = await run_in_threadpool(review_service.generate_marked_docx, task_id)
        if result is None:
            return ResponseModel(code=500, message="生成标记版 DOCX 失败")
        marked_path = Path(result.get("marked_docx_path", ""))

    if not marked_path.exists():
        return ResponseModel(code=404, message="标记版 DOCX 不存在，请先生成")

    original_stem = Path(task.filename or "document").stem
    download_name = f"{original_stem}_审查标记.docx"

    return FileResponse(
        path=str(marked_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{task_id}/review/marked-preview", response_model=ResponseModel)
async def get_marked_preview(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """获取标记版 HTML 预览

    返回带问题高亮的 HTML 内容，前端可通过 iframe 渲染。
    """
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成")

    review_service = _get_review_service()
    result = await run_in_threadpool(review_service.generate_marked_html, task_id)

    if result is None:
        return ResponseModel(code=500, message="生成 HTML 预览失败")

    return ResponseModel(data=MarkedPreviewResponse(**result).model_dump())


@router.post("/{task_id}/review/fix", response_model=ResponseModel)
async def fix_single_issue(
    task_id: str,
    body: FixIssueRequest,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """修正单条审查 issue

    - mode=ai: LLM 自动修正
    - mode=manual: 使用 fix_text 中的文本替换
    """
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成")

    review_service = _get_review_service()
    result = await run_in_threadpool(
        review_service.fix_single_issue,
        task_id,
        body.issue_index,
        body.fix_text,
        body.mode,
    )

    if result is None:
        return ResponseModel(code=500, message="修正失败")

    # 修正后清除 HTML 缓存
    review_service.invalidate_html_cache(task_id)

    return ResponseModel(data=result)


@router.post("/{task_id}/review/requick", response_model=ResponseModel)
async def requick_review(
    task_id: str,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """重新运行快速审查

    修正后重新跑 quick_review 验证是否还有残留问题。
    """
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成")
        if not task.result_path:
            return ResponseModel(code=400, message="任务无输出文件")

    review_service = _get_review_service()
    result = await run_in_threadpool(review_service.quick_review, task_id)

    if result is None:
        return ResponseModel(code=500, message="快速审查失败")

    # 重新审查后清除 HTML 缓存
    review_service.invalidate_html_cache(task_id)

    return ResponseModel(data=result)


@router.post("/{task_id}/review/fix-batch", response_model=ResponseModel)
async def fix_batch_issues(
    task_id: str,
    body: BatchFixRequest,
    current_user: UserModel = Depends(get_current_user),
) -> ResponseModel:
    """批量修正审查 issues

    - auto_fix_low=True: 自动修正所有 low 级别 issues
    - issue_indices: 指定修正的 issue 索引列表
    """
    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id, user_id=current_user.id)
        if not task:
            return ResponseModel(code=404, message="任务不存在")
        if task.status != "completed":
            return ResponseModel(code=400, message="任务未完成")

    review_service = _get_review_service()
    result = await run_in_threadpool(
        review_service.batch_fix_issues,
        task_id,
        body.auto_fix_low,
        body.issue_indices,
    )

    if result is None:
        return ResponseModel(code=500, message="批量修正失败")

    # 修正后清除 HTML 缓存
    review_service.invalidate_html_cache(task_id)

    return ResponseModel(data=FixIssueResponse(**result).model_dump())

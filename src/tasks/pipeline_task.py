"""Celery 排版管线任务

定义异步排版任务，由 Celery Worker 执行。
每个任务独立处理一个文档的完整排版管线。

从 TaskManager._process_task 提取，作为 Celery task 运行。
"""

from __future__ import annotations

from src.tasks.celery_app import celery_app
from src.utils.logger import get_logger

logger = get_logger(__name__)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_pipeline_task(self, task_id: str) -> dict:
    """Celery 任务：执行完整的文档排版管线

    该任务会被 Worker 从 Redis 队列中取出并执行。
    失败时自动重试最多 3 次，每次间隔 60 秒。

    Args:
        task_id: 数据库中的任务 ID

    Returns:
        { "task_id": str, "status": str, "result_path": str | None }
    """
    from src.api.services.task_manager import task_manager

    logger.info("Celery 任务启动: task_id=%s", task_id)
    try:
        task_manager.process_task(task_id)
        return {"task_id": task_id, "status": "completed"}
    except Exception as exc:
        logger.exception("Celery 任务失败: task_id=%s, retry=%d", task_id, self.request.retries)
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc) from exc
        return {"task_id": task_id, "status": "failed", "error": str(exc)}

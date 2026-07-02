"""后台任务管理服务

管理文档排版任务的生命周期，支持异步处理 + 数据库持久化。
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from sqlalchemy.orm import Session

from src.db.crud import TaskCRUD
from src.db.database import SessionLocal
from src.db.models import TaskModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _get_db() -> Session:
    """获取数据库会话"""
    return SessionLocal()


class TaskManager:
    """任务管理器（单例）"""

    _instance: TaskManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._executor = ThreadPoolExecutor(max_workers=4)
        return cls._instance

    def create_task(
        self,
        upload_id: str,
        filename: str,
        standard: str,
        use_rag: bool = True,
        llm_model: str = "qwen-plus",
        custom_config: dict | None = None,
    ) -> TaskModel:
        """创建新任务（持久化到数据库）"""
        db = _get_db()
        try:
            task = TaskCRUD.create(
                db,
                upload_id=upload_id,
                filename=filename,
                standard=standard,
                status="pending",
                progress=0,
                current_step="pending",
                config={
                    "use_rag": use_rag,
                    "llm_model": llm_model,
                    **(custom_config or {}),
                },
            )
            logger.info("创建任务: %s (upload_id=%s)", task.id, upload_id)
            return task
        finally:
            db.close()

    def get_task(self, task_id: str) -> TaskModel | None:
        """获取任务"""
        db = _get_db()
        try:
            return TaskCRUD.get(db, task_id)
        finally:
            db.close()

    def list_tasks(
        self,
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
    ) -> tuple[list[TaskModel], int]:
        """获取任务列表"""
        db = _get_db()
        try:
            return TaskCRUD.list_tasks(db, page=page, page_size=page_size, status=status)
        finally:
            db.close()

    def update_status(
        self,
        task_id: str,
        status: str,
        progress: int | None = None,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> TaskModel | None:
        """更新任务状态"""
        db = _get_db()
        try:
            return TaskCRUD.update_status(
                db, task_id, status=status, progress=progress,
                current_step=current_step, error_message=error_message,
            )
        finally:
            db.close()

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        db = _get_db()
        try:
            task = TaskCRUD.get(db, task_id)
            if not task or task.status in ("completed", "failed"):
                return False
            TaskCRUD.update_status(db, task_id, status="cancelled", progress=0)
            return True
        finally:
            db.close()

    def submit_task(self, task_id: str) -> None:
        """提交任务到线程池异步处理"""
        self._executor.submit(self._process_task, task_id)

    def _process_task(self, task_id: str) -> None:
        """模拟处理任务（实际应调用工作流）"""
        self.update_status(task_id, "processing", progress=0, current_step="parse_input")
        try:
            # 模拟各阶段
            steps = [
                ("parse_input", "解析输入文档", 10),
                ("analyze_intent", "分析文档意图", 25),
                ("review_content", "审查 Markdown 内容", 40),
                ("extract_style", "提取排版样式", 60),
                ("validate_output", "校验输出", 75),
                ("render_docx", "生成 Word 文档", 90),
                ("finalize", "完成处理", 100),
            ]
            for step, desc, progress in steps:
                time.sleep(1.5)  # 模拟耗时
                self.update_status(task_id, "processing", progress=progress, current_step=step)
            self.update_status(task_id, "completed", progress=100, current_step="completed")
        except Exception as e:
            logger.exception("任务 %s 处理失败", task_id)
            self.update_status(task_id, "failed", error_message=str(e))

    def to_info_dict(self, task: TaskModel) -> dict:
        """转换为 API 响应字典"""
        return {
            "id": task.id,
            "upload_id": task.upload_id,
            "filename": task.filename,
            "standard": task.standard,
            "status": task.status,
            "progress": task.progress,
            "current_step": task.current_step,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "error_message": task.error_message,
            "file_size_mb": task.file_size_mb,
        }

    def to_detail_dict(self, task: TaskModel) -> dict:
        """转换为详情响应字典"""
        info = self.to_info_dict(task)
        info.update({
            "cleaned_markdown_preview": task.cleaned_markdown_preview,
            "style_config_preview": task.style_config_preview,
            "config": task.config,
        })
        return info


# 全局任务管理器实例
task_manager = TaskManager()

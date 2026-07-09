"""后台任务管理服务（门面模式）

管理文档排版任务的生命周期，支持异步处理 + 数据库持久化。
管线编排委托 PipelineService，预览委托 PreviewService，内容编辑委托 ContentEditService。
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from sqlalchemy.orm import Session

from src.config import AppConfig
from src.db.crud import TaskCRUD
from src.db.database import SessionLocal
from src.db.models import TaskModel
from src.db.session import get_db_session
from src.llm_client import LLMClient
from src.utils.file_utils import get_user_output_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 加载全局配置
_config = AppConfig.load()


def _get_db() -> Session:
    """获取数据库会话（向后兼容）"""
    return SessionLocal()


class TaskManager:
    """任务管理器（门面模式）

    委托调用 PipelineService / PreviewService / ContentEditService。
    保持 API 层调用兼容性，task_manager 实例的接口不变。
    """

    _instance: TaskManager | None = None
    _lock = threading.Lock()

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._executor = ThreadPoolExecutor(max_workers=4)
                    # 创建共享依赖容器和服务实例
                    from src.api.services.content_edit_service import ContentEditService
                    from src.api.services.pipeline_service import PipelineService
                    from src.api.services.preview_service import PreviewService
                    from src.api.services.service_deps import ServiceDeps

                    instance._deps = ServiceDeps(_config)
                    instance._pipeline = PipelineService(
                        deps=instance._deps,
                        update_status=instance.update_status,
                    )
                    instance._preview = PreviewService(
                        get_task_fn=instance.get_task,
                    )
                    instance._content_edit = ContentEditService(
                        deps=instance._deps,
                        get_task_fn=instance.get_task,
                        get_mineru_docx_fn=instance._preview.get_mineru_docx_path,
                        apply_style_fn=instance._pipeline._apply_style,
                        convert_to_docx_fn=instance._pipeline._convert_to_docx,
                    )
                    cls._instance = instance
        return cls._instance

    # ──────── LLM / RAG 懒加载（委托 ServiceDeps） ────────

    def _get_llm_client(self) -> LLMClient | None:
        """获取 LLM 客户端（委托 ServiceDeps 懒加载）"""
        return self._deps.get_llm_client()

    def _get_retriever(self):
        """获取 RAG 检索器（委托 ServiceDeps 懒加载）"""
        return self._deps.get_retriever()

    def _ensure_prompts(self) -> None:
        """加载提示词模板（委托 ServiceDeps 懒加载）"""
        self._deps.ensure_prompts()

    @property
    def _system_prompt(self) -> str:
        return self._deps.system_prompt

    @property
    def _intent_prompt(self) -> str:
        return self._deps.intent_prompt

    @property
    def _style_prompt(self) -> str:
        return self._deps.style_prompt

    # ──────── 任务 CRUD ────────

    def create_task(
        self,
        upload_id: str,
        filename: str,
        user_id: str,
        standard: str,
        use_rag: bool = True,
        llm_model: str = "qwen-plus",
        custom_config: dict | None = None,
    ) -> TaskModel:
        """创建新任务（持久化到数据库）"""
        file_size_mb = None
        file_path = (custom_config or {}).get("file_path")
        if file_path and Path(file_path).exists():
            file_size_mb = round(Path(file_path).stat().st_size / 1024 / 1024, 2)

        with get_db_session() as db:
            task = TaskCRUD.create(
                db,
                upload_id=upload_id,
                user_id=user_id,
                filename=filename,
                standard=standard,
                status="pending",
                progress=0,
                current_step="pending",
                file_size_mb=file_size_mb,
                config={"use_rag": use_rag, "llm_model": llm_model, **(custom_config or {})},
            )
            logger.info("创建任务: %s (upload_id=%s, file_size=%.2fMB)", task.id, upload_id, file_size_mb or 0)
            return task

    def get_task(self, task_id: str, user_id: str | None = None) -> TaskModel | None:
        """获取任务"""
        with get_db_session() as db:
            return TaskCRUD.get(db, task_id, user_id=user_id)

    def list_tasks(
        self, page: int = 1, page_size: int = 10, status: str | None = None, user_id: str | None = None
    ) -> tuple[list[TaskModel], int]:
        """获取任务列表"""
        with get_db_session() as db:
            return TaskCRUD.list_tasks(db, page=page, page_size=page_size, status=status, user_id=user_id)

    def update_status(
        self,
        task_id: str,
        status: str,
        progress: int | None = None,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> TaskModel | None:
        """更新任务状态（含竞态保护：cancelled 不被 processing 覆盖）"""
        with get_db_session() as db:
            if status == "processing":
                existing = TaskCRUD.get(db, task_id)
                if existing and existing.status == "cancelled":
                    logger.info("任务 %s 已被取消，跳过 processing 状态更新", task_id)
                    return existing
            return TaskCRUD.update_status(
                db,
                task_id,
                status=status,
                progress=progress,
                current_step=current_step,
                error_message=error_message,
            )

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        with get_db_session() as db:
            task = TaskCRUD.get(db, task_id)
            if not task or task.status in ("completed", "failed"):
                return False
            TaskCRUD.update_status(db, task_id, status="cancelled", progress=0)
            return True

    def retry_task(self, task_id: str) -> TaskModel | None:
        """重试失败的任务"""
        with get_db_session() as db:
            task = TaskCRUD.get(db, task_id)
            if not task or task.status not in ("failed", "cancelled"):
                return None
            TaskCRUD.update_status(
                db,
                task_id,
                status="pending",
                progress=0,
                current_step="pending",
                error_message=None,
            )
            return TaskCRUD.get(db, task_id)

    def delete_task(self, task_id: str) -> bool:
        """删除任务（处理中的任务不允许删除）"""
        with get_db_session() as db:
            task = TaskCRUD.get(db, task_id)
            if not task:
                return False
            if task.status == "processing":
                return False

            output_dir = get_user_output_dir(task.user_id, task_id)
            if output_dir.exists():
                import shutil

                shutil.rmtree(output_dir, ignore_errors=True)
                logger.info("任务 %s: 已清理输出目录 %s", task_id, output_dir)

            # 兼容旧格式（无 user_id 隔离的目录）
            legacy_output_dir = Path("data/output") / task_id
            if legacy_output_dir.exists():
                import shutil

                shutil.rmtree(legacy_output_dir, ignore_errors=True)
                logger.info("任务 %s: 已清理旧格式输出目录 %s", task_id, legacy_output_dir)

            TaskCRUD.delete(db, task_id)
            logger.info("任务 %s: 已删除", task_id)
            return True

    def get_stats(self, user_id: str | None = None) -> dict[str, int]:
        """获取任务统计"""
        with get_db_session() as db:
            return TaskCRUD.count_by_status(db, user_id=user_id)

    def get_disk_usage(self, user_id: str | None = None) -> dict:
        """获取磁盘用量统计

        Args:
            user_id: 可选，按用户过滤统计

        Returns:
            { output_mb, uploads_mb, total_mb, output_task_count, orphaned_count }
        """
        if user_id:
            output_dir = get_user_output_dir(user_id)
            uploads_dir = Path("data/uploads") / user_id
        else:
            output_dir = Path("data/output")
            uploads_dir = Path("data/uploads")

        def _dir_size(path: Path) -> float:
            if not path.exists():
                return 0.0
            total = 0
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
            return total / (1024 * 1024)

        output_mb = round(_dir_size(output_dir), 2)
        uploads_mb = round(_dir_size(uploads_dir), 2)
        task_count = 0
        orphaned_count = 0
        if output_dir.exists():
            # 获取所有 DB 中存在的 task_id 集合
            with get_db_session() as db:
                query = db.query(TaskModel.id)
                if user_id:
                    query = query.filter(TaskModel.user_id == user_id)
                db_task_ids = {t[0] for t in query.all()}
            for d in output_dir.iterdir():
                if d.is_dir():
                    task_count += 1
                    if d.name not in db_task_ids:
                        orphaned_count += 1

        return {
            "output_mb": output_mb,
            "uploads_mb": uploads_mb,
            "total_mb": round(output_mb + uploads_mb, 2),
            "output_task_count": task_count,
            "orphaned_count": orphaned_count,
        }

    def cleanup_old_tasks(self, older_than_days: int = 30, dry_run: bool = False) -> dict:
        """清理超过 N 天的任务输出目录（支持用户隔离目录）

        扫描策略：遍历 data/output/ 目录，包括用户隔离子目录。
        确保 DB 记录已被删除的孤儿目录也能被清理。

        Args:
            older_than_days: 清理多少天前的目录
            dry_run: 仅计算不实际删除

        Returns:
            { deleted_count, freed_mb, scanned_count, orphaned_count }
        """
        import shutil
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=older_than_days)
        output_root = Path("data/output")
        deleted_count = 0
        freed_bytes = 0
        scanned_count = 0
        orphaned_count = 0

        if not output_root.exists():
            return {"deleted_count": 0, "freed_mb": 0.0, "scanned_count": 0, "orphaned_count": 0}

        # 一次性加载 DB 中的任务信息（ID → (status, created_at)）
        db_tasks: dict[str, tuple[str, datetime]] = {}
        with get_db_session() as db:
            rows = db.query(TaskModel.id, TaskModel.status, TaskModel.created_at).all()
            db_tasks = {r[0]: (r[1], r[2]) for r in rows}

        # 收集所有需要扫描的任务目录（包括用户隔离子目录和旧格式）
        task_dirs: list[tuple[Path, str]] = []  # (path, task_id)
        for entry in output_root.iterdir():
            if not entry.is_dir():
                continue
            # 检查是否是用户 ID 子目录（UUID 格式，36 字符）
            if len(entry.name) == 36 and entry.name.count("-") == 4:
                for task_entry in entry.iterdir():
                    if task_entry.is_dir():
                        task_dirs.append((task_entry, task_entry.name))
            else:
                # 旧格式：task_id 直接在 output/ 下
                task_dirs.append((entry, entry.name))

        for task_dir, task_id in task_dirs:
            scanned_count += 1

            # 判断是否需要清理
            should_clean = False
            is_orphan = task_id not in db_tasks

            if is_orphan:
                orphaned_count += 1
                dir_mtime = datetime.fromtimestamp(task_dir.stat().st_mtime)
                if dir_mtime < cutoff:
                    should_clean = True
            else:
                status, created_at = db_tasks[task_id]
                if status in ("completed", "failed", "cancelled") and created_at < cutoff:
                    should_clean = True

            if not should_clean:
                continue

            # 计算目录大小
            dir_size = 0
            for f in task_dir.rglob("*"):
                if f.is_file():
                    try:
                        dir_size += f.stat().st_size
                    except OSError:
                        pass

            if not dry_run:
                shutil.rmtree(task_dir, ignore_errors=True)
                logger.info(
                    "清理%s输出: %s (%.2f MB)",
                    "孤儿" if is_orphan else "旧任务",
                    task_id,
                    dir_size / 1024 / 1024,
                )

            deleted_count += 1
            freed_bytes += dir_size

        freed_mb = round(freed_bytes / (1024 * 1024), 2)
        logger.info(
            "清理完成: 扫描 %d 个目录(含 %d 孤儿), 删除 %d 个, 释放 %.2f MB%s",
            scanned_count,
            orphaned_count,
            deleted_count,
            freed_mb,
            " (dry_run)" if dry_run else "",
        )
        return {
            "deleted_count": deleted_count,
            "freed_mb": freed_mb,
            "scanned_count": scanned_count,
            "orphaned_count": orphaned_count,
        }

    def get_recent_tasks(self, limit: int = 5, user_id: str | None = None) -> list[TaskModel]:
        """获取最近任务"""
        with get_db_session() as db:
            return TaskCRUD.get_recent(db, limit=limit, user_id=user_id)

    def submit_task(self, task_id: str) -> None:
        """提交任务到异步处理队列

        优先使用 Celery（需要 Redis），不可用时降级为 ThreadPoolExecutor。
        """
        self._submit_via_celery_or_thread(task_id)

    def _submit_via_celery_or_thread(self, task_id: str) -> None:
        """提交任务：Celery 优先，降级线程池"""
        try:
            from src.tasks.pipeline_task import process_pipeline_task

            # 检查 Celery broker 是否可用（简单探测）
            process_pipeline_task.delay(task_id)
            logger.info("任务 %s: 已提交到 Celery 队列", task_id)
            return
        except Exception as e:
            logger.warning("Celery 不可用 (%s)，降级为线程池处理任务 %s", e, task_id)

        # 降级：使用线程池
        self._executor.submit(self._process_task, task_id)
        logger.info("任务 %s: 已提交到线程池", task_id)

    def process_task(self, task_id: str) -> None:
        """处理任务（公开接口，供 Celery Worker 调用）

        执行完整的排版管线，与 _process_task 逻辑一致。
        """
        self._process_task(task_id)

    # ──────── 管线处理（委托 PipelineService） ────────

    def _process_task(self, task_id: str) -> None:
        """处理任务：委托 PipelineService 执行完整管线"""
        with get_db_session() as db:
            task = TaskCRUD.get(db, task_id)
            if not task:
                logger.error("任务不存在: %s", task_id)
                return
            if task.status == "cancelled":
                logger.info("任务 %s 已被取消，跳过处理", task_id)
                return
            config = task.config or {}
            file_path = config.get("file_path")
            target_standard = task.standard or ""
            template_id = config.get("template_id")

        self.update_status(task_id, "processing", progress=0, current_step="parse_input")

        try:
            cleaned_md, styled_path, mineru_docx, style_config = self._pipeline.process_task(
                task_id=task_id,
                file_path=file_path,
                target_standard=target_standard,
                template_id=template_id,
                config=config,
            )
            self.update_status(task_id, "completed", progress=100, current_step="completed")
        except Exception as e:
            logger.exception("任务 %s 处理失败", task_id)
            current_task = self.get_task(task_id)
            if current_task and current_task.status == "cancelled":
                logger.info("任务 %s 已被取消，不覆盖为 failed 状态", task_id)
                return
            self.update_status(task_id, "failed", error_message=str(e))

    # ──────── 样式管理（委托 PipelineService） ────────

    def apply_template_to_task(
        self, task_id: str, style_config: dict, record_adjustment: bool = True, source: str = "apply_template"
    ) -> str:
        """对已完成任务重新应用样式模板（委托 PipelineService）"""
        return self._pipeline.apply_template_to_task(
            task_id,
            style_config,
            self.get_task,
            record_adjustment,
            source,
        )

    def upload_corrected_docx(self, task_id: str, corrected_docx_path: str) -> dict:
        """处理用户上传的修正后 DOCX 文件（委托 PipelineService）"""
        return self._pipeline.upload_corrected_docx(task_id, corrected_docx_path, self.get_task)

    def _default_style_config(self) -> dict:
        """默认样式配置（委托 PipelineService）"""
        return self._pipeline._default_style_config()

    # ──────── 预览（委托 PreviewService） ────────

    def get_docx_html_preview(self, task_id: str) -> str | None:
        """DOCX → HTML 预览（委托 PreviewService）"""
        return self._preview.get_docx_html_preview(task_id)

    def get_mineru_docx_html_preview(self, task_id: str) -> str | None:
        """MinerU DOCX → HTML 预览（委托 PreviewService）"""
        return self._preview.get_mineru_docx_html_preview(task_id)

    def get_mineru_docx_path(self, task_id: str) -> str | None:
        """获取 MinerU DOCX 路径（委托 PreviewService）"""
        return self._preview.get_mineru_docx_path(task_id)

    def get_original_pdf_path(self, task_id: str) -> str | None:
        """获取原始 PDF 路径（委托 PreviewService）"""
        return self._preview.get_original_pdf_path(task_id)

    def get_pdf_page_images(self, task_id: str, dpi: int = 150, page: int = 1, page_size: int = 5) -> dict | None:
        """PDF → 页面图片预览（委托 PreviewService）"""
        return self._preview.get_pdf_page_images(task_id, dpi, page, page_size)

    # ──────── 内容编辑（委托 ContentEditService） ────────

    def update_content(
        self, task_id: str, content: str, content_type: str = "markdown", regenerate_docx: bool = True
    ) -> dict:
        """更新文档内容（委托 ContentEditService）"""
        return self._content_edit.update_content(task_id, content, content_type, regenerate_docx)

    def get_content_html(self, task_id: str) -> str | None:
        """获取文档 HTML 内容（委托 ContentEditService）"""
        return self._content_edit.get_content_html(task_id)

    def update_content_via_llm(self, task_id: str, message: str, session_id: str | None = None) -> dict:
        """LLM 对话修改文档内容（委托 ContentEditService）"""
        return self._content_edit.update_content_via_llm(task_id, message, session_id)

    # ──────── 信息转换 ────────

    def to_info_dict(self, task: TaskModel) -> dict:
        """转换为 API 响应字典"""
        config = task.config or {}
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
            "mineru_docx_available": bool(config.get("mineru_docx_path")),
            "auto_matched_template": config.get("auto_matched_template"),
        }

    def to_detail_dict(self, task: TaskModel) -> dict:
        """转换为详情响应字典"""
        info = self.to_info_dict(task)
        info.update(
            {
                "cleaned_markdown_preview": task.cleaned_markdown_preview,
                "style_config_preview": task.style_config_preview,
                "config": task.config,
                "result_path": task.result_path,
                "result_json_path": task.result_json_path,
            }
        )
        return info


# 全局任务管理器实例
task_manager = TaskManager()

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

    def get_task(self, task_id: str) -> TaskModel | None:
        """获取任务"""
        with get_db_session() as db:
            return TaskCRUD.get(db, task_id)

    def list_tasks(self, page: int = 1, page_size: int = 10, status: str | None = None) -> tuple[list[TaskModel], int]:
        """获取任务列表"""
        with get_db_session() as db:
            return TaskCRUD.list_tasks(db, page=page, page_size=page_size, status=status)

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

            output_dir = Path("data/output") / task_id
            if output_dir.exists():
                import shutil

                shutil.rmtree(output_dir, ignore_errors=True)
                logger.info("任务 %s: 已清理输出目录 %s", task_id, output_dir)

            TaskCRUD.delete(db, task_id)
            logger.info("任务 %s: 已删除", task_id)
            return True

    def get_stats(self) -> dict[str, int]:
        """获取任务统计"""
        with get_db_session() as db:
            return TaskCRUD.count_by_status(db)

    def get_recent_tasks(self, limit: int = 5) -> list[TaskModel]:
        """获取最近任务"""
        with get_db_session() as db:
            return TaskCRUD.get_recent(db, limit=limit)

    def submit_task(self, task_id: str) -> None:
        """提交任务到线程池异步处理"""
        self._executor.submit(self._process_task, task_id)

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

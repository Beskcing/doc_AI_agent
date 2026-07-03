"""后台任务管理服务

管理文档排版任务的生命周期，支持异步处理 + 数据库持久化。
集成 MinerU 线上 API 进行 PDF 解析。
"""

from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from src.config import AppConfig
from src.db.crud import TaskCRUD
from src.db.database import SessionLocal
from src.db.models import TaskModel
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 加载全局配置
_config = AppConfig.load()


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
        # 计算文件大小
        file_size_mb = None
        file_path = (custom_config or {}).get("file_path")
        if file_path and Path(file_path).exists():
            file_size_mb = round(Path(file_path).stat().st_size / 1024 / 1024, 2)

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
                file_size_mb=file_size_mb,
                config={
                    "use_rag": use_rag,
                    "llm_model": llm_model,
                    **(custom_config or {}),
                },
            )
            logger.info("创建任务: %s (upload_id=%s, file_size=%.2fMB)", task.id, upload_id, file_size_mb or 0)
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

    def retry_task(self, task_id: str) -> TaskModel | None:
        """重试失败的任务"""
        db = _get_db()
        try:
            task = TaskCRUD.get(db, task_id)
            if not task or task.status not in ("failed", "cancelled"):
                return None
            TaskCRUD.update_status(
                db, task_id, status="pending", progress=0,
                current_step="pending", error_message=None,
            )
            return TaskCRUD.get(db, task_id)
        finally:
            db.close()

    def delete_task(self, task_id: str) -> bool:
        """删除任务

        删除数据库记录并清理关联的输出文件。
        处理中（processing）的任务不允许删除，需先取消。
        """
        db = _get_db()
        try:
            task = TaskCRUD.get(db, task_id)
            if not task:
                return False
            if task.status == "processing":
                # 处理中的任务不允许直接删除
                return False

            # 清理输出目录
            output_dir = Path("data/output") / task_id
            if output_dir.exists():
                import shutil
                shutil.rmtree(output_dir, ignore_errors=True)
                logger.info("任务 %s: 已清理输出目录 %s", task_id, output_dir)

            # 删除数据库记录
            TaskCRUD.delete(db, task_id)
            logger.info("任务 %s: 已删除", task_id)
            return True
        finally:
            db.close()

    def get_stats(self) -> dict[str, int]:
        """获取任务统计"""
        db = _get_db()
        try:
            return TaskCRUD.count_by_status(db)
        finally:
            db.close()

    def get_recent_tasks(self, limit: int = 5) -> list[TaskModel]:
        """获取最近任务"""
        db = _get_db()
        try:
            return TaskCRUD.get_recent(db, limit=limit)
        finally:
            db.close()

    def submit_task(self, task_id: str) -> None:
        """提交任务到线程池异步处理"""
        self._executor.submit(self._process_task, task_id)

    def _process_task(self, task_id: str) -> None:
        """处理任务：MinerU 解析 → Markdown 清洗 → 样式渲染

        集成 MinerU 线上 API 进行 PDF 解析，后续步骤使用工作流管线。
        """
        # 阶段 0: 读取任务配置（短会话）
        db = _get_db()
        try:
            task = TaskCRUD.get(db, task_id)
            if not task:
                logger.error("任务不存在: %s", task_id)
                return
            config = task.config or {}
            file_path = config.get("file_path")
        finally:
            db.close()  # Bug#6 修复：关闭短会话，不在长耗时操作中持有

        self.update_status(task_id, "processing", progress=0, current_step="parse_input")

        try:
            # ──────── 阶段 1: MinerU 解析 ────────
            markdown_content = ""

            if file_path and Path(file_path).exists():
                ext = Path(file_path).suffix.lower()

                if ext == ".pdf":
                    # PDF 文件：使用 MinerU 解析
                    markdown_content, extract_dir = self._parse_with_mineru(task_id, file_path)
                elif ext in (".md", ".txt"):
                    # Markdown/TXT 文件：直接读取
                    markdown_content = Path(file_path).read_text(encoding="utf-8")
                    extract_dir = str(Path(file_path).parent)
                    self.update_status(task_id, "processing", progress=10, current_step="parse_input")
                else:
                    raise ValueError(f"不支持的文件类型: {ext}")
            else:
                raise FileNotFoundError(f"上传文件不存在: {file_path}")

            # Bug#6 修复：用新会话保存解析结果
            db = _get_db()
            try:
                TaskCRUD.update_status(
                    db, task_id,
                    progress=15,
                    current_step="parse_input_done",
                )
                task_db = TaskCRUD.get(db, task_id)
                if task_db:
                    task_db.cleaned_markdown_preview = markdown_content
                    db.commit()
            finally:
                db.close()

            # ──────── 阶段 2: Markdown 清洗 ────────
            self.update_status(task_id, "processing", progress=20, current_step="review_content")
            cleaned_markdown = self._clean_markdown(task_id, markdown_content, extract_dir)

            # 存储完整清洗后的 Markdown（供预览使用）
            # 同时写入文件和数据库，文件作为降级回读数据源
            result_dir = Path("data/output") / task_id
            result_dir.mkdir(parents=True, exist_ok=True)
            cleaned_md_path = result_dir / "cleaned.md"
            cleaned_md_path.write_text(cleaned_markdown, encoding="utf-8")

            db = _get_db()
            try:
                task_db = TaskCRUD.get(db, task_id)
                if task_db:
                    task_db.cleaned_markdown_preview = cleaned_markdown
                    db.commit()
            finally:
                db.close()

            # ──────── 阶段 2.5: 生成样式配置 ────────
            style_config = self._generate_style_config(task_id, cleaned_markdown)

            # ──────── 阶段 3: Pandoc 转换 → DOCX ────────
            self.update_status(task_id, "processing", progress=40, current_step="render_docx")
            docx_path = self._convert_to_docx(task_id, cleaned_markdown, extract_dir)

            # ──────── 阶段 4: 国标样式渲染 ────────
            self.update_status(task_id, "processing", progress=70, current_step="apply_style")
            styled_path = self._apply_style(task_id, docx_path, style_config)

            # ──────── 阶段 5: 最终化 ────────
            self.update_status(task_id, "processing", progress=90, current_step="finalize")

            # Bug#3 修复：保存 result_path 和 style_config_preview
            # Bug#1 修复：completed_at 由 CRUD 自动设置
            db = _get_db()
            try:
                task_db = TaskCRUD.get(db, task_id)
                if task_db:
                    task_db.style_config_preview = style_config
                    # 保存最终 DOCX 路径
                    task_db.result_path = styled_path
                    db.commit()
            finally:
                db.close()

            self.update_status(task_id, "completed", progress=100, current_step="completed")
        except Exception as e:
            logger.exception("任务 %s 处理失败", task_id)
            self.update_status(task_id, "failed", error_message=str(e))

    def _generate_style_config(self, task_id: str, markdown_content: str) -> dict:
        """生成基本样式配置（模拟 LLM 样式提取）

        实际项目中应由 LLM 根据 RAG 检索结果生成。
        """
        return {
            "page_layout": {
                "paper_size": "A4",
                "margin_top_cm": 3.7,
                "margin_bottom_cm": 3.5,
                "margin_left_cm": 2.8,
                "margin_right_cm": 2.6,
            },
            "title": {
                "font": "方正小标宋简体",
                "size_pt": 22,
                "align": "center",
                "bold": True,
            },
            "body": {
                "font": "仿宋_GB2312",
                "size_pt": 16,
                "line_spacing": 1.5,
                "first_line_indent": 2,
            },
            "heading": {
                "font": "黑体",
                "size_pt": 16,
                "bold": True,
            },
            "table": {
                "border_width": 1,
                "header_bold": True,
                "rag_note": "依据检索到的复杂表格规范，表头需加粗且边框设为1pt",
            },
            "rag_sources": ["国标排版规范_v2.0_第3章"],
        }

    def _parse_with_mineru(self, task_id: str, file_path: str) -> tuple[str, str]:
        """使用 MinerU 解析 PDF 文件

        根据 config.mineru.mode 选择 online 或 local 模式。

        Returns:
            (markdown_content, extract_dir): 解析后的 Markdown 和资源解压目录
        """
        mineru_cfg = _config.mineru
        output_dir = Path("data/output") / task_id

        def on_progress(stage: str, info: dict) -> None:
            """MinerU 解析进度回调"""
            stage_map = {
                "uploading": ("上传文件中", 2),
                "submitting": ("提交任务中", 2),
                "pending": ("排队中", 3),
                "running": ("解析中", 5),
                "converting": ("格式转换中", 8),
                "done": ("解析完成", 10),
            }
            desc, prog = stage_map.get(stage, (stage, 5))
            self.update_status(task_id, "processing", progress=prog, current_step=f"mineru_{stage}")
            logger.info("任务 %s MinerU 进度: %s (%s)", task_id, desc, info)

        try:
            from src.tools.mineru_parser import MinerUParser

            parser = MinerUParser(
                output_dir=str(output_dir),
                mode=mineru_cfg.mode,
                api_token=mineru_cfg.get_token(),
                model_version=mineru_cfg.model_version,
            )

            logger.info("任务 %s: MinerU 解析 PDF: %s (mode=%s)", task_id, file_path, mineru_cfg.mode)
            parsed_doc = parser.parse_pdf(file_path, on_progress=on_progress)
            markdown_content = parsed_doc.raw_markdown
            extract_dir = parsed_doc.metadata.get("extract_dir", str(output_dir))

            logger.info("任务 %s: MinerU 解析完成, Markdown %d 字符", task_id, len(markdown_content))
            return markdown_content, extract_dir

        except Exception as e:
            logger.error("任务 %s: MinerU 解析失败: %s", task_id, e)
            raise

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
            "result_path": task.result_path,
            "result_json_path": task.result_json_path,
        })
        return info

    def get_docx_html_preview(self, task_id: str) -> str | None:
        """将任务生成的 DOCX 转换为 HTML 供前端预览

        使用 Pandoc 将 DOCX 转换为 HTML fragment，保留表格、图片等格式。
        不使用 --standalone/--embed-resources，生成轻量 HTML 片段，
        避免大文件 base64 编码导致内容过重被截断。
        """
        task = self.get_task(task_id)
        if not task or not task.result_path:
            return None

        result_path = Path(task.result_path)
        if not result_path.exists():
            return None

        try:
            import pypandoc
            html = pypandoc.convert_file(
                str(result_path),
                "html",
                format="docx",
                extra_args=["--wrap=none"],
            )
            logger.info("任务 %s: DOCX→HTML 预览生成成功, %d 字符", task_id, len(html))
            return html
        except Exception as e:
            logger.error("任务 %s: DOCX→HTML 转换失败: %s", task_id, e)
            return None

    # ──────── 管线辅助方法 ────────

    def _clean_markdown(self, task_id: str, markdown_content: str, extract_dir: str) -> str:
        """清洗 Markdown：修复 OCR 错误、校验图片路径、HTML 表格→Pipe 转换

        Args:
            task_id: 任务 ID
            markdown_content: MinerU 输出的原始 Markdown
            extract_dir: MinerU 解压目录（图片等资源所在位置）

        Returns:
            清洗后的 Markdown（管道表格格式）
        """
        from src.tools.markdown_cleaner import MarkdownCleaner
        from src.tools.html_to_pipe import convert_html_tables_in_markdown

        # 1. 插入图片引用（从 content_list.json 提取表格图片路径）
        markdown_content = self._insert_image_refs(markdown_content, extract_dir)

        # 2. Markdown 规则化清洗
        cleaner = MarkdownCleaner(base_dir=extract_dir)
        result = cleaner.clean(markdown_content)
        cleaned = result.cleaned_markdown

        # 3. HTML 表格 → Markdown 管道表格（Pandoc raw_html 不转为 DOCX 表格）
        cleaned = convert_html_tables_in_markdown(cleaned)

        logger.info("任务 %s: Markdown 清洗完成, %d 处修改, %d 个缺失图片",
                    task_id, len(result.changes_log), result.images_missing)
        return cleaned

    def _insert_image_refs(self, markdown: str, extract_dir: str) -> str:
        """从 MinerU content_list.json 提取图片引用并插入 Markdown

        MinerU 的 full.md 不包含表格图片引用，需要从 content_list.json 中提取
        表格的 img_path，并在对应表格前插入图片引用。

        Args:
            markdown: MinerU full.md 内容
            extract_dir: MinerU 解压目录

        Returns:
            插入图片引用后的 Markdown
        """
        import json
        from pathlib import Path

        extract_path = Path(extract_dir)
        # 查找 content_list.json
        json_files = list(extract_path.glob("*_content_list.json"))
        if not json_files:
            return markdown

        try:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return markdown
        except (json.JSONDecodeError, OSError):
            return markdown

        # 收集所有表格的图片引用
        table_images: list[str] = []
        for item in data:
            if item.get("type") == "table" and item.get("img_path"):
                img_path = item["img_path"]
                # 验证图片文件存在
                full_path = extract_path / img_path
                if full_path.exists():
                    table_images.append(img_path)

        if not table_images:
            return markdown

        # 在 Markdown 中每个 <table> 标签前插入对应的图片引用
        import re
        table_pattern = re.compile(r"<table[\s>]", re.IGNORECASE)
        img_idx = 0

        def insert_img(match: re.Match) -> str:
            nonlocal img_idx
            if img_idx < len(table_images):
                img = table_images[img_idx]
                img_idx += 1
                return f"![表格图片]({img})\n\n{match.group(0)}"
            return match.group(0)

        return table_pattern.sub(insert_img, markdown, count=len(table_images))

    def _convert_to_docx(self, task_id: str, markdown: str, extract_dir: str) -> str:
        """通过 Pandoc 将 Markdown 转换为 DOCX

        关键设计：
        1. 将 Markdown 写入临时文件（而非通过 stdin），确保图片相对路径可解析
        2. 设置 Pandoc 工作目录为 extract_dir，使图片路径正确
        3. 使用 --from=markdown+raw_html+tex_math_dollars 支持 HTML 表格和 LaTeX 公式

        Args:
            task_id: 任务 ID
            markdown: 清洗后的 Markdown
            extract_dir: MinerU 解压目录

        Returns:
            生成的 DOCX 文件路径
        """
        import pypandoc
        import tempfile

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        docx_path = result_dir / "formatted.docx"
        extract_path = Path(extract_dir)

        # 关键：将 Markdown 写入 extract_dir（图片所在目录），
        # 确保 Pandoc 能通过相对路径找到图片文件
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False,
            dir=str(extract_path),
        ) as tmp:
            tmp.write(markdown)
            md_tmp_path = tmp.name

        try:
            logger.info("任务 %s: 执行 Pandoc 转换 (extract_dir=%s)", task_id, extract_dir)

            pypandoc.convert_file(
                md_tmp_path,
                "docx",
                outputfile=str(docx_path),
                format="markdown+raw_html+tex_math_dollars",
                extra_args=[
                    "--resource-path", extract_dir,
                ],
            )

            if not docx_path.exists() or docx_path.stat().st_size == 0:
                raise RuntimeError("Pandoc 生成的 DOCX 文件为空")

            logger.info("任务 %s: DOCX 生成成功: %s (%.2f MB)",
                        task_id, docx_path, docx_path.stat().st_size / 1024 / 1024)
            return str(docx_path)

        finally:
            # 清理临时文件
            try:
                Path(md_tmp_path).unlink()
            except OSError:
                pass

    def _apply_style(self, task_id: str, docx_path: str, style_config: dict) -> str:
        """应用国标排版样式到 DOCX

        Args:
            task_id: 任务 ID
            docx_path: 输入的 DOCX 文件路径
            style_config: 样式配置字典

        Returns:
            样式化后的 DOCX 文件路径
        """
        from src.models.style_config import StyleConfig
        from src.tools.docx_styler import DocxStyler

        result_dir = Path("data/output") / task_id
        styled_path = result_dir / "formatted_styled.docx"

        try:
            style = StyleConfig.model_validate(style_config)
        except Exception as e:
            logger.warning("任务 %s: 样式配置校验失败，使用默认样式: %s", task_id, e)
            style = StyleConfig(
                page_layout={"paper_size": "A4", "margin_top_cm": 3.7, "margin_bottom_cm": 3.5,
                             "margin_left_cm": 2.8, "margin_right_cm": 2.6,
                             "header_distance_cm": 1.5, "footer_distance_cm": 1.75},
                body_style={"font": {"family": "仿宋_GB2312", "size_pt": 16},
                           "line_spacing": 1.5, "first_line_indent_chars": 2,
                           "alignment": "justify"},
            )

        styler = DocxStyler(style)
        report = styler.apply_gb_style(docx_path, styled_path)

        if not report.success:
            logger.warning("任务 %s: 样式应用部分失败: %s", task_id, report.warnings)
            # 回退：使用 Pandoc 生成的原始 DOCX
            import shutil
            shutil.copy(docx_path, styled_path)
            logger.info("任务 %s: 回退到 Pandoc 原始输出", task_id)

        logger.info("任务 %s: 样式应用完成 → %s", task_id, styled_path)
        return str(styled_path)


# 全局任务管理器实例
task_manager = TaskManager()

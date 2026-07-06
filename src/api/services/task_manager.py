"""后台任务管理服务

管理文档排版任务的生命周期，支持异步处理 + 数据库持久化。
集成 MinerU 线上 API 进行 PDF 解析。
"""

from __future__ import annotations

import json
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
from src.llm_client import LLMClient
from src.models.document_schema import IntentAnalysis
from src.utils.json_validator import safe_parse_llm_json
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

    # LLM / RAG 懒加载缓存
    _llm_client: LLMClient | None = None
    _retriever = None  # HybridRetriever，延迟导入避免依赖问题
    _prompts_loaded: bool = False
    _system_prompt: str = ""
    _intent_prompt: str = ""
    _style_prompt: str = ""

    def __new__(cls) -> TaskManager:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._executor = ThreadPoolExecutor(max_workers=4)
        return cls._instance

    # ──────── LLM / RAG 懒加载 ────────

    def _get_llm_client(self) -> LLMClient | None:
        """懒加载 LLM 客户端，初始化失败时返回 None"""
        if self._llm_client is None:
            try:
                self._llm_client = LLMClient(_config.llm)
                logger.info("LLM 客户端初始化成功: provider=%s", _config.llm.default_provider)
            except Exception as e:
                logger.warning("LLM 客户端初始化失败，将使用降级模式: %s", e)
        return self._llm_client

    def _get_retriever(self):
        """懒加载 RAG 混合检索器，初始化失败时返回 None"""
        if self._retriever is None:
            try:
                from src.rag.knowledge_base_config import KnowledgeBaseManager

                kb_manager = KnowledgeBaseManager(_config.rag)
                kb_manager.initialize()
                self._retriever = kb_manager.get_retriever()
                logger.info("RAG 知识库加载成功")
            except Exception as e:
                logger.warning("RAG 知识库初始化失败，将不使用 RAG: %s", e)
        return self._retriever

    def _ensure_prompts(self) -> None:
        """懒加载提示词模板"""
        if self._prompts_loaded:
            return
        prompts_dir = Path(_config.paths.prompts_dir)
        for name, attr in [
            ("system_prompt.md", "_system_prompt"),
            ("intent_parsing_prompt.md", "_intent_prompt"),
            ("style_extraction_prompt.md", "_style_prompt"),
        ]:
            path = prompts_dir / name
            if path.exists():
                setattr(self, attr, path.read_text(encoding="utf-8"))
            else:
                logger.warning("提示词文件不存在: %s", path)
        self._prompts_loaded = True

    def _analyze_intent(self, task_id: str, markdown_content: str, target_standard: str = "") -> IntentAnalysis:
        """意图分析（LLM + RAG）

        LLM 不可用时降级为默认意图。

        Args:
            task_id: 任务 ID
            markdown_content: 原始 Markdown
            target_standard: 用户指定的目标标准

        Returns:
            IntentAnalysis 意图分析结果
        """
        self.update_status(task_id, "processing", progress=15, current_step="analyze_intent")

        llm = self._get_llm_client()
        self._ensure_prompts()

        # LLM 不可用 → 降级
        if not llm or not self._intent_prompt:
            logger.warning("任务 %s: LLM 不可用，使用默认意图", task_id)
            intent = IntentAnalysis()
            if target_standard:
                intent.detected_standard = target_standard
            return intent

        try:
            prompt = self._intent_prompt.replace("{markdown_content}", markdown_content[:3000])
            response = llm.invoke(prompt, self._system_prompt or None)

            try:
                json_data = safe_parse_llm_json(response)
                intent = IntentAnalysis.model_validate(json_data)
            except Exception:
                logger.warning("任务 %s: 意图解析 JSON 校验失败，使用默认意图", task_id)
                intent = IntentAnalysis()

            if target_standard:
                intent.detected_standard = target_standard

            logger.info("任务 %s: 意图分析完成 - 类型=%s, 标准=%s",
                        task_id, intent.document_type, intent.detected_standard)
            return intent
        except Exception as e:
            logger.error("任务 %s: 意图分析失败: %s", task_id, e)
            intent = IntentAnalysis()
            if target_standard:
                intent.detected_standard = target_standard
            return intent

    def _auto_match_template(self, standard: str) -> dict | None:
        """根据标准号自动匹配数据库中的模板（功能2）

        Args:
            standard: 检测到的标准号（如 GB/T 14454.13-2008）

        Returns:
            匹配的模板信息 dict，无匹配时返回 None
        """
        from src.db.crud import StyleTemplateCRUD

        db = _get_db()
        try:
            template = StyleTemplateCRUD.match_by_standard(db, standard)
            if template:
                return {
                    "id": template.id,
                    "name": template.name,
                    "description": template.description,
                }
            return None
        except Exception as e:
            logger.warning("自动匹配模板失败: %s", e)
            return None
        finally:
            db.close()

    def _record_style_adjustment(
        self,
        task_id: str,
        source: str,
        before_config: dict | None,
        after_config: dict | None,
        standard: str | None = None,
    ) -> None:
        """记录样式调整历史（功能4：迭代学习）

        Args:
            task_id: 任务 ID
            source: 调整来源 (edit_style/upload_corrected/apply_template/chat)
            before_config: 调整前的样式配置
            after_config: 调整后的样式配置
            standard: 关联标准号
        """
        from src.db.crud import StyleAdjustmentHistoryCRUD

        # 生成差异摘要
        diff_summary = self._compute_style_diff(before_config, after_config)

        db = _get_db()
        try:
            StyleAdjustmentHistoryCRUD.create(
                db,
                task_id=task_id,
                source=source,
                before_config=before_config,
                after_config=after_config,
                diff_summary=diff_summary,
                standard=standard,
            )
            logger.info("任务 %s: 样式调整已记录 (source=%s, diff=%s)", task_id, source, diff_summary[:100] if diff_summary else "无")
        except Exception as e:
            logger.warning("记录样式调整失败: %s", e)
        finally:
            db.close()

    @staticmethod
    def _compute_style_diff(before: dict | None, after: dict | None) -> str:
        """计算两个样式配置的差异摘要"""
        if not before or not after:
            return "新建样式配置" if after else "删除样式配置"

        changes = []

        # 比较正文样式
        before_body = before.get("body_style", {})
        after_body = after.get("body_style", {})
        before_font = before_body.get("font", {})
        after_font = after_body.get("font", {})

        for key in ["family", "east_asia_family", "size_pt", "bold"]:
            old_val = before_font.get(key)
            new_val = after_font.get(key)
            if old_val != new_val:
                changes.append(f"正文字体.{key}: {old_val} → {new_val}")

        for key in ["line_spacing", "first_line_indent_chars", "alignment"]:
            old_val = before_body.get(key)
            new_val = after_body.get(key)
            if old_val != new_val:
                changes.append(f"正文.{key}: {old_val} → {new_val}")

        # 比较页面布局
        before_pl = before.get("page_layout", {})
        after_pl = after.get("page_layout", {})
        for key in ["margin_top_cm", "margin_bottom_cm", "margin_left_cm", "margin_right_cm"]:
            old_val = before_pl.get(key)
            new_val = after_pl.get(key)
            if old_val != new_val:
                changes.append(f"页面.{key}: {old_val} → {new_val}")

        # 比较表格样式
        before_ts = before.get("table_style", {})
        after_ts = after.get("table_style", {})
        for key in ["border_style", "border_width_pt", "header_bold", "table_alignment"]:
            old_val = before_ts.get(key)
            new_val = after_ts.get(key)
            if old_val != new_val:
                changes.append(f"表格.{key}: {old_val} → {new_val}")

        return "; ".join(changes) if changes else "无显著差异"

    def _get_few_shot_examples(self, standard: str | None = None, limit: int = 3) -> str:
        """获取历史样式调整记录作为 few-shot 示例（功能4：迭代学习）

        Args:
            standard: 标准号，用于筛选相关记录
            limit: 最多返回的示例数量

        Returns:
            格式化的 few-shot 示例文本
        """
        from src.db.crud import StyleAdjustmentHistoryCRUD

        db = _get_db()
        try:
            records = StyleAdjustmentHistoryCRUD.list_recent(db, limit=limit, standard=standard)
            if not records:
                return "暂无历史调整记录。"

            examples = []
            for record in records:
                if record.before_config and record.after_config and record.diff_summary:
                    examples.append(
                        f"- 调整来源: {record.source}\n"
                        f"  差异: {record.diff_summary}\n"
                        f"  调整前: {json.dumps(record.before_config, ensure_ascii=False)[:200]}...\n"
                        f"  调整后: {json.dumps(record.after_config, ensure_ascii=False)[:200]}..."
                    )

            return "\n".join(examples) if examples else "暂无有效的历史调整记录。"
        except Exception as e:
            logger.warning("获取 few-shot 示例失败: %s", e)
            return "暂无历史调整记录。"
        finally:
            db.close()

    def _default_style_config(self) -> dict:
        """默认样式配置（LLM 降级用）

        键名严格对齐 StyleConfig 模型，确保 StyleConfig.model_validate() 可通过。
        """
        return {
            "page_layout": {
                "paper_size": "A4",
                "margin_top_cm": 3.7,
                "margin_bottom_cm": 3.5,
                "margin_left_cm": 2.8,
                "margin_right_cm": 2.6,
                "header_distance_cm": 1.5,
                "footer_distance_cm": 1.75,
            },
            "heading_styles": [
                {
                    "level": 1,
                    "font": {"family": "黑体", "size_pt": 22, "bold": True},
                    "alignment": "center",
                    "line_spacing": 2.0,
                },
                {
                    "level": 2,
                    "font": {"family": "黑体", "size_pt": 16, "bold": True},
                    "alignment": "left",
                    "line_spacing": 1.5,
                },
            ],
            "body_style": {
                "font": {"family": "仿宋_GB2312", "size_pt": 16},
                "line_spacing": 1.5,
                "first_line_indent_chars": 2,
                "alignment": "justify",
            },
            "table_style": {
                "border_style": "single",
                "border_width_pt": 0.5,
                "header_font": {"family": "黑体", "size_pt": 12, "bold": True},
                "body_font": {"family": "仿宋_GB2312", "size_pt": 10.5},
                "header_bold": True,
            },
            "rag_sources": [],
        }

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
        """更新任务状态

        Bug 修复：如果任务已被取消（cancelled），不允许被 processing 覆盖。
        仅允许 cancelled → cancelled（幂等）或终态覆盖。
        """
        db = _get_db()
        try:
            # 检查竞态：如果任务已取消且新状态是 processing，跳过更新
            if status == "processing":
                existing = TaskCRUD.get(db, task_id)
                if existing and existing.status == "cancelled":
                    logger.info("任务 %s 已被取消，跳过 processing 状态更新", task_id)
                    return existing
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
            # Bug 修复：检查任务是否已被取消
            if task.status == "cancelled":
                logger.info("任务 %s 已被取消，跳过处理", task_id)
                return
            config = task.config or {}
            file_path = config.get("file_path")
            target_standard = task.standard or ""
        finally:
            db.close()  # Bug#6 修复：关闭短会话，不在长耗时操作中持有

        self.update_status(task_id, "processing", progress=0, current_step="parse_input")

        try:
            # ──────── 阶段 1: MinerU 解析 ────────
            markdown_content = ""
            mineru_docx_path: str | None = None

            if file_path and Path(file_path).exists():
                ext = Path(file_path).suffix.lower()

                if ext == ".pdf":
                    # PDF 文件：使用 MinerU 解析
                    markdown_content, extract_dir, mineru_docx_path = self._parse_with_mineru(task_id, file_path)
                    # 保存 MinerU DOCX 路径到任务配置
                    if mineru_docx_path:
                        self._save_mineru_docx_path(task_id, mineru_docx_path)
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

            # ──────── 阶段 1.5: 意图分析（LLM + RAG） ────────
            intent = self._analyze_intent(task_id, markdown_content, target_standard)

            # ──────── 阶段 1.6: 自动匹配模板（功能2） ────────
            if not template_id and intent.detected_standard:
                matched_template = self._auto_match_template(intent.detected_standard)
                if matched_template:
                    template_id = matched_template["id"]
                    logger.info("任务 %s: 自动匹配模板: %s (%s)", task_id, matched_template["name"], template_id)
                    # 保存匹配结果到任务配置
                    db = _get_db()
                    try:
                        from sqlalchemy.orm.attributes import flag_modified
                        task_db = TaskCRUD.get(db, task_id)
                        if task_db:
                            new_config = {**(task_db.config or {}), "auto_matched_template": matched_template}
                            task_db.config = new_config
                            db.commit()
                    finally:
                        db.close()

            # ──────── 阶段 2: Markdown 清洗（规则预处理 + LLM 智能审查） ────────
            self.update_status(task_id, "processing", progress=20, current_step="review_content")
            cleaned_markdown = self._clean_markdown(task_id, markdown_content, extract_dir, intent=intent)

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

            # ──────── 阶段 2.5: 样式提取（LLM + RAG 或模板） ────────
            template_id = config.get("template_id")
            if template_id:
                # 使用指定模板的样式配置，跳过 LLM 提取
                style_config = self._get_template_style(template_id)
                logger.info("任务 %s: 使用模板 %s 的样式配置", task_id, template_id)
            else:
                style_config = self._generate_style_config(task_id, cleaned_markdown, intent)

            # ──────── 阶段 3: 确定基础 DOCX ────────
            # PDF 文件优先使用 MinerU 原始 DOCX；非 PDF 文件回退到 Pandoc 转换
            self.update_status(task_id, "processing", progress=40, current_step="prepare_docx")
            if mineru_docx_path and Path(mineru_docx_path).exists():
                docx_path = mineru_docx_path
                logger.info("任务 %s: 使用 MinerU 原始 DOCX 作为样式基础: %s", task_id, docx_path)
            else:
                # 回退：Pandoc MD→DOCX（保留代码路径，用于非 PDF 文件）
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
            # Bug 修复：检查任务是否已被取消，避免覆盖 cancelled 状态
            current_task = self.get_task(task_id)
            if current_task and current_task.status == "cancelled":
                logger.info("任务 %s 已被取消，不覆盖为 failed 状态", task_id)
                return
            self.update_status(task_id, "failed", error_message=str(e))

    def _generate_style_config(self, task_id: str, markdown_content: str, intent: IntentAnalysis) -> dict:
        """使用 LLM + RAG 生成样式配置

        LLM 不可用时降级为默认样式配置。

        Args:
            task_id: 任务 ID
            markdown_content: 清洗后的 Markdown（用于上下文参考）
            intent: 意图分析结果

        Returns:
            样式配置字典
        """
        self.update_status(task_id, "processing", progress=30, current_step="extract_style")

        llm = self._get_llm_client()
        self._ensure_prompts()
        retriever = self._get_retriever()

        # LLM 不可用 → 降级
        if not llm or not self._style_prompt:
            logger.warning("任务 %s: LLM 不可用，使用默认样式配置", task_id)
            return self._default_style_config()

        try:
            # RAG 检索排版规范
            rag_context = "无 RAG 检索结果，请使用国标默认值。"
            rag_sources = []
            if retriever:
                query = f"{intent.document_type} {intent.detected_standard or ''} 排版规范"
                results = retriever.retrieve(query)
                if results:
                    rag_context = "\n\n".join(r.content for r in results[:5])
                    rag_sources = [f"{r.source} ({r.section})" for r in results]

            # 构建特殊元素描述
            special = []
            if intent.has_complex_tables:
                special.append("包含复杂表格")
            if intent.has_formulas:
                special.append("包含数学公式")
            if intent.has_chemical_structures:
                special.append("包含化学结构式")

            # 填充提示词模板
            prompt = self._style_prompt.replace("{document_type}", intent.document_type or "通用文档")
            prompt = prompt.replace("{detected_standard}", intent.detected_standard or "GB/T 9704")
            prompt = prompt.replace("{special_elements}", "、".join(special) if special else "无特殊元素")
            prompt = prompt.replace("{rag_context}", rag_context)
            # 功能4：注入历史调整 few-shot 示例
            few_shot = self._get_few_shot_examples(standard=intent.detected_standard, limit=3)
            prompt = prompt.replace("{few_shot_examples}", few_shot)

            response = llm.invoke(prompt, self._system_prompt or None)
            json_data = safe_parse_llm_json(response)

            # 补充 RAG 来源
            if rag_sources:
                json_data["rag_sources"] = rag_sources

            logger.info("任务 %s: LLM 样式提取成功", task_id)
            return json_data
        except Exception as e:
            logger.error("任务 %s: LLM 样式提取失败，降级为默认配置: %s", task_id, e)
            return self._default_style_config()

    def _parse_with_mineru(self, task_id: str, file_path: str) -> tuple[str, str, str | None]:
        """使用 MinerU 解析 PDF 文件

        根据 config.mineru.mode 选择 online 或 local 模式。
        online 模式时自动请求 extra_formats=["docx"] 以获取 MinerU 原始 DOCX。

        Returns:
            (markdown_content, extract_dir, mineru_docx_path): 解析后的 Markdown、资源解压目录、MinerU DOCX 路径
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
            # online 模式时请求 extra_formats=["docx"] 以获取 MinerU 原始 DOCX
            extra_formats = ["docx"] if mineru_cfg.mode == "online" else None
            parsed_doc = parser.parse_pdf(file_path, on_progress=on_progress, extra_formats=extra_formats)
            markdown_content = parsed_doc.raw_markdown
            extract_dir = parsed_doc.metadata.get("extract_dir", str(output_dir))
            mineru_docx_path = parsed_doc.metadata.get("mineru_docx_path")

            logger.info(
                "任务 %s: MinerU 解析完成, Markdown %d 字符, DOCX=%s",
                task_id, len(markdown_content), mineru_docx_path or "无",
            )
            return markdown_content, extract_dir, mineru_docx_path

        except Exception as e:
            logger.error("任务 %s: MinerU 解析失败: %s", task_id, e)
            raise

    def _save_mineru_docx_path(self, task_id: str, mineru_docx_path: str) -> None:
        """将 MinerU 提供的 DOCX 文件路径保存到任务配置中"""
        from sqlalchemy.orm.attributes import flag_modified
        db = _get_db()
        try:
            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                # 创建新 dict 以确保 SQLAlchemy 检测到 JSON 列变化
                new_config = {**(task_db.config or {}), "mineru_docx_path": mineru_docx_path}
                task_db.config = new_config
                db.commit()
                logger.info("任务 %s: 已保存 MinerU DOCX 路径: %s", task_id, mineru_docx_path)
        finally:
            db.close()

    def _get_template_style(self, template_id: str) -> dict:
        """从数据库获取模板的样式配置

        Args:
            template_id: 模板 ID

        Returns:
            样式配置字典，模板不存在时返回默认配置
        """
        from src.db.crud import StyleTemplateCRUD

        db = _get_db()
        try:
            template = StyleTemplateCRUD.get(db, template_id)
            if template:
                return template.style_config
            logger.warning("模板不存在: %s，使用默认样式", template_id)
            return self._default_style_config()
        finally:
            db.close()

    def apply_template_to_task(self, task_id: str, style_config: dict, record_adjustment: bool = True, source: str = "apply_template") -> str:
        """对已完成任务重新应用样式模板

        使用任务的基础 DOCX（MinerU 原始或 Pandoc 生成）重新渲染样式。

        Args:
            task_id: 任务 ID
            style_config: 新的样式配置
            record_adjustment: 是否记录样式调整历史（功能4）
            source: 调整来源标记

        Returns:
            样式化后的 DOCX 文件路径
        """
        # 获取任务信息
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status != "completed":
            raise ValueError(f"任务尚未完成，无法应用模板")

        # 记录调整前的样式配置
        before_config = task.style_config_preview

        config = task.config or {}

        # 确定基础 DOCX 路径
        # 优先使用 MinerU 原始 DOCX，其次使用已生成的 DOCX
        base_docx = config.get("mineru_docx_path")
        if not base_docx or not Path(base_docx).exists():
            # 回退：使用当前 result_path 作为基础
            base_docx = task.result_path
            if not base_docx or not Path(base_docx).exists():
                # 最后回退：在输出目录查找
                result_dir = Path("data/output") / task_id
                if result_dir.exists():
                    for pattern in ("full.docx", "formatted.docx", "formatted_styled.docx"):
                        candidate = result_dir / pattern
                        if candidate.exists():
                            base_docx = str(candidate)
                            break

        if not base_docx or not Path(base_docx).exists():
            raise ValueError(f"找不到基础 DOCX 文件，无法重新应用模板")

        logger.info("任务 %s: 重新应用模板，基础 DOCX: %s", task_id, base_docx)

        # 应用新样式
        styled_path = self._apply_style(task_id, base_docx, style_config)

        # 更新数据库
        db = _get_db()
        try:
            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.style_config_preview = style_config
                task_db.result_path = styled_path
                db.commit()
                logger.info("任务 %s: 模板应用完成，结果: %s", task_id, styled_path)
        finally:
            db.close()

        # 功能4：记录样式调整历史
        if record_adjustment:
            self._record_style_adjustment(
                task_id=task_id,
                source=source,
                before_config=before_config,
                after_config=style_config,
                standard=task.standard,
            )

        return styled_path

    def upload_corrected_docx(self, task_id: str, corrected_docx_path: str) -> dict:
        """处理用户上传的修正后 DOCX 文件（功能1：用户直接修正DOC）

        流程：
        1. 使用 DocxStyleExtractor 从修正后的 DOCX 提取样式
        2. 用提取的样式重新渲染 DOCX
        3. 记录样式调整历史（功能4）

        Args:
            task_id: 任务 ID
            corrected_docx_path: 用户上传的修正后 DOCX 文件路径

        Returns:
            {"style_config": ..., "result_path": ...}
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status != "completed":
            raise ValueError(f"任务尚未完成，无法上传修正文件")

        before_config = task.style_config_preview

        # 1. 从修正后的 DOCX 提取样式
        from src.tools.docx_style_extractor import DocxStyleExtractor

        extractor = DocxStyleExtractor()
        style_config = extractor.extract(corrected_docx_path)

        logger.info("任务 %s: 从修正后 DOCX 提取样式成功", task_id)

        # 2. 用提取的样式重新渲染
        styled_path = self.apply_template_to_task(
            task_id, style_config, record_adjustment=False, source="upload_corrected"
        )

        # 3. 记录样式调整历史
        self._record_style_adjustment(
            task_id=task_id,
            source="upload_corrected",
            before_config=before_config,
            after_config=style_config,
            standard=task.standard,
        )

        return {
            "style_config": style_config,
            "result_path": styled_path,
        }

    def get_mineru_docx_path(self, task_id: str) -> str | None:
        """获取 MinerU 提供的 DOCX 文件路径"""
        task = self.get_task(task_id)
        if not task:
            return None
        config = task.config or {}
        docx_path = config.get("mineru_docx_path")
        if docx_path and Path(docx_path).exists():
            return docx_path
        return None

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
        info.update({
            "cleaned_markdown_preview": task.cleaned_markdown_preview,
            "style_config_preview": task.style_config_preview,
            "config": task.config,
            "result_path": task.result_path,
            "result_json_path": task.result_json_path,
        })
        return info

    def get_docx_html_preview(self, task_id: str) -> str | None:
        """将任务生成的最终 DOCX 转换为 HTML 供前端预览

        使用 Pandoc 将 DOCX 转换为 HTML，内嵌图片资源（base64），
        确保前端 iframe 预览时图片能正确显示。
        """
        task = self.get_task(task_id)
        if not task or not task.result_path:
            return None

        result_path = Path(task.result_path)
        if not result_path.exists():
            return None

        try:
            import pypandoc
            # 使用 --standalone --embed-resources 内嵌图片为 base64，
            # 避免前端 iframe 预览时图片 404
            html = pypandoc.convert_file(
                str(result_path),
                "html",
                format="docx",
                extra_args=["--wrap=none", "--standalone", "--embed-resources"],
            )
            logger.info("任务 %s: DOCX→HTML 预览生成成功, %d 字符", task_id, len(html))
            return html
        except Exception as e:
            logger.error("任务 %s: DOCX→HTML 转换失败: %s", task_id, e)
            return None

    def get_mineru_docx_html_preview(self, task_id: str) -> str | None:
        """将 MinerU 原始 DOCX 转换为 HTML 供前端预览

        与 get_docx_html_preview 逻辑相同，但输入为 MinerU 提供的原始 DOCX，
        用于展示 MinerU 解析后的原始排版效果（样式渲染前）。
        """
        docx_path = self.get_mineru_docx_path(task_id)
        if not docx_path:
            return None

        try:
            import pypandoc
            html = pypandoc.convert_file(
                str(docx_path),
                "html",
                format="docx",
                extra_args=["--wrap=none", "--standalone", "--embed-resources"],
            )
            logger.info("任务 %s: MinerU DOCX→HTML 预览生成成功, %d 字符", task_id, len(html))
            return html
        except Exception as e:
            logger.error("任务 %s: MinerU DOCX→HTML 转换失败: %s", task_id, e)
            return None

    # ──────── 管线辅助方法 ────────

    def _clean_markdown(
        self,
        task_id: str,
        markdown_content: str,
        extract_dir: str,
        intent: IntentAnalysis | None = None,
    ) -> str:
        """清洗 Markdown：规则预处理 + LLM 智能审查 + HTML 表格→Pipe 转换

        两阶段清洗：
        1. pre_clean: 规则化预处理（全角转半角、断行修复、乱码清理等）
        2. llm_review: LLM 智能审查（语义级 OCR 错误修复）

        Args:
            task_id: 任务 ID
            markdown_content: MinerU 输出的原始 Markdown
            extract_dir: MinerU 解压目录（图片等资源所在位置）
            intent: 意图分析结果（用于 LLM 审查上下文）

        Returns:
            清洗后的 Markdown（管道表格格式）
        """
        from src.tools.markdown_cleaner import MarkdownCleaner
        from src.tools.html_to_pipe import convert_html_tables_in_markdown

        # 1. 插入图片引用（从 content_list.json 提取表格图片路径）
        markdown_content = self._insert_image_refs(markdown_content, extract_dir)

        # 2. Markdown 两阶段清洗（规则预处理 + LLM 智能审查）
        cleaner = MarkdownCleaner(llm_client=self._get_llm_client(), base_dir=extract_dir)
        result = cleaner.clean(markdown_content, context=intent)
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

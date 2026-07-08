"""管线编排服务

负责文档排版的核心处理流程：
MinerU解析 → 意图分析 → Markdown清洗 → 样式提取/匹配 → 样式渲染

从 TaskManager 提取，保持单一职责。
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from src.api.services.service_deps import ServiceDeps
from src.db.session import get_db_session
from src.models.document_schema import IntentAnalysis
from src.utils.json_validator import safe_parse_llm_json
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.tools.formatters.base import BaseDocxFormatter

logger = get_logger(__name__)


class PipelineService:
    """管线编排服务

    封装文档排版的核心处理流程，通过 ServiceDeps 获取 LLM/RAG/Prompts 依赖。
    """

    def __init__(
        self,
        deps: ServiceDeps,
        update_status: Callable[..., None],
    ):
        """初始化管线服务

        Args:
            deps: 共享依赖容器（LLM/RAG/Prompts）
            update_status: 任务状态更新回调
                update_status(task_id, status, progress=..., current_step=..., error_message=...)
        """
        self.deps = deps
        self._update_status = update_status

    def process_task(
        self,
        task_id: str,
        file_path: str,
        target_standard: str,
        template_id: str | None,
        config: dict,
    ) -> tuple[str, str, str | None, dict]:
        """执行完整管线

        Returns:
            (cleaned_markdown, styled_docx_path, mineru_docx_path, style_config)
        """
        # ── 阶段 1: MinerU 解析 ──
        markdown_content = ""
        mineru_docx_path: str | None = None
        extract_dir = ""

        if file_path and Path(file_path).exists():
            ext = Path(file_path).suffix.lower()
            if ext == ".pdf":
                markdown_content, extract_dir, mineru_docx_path = self._parse_input(task_id, file_path)
                if mineru_docx_path:
                    self._save_mineru_docx_path(task_id, mineru_docx_path)
            elif ext in (".md", ".txt"):
                markdown_content = Path(file_path).read_text(encoding="utf-8")
                extract_dir = str(Path(file_path).parent)
                self._update_status(task_id, "processing", progress=10, current_step="parse_input")
            else:
                raise ValueError(f"不支持的文件类型: {ext}")
        else:
            raise FileNotFoundError(f"上传文件不存在: {file_path}")

        # 保存解析结果
        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            TaskCRUD.update_status(db, task_id, progress=15, current_step="parse_input_done")
            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.cleaned_markdown_preview = markdown_content
                db.commit()

        # ── 阶段 1.5: 意图分析 ──
        intent = self._analyze_intent(task_id, markdown_content, target_standard)

        # ── 阶段 1.6: 自动匹配模板 ──
        # 注意：如目标标准已有注册 Formatter，跳过模板匹配，直接使用 Formatter
        if not template_id and intent.detected_standard:
            registry_key = self._standard_to_registry_key(intent.detected_standard)
            from src.tools.formatters.registry import is_registered

            if not is_registered(registry_key):
                matched = self._auto_match_template(intent.detected_standard)
                if matched:
                    template_id = matched["id"]
                    logger.info("任务 %s: 自动匹配模板: %s (%s)", task_id, matched["name"], template_id)
                    with get_db_session() as db:
                        from src.db.crud import TaskCRUD

                        task_db = TaskCRUD.get(db, task_id)
                        if task_db:
                            new_config = {**(task_db.config or {}), "auto_matched_template": matched}
                            task_db.config = new_config
                            db.commit()
            else:
                logger.info(
                    "任务 %s: 标准 %s 已注册 Formatter，跳过模板匹配",
                    task_id,
                    intent.detected_standard,
                )

        # ── 阶段 2: Markdown 清洗 ──
        self._update_status(task_id, "processing", progress=20, current_step="review_content")
        cleaned_markdown = self._clean_markdown(task_id, markdown_content, extract_dir, intent=intent)

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        cleaned_md_path = result_dir / "cleaned.md"
        cleaned_md_path.write_text(cleaned_markdown, encoding="utf-8")

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.cleaned_markdown_preview = cleaned_markdown
                db.commit()

        # ── 阶段 2.5: 样式提取 ──
        if template_id:
            style_config = self._get_template_style(template_id)
            logger.info("任务 %s: 使用模板 %s 的样式配置", task_id, template_id)
        else:
            # 无模板时：MinerU DOCX 路径由 GbtDocxFormatter 硬编码处理（不依赖 LLM）
            # 仅 Pandoc 降级路径需要 LLM 生成 style_config
            style_config = self._generate_style_config(task_id, cleaned_markdown, intent)

        # ── 阶段 3: 确定基础 DOCX ──
        self._update_status(task_id, "processing", progress=40, current_step="prepare_docx")
        applied_format: dict = {"source": "llm"}
        if mineru_docx_path and Path(mineru_docx_path).exists():
            docx_path = mineru_docx_path

            if not template_id:
                # 无模板 + MinerU DOCX → 查询注册表
                formatter = self._resolve_formatter(intent.detected_standard)
                if formatter is not None:
                    logger.info(
                        "任务 %s: 使用注册 Formatter: %s (%s)",
                        task_id,
                        formatter.display_name,
                        formatter.standard_id,
                    )
                    style_config = self._default_style_config()
                    styled_path = self._apply_registered_formatter(task_id, docx_path, formatter)
                    applied_format = {
                        "source": "formatter",
                        "name": formatter.display_name,
                        "id": formatter.standard_id,
                    }
                else:
                    # 无注册 Formatter → DocxNormalizer + DocxStyler
                    logger.info("任务 %s: 无注册 Formatter，降级使用 DocxStyler", task_id)
                    from src.tools.docx_normalizer import DocxNormalizer

                    normalizer = DocxNormalizer()
                    normalized_path = str(result_dir / "normalized.docx")
                    docx_path = normalizer.normalize(docx_path, normalized_path)
                    logger.info(
                        "任务 %s: DOCX 内容规整完成, %d 处更改",
                        task_id,
                        len(normalizer.changes),
                    )
                    self._update_status(task_id, "processing", progress=70, current_step="apply_style")
                    styled_path = self._apply_style(task_id, docx_path, style_config)
            else:
                # 有模板 → DocxNormalizer + DocxStyler
                logger.info("任务 %s: 使用 MinerU 原始 DOCX + 模板样式", task_id)
                from src.db.crud import StyleTemplateCRUD

                with get_db_session() as db:
                    tmpl = StyleTemplateCRUD.get(db, template_id)
                    if tmpl:
                        applied_format = {
                            "source": "template",
                            "name": tmpl.name,
                            "id": tmpl.id,
                            "standard": tmpl.standard,
                        }

                from src.tools.docx_normalizer import DocxNormalizer

                normalizer = DocxNormalizer()
                normalized_path = str(result_dir / "normalized.docx")
                docx_path = normalizer.normalize(docx_path, normalized_path)
                logger.info("任务 %s: DOCX 内容规整完成, %d 处更改", task_id, len(normalizer.changes))

                # ── 阶段 4: 模板样式渲染 ──
                self._update_status(task_id, "processing", progress=70, current_step="apply_style")
                styled_path = self._apply_style(task_id, docx_path, style_config)
        else:
            logger.warning("任务 %s: MinerU 未输出 DOCX，降级使用 Pandoc 转换", task_id)
            docx_path = self._convert_to_docx(task_id, cleaned_markdown, extract_dir)

            # ── 阶段 4: 国标样式渲染 ──
            self._update_status(task_id, "processing", progress=70, current_step="apply_style")
            styled_path = self._apply_style(task_id, docx_path, style_config)

        # ── 阶段 5: 最终化 ──
        self._update_status(task_id, "processing", progress=90, current_step="finalize")

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.style_config_preview = style_config
                task_db.result_path = styled_path
                new_config = {**(task_db.config or {}), "applied_format": applied_format}
                task_db.config = new_config
                db.commit()

        return cleaned_markdown, styled_path, mineru_docx_path, style_config

    def _parse_input(self, task_id: str, file_path: str) -> tuple[str, str, str | None]:
        """使用 MinerU 解析 PDF"""
        mineru_cfg = self.deps.config.mineru
        output_dir = Path("data/output") / task_id

        def on_progress(stage: str, info: dict) -> None:
            stage_map = {
                "uploading": ("上传文件中", 2),
                "submitting": ("提交任务中", 2),
                "pending": ("排队中", 3),
                "running": ("解析中", 5),
                "converting": ("格式转换中", 8),
                "done": ("解析完成", 10),
            }
            desc, prog = stage_map.get(stage, (stage, 5))
            self._update_status(task_id, "processing", progress=prog, current_step=f"mineru_{stage}")
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
            extra_formats = ["docx"] if mineru_cfg.mode == "online" else None
            parsed_doc = parser.parse_pdf(file_path, on_progress=on_progress, extra_formats=extra_formats)
            markdown_content = parsed_doc.raw_markdown
            extract_dir = parsed_doc.metadata.get("extract_dir", str(output_dir))
            mineru_docx_path = parsed_doc.metadata.get("mineru_docx_path")
            logger.info(
                "任务 %s: MinerU 解析完成, Markdown %d 字符, DOCX=%s",
                task_id,
                len(markdown_content),
                mineru_docx_path or "无",
            )
            return markdown_content, extract_dir, mineru_docx_path
        except Exception as e:
            logger.error("任务 %s: MinerU 解析失败: %s", task_id, e)
            raise

    def _save_mineru_docx_path(self, task_id: str, mineru_docx_path: str) -> None:
        """将 MinerU DOCX 路径保存到任务配置"""
        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                new_config = {**(task_db.config or {}), "mineru_docx_path": mineru_docx_path}
                task_db.config = new_config
                db.commit()
                logger.info("任务 %s: 已保存 MinerU DOCX 路径: %s", task_id, mineru_docx_path)

    def _analyze_intent(self, task_id: str, markdown_content: str, target_standard: str = "") -> IntentAnalysis:
        """意图分析（LLM + RAG）"""
        self._update_status(task_id, "processing", progress=15, current_step="analyze_intent")
        llm = self.deps.get_llm_client()
        self.deps.ensure_prompts()

        if not llm or not self.deps.intent_prompt:
            logger.warning("任务 %s: LLM 不可用，使用默认意图", task_id)
            intent = IntentAnalysis()
            if target_standard:
                intent.detected_standard = target_standard
            return intent

        try:
            prompt = self.deps.intent_prompt.replace("{markdown_content}", markdown_content[:3000])
            response = llm.invoke(prompt, self.deps.system_prompt or None).content
            try:
                json_data = safe_parse_llm_json(response)
                intent = IntentAnalysis.model_validate(json_data)
            except Exception:
                logger.warning("任务 %s: 意图解析 JSON 校验失败，使用默认意图", task_id)
                intent = IntentAnalysis()
            if target_standard:
                intent.detected_standard = target_standard
            logger.info(
                "任务 %s: 意图分析完成 - 类型=%s, 标准=%s", task_id, intent.document_type, intent.detected_standard
            )
            return intent
        except Exception as e:
            logger.error("任务 %s: 意图分析失败: %s", task_id, e)
            intent = IntentAnalysis()
            if target_standard:
                intent.detected_standard = target_standard
            return intent

    def _auto_match_template(self, standard: str) -> dict | None:
        """根据标准号自动匹配数据库中的模板"""
        from src.db.crud import StyleTemplateCRUD

        with get_db_session() as db:
            try:
                template = StyleTemplateCRUD.match_by_standard(db, standard)
                if template:
                    return {"id": template.id, "name": template.name, "description": template.description}
                return None
            except Exception as e:
                logger.warning("自动匹配模板失败: %s", e)
                return None

    def _clean_markdown(
        self, task_id: str, markdown_content: str, extract_dir: str, intent: IntentAnalysis | None = None
    ) -> str:
        """清洗 Markdown：规则预处理 + LLM 智能审查 + HTML 表格→Pipe 转换"""
        from src.tools.html_to_pipe import convert_html_tables_in_markdown
        from src.tools.markdown_cleaner import MarkdownCleaner

        markdown_content = self._insert_image_refs(markdown_content, extract_dir)
        cleaner = MarkdownCleaner(llm_client=self.deps.get_llm_client(), base_dir=extract_dir)
        result = cleaner.clean(markdown_content, context=intent)
        cleaned = result.cleaned_markdown

        # 内容规整：日期合并、拆分标题合并、TOC删除、双空格修正
        from src.tools.content_normalizer import ContentNormalizer

        normalizer = ContentNormalizer()
        cleaned = normalizer.normalize(cleaned)
        logger.info(
            "任务 %s: 内容规整完成, %d 处更改: %s",
            task_id,
            len(normalizer.changes),
            normalizer.changes[:5],
        )

        cleaned = convert_html_tables_in_markdown(cleaned)
        logger.info(
            "任务 %s: Markdown 清洗完成, %d 处修改, %d 个缺失图片",
            task_id,
            len(result.changes_log),
            result.images_missing,
        )
        return cleaned

    def _insert_image_refs(self, markdown: str, extract_dir: str) -> str:
        """从 MinerU content_list.json 提取图片引用并插入 Markdown"""
        extract_path = Path(extract_dir)
        json_files = list(extract_path.glob("*_content_list.json"))
        if not json_files:
            return markdown

        try:
            data = json.loads(json_files[0].read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return markdown
        except (json.JSONDecodeError, OSError):
            return markdown

        table_images: list[str] = []
        for item in data:
            if item.get("type") == "table" and item.get("img_path"):
                img_path = item["img_path"]
                full_path = extract_path / img_path
                if full_path.exists():
                    table_images.append(img_path)

        if not table_images:
            return markdown

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

    def _generate_style_config(self, task_id: str, markdown_content: str, intent: IntentAnalysis) -> dict:
        """使用 LLM + RAG 生成样式配置"""
        self._update_status(task_id, "processing", progress=30, current_step="extract_style")
        llm = self.deps.get_llm_client()
        self.deps.ensure_prompts()
        retriever = self.deps.get_retriever()

        if not llm or not self.deps.style_prompt:
            logger.warning("任务 %s: LLM 不可用，使用默认样式配置", task_id)
            return self._default_style_config()

        try:
            rag_context = "无 RAG 检索结果，请使用国标默认值。"
            rag_sources = []
            if retriever:
                query = f"{intent.document_type} {intent.detected_standard or ''} 排版规范"
                results = retriever.retrieve(query)
                if results:
                    rag_context = "\n\n".join(r.content for r in results[:5])
                    rag_sources = [f"{r.source} ({r.section})" for r in results]

            special = []
            if intent.has_complex_tables:
                special.append("包含复杂表格")
            if intent.has_formulas:
                special.append("包含数学公式")
            if intent.has_chemical_structures:
                special.append("包含化学结构式")

            prompt = self.deps.style_prompt.replace("{document_type}", intent.document_type or "通用文档")
            prompt = prompt.replace("{detected_standard}", intent.detected_standard or "GB/T 9704")
            prompt = prompt.replace("{special_elements}", "、".join(special) if special else "无特殊元素")
            prompt = prompt.replace("{rag_context}", rag_context)
            few_shot = self._get_few_shot_examples(standard=intent.detected_standard, limit=3)
            prompt = prompt.replace("{few_shot_examples}", few_shot)

            response = llm.invoke(prompt, self.deps.system_prompt or None).content
            json_data = safe_parse_llm_json(response)
            if rag_sources:
                json_data["rag_sources"] = rag_sources
            logger.info("任务 %s: LLM 样式提取成功", task_id)
            return json_data
        except Exception as e:
            logger.error("任务 %s: LLM 样式提取失败，降级为默认配置: %s", task_id, e)
            return self._default_style_config()

    def _get_template_style(self, template_id: str) -> dict:
        """从数据库获取模板的样式配置"""
        from src.db.crud import StyleTemplateCRUD

        with get_db_session() as db:
            template = StyleTemplateCRUD.get(db, template_id)
            if template:
                return template.style_config
            logger.warning("模板不存在: %s，使用默认样式", template_id)
            return self._default_style_config()

    def _convert_to_docx(self, task_id: str, markdown: str, extract_dir: str) -> str:
        """通过 Pandoc 将 Markdown 转换为 DOCX"""
        import tempfile

        import pypandoc

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        docx_path = result_dir / "formatted.docx"
        extract_path = Path(extract_dir)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".md",
            encoding="utf-8",
            delete=False,
            dir=str(extract_path),
        ) as tmp:
            tmp.write(markdown)
            md_tmp_path = tmp.name

        try:
            logger.info("任务 %s: 执行 Pandoc 转换 (extract_dir=%s)", task_id, extract_dir)
            extra_args = ["--resource-path", extract_dir, "--standalone"]
            ref_docx = Path("configs/reference.docx")
            if ref_docx.exists():
                extra_args.extend(["--reference-doc", str(ref_docx)])
            pypandoc.convert_file(
                md_tmp_path,
                "docx",
                outputfile=str(docx_path),
                format="markdown+raw_html+tex_math_dollars",
                extra_args=extra_args,
            )
            if not docx_path.exists() or docx_path.stat().st_size == 0:
                raise RuntimeError("Pandoc 生成的 DOCX 文件为空")
            logger.info(
                "任务 %s: DOCX 生成成功: %s (%.2f MB)", task_id, docx_path, docx_path.stat().st_size / 1024 / 1024
            )
            return str(docx_path)
        finally:
            try:
                Path(md_tmp_path).unlink()
            except OSError:
                pass

    def _apply_style(self, task_id: str, docx_path: str, style_config: dict) -> str:
        """应用国标排版样式到 DOCX"""
        from src.models.style_config import StyleConfig
        from src.tools.docx_styler import DocxStyler

        result_dir = Path("data/output") / task_id
        styled_path = result_dir / "formatted_styled.docx"

        try:
            style = StyleConfig.model_validate(style_config)
        except Exception as e:
            logger.warning("任务 %s: 样式配置校验失败，使用默认样式: %s", task_id, e)
            style = StyleConfig(
                page_layout={
                    "paper_size": "A4",
                    "margin_top_cm": 2.5,
                    "margin_bottom_cm": 2.5,
                    "margin_left_cm": 2.5,
                    "margin_right_cm": 2.1,
                    "header_distance_cm": 1.5,
                    "footer_distance_cm": 1.75,
                },
                body_style={
                    "font": {"family": "Times New Roman", "east_asia_family": "宋体", "size_pt": 10.5},
                    "line_spacing": 1.0,
                    "first_line_indent_chars": 2,
                    "alignment": "justify",
                },
            )

        styler = DocxStyler(style)
        report = styler.apply_gb_style(docx_path, styled_path)

        if not report.success:
            logger.warning("任务 %s: 样式应用部分失败: %s", task_id, report.warnings)
            import shutil

            shutil.copy(docx_path, styled_path)
            logger.info("任务 %s: 回退到原始输出", task_id)

        logger.info("任务 %s: 样式应用完成 → %s", task_id, styled_path)
        return str(styled_path)

    @staticmethod
    def _standard_to_registry_key(standard: str) -> str:
        """将标准号转换为注册表 key 格式

        Examples:
            "GB/T 1.1" → "gbt_1_1"
            "GB/T 9704" → "gbt_9704"
            "GB 5009.225" → "gb_5009_225"
        """
        key = standard.lower().replace("/", "").replace(" ", "_").replace("-", "_").replace(".", "_")
        while "__" in key:
            key = key.replace("__", "_")
        return key.strip("_")

    def _resolve_formatter(self, standard: str | None) -> BaseDocxFormatter | None:
        """根据标准号查找注册的 Formatter 实例

        Returns:
            Formatter 实例，或 None（未注册或 standard 为空）
        """
        if not standard:
            return None
        from src.tools.formatters.registry import get_formatter

        registry_key = self._standard_to_registry_key(standard)
        formatter_cls = get_formatter(registry_key)
        if formatter_cls is not None:
            return formatter_cls()
        return None

    def _apply_registered_formatter(self, task_id: str, docx_path: str, formatter: BaseDocxFormatter) -> str:
        """使用注册的 Formatter 格式化 DOCX

        替代原 _apply_gbt_format，支持任意已注册的 BaseDocxFormatter。

        Args:
            task_id: 任务 ID
            docx_path: 输入 DOCX 路径
            formatter: 已注册的 Formatter 实例

        Returns:
            输出 DOCX 路径
        """
        result_dir = Path("data/output") / task_id
        styled_path = result_dir / "formatted_styled.docx"

        self._update_status(task_id, "processing", progress=50, current_step="formatter")
        report = formatter.process(docx_path, str(styled_path))

        if not report.success:
            logger.warning("任务 %s: Formatter(%s) 部分失败: %s", task_id, formatter.display_name, report.warnings)
            import shutil

            shutil.copy(docx_path, styled_path)
            logger.info("任务 %s: 回退到原始输出", task_id)

        logger.info(
            "任务 %s: Formatter(%s) 完成 → %s (段落=%d, 标题=%d, 表格=%d)",
            task_id,
            formatter.display_name,
            styled_path,
            report.paragraphs_styled,
            report.headings_styled,
            report.tables_styled,
        )
        return str(styled_path)

    # 向后兼容：保留旧方法名，内部委托到注册表
    def _apply_gbt_format(self, task_id: str, docx_path: str) -> str:
        """向后兼容：使用 GB/T 1.1 Formatter 格式化

        已废弃：请使用 _apply_registered_formatter + _resolve_formatter。
        保留此方法以避免破坏现有调用。
        """
        from src.tools.formatters.registry import get_formatter

        formatter_cls = get_formatter("gbt_1.1")
        if formatter_cls is None:
            # 降级：直接导入（兼容未注册场景）
            from src.tools.formatters.gbt_1_1 import GbtDocxFormatter

            formatter = GbtDocxFormatter()
        else:
            formatter = formatter_cls()
        return self._apply_registered_formatter(task_id, docx_path, formatter)

    def apply_template_to_task(
        self,
        task_id: str,
        style_config: dict,
        get_task_fn,
        record_adjustment: bool = True,
        source: str = "apply_template",
    ) -> str:
        """对已完成任务重新应用样式模板"""
        task = get_task_fn(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status != "completed":
            raise ValueError("任务尚未完成，无法应用模板")

        before_config = task.style_config_preview
        config = task.config or {}

        base_docx = config.get("mineru_docx_path")
        if not base_docx or not Path(base_docx).exists():
            base_docx = task.result_path
            if not base_docx or not Path(base_docx).exists():
                result_dir = Path("data/output") / task_id
                if result_dir.exists():
                    for pattern in ("full.docx", "formatted.docx", "formatted_styled.docx"):
                        candidate = result_dir / pattern
                        if candidate.exists():
                            base_docx = str(candidate)
                            break

        if not base_docx or not Path(base_docx).exists():
            raise ValueError("找不到基础 DOCX 文件，无法重新应用模板")

        logger.info("任务 %s: 重新应用模板，基础 DOCX: %s", task_id, base_docx)
        styled_path = self._apply_style(task_id, base_docx, style_config)

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.style_config_preview = style_config
                task_db.result_path = styled_path
                db.commit()
                logger.info("任务 %s: 模板应用完成，结果: %s", task_id, styled_path)

        if record_adjustment:
            self._record_style_adjustment(
                task_id=task_id,
                source=source,
                before_config=before_config,
                after_config=style_config,
                standard=task.standard,
            )
        return styled_path

    def upload_corrected_docx(self, task_id: str, corrected_docx_path: str, get_task_fn) -> dict:
        """处理用户上传的修正后 DOCX 文件"""
        task = get_task_fn(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status != "completed":
            raise ValueError("任务尚未完成，无法上传修正文件")

        before_config = task.style_config_preview
        from src.tools.docx_style_extractor import DocxStyleExtractor

        extractor = DocxStyleExtractor()
        style_config = extractor.extract(corrected_docx_path)
        logger.info("任务 %s: 从修正后 DOCX 提取样式成功", task_id)

        styled_path = self.apply_template_to_task(
            task_id, style_config, get_task_fn, record_adjustment=False, source="upload_corrected"
        )
        self._record_style_adjustment(
            task_id=task_id,
            source="upload_corrected",
            before_config=before_config,
            after_config=style_config,
            standard=task.standard,
        )
        return {"style_config": style_config, "result_path": styled_path}

    def _record_style_adjustment(
        self,
        task_id: str,
        source: str,
        before_config: dict | None,
        after_config: dict | None,
        standard: str | None = None,
    ) -> None:
        """记录样式调整历史"""
        from src.db.crud import StyleAdjustmentHistoryCRUD

        diff_summary = self._compute_style_diff(before_config, after_config)
        with get_db_session() as db:
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
                logger.info(
                    "任务 %s: 样式调整已记录 (source=%s, diff=%s)",
                    task_id,
                    source,
                    diff_summary[:100] if diff_summary else "无",
                )
            except Exception as e:
                logger.warning("记录样式调整失败: %s", e)

    @staticmethod
    def _compute_style_diff(before: dict | None, after: dict | None) -> str:
        """计算两个样式配置的差异摘要"""
        if not before or not after:
            return "新建样式配置" if after else "删除样式配置"

        changes = []
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

        before_pl = before.get("page_layout", {})
        after_pl = after.get("page_layout", {})
        for key in ["margin_top_cm", "margin_bottom_cm", "margin_left_cm", "margin_right_cm"]:
            old_val = before_pl.get(key)
            new_val = after_pl.get(key)
            if old_val != new_val:
                changes.append(f"页面.{key}: {old_val} → {new_val}")

        before_ts = before.get("table_style", {})
        after_ts = after.get("table_style", {})
        for key in ["border_style", "border_width_pt", "header_bold", "table_alignment"]:
            old_val = before_ts.get(key)
            new_val = after_ts.get(key)
            if old_val != new_val:
                changes.append(f"表格.{key}: {old_val} → {new_val}")

        return "; ".join(changes) if changes else "无显著差异"

    def _get_few_shot_examples(self, standard: str | None = None, limit: int = 3) -> str:
        """获取历史样式调整记录作为 few-shot 示例"""
        from src.db.crud import StyleAdjustmentHistoryCRUD

        with get_db_session() as db:
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

    def _default_style_config(self) -> dict:
        """默认样式配置（GB/T 1.1 国标编写规则）

        用于 LLM 降级和 Pandoc 转换路径。
        MinerU DOCX 路径由 GbtDocxFormatter 硬编码处理，不使用此配置。
        """
        return {
            "page_layout": {
                "paper_size": "A4",
                "margin_top_cm": 2.5,
                "margin_bottom_cm": 2.5,
                "margin_left_cm": 2.5,
                "margin_right_cm": 2.1,
                "header_distance_cm": 1.5,
                "footer_distance_cm": 1.75,
            },
            "heading_styles": [
                {
                    "level": 1,
                    "font": {"family": "宋体", "east_asia_family": "黑体", "size_pt": 16, "bold": True},
                    "alignment": "center",
                    "line_spacing": 1.0,
                },
                {
                    "level": 2,
                    "font": {"family": "宋体", "east_asia_family": "宋体", "size_pt": 10.5, "bold": False},
                    "alignment": "justify",
                    "line_spacing": 1.0,
                },
                {
                    "level": 3,
                    "font": {"family": "宋体", "east_asia_family": "宋体", "size_pt": 10.5, "bold": False},
                    "alignment": "justify",
                    "line_spacing": 1.0,
                },
                {
                    "level": 4,
                    "font": {"family": "宋体", "east_asia_family": "宋体", "size_pt": 10.5, "bold": False},
                    "alignment": "justify",
                    "line_spacing": 1.0,
                },
                {
                    "level": 5,
                    "font": {"family": "宋体", "east_asia_family": "宋体", "size_pt": 10.5, "bold": False},
                    "alignment": "justify",
                    "line_spacing": 1.0,
                },
            ],
            "body_style": {
                "font": {"family": "Times New Roman", "east_asia_family": "宋体", "size_pt": 10.5},
                "line_spacing": 1.0,
                "first_line_indent_chars": 2,
                "alignment": "justify",
            },
            "table_style": {
                "border_style": "single",
                "border_width_pt": 0.5,
                "header_font": {
                    "family": "Times New Roman",
                    "east_asia_family": "宋体",
                    "size_pt": 10.5,
                    "bold": False,
                },
                "body_font": {"family": "Times New Roman", "east_asia_family": "宋体", "size_pt": 10.5},
                "header_bold": False,
            },
            "rag_sources": ["GB/T 1.1 标准化工作导则"],
        }

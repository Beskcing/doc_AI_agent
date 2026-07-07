"""LangGraph 文档排版工作流

主工作流编排：
parse_input → analyze_intent → review_content → extract_style → validate_output → render_docx
"""

from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, StateGraph

from src.config import AppConfig
from src.llm_client import LLMClient
from src.models.document_schema import CleaningResult, IntentAnalysis, StyleReport
from src.models.style_config import StyleConfig
from src.rag.hybrid_retriever import HybridRetriever
from src.tools.docx_styler import DocxStyler
from src.tools.html_table_preserver import HTMLTablePreserver
from src.tools.markdown_cleaner import MarkdownCleaner
from src.tools.mineru_parser import MinerUParser
from src.tools.pandoc_converter import PandocConverter
from src.utils.file_utils import ensure_dir, read_text_file, write_text_file
from src.utils.json_validator import safe_parse_llm_json, validate_style_config
from src.utils.logger import get_logger
from src.workflows.conditions import route_after_validation
from src.workflows.state import FormattingState

logger = get_logger(__name__)


def create_formatting_graph(
    llm_client: LLMClient,
    retriever: HybridRetriever | None,
    config: AppConfig,
) -> StateGraph:
    """构建并编译文档排版工作流

    Args:
        llm_client: LLM 客户端
        retriever: RAG 混合检索器（可选）
        config: 应用配置

    Returns:
        编译后的 StateGraph
    """
    # 创建工具实例
    mineru_parser = MinerUParser()
    table_preserver = HTMLTablePreserver()
    markdown_cleaner = MarkdownCleaner(llm_client=llm_client)
    pandoc_converter = PandocConverter(
        pandoc_path=config.pandoc.executable_path,
        extra_args=config.pandoc.extra_args,
    )

    # 加载提示词模板
    prompts_dir = Path(config.paths.prompts_dir)
    system_prompt = _load_prompt(prompts_dir / "system_prompt.md")
    intent_prompt = _load_prompt(prompts_dir / "intent_parsing_prompt.md")
    review_prompt = _load_prompt(prompts_dir / "content_review_prompt.md")
    style_prompt = _load_prompt(prompts_dir / "style_extraction_prompt.md")

    # 构建节点函数（通过闭包捕获工具实例）
    def parse_input_node(state: FormattingState) -> dict:
        return _parse_input(state, mineru_parser, table_preserver)

    def analyze_intent_node(state: FormattingState) -> dict:
        return _analyze_intent(state, llm_client, retriever, system_prompt, intent_prompt)

    def review_content_node(state: FormattingState) -> dict:
        return _review_content(state, markdown_cleaner, system_prompt, review_prompt)

    def extract_style_node(state: FormattingState) -> dict:
        return _extract_style(state, llm_client, retriever, system_prompt, style_prompt)

    def validate_output_node(state: FormattingState) -> dict:
        return _validate_output(state)

    def render_docx_node(state: FormattingState) -> dict:
        return _render_docx(state, pandoc_converter, config)

    def handle_failure_node(state: FormattingState) -> dict:
        return _handle_failure(state)

    # 构建状态图
    graph = StateGraph(FormattingState)

    # 注册节点
    graph.add_node("parse_input", parse_input_node)
    graph.add_node("analyze_intent", analyze_intent_node)
    graph.add_node("review_content", review_content_node)
    graph.add_node("extract_style", extract_style_node)
    graph.add_node("validate_output", validate_output_node)
    graph.add_node("render_docx", render_docx_node)
    graph.add_node("handle_failure", handle_failure_node)

    # 设置入口
    graph.set_entry_point("parse_input")

    # 线性边
    graph.add_edge("parse_input", "analyze_intent")
    graph.add_edge("analyze_intent", "review_content")
    graph.add_edge("review_content", "extract_style")
    graph.add_edge("extract_style", "validate_output")
    graph.add_edge("render_docx", END)
    graph.add_edge("handle_failure", END)

    # 条件路由
    graph.add_conditional_edges(
        "validate_output",
        route_after_validation,
        {
            "pass": "render_docx",
            "retry": "extract_style",
            "fail": "handle_failure",
        },
    )

    return graph.compile()


# ==================== 节点实现 ====================


def _parse_input(
    state: FormattingState,
    mineru_parser: MinerUParser,
    table_preserver: HTMLTablePreserver,
) -> dict:
    """节点 1: 输入解析

    解析 PDF 或已有 Markdown 文件。
    """
    input_path = state["input_path"]
    logger.info("[parse_input] 解析输入: %s", input_path)

    try:
        path = Path(input_path)
        if path.suffix.lower() == ".pdf":
            parsed = mineru_parser.parse_pdf(input_path)
        elif path.suffix.lower() in (".md", ".markdown"):
            parsed = mineru_parser.load_markdown(input_path)
        else:
            raise ValueError(f"不支持的输入格式: {path.suffix}")

        # 保护 HTML 表格
        protected_md, table_map = table_preserver.protect(parsed.raw_markdown)

        return {
            "raw_markdown": parsed.raw_markdown,
            "parsed_document": parsed.model_dump(),
            "table_placeholder_map": table_map,
            "error": None,
        }
    except Exception as e:
        logger.error("[parse_input] 解析失败: %s", e)
        return {"error": f"输入解析失败: {e}"}


def _analyze_intent(
    state: FormattingState,
    llm_client: LLMClient,
    retriever: HybridRetriever | None,
    system_prompt: str,
    intent_prompt: str,
) -> dict:
    """节点 2: 意图解析 + RAG 检索"""
    raw_markdown = state.get("raw_markdown", "")
    target_standard = state.get("target_standard", "")
    logger.info("[analyze_intent] 分析文档意图...")

    try:
        # LLM 意图分析
        prompt = intent_prompt.replace("{markdown_content}", raw_markdown[:3000])
        response = llm_client.invoke(prompt, system_prompt)

        # 解析 LLM 输出
        try:
            json_data = safe_parse_llm_json(response)
            intent = IntentAnalysis.model_validate(json_data)
        except Exception:
            # 降级为默认意图
            intent = IntentAnalysis()

        # 如果有目标标准，覆盖检测结果
        if target_standard:
            intent.detected_standard = target_standard

        # RAG 检索
        rag_results = []
        rag_sources = []
        if retriever:
            query = f"{intent.document_type} {intent.detected_standard or ''} 排版规范"
            results = retriever.retrieve(query)
            for r in results:
                rag_results.append(r.model_dump())
                rag_sources.append(f"{r.source} ({r.section})")

        return {
            "intent_analysis": intent.model_dump(),
            "rag_results": rag_results,
            "rag_sources": rag_sources,
        }
    except Exception as e:
        logger.error("[analyze_intent] 意图分析失败: %s", e)
        return {
            "intent_analysis": IntentAnalysis().model_dump(),
            "rag_results": [],
            "rag_sources": [],
        }


def _review_content(
    state: FormattingState,
    cleaner: MarkdownCleaner,
    system_prompt: str,
    review_prompt: str,
) -> dict:
    """节点 3: 内容审查与清洗"""
    raw_markdown = state.get("raw_markdown", "")
    intent = state.get("intent_analysis", {})
    logger.info("[review_content] 清洗 Markdown...")

    try:
        context = IntentAnalysis.model_validate(intent)
        result = cleaner.clean(raw_markdown, context)
        return {
            "cleaned_markdown": result.cleaned_markdown,
            "cleaning_log": result.changes_log,
        }
    except Exception as e:
        logger.error("[review_content] 清洗失败: %s", e)
        return {
            "cleaned_markdown": raw_markdown,
            "cleaning_log": [f"清洗失败: {e}"],
        }


def _extract_style(
    state: FormattingState,
    llm_client: LLMClient,
    retriever: HybridRetriever | None,
    system_prompt: str,
    style_prompt: str,
) -> dict:
    """节点 4: 样式参数提取"""
    intent = state.get("intent_analysis", {})
    rag_results = state.get("rag_results", [])
    retry_count = state.get("retry_count", 0)
    logger.info("[extract_style] 提取样式配置 (尝试 %d)...", retry_count + 1)

    try:
        # 构建 RAG 上下文
        rag_context = "\n\n".join(
            r.get("content", "") for r in rag_results[:5]
        ) or "无 RAG 检索结果，请使用国标 GB/T 9704 默认值。"

        # 特殊元素描述
        special = []
        if intent.get("has_complex_tables"):
            special.append("包含复杂表格")
        if intent.get("has_formulas"):
            special.append("包含数学公式")
        if intent.get("has_chemical_structures"):
            special.append("包含化学结构式")

        prompt = style_prompt.replace("{document_type}", intent.get("document_type", "通用文档"))
        prompt = prompt.replace("{detected_standard}", intent.get("detected_standard", "GB/T 9704") or "GB/T 9704")
        prompt = prompt.replace("{special_elements}", "、".join(special) if special else "无特殊元素")
        prompt = prompt.replace("{rag_context}", rag_context)
        # 注入 few-shot 示例
        try:
            from src.api.services.service_deps import ServiceDeps
            deps = ServiceDeps(config)
            from src.api.services.pipeline_service import PipelineService
            pipeline = PipelineService(deps=deps, update_status=lambda *a, **kw: None)
            few_shot = pipeline._get_few_shot_examples(
                standard=intent.get("detected_standard"), limit=3
            )
            prompt = prompt.replace("{few_shot_examples}", few_shot)
        except Exception:
            prompt = prompt.replace("{few_shot_examples}", "暂无历史调整记录。")

        response = llm_client.invoke(prompt, system_prompt)

        # 解析 JSON
        json_data = safe_parse_llm_json(response)
        return {
            "style_config": json_data,
            "retry_count": retry_count,
        }
    except Exception as e:
        logger.error("[extract_style] 样式提取失败: %s", e)
        return {
            "style_config": {},
            "retry_count": retry_count + 1,
            "validation_passed": False,
        }


def _validate_output(state: FormattingState) -> dict:
    """节点 5: JSON Schema 校验"""
    style_config = state.get("style_config", {})
    retry_count = state.get("retry_count", 0)
    logger.info("[validate_output] 校验样式配置...")

    if not style_config:
        return {
            "validation_passed": False,
            "retry_count": retry_count + 1,
        }

    passed, errors, _ = validate_style_config(style_config)
    if passed:
        logger.info("[validate_output] 校验通过")
        return {"validation_passed": True}

    logger.warning("[validate_output] 校验失败: %s", errors[:3])
    return {
        "validation_passed": False,
        "retry_count": retry_count + 1,
    }


def _render_docx(
    state: FormattingState,
    pandoc_converter: PandocConverter,
    config: AppConfig,
) -> dict:
    """节点 6: 文档渲染（优先 MinerU DOCX，回退 Pandoc + python-docx）"""
    cleaned_md = state.get("cleaned_markdown", "")
    style_config = state.get("style_config", {})
    table_map = state.get("table_placeholder_map", {})
    parsed_document = state.get("parsed_document", {})
    logger.info("[render_docx] 渲染 Word 文档...")

    output_dir = ensure_dir(Path(config.paths.output_dir))
    final_path = output_dir / "output.docx"

    # 优先使用 MinerU 原始 DOCX 作为基础（保留原始排版）
    mineru_docx_path = parsed_document.get("metadata", {}).get("mineru_docx_path")
    if mineru_docx_path and Path(mineru_docx_path).exists():
        docx_base_path = mineru_docx_path
        logger.info("[render_docx] 使用 MinerU 原始 DOCX 作为样式基础: %s", docx_base_path)
    else:
        # 回退：Pandoc MD → DOCX
        intermediate_path = output_dir / "intermediate.docx"
        table_preserver = HTMLTablePreserver()
        final_md = table_preserver.restore(cleaned_md, table_map)
        report = pandoc_converter.markdown_to_docx(final_md, str(intermediate_path))
        if not report.success:
            return {
                "error": f"Pandoc 转换失败: {report.errors}",
                "final_output_path": "",
            }
        docx_base_path = str(intermediate_path)

    try:
        # python-docx 样式渲染
        sc = StyleConfig.model_validate(style_config)
        styler = DocxStyler(sc)
        style_report = styler.apply_gb_style(docx_base_path, str(final_path))

        return {
            "intermediate_docx_path": str(intermediate_path),
            "final_output_path": style_report.output_path,
            "style_report": style_report.model_dump(),
            "error": None if style_report.success else f"样式应用问题: {style_report.warnings}",
        }
    except Exception as e:
        logger.error("[render_docx] 渲染失败: %s", e)
        return {"error": f"文档渲染失败: {e}", "final_output_path": ""}


def _handle_failure(state: FormattingState) -> dict:
    """节点 7: 失败处理"""
    retry_count = state.get("retry_count", 0)
    logger.error("[handle_failure] 工作流失败（重试 %d 次后）", retry_count)
    return {
        "error": f"样式提取校验失败，已重试 {retry_count} 次。请检查输入文档或 RAG 知识库。",
        "final_output_path": "",
    }


# ==================== 辅助函数 ====================


def _load_prompt(prompt_path: Path) -> str:
    """加载提示词模板，文件不存在时返回空字符串"""
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    logger.warning("提示词文件不存在: %s", prompt_path)
    return ""

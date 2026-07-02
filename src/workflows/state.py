"""工作流状态定义

定义 LangGraph 工作流中各阶段的状态数据结构。
"""

from __future__ import annotations

from typing import Any, TypedDict


class FormattingState(TypedDict, total=False):
    """文档排版工作流状态

    贯穿整个工作流的数据容器，各节点读取和更新对应的字段。
    """

    # ========== 输入 ==========
    input_path: str  # 输入 PDF/Markdown 路径
    target_standard: str  # 目标标准，如 "GB/T 9704"
    user_requirements: str  # 用户自然语言描述的排版要求

    # ========== 阶段 1: 输入解析 ==========
    raw_markdown: str  # MinerU 解析的原始 Markdown
    parsed_document: dict[str, Any]  # 结构化解析结果
    table_placeholder_map: dict[str, str]  # HTML 表格占位符映射

    # ========== 阶段 2: 意图解析 + RAG ==========
    intent_analysis: dict[str, Any]  # 意图分析结果
    rag_results: list[dict[str, Any]]  # RAG 检索结果
    rag_sources: list[str]  # RAG 来源追溯

    # ========== 阶段 3: 内容审查清洗 ==========
    cleaned_markdown: str  # 清洗后的 Markdown
    cleaning_log: list[str]  # 清洗操作日志

    # ========== 阶段 4: 样式提取 ==========
    style_config: dict[str, Any]  # JSON 排版配置
    validation_passed: bool  # JSON Schema 校验结果

    # ========== 阶段 5: 渲染 ==========
    intermediate_docx_path: str  # Pandoc 生成的中间 DOCX
    final_output_path: str  # 最终输出的 Word 文档路径
    style_report: dict[str, Any]  # 样式应用报告

    # ========== 控制流 ==========
    error: str | None  # 错误信息
    retry_count: int  # 重试计数（用于 JSON 校验失败重试）

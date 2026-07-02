"""文档排版智能体 CLI 入口

用法:
    python -m scripts.run_pipeline --input doc.pdf --output output.docx
    python -m scripts.run_pipeline --input doc.md --standard "GB/T 9704" --provider glm
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AppConfig
from src.llm_client import LLMClient
from src.rag.knowledge_base_config import KnowledgeBaseManager
from src.utils.file_utils import ensure_dir, write_text_file
from src.utils.logger import get_logger, setup_logging
from src.workflows.doc_formatting_graph import create_formatting_graph

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="企业级国标文档排版智能体",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python -m scripts.run_pipeline --input doc.pdf --output output.docx
  python -m scripts.run_pipeline --input doc.md --standard "GB/T 9704" --provider glm
  python -m scripts.run_pipeline --input doc.md --output-json style.json --skip-render
        """,
    )

    parser.add_argument("--input", "-i", required=True, help="输入文件路径（PDF 或 Markdown）")
    parser.add_argument("--output", "-o", default="data/output/output.docx", help="输出 Word 文件路径")
    parser.add_argument("--standard", "-s", default="", help="目标标准编号，如 GB/T 9704")
    parser.add_argument("--provider", "-p", default=None, help="LLM Provider (qwen / glm)")
    parser.add_argument("--config", "-c", default=None, help="配置文件路径")
    parser.add_argument("--output-json", default=None, help="额外输出 style_config JSON 文件")
    parser.add_argument("--output-markdown", default=None, help="额外输出清洗后 Markdown 文件")
    parser.add_argument("--skip-render", action="store_true", help="跳过渲染阶段（仅输出 JSON 和 Markdown）")
    parser.add_argument("--no-rag", action="store_true", help="禁用 RAG 知识库")
    parser.add_argument("--verbose", "-v", action="store_true", help="详细日志输出")

    args = parser.parse_args()

    setup_logging()

    logger.info("=" * 60)
    logger.info("  企业级国标文档排版智能体 v0.1.0")
    logger.info("=" * 60)

    start_time = time.time()

    # 加载配置
    config = AppConfig.load(args.config)
    if args.provider:
        config.llm.default_provider = args.provider

    # 校验输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s", input_path)
        sys.exit(1)

    logger.info("输入文件: %s", input_path)
    logger.info("目标标准: %s", args.standard or "(自动检测)")
    logger.info("LLM Provider: %s", config.llm.default_provider)

    # 初始化 LLM 客户端
    llm_client = LLMClient(config.llm, provider=args.provider)

    # 初始化 RAG
    retriever = None
    if not args.no_rag:
        try:
            kb_manager = KnowledgeBaseManager(config.rag)
            kb_manager.initialize()
            retriever = kb_manager.get_retriever()
            logger.info("RAG 知识库已加载")
        except Exception as e:
            logger.warning("RAG 知识库初始化失败: %s，将不使用 RAG", e)

    # 构建并运行工作流
    graph = create_formatting_graph(llm_client, retriever, config)

    initial_state = {
        "input_path": str(input_path),
        "target_standard": args.standard,
        "user_requirements": "",
        "retry_count": 0,
        "error": None,
    }

    logger.info("-" * 60)
    logger.info("开始执行工作流...")
    result = graph.invoke(initial_state)

    # 输出结果
    elapsed = time.time() - start_time
    logger.info("-" * 60)

    if result.get("error"):
        logger.error("工作流错误: %s", result["error"])
    else:
        logger.info("工作流执行成功！")

    if result.get("final_output_path"):
        logger.info("输出文件: %s", result["final_output_path"])

    if result.get("cleaning_log"):
        logger.info("清洗日志:")
        for log_entry in result["cleaning_log"]:
            logger.info("  - %s", log_entry)

    if result.get("style_report"):
        report = result["style_report"]
        logger.info("样式报告: %d 段落, %d 标题, %d 表格", 
                     report.get("paragraphs_styled", 0),
                     report.get("headings_styled", 0),
                     report.get("tables_styled", 0))

    # 额外输出
    if args.output_json and result.get("style_config"):
        json_path = write_text_file(
            args.output_json,
            json.dumps(result["style_config"], ensure_ascii=False, indent=2),
        )
        logger.info("样式配置已保存: %s", json_path)

    if args.output_markdown and result.get("cleaned_markdown"):
        md_path = write_text_file(args.output_markdown, result["cleaned_markdown"])
        logger.info("清洗后 Markdown 已保存: %s", md_path)

    logger.info("=" * 60)
    logger.info("耗时: %.1f 秒", elapsed)
    logger.info("=" * 60)

    # 退出码
    sys.exit(1 if result.get("error") else 0)


if __name__ == "__main__":
    main()

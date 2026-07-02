"""初始化 RAG 知识库脚本

用法:
    python -m scripts.init_knowledge_base [--force-rebuild]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import AppConfig
from src.rag.knowledge_base_config import KnowledgeBaseManager
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="初始化 RAG 排版规范知识库")
    parser.add_argument("--force-rebuild", action="store_true", help="强制重建知识库")
    parser.add_argument("--config", type=str, default=None, help="配置文件路径")
    args = parser.parse_args()

    setup_logging()

    # 加载配置
    config = AppConfig.load(args.config)

    logger.info("=" * 50)
    logger.info("知识库初始化")
    logger.info("=" * 50)
    logger.info("Chroma 路径: %s", config.rag.chroma_path)
    logger.info("Collection: %s", config.rag.collection_name)
    logger.info("Chunk Size: %d, Overlap: %.0f%%", config.rag.chunk_size, config.rag.chunk_overlap_ratio * 100)
    logger.info("Embedding: %s / %s", config.rag.embedding_provider, config.rag.embedding_model)
    logger.info("规范文档目录: %s", config.rag.raw_docs_dir)

    # 初始化知识库
    manager = KnowledgeBaseManager(config.rag)
    manager.initialize(force_rebuild=args.force_rebuild)

    # 测试检索
    retriever = manager.get_retriever()
    test_queries = [
        "仿宋_GB2312 字体使用场景",
        "国标表格边框线宽规范",
        "公文标题格式要求",
    ]

    logger.info("-" * 50)
    logger.info("检索测试:")
    for query in test_queries:
        results = retriever.retrieve(query)
        logger.info("查询: '%s' → %d 个结果", query, len(results))
        for r in results[:2]:
            logger.info("  [%.3f] %s (%s)", r.score, r.source, r.retrieval_method)

    logger.info("=" * 50)
    logger.info("知识库初始化完成！")


if __name__ == "__main__":
    main()

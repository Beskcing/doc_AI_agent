"""Chroma 知识库管理

管理知识库的初始化、构建、增量更新和检索器获取。
"""

from __future__ import annotations

from pathlib import Path

from langchain_chroma import Chroma

from src.config import RAGConfig
from src.rag.chunking_strategy import StandardsChunker
from src.rag.document_loader import StandardsDocumentLoader
from src.rag.embedding_factory import EmbeddingFactory
from src.rag.hybrid_retriever import HybridRetriever
from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeBaseManager:
    """Chroma 知识库管理器"""

    def __init__(self, config: RAGConfig):
        """初始化管理器

        Args:
            config: RAG 配置
        """
        self.config = config
        self._vectorstore: Chroma | None = None
        self._chunked_docs: list = []
        self._retriever: HybridRetriever | None = None

    def initialize(self, force_rebuild: bool = False) -> Chroma:
        """初始化知识库

        流程:
        1. 检查是否存在持久化数据
        2. 若不存在或 force_rebuild，执行完整构建
        3. 加载文档 -> 切片 -> 向量化 -> 存入 Chroma

        Args:
            force_rebuild: 是否强制重建知识库

        Returns:
            Chroma 向量存储实例
        """
        chroma_path = Path(self.config.chroma_path)
        collection_name = self.config.collection_name

        # 检查是否可以加载已有数据
        if not force_rebuild and chroma_path.exists() and any(chroma_path.iterdir()):
            logger.info("加载已有知识库: %s", chroma_path)
            try:
                embedding = EmbeddingFactory.create(
                    provider=self.config.embedding_provider,
                    model_name=self.config.embedding_model,
                )
                self._vectorstore = Chroma(
                    collection_name=collection_name,
                    embedding_function=embedding,
                    persist_directory=str(chroma_path),
                )
                # 需要重新加载文档以构建 BM25 索引
                self._chunked_docs = self._load_and_chunk_documents()
                logger.info("知识库加载完成，%d 个文档片段", len(self._chunked_docs))
                return self._vectorstore
            except Exception as e:
                logger.warning("加载已有知识库失败: %s，将重新构建", e)

        # 完整构建
        logger.info("开始构建知识库...")
        ensure_dir(chroma_path)

        # 1. 加载文档
        self._chunked_docs = self._load_and_chunk_documents()
        if not self._chunked_docs:
            logger.warning("知识库为空（无规范文档），创建空向量库")
            embedding = EmbeddingFactory.create(
                provider=self.config.embedding_provider,
                model_name=self.config.embedding_model,
            )
            self._vectorstore = Chroma(
                collection_name=collection_name,
                embedding_function=embedding,
                persist_directory=str(chroma_path),
            )
            return self._vectorstore

        # 2. 向量化并存储
        embedding = EmbeddingFactory.create(
            provider=self.config.embedding_provider,
            model_name=self.config.embedding_model,
        )

        logger.info("向量化 %d 个文档片段...", len(self._chunked_docs))
        self._vectorstore = Chroma.from_documents(
            documents=self._chunked_docs,
            embedding=embedding,
            collection_name=collection_name,
            persist_directory=str(chroma_path),
        )

        logger.info("知识库构建完成: %s", chroma_path)
        return self._vectorstore

    def get_retriever(self) -> HybridRetriever:
        """获取混合检索器实例

        Returns:
            HybridRetriever 实例

        Raises:
            RuntimeError: 知识库未初始化
        """
        if self._vectorstore is None:
            raise RuntimeError("知识库未初始化，请先调用 initialize()")

        if self._retriever is None:
            self._retriever = HybridRetriever(
                vectorstore=self._vectorstore,
                chunked_docs=self._chunked_docs,
                k=self.config.top_k,
                bm25_weight=self.config.bm25_weight,
                vector_weight=self.config.vector_weight,
            )

        return self._retriever

    def add_documents(self, doc_paths: list[str]) -> int:
        """增量添加新规范文档

        Args:
            doc_paths: 新文档路径列表

        Returns:
            新增的 chunk 数量
        """
        if self._vectorstore is None:
            raise RuntimeError("知识库未初始化，请先调用 initialize()")

        loader = StandardsDocumentLoader("")
        new_docs = []
        for path in doc_paths:
            try:
                docs = loader._load_single(Path(path))
                new_docs.extend(docs)
            except Exception as e:
                logger.error("加载文档失败 %s: %s", path, e)

        if not new_docs:
            return 0

        # 切片
        chunker = StandardsChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap_ratio=self.config.chunk_overlap_ratio,
        )
        new_chunks = chunker.split_documents(new_docs)

        # 添加到向量存储
        self._vectorstore.add_documents(new_chunks)
        self._chunked_docs.extend(new_chunks)

        # 重建检索器
        self._retriever = None

        logger.info("增量添加 %d 个 chunk", len(new_chunks))
        return len(new_chunks)

    def _load_and_chunk_documents(self) -> list:
        """加载并切片所有规范文档

        Returns:
            切片后的 Document 列表
        """
        loader = StandardsDocumentLoader(self.config.raw_docs_dir)
        documents = loader.load_all()

        if not documents:
            return []

        chunker = StandardsChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap_ratio=self.config.chunk_overlap_ratio,
        )
        return chunker.split_documents(documents)

    @property
    def chunked_docs(self) -> list:
        """获取切片后的文档列表"""
        return self._chunked_docs

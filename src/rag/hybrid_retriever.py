"""BM25 + 向量混合检索器

实现混合检索策略：
- BM25 关键词检索（精确匹配专有名词）
- Chroma 向量检索（语义相似性）
- RRF (Reciprocal Rank Fusion) 分数融合
"""

from __future__ import annotations

import math

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi

from src.models.document_schema import RetrievalResult
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 将专有名词加入 jieba 自定义词典
_CUSTOM_TERMS = [
    "仿宋_GB2312", "楷体_GB2312", "方正小标宋简体",
    "OMML", "OOXML", "三线表", "版心尺寸",
    "首行缩进", "段前间距", "段后间距", "行距倍数",
    "GB/T", "页边距", "页眉", "页脚",
]
for term in _CUSTOM_TERMS:
    jieba.add_word(term)


class HybridRetriever:
    """BM25 + 向量混合检索器"""

    def __init__(
        self,
        vectorstore,
        chunked_docs: list[Document],
        k: int = 5,
        bm25_weight: float = 0.3,
        vector_weight: float = 0.7,
    ):
        """初始化混合检索器

        Args:
            vectorstore: Chroma 向量存储
            chunked_docs: 切片后的文档列表（用于构建 BM25 索引）
            k: 返回 Top-K 结果
            bm25_weight: BM25 权重
            vector_weight: 向量检索权重
        """
        self.vectorstore = vectorstore
        self.k = k
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight

        # 构建 BM25 索引
        self._docs = chunked_docs
        self._bm25 = self._build_bm25_index(chunked_docs)

        # 新增：构建内容哈希索引（O(1) 查找）
        self._content_index: dict[str, int] = {}
        self._metadata_index: dict[tuple, int] = {}
        for idx, doc in enumerate(chunked_docs):
            self._content_index[doc.page_content] = idx
            meta_key = (
                doc.metadata.get("source"),
                doc.metadata.get("chunk_index"),
            )
            if meta_key[1] is not None:
                self._metadata_index[meta_key] = idx

        logger.info(
            "混合检索器初始化: %d 个文档, BM25 权重=%.2f, 向量权重=%.2f",
            len(chunked_docs), bm25_weight, vector_weight,
        )

    @property
    def documents(self) -> list[Document]:
        """返回已索引的文档列表"""
        return self._docs

    def retrieve(self, query: str) -> list[RetrievalResult]:
        """执行混合检索

        流程:
        1. BM25 关键词检索
        2. 向量语义检索
        3. RRF 分数融合
        4. 返回 Top-K 结果

        Args:
            query: 查询文本

        Returns:
            RetrievalResult 列表（按相关性降序排列）
        """
        if not query.strip():
            return []

        # BM25 检索
        bm25_results = self._bm25_search(query)

        # 向量检索
        vector_results = self._vector_search(query)

        # RRF 融合
        fused = self._rrf_fusion(bm25_results, vector_results)

        # 返回 Top-K
        top_results = fused[: self.k]

        logger.info(
            "检索完成: query='%s', BM25=%d, 向量=%d, 融合=%d",
            query[:30], len(bm25_results), len(vector_results), len(top_results),
        )

        return top_results

    def _build_bm25_index(self, documents: list[Document]) -> BM25Okapi | None:
        """构建 BM25 索引

        Args:
            documents: 文档列表

        Returns:
            BM25Okapi 实例
        """
        if not documents:
            return None

        tokenized = []
        for doc in documents:
            tokens = self._tokenize(doc.page_content)
            tokenized.append(tokens)

        try:
            return BM25Okapi(tokenized)
        except Exception as e:
            logger.error("BM25 索引构建失败: %s", e)
            return None

    def _bm25_search(self, query: str) -> list[tuple[int, float]]:
        """BM25 关键词检索

        Args:
            query: 查询文本

        Returns:
            [(文档索引, 得分), ...] 按得分降序
        """
        if self._bm25 is None:
            return []

        tokens = self._tokenize(query)
        scores = self._bm25.get_scores(tokens)

        # 排序并返回 Top-20（给 RRF 更多候选）
        indexed_scores = list(enumerate(scores))
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:20]

    def _vector_search(self, query: str) -> list[tuple[int, float]]:
        """向量语义检索

        Args:
            query: 查询文本

        Returns:
            [(文档索引, 得分), ...] 按得分降序
        """
        try:
            # Chroma similarity_search_with_relevance_scores
            results = self.vectorstore.similarity_search_with_relevance_scores(query, k=20)

            indexed_results = []
            for doc, score in results:
                # 通过元数据查找文档索引
                doc_idx = self._find_doc_index(doc)
                if doc_idx is not None:
                    indexed_results.append((doc_idx, score))

            indexed_results.sort(key=lambda x: x[1], reverse=True)
            return indexed_results

        except Exception as e:
            logger.warning("向量检索失败: %s", e)
            return []

    def _rrf_fusion(
        self,
        bm25_results: list[tuple[int, float]],
        vector_results: list[tuple[int, float]],
        k: int = 60,
    ) -> list[RetrievalResult]:
        """RRF (Reciprocal Rank Fusion) 分数融合

        score(d) = Σ weight_i / (k + rank_i(d))

        Args:
            bm25_results: BM25 检索结果
            vector_results: 向量检索结果
            k: RRF 常数（默认 60）

        Returns:
            融合后的 RetrievalResult 列表
        """
        scores: dict[int, float] = {}
        methods: dict[int, str] = {}

        # BM25 排名
        for rank, (doc_idx, _) in enumerate(bm25_results):
            rrf_score = self.bm25_weight / (k + rank + 1)
            scores[doc_idx] = scores.get(doc_idx, 0) + rrf_score
            methods[doc_idx] = "bm25"

        # 向量排名
        for rank, (doc_idx, _) in enumerate(vector_results):
            rrf_score = self.vector_weight / (k + rank + 1)
            scores[doc_idx] = scores.get(doc_idx, 0) + rrf_score
            if doc_idx in methods:
                methods[doc_idx] = "hybrid"
            else:
                methods[doc_idx] = "vector"

        # 按融合分数排序
        sorted_indices = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for doc_idx, score in sorted_indices:
            if doc_idx < len(self._docs):
                doc = self._docs[doc_idx]
                results.append(
                    RetrievalResult(
                        content=doc.page_content,
                        source=doc.metadata.get("source", "unknown"),
                        section=doc.metadata.get("section_title", ""),
                        score=score,
                        retrieval_method=methods.get(doc_idx, "unknown"),
                    )
                )

        return results

    def _tokenize(self, text: str) -> list[str]:
        """中文分词

        使用 jieba 分词，专有名词已加入自定义词典。

        Args:
            text: 文本

        Returns:
            分词结果列表
        """
        return [w for w in jieba.cut(text) if w.strip()]

    def _find_doc_index(self, doc: Document) -> int | None:
        """通过文档内容或元数据查找索引（O(1) 哈希查找）

        Args:
            doc: Document 对象

        Returns:
            文档索引或 None
        """
        # 1. 内容哈希查找
        idx = self._content_index.get(doc.page_content)
        if idx is not None:
            return idx
        # 2. 元数据查找
        meta_key = (
            doc.metadata.get("source"),
            doc.metadata.get("chunk_index"),
        )
        if meta_key[1] is not None:
            return self._metadata_index.get(meta_key)
        # 3. 回退：遍历查找（用于无 chunk_index 的文档）
        for idx, d in enumerate(self._docs):
            if d.page_content == doc.page_content:
                return idx
        return None

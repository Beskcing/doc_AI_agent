"""Embedding 模型工厂

提供统一的 Embedding 模型创建接口，支持多种后端。
"""

from __future__ import annotations

import os

from langchain_core.embeddings import Embeddings

from src.utils.logger import get_logger

logger = get_logger(__name__)


class DashScopeEmbeddings(Embeddings):
    """阿里 DashScope Embedding 模型封装"""

    def __init__(self, model: str = "text-embedding-v3", api_key: str | None = None):
        self.model = model
        self.api_key = api_key or os.getenv("DASHSCOPE_API_KEY", "")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化"""
        try:
            import dashscope
            from dashscope import TextEmbedding

            if self.api_key:
                dashscope.api_key = self.api_key

            # DashScope 限制每次最多 25 条
            all_embeddings = []
            batch_size = 25

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]
                response = TextEmbedding.call(
                    model=self.model,
                    input=batch,
                )
                if response.status_code == 200:
                    batch_embeddings = [item["embedding"] for item in response.output["embeddings"]]
                    all_embeddings.extend(batch_embeddings)
                else:
                    raise RuntimeError(f"DashScope Embedding 调用失败: {response.code} - {response.message}")

            return all_embeddings

        except ImportError:
            logger.error("dashscope 未安装，请执行: pip install dashscope")
            raise

    def embed_query(self, text: str) -> list[float]:
        """单条文本向量化"""
        return self.embed_documents([text])[0]


class EmbeddingFactory:
    """Embedding 模型工厂"""

    @staticmethod
    def create(
        provider: str = "dashscope",
        model_name: str = "text-embedding-v3",
        api_key: str | None = None,
    ) -> Embeddings:
        """创建 LangChain 兼容的 Embedding 实例

        Args:
            provider: Embedding 提供商 (dashscope / openai / local)
            model_name: 模型名称
            api_key: API Key（为 None 时从环境变量读取）

        Returns:
            Embeddings 实例
        """
        if provider == "dashscope":
            logger.info("创建 DashScope Embedding: %s", model_name)
            return DashScopeEmbeddings(model=model_name, api_key=api_key)

        elif provider == "openai":
            try:
                from langchain_openai import OpenAIEmbeddings

                logger.info("创建 OpenAI Embedding: %s", model_name)
                return OpenAIEmbeddings(
                    model=model_name,
                    openai_api_key=api_key or os.getenv("OPENAI_API_KEY"),
                )
            except ImportError:
                raise ImportError("langchain-openai 未安装，请执行: pip install langchain-openai") from None

        else:
            raise ValueError(f"不支持的 Embedding 提供商: {provider}")

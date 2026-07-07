"""服务共享依赖容器

封装 LLM 客户端、RAG 检索器、提示词模板等懒加载依赖，
供 PipelineService / PreviewService / ContentEditService 共享使用。
"""

from __future__ import annotations

from pathlib import Path

from src.config import AppConfig
from src.llm_client import LLMClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ServiceDeps:
    """服务共享依赖容器（懒加载）

    封装 LLM/RAG/Prompts 的懒加载逻辑，避免各服务类重复实现。
    """

    def __init__(self, config: AppConfig, enable_rag: bool = True):
        self.config = config
        self._llm_client: LLMClient | None = None
        self._retriever = None
        self._rag_enabled: bool = enable_rag
        self._prompts_loaded: bool = False
        self._system_prompt: str = ""
        self._intent_prompt: str = ""
        self._style_prompt: str = ""

    def get_llm_client(self) -> LLMClient | None:
        """懒加载 LLM 客户端，初始化失败时返回 None"""
        if self._llm_client is None:
            try:
                self._llm_client = LLMClient(self.config.llm)
                logger.info("LLM 客户端初始化成功: provider=%s", self.config.llm.default_provider)
            except Exception as e:
                logger.warning("LLM 客户端初始化失败，将使用降级模式: %s", e)
        return self._llm_client

    def get_retriever(self):
        """懒加载 RAG 混合检索器，初始化失败时返回 None"""
        if not self._rag_enabled:
            return None
        if self._retriever is None:
            try:
                from src.rag.knowledge_base_config import KnowledgeBaseManager

                kb_manager = KnowledgeBaseManager(self.config.rag)
                kb_manager.initialize()
                self._retriever = kb_manager.get_retriever()
                logger.info("RAG 知识库加载成功")
            except Exception as e:
                logger.warning("RAG 知识库初始化失败，将不使用 RAG: %s", e)
        return self._retriever

    def ensure_prompts(self) -> None:
        """懒加载提示词模板"""
        if self._prompts_loaded:
            return
        prompts_dir = Path(self.config.paths.prompts_dir)
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

    @property
    def system_prompt(self) -> str:
        return self._system_prompt

    @property
    def intent_prompt(self) -> str:
        return self._intent_prompt

    @property
    def style_prompt(self) -> str:
        return self._style_prompt

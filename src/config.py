"""全局配置加载器

读取 configs/ 目录下的 YAML 配置文件，提供类型安全的配置访问。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# 加载 .env 文件中的环境变量
load_dotenv()

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class LLMProviderConfig(BaseModel):
    """单个 LLM Provider 的配置"""

    model: str = "qwen-plus"
    base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    temperature: float = 0.1
    max_tokens: int = 4096


class LLMConfig(BaseModel):
    """LLM 配置（支持多 Provider 切换）"""

    default_provider: Literal["qwen", "glm"] = "qwen"
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict)
    api_keys: dict[str, str] = Field(default_factory=dict)

    def get_provider_config(self, provider: str | None = None) -> LLMProviderConfig:
        """获取指定 provider 的配置，默认使用 default_provider"""
        provider = provider or self.default_provider
        if provider not in self.providers:
            raise ValueError(f"未知的 LLM Provider: {provider}，可用: {list(self.providers.keys())}")
        return self.providers[provider]

    def get_api_key(self, provider: str | None = None) -> str:
        """获取指定 provider 的 API Key（优先从环境变量读取）"""
        provider = provider or self.default_provider
        env_map = {
            "qwen": "DASHSCOPE_API_KEY",
            "glm": "ZHIPUAI_API_KEY",
        }
        env_var = env_map.get(provider, "")
        key = os.getenv(env_var, "")
        if key:
            return key
        return self.api_keys.get(provider, "")


class RAGConfig(BaseModel):
    """RAG 知识库配置"""

    chroma_path: str = "knowledge_data/chroma_db"
    collection_name: str = "formatting_standards"
    raw_docs_dir: str = "knowledge_data/raw_docs"
    chunk_size: int = 700
    chunk_overlap_ratio: float = 0.15
    embedding_provider: str = "dashscope"
    embedding_model: str = "text-embedding-v3"
    top_k: int = 5
    bm25_weight: float = 0.3
    vector_weight: float = 0.7


class MinerUConfig(BaseModel):
    """MinerU 解析配置"""

    mode: Literal["online", "local"] = "online"
    api_token: str = ""  # 优先从环境变量 MINERU_API_TOKEN 读取
    base_url: str = "https://mineru.net"
    model_version: str = "vlm"  # pipeline / vlm / MinerU-HTML
    is_ocr: bool = False
    enable_formula: bool = True
    enable_table: bool = True
    language: str = "ch"
    poll_interval: int = 5  # 轮询间隔（秒）
    poll_timeout: int = 600  # 轮询总超时（秒）
    request_timeout: int = 120  # HTTP 请求超时（秒）

    def get_token(self) -> str:
        """获取 API Token（优先从环境变量）"""
        return os.getenv("MINERU_API_TOKEN", "") or self.api_token


class PathsConfig(BaseModel):
    """路径配置"""

    input_dir: str = "data/input"
    output_dir: str = "data/output"
    uploads_dir: str = "data/uploads"
    knowledge_data_dir: str = "knowledge_data"
    raw_docs_dir: str = "knowledge_data/raw_docs"
    prompts_dir: str = "prompts"


class PandocConfig(BaseModel):
    """Pandoc 配置"""

    executable_path: str = "pandoc"
    extra_args: list[str] = Field(default_factory=lambda: ["--from=markdown+raw_html", "--to=docx"])


class AppConfig(BaseModel):
    """应用全局配置"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    rag: RAGConfig = Field(default_factory=RAGConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    pandoc: PandocConfig = Field(default_factory=PandocConfig)
    mineru: MinerUConfig = Field(default_factory=MinerUConfig)

    @classmethod
    def load(cls, config_path: str | Path | None = None) -> AppConfig:
        """从 YAML 文件加载配置

        Args:
            config_path: 配置文件路径，默认为 configs/settings.yaml

        Returns:
            AppConfig 实例
        """
        if config_path is None:
            config_path = PROJECT_ROOT / "configs" / "settings.yaml"
        else:
            config_path = Path(config_path)

        if not config_path.exists():
            # 使用默认配置
            instance = cls._create_default()
            instance._validate_required()
            return instance

        with open(config_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        instance = cls._from_raw(raw)
        instance._validate_required()
        return instance

    @classmethod
    def _create_default(cls) -> AppConfig:
        """创建默认配置"""
        return cls(
            llm=LLMConfig(
                default_provider="qwen",
                providers={
                    "qwen": LLMProviderConfig(
                        model="qwen-plus",
                        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                        temperature=0.1,
                    ),
                    "glm": LLMProviderConfig(
                        model="glm-4",
                        base_url="https://open.bigmodel.cn/api/paas/v4",
                        temperature=0.1,
                    ),
                },
            ),
        )

    @classmethod
    def _from_raw(cls, raw: dict) -> AppConfig:
        """从原始字典构建 AppConfig"""
        llm_raw = raw.get("llm", {})
        providers = {}
        for name, prov_cfg in llm_raw.get("providers", {}).items():
            providers[name] = LLMProviderConfig(**prov_cfg)

        llm = LLMConfig(
            default_provider=llm_raw.get("default_provider", "qwen"),
            providers=providers,
        )

        # 将 paths.raw_docs_dir 传入 rag 配置，供 KnowledgeBaseManager 使用
        rag_raw = raw.get("rag", {})
        paths_raw = raw.get("paths", {})
        if "raw_docs_dir" not in rag_raw and "raw_docs_dir" in paths_raw:
            rag_raw["raw_docs_dir"] = paths_raw["raw_docs_dir"]

        return cls(
            llm=llm,
            rag=RAGConfig(**rag_raw),
            paths=PathsConfig(**paths_raw),
            pandoc=PandocConfig(**raw.get("pandoc", {})),
            mineru=MinerUConfig(**raw.get("mineru", {})),
        )

    def _validate_required(self) -> None:
        """校验必要配置是否完整"""
        errors = []
        if not self.llm.default_provider:
            errors.append("llm.default_provider 未设置")
        if not self.llm.providers:
            errors.append("llm.providers 未配置任何 Provider")
        if not self.paths.output_dir:
            errors.append("paths.output_dir 未设置")
        if errors:
            raise ValueError(f"配置校验失败: {'; '.join(errors)}")

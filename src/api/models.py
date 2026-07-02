"""API 数据模型"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DocumentType(str, Enum):
    """文档类型"""

    PDF = "pdf"
    MARKDOWN = "markdown"
    TXT = "txt"


class StandardOption(str, Enum):
    """排版规范选项"""

    GBT_9704 = "GB/T 9704"
    GBT_7713 = "GB/T 7713"
    CUSTOM = "custom"


# ────────── 通用 ──────────
class ResponseModel(BaseModel):
    """通用响应模型"""

    code: int = Field(default=0, description="业务状态码，0 表示成功")
    message: str = Field(default="success", description="响应消息")
    data: Any | None = Field(default=None, description="响应数据")


class PaginationParams(BaseModel):
    """分页参数"""

    page: int = Field(default=1, ge=1, description="页码")
    page_size: int = Field(default=10, ge=1, le=100, description="每页数量")


class PaginatedResponse(BaseModel):
    """分页响应"""

    total: int = Field(description="总数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
    items: list[Any] = Field(description="数据列表")


# ────────── 上传 ──────────
class UploadResponse(BaseModel):
    """上传响应"""

    upload_id: str = Field(description="上传文件 ID")
    filename: str = Field(description="原始文件名")
    file_size: int = Field(description="文件大小（字节）")
    content_type: str = Field(description="文件类型")


# ────────── 任务 ──────────
class CreateTaskRequest(BaseModel):
    """创建任务请求"""

    upload_id: str = Field(description="上传文件 ID")
    standard: str = Field(description="排版规范")
    use_rag: bool = Field(default=True, description="是否使用 RAG")
    llm_model: str = Field(default="qwen-plus", description="LLM 模型")
    custom_config: dict[str, Any] | None = Field(default=None, description="自定义配置")


class TaskInfo(BaseModel):
    """任务信息"""

    id: str = Field(description="任务 ID")
    filename: str = Field(description="文件名")
    standard: str = Field(description="排版规范")
    status: TaskStatus = Field(description="任务状态")
    progress: int = Field(default=0, ge=0, le=100, description="进度百分比")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
    error_message: str | None = Field(default=None, description="错误信息")
    file_size_mb: float | None = Field(default=None, description="文件大小（MB）")


class TaskDetail(TaskInfo):
    """任务详情"""

    current_step: str | None = Field(default=None, description="当前处理步骤")
    cleaned_markdown_preview: str | None = Field(default=None, description="清洗后的 Markdown 预览")
    style_config_preview: dict | None = Field(default=None, description="样式配置预览")


class TaskListResponse(PaginatedResponse):
    """任务列表响应"""

    items: list[TaskInfo] = Field(description="任务列表")


# ────────── 知识库 ──────────
class KbDocumentInfo(BaseModel):
    """知识库文档信息"""

    id: str = Field(description="文档 ID")
    name: str = Field(description="文档名称")
    source: str = Field(description="来源路径")
    status: str = Field(description="索引状态: indexed/pending/failed")
    chunk_count: int = Field(default=0, description="切片数量")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class KbListResponse(PaginatedResponse):
    """知识库文档列表"""

    items: list[KbDocumentInfo] = Field(description="文档列表")


class RebuildKbRequest(BaseModel):
    """重建知识库请求"""

    force: bool = Field(default=False, description="强制重建")


# ────────── 系统配置 ──────────
class SystemConfig(BaseModel):
    """系统配置"""

    llm_provider: str = Field(default="qwen", description="默认 LLM Provider")
    llm_model: str = Field(default="qwen-plus", description="默认 LLM 模型")
    rag_bm25_weight: float = Field(default=0.3, ge=0, le=1, description="BM25 权重")
    rag_vector_weight: float = Field(default=0.7, ge=0, le=1, description="向量权重")
    rag_top_k: int = Field(default=5, ge=1, le=20, description="Top-K 检索数量")
    pandoc_path: str = Field(default="pandoc", description="Pandoc 可执行路径")
    output_dir: str = Field(default="data/output", description="输出目录")
    max_file_size_mb: int = Field(default=50, ge=1, le=500, description="最大文件大小（MB）")
    supported_formats: list[str] = Field(default=["pdf", "md", "txt"], description="支持的文件格式")


class UpdateConfigRequest(BaseModel):
    """更新配置请求"""

    llm_provider: str | None = Field(default=None, description="LLM Provider")
    llm_model: str | None = Field(default=None, description="LLM 模型")
    rag_bm25_weight: float | None = Field(default=None, ge=0, le=1)
    rag_vector_weight: float | None = Field(default=None, ge=0, le=1)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    pandoc_path: str | None = Field(default=None)
    max_file_size_mb: int | None = Field(default=None, ge=1, le=500)

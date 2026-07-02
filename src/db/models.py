"""数据库 ORM 模型"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class TaskModel(Base):
    """任务表"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    upload_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    standard: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[str] = mapped_column(String(100), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size_mb: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_json_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cleaned_markdown_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_config_preview: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, default=dict)

    def __repr__(self) -> str:
        return f"<Task(id={self.id}, filename={self.filename}, status={self.status})>"


class KbDocumentModel(Base):
    """知识库文档表"""

    __tablename__ = "kb_documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<KbDocument(id={self.id}, name={self.name})>"


class SystemConfigModel(Base):
    """系统配置表（单条记录）"""

    __tablename__ = "system_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    llm_provider: Mapped[str] = mapped_column(String(50), default="qwen")
    llm_model: Mapped[str] = mapped_column(String(100), default="qwen-plus")
    rag_bm25_weight: Mapped[float] = mapped_column(Float, default=0.3)
    rag_vector_weight: Mapped[float] = mapped_column(Float, default=0.7)
    rag_top_k: Mapped[int] = mapped_column(Integer, default=5)
    pandoc_path: Mapped[str] = mapped_column(String(500), default="pandoc")
    output_dir: Mapped[str] = mapped_column(String(500), default="data/output")
    max_file_size_mb: Mapped[int] = mapped_column(Integer, default=50)
    supported_formats: Mapped[str] = mapped_column(String(500), default="pdf,md,txt")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<SystemConfig(id={self.id})>"

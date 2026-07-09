"""数据库 ORM 模型"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.database import Base


class TaskModel(Base):
    """任务表"""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
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


class StyleTemplateModel(Base):
    """样式模板表

    保存用户上传/自定义的排版样式模板，可在创建任务时选择使用。
    user_id 为空表示为系统预置模板（所有人可见），非空为个人模板。
    """

    __tablename__ = "style_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    style_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_docx_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<StyleTemplate(id={self.id}, name={self.name})>"


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


class ChatSessionModel(Base):
    """对话会话表

    保存用户的对话排版会话，支持多轮对话历史持久化。
    """

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), default="新对话")
    style_config: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def __repr__(self) -> str:
        return f"<ChatSession(id={self.id}, title={self.title})>"


class ChatMessageModel(Base):
    """对话消息表

    保存会话中的每条消息（用户/AI），支持多轮对话历史恢复。
    """

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user / assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    style_config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # AI回复时的样式快照
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<ChatMessage(session={self.session_id}, role={self.role})>"


class StyleAdjustmentHistoryModel(Base):
    """样式调整历史表

    记录用户每次调整样式的操作（修正样式/上传修正DOCX/应用模板/对话排版），
    用于 AI 迭代学习：后续 LLM 样式提取时作为 few-shot 示例参考。
    """

    __tablename__ = "style_adjustment_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    source: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # edit_style / upload_corrected / apply_template / chat
    before_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    standard: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<StyleAdjustmentHistory(task={self.task_id}, source={self.source})>"


class UserModel(Base):
    """用户表

    支持用户名+密码注册登录，role 区分普通用户和管理员。
    管理员可访问知识库管理、系统配置等全局功能。
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user")  # user / admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"

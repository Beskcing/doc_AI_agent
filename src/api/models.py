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

    GBT_1_1 = "GB/T 1.1"
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


class BatchUploadResponse(BaseModel):
    """批量上传响应"""

    results: list[UploadResponse] = Field(description="上传结果列表")


# ────────── 任务 ──────────
class CreateTaskRequest(BaseModel):
    """创建任务请求"""

    upload_id: str = Field(description="上传文件 ID")
    standard: str = Field(description="排版规范")
    use_rag: bool = Field(default=True, description="是否使用 RAG")
    llm_model: str = Field(default="qwen-plus", description="LLM 模型")
    template_id: str | None = Field(default=None, description="样式模板 ID，指定后跳过 LLM 样式提取")
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


class BatchTaskItem(BaseModel):
    """批量任务项"""

    upload_id: str = Field(description="上传文件 ID")
    filename: str = Field(description="原始文件名")


class BatchCreateTaskRequest(BaseModel):
    """批量创建任务请求"""

    items: list[BatchTaskItem] = Field(description="任务项列表")
    standard: str = Field(description="排版规范")
    use_rag: bool = Field(default=True, description="是否使用 RAG")
    llm_model: str = Field(default="qwen-plus", description="LLM 模型")
    template_id: str | None = Field(default=None, description="样式模板 ID")
    custom_config: dict[str, Any] | None = Field(default=None, description="自定义配置")


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


class KbSearchRequest(BaseModel):
    """知识库检索请求"""

    query: str = Field(description="检索查询文本")
    top_k: int = Field(default=5, description="返回结果数量")


class KbUpdateContentRequest(BaseModel):
    """知识库文档内容更新请求"""

    content: str = Field(description="文档内容（Markdown/纯文本）")
    rebuild_index: bool = Field(default=False, description="是否重建索引")


# ────────── 样式模板 ──────────
class SaveTemplateRequest(BaseModel):
    """保存样式模板请求"""

    name: str = Field(description="模板名称")
    style_config: dict[str, Any] = Field(description="样式配置 JSON")
    standard: str | None = Field(default=None, description="关联标准号，如 GB/T 1.1")
    description: str | None = Field(default=None, description="模板描述")
    source_docx_path: str | None = Field(default=None, description="来源 DOCX 路径")


class UpdateTemplateRequest(BaseModel):
    """更新样式模板请求"""

    name: str | None = Field(default=None, description="模板名称")
    style_config: dict[str, Any] | None = Field(default=None, description="样式配置 JSON")
    standard: str | None = Field(default=None, description="关联标准号")
    description: str | None = Field(default=None, description="模板描述")


class StyleTemplateInfo(BaseModel):
    """样式模板信息"""

    id: str = Field(description="模板 ID")
    name: str = Field(description="模板名称")
    description: str | None = Field(default=None, description="模板描述")
    standard: str | None = Field(default=None, description="关联标准号")
    style_config: dict[str, Any] = Field(description="样式配置")
    source_docx_path: str | None = Field(default=None, description="来源 DOCX 路径")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class StyleTemplateListResponse(PaginatedResponse):
    """样式模板列表响应"""

    items: list[StyleTemplateInfo] = Field(description="模板列表")


# ────────── 对话排版 ──────────
class ChatRequest(BaseModel):
    """对话排版请求"""

    message: str = Field(description="用户消息")
    current_style_config: dict[str, Any] = Field(description="当前样式配置")
    context: str | None = Field(default=None, description="上下文信息（文档类型等）")
    session_id: str | None = Field(default=None, description="会话 ID，为空时自动创建新会话")


class ChatResponse(BaseModel):
    """对话排版响应"""

    reply: str = Field(description="AI 回复")
    updated_style_config: dict[str, Any] = Field(description="更新后的样式配置")
    session_id: str = Field(description="会话 ID")


class ChatSessionInfo(BaseModel):
    """会话信息"""

    id: str = Field(description="会话 ID")
    title: str = Field(description="会话标题")
    style_config: dict[str, Any] = Field(description="当前样式配置")
    message_count: int = Field(default=0, description="消息数量")
    created_at: datetime = Field(description="创建时间")
    updated_at: datetime = Field(description="更新时间")


class ChatSessionListResponse(PaginatedResponse):
    """会话列表响应"""

    items: list[ChatSessionInfo] = Field(description="会话列表")


class ChatMessageInfo(BaseModel):
    """消息信息"""

    id: str = Field(description="消息 ID")
    session_id: str = Field(description="会话 ID")
    role: str = Field(description="角色: user/assistant")
    content: str = Field(description="消息内容")
    style_config_snapshot: dict[str, Any] | None = Field(default=None, description="样式快照")
    created_at: datetime = Field(description="创建时间")


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    title: str = Field(default="新对话", description="会话标题")
    style_config: dict[str, Any] | None = Field(default=None, description="初始样式配置")


# ────────── 应用模板 ──────────
class ApplyTemplateRequest(BaseModel):
    """应用模板到任务请求"""

    template_id: str | None = Field(default=None, description="模板 ID")
    style_config: dict[str, Any] | None = Field(default=None, description="直接传入样式配置")
    source: str = Field(default="apply_template", description="调整来源: apply_template/edit_style")


# ────────── 调整回写 ──────────
class SaveStyleToTemplateRequest(BaseModel):
    """保存样式配置到模板请求"""

    template_id: str | None = Field(default=None, description="要更新的模板 ID，为空则新建模板")
    template_name: str = Field(description="模板名称")
    style_config: dict[str, Any] = Field(description="样式配置")
    description: str | None = Field(default=None, description="模板描述")


# ────────── 样式调整历史 ──────────
class StyleAdjustmentInfo(BaseModel):
    """样式调整记录信息"""

    id: str = Field(description="记录 ID")
    task_id: str = Field(description="任务 ID")
    source: str = Field(description="调整来源: edit_style/upload_corrected/apply_template/chat")
    before_config: dict[str, Any] | None = Field(default=None, description="调整前样式")
    after_config: dict[str, Any] | None = Field(default=None, description="调整后样式")
    diff_summary: str | None = Field(default=None, description="差异摘要")
    standard: str | None = Field(default=None, description="关联标准号")
    created_at: datetime = Field(description="创建时间")


# ────────── 磁盘管理 ──────────
class CleanupRequest(BaseModel):
    """批量清理请求"""

    older_than_days: int = Field(default=30, ge=1, le=365, description="清理多少天前的任务输出")
    dry_run: bool = Field(default=False, description="仅计算不实际删除")


# ────────── 内容编辑 ──────────
class UpdateContentRequest(BaseModel):
    """更新文档内容请求"""

    content: str = Field(description="修改后的内容")
    content_type: str = Field(default="markdown", description="内容类型: html 或 markdown")
    regenerate_docx: bool = Field(default=True, description="是否重新生成 DOCX")


class ContentEditRequest(BaseModel):
    """LLM 对话修改文档内容请求"""

    message: str = Field(description="用户修改指令")
    task_id: str = Field(description="关联的任务 ID")
    session_id: str | None = Field(default=None, description="会话 ID")


class ChatStreamRequest(BaseModel):
    """流式对话请求"""

    message: str = Field(description="用户消息")
    system_prompt: str | None = Field(default=None, description="系统提示词")


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


# ────────── 用户认证 ──────────
class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(
        min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$", description="用户名，3-20位字母数字下划线"
    )
    password: str = Field(min_length=8, max_length=64, description="密码，8-64位，需含大小写字母和数字")


class LoginRequest(BaseModel):
    """用户登录请求"""

    username: str = Field(description="用户名")
    password: str = Field(description="密码")


class TokenResponse(BaseModel):
    """Token 响应"""

    access_token: str = Field(description="Access Token")
    refresh_token: str = Field(description="Refresh Token")
    token_type: str = Field(default="bearer", description="Token 类型")
    expires_in: int = Field(default=1800, description="过期时间（秒）")
    user: dict = Field(default_factory=dict, description="用户信息摘要")


class RefreshRequest(BaseModel):
    """刷新 Token 请求"""

    refresh_token: str = Field(description="Refresh Token")


class UserInfo(BaseModel):
    """用户信息"""

    id: str = Field(description="用户 ID")
    username: str = Field(description="用户名")
    role: str = Field(description="角色: user/admin")
    is_active: bool = Field(description="是否启用")
    created_at: datetime = Field(description="注册时间")


class UpdateConfigRequest(BaseModel):
    """更新配置请求"""

    llm_provider: str | None = Field(default=None, description="LLM Provider")
    llm_model: str | None = Field(default=None, description="LLM 模型")
    rag_bm25_weight: float | None = Field(default=None, ge=0, le=1)
    rag_vector_weight: float | None = Field(default=None, ge=0, le=1)
    rag_top_k: int | None = Field(default=None, ge=1, le=20)
    pandoc_path: str | None = Field(default=None)
    output_dir: str | None = Field(default=None, description="输出目录")
    max_file_size_mb: int | None = Field(default=None, ge=1, le=500)


# ────────── 管理员用户管理 ──────────
class AdminCreateUserRequest(BaseModel):
    """管理员创建用户请求"""

    username: str = Field(
        min_length=3, max_length=20, pattern=r"^[a-zA-Z0-9_]+$", description="用户名，3-20位字母数字下划线"
    )
    password: str = Field(min_length=8, max_length=64, description="密码，8-64位，需含大小写字母和数字")
    role: str = Field(default="user", pattern=r"^(user|admin)$", description="角色: user 或 admin")


class AdminUpdateUserRequest(BaseModel):
    """管理员更新用户请求（所有字段可选）"""

    password: str | None = Field(default=None, min_length=8, max_length=64, description="新密码，8-64位")
    is_active: bool | None = Field(default=None, description="是否启用")
    role: str | None = Field(default=None, pattern=r"^(user|admin)$", description="角色: user 或 admin")

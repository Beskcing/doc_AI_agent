"""文档结构数据模型

定义文档解析、清洗、意图分析等阶段的数据结构。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DocumentSection(BaseModel):
    """文档章节"""

    heading: str = Field(description="章节标题")
    level: int = Field(ge=1, le=6, description="标题层级 1-6")
    content_md: str = Field(description="章节 Markdown 内容")
    tables: list[str] = Field(default_factory=list, description="章节中的 HTML 表格原文")
    images: list[str] = Field(default_factory=list, description="章节中的图片引用路径")


class ParsedDocument(BaseModel):
    """MinerU 解析结果"""

    title: str = Field(default="", description="文档标题")
    sections: list[DocumentSection] = Field(default_factory=list, description="文档章节列表")
    raw_markdown: str = Field(description="MinerU 输出的原始 Markdown 全文")
    metadata: dict = Field(default_factory=dict, description="MinerU 解析元数据（置信度、页码映射等）")
    page_count: int = Field(default=0, description="原始 PDF 页数")
    image_paths: list[str] = Field(default_factory=list, description="所有图片路径列表")


class CleaningResult(BaseModel):
    """Markdown 清洗结果"""

    cleaned_markdown: str = Field(description="清洗后的纯净 Markdown 文本")
    changes_log: list[str] = Field(default_factory=list, description="清洗操作日志")
    ocr_issues_found: int = Field(default=0, description="发现的 OCR 问题数量")
    ocr_errors_marked: int = Field(default=0, description="标记为需人工核对的 OCR 错误数量")
    images_missing: int = Field(default=0, description="缺失图片数量")
    formulas_preserved: int = Field(default=0, description="保留的公式图片引用数量")


class IntentAnalysis(BaseModel):
    """文档意图分析结果"""

    document_type: str = Field(default="general", description="文档类型，如 '技术报告'、'公文'、'论文'、'标准文件'")
    detected_standard: str | None = Field(default=None, description="检测到的适用标准，如 'GB/T 9704'、'GB/T 7713'")
    formatting_requirements: list[str] = Field(default_factory=list, description="从文档内容推断的排版需求列表")
    has_complex_tables: bool = Field(default=False, description="是否包含复杂表格")
    has_formulas: bool = Field(default=False, description="是否包含数学公式")
    has_chemical_structures: bool = Field(default=False, description="是否包含化学结构式")
    language: str = Field(default="zh-CN", description="文档主语言")


class ConversionReport(BaseModel):
    """Pandoc 转换结果报告"""

    success: bool = Field(description="转换是否成功")
    output_path: str = Field(default="", description="输出文件路径")
    tables_converted: int = Field(default=0, description="成功转换的表格数量")
    formulas_converted: int = Field(default=0, description="成功转换的公式数量")
    warnings: list[str] = Field(default_factory=list, description="转换过程中的警告信息")
    errors: list[str] = Field(default_factory=list, description="转换过程中的错误信息")


class StyleReport(BaseModel):
    """样式应用结果报告"""

    success: bool = Field(description="样式应用是否成功")
    paragraphs_styled: int = Field(default=0, description="应用样式的段落数量")
    tables_styled: int = Field(default=0, description="应用样式的表格数量")
    headings_styled: int = Field(default=0, description="应用样式的标题数量")
    warnings: list[str] = Field(default_factory=list, description="警告信息（如字体缺失）")
    output_path: str = Field(default="", description="最终输出文件路径")


class RetrievalResult(BaseModel):
    """RAG 检索结果"""

    content: str = Field(description="检索到的文档片段内容")
    source: str = Field(description="来源文档名称")
    section: str = Field(default="", description="来源章节")
    score: float = Field(description="相关性得分")
    retrieval_method: str = Field(default="hybrid", description="检索方式: bm25 / vector / hybrid")

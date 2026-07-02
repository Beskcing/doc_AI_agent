"""MinerU PDF 解析工具

封装 MinerU SDK，将 PDF 解析为 Markdown + 元数据。
MinerU 为可选依赖，未安装时可通过预生成的 Markdown fixture 进行测试。
"""

from __future__ import annotations

import re
from pathlib import Path

from src.models.document_schema import DocumentSection, ParsedDocument
from src.tools.html_table_preserver import HTMLTablePreserver
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MinerUParser:
    """MinerU PDF 解析器

    将 PDF 文件解析为结构化 Markdown，提取表格、图片和公式等元素。
    """

    def __init__(self, output_dir: str | None = None):
        """初始化解析器

        Args:
            output_dir: MinerU 输出目录，为 None 时使用临时目录
        """
        self.output_dir = Path(output_dir) if output_dir else None
        self._table_preserver = HTMLTablePreserver()

    def check_installation(self) -> bool:
        """检查 MinerU (magic-pdf) 是否已安装

        Returns:
            是否可用
        """
        try:
            import magic_pdf  # noqa: F401
            return True
        except ImportError:
            logger.warning("MinerU (magic-pdf) 未安装，仅支持从已有 Markdown 加载")
            return False

    def parse_pdf(self, pdf_path: str | Path) -> ParsedDocument:
        """解析 PDF 文件为结构化 Markdown

        Args:
            pdf_path: PDF 文件路径

        Returns:
            ParsedDocument 实例

        Raises:
            ImportError: MinerU 未安装
            FileNotFoundError: PDF 文件不存在
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        if not self.check_installation():
            raise ImportError(
                "MinerU (magic-pdf) 未安装。请执行: pip install magic-pdf\n"
                "或使用 load_markdown() 方法直接加载已解析的 Markdown 文件。"
            )

        logger.info("开始解析 PDF: %s", pdf_path)

        try:
            from magic_pdf.pipe.UNIPipe import UNIPipe
            from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

            # 使用 MinerU 解析
            image_writer = DiskReaderWriter(str(pdf_path.parent / "images")) if self.output_dir else None
            model_json_path = None  # 使用默认模型

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            jso_useful_key = {"_pdf_type": "", "model_list": []}
            pipe = UNIPipe(pdf_bytes, jso_useful_key, image_writer)
            pipe.pipe_classify()
            pipe.pipe_analyze()
            pipe.pipe_parse()

            # 获取 Markdown 输出
            markdown_content = pipe.pipe_mk_uni_format(str(pdf_path.parent), drop_mode="none")
            content_list = pipe.pipe_mk_uni_format(str(pdf_path.parent), drop_mode="none")

            # 构建解析结果
            return self._build_parsed_document(markdown_content, pdf_path)

        except Exception as e:
            logger.error("MinerU 解析失败: %s", e)
            raise RuntimeError(f"MinerU 解析 PDF 失败: {e}") from e

    def load_markdown(self, markdown_path: str | Path, pdf_path: str | None = None) -> ParsedDocument:
        """从已有的 Markdown 文件加载解析结果

        适用于 MinerU 已解析完成的场景，或测试时使用 fixture。

        Args:
            markdown_path: Markdown 文件路径
            pdf_path: 原始 PDF 路径（可选，用于关联图片等资源）

        Returns:
            ParsedDocument 实例
        """
        markdown_path = Path(markdown_path)
        if not markdown_path.exists():
            raise FileNotFoundError(f"Markdown 文件不存在: {markdown_path}")

        markdown_content = markdown_path.read_text(encoding="utf-8")
        logger.info("从 Markdown 加载: %s (%d 字节)", markdown_path, len(markdown_content))

        return self._build_parsed_document(markdown_content, Path(pdf_path) if pdf_path else None)

    def _build_parsed_document(self, markdown: str, pdf_path: Path | None) -> ParsedDocument:
        """从 Markdown 文本构建 ParsedDocument

        Args:
            markdown: Markdown 文本
            pdf_path: 原始 PDF 路径

        Returns:
            ParsedDocument 实例
        """
        # 提取标题（第一个 # 开头的行）
        title = self._extract_title(markdown)

        # 提取章节结构
        sections = self._extract_sections(markdown)

        # 提取图片路径
        image_paths = self._extract_image_paths(markdown)

        # 构建元数据
        metadata = {
            "source_pdf": str(pdf_path) if pdf_path else None,
            "table_count": self._table_preserver.count_tables(markdown),
            "image_count": len(image_paths),
        }

        return ParsedDocument(
            title=title,
            sections=sections,
            raw_markdown=markdown,
            metadata=metadata,
            image_paths=image_paths,
        )

    def _extract_title(self, markdown: str) -> str:
        """提取文档标题

        Args:
            markdown: Markdown 文本

        Returns:
            标题文本，未找到返回空字符串
        """
        for line in markdown.splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
        return ""

    def _extract_sections(self, markdown: str) -> list[DocumentSection]:
        """提取文档章节结构

        Args:
            markdown: Markdown 文本

        Returns:
            DocumentSection 列表
        """
        sections: list[DocumentSection] = []
        # 匹配标题行 (# ## ### 等)
        heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)

        matches = list(heading_pattern.finditer(markdown))
        if not matches:
            # 没有标题，整篇作为一个章节
            if markdown.strip():
                sections.append(
                    DocumentSection(
                        heading="(无标题)",
                        level=1,
                        content_md=markdown,
                        tables=self._table_preserver.find_unprotected_tables(markdown),
                        images=self._extract_image_paths(markdown),
                    )
                )
            return sections

        for i, match in enumerate(matches):
            level = len(match.group(1))
            heading = match.group(2).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
            content = markdown[start:end].strip()

            sections.append(
                DocumentSection(
                    heading=heading,
                    level=level,
                    content_md=content,
                    tables=self._table_preserver.find_unprotected_tables(content),
                    images=self._extract_image_paths(content),
                )
            )

        return sections

    def _extract_image_paths(self, markdown: str) -> list[str]:
        """从 Markdown 中提取所有图片引用路径

        支持格式:
        - ![alt](path)
        - <img src="path">

        Args:
            markdown: Markdown 文本

        Returns:
            图片路径列表
        """
        paths: list[str] = []

        # Markdown 图片语法
        md_pattern = re.compile(r"!\[.*?\]\((.*?)\)")
        for match in md_pattern.finditer(markdown):
            paths.append(match.group(1))

        # HTML img 标签
        html_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        for match in html_pattern.finditer(markdown):
            paths.append(match.group(1))

        return paths

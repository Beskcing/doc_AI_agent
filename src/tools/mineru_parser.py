"""MinerU PDF 解析工具

支持两种解析模式：
1. online  — 调用 MinerU 线上 API（精准解析），无需本地安装 SDK
2. local   — 使用本地 MinerU (magic-pdf) SDK 解析

MinerU SDK 为可选依赖，未安装时可通过 online 模式或预生成 Markdown fixture 进行测试。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from src.models.document_schema import DocumentSection, ParsedDocument
from src.tools.html_table_preserver import HTMLTablePreserver
from src.tools.mineru_api_client import MinerUAPIClient, MinerUModelVersion
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MinerUParser:
    """MinerU PDF 解析器

    将 PDF 文件解析为结构化 Markdown，提取表格、图片和公式等元素。

    支持双模式:
    - online: 通过 MinerU 线上 API 解析（推荐，无需安装 SDK）
    - local:  通过本地 magic-pdf SDK 解析
    """

    def __init__(
        self,
        output_dir: str | None = None,
        mode: Literal["online", "local"] = "online",
        api_token: str | None = None,
        model_version: str = MinerUModelVersion.VLM,
    ):
        """初始化解析器

        Args:
            output_dir: MinerU 输出目录，为 None 时使用临时目录
            mode: 解析模式，online（线上API）或 local（本地SDK）
            api_token: MinerU API Token（online 模式必填）
            model_version: 模型版本 (pipeline/vlm/MinerU-HTML)
        """
        self.output_dir = Path(output_dir) if output_dir else None
        self.mode = mode
        self.model_version = model_version
        self._table_preserver = HTMLTablePreserver()

        # 初始化线上 API 客户端
        self._api_client: MinerUAPIClient | None = None
        if mode == "online":
            if not api_token:
                raise ValueError("online 模式需要提供 api_token")
            self._api_client = MinerUAPIClient(token=api_token)

    def check_installation(self) -> bool:
        """检查本地 MinerU (magic-pdf) 是否已安装

        Returns:
            是否可用
        """
        try:
            import magic_pdf  # noqa: F401
            return True
        except ImportError:
            logger.warning("MinerU (magic-pdf) 未安装，仅支持 online 模式或从已有 Markdown 加载")
            return False

    def parse_pdf(
        self,
        pdf_path: str | Path,
        on_progress: Any | None = None,
        extra_formats: list[str] | None = None,
    ) -> ParsedDocument:
        """解析 PDF 文件为结构化 Markdown

        根据初始化时的 mode 选择解析方式:
        - online: 上传到 MinerU 线上 API 解析
        - local:  使用本地 magic-pdf SDK 解析

        Args:
            pdf_path: PDF 文件路径
            on_progress: 进度回调函数 (stage, info) -> None（仅 online 模式）
            extra_formats: 额外输出格式，如 ["docx"]（仅 online 模式）

        Returns:
            ParsedDocument 实例

        Raises:
            FileNotFoundError: PDF 文件不存在
            ImportError: local 模式但 MinerU SDK 未安装
            RuntimeError: 解析失败
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")

        if self.mode == "online":
            return self._parse_pdf_online(pdf_path, on_progress, extra_formats)
        else:
            return self._parse_pdf_local(pdf_path)

    def _parse_pdf_online(
        self,
        pdf_path: Path,
        on_progress: Any | None = None,
        extra_formats: list[str] | None = None,
    ) -> ParsedDocument:
        """通过线上 API 解析 PDF"""
        if not self._api_client:
            raise RuntimeError("online 模式未初始化 API 客户端")

        output_dir = self.output_dir or (pdf_path.parent / f"{pdf_path.stem}_mineru_output")

        logger.info("[online] 开始解析 PDF: %s (extra_formats=%s)", pdf_path, extra_formats)
        result = self._api_client.parse_file(
            pdf_path,
            output_dir=output_dir,
            model_version=self.model_version,
            extra_formats=extra_formats,
            on_progress=on_progress,
        )

        markdown_content = result.get("markdown_content", "")
        if not markdown_content:
            raise RuntimeError("MinerU API 返回空 Markdown 内容")

        # 将线上解析的图片路径补全为绝对路径
        extract_dir = Path(result.get("extract_dir", ""))
        image_dir = result.get("image_dir")
        if image_dir:
            markdown_content = self._fix_image_paths(markdown_content, extract_dir)

        doc = self._build_parsed_document(markdown_content, pdf_path)
        # 补充 MinerU API 元数据
        doc.metadata["mineru_task_id"] = result.get("markdown_path", "")
        doc.metadata["parse_mode"] = "online"
        doc.metadata["model_version"] = self.model_version
        doc.metadata["extract_dir"] = str(extract_dir)
        # MinerU 提供的 DOCX 文件路径（extra_formats=["docx"] 时可用）
        doc.metadata["mineru_docx_path"] = result.get("mineru_docx_path")
        return doc

    def _parse_pdf_local(self, pdf_path: Path) -> ParsedDocument:
        """通过本地 SDK 解析 PDF"""
        if not self.check_installation():
            raise ImportError(
                "MinerU (magic-pdf) 未安装。请执行: pip install magic-pdf\n"
                "或使用 online 模式，或使用 load_markdown() 方法直接加载已解析的 Markdown 文件。"
            )

        logger.info("[local] 开始解析 PDF: %s", pdf_path)

        try:
            from magic_pdf.pipe.UNIPipe import UNIPipe
            from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter

            image_writer = DiskReaderWriter(str(pdf_path.parent / "images")) if self.output_dir else None

            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            jso_useful_key = {"_pdf_type": "", "model_list": []}
            pipe = UNIPipe(pdf_bytes, jso_useful_key, image_writer)
            pipe.pipe_classify()
            pipe.pipe_analyze()
            pipe.pipe_parse()

            markdown_content = pipe.pipe_mk_uni_format(str(pdf_path.parent), drop_mode="none")

            doc = self._build_parsed_document(markdown_content, pdf_path)
            doc.metadata["parse_mode"] = "local"
            return doc

        except Exception as e:
            logger.error("MinerU 本地解析失败: %s", e)
            raise RuntimeError(f"MinerU 本地解析 PDF 失败: {e}") from e

    def _fix_image_paths(self, markdown: str, base_dir: Path) -> str:
        """验证并修复 Markdown 中的图片路径

        保持相对路径不变（Pandoc 通过 --resource-path 解析），
        仅校验图片文件是否存在，失效路径替换为占位符。
        """
        def replace_md_img(match: re.Match) -> str:
            alt = match.group(1)
            path = match.group(2)
            # 跳过外部 URL
            if path.startswith("http"):
                return match.group(0)
            # 校验本地文件是否存在
            full_path = (base_dir / path).resolve()
            if not full_path.exists():
                logger.warning("图片文件不存在: %s", full_path)
                return f"![{alt}]([IMAGE_MISSING])"
            return match.group(0)  # 保持原相对路径

        markdown = re.sub(r"!\[(.*?)\]\((.*?)\)", replace_md_img, markdown)

        def replace_html_img(match: re.Match) -> str:
            full = match.group(0)
            path = match.group(1)
            if path.startswith("http"):
                return full
            full_path = (base_dir / path).resolve()
            if not full_path.exists():
                logger.warning("HTML img 文件不存在: %s", full_path)
                return full.replace(path, "[IMAGE_MISSING]")
            return full

        html_img_pattern = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)
        markdown = html_img_pattern.sub(replace_html_img, markdown)
        return markdown

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

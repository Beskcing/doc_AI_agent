"""DOCX 样式提取工具

从用户上传的 Word 模板文件中提取排版格式，输出 StyleConfig 兼容的 dict。
使用 python-docx 读取文档属性，纯工具函数，无 LLM 参与。
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Emu, Pt

from src.utils.logger import get_logger

logger = get_logger(__name__)

# EMU 转换常量
EMU_PER_CM = 360000  # 1cm = 360000 EMU
EMU_PER_PT = 12700  # 1pt = 12700 EMU

# 对齐方式反向映射
ALIGNMENT_REVERSE_MAP = {
    WD_ALIGN_PARAGRAPH.LEFT: "left",
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
}

# 标题样式名映射
HEADING_STYLE_MAP = {
    "Heading 1": 1, "Heading 2": 2, "Heading 3": 3,
    "Heading 4": 4, "Heading 5": 5, "Heading 6": 6,
    "heading 1": 1, "heading 2": 2, "heading 3": 3,
    "heading 4": 4, "heading 5": 5, "heading 6": 6,
    "Title": 1,  # Title 样式视为一级标题
}

# 常见国标纸张尺寸 (EMU)
PAPER_SIZES = {
    (Cm(21.0), Cm(29.7)): "A4",
    (Cm(29.7), Cm(42.0)): "A3",
    (Cm(17.6), Cm(25.0)): "B5",
    (Cm(21.59), Cm(27.94)): "Letter",
}


def _emu_to_cm(emu: int) -> float:
    """将 EMU 转换为厘米"""
    if emu is None:
        return 0.0
    return round(emu / EMU_PER_CM, 2)


def _emu_to_pt(emu: int) -> float:
    """将 EMU 转换为磅"""
    if emu is None:
        return 0.0
    return round(emu / EMU_PER_PT, 1)


def _rgb_to_hex(rgb) -> str:
    """将 RGBColor 转换为十六进制字符串"""
    if rgb is None:
        return "#000000"
    return f"#{str(rgb)}"


class DocxStyleExtractor:
    """从 DOCX 文件提取排版样式配置"""

    def extract(self, docx_path: str | Path) -> dict:
        """从 DOCX 提取完整的样式配置

        Args:
            docx_path: DOCX 文件路径

        Returns:
            StyleConfig 兼容的字典
        """
        docx_path = Path(docx_path)
        if not docx_path.exists():
            raise FileNotFoundError(f"DOCX 文件不存在: {docx_path}")

        logger.info("开始提取 DOCX 样式: %s", docx_path)
        doc = Document(str(docx_path))

        result = {
            "page_layout": self._extract_page_layout(doc),
            "heading_styles": self._extract_heading_styles(doc),
            "body_style": self._extract_body_style(doc),
            "table_style": self._extract_table_style(doc),
            "rag_sources": [],
        }

        logger.info("DOCX 样式提取完成: %d 标题样式, 表格=%s",
                     len(result["heading_styles"]),
                     result["table_style"] is not None)
        return result

    def _extract_page_layout(self, doc: Document) -> dict:
        """提取页面布局"""
        layout = {
            "paper_size": "A4",
            "margin_top_cm": 3.7,
            "margin_bottom_cm": 3.5,
            "margin_left_cm": 2.8,
            "margin_right_cm": 2.6,
            "header_distance_cm": 1.5,
            "footer_distance_cm": 1.75,
            "orientation": "portrait",
        }

        if not doc.sections:
            return layout

        section = doc.sections[0]

        # 纸张大小
        try:
            width = section.page_width
            height = section.page_height
            if width and height:
                key = (width, height)
                if key in PAPER_SIZES:
                    layout["paper_size"] = PAPER_SIZES[key]
                else:
                    # 尝试匹配宽高颠倒的情况
                    key_rev = (height, width)
                    if key_rev in PAPER_SIZES:
                        layout["paper_size"] = PAPER_SIZES[key_rev]

                # 方向判断
                if height < width:
                    layout["orientation"] = "landscape"
        except Exception:
            pass

        # 页边距
        try:
            if section.top_margin:
                layout["margin_top_cm"] = _emu_to_cm(section.top_margin)
            if section.bottom_margin:
                layout["margin_bottom_cm"] = _emu_to_cm(section.bottom_margin)
            if section.left_margin:
                layout["margin_left_cm"] = _emu_to_cm(section.left_margin)
            if section.right_margin:
                layout["margin_right_cm"] = _emu_to_cm(section.right_margin)
            if section.header_distance:
                layout["header_distance_cm"] = _emu_to_cm(section.header_distance)
            if section.footer_distance:
                layout["footer_distance_cm"] = _emu_to_cm(section.footer_distance)
        except Exception:
            pass

        return layout

    def _extract_heading_styles(self, doc: Document) -> list[dict]:
        """提取各级标题样式"""
        heading_styles: dict[int, dict] = {}

        for paragraph in doc.paragraphs:
            style_name = paragraph.style.name if paragraph.style else ""
            if style_name not in HEADING_STYLE_MAP:
                continue

            level = HEADING_STYLE_MAP[style_name]
            if level in heading_styles:
                continue  # 只取第一次出现的

            font_config = self._extract_font_from_paragraph(paragraph)
            alignment = self._extract_alignment(paragraph)
            line_spacing = self._extract_line_spacing(paragraph)
            space_before, space_after = self._extract_spacing(paragraph)
            first_indent = self._extract_first_indent(paragraph)

            heading_styles[level] = {
                "level": level,
                "font": font_config,
                "line_spacing": line_spacing,
                "space_before_pt": space_before,
                "space_after_pt": space_after,
                "alignment": alignment,
                "first_line_indent_chars": first_indent,
                "keep_with_next": True,
            }

        return list(heading_styles.values())

    def _extract_body_style(self, doc: Document) -> dict:
        """提取正文样式

        从文档中找到第一个非标题、非空、非列表的段落作为正文参考。
        """
        for paragraph in doc.paragraphs:
            style_name = paragraph.style.name if paragraph.style else ""
            if style_name in HEADING_STYLE_MAP:
                continue
            if "List" in style_name or "list" in style_name:
                continue
            if "TOC" in style_name or "toc" in style_name:
                continue
            if not paragraph.text.strip():
                continue

            font_config = self._extract_font_from_paragraph(paragraph)
            alignment = self._extract_alignment(paragraph)
            line_spacing = self._extract_line_spacing(paragraph)
            space_before, space_after = self._extract_spacing(paragraph)
            first_indent = self._extract_first_indent(paragraph)

            return {
                "font": font_config,
                "line_spacing": line_spacing,
                "space_before_pt": space_before,
                "space_after_pt": space_after,
                "alignment": alignment,
                "first_line_indent_chars": first_indent,
            }

        # 未找到正文段落，返回默认值
        return {
            "font": {
                "family": "仿宋_GB2312",
                "size_pt": 16,
                "bold": False,
                "italic": False,
                "color_hex": "#000000",
            },
            "line_spacing": 1.5,
            "space_before_pt": 0,
            "space_after_pt": 0,
            "alignment": "justify",
            "first_line_indent_chars": 2,
        }

    def _extract_table_style(self, doc: Document) -> dict | None:
        """提取表格样式"""
        if not doc.tables:
            return None

        table = doc.tables[0]

        # 提取边框信息
        border_style = "single"
        border_width = 0.5
        try:
            tbl = table._tbl
            tblPr = tbl.find(qn("w:tblPr"))
            if tblPr is not None:
                tblBorders = tblPr.find(qn("w:tblBorders"))
                if tblBorders is not None:
                    top = tblBorders.find(qn("w:top"))
                    if top is not None:
                        val = top.get(qn("w:val"), "single")
                        sz = top.get(qn("w:sz"), "4")
                        border_style = "double" if val == "double" else "single"
                        border_width = round(int(sz) / 8, 1)
        except Exception:
            pass

        # 提取表头和正文字体
        header_font = self._extract_font_from_table_cell(table, 0, 0)
        body_font = self._extract_font_from_table_cell(table, 1, 0) if len(table.rows) > 1 else header_font

        return {
            "border_style": border_style,
            "border_width_pt": border_width,
            "header_font": header_font,
            "body_font": body_font,
            "header_bold": True,
            "header_bg_color": None,
            "cell_padding_pt": 2.0,
        }

    def _extract_font_from_paragraph(self, paragraph) -> dict:
        """从段落中提取字体配置"""
        font_config = {
            "family": "仿宋_GB2312",
            "size_pt": 16,
            "bold": False,
            "italic": False,
            "color_hex": "#000000",
        }

        # 优先从 run 提取
        for run in paragraph.runs:
            if run.font.name:
                font_config["family"] = run.font.name
            if run.font.size:
                font_config["size_pt"] = _emu_to_pt(run.font.size)
            if run.font.bold is not None:
                font_config["bold"] = run.font.bold
            if run.font.italic is not None:
                font_config["italic"] = run.font.italic
            if run.font.color and run.font.color.rgb:
                font_config["color_hex"] = _rgb_to_hex(run.font.color.rgb)
            break  # 只取第一个 run

        # 尝试从东亚字体属性提取
        try:
            r_element = paragraph._element
            rpr = r_element.find(qn("w:pPr"))
            if rpr is not None:
                r_fonts = rpr.find(qn("w:rFonts"))
                if r_fonts is not None:
                    east_asia = r_fonts.get(qn("w:eastAsia"))
                    if east_asia:
                        font_config["family"] = east_asia
        except Exception:
            pass

        # 从段落样式继承
        try:
            style = paragraph.style
            if style and style.font:
                if not paragraph.runs:
                    if style.font.name:
                        font_config["family"] = style.font.name
                    if style.font.size:
                        font_config["size_pt"] = _emu_to_pt(style.font.size)
                    if style.font.bold is not None:
                        font_config["bold"] = style.font.bold
        except Exception:
            pass

        return font_config

    def _extract_font_from_table_cell(self, table, row_idx: int, col_idx: int) -> dict:
        """从表格单元格提取字体配置"""
        default_font = {
            "family": "宋体",
            "size_pt": 12,
            "bold": False,
            "italic": False,
            "color_hex": "#000000",
        }

        try:
            cell = table.rows[row_idx].cells[col_idx]
            for paragraph in cell.paragraphs:
                if not paragraph.text.strip():
                    continue
                return self._extract_font_from_paragraph(paragraph)
        except Exception:
            pass

        return default_font

    def _extract_alignment(self, paragraph) -> str:
        """提取对齐方式"""
        try:
            if paragraph.alignment is not None:
                return ALIGNMENT_REVERSE_MAP.get(paragraph.alignment, "left")
        except Exception:
            pass
        return "left"

    def _extract_line_spacing(self, paragraph) -> float:
        """提取行距"""
        try:
            pf = paragraph.paragraph_format
            if pf and pf.line_spacing:
                return float(pf.line_spacing)
        except Exception:
            pass
        return 1.5

    def _extract_spacing(self, paragraph) -> tuple[float, float]:
        """提取段前段后间距 (pt)"""
        space_before = 0.0
        space_after = 0.0
        try:
            pf = paragraph.paragraph_format
            if pf:
                if pf.space_before:
                    space_before = _emu_to_pt(pf.space_before)
                if pf.space_after:
                    space_after = _emu_to_pt(pf.space_after)
        except Exception:
            pass
        return space_before, space_after

    def _extract_first_indent(self, paragraph) -> float:
        """提取首行缩进（字符数）"""
        try:
            pf = paragraph.paragraph_format
            if pf and pf.first_line_indent:
                indent_pt = _emu_to_pt(pf.first_line_indent)
                # 假设正文字号16pt，缩进2字符 = 32pt
                font_size = 16
                for run in paragraph.runs:
                    if run.font.size:
                        font_size = _emu_to_pt(run.font.size)
                        break
                if font_size > 0:
                    return round(indent_pt / font_size, 1)
        except Exception:
            pass
        return 0

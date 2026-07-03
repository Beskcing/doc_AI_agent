"""排版样式配置模型

定义 LLM 输出的 JSON 排版配置的 Pydantic Schema。
所有字段严格对应国标排版规范中的参数。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FontConfig(BaseModel):
    """字体配置"""

    family: str = Field(description="字体名称（西文/ASCII），如 'Times New Roman'、'Arial'")
    east_asia_family: str | None = Field(default=None, description="东亚字体名称，如 '仿宋_GB2312'、'黑体'、'楷体'，None 时与 family 相同")
    size_pt: float = Field(description="字号（磅），如 12、16、22")
    bold: bool = Field(default=False, description="是否加粗")
    italic: bool = Field(default=False, description="是否斜体")
    underline: bool = Field(default=False, description="是否下划线")
    strikethrough: bool = Field(default=False, description="是否删除线")
    color_hex: str = Field(default="#000000", description="字体颜色（十六进制）")


class ParagraphStyleConfig(BaseModel):
    """段落样式配置"""

    font: FontConfig = Field(description="字体配置")
    line_spacing: float = Field(default=1.5, description="行距倍数，如 1.5、2.0")
    line_spacing_pt: float | None = Field(default=None, description="固定行距（磅），设置后忽略 line_spacing")
    line_spacing_rule: Literal["multiple", "exact", "at_least"] = Field(
        default="multiple", description="行距类型：multiple=倍数行距, exact=固定行距, at_least=最小行距"
    )
    space_before_pt: float = Field(default=0, description="段前间距（磅）")
    space_after_pt: float = Field(default=0, description="段后间距（磅）")
    alignment: Literal["left", "center", "right", "justify"] = Field(
        default="left", description="对齐方式"
    )
    first_line_indent_chars: float = Field(
        default=0, description="首行缩进（字符数），如 2 表示缩进两个字符"
    )
    left_indent_cm: float = Field(default=0, description="左缩进（厘米）")
    right_indent_cm: float = Field(default=0, description="右缩进（厘米）")
    keep_together: bool = Field(default=False, description="段中不分页")
    keep_with_next: bool = Field(default=False, description="与下段同页")
    widow_control: bool = Field(default=True, description="孤行控制")


class HeadingStyleConfig(ParagraphStyleConfig):
    """标题样式配置（继承段落样式）"""

    level: int = Field(ge=1, le=6, description="标题层级 1-6")
    numbering_format: str | None = Field(
        default=None, description="编号格式，如 '1.1.1'、'一、'、'(一)'"
    )
    outline_level: int | None = Field(default=None, description="大纲级别（与 level 可能不同）")


class TableStyleConfig(BaseModel):
    """表格样式配置"""

    border_style: Literal["single", "double", "none", "three-line"] = Field(
        default="single", description="边框样式"
    )
    border_width_pt: float = Field(default=0.5, description="边框线宽（磅）")
    border_width_top_pt: float | None = Field(default=None, description="上边框线宽（磅），None 时使用 border_width_pt")
    border_width_bottom_pt: float | None = Field(default=None, description="下边框线宽（磅）")
    border_width_left_pt: float | None = Field(default=None, description="左边框线宽（磅）")
    border_width_right_pt: float | None = Field(default=None, description="右边框线宽（磅）")
    border_width_inside_h_pt: float | None = Field(default=None, description="内部水平边框线宽（磅）")
    border_width_inside_v_pt: float | None = Field(default=None, description="内部垂直边框线宽（磅）")
    header_font: FontConfig = Field(description="表头字体配置")
    body_font: FontConfig = Field(description="表格正文字体配置")
    header_bold: bool = Field(default=True, description="表头是否加粗")
    header_bg_color: str | None = Field(default=None, description="表头背景色（十六进制），None 为无背景")
    header_repeat: bool = Field(default=False, description="表头行是否跨页重复")
    cell_padding_top_pt: float = Field(default=2.0, description="单元格上内边距（磅）")
    cell_padding_bottom_pt: float = Field(default=2.0, description="单元格下内边距（磅）")
    cell_padding_left_pt: float = Field(default=2.0, description="单元格左内边距（磅）")
    cell_padding_right_pt: float = Field(default=2.0, description="单元格右内边距（磅）")
    table_alignment: Literal["left", "center", "right"] = Field(default="left", description="表格对齐方式")
    cell_vertical_alignment: Literal["top", "center", "bottom"] = Field(default="center", description="单元格垂直对齐方式")
    rag_note: str | None = Field(default=None, description="RAG 规范来源备注")


class PageLayoutConfig(BaseModel):
    """页面布局配置"""

    paper_size: Literal["A4", "A3", "B5", "Letter"] = Field(default="A4", description="纸张大小")
    margin_top_cm: float = Field(default=3.7, description="上页边距（厘米）")
    margin_bottom_cm: float = Field(default=3.5, description="下页边距（厘米）")
    margin_left_cm: float = Field(default=2.8, description="左页边距（厘米）")
    margin_right_cm: float = Field(default=2.6, description="右页边距（厘米）")
    header_distance_cm: float = Field(default=1.5, description="页眉距边界（厘米）")
    footer_distance_cm: float = Field(default=1.75, description="页脚距边界（厘米）")
    orientation: Literal["portrait", "landscape"] = Field(default="portrait", description="页面方向")
    gutter_cm: float = Field(default=0, description="装订线宽度（厘米）")
    page_number_format: str | None = Field(default=None, description="页码格式，如 '第X页'、'- X -'")


class StyleConfig(BaseModel):
    """LLM 输出的完整排版配置

    通过 JSON Schema 校验，确保所有样式参数完整且合法。
    """

    page_layout: PageLayoutConfig = Field(default_factory=PageLayoutConfig, description="页面布局")
    heading_styles: list[HeadingStyleConfig] = Field(
        default_factory=list, description="各级标题样式列表"
    )
    body_style: ParagraphStyleConfig = Field(description="正文样式")
    table_style: TableStyleConfig | None = Field(default=None, description="表格样式")
    list_style: ParagraphStyleConfig | None = Field(default=None, description="列表样式")
    footnote_style: ParagraphStyleConfig | None = Field(default=None, description="脚注/尾注样式")
    caption_style: ParagraphStyleConfig | None = Field(default=None, description="图表标题样式")
    header_footer_style: ParagraphStyleConfig | None = Field(default=None, description="页眉页脚样式")
    rag_sources: list[str] = Field(
        default_factory=list,
        description="RAG 检索到的规范文档来源列表，如 ['国标排版规范_v2.0_第3章']",
    )

    def get_heading_style(self, level: int) -> HeadingStyleConfig | None:
        """获取指定层级的标题样式

        Args:
            level: 标题层级 1-6

        Returns:
            对应的 HeadingStyleConfig，未找到返回 None
        """
        for style in self.heading_styles:
            if style.level == level:
                return style
        return None

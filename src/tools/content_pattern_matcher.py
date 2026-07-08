"""国标文档内容模式识别（共享模块）

供 docx_styler 和 docx_style_extractor 共用，
确保样式提取和样式渲染使用一致的段落角色判断逻辑。
"""

from __future__ import annotations

import re

# 标题编号模式（1~5级），从高到低避免误匹配
HEADING_PATTERNS: list[tuple[int, re.Pattern]] = [
    (5, re.compile(r"^\d+\.\d+\.\d+\.\d+\.\d+\s+\S")),
    (4, re.compile(r"^\d+\.\d+\.\d+\.\d+\s+\S")),
    (3, re.compile(r"^\d+\.\d+\.\d+\s+\S")),
    (2, re.compile(r"^\d+\.\d+\s+\S")),
    (1, re.compile(r"^\d+\s+\S")),
]

# 特殊标题（前言、引言等，视为一级标题）
SPECIAL_HEADING_PATTERNS: list[re.Pattern] = [
    re.compile(r"^前言$"),
    re.compile(r"^引言$"),
    re.compile(r"^第[一二三四五六七八九十]+\s*(法|部分|章|节)"),
    re.compile(r"^参考文献$"),
]

# 附录标题模式（附录A / 附录B 等，独立于普通标题因为附录标题通常加粗）
APPENDIX_TITLE_PATTERN: re.Pattern = re.compile(r"^附录\s*[A-Z]")

# 附录内条款模式（A.1 / B.1.1 等）
APPENDIX_CLAUSE_PATTERNS: list[tuple[int, re.Pattern]] = [
    (5, re.compile(r"^[A-Z]\.\d+\.\d+\.\d+\.\d+\s+\S")),
    (4, re.compile(r"^[A-Z]\.\d+\.\d+\.\d+\s+\S")),
    (3, re.compile(r"^[A-Z]\.\d+\.\d+\s+\S")),
    (2, re.compile(r"^[A-Z]\.\d+\s+\S")),
]

# 表格标题模式（表B.1 / 表1 等）
TABLE_CAPTION_PATTERN: re.Pattern = re.compile(r"^表\s*[A-Z]?\.?\d+")

# 图表标题模式（图1 / 图A.1 等）
FIGURE_CAPTION_PATTERN: re.Pattern = re.compile(r"^图\s*\d+")

# 方法标题模式（第一法 / 第二法等）
METHOD_HEADING_PATTERN: re.Pattern = re.compile(r"^第[一二三四五六七八九十百]+法\s")

# 公式模式（LaTeX 或简单公式）
FORMULA_PATTERNS: list[re.Pattern] = [
    re.compile(r"^\$\$"),
    re.compile(r"^[A-Za-z]\s*=\s*"),
]

# 封面标识行
COVER_MARKER_PATTERN: re.Pattern = re.compile(r"中华人民共和国国家标准")

# 国标编号行（GB/T xxxx, GB xxxx 等）
GB_CODE_PATTERN: re.Pattern = re.compile(r"^GB[/T\s]*\d")

# 日期行（含"发布"或"实施"）
DATE_LINE_PATTERN: re.Pattern = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}|发布|实施)")

# 前言标题模式
PREFACE_TITLE_PATTERN: re.Pattern = re.compile(r"^(前\s*言|引\s*言)$")

# 正文标题模式（在 chapter 1 之前的文档标准名称行，如"橄榄油、油橄榄果渣油"）
BODY_TITLE_PATTERN: re.Pattern = re.compile(r"^[\u4e00-\u9fff][\u4e00-\u9fff、，,\s]+")


def classify_paragraph_role(text: str) -> str | None:
    """根据文本内容判断段落角色

    识别国标文档常见的条款编号格式，返回对应的角色字符串。
    注意：附录标题和附录内条款不作为普通标题识别，
    它们有独立的样式（appendix_title_style / appendix_clause_style）。

    Args:
        text: 段落文本（已 strip）

    Returns:
        角色字符串:
        - 'heading_1' ~ 'heading_5': 普通标题
        - 'preface': 前言/引言标题
        - 'appendix_title': 附录标题
        - 'appendix_clause_2' ~ 'appendix_clause_5': 附录内条款
        - 'table_caption': 表格标题
        - None: 非特殊内容（普通正文）
    """
    text = text.strip()
    if not text:
        return None

    # 附录标题（优先级最高，因为附录标题加粗而普通一级标题不加粗）
    if APPENDIX_TITLE_PATTERN.match(text):
        return "appendix_title"

    # 附录内条款
    for level, pattern in APPENDIX_CLAUSE_PATTERNS:
        if pattern.match(text):
            return f"appendix_clause_{level}"

    # 表格标题
    if TABLE_CAPTION_PATTERN.match(text):
        return "table_caption"

    # 图表标题
    if FIGURE_CAPTION_PATTERN.match(text):
        return "figure_caption"

    # 方法标题（第X法）
    if METHOD_HEADING_PATTERN.match(text):
        return "method_heading"

    # 封面标识行
    if COVER_MARKER_PATTERN.search(text):
        return "cover_marker"

    # 特殊标题（前言、引言等）
    for pattern in SPECIAL_HEADING_PATTERNS:
        if pattern.match(text):
            return "preface"

    # 普通编号标题（从高到低匹配）
    for level, pattern in HEADING_PATTERNS:
        if pattern.match(text):
            return f"heading_{level}"

    return None


def classify_heading_level_by_content(text: str) -> int | None:
    """基于内容模式识别标题级别（向后兼容）

    用于文档不使用标准 Heading 样式的后备方案。
    注意：附录标题和附录内条款不在此方法中识别，
    它们有独立的样式。

    Args:
        text: 段落文本（已 strip）

    Returns:
        标题级别 (1-5)，非标题返回 None
    """
    # 附录标题和附录内条款不作为普通标题识别
    if APPENDIX_TITLE_PATTERN.match(text):
        return None
    for _, pattern in APPENDIX_CLAUSE_PATTERNS:
        if pattern.match(text):
            return None
    # 表格标题不作为普通标题
    if TABLE_CAPTION_PATTERN.match(text):
        return None

    # 检查特殊标题
    for pattern in SPECIAL_HEADING_PATTERNS:
        if pattern.match(text):
            return 1

    # 检查编号格式（从高到低，避免误匹配）
    for level, pattern in HEADING_PATTERNS:
        if pattern.match(text):
            return level

    return None

"""HTML 表格 → Markdown 管道表格转换器

Pandoc 的 markdown+raw_html 不会将 HTML 表格转换为 DOCX 原生表格。
需要先将 HTML 表格转为 Markdown 管道表格格式，再通过 Pandoc 转换。
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any


class HTMLTableExtractor(HTMLParser):
    """从 HTML 中提取表格数据为结构化列表"""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[list[str]]]] = []  # [表格][行][列][文本]
        self._current_table: list[list[list[str]]] | None = None
        self._current_row: list[list[str]] | None = None
        self._current_cell: list[str] | None = None
        self._in_cell = False
        self._cell_data: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._current_table = []
        elif tag == "tr":
            if self._current_table is not None:
                self._current_row = []
        elif tag in ("td", "th"):
            if self._current_row is not None:
                self._in_cell = True
                self._cell_data = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
        elif tag == "tr":
            if self._current_table is not None and self._current_row is not None:
                self._current_table.append(self._current_row)
                self._current_row = None
        elif tag in ("td", "th"):
            if self._current_row is not None and self._in_cell:
                self._current_row.append(self._cell_data)
                self._in_cell = False
                self._cell_data = []

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_data.append(data)


def html_table_to_pipe(html_table: str) -> str:
    """将单个 HTML 表格转换为 Markdown 管道表格

    Args:
        html_table: HTML 表格字符串

    Returns:
        Markdown 管道表格字符串
    """
    parser = HTMLTableExtractor()
    parser.feed(html_table)

    if not parser.tables:
        return html_table  # 无法解析，保留原样

    result_lines = []
    for table in parser.tables:
        if not table:
            continue

        # 确定最大列数
        max_cols = max(len(row) for row in table) if table else 0
        if max_cols == 0:
            continue

        # 规范化：确保每行有相同列数
        normalized = []
        for row in table:
            while len(row) < max_cols:
                row.append([""])
            normalized.append(row)

        # 生成管道表格
        for row_idx, row in enumerate(normalized):
            cells = ["".join(cell).strip().replace("\n", " ").replace("|", "\\|") for cell in row]
            result_lines.append("| " + " | ".join(cells) + " |")

            # 表头后添加分隔行
            if row_idx == 0:
                result_lines.append("| " + " | ".join(["---"] * max_cols) + " |")

        result_lines.append("")  # 空行分隔

    return "\n".join(result_lines)


def convert_html_tables_in_markdown(markdown: str) -> str:
    """将 Markdown 中所有 HTML 表格转换为管道表格

    Args:
        markdown: 包含 HTML 表格的 Markdown

    Returns:
        转换后的 Markdown
    """
    table_pattern = re.compile(r"<table[\s>].*?</table>", re.DOTALL | re.IGNORECASE)

    def replace_table(match: re.Match) -> str:
        return html_table_to_pipe(match.group(0))

    return table_pattern.sub(replace_table, markdown)
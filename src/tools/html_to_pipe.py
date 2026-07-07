"""HTML 表格 → Markdown 管道表格转换器

Pandoc 的 markdown+raw_html 不会将 HTML 表格转换为 DOCX 原生表格。
需要先将 HTML 表格转为 Markdown 管道表格格式，再通过 Pandoc 转换。
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class HTMLTableExtractor(HTMLParser):
    """从 HTML 中提取表格数据为结构化列表（支持 colspan/rowspan）"""

    def __init__(self):
        super().__init__()
        self.tables: list[list[list[list[str]]]] = []  # [表格][行][列][文本]
        self._current_table: list[list[list[str]]] | None = None
        self._current_row: list[list[str]] | None = None
        self._current_cell: list[str] | None = None
        self._in_cell = False
        self._cell_data: list[str] = []
        self._cell_colspan = 1
        self._cell_rowspan = 1
        self._rowspan_carry: dict[int, list[tuple[int, list[str]]]] = {}  # {row_offset: [(col, text), ...]}
        self._table_depth = 0  # 支持嵌套表格计数
        self._row_col_idx = 0  # 当前行中下一个实际列索引

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:  # 只处理最外层表格，忽略嵌套
                self._current_table = []
                self._rowspan_carry.clear()
        elif tag == "tr":
            if self._current_table is not None and self._table_depth == 1:
                self._current_row = []
                self._row_col_idx = 0
                # 处理 rowspan 跨行延续
                row_idx = len(self._current_table)
                if row_idx in self._rowspan_carry:
                    for col, cell_data in self._rowspan_carry[row_idx]:
                        while len(self._current_row) < col + 1:
                            self._current_row.append([""])
                        self._current_row[col] = cell_data
                    self._row_col_idx = max(self._row_col_idx, len(self._current_row))
        elif tag in ("td", "th"):
            if self._current_row is not None and self._table_depth == 1:
                self._in_cell = True
                self._cell_data = []
                attrs_dict = dict(attrs)
                self._cell_colspan = int(attrs_dict.get("colspan", 1))
                self._cell_rowspan = int(attrs_dict.get("rowspan", 1))

    def handle_endtag(self, tag: str) -> None:
        if tag == "table":
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
                self._rowspan_carry.clear()
            self._table_depth -= 1
        elif tag == "tr":
            if self._current_table is not None and self._current_row is not None and self._table_depth == 1:
                self._current_table.append(self._current_row)
                self._current_row = None
        elif tag in ("td", "th"):
            if self._current_row is not None and self._in_cell and self._table_depth == 1:
                cell_text = [d.strip() for d in self._cell_data]
                cell_text_str = " ".join(d for d in cell_text if d)
                # 跳过 rowspan 填充列
                while len(self._current_row) < self._row_col_idx:
                    self._current_row.append([""])
                # 按 colspan 展开单元格
                for c in range(self._cell_colspan):
                    self._current_row.append([cell_text_str] if c == 0 else [""])
                # 记录 rowspan（后续行需填充）
                if self._cell_rowspan > 1:
                    row_idx = len(self._current_table)
                    for offset in range(1, self._cell_rowspan):
                        target_row = row_idx + offset
                        if target_row not in self._rowspan_carry:
                            self._rowspan_carry[target_row] = []
                        self._rowspan_carry[target_row].append((self._row_col_idx, [cell_text_str]))
                self._row_col_idx += self._cell_colspan
                self._in_cell = False
                self._cell_data = []
                self._cell_colspan = 1
                self._cell_rowspan = 1

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

"""HTML 表格结构保护工具

在处理管线中保护 HTML 表格不被 LLM 或正则操作破坏。
使用占位符机制：将 HTML 表格替换为唯一占位符，处理完成后恢复。
"""

from __future__ import annotations

import re
from typing import ClassVar

from src.utils.logger import get_logger

logger = get_logger(__name__)


class HTMLTablePreserver:
    """HTML 表格占位符保护器"""

    # 占位符格式：<!-- TABLE_PLACEHOLDER_{index} -->
    PLACEHOLDER_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"<!--\s*TABLE_PLACEHOLDER_(\d+)\s*-->"
    )
    PLACEHOLDER_TEMPLATE: ClassVar[str] = "<!-- TABLE_PLACEHOLDER_{} -->"

    # HTML 表格匹配模式（支持嵌套表格）
    TABLE_PATTERN: ClassVar[re.Pattern] = re.compile(
        r"<table[\s>].*?</table>",
        re.DOTALL | re.IGNORECASE,
    )

    def protect(self, markdown: str) -> tuple[str, dict[str, str]]:
        """将 HTML 表格替换为占位符

        Args:
            markdown: 包含 HTML 表格的 Markdown 文本

        Returns:
            (处理后的文本, 占位符映射 {占位符: 原始表格HTML})
        """
        placeholder_map: dict[str, str] = {}
        tables = self.TABLE_PATTERN.findall(markdown)

        if not tables:
            logger.debug("未发现 HTML 表格，跳过保护")
            return markdown, placeholder_map

        result = markdown
        for idx, table_html in enumerate(tables):
            placeholder = self.PLACEHOLDER_TEMPLATE.format(idx)
            placeholder_map[placeholder] = table_html
            # 只替换第一次出现的相同表格（避免重复替换）
            result = result.replace(table_html, placeholder, 1)

        logger.info("已保护 %d 个 HTML 表格", len(placeholder_map))
        return result, placeholder_map

    def restore(self, text: str, placeholder_map: dict[str, str]) -> str:
        """将占位符恢复为原始 HTML 表格

        Args:
            text: 包含占位符的文本
            placeholder_map: 占位符映射 {占位符: 原始表格HTML}

        Returns:
            恢复后的文本
        """
        if not placeholder_map:
            return text

        result = text
        restored_count = 0
        for placeholder, table_html in placeholder_map.items():
            if placeholder in result:
                result = result.replace(placeholder, table_html)
                restored_count += 1

        logger.info("已恢复 %d/%d 个 HTML 表格", restored_count, len(placeholder_map))

        if restored_count < len(placeholder_map):
            missing = set(placeholder_map.keys()) - set(
                p for p in placeholder_map if p not in result
            )
            logger.warning("有 %d 个表格占位符未在文本中找到", len(placeholder_map) - restored_count)

        return result

    def validate_table_integrity(self, html_table: str) -> tuple[bool, list[str]]:
        """校验 HTML 表格结构完整性

        检查项:
        - <table> 和 </table> 标签配对
        - <tr> 和 </tr> 标签配对
        - <td>/<th> 和 </td>/</th> 标签配对

        Args:
            html_table: HTML 表格字符串

        Returns:
            (是否完整, 问题描述列表)
        """
        issues: list[str] = []
        html_lower = html_table.lower()

        # 检查 table 标签
        table_open = html_lower.count("<table")
        table_close = html_lower.count("</table>")
        if table_open != table_close:
            issues.append(f"<table> 标签不匹配: 开 {table_open} 个, 闭 {table_close} 个")

        # 检查 tr 标签
        tr_open = html_lower.count("<tr")
        tr_close = html_lower.count("</tr>")
        if tr_open != tr_close:
            issues.append(f"<tr> 标签不匹配: 开 {tr_open} 个, 闭 {tr_close} 个")

        # 检查 td 标签
        td_open = html_lower.count("<td")
        td_close = html_lower.count("</td>")
        if td_open != td_close:
            issues.append(f"<td> 标签不匹配: 开 {td_open} 个, 闭 {td_close} 个")

        # 检查 th 标签
        th_open = html_lower.count("<th")
        th_close = html_lower.count("</th>")
        if th_open != th_close:
            issues.append(f"<th> 标签不匹配: 开 {th_open} 个, 闭 {th_close} 个")

        is_valid = len(issues) == 0
        return is_valid, issues

    def find_unprotected_tables(self, markdown: str) -> list[str]:
        """查找文本中未被保护的 HTML 表格

        Args:
            markdown: Markdown 文本

        Returns:
            未保护的 HTML 表格列表
        """
        return self.TABLE_PATTERN.findall(markdown)

    def count_tables(self, markdown: str) -> int:
        """统计文本中的 HTML 表格数量

        Args:
            markdown: Markdown 文本

        Returns:
            表格数量
        """
        return len(self.TABLE_PATTERN.findall(markdown))

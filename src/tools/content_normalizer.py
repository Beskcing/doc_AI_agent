"""Markdown 内容规整工具

从 .qoder/skills/gbt/scripts/format_gbt.py 提取的核心内容规整逻辑，
在 Markdown 文本层执行（Pandoc 转换前），避免直接操作 DOCX XML。

包含：
- 日期行合并（2022-06-30发布 + 2022-12-30实施 → 一行）
- 拆分标题合并（3.1.1 + 白兰地 brandy → 3.1.1  白兰地 brandy）
- 附录标题合并（附录 A + 培养基和试剂 → 附录 A  培养基和试剂）
- 目次/目录删除
- 标题编号后双空格规范化
- 正文多余空格规整
"""

from __future__ import annotations

import re

from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContentNormalizer:
    """Markdown 内容规整器

    在 Pandoc 转换前对 Markdown 文本执行结构性修正，
    解决 MinerU 解析产生的标题拆分、日期分列等问题。
    """

    def __init__(self) -> None:
        self._changes: list[str] = []

    @property
    def changes(self) -> list[str]:
        """获取本次规整的变更日志"""
        return self._changes

    def normalize(self, markdown: str) -> str:
        """执行全部规整操作

        Args:
            markdown: 原始 Markdown 文本

        Returns:
            规整后的 Markdown 文本
        """
        self._changes = []
        result = markdown

        # 1. 日期行合并（必须在其他操作之前，避免日期被错误归类）
        result = self._merge_date_lines(result)

        # 2. 拆分标题合并（附录标题 + 编号标题）
        result = self._merge_split_headings(result)

        # 3. 目次/目录删除
        result = self._remove_toc(result)

        # 4. 标题编号后双空格规范化
        result = self._fix_heading_spaces(result)

        logger.info("内容规整完成，共 %d 处更改", len(self._changes))
        return result

    # =========================================================================
    # 日期行合并
    # =========================================================================

    def _merge_date_lines(self, text: str) -> str:
        """合并被 MinerU 拆分的日期行

        MinerU 常将 '2022-06-30发布' 和 '2022-12-30实施' 解析为两行，
        将它们合并为 '2022-06-30发布 2022-12-30实施'。
        """
        lines = text.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            # 检查当前行是否以 "发布" 结尾（不含日期）
            is_pub_line = line.strip().endswith("发布") and not re.search(r"\d{4}[-/]\d{2}[-/]\d{2}发布", line)
            # 检查是否有下一行且以 "实施" 结尾
            if is_pub_line and i + 1 < len(lines):
                next_line = lines[i + 1]
                is_impl_line = next_line.strip().endswith("实施") and not re.search(
                    r"\d{4}[-/]\d{2}[-/]\d{2}实施", next_line
                )
                if is_impl_line:
                    pub_date = line.strip().replace("发布", "").strip()
                    impl_date = next_line.strip().replace("实施", "").strip()
                    merged = f"{pub_date}发布 {impl_date}实施"
                    # 保持原行的缩进
                    indent = line[: len(line) - len(line.lstrip())] if line else ""
                    result.append(indent + merged)
                    self._changes.append(f"合并日期行: '{line.strip()}' + '{next_line.strip()}' → '{merged}'")
                    i += 2
                    continue

            # 检查是否有完整的日期行格式（YYYY-MM-DD发布）
            date_pub_match = re.match(r"^(\d{4}[-/]\d{2}[-/]\d{2})发布$", line.strip())
            if date_pub_match and i + 1 < len(lines):
                next_line = lines[i + 1]
                date_impl_match = re.match(r"^(\d{4}[-/]\d{2}[-/]\d{2})实施$", next_line.strip())
                if date_impl_match:
                    merged = f"{date_pub_match.group(1)}发布 {date_impl_match.group(1)}实施"
                    result.append(merged)
                    self._changes.append(f"合并日期行: '{line.strip()}' + '{next_line.strip()}' → '{merged}'")
                    i += 2
                    continue

            result.append(line)
            i += 1

        return "\n".join(result)

    # =========================================================================
    # 拆分标题合并
    # =========================================================================

    def _merge_split_headings(self, text: str) -> str:
        """合并被 MinerU 拆分的标题行

        处理两种拆分情况：
        1. 附录标题拆分：'附录 A' + '培养基和试剂' → '附录 A  培养基和试剂'
        2. 编号标题拆分：'3.1.1' + '白兰地 brandy' → '3.1.1  白兰地 brandy'
        """
        lines = text.split("\n")
        result: list[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            should_merge = False

            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()

                # 情况 1：附录标题拆分（附录 A 后跟描述性文本）
                if re.match(r"^附录\s*[A-Z]$", stripped) and next_stripped:
                    if not next_stripped.startswith("附录") and not re.match(r"^\d+\s+", next_stripped):
                        should_merge = True

                # 情况 2：编号标题拆分（如 3.1.1 后跟描述性文本）
                elif re.match(r"^(\d+(\.\d+)*|[A-Z]\.\d+(\.\d+)*)$", stripped) and next_stripped:
                    if not re.match(r"^(\d+(\.\d+)*|[A-Z]\.\d+)", next_stripped) and not next_stripped.startswith(
                        "附录"
                    ):
                        should_merge = True

            if should_merge and i + 1 < len(lines):
                next_line = lines[i + 1]
                next_stripped = next_line.strip()
                merged = f"{stripped}  {next_stripped}"
                # 保持原行缩进
                indent = line[: len(line) - len(line.lstrip())] if line else ""
                result.append(indent + merged)
                self._changes.append(f"合并拆分标题: '{stripped}' + '{next_stripped}' → '{merged}'")
                i += 2
                continue

            result.append(line)
            i += 1

        return "\n".join(result)

    # =========================================================================
    # 目次/目录删除
    # =========================================================================

    def _remove_toc(self, text: str) -> str:
        """检测并删除目次/目录区域

        找到 '目次' 或 '目录'（支持 Markdown 标题格式如 '## 目次'），
        删除它到 '前言' 之间的所有内容。
        """
        lines = text.split("\n")
        result: list[str] = []
        in_toc = False
        removed_count = 0

        for line in lines:
            stripped = line.strip()

            # 检测 TOC 开始（支持 Markdown 标题前缀如 ## 目次、# 目次 等）
            toc_stripped = re.sub(r"^#+\s*", "", stripped)  # 去掉 Markdown ## 前缀
            if not in_toc and toc_stripped in ("目  次", "目次", "目  录", "目录"):
                in_toc = True
                removed_count += 1
                self._changes.append(f"删除 TOC 起始行: '{stripped}'")
                continue

            # 检测 TOC 结束
            if in_toc:
                removed_count += 1
                # 去掉 Markdown 前缀后检查"前言"
                preface_stripped = re.sub(r"^#+\s*", "", stripped)
                if preface_stripped.startswith("前") and "言" in preface_stripped:
                    in_toc = False
                    result.append(line)
                    removed_count -= 1
                    continue
                # 检查是否已经到了正文标题（1  xxx）
                if re.match(r"^1\s{2,}\S", stripped):
                    in_toc = False
                    result.append(line)
                    removed_count -= 1
                    continue
                # 跳过 TOC 内的空行也跳过（但不计数避免混淆）
                if not stripped:
                    continue
                continue

            result.append(line)

        if removed_count > 0:
            self._changes.append(f"删除 TOC 区域共 {removed_count} 行")
        return "\n".join(result)

    # =========================================================================
    # 标题双空格规范化
    # =========================================================================

    def _fix_heading_spaces(self, text: str) -> str:
        """确保标题编号后有且只有两个空格

        将 '1 范围' 修正为 '1  范围'，'3.1 分析天平' 修正为 '3.1  分析天平'。
        """
        lines = text.split("\n")
        result: list[str] = []

        for line in lines:
            stripped = line.strip()
            # 匹配编号标题：数字.数字... 后跟空格和中文文本
            match = re.match(r"^(\d+(?:\.\d+)*)(\s+)([\u4e00-\u9fff].*)$", stripped)
            if match:
                num = match.group(1)
                rest = match.group(3)
                current_spaces = match.group(2)
                if current_spaces != "  ":
                    new_text = f"{num}  {rest}"
                    # 保持缩进
                    indent = line[: len(line) - len(line.lstrip())] if line else ""
                    result.append(indent + new_text)
                    self._changes.append(f"修正标题空格: '{stripped}' → '{new_text}'")
                    continue

            result.append(line)

        return "\n".join(result)

    # =========================================================================
    # 独立方法（可按需单独调用）
    # =========================================================================

    @staticmethod
    def merge_date_lines_only(markdown: str) -> str:
        """仅执行日期行合并"""
        normalizer = ContentNormalizer()
        return normalizer._merge_date_lines(markdown)

    @staticmethod
    def merge_split_headings_only(markdown: str) -> str:
        """仅执行拆分标题合并"""
        normalizer = ContentNormalizer()
        return normalizer._merge_split_headings(markdown)

    @staticmethod
    def remove_toc_only(markdown: str) -> str:
        """仅执行目次删除"""
        normalizer = ContentNormalizer()
        return normalizer._remove_toc(markdown)

    @staticmethod
    def fix_heading_spaces_only(markdown: str) -> str:
        """仅执行标题双空格修正"""
        normalizer = ContentNormalizer()
        return normalizer._fix_heading_spaces(markdown)

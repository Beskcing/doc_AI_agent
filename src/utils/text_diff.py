"""文本差异对比工具

对比原始 Markdown 文本与 DOCX 提取文本，识别差异块，
用于排版后审查的增量 LLM 分析（只审查变化部分）。

输出 DiffBlock 列表，每块包含：
- type: added / removed / modified / unchanged
- md_lines: 原始 MD 文本行
- docx_lines: DOCX 提取文本行
- md_start / md_end / docx_start / docx_end: 行号范围
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from src.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DiffBlock:
    """单个差异块"""

    type: str  # added / removed / modified / unchanged
    md_lines: list[str] = field(default_factory=list)
    docx_lines: list[str] = field(default_factory=list)
    md_start: int = 0
    md_end: int = 0
    docx_start: int = 0
    docx_end: int = 0

    @property
    def md_text(self) -> str:
        """获取 MD 侧文本"""
        return "\n".join(self.md_lines)

    @property
    def docx_text(self) -> str:
        """获取 DOCX 侧文本"""
        return "\n".join(self.docx_lines)

    @property
    def line_count(self) -> int:
        """差异涉及的总行数"""
        return max(len(self.md_lines), len(self.docx_lines))


@dataclass
class DiffResult:
    """差异对比结果"""

    blocks: list[DiffBlock] = field(default_factory=list)
    total_added: int = 0
    total_removed: int = 0
    total_modified: int = 0
    total_unchanged: int = 0

    @property
    def changed_blocks(self) -> list[DiffBlock]:
        """获取所有变化块（排除 unchanged）"""
        return [b for b in self.blocks if b.type != "unchanged"]

    @property
    def has_changes(self) -> bool:
        """是否有任何变化"""
        return self.total_added > 0 or self.total_removed > 0 or self.total_modified > 0


def compute_diff(md_text: str, docx_text: str, context_lines: int = 2) -> DiffResult:
    """对比 MD 文本和 DOCX 文本的差异

    使用 difflib.SequenceMatcher 按行对比，生成结构化的差异块。
    相邻的同类型块会合并，避免碎片化。

    Args:
        md_text: 原始 cleaned_markdown 文本
        docx_text: DOCX 提取的文本
        context_lines: 变化块前后保留的上下文行数（默认 2）

    Returns:
        DiffResult 差异对比结果
    """
    md_lines = md_text.splitlines()
    docx_lines = docx_text.splitlines()

    if not md_lines and not docx_lines:
        return DiffResult()

    # 使用 SequenceMatcher 获取操作码
    matcher = difflib.SequenceMatcher(None, md_lines, docx_lines)
    opcodes = matcher.get_opcodes()

    blocks: list[DiffBlock] = []
    stats = {"added": 0, "removed": 0, "modified": 0, "unchanged": 0}

    for tag, i1, i2, j1, j2 in opcodes:
        if tag == "equal":
            # 上下文处理：只在前后有变化时才保留少量上下文行
            block = DiffBlock(
                type="unchanged",
                md_lines=md_lines[i1:i2],
                docx_lines=docx_lines[j1:j2],
                md_start=i1,
                md_end=i2,
                docx_start=j1,
                docx_end=j2,
            )
            blocks.append(block)
            stats["unchanged"] += 1
        elif tag == "replace":
            block = DiffBlock(
                type="modified",
                md_lines=md_lines[i1:i2],
                docx_lines=docx_lines[j1:j2],
                md_start=i1,
                md_end=i2,
                docx_start=j1,
                docx_end=j2,
            )
            blocks.append(block)
            stats["modified"] += 1
        elif tag == "delete":
            block = DiffBlock(
                type="removed",
                md_lines=md_lines[i1:i2],
                docx_lines=[],
                md_start=i1,
                md_end=i2,
                docx_start=j1,
                docx_end=j1,
            )
            blocks.append(block)
            stats["removed"] += 1
        elif tag == "insert":
            block = DiffBlock(
                type="added",
                md_lines=[],
                docx_lines=docx_lines[j1:j2],
                md_start=i1,
                md_end=i1,
                docx_start=j1,
                docx_end=j2,
            )
            blocks.append(block)
            stats["added"] += 1

    # 合并相邻的同类型变化块
    merged_blocks = _merge_adjacent_blocks(blocks)

    result = DiffResult(
        blocks=merged_blocks,
        total_added=stats["added"],
        total_removed=stats["removed"],
        total_modified=stats["modified"],
        total_unchanged=stats["unchanged"],
    )

    logger.info(
        "文本差异对比完成: +%d -%d ~%d =%d, 共 %d 块",
        result.total_added,
        result.total_removed,
        result.total_modified,
        result.total_unchanged,
        len(result.blocks),
    )
    return result


def _merge_adjacent_blocks(blocks: list[DiffBlock]) -> list[DiffBlock]:
    """合并相邻的同类型变化块

    将相邻的同类型非 unchanged 块合并为一个，减少碎片化。
    """
    if len(blocks) <= 1:
        return blocks

    merged: list[DiffBlock] = []
    current = blocks[0]

    for i in range(1, len(blocks)):
        nxt = blocks[i]

        # 跳过连续的 unchanged 块之间的合并
        if current.type == "unchanged" and nxt.type == "unchanged":
            # 合并为一个大 unchanged 块
            current.md_lines.extend(nxt.md_lines)
            current.docx_lines.extend(nxt.docx_lines)
            current.md_end = nxt.md_end
            current.docx_end = nxt.docx_end
            continue

        # 合并同类型的变化块（added+added, removed+removed, modified+modified）
        if current.type == nxt.type and current.type != "unchanged":
            current.md_lines.extend(nxt.md_lines)
            current.docx_lines.extend(nxt.docx_lines)
            current.md_end = nxt.md_end or current.md_end
            current.docx_end = nxt.docx_end or current.docx_end
            continue

        merged.append(current)
        current = nxt

    merged.append(current)
    return merged


def get_changed_text(diff_result: DiffResult, side: str = "docx") -> str:
    """提取差异结果中变化部分的文本

    Args:
        diff_result: 差异对比结果
        side: 提取哪一侧的文本 ("md" 或 "docx")

    Returns:
        变化部分的文本（合并为一个字符串）
    """
    lines: list[str] = []
    for block in diff_result.changed_blocks:
        source = block.docx_lines if side == "docx" else block.md_lines
        if source:
            # 添加位置标记
            location = (
                f"DOCX行{block.docx_start}-{block.docx_end}"
                if side == "docx"
                else f"MD行{block.md_start}-{block.md_end}"
            )
            lines.append(f"<!-- {block.type} @ {location} -->")
            lines.extend(source)
            lines.append("")
    return "\n".join(lines)


def get_unchanged_ranges(diff_result: DiffResult, max_chars: int = 8000) -> list[str]:
    """将未变化部分按最大字符数分块，用于 LLM 上下文

    Args:
        diff_result: 差异对比结果
        max_chars: 每块最大字符数

    Returns:
        分块后的未变化文本列表
    """
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_len = 0

    for block in diff_result.blocks:
        if block.type != "unchanged":
            continue
        text = block.docx_text
        text_len = len(text)

        if current_len + text_len > max_chars and current_chunk:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            current_len = 0

        current_chunk.append(text)
        current_len += text_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks

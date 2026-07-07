"""Markdown 内容审查与清洗工具

两阶段清洗：
1. pre_clean: 规则化预处理（不调用 LLM），修复常见 OCR 错误
2. llm_review: LLM 智能审查，识别语义级问题

关键约束：
- 保留 HTML 表格结构，不转换为 Markdown 管道语法
- LaTeX 严重破损时保留图片引用 [FORMULA_IMAGE]
- 失效图片使用 [IMAGE_MISSING] 占位
- 不可修复的 OCR 错误标记 [⚠️ OCR_ERROR: 需人工核对]
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from src.models.document_schema import CleaningResult, IntentAnalysis
from src.tools.html_table_preserver import HTMLTablePreserver
from src.utils.logger import get_logger

if TYPE_CHECKING:
    from src.llm_client import LLMClient

logger = get_logger(__name__)


class MarkdownCleaner:
    """Markdown 两阶段清洗器"""

    # OCR 错误标记
    OCR_ERROR_MARK = "[⚠️ OCR_ERROR: 需人工核对]"
    FORMULA_IMAGE_MARK = "[FORMULA_IMAGE]"
    IMAGE_MISSING_MARK = "[IMAGE_MISSING]"

    def __init__(self, llm_client: LLMClient | None = None, base_dir: str | Path | None = None):
        """初始化清洗器

        Args:
            llm_client: LLM 客户端（用于第二阶段智能审查），可为 None 跳过 LLM 审查
            base_dir: 图片路径的基准目录
        """
        self.llm_client = llm_client
        self.base_dir = Path(base_dir) if base_dir else None
        self._table_preserver = HTMLTablePreserver()

    def clean(self, markdown: str, context: IntentAnalysis | None = None) -> CleaningResult:
        """完整清洗流程

        Args:
            markdown: 原始 Markdown 文本
            context: 文档意图分析结果（可选）

        Returns:
            CleaningResult 清洗结果
        """
        logger.info("开始 Markdown 清洗（原文 %d 字节）", len(markdown))

        # 保护 HTML 表格
        protected_md, table_map = self._table_preserver.protect(markdown)

        # 第一阶段：规则化预处理
        pre_cleaned, pre_log = self.pre_clean(protected_md)

        # 第二阶段：LLM 智能审查（如果有 LLM 客户端）
        if self.llm_client and context:
            llm_result = self.llm_review(pre_cleaned, context)
            cleaned = llm_result.cleaned_markdown
            llm_log = llm_result.changes_log
            ocr_errors = llm_result.ocr_errors_marked
        else:
            cleaned = pre_cleaned
            llm_log = []
            ocr_errors = 0

        # 恢复 HTML 表格
        cleaned = self._table_preserver.restore(cleaned, table_map)

        # 统计信息
        images_missing = cleaned.count(self.IMAGE_MISSING_MARK)
        formulas_preserved = cleaned.count(self.FORMULA_IMAGE_MARK)

        result = CleaningResult(
            cleaned_markdown=cleaned,
            changes_log=pre_log + llm_log,
            ocr_issues_found=len(pre_log) + ocr_errors,
            ocr_errors_marked=ocr_errors,
            images_missing=images_missing,
            formulas_preserved=formulas_preserved,
        )

        logger.info(
            "清洗完成: %d 处修改, %d 个 OCR 错误标记, %d 个缺失图片",
            len(result.changes_log),
            result.ocr_errors_marked,
            result.images_missing,
        )
        return result

    def pre_clean(self, markdown: str) -> tuple[str, list[str]]:
        """规则化预处理（不调用 LLM）

        清洗项:
        1. 全角数字/字母转半角
        2. 连续空格合并（保留标题和代码块内的）
        3. OCR 断行修复
        4. 标题格式统一
        5. LaTeX 公式检查与修复
        6. 图片路径校验
        7. 乱码字符清理

        Args:
            markdown: 待清洗的 Markdown 文本

        Returns:
            (处理后文本, 变更日志)
        """
        changes: list[str] = []
        result = markdown

        # 1. 全角转半角
        result, count = self._fullwidth_to_halfwidth(result)
        if count:
            changes.append(f"全角字符转半角: {count} 处")

        # 2. 连续空格清理（保留代码块和标题）
        result, count = self._clean_extra_spaces(result)
        if count:
            changes.append(f"多余空格清理: {count} 处")

        # 3. OCR 断行修复
        result, count = self._fix_ocr_line_breaks(result)
        if count:
            changes.append(f"OCR 断行修复: {count} 处")

        # 4. 标题格式统一
        result, count = self._normalize_headings(result)
        if count:
            changes.append(f"标题格式统一: {count} 处")

        # 5. LaTeX 公式检查与修复
        result, count = self._fix_latex_formulas(result)
        if count:
            changes.append(f"LaTeX 公式修复: {count} 处")

        # 6. 图片路径校验
        result, count = self._validate_image_paths(result)
        if count:
            changes.append(f"图片路径校验: {count} 个失效图片")

        # 7. 乱码字符清理
        result, count = self._clean_garbled_chars(result)
        if count:
            changes.append(f"乱码字符清理: {count} 处")

        # 8. Markdown 列表格式修复
        result, count = self._fix_list_format(result)
        if count:
            changes.append(f"列表格式修复: {count} 处")

        return result, changes

    # LLM 审查的最大文本长度（字符），超过此长度跳过 LLM 审查
    # 避免 LLM 输出截断导致表格占位符等内容丢失
    LLM_REVIEW_MAX_CHARS: int = 15000

    def llm_review(self, markdown: str, context: IntentAnalysis) -> CleaningResult:
        """LLM 智能审查

        识别语义级别的 OCR 错误：
        - 专业术语识别错误
        - 内容连贯性问题
        - 需要人工确认的问题标记

        对于超长文档（超过 LLM_REVIEW_MAX_CHARS），跳过 LLM 审查，
        仅使用规则预处理结果，避免 LLM 输出截断导致表格占位符等内容丢失。

        Args:
            markdown: 预处理后的 Markdown
            context: 文档意图分析

        Returns:
            CleaningResult
        """
        if not self.llm_client:
            return CleaningResult(cleaned_markdown=markdown)

        total_len = len(markdown)

        # 超长文档：启用分段 LLM 审查，而非直接跳过
        if total_len > self.LLM_REVIEW_MAX_CHARS:
            logger.info(
                "文档较长 (%d 字符 > %d)，启用分段 LLM 审查",
                total_len, self.LLM_REVIEW_MAX_CHARS,
            )
            return self._llm_review_chunked(markdown, context)

        # 包含表格占位符时跳过 LLM 审查，避免 LLM 修改占位符导致表格恢复失败
        if "@@TABLE_PLACEHOLDER_" in markdown:
            placeholder_count = markdown.count("@@TABLE_PLACEHOLDER_")
            logger.warning(
                "文本包含 %d 个表格占位符，跳过 LLM 审查以保护表格结构",
                placeholder_count,
            )
            return CleaningResult(
                cleaned_markdown=markdown,
                changes_log=[f"包含 {placeholder_count} 个表格占位符，跳过 LLM 审查"],
            )

        prompt = self._build_review_prompt(markdown, context)

        try:
            response = self.llm_client.invoke(prompt).content
            # 从 LLM 响应中提取清洗后的 Markdown
            cleaned = self._extract_cleaned_markdown(response)
            marked_count = cleaned.count(self.OCR_ERROR_MARK)

            return CleaningResult(
                cleaned_markdown=cleaned,
                changes_log=[f"LLM 审查完成（{total_len} 字符），标记 {marked_count} 个需人工核对项"],
                ocr_errors_marked=marked_count,
            )
        except Exception as e:
            logger.warning("LLM 审查失败，使用预处理结果: %s", e)
            return CleaningResult(cleaned_markdown=markdown)

    # ==================== 分段 LLM 审查 ====================

    def _split_by_sections(self, markdown: str, max_chunk_size: int = 12000) -> list[str]:
        """按章节边界将 Markdown 分块

        优先在标题行（# 开头）处分割，每个块不超过 max_chunk_size。

        Args:
            markdown: 待分块的 Markdown 文本
            max_chunk_size: 单块最大字符数

        Returns:
            分块后的文本列表
        """
        lines = markdown.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            # 在标题行处分块（且当前块已有内容）
            if line.strip().startswith("#") and current and current_len > max_chunk_size:
                chunks.append("\n".join(current))
                current = []
                current_len = 0
            current.append(line)
            current_len += line_len

        if current:
            chunks.append("\n".join(current))

        # 如果某个块仍然过大，按行硬切
        final_chunks: list[str] = []
        for chunk in chunks:
            if len(chunk) > max_chunk_size * 1.5:
                # 按行拼接直到接近 max_chunk_size
                chunk_lines = chunk.splitlines()
                sub: list[str] = []
                sub_len = 0
                for cl in chunk_lines:
                    cl_len = len(cl) + 1
                    if sub and sub_len + cl_len > max_chunk_size:
                        final_chunks.append("\n".join(sub))
                        sub = []
                        sub_len = 0
                    sub.append(cl)
                    sub_len += cl_len
                if sub:
                    final_chunks.append("\n".join(sub))
            else:
                final_chunks.append(chunk)

        return final_chunks

    def _llm_review_chunked(self, markdown: str, context: IntentAnalysis) -> CleaningResult:
        """分段 LLM 审查：按章节边界分块，逐块送 LLM 审查，最后合并"""
        chunks = self._split_by_sections(markdown, max_chunk_size=12000)
        reviewed_parts: list[str] = []
        total_changes = 0
        total_errors = 0

        for i, chunk in enumerate(chunks):
            # 包含表格占位符的块跳过 LLM 审查
            if "@@TABLE_PLACEHOLDER_" in chunk:
                reviewed_parts.append(chunk)
                logger.info("分段审查 [%d/%d]: 跳过（含表格占位符）", i + 1, len(chunks))
                continue
            # 过短的块跳过
            if len(chunk) < 50:
                reviewed_parts.append(chunk)
                continue

            result = self._review_single_chunk(chunk, context)
            reviewed_parts.append(result.cleaned_markdown)
            total_changes += len(result.changes_log)
            total_errors += result.ocr_errors_marked
            logger.info("分段审查 [%d/%d]: %d 字符", i + 1, len(chunks), len(chunk))

        return CleaningResult(
            cleaned_markdown="\n".join(reviewed_parts),
            changes_log=[f"分段LLM审查完成（{len(chunks)}段），{total_changes}处修改"],
            ocr_errors_marked=total_errors,
        )

    def _review_single_chunk(self, chunk: str, context: IntentAnalysis) -> CleaningResult:
        """审查单个文本块"""
        prompt = self._build_review_prompt(chunk, context)
        try:
            response = self.llm_client.invoke(prompt).content
            cleaned = self._extract_cleaned_markdown(response)
            marked_count = cleaned.count(self.OCR_ERROR_MARK)
            return CleaningResult(
                cleaned_markdown=cleaned,
                changes_log=[f"LLM 审查完成（{len(chunk)} 字符），标记 {marked_count} 个需人工核对项"],
                ocr_errors_marked=marked_count,
            )
        except Exception as e:
            logger.warning("单块 LLM 审查失败: %s", e)
            return CleaningResult(cleaned_markdown=chunk)

    # ==================== 规则化清洗方法 ====================

    def _fullwidth_to_halfwidth(self, text: str) -> tuple[str, int]:
        """全角数字和英文字母转半角

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 替换次数)
        """
        count = 0
        result = []
        for char in text:
            code = ord(char)
            # 全角数字 0-9: 0xFF10-0xFF19
            # 全角大写 A-Z: 0xFF21-0xFF3A
            # 全角小写 a-z: 0xFF41-0xFF5A
            if 0xFF10 <= code <= 0xFF19 or 0xFF21 <= code <= 0xFF3A or 0xFF41 <= code <= 0xFF5A:
                result.append(chr(code - 0xFEE0))
                count += 1
            # 全角括号 () → 半角（代码中常见，保留转换）
            elif code == 0xFF08:  # （
                result.append("(")
                count += 1
            elif code == 0xFF09:  # ）
                result.append(")")
                count += 1
            # 全角标点（中文逗号、冒号、分号）保留不转换，国标文档要求全角标点
            else:
                result.append(char)
        return "".join(result), count

    def _clean_extra_spaces(self, text: str) -> tuple[str, int]:
        """清理多余空格（保护代码块和标题行）

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 替换次数)
        """
        count = 0
        lines = text.splitlines()
        result_lines = []
        in_code_block = False

        for line in lines:
            # 跟踪代码块状态
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                result_lines.append(line)
                continue

            if in_code_block:
                result_lines.append(line)
                continue

            # 标题行只修复 # 后无空格的情况
            if line.strip().startswith("#"):
                result_lines.append(line)
                continue

            # 正文行：多个空格合并为一个（保留行首缩进）
            stripped = line.lstrip()
            indent = line[: len(line) - len(stripped)]
            new_stripped = re.sub(r" {2,}", " ", stripped)
            if new_stripped != stripped:
                count += 1
            result_lines.append(indent + new_stripped)

        return "\n".join(result_lines), count

    def _fix_ocr_line_breaks(self, text: str) -> tuple[str, int]:
        """修复 OCR 断行错误

        规则：如果一行不以句号/问号/感叹号结尾，且下一行不以标题/列表/表格开头，
        则将两行合并（修复被截断的段落）。

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 修复次数)
        """
        count = 0
        lines = text.splitlines()
        result_lines: list[str] = []
        in_code_block = False

        i = 0
        while i < len(lines):
            line = lines[i]

            # 跟踪代码块
            if line.strip().startswith("```"):
                in_code_block = not in_code_block
                result_lines.append(line)
                i += 1
                continue

            if in_code_block or not line.strip():
                result_lines.append(line)
                i += 1
                continue

            # 判断是否需要与下一行合并
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                # 当前行不以结束标点结尾
                ends_with_punct = line.rstrip().endswith(("。", "？", "！", ".", "?", "!", ":", "：", ";", "；"))
                # 下一行不是特殊格式
                next_is_special = (
                    not next_line.strip()
                    or next_line.strip().startswith(("#", "-", "*", "+", ">", "|", "<"))
                    or re.match(r"^\d+\.", next_line.strip())
                )

                if not ends_with_punct and not next_is_special and next_line.strip():
                    # 合并两行
                    merged = line.rstrip() + next_line.lstrip()
                    result_lines.append(merged)
                    count += 1
                    i += 2
                    continue

            result_lines.append(line)
            i += 1

        return "\n".join(result_lines), count

    def _normalize_headings(self, text: str) -> tuple[str, int]:
        """统一标题格式

        - 确保 # 后有空格
        - 清理标题行末尾的多余空白

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 修复次数)
        """
        count = 0

        def fix_heading(match: re.Match) -> str:
            nonlocal count
            hashes = match.group(1)
            rest = match.group(2)
            # 确保 # 后有空格
            if not rest.startswith(" "):
                count += 1
                return f"{hashes} {rest.strip()}"
            return f"{hashes} {rest.strip()}"

        result = re.sub(r"^(#{1,6})(.*)", fix_heading, text, flags=re.MULTILINE)
        return result, count

    def _fix_latex_formulas(self, text: str) -> tuple[str, int]:
        """检查并修复 LaTeX 公式

        - 检查 $$...$$ 块公式是否闭合
        - 修复常见的 OCR 识别错误
        - 严重破损的公式标记为 [FORMULA_IMAGE]

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 修复次数)
        """
        count = 0

        # 检查块公式 $$...$$ 闭合
        block_pattern = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
        for match in block_pattern.finditer(text):
            formula = match.group(1)
            fixed = self._fix_single_latex(formula)
            if fixed != formula:
                text = text.replace(match.group(0), f"$${fixed}$$")
                count += 1

        # 检查行内公式 $...$ 闭合（排除 $$ 块公式）
        # 找出所有单个 $ 的位置，检查是否配对
        inline_pattern = re.compile(r"(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)", re.DOTALL)
        for match in inline_pattern.finditer(text):
            formula = match.group(1)
            if not formula.strip():
                continue
            fixed = self._fix_single_latex(formula)
            if fixed != formula:
                text = text.replace(match.group(0), f"${fixed}$")
                count += 1

        return text, count

    def _fix_single_latex(self, formula: str) -> str:
        """修复单个 LaTeX 公式中的常见 OCR 错误

        Args:
            formula: LaTeX 公式内容（不含 $ 符号）

        Returns:
            修复后的公式
        """
        result = formula

        # 常见 OCR 错误映射
        replacements = {
            # 积分号
            r"\\intt": r"\int",
            r"\\intl": r"\int",
            # 求和号
            r"\\summ": r"\sum",
            r"\\suM": r"\sum",
            # 极限
            r"\\limm": r"\lim",
            r"\\Iim": r"\lim",
            # 分数
            r"\\fraC": r"\frac",
            r"\\f rac": r"\frac",
            # 根号
            r"\\sq rt": r"\sqrt",
            r"\\sqrt[": r"\sqrt[",
            # 希腊字母
            r"\\alphaI": r"\alpha",
            r"\\betaI": r"\beta",
            r"\\gammaI": r"\gamma",
            # 上下标空格
            r"_ {": r"_{",
            r"^ {": r"^{",
        }

        for wrong, correct in replacements.items():
            result = result.replace(wrong, correct)

        # 移除 Pandoc 不支持的 \tag{} 命令（公式编号）
        # Pandoc 的 TeX math 不支持 \tag，会导致渲染警告
        result = re.sub(r"\\tag\{[^}]*\}", "", result)

        # 移除其他 Pandoc 不支持的 LaTeX 命令
        result = result.replace(r"\nonumber", "")

        return result

    def _validate_image_paths(self, text: str) -> tuple[str, int]:
        """校验图片路径，失效路径替换为占位符

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 失效图片数量)
        """
        count = 0

        def check_image(match: re.Match) -> str:
            nonlocal count
            alt = match.group(1)
            path = match.group(2)

            if self.base_dir:
                full_path = self.base_dir / path
                if not full_path.exists():
                    count += 1
                    return f"![{alt}]({self.IMAGE_MISSING_MARK})"

            return match.group(0)

        # Markdown 图片语法
        result = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", check_image, text)
        return result, count

    def _clean_garbled_chars(self, text: str) -> tuple[str, int]:
        """清理常见乱码字符

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 清理次数)
        """
        count = 0
        # Unicode 替换字符
        replacement_char = "\ufffd"
        if replacement_char in text:
            count += text.count(replacement_char)
            text = text.replace(replacement_char, "")

        # 控制字符（保留换行和制表符）
        control_pattern = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
        matches = control_pattern.findall(text)
        if matches:
            count += len(matches)
            text = control_pattern.sub("", text)

        return text, count

    def _fix_list_format(self, text: str) -> tuple[str, int]:
        """修复 Markdown 列表格式

        - 确保列表符号后有空格
        - 统一缩进

        Args:
            text: 输入文本

        Returns:
            (处理后文本, 修复次数)
        """
        count = 0

        def fix_list_item(match: re.Match) -> str:
            nonlocal count
            indent = match.group(1)
            marker = match.group(2)
            rest = match.group(3)
            if not rest.startswith(" "):
                count += 1
                return f"{indent}{marker} {rest.strip()}"
            return match.group(0)

        # 无序列表: - * +
        result = re.sub(r"^(\s*)([-*+])(.*)", fix_list_item, text, flags=re.MULTILINE)
        # 有序列表: 1. 2. 等
        result = re.sub(r"^(\s*)(\d+\.)(.*)", fix_list_item, result, flags=re.MULTILINE)

        return result, count

    # ==================== LLM 审查辅助 ====================

    def _build_review_prompt(self, markdown: str, context: IntentAnalysis) -> str:
        """构建 LLM 审查提示词

        Args:
            markdown: 预处理后的 Markdown
            context: 意图分析

        Returns:
            提示词字符串
        """
        return f"""你是一个文档内容审查专家。请审查以下 Markdown 文本，识别并修复语义级别的 OCR 错误。

文档类型: {context.document_type}
适用标准: {context.detected_standard or '未指定'}

审查要求:
1. 识别专业术语的 OCR 识别错误
2. 检查内容连贯性和逻辑一致性
3. 对于无法确定修复方案的内容，用 {self.OCR_ERROR_MARK} 标记
4. 不要修改 HTML 表格结构
5. 不要修改 LaTeX 公式（已在预处理阶段修复）

请直接输出审查后的完整 Markdown 文本，不要添加任何解释性文字。

--- 待审查文本 ---
{markdown}
"""

    def _extract_cleaned_markdown(self, llm_response: str) -> str:
        """从 LLM 响应中提取清洗后的 Markdown

        Args:
            llm_response: LLM 原始响应

        Returns:
            提取的 Markdown 文本
        """
        # 移除可能的代码块包裹
        response = llm_response.strip()
        if response.startswith("```markdown"):
            response = response[len("```markdown"):].strip()
        if response.startswith("```md"):
            response = response[len("```md"):].strip()
        if response.startswith("```"):
            response = response[3:].strip()
        if response.endswith("```"):
            response = response[:-3].strip()
        return response

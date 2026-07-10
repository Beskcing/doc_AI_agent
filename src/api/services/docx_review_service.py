"""DOCX 排版后审查服务

排版完成后对最终 DOCX 进行全文质量审查：
- quick_review: 规则化快速检查（自动执行，不调用 LLM）
- deep_review: LLM 深度审查（用户手动触发，按章节分块审查）

审查维度：OCR 残留错误、语义错误、文字错误、结构完整性、格式一致性
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.config import AppConfig
from src.db.crud import TaskCRUD, TaskReviewCRUD
from src.db.session import get_db_session
from src.tools.docx_text_extractor import DocxText, DocxTextExtractor
from src.utils.logger import get_logger
from src.utils.text_diff import DiffResult, compute_diff, get_changed_text

logger = get_logger(__name__)

# 快速审查：规则化检查的常见 OCR 错误模式
# 注：异常 Unicode 检测已扩充合法字符范围，涵盖国标技术文档常见符号：
#   拉丁扩展(U+00B0-00FF)、希腊字母(U+0370-03FF)、通用标点(U+2000-206F)
#   上下标(U+2070-209F)、类字母符号(U+2100-214F)、箭头(U+2190-21FF)、数学运算符(U+2200-22FF)
_QUICK_CHECK_PATTERNS: list[tuple[str, str, str, str]] = [
    # (正则模式, 错误类型, 位置提示, 修正建议)
    (r"[a-zA-Z]{2,}[，。；：]", "format", "英文单词后出现中文标点", "将中文标点替换为英文标点"),
    (r"\d+[。，]\d+", "text", "数字间出现中文标点", "将中文标点替换为小数点或英文逗号"),
    (
        r"[^\x00-\x7f\u00b0-\u00ff\u0370-\u03ff\u2000-\u206f\u2070-\u209f\u2100-\u214f\u2190-\u21ff\u2200-\u22ff\u3000-\u303f\u4e00-\u9fff\uff00-\uffef]",
        "ocr",
        "包含异常 Unicode 字符（疑似乱码）",
        "检查是否为 OCR 识别错误",
    ),
    (r"\b[01OIlZSB]{2,}\b", "ocr", "疑似数字/字母混淆", "检查是否为 0/O、1/l/I 混淆"),
    (r"([\u4e00-\u9fff])([A-Za-z0-9])", "format", "中文与英文/数字间缺少空格", "建议在中文与英文/数字之间添加空格"),
]


class DocxReviewService:
    """DOCX 排版后审查服务"""

    # 深度审查每块最大字符数
    DEEP_REVIEW_CHUNK_SIZE: int = 8000

    def __init__(
        self,
        config: AppConfig,
        get_llm_client: Callable[[], Any],
        review_prompt_template: str = "",
    ):
        """初始化审查服务

        Args:
            config: 应用配置
            get_llm_client: LLM 客户端工厂函数（懒加载）
            review_prompt_template: 审查提示词模板（含 {review_text} 等占位符）
        """
        self._config = config
        self._get_llm_client = get_llm_client
        self._review_prompt_template = review_prompt_template
        self._extractor = DocxTextExtractor()

    def quick_review(self, task_id: str) -> dict | None:
        """快速审查：规则化检查（不调用 LLM）

        在排版管线完成后自动执行。仅做模式匹配检查，速度快、免费。

        Args:
            task_id: 任务 ID

        Returns:
            审查结果 dict，含 issues 和 summary；失败返回 None
        """
        logger.info("任务 %s: 开始快速审查", task_id)

        try:
            # 获取任务信息
            with get_db_session() as db:
                task = TaskCRUD.get(db, task_id)
                if not task:
                    logger.warning("任务 %s: 不存在", task_id)
                    return None
                docx_path = task.result_path
                user_id = task.user_id

            if not docx_path or not Path(docx_path).exists():
                logger.warning("任务 %s: DOCX 文件不存在: %s", task_id, docx_path)
                return None

            # 创建审查记录
            with get_db_session() as db:
                review = TaskReviewCRUD.create(
                    db,
                    task_id=task_id,
                    user_id=user_id,
                    review_type="quick",
                    status="running",
                )
                review_id = review.id

            # 提取 DOCX 文本
            docx_text: DocxText = self._extractor.extract(docx_path)
            full_text = docx_text.get_full_text()

            # 获取原始 cleaned_markdown 做增量对比（无原文时跳过，避免全量标记为 added）
            cleaned_md = task.cleaned_markdown_preview or ""
            if cleaned_md.strip():
                diff_result: DiffResult = compute_diff(cleaned_md, full_text)
                diff_summary = {
                    "total_added": diff_result.total_added,
                    "total_removed": diff_result.total_removed,
                    "total_modified": diff_result.total_modified,
                    "total_unchanged": diff_result.total_unchanged,
                    "has_changes": diff_result.has_changes,
                }
            else:
                diff_summary = None

            # 执行规则检查
            issues: list[dict] = self._run_rule_checks(full_text, docx_text)

            # 构建结果
            summary = self._build_summary(issues)
            summary["diff"] = diff_summary

            result = {"issues": issues, "summary": summary}

            # 保存结果
            with get_db_session() as db:
                TaskReviewCRUD.update_issues(db, review_id, result, status="completed")

            logger.info(
                "任务 %s: 快速审查完成, %d 个问题",
                task_id,
                summary["total_issues"],
            )
            return result

        except Exception as e:
            logger.error("任务 %s: 快速审查失败: %s", task_id, e)
            # 尝试标记失败
            try:
                with get_db_session() as db:
                    if "review_id" in dir():
                        TaskReviewCRUD.mark_failed(db, review_id, str(e))
            except Exception:
                pass
            return None

    def deep_review(
        self,
        task_id: str,
        progress_callback: Callable[[int, int, int], None] | None = None,
    ) -> dict | None:
        """深度审查：LLM 分块审查

        用户手动触发。按一级标题分块，每块独立 LLM 审查后汇总。

        Args:
            task_id: 任务 ID
            progress_callback: 进度回调 (progress, current_chunk, total_chunks)

        Returns:
            审查结果 dict；失败返回 None
        """
        logger.info("任务 %s: 开始深度审查", task_id)

        try:
            # 获取任务信息
            with get_db_session() as db:
                task = TaskCRUD.get(db, task_id)
                if not task:
                    return None
                docx_path = task.result_path
                user_id = task.user_id
                cleaned_md = task.cleaned_markdown_preview or ""
                doc_type = (task.config or {}).get("document_type", "通用文档")
                standard = task.standard or "GB/T 9704"

            if not docx_path or not Path(docx_path).exists():
                logger.warning("任务 %s: DOCX 文件不存在", task_id)
                return None

            # 创建审查记录
            with get_db_session() as db:
                review = TaskReviewCRUD.create(
                    db,
                    task_id=task_id,
                    user_id=user_id,
                    review_type="deep",
                    status="running",
                )
                review_id = review.id

            # 提取 DOCX 文本
            docx_text: DocxText = self._extractor.extract(docx_path)

            # 增量对比：只审查有变化的部分
            diff_result: DiffResult = compute_diff(cleaned_md, docx_text.get_full_text())
            if diff_result.has_changes:
                review_text = get_changed_text(diff_result, side="docx")
                review_scope = "增量审查（仅审查排版过程中发生变化的部分）"
            else:
                review_text = docx_text.get_full_text()
                review_scope = "全文审查"

            if not review_text.strip():
                # 无文本可审查
                empty_result = {"issues": [], "summary": self._build_summary([])}
                with get_db_session() as db:
                    TaskReviewCRUD.update_issues(db, review_id, empty_result)
                return empty_result

            # 按章节分块
            chunks = self._split_into_chunks(docx_text, max_chars=self.DEEP_REVIEW_CHUNK_SIZE)
            total_chunks = len(chunks)

            logger.info("任务 %s: 深度审查分 %d 块", task_id, total_chunks)

            if progress_callback:
                progress_callback(0, 0, total_chunks)

            # LLM 逐块审查
            all_issues: list[dict] = []
            llm = self._get_llm_client()

            for i, chunk_text in enumerate(chunks):
                logger.info("任务 %s: 审查第 %d/%d 块 (%d 字符)", task_id, i + 1, total_chunks, len(chunk_text))

                try:
                    chunk_issues = self._review_chunk(
                        llm,
                        chunk_text,
                        doc_type,
                        standard,
                        review_scope,
                    )
                    all_issues.extend(chunk_issues)
                except Exception as e:
                    logger.warning("任务 %s: 第 %d 块审查失败: %s", task_id, i + 1, e)
                    # 单块失败不中断整体流程

                if progress_callback:
                    progress_callback(
                        int((i + 1) / total_chunks * 100),
                        i + 1,
                        total_chunks,
                    )

                # 更新进度到 DB
                try:
                    with get_db_session() as db:
                        TaskReviewCRUD.update_progress(
                            db,
                            review_id,
                            progress=int((i + 1) / total_chunks * 100),
                            current_chunk=i + 1,
                            total_chunks=total_chunks,
                        )
                except Exception:
                    pass

            # 去重和汇总
            all_issues = self._deduplicate_issues(all_issues)
            summary = self._build_summary(all_issues)

            result = {"issues": all_issues, "summary": summary}

            # 保存结果
            with get_db_session() as db:
                TaskReviewCRUD.update_issues(db, review_id, result, status="completed")

            logger.info(
                "任务 %s: 深度审查完成, %d 个问题 (OCR:%d 语义:%d 文字:%d 结构:%d 格式:%d)",
                task_id,
                summary["total_issues"],
                summary["ocr_errors"],
                summary["semantic_errors"],
                summary["text_errors"],
                summary["structure_issues"],
                summary["format_issues"],
            )
            return result

        except Exception as e:
            logger.error("任务 %s: 深度审查失败: %s", task_id, e)
            try:
                with get_db_session() as db:
                    if "review_id" in dir():
                        TaskReviewCRUD.mark_failed(db, review_id, str(e))
            except Exception:
                pass
            return None

    # ==================== 规则检查 ====================

    def _run_rule_checks(self, text: str, docx_text: DocxText) -> list[dict]:
        """执行规则化快速检查"""
        issues: list[dict] = []

        for pattern, issue_type, location_hint, suggestion in _QUICK_CHECK_PATTERNS:
            for match in re.finditer(pattern, text):
                # 找到匹配所在的段落
                para_idx = self._find_paragraph_index(docx_text, match.start())
                issues.append(
                    {
                        "type": issue_type,
                        "severity": "low",
                        "location": f"第{para_idx + 1}段",
                        "original": match.group(0),
                        "suggested": suggestion,
                        "reason": location_hint,
                    }
                )

        return issues

    def _find_paragraph_index(self, docx_text: DocxText, char_pos: int) -> int:
        """根据字符位置查找段落索引"""
        current_pos = 0
        for para in docx_text.paragraphs:
            para_len = len(para.text) + 1  # +1 for newline
            if current_pos + para_len > char_pos:
                return para.index
            current_pos += para_len
        return len(docx_text.paragraphs) - 1

    # ==================== LLM 审查 ====================

    def _split_into_chunks(self, docx_text: DocxText, max_chars: int = 8000) -> list[str]:
        """按一级标题将文档分块

        优先在标题处分割，每块不超过 max_chars。
        如果单段超过 max_chars，强制在 max_chars 处截断。
        """
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0

        for para in docx_text.paragraphs:
            para_text = para.text
            para_len = len(para_text) + 1

            # 一级标题始终开启新块
            if para.level == 1 and current_len > 0:
                chunks.append("\n".join(current))
                current = []
                current_len = 0

            # 如果当前段加入后超长，先保存当前块
            if current_len + para_len > max_chars and current:
                chunks.append("\n".join(current))
                current = []
                current_len = 0

            current.append(para_text)
            current_len += para_len

        if current:
            chunks.append("\n".join(current))

        return chunks

    def _review_chunk(
        self,
        llm: Any,
        chunk_text: str,
        doc_type: str,
        standard: str,
        scope: str,
    ) -> list[dict]:
        """审查单个文本块（调用 LLM）"""
        if not llm or not self._review_prompt_template:
            logger.warning("LLM 或提示词不可用，跳过审查")
            return []

        prompt = self._review_prompt_template
        prompt = prompt.replace("{review_text}", chunk_text)
        prompt = prompt.replace("{document_type}", doc_type)
        prompt = prompt.replace("{detected_standard}", standard)
        prompt = prompt.replace("{review_scope}", scope)

        response = llm.invoke(prompt).content

        # 解析 LLM JSON 响应
        try:
            # 尝试直接解析
            data = json.loads(response)
        except json.JSONDecodeError:
            # 尝试提取 JSON（可能有 Markdown 包裹）
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                try:
                    data = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    logger.warning("LLM 审查响应 JSON 解析失败")
                    return []
            else:
                logger.warning("LLM 审查响应无 JSON")
                return []

        return data.get("issues", [])

    # ==================== 工具方法 ====================

    @staticmethod
    def _build_summary(issues: list[dict]) -> dict:
        """根据 issues 列表构建汇总统计"""
        ocr = sum(1 for i in issues if i.get("type") == "ocr")
        semantic = sum(1 for i in issues if i.get("type") == "semantic")
        text = sum(1 for i in issues if i.get("type") == "text")
        structure = sum(1 for i in issues if i.get("type") == "structure")
        fmt = sum(1 for i in issues if i.get("type") == "format")
        total = len(issues)

        if total == 0:
            quality = "good"
        elif sum(1 for i in issues if i.get("severity") == "high") > 0:
            quality = "poor"
        elif total > 10:
            quality = "poor"
        elif total > 3:
            quality = "fair"
        else:
            quality = "good"

        return {
            "total_issues": total,
            "ocr_errors": ocr,
            "semantic_errors": semantic,
            "text_errors": text,
            "structure_issues": structure,
            "format_issues": fmt,
            "overall_quality": quality,
        }

    @staticmethod
    def _deduplicate_issues(issues: list[dict]) -> list[dict]:
        """去除重复的 issue（按 original 文本去重）"""
        seen: set[str] = set()
        unique: list[dict] = []
        for issue in issues:
            key = issue.get("original", "")
            if key and key not in seen:
                seen.add(key)
                unique.append(issue)
        return unique

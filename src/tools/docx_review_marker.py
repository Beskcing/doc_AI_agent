"""DOCX 审查标记工具

审查完成后在 DOCX 中标记问题：黄色高亮 + Word 批注。

核心功能：
- mark_issues(): 为每条审查 issue 在 DOCX 中做黄色高亮 + 右侧批注
- 通过 python-docx 应用高亮，通过 zip/lxml 注入 Word 批注
"""

from __future__ import annotations

import datetime
import re
import shutil
import zipfile
from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from lxml import etree

from src.utils.logger import get_logger

logger = get_logger(__name__)

# OOXML 命名空间
WML_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
COMMENTS_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments"
COMMENTS_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml"

# 审查 issue 类型中文标签
ISSUE_TYPE_LABELS: dict[str, str] = {
    "ocr": "OCR错误",
    "semantic": "语义错误",
    "text": "文字错误",
    "structure": "结构问题",
    "format": "格式问题",
    "latex": "LaTeX残留",
}


class DocxReviewMarker:
    """DOCX 审查标记器

    在排版完成的 DOCX 中为审查发现的问题添加黄色高亮和 Word 批注。
    """

    def __init__(self) -> None:
        pass

    def mark_issues(
        self,
        docx_path: str | Path,
        issues: list[dict],
        output_path: str | Path,
        author: str = "审查系统",
    ) -> dict:
        """在 DOCX 中标记审查问题

        Args:
            docx_path: 输入 DOCX 路径
            issues: 审查 issues 列表，每项含 location/original/type/reason/suggested
            output_path: 输出标记版 DOCX 路径
            author: 批注作者名

        Returns:
            标记统计 dict: {total_issues, highlighted, commented, errors}
        """
        docx_path = Path(docx_path)
        output_path = Path(output_path)

        if not docx_path.exists():
            raise FileNotFoundError(f"DOCX 文件不存在: {docx_path}")

        # 确保输出目录存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        stats = {"total_issues": len(issues), "highlighted": 0, "commented": 0, "errors": 0}

        if not issues:
            shutil.copy(docx_path, output_path)
            logger.info("无 issues，直接复制文档")
            return stats

        logger.info("开始标记 DOCX: %d 个 issues", len(issues))

        # ── 阶段 1: python-docx 打开，应用黄色高亮 + 添加批注标记 ──
        doc = Document(str(docx_path))
        paragraphs = doc.paragraphs

        # 构建评论数据（稍后注入 comments.xml）
        comments_data: list[dict] = []

        for issue in issues:
            try:
                para_idx = self._parse_location(issue.get("location", ""))
                original = issue.get("original", "")
                if para_idx < 0 or para_idx >= len(paragraphs):
                    logger.warning("段落索引越界: %d (总 %d 段)", para_idx, len(paragraphs))
                    stats["errors"] += 1
                    continue

                para = paragraphs[para_idx]
                if not original or original not in para.text:
                    # 模糊搜索：只匹配关键词
                    matched = self._fuzzy_find_issue_text(para, original, issue)
                    if not matched:
                        logger.warning("未在段落 %d 中找到原文: '%s'", para_idx, original[:40])
                        stats["errors"] += 1
                        continue
                    original = matched

                # 应用黄色高亮
                comment_id = len(comments_data)
                highlighted = self._highlight_text_in_paragraph(para, original)
                if highlighted:
                    stats["highlighted"] += 1

                # 添加批注标记（commentRangeStart/End + commentReference）
                if highlighted:
                    self._add_comment_markers(para, comment_id)

                # 记录批注数据
                issue_type = issue.get("type", "unknown")
                issue_type_label = ISSUE_TYPE_LABELS.get(issue_type, issue_type)
                reason = issue.get("reason", "")
                suggested = issue.get("suggested", "")
                comment_text = f"[{issue_type_label}] {reason}"
                if suggested:
                    # 截断过长的建议
                    short_suggestion = suggested[:200] + ("..." if len(suggested) > 200 else "")
                    comment_text += f"\n建议: {short_suggestion}"

                comments_data.append(
                    {
                        "id": comment_id,
                        "text": comment_text,
                        "author": author,
                    }
                )
                stats["commented"] += 1

            except Exception as e:
                logger.warning("标记 issue 失败: %s", e)
                stats["errors"] += 1

        # ── 阶段 2: 保存临时 DOCX ──
        temp_path = output_path.with_suffix(".tmp.docx")
        doc.save(str(temp_path))

        # ── 阶段 3: zip 注入 comments.xml ──
        if comments_data:
            self._inject_comments_xml(temp_path, output_path, comments_data)
        else:
            shutil.copy(temp_path, output_path)

        # 清理临时文件
        try:
            temp_path.unlink()
        except OSError:
            pass

        logger.info(
            "DOCX 标记完成: 高亮=%d, 批注=%d, 错误=%d",
            stats["highlighted"],
            stats["commented"],
            stats["errors"],
        )
        return stats

    # ── 定位 ──

    @staticmethod
    def _parse_location(location: str) -> int:
        """解析 location 字段获取段落索引

        支持格式: "第5段" → 4 (0-based)
        """
        match = re.search(r"(\d+)", location)
        if match:
            return int(match.group(1)) - 1  # 转为 0-based
        return -1

    # ── 文本匹配 ──

    @staticmethod
    def _fuzzy_find_issue_text(para, original: str, issue: dict) -> str | None:
        """模糊搜索 issue 原文

        有些 issue 的 original 可能不完整，尝试在段落中匹配关键词。
        """
        # 尝试用原文中较长的词搜索
        tokens = re.findall(r"[\u4e00-\u9fff\w]+", original)
        for token in sorted(tokens, key=len, reverse=True):
            if len(token) >= 2 and token in para.text:
                return token
        return None

    # ── 高亮 ──

    @staticmethod
    def _highlight_text_in_paragraph(para, target: str) -> bool:
        """在段落中查找 target 文本并应用黄色高亮

        Returns:
            True 如果找到并高亮了至少一个 run
        """
        highlighted = False
        remaining = target

        for run in para.runs:
            if not remaining or not run.text:
                continue

            run_text = run.text
            idx = run_text.find(remaining)

            if idx >= 0:
                # 完全在当前 run 中
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                highlighted = True
                remaining = ""
            elif len(run_text) <= len(remaining):
                # 当前 run 是 target 的一部分前缀
                if remaining.startswith(run_text):
                    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                    highlighted = True
                    remaining = remaining[len(run_text) :]
            elif remaining and run_text.startswith(remaining):
                # 当前 run 以 target 结尾开头
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                highlighted = True
                remaining = ""

            if not remaining:
                break

        return highlighted

    # ── 批注标记 ──

    @staticmethod
    def _add_comment_markers(para, comment_id: int) -> None:
        """在段落末尾添加 Word 批注标记

        为段落中高亮的文本范围添加:
        - w:commentRangeStart (在段落第一个 run 之前)
        - w:commentRangeEnd (在段落最后一个 run 之后)
        - w:commentReference (在 commentRangeEnd 之后的特殊 run 中)
        """
        para_element = para._element
        runs = para_element.findall(qn("w:r"))
        if not runs:
            return

        first_run = runs[0]
        last_run = runs[-1]

        # commentRangeStart
        range_start = OxmlElement("w:commentRangeStart")
        range_start.set(qn("w:id"), str(comment_id))
        first_run.addprevious(range_start)

        # commentRangeEnd (放在最后一个 run 之后)
        range_end = OxmlElement("w:commentRangeEnd")
        range_end.set(qn("w:id"), str(comment_id))
        # 使用 lxml 的 addnext（在元素之后添加同级节点）
        last_run.addnext(range_end)

        # commentReference run (在 commentRangeEnd 之后)
        ref_run = OxmlElement("w:r")
        ref_rpr = OxmlElement("w:rPr")
        ref_style = OxmlElement("w:rStyle")
        ref_style.set(qn("w:val"), "CommentReference")
        ref_rpr.append(ref_style)
        ref_run.append(ref_rpr)

        ref = OxmlElement("w:commentReference")
        ref.set(qn("w:id"), str(comment_id))
        ref_run.append(ref)

        range_end.addnext(ref_run)

    # ── comments.xml 注入 ──

    @staticmethod
    def _inject_comments_xml(src_path: Path, dest_path: Path, comments_data: list[dict]) -> None:
        """向 DOCX zip 中注入 word/comments.xml

        步骤：
        1. 复制原 DOCX
        2. 添加 word/comments.xml
        3. 更新 word/_rels/document.xml.rels（添加 comments 关系）
        4. 更新 [Content_Types].xml（添加 comments content type）
        """
        shutil.copy(src_path, dest_path)

        # 生成 comments.xml 内容
        comments_xml_bytes = DocxReviewMarker._build_comments_xml(comments_data)

        with zipfile.ZipFile(str(dest_path), "a", zipfile.ZIP_DEFLATED) as zf:
            # 1. 添加 word/comments.xml
            if "word/comments.xml" not in zf.namelist():
                zf.writestr("word/comments.xml", comments_xml_bytes)

            # 2. 更新 Content_Types
            DocxReviewMarker._update_content_types(zf)

        # 3. 更新关系文件（需要读-改-写整个 zip）
        DocxReviewMarker._update_rels(dest_path, comments_data)

    @staticmethod
    def _build_comments_xml(comments_data: list[dict]) -> bytes:
        """构建 comments.xml 内容"""
        comments_el = etree.Element(f"{{{WML_NS}}}comments")

        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

        for c in comments_data:
            comment_el = etree.SubElement(comments_el, f"{{{WML_NS}}}comment")
            comment_el.set(f"{{{WML_NS}}}id", str(c["id"]))
            comment_el.set(f"{{{WML_NS}}}author", c.get("author", "审查系统"))
            comment_el.set(f"{{{WML_NS}}}date", now)

            # 每条 comment 包含一个 w:p → w:r → w:t
            p_el = etree.SubElement(comment_el, f"{{{WML_NS}}}p")
            r_el = etree.SubElement(p_el, f"{{{WML_NS}}}r")

            rpr_el = etree.SubElement(r_el, f"{{{WML_NS}}}rPr")
            sz_el = etree.SubElement(rpr_el, f"{{{WML_NS}}}sz")
            sz_el.set(f"{{{WML_NS}}}val", "18")

            t_el = etree.SubElement(r_el, f"{{{WML_NS}}}t")
            t_el.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t_el.text = c["text"]

        return etree.tostring(
            comments_el,
            xml_declaration=True,
            encoding="UTF-8",
            standalone=True,
        )

    @staticmethod
    def _update_rels(dest_path: Path, comments_data: list[dict]) -> None:
        """更新 word/_rels/document.xml.rels 添加 comments 关系"""
        if not comments_data:
            return

        rels_path = "word/_rels/document.xml.rels"
        temp_path = dest_path.with_suffix(".tmp2.docx")

        with zipfile.ZipFile(str(dest_path), "r") as zin:
            with zipfile.ZipFile(str(temp_path), "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)

                    if item.filename == rels_path:
                        data = DocxReviewMarker._patch_rels_xml(data)
                    elif item.filename == "[Content_Types].xml":
                        data = DocxReviewMarker._patch_content_types(data)

                    zout.writestr(item, data)

        # 替换
        temp_path.replace(dest_path)

    @staticmethod
    def _patch_rels_xml(data: bytes) -> bytes:
        """向 document.xml.rels 添加 comments 关系"""
        root = etree.fromstring(data)

        # 查找最大 rId
        max_id = 0
        for rel in root.findall(f"{{{REL_NS}}}Relationship"):
            rid = rel.get("Id", "")
            if rid.startswith("rId"):
                try:
                    max_id = max(max_id, int(rid[3:]))
                except ValueError:
                    pass

        # 添加 comments 关系
        new_rel = etree.SubElement(root, f"{{{REL_NS}}}Relationship")
        new_rel.set("Id", f"rId{max_id + 1}")
        new_rel.set("Type", COMMENTS_REL_TYPE)
        new_rel.set("Target", "comments.xml")

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    @staticmethod
    def _patch_content_types(data: bytes) -> bytes:
        """向 [Content_Types].xml 添加 comments content type"""
        root = etree.fromstring(data)
        ct_ns = CONTENT_TYPES_NS

        # 检查是否已存在
        for override in root.findall(f"{{{ct_ns}}}Override"):
            if override.get("PartName") == "/word/comments.xml":
                return data

        # 添加
        override = etree.SubElement(root, f"{{{ct_ns}}}Override")
        override.set("PartName", "/word/comments.xml")
        override.set("ContentType", COMMENTS_CONTENT_TYPE)

        return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)

    @staticmethod
    def _update_content_types(zf: zipfile.ZipFile) -> None:
        """向 zip 中的 [Content_Types].xml 添加 comments content type（通过读-写方式）"""
        # 此方法在 _update_rels 中统一处理，这里保留空实现以保持接口清晰
        pass

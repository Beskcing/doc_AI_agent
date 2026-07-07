"""内容编辑服务

负责文档内容的编辑功能：
- Markdown/HTML 内容更新与 DOCX 重新生成
- LLM 对话修改文档内容（全量模式 + diff 模式）

从 TaskManager 提取，保持单一职责。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.api.services.service_deps import ServiceDeps
from src.db.session import get_db_session
from src.utils.json_validator import safe_parse_llm_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContentEditService:
    """文档内容编辑服务"""

    def __init__(
        self,
        deps: ServiceDeps,
        get_task_fn: Callable,
        get_mineru_docx_fn: Callable[[str], str | None],
        apply_style_fn: Callable[[str, str, dict], str],
        convert_to_docx_fn: Callable[[str, str, str], str],
    ):
        """初始化内容编辑服务

        Args:
            deps: 共享依赖容器
            get_task_fn: 获取任务信息的回调
            get_mineru_docx_fn: 获取 MinerU DOCX 路径的回调
            apply_style_fn: 应用样式的回调 (task_id, docx_path, style_config) -> styled_path
            convert_to_docx_fn: Markdown 转 DOCX 的回调 (task_id, markdown, extract_dir) -> docx_path
        """
        self.deps = deps
        self._get_task = get_task_fn
        self._get_mineru_docx = get_mineru_docx_fn
        self._apply_style = apply_style_fn
        self._convert_to_docx = convert_to_docx_fn

    def update_content(
        self, task_id: str, content: str, content_type: str = "markdown", regenerate_docx: bool = True
    ) -> dict:
        """更新任务的文档内容"""
        task = self._get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")
        if task.status != "completed":
            raise ValueError("任务尚未完成，无法编辑内容")

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)

        markdown_content = content
        docx_path = None

        if content_type == "html":
            markdown_content = self._html_to_markdown(content, task_id)
            if regenerate_docx:
                docx_path = self._html_to_docx(task_id, content)

        cleaned_md_path = result_dir / "cleaned.md"
        cleaned_md_path.write_text(markdown_content, encoding="utf-8")

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.cleaned_markdown_preview = markdown_content
                db.commit()

        if regenerate_docx and content_type == "markdown":
            mineru_docx = self._get_mineru_docx(task_id)
            if mineru_docx and Path(mineru_docx).exists():
                docx_path = mineru_docx
                logger.info("任务 %s: Markdown 保存后使用 MinerU 原始 DOCX 作为基础", task_id)
            else:
                config = task.config or {}
                extract_dir = config.get("extract_dir", str(result_dir))
                docx_path = self._convert_to_docx(task_id, markdown_content, extract_dir)

        styled_path = None
        if regenerate_docx and docx_path and Path(docx_path).exists():
            style_config = task.style_config_preview or {}
            styled_path = self._apply_style(task_id, docx_path, style_config)

            with get_db_session() as db:
                from src.db.crud import TaskCRUD

                task_db = TaskCRUD.get(db, task_id)
                if task_db:
                    task_db.result_path = styled_path
                    db.commit()

        logger.info("任务 %s: 内容更新完成 (type=%s)", task_id, content_type)
        return {
            "result_path": styled_path or (task.result_path if not regenerate_docx else None),
            "cleaned_markdown_preview": markdown_content,
        }

    def get_content_html(self, task_id: str) -> str | None:
        """加载文档内容为 HTML 供富文本编辑器使用"""
        task = self._get_task(task_id)
        if not task:
            return None

        mineru_docx = self._get_mineru_docx(task_id)
        if mineru_docx and Path(mineru_docx).exists():
            try:
                import pypandoc

                html = pypandoc.convert_file(
                    str(mineru_docx),
                    "html",
                    format="docx",
                    extra_args=["--wrap=none", "--standalone", "--embed-resources"],
                )
                logger.info("任务 %s: MinerU DOCX→HTML 加载成功, %d 字符", task_id, len(html))
                return html
            except Exception as e:
                logger.warning("任务 %s: MinerU DOCX→HTML 转换失败: %s", task_id, e)

        markdown_content = task.cleaned_markdown_preview
        if not markdown_content:
            result_dir = Path("data/output") / task_id
            md_path = result_dir / "cleaned.md"
            if md_path.exists():
                markdown_content = md_path.read_text(encoding="utf-8")
            else:
                return None

        try:
            import pypandoc

            html = pypandoc.convert_text(
                markdown_content,
                "html",
                format="markdown+raw_html+tex_math_dollars",
                extra_args=["--standalone"],
            )
            return html
        except Exception as e:
            logger.warning("任务 %s: Markdown→HTML 转换失败: %s", task_id, e)
            return f"<pre>{markdown_content}</pre>"

    def update_content_via_llm(self, task_id: str, message: str, session_id: str | None = None) -> dict:
        """通过 LLM 对话修改文档内容"""
        task = self._get_task(task_id)
        if not task:
            raise ValueError(f"任务不存在: {task_id}")

        markdown_content = task.cleaned_markdown_preview
        if not markdown_content:
            result_dir = Path("data/output") / task_id
            md_path = result_dir / "cleaned.md"
            if md_path.exists():
                markdown_content = md_path.read_text(encoding="utf-8")
            else:
                raise ValueError("任务无内容可编辑")

        content_len = len(markdown_content)

        if content_len > 10000:
            updated_markdown, reply = self._llm_edit_content_diff_mode(markdown_content, message)
        else:
            updated_markdown, reply = self._llm_edit_content_full_mode(markdown_content, message)

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        cleaned_md_path = result_dir / "cleaned.md"
        cleaned_md_path.write_text(updated_markdown, encoding="utf-8")

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.cleaned_markdown_preview = updated_markdown
                db.commit()

        config = task.config or {}
        extract_dir = config.get("extract_dir", str(result_dir))
        mineru_docx = self._get_mineru_docx(task_id)
        if mineru_docx and Path(mineru_docx).exists():
            docx_path = mineru_docx
            logger.info("任务 %s: LLM 内容编辑后使用 MinerU 原始 DOCX 作为基础", task_id)
        else:
            docx_path = self._convert_to_docx(task_id, updated_markdown, extract_dir)

        style_config = task.style_config_preview or {}
        styled_path = self._apply_style(task_id, docx_path, style_config)

        with get_db_session() as db:
            from src.db.crud import TaskCRUD

            task_db = TaskCRUD.get(db, task_id)
            if task_db:
                task_db.result_path = styled_path
                db.commit()

        logger.info(
            "任务 %s: LLM 内容修改完成 (mode=%s, content_len=%d)",
            task_id,
            "diff" if content_len > 10000 else "full",
            content_len,
        )
        return {"reply": reply, "updated_markdown": updated_markdown, "task_id": task_id}

    def _html_to_markdown(self, html: str, task_id: str) -> str:
        """HTML → Markdown 转换"""
        try:
            import pypandoc

            md = pypandoc.convert_text(html, "markdown", format="html")
            return md
        except Exception as e:
            logger.warning("任务 %s: HTML→Markdown 转换失败: %s", task_id, e)
            return html

    def _html_to_docx(self, task_id: str, html: str) -> str:
        """HTML → DOCX 转换（使用 htmldocx，无需 Pandoc）"""
        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        docx_path = result_dir / "formatted.docx"

        try:
            from docx import Document
            from htmldocx import HtmlToDocx

            document = Document()
            parser = HtmlToDocx()
            parser.add_html_to_document(html, document)
            document.save(str(docx_path))

            if not docx_path.exists() or docx_path.stat().st_size == 0:
                raise RuntimeError("htmldocx HTML→DOCX 转换失败")
            logger.info("任务 %s: HTML→DOCX (htmldocx) 生成成功: %s", task_id, docx_path)
            return str(docx_path)
        except Exception as e:
            logger.warning("任务 %s: htmldocx 转换失败: %s，回退到 Pandoc", task_id, e)
            return self._html_to_docx_pandoc(task_id, html)

    def _html_to_docx_pandoc(self, task_id: str, html: str) -> str:
        """HTML → DOCX 转换（Pandoc 回退方案）"""
        import tempfile

        import pypandoc

        result_dir = Path("data/output") / task_id
        result_dir.mkdir(parents=True, exist_ok=True)
        docx_path = result_dir / "formatted.docx"

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".html",
            encoding="utf-8",
            delete=False,
            dir=str(result_dir),
        ) as tmp:
            tmp.write(html)
            html_tmp_path = tmp.name

        try:
            pypandoc.convert_file(html_tmp_path, "docx", outputfile=str(docx_path), format="html")
            if not docx_path.exists() or docx_path.stat().st_size == 0:
                raise RuntimeError("Pandoc HTML→DOCX 转换失败")
            logger.info("任务 %s: HTML→DOCX (Pandoc回退) 生成成功: %s", task_id, docx_path)
            return str(docx_path)
        finally:
            try:
                Path(html_tmp_path).unlink()
            except OSError:
                pass

    def _llm_edit_content_full_mode(self, markdown_content: str, message: str) -> tuple[str, str]:
        """全量模式：LLM 输出完整修改后文档（适用于小文档）"""
        prompt_path = Path("prompts/content_edit_prompt.md")
        if prompt_path.exists():
            prompt_template = prompt_path.read_text(encoding="utf-8")
        else:
            prompt_template = (
                "你是一个国标文档内容编辑专家。请根据用户指令修改 Markdown 内容。\n\n"
                "## 当前文档内容\n\n{current_content}\n\n"
                "## 用户修改指令\n\n{message}\n\n"
                "## 输出格式\n\n请输出 JSON 格式：\n"
                "- `reply`: 对修改内容的简要说明\n"
                "- `markdown`: 修改后的完整 Markdown 内容\n"
            )

        prompt = prompt_template.replace("{current_content}", markdown_content)
        prompt = prompt.replace("{message}", message)

        llm_client = self.deps.get_llm_client()
        response = llm_client.invoke(prompt).content
        result = safe_parse_llm_json(response)
        reply = result.get("reply", "内容已修改")
        updated_markdown = result.get("markdown", markdown_content)
        return updated_markdown, reply

    def _llm_edit_content_diff_mode(self, markdown_content: str, message: str) -> tuple[str, str]:
        """Diff 模式：LLM 只输出修改操作（适用于大文档）"""
        head = markdown_content[:4000]
        tail = markdown_content[-3000:] if len(markdown_content) > 7000 else ""
        content_summary = head
        if tail:
            content_summary += f"\n\n... (中间省略 {len(markdown_content) - 7000} 字符) ...\n\n{tail}"

        prompt = (
            "你是一个国标文档内容编辑专家。用户会描述对文档的修改需求。\n\n"
            "## 文档摘要（首尾部分）\n\n"
            f"{content_summary}\n\n"
            f"## 文档总长度: {len(markdown_content)} 字符\n\n"
            f"## 用户修改指令\n\n{message}\n\n"
            "## 修改操作格式\n\n"
            "请输出严格的 JSON 格式，描述如何修改文档：\n"
            "{\n"
            '  "reply": "对修改的简要说明",\n'
            '  "action": "append" | "replace" | "insert",\n'
            '  "content": "要追加/插入的新内容",\n'
            '  "search": "要替换的原文片段（仅 replace 操作需要）",\n'
            '  "position": "end" | "beginning" | 具体描述（仅 insert 操作需要）\n'
            "}\n\n"
            "注意：action 说明：\n"
            "- append: 在文档末尾追加内容\n"
            "- replace: 查找 search 文本并替换为 content 文本\n"
            "- insert: 在指定位置插入内容\n"
        )

        llm_client = self.deps.get_llm_client()
        response = llm_client.invoke(prompt).content

        try:
            result = safe_parse_llm_json(response)
        except Exception:
            logger.warning("Diff 模式 JSON 解析失败，回退为追加模式")
            return (
                markdown_content + f"\n\n{message}\n",
                "已将用户指令作为内容追加到文档末尾（JSON 解析失败回退）",
            )

        reply = result.get("reply", "内容已修改")
        action = result.get("action", "append")
        new_content = result.get("content", "")

        if action == "append":
            updated = markdown_content + f"\n\n{new_content}"
        elif action == "replace":
            search_text = result.get("search", "")
            if search_text and search_text in markdown_content:
                updated = markdown_content.replace(search_text, new_content, 1)
            else:
                updated = markdown_content + f"\n\n{new_content}"
                reply += "（原文未找到匹配片段，已追加到末尾）"
        elif action == "insert":
            position = result.get("position", "end")
            if position == "beginning":
                updated = new_content + "\n\n" + markdown_content
            elif position == "end":
                updated = markdown_content + "\n\n" + new_content
            else:
                import re

                pattern = re.compile(re.escape(position), re.IGNORECASE)
                match = pattern.search(markdown_content)
                if match:
                    insert_pos = match.end()
                    next_newline = markdown_content.find("\n", insert_pos)
                    if next_newline == -1:
                        next_newline = len(markdown_content)
                    updated = markdown_content[:next_newline] + f"\n\n{new_content}" + markdown_content[next_newline:]
                else:
                    updated = markdown_content + f"\n\n{new_content}"
                    reply += "（未找到指定位置，已追加到末尾）"
        else:
            updated = markdown_content + f"\n\n{new_content}"

        return updated, reply

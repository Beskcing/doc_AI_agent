"""预览服务

负责文档预览相关的功能：
- DOCX → HTML 预览
- MinerU 原始 DOCX → HTML 预览
- 原始 PDF → 页面图片预览（分页加载）

从 TaskManager 提取，保持单一职责。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


class PreviewService:
    """文档预览服务"""

    def __init__(self, get_task_fn: Callable):
        """初始化预览服务

        Args:
            get_task_fn: 获取任务信息的回调函数 get_task_fn(task_id) -> TaskModel | None
        """
        self._get_task = get_task_fn

    def get_docx_html_preview(self, task_id: str) -> str | None:
        """将任务生成的最终 DOCX 转换为 HTML 供前端预览"""
        task = self._get_task(task_id)
        if not task or not task.result_path:
            return None

        result_path = Path(task.result_path)
        if not result_path.exists():
            return None

        try:
            import pypandoc

            html = pypandoc.convert_file(
                str(result_path),
                "html",
                format="docx",
                extra_args=["--wrap=none", "--standalone", "--embed-resources"],
            )
            logger.info("任务 %s: DOCX→HTML 预览生成成功, %d 字符", task_id, len(html))
            return html
        except Exception as e:
            logger.error("任务 %s: DOCX→HTML 转换失败: %s", task_id, e)
            return None

    def get_mineru_docx_html_preview(self, task_id: str) -> str | None:
        """将 MinerU 原始 DOCX 转换为 HTML 供前端预览"""
        docx_path = self.get_mineru_docx_path(task_id)
        if not docx_path:
            return None

        try:
            import pypandoc

            html = pypandoc.convert_file(
                str(docx_path),
                "html",
                format="docx",
                extra_args=["--wrap=none", "--standalone", "--embed-resources"],
            )
            logger.info("任务 %s: MinerU DOCX→HTML 预览生成成功, %d 字符", task_id, len(html))
            return html
        except Exception as e:
            logger.error("任务 %s: MinerU DOCX→HTML 转换失败: %s", task_id, e)
            return None

    def get_mineru_docx_path(self, task_id: str) -> str | None:
        """获取 MinerU 提供的 DOCX 文件路径"""
        task = self._get_task(task_id)
        if not task:
            return None
        config = task.config or {}
        docx_path = config.get("mineru_docx_path")
        if docx_path and Path(docx_path).exists():
            return docx_path
        return None

    def get_original_pdf_path(self, task_id: str) -> str | None:
        """获取用户上传的原始 PDF 文件路径"""
        task = self._get_task(task_id)
        if not task:
            return None
        config = task.config or {}
        file_path = config.get("file_path")
        if file_path and Path(file_path).exists():
            if Path(file_path).suffix.lower() == ".pdf":
                return file_path
        return None

    def get_pdf_page_images(
        self,
        task_id: str,
        dpi: int = 150,
        page: int = 1,
        page_size: int = 5,
    ) -> dict | None:
        """将原始 PDF 指定页渲染为 base64 PNG 图片（分页加载）"""
        pdf_path = self.get_original_pdf_path(task_id)
        if not pdf_path:
            return None

        try:
            import base64

            import fitz  # PyMuPDF

            doc = fitz.open(pdf_path)
            total_pages = len(doc)

            if page_size > 0:
                start = (page - 1) * page_size
                end = min(start + page_size, total_pages)
            else:
                start = 0
                end = total_pages

            pages = []
            zoom = dpi / 72
            mat = fitz.Matrix(zoom, zoom)

            for i in range(start, end):
                page_obj = doc[i]
                pix = page_obj.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode("ascii")
                pages.append(
                    {
                        "page": i + 1,
                        "image": f"data:image/png;base64,{img_b64}",
                        "width": pix.width,
                        "height": pix.height,
                    }
                )

            doc.close()
            logger.info("任务 %s: PDF 转图片成功，共 %d 页，返回第 %d-%d 页", task_id, total_pages, start + 1, end)
            return {"pages": pages, "total_pages": total_pages}
        except Exception as e:
            logger.error("任务 %s: PDF 转图片失败: %s", task_id, e)
            return None

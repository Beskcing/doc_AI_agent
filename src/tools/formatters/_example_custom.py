"""自定义 Formatter 模板示例

将此文件复制并重命名为 your_format.py，然后修改以下内容：
1. 文件名：使用有意义的名称（如 gbt_9704.py、enterprise_xxx.py）
2. 类名：使用有意义的类名
3. standard_id：唯一标识符（如 "gbt_9704"、"enterprise_xxx"）
4. display_name：显示名称（如 "GB/T 9704 党政机关公文格式"）
5. process() 方法：实现具体的格式修正逻辑

注意：
- 文件名不能以 "_" 或 "test_" 开头（这些会被自动发现跳过）
- standard_id 必须全局唯一，不能与已有的重复
- 系统启动时会自动扫描 formatters/ 目录并注册所有 Formatter
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.shared import Cm

from src.models.document_schema import StyleReport
from src.tools.formatters.base import BaseDocxFormatter
from src.tools.formatters.registry import register_formatter
from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)


@register_formatter
class ExampleCustomFormatter(BaseDocxFormatter):
    """自定义格式修正器示例

    这是一个最小实现模板，展示如何创建自定义 Formatter。
    用户可在此基础上编写完整的格式修正逻辑。

    参考：gbt_1_1.py 完整实现（含段落分类、内容规整、表格图片处理等）
    """

    standard_id: str = "example_custom"
    display_name: str = "示例自定义格式规范"

    def __init__(self) -> None:
        self._warnings: list[str] = []

    def process(self, input_path: str, output_path: str) -> StyleReport:
        """主入口：对 DOCX 文件执行自定义格式修正

        Args:
            input_path: 输入 DOCX 路径
            output_path: 输出 DOCX 路径

        Returns:
            StyleReport 格式处理报告
        """
        input_p = Path(input_path)
        output_p = Path(output_path)
        self._warnings = []

        if not input_p.exists():
            return StyleReport(
                success=False,
                warnings=[f"输入文件不存在: {input_path}"],
                output_path=str(output_p),
            )

        ensure_dir(output_p.parent)

        try:
            doc = Document(str(input_p))
        except Exception as e:
            return StyleReport(
                success=False,
                warnings=[f"无法打开 DOCX 文件: {e}"],
                output_path=str(output_p),
            )

        # ─────────────────────────────────────────────
        # 在这里实现你的格式修正逻辑
        # ─────────────────────────────────────────────

        # 示例：设置页面为 A4
        for section in doc.sections:
            section.page_width = Cm(21.0)
            section.page_height = Cm(29.7)
            section.orientation = WD_ORIENT.PORTRAIT

        # 处理段落（示例）
        paragraph_count = 0
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                paragraph_count += 1
            # TODO: 在此添加具体的格式修正逻辑

        # 保存
        try:
            doc.save(str(output_p))
            logger.info(
                "自定义格式化完成: %s → %s (段落=%d)",
                input_p.name,
                output_p.name,
                paragraph_count,
            )
        except Exception as e:
            return StyleReport(
                success=False,
                paragraphs_styled=paragraph_count,
                warnings=self._warnings + [f"保存失败: {e}"],
                output_path=str(output_p),
            )

        return StyleReport(
            success=True,
            paragraphs_styled=paragraph_count,
            warnings=self._warnings,
            output_path=str(output_p),
        )

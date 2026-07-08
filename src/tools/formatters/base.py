"""Formatter 抽象基类

所有文档格式修正器必须继承 BaseDocxFormatter 并实现 process() 方法。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.models.document_schema import StyleReport


class BaseDocxFormatter(ABC):
    """DOCX 格式修正器抽象基类

    子类必须定义：
    - standard_id: 标准标识符（如 "gbt_1.1"）
    - display_name: 显示名称（如 "GB/T 1.1 标准化工作导则"）
    - process(): 格式修正主方法

    使用 @register_formatter 装饰器自动注册到全局注册表。
    """

    standard_id: str = ""
    display_name: str = ""

    @abstractmethod
    def process(self, input_path: str, output_path: str) -> StyleReport:
        """对 DOCX 文件执行格式修正

        Args:
            input_path: 输入 DOCX 文件路径
            output_path: 输出 DOCX 文件路径

        Returns:
            StyleReport 格式处理报告
        """
        ...

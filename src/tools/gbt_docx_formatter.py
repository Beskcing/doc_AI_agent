# ruff: noqa: F401
"""兼容性转发

GbtDocxFormatter 已迁移至 src/tools/formatters/gbt_1_1.py。
本文件保留以兼容旧 import 路径，内部直接转发到新位置。

DEPRECATED: 请使用 from src.tools.formatters.gbt_1_1 import GbtDocxFormatter
"""

from src.tools.formatters.gbt_1_1 import GbtDocxFormatter  # noqa: F401

__all__ = ["GbtDocxFormatter"]

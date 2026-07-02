"""文件 I/O 工具函数

提供项目中常用的文件读写和路径操作。
"""

from __future__ import annotations

import os
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)


def ensure_dir(path: str | Path) -> Path:
    """确保目录存在，不存在则创建

    Args:
        path: 目录路径

    Returns:
        Path 对象
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_text_file(file_path: str | Path, encoding: str = "utf-8") -> str:
    """读取文本文件

    Args:
        file_path: 文件路径
        encoding: 文件编码

    Returns:
        文件内容

    Raises:
        FileNotFoundError: 文件不存在
    """
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"文件不存在: {p}")
    return p.read_text(encoding=encoding)


def write_text_file(file_path: str | Path, content: str, encoding: str = "utf-8") -> Path:
    """写入文本文件（自动创建父目录）

    Args:
        file_path: 文件路径
        content: 文件内容
        encoding: 文件编码

    Returns:
        写入的文件 Path 对象
    """
    p = Path(file_path)
    ensure_dir(p.parent)
    p.write_text(content, encoding=encoding)
    logger.debug("文件已写入: %s (%d 字节)", p, len(content))
    return p


def resolve_path(path: str | Path, base_dir: str | Path | None = None) -> Path:
    """解析路径，支持相对路径转绝对路径

    Args:
        path: 待解析的路径
        base_dir: 基准目录，为 None 时使用当前工作目录

    Returns:
        解析后的绝对路径
    """
    p = Path(path)
    if p.is_absolute():
        return p
    if base_dir:
        return Path(base_dir) / p
    return p.resolve()


def get_file_extension(file_path: str | Path) -> str:
    """获取文件扩展名（小写，不含点号）

    Args:
        file_path: 文件路径

    Returns:
        扩展名，如 'pdf'、'md'、'docx'
    """
    return Path(file_path).suffix.lstrip(".").lower()


def find_files(directory: str | Path, pattern: str = "*") -> list[Path]:
    """在目录中查找匹配的文件

    Args:
        directory: 搜索目录
        pattern: glob 匹配模式

    Returns:
        匹配文件路径列表
    """
    d = Path(directory)
    if not d.exists():
        logger.warning("目录不存在: %s", d)
        return []
    return sorted(d.glob(pattern))


def get_file_size_mb(file_path: str | Path) -> float:
    """获取文件大小（MB）

    Args:
        file_path: 文件路径

    Returns:
        文件大小（MB）
    """
    return os.path.getsize(file_path) / (1024 * 1024)

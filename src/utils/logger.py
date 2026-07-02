"""统一日志模块

提供项目全局一致的日志配置和获取方式。
"""

from __future__ import annotations

import logging
import logging.config
from pathlib import Path

import yaml

_configured = False


def setup_logging(config_path: str | Path | None = None, level: int = logging.INFO) -> None:
    """初始化日志配置

    Args:
        config_path: logging.yaml 配置文件路径，为 None 时使用默认路径
        level: 最低日志级别
    """
    global _configured
    if _configured:
        return

    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent.parent / "configs" / "logging.yaml"
    else:
        config_path = Path(config_path)

    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        # 确保日志目录存在
        for handler in config.get("handlers", {}).values():
            if "filename" in handler:
                log_dir = Path(handler["filename"]).parent
                log_dir.mkdir(parents=True, exist_ok=True)
        logging.config.dictConfig(config)
    else:
        # 简单默认配置
        logging.basicConfig(
            level=level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """获取指定名称的 Logger

    Args:
        name: Logger 名称，通常使用 __name__

    Returns:
        配置好的 Logger 实例
    """
    setup_logging()
    return logging.getLogger(name)

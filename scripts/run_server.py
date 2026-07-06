"""API 服务启动脚本

用法:
    python -m scripts.run_server [--port 8000] [--host 0.0.0.0] [--reload]

或者通过 uvicorn 直接启动:
    uvicorn src.api.main:app --reload --port 8000
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="文档排版智能体 API 服务")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--reload", action="store_true", help="开发模式热重载")
    args = parser.parse_args()

    setup_logging()
    logger.info("启动 API 服务: http://%s:%d", args.host, args.port)

    uvicorn.run(
        "src.api.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
        # Bug 修复：排除 data/knowledge_data/logs 等目录，
        # 防止 MinerU 输出文件和数据库变化触发频繁重载导致任务中断
        reload_excludes=[
            "data/**",
            "knowledge_data/**",
            "logs/**",
            "frontend/**",
            "tests/**",
            "__pycache__/**",
            "*.db",
            "*.sqlite3",
        ] if args.reload else None,
    )


if __name__ == "__main__":
    main()

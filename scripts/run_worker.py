"""Celery Worker 启动脚本

启动独立的 Celery Worker 进程，从 Redis 队列中消费排版任务。

用法：
    python scripts/run_worker.py                          # 默认 4 并发
    python scripts/run_worker.py --concurrency 8          # 8 并发
    python scripts/run_worker.py --queues pipeline        # 指定队列

环境变量：
    CELERY_BROKER_URL: 消息队列地址
    CELERY_RESULT_BACKEND: 结果后端地址
"""

from __future__ import annotations

import os
import sys

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tasks.celery_app import celery_app

if __name__ == "__main__":
    # 默认并发数：通过环境变量或命令行参数控制
    argv = [
        "worker",
        "--loglevel=info",
        "--concurrency=4",
    ]
    # 允许命令行覆盖参数
    argv.extend(sys.argv[1:])
    celery_app.worker_main(argv)

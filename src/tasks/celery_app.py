"""Celery 实例配置

提供 Celery 应用实例，连接 Redis 作为 Broker 和 Result Backend。

环境变量：
    CELERY_BROKER_URL: 消息队列地址（默认 redis://localhost:6379/0）
    CELERY_RESULT_BACKEND: 结果后端地址（默认 redis://localhost:6379/1）
"""

from __future__ import annotations

import os

from celery import Celery

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

celery_app = Celery(
    "doc_ai_agent",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=["src.tasks.pipeline_task"],
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,  # 任务完成后才确认，防止 Worker 崩溃丢任务
    worker_prefetch_multiplier=1,  # 每个 Worker 一次只取一个任务
    task_acks_on_failure_or_timeout=False,  # 失败时不确认，任务可重新分发
    task_reject_on_worker_lost=True,  # Worker 丢失时自动重新分发
    result_expires=3600,  # 结果保留 1 小时
)

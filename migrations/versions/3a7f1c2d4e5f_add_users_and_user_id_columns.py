"""添加用户表和各表 user_id 列 — 多用户 SaaS 改造

Revision ID: 3a7f1c2d4e5f
Revises: 820ed49c4fca
Create Date: 2026-07-09 16:00:00.000000

本迁移实现 Spec Task 2 的数据库层改造：
- 新增 users 表（用户认证）
- 5 张核心表新增 user_id 列和索引
- kb_documents 和 system_config 保持不变（全局共享）
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a7f1c2d4e5f"
down_revision: Union[str, None] = "820ed49c4fca"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────── 1. 创建 users 表 ────────
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), server_default="user"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ──────── 2. 各表新增 user_id 列 ────────
    tables_with_user_id = [
        "tasks",
        "chat_sessions",
        "chat_messages",
        "style_adjustment_history",
    ]
    for table in tables_with_user_id:
        op.add_column(table, sa.Column("user_id", sa.String(36), nullable=True))
        op.create_index(f"ix_{table}_user_id", table, ["user_id"])

    # style_templates: user_id 可为空（NULL=系统预置模板）
    op.add_column("style_templates", sa.Column("user_id", sa.String(36), nullable=True))
    op.create_index("ix_style_templates_user_id", "style_templates", ["user_id"])

    # kb_documents 和 system_config 保持全局共享，不添加 user_id


def downgrade() -> None:
    # ──────── 回滚：删除 user_id 列 ────────
    tables_with_user_id = [
        "tasks",
        "chat_sessions",
        "chat_messages",
        "style_templates",
        "style_adjustment_history",
    ]
    for table in tables_with_user_id:
        op.drop_index(f"ix_{table}_user_id", table_name=table)
        op.drop_column(table, "user_id")

    # ──────── 删除 users 表 ────────
    op.drop_table("users")

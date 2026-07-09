"""数据库连接和会话管理

使用 SQLAlchemy 2.0 异步 API。
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# 数据库路径
DB_DIR = Path("data")
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "app.db"

# 同步引擎（简化处理，使用同步 Session）
engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},
    echo=False,
)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类"""

    pass


def get_db() -> Session:
    """获取数据库会话（FastAPI 依赖用）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """初始化数据库（优先使用 Alembic 迁移，降级回 create_all）"""
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        alembic_cfg_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
        if alembic_cfg_path.exists():
            alembic_cfg = AlembicConfig(str(alembic_cfg_path))
            command.upgrade(alembic_cfg, "head")
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning("Alembic 迁移失败，降级为 create_all: %s", e)

    # 检查核心表是否存在，不存在则 create_all
    # 注意：即使 Alembic 成功，也需要 create_all 来添加新的列（SQLite ALTER TABLE 受限）
    import logging

    from sqlalchemy import inspect

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()
    required_tables = {
        "users",
        "tasks",
        "system_config",
        "kb_documents",
        "style_templates",
        "chat_sessions",
        "chat_messages",
        "style_adjustment_history",
    }
    missing = required_tables - set(existing_tables)
    if missing:
        logging.getLogger(__name__).warning("缺少表 %s，执行 create_all", missing)
        Base.metadata.create_all(bind=engine)
    else:
        # 表都存在，但仍需确保所有列都存在（Alembic 迁移可能不包含新列如 user_id）
        # SQLite 不支持 ALTER TABLE ADD COLUMN IF NOT EXISTS，create_all 会检查并跳过已存在的列
        Base.metadata.create_all(bind=engine)

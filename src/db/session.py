"""数据库会话上下文管理器

提供统一的数据库会话获取和释放机制，消除重复的 try/finally 样板代码。

用法::

    from src.db.session import get_db_session

    with get_db_session() as db:
        task = TaskCRUD.get(db, task_id)
        db.commit()
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy.orm import Session

from src.db.database import SessionLocal


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """获取数据库会话的上下文管理器

    自动管理会话的生命周期：
    - 进入时创建 SessionLocal 实例
    - 退出时自动 close，无论是否发生异常

    Yields:
        SQLAlchemy Session 实例
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

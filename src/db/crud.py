"""CRUD 操作封装

为 Task、KbDocument、SystemConfig 提供数据库操作。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.db.models import KbDocumentModel, SystemConfigModel, TaskModel


class TaskCRUD:
    """任务 CRUD"""

    @staticmethod
    def create(db: Session, **kwargs) -> TaskModel:
        db_task = TaskModel(**kwargs)
        db.add(db_task)
        db.commit()
        db.refresh(db_task)
        return db_task

    @staticmethod
    def get(db: Session, task_id: str) -> TaskModel | None:
        return db.query(TaskModel).filter(TaskModel.id == task_id).first()

    @staticmethod
    def list_tasks(
        db: Session,
        page: int = 1,
        page_size: int = 10,
        status: str | None = None,
    ) -> tuple[list[TaskModel], int]:
        query = db.query(TaskModel)
        if status:
            query = query.filter(TaskModel.status == status)
        total = query.count()
        tasks = query.order_by(TaskModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return tasks, total

    @staticmethod
    def update_status(
        db: Session,
        task_id: str,
        status: str | None = None,
        progress: int | None = None,
        current_step: str | None = None,
        error_message: str | None = None,
    ) -> TaskModel | None:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if not task:
            return None
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if current_step is not None:
            task.current_step = current_step
        if error_message is not None:
            task.error_message = error_message
        db.commit()
        db.refresh(task)
        return task

    @staticmethod
    def delete(db: Session, task_id: str) -> bool:
        task = db.query(TaskModel).filter(TaskModel.id == task_id).first()
        if task:
            db.delete(task)
            db.commit()
            return True
        return False


class KbDocumentCRUD:
    """知识库文档 CRUD"""

    @staticmethod
    def create(db: Session, **kwargs) -> KbDocumentModel:
        db_doc = KbDocumentModel(**kwargs)
        db.add(db_doc)
        db.commit()
        db.refresh(db_doc)
        return db_doc

    @staticmethod
    def get(db: Session, doc_id: str) -> KbDocumentModel | None:
        return db.query(KbDocumentModel).filter(KbDocumentModel.id == doc_id).first()

    @staticmethod
    def list_documents(
        db: Session,
        page: int = 1,
        page_size: int = 10,
    ) -> tuple[list[KbDocumentModel], int]:
        query = db.query(KbDocumentModel)
        total = query.count()
        docs = query.order_by(KbDocumentModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return docs, total

    @staticmethod
    def delete(db: Session, doc_id: str) -> bool:
        doc = db.query(KbDocumentModel).filter(KbDocumentModel.id == doc_id).first()
        if doc:
            db.delete(doc)
            db.commit()
            return True
        return False


class SystemConfigCRUD:
    """系统配置 CRUD（单条记录）"""

    @staticmethod
    def get_or_create(db: Session) -> SystemConfigModel:
        config = db.query(SystemConfigModel).first()
        if not config:
            config = SystemConfigModel()
            db.add(config)
            db.commit()
            db.refresh(config)
        return config

    @staticmethod
    def update(db: Session, **kwargs) -> SystemConfigModel:
        config = SystemConfigCRUD.get_or_create(db)
        for key, value in kwargs.items():
            if value is not None and hasattr(config, key):
                setattr(config, key, value)
        db.commit()
        db.refresh(config)
        return config

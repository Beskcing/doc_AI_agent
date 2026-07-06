"""CRUD 操作封装

为 Task、KbDocument、SystemConfig 提供数据库操作。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from src.db.models import ChatMessageModel, ChatSessionModel, KbDocumentModel, StyleAdjustmentHistoryModel, StyleTemplateModel, SystemConfigModel, TaskModel


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
        # 自动设置 completed_at
        if status == "completed" and not task.completed_at:
            task.completed_at = datetime.now()
        # 重试时清除 completed_at
        if status in ("pending", "processing") and task.completed_at:
            task.completed_at = None
        # 清除 error_message 当状态不是 failed 时
        if status and status != "failed" and task.error_message and error_message is None:
            task.error_message = None
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

    @staticmethod
    def count_by_status(db: Session) -> dict[str, int]:
        """按状态统计任务数量"""
        from sqlalchemy import func

        results = db.query(TaskModel.status, func.count(TaskModel.id)).group_by(TaskModel.status).all()
        counts = {"total": 0, "pending": 0, "processing": 0, "completed": 0, "failed": 0, "cancelled": 0}
        for status, count in results:
            counts[status] = count
            counts["total"] += count
        return counts

    @staticmethod
    def get_recent(db: Session, limit: int = 5) -> list[TaskModel]:
        """获取最近的任务"""
        return db.query(TaskModel).order_by(TaskModel.created_at.desc()).limit(limit).all()


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


class StyleTemplateCRUD:
    """样式模板 CRUD"""

    @staticmethod
    def create(db: Session, **kwargs) -> StyleTemplateModel:
        db_template = StyleTemplateModel(**kwargs)
        db.add(db_template)
        db.commit()
        db.refresh(db_template)
        return db_template

    @staticmethod
    def get(db: Session, template_id: str) -> StyleTemplateModel | None:
        return db.query(StyleTemplateModel).filter(StyleTemplateModel.id == template_id).first()

    @staticmethod
    def list_templates(
        db: Session,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[StyleTemplateModel], int]:
        query = db.query(StyleTemplateModel)
        total = query.count()
        templates = query.order_by(StyleTemplateModel.created_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return templates, total

    @staticmethod
    def update(db: Session, template_id: str, **kwargs) -> StyleTemplateModel | None:
        template = db.query(StyleTemplateModel).filter(StyleTemplateModel.id == template_id).first()
        if not template:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(template, key):
                setattr(template, key, value)
        db.commit()
        db.refresh(template)
        return template

    @staticmethod
    def delete(db: Session, template_id: str) -> bool:
        template = db.query(StyleTemplateModel).filter(StyleTemplateModel.id == template_id).first()
        if template:
            db.delete(template)
            db.commit()
            return True
        return False

    @staticmethod
    def match_by_standard(db: Session, standard: str) -> StyleTemplateModel | None:
        """根据标准号自动匹配模板

        策略：
        1. 从标准号提取关键词（如 GB/T 14454.13 → 14454）
        2. 在模板名称中搜索匹配的关键词
        3. 返回最近创建的匹配模板
        """
        import re

        # 从标准号提取数字关键词
        numbers = re.findall(r'\d+', standard)
        if not numbers:
            return None

        # 使用最长的数字串作为关键词
        keyword = max(numbers, key=len)
        if len(keyword) < 3:
            return None

        # 在模板名称中搜索
        templates = db.query(StyleTemplateModel).filter(
            StyleTemplateModel.name.like(f'%{keyword}%')
        ).order_by(StyleTemplateModel.created_at.desc()).all()

        return templates[0] if templates else None


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


class ChatSessionCRUD:
    """对话会话 CRUD"""

    @staticmethod
    def create(db: Session, title: str = "新对话", style_config: dict | None = None) -> ChatSessionModel:
        session = ChatSessionModel(title=title, style_config=style_config or {})
        db.add(session)
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def get(db: Session, session_id: str) -> ChatSessionModel | None:
        return db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()

    @staticmethod
    def list_sessions(db: Session, page: int = 1, page_size: int = 50) -> tuple[list[ChatSessionModel], int]:
        query = db.query(ChatSessionModel)
        total = query.count()
        sessions = query.order_by(ChatSessionModel.updated_at.desc()).offset(
            (page - 1) * page_size
        ).limit(page_size).all()
        return sessions, total

    @staticmethod
    def update_style_config(db: Session, session_id: str, style_config: dict) -> ChatSessionModel | None:
        session = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
        if not session:
            return None
        session.style_config = style_config
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def update_title(db: Session, session_id: str, title: str) -> ChatSessionModel | None:
        session = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
        if not session:
            return None
        session.title = title
        db.commit()
        db.refresh(session)
        return session

    @staticmethod
    def delete(db: Session, session_id: str) -> bool:
        # 先删除关联的消息
        db.query(ChatMessageModel).filter(ChatMessageModel.session_id == session_id).delete()
        session = db.query(ChatSessionModel).filter(ChatSessionModel.id == session_id).first()
        if session:
            db.delete(session)
            db.commit()
            return True
        return False


class ChatMessageCRUD:
    """对话消息 CRUD"""

    @staticmethod
    def create(
        db: Session,
        session_id: str,
        role: str,
        content: str,
        style_config_snapshot: dict | None = None,
    ) -> ChatMessageModel:
        msg = ChatMessageModel(
            session_id=session_id,
            role=role,
            content=content,
            style_config_snapshot=style_config_snapshot,
        )
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    @staticmethod
    def list_messages(db: Session, session_id: str, limit: int | None = None) -> list[ChatMessageModel]:
        query = db.query(ChatMessageModel).filter(ChatMessageModel.session_id == session_id)
        query = query.order_by(ChatMessageModel.created_at.asc())
        if limit:
            query = query.limit(limit)
        return query.all()

    @staticmethod
    def count_messages(db: Session, session_id: str) -> int:
        return db.query(ChatMessageModel).filter(ChatMessageModel.session_id == session_id).count()


class StyleAdjustmentHistoryCRUD:
    """样式调整历史 CRUD"""

    @staticmethod
    def create(db: Session, **kwargs) -> StyleAdjustmentHistoryModel:
        record = StyleAdjustmentHistoryModel(**kwargs)
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_by_task(db: Session, task_id: str) -> list[StyleAdjustmentHistoryModel]:
        return db.query(StyleAdjustmentHistoryModel).filter(
            StyleAdjustmentHistoryModel.task_id == task_id
        ).order_by(StyleAdjustmentHistoryModel.created_at.desc()).all()

    @staticmethod
    def list_recent(db: Session, limit: int = 10, standard: str | None = None) -> list[StyleAdjustmentHistoryModel]:
        """获取最近的样式调整记录（用于 LLM few-shot 示例）"""
        query = db.query(StyleAdjustmentHistoryModel)
        if standard:
            query = query.filter(StyleAdjustmentHistoryModel.standard == standard)
        return query.order_by(StyleAdjustmentHistoryModel.created_at.desc()).limit(limit).all()

    @staticmethod
    def delete_by_task(db: Session, task_id: str) -> bool:
        records = db.query(StyleAdjustmentHistoryModel).filter(
            StyleAdjustmentHistoryModel.task_id == task_id
        ).all()
        for record in records:
            db.delete(record)
        db.commit()
        return True

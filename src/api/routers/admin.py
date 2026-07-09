"""管理员路由

提供用户账号管理（仅管理员可访问）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from src.api.middleware.auth import get_current_admin, hash_password
from src.api.models import (
    AdminCreateUserRequest,
    AdminUpdateUserRequest,
    ResponseModel,
    UserInfo,
)
from src.db.crud import UserCRUD
from src.db.session import get_db_session
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/admin", tags=["管理员"])


def _user_to_info(user) -> dict:
    return UserInfo(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    ).model_dump()


# ────────── 用户管理 ──────────


@router.get("/users", response_model=ResponseModel)
async def list_users(
    page: int = 1,
    page_size: int = 20,
    _admin=Depends(get_current_admin),
) -> ResponseModel:
    """列出所有用户（仅管理员）"""
    try:
        with get_db_session() as db:
            users, total = UserCRUD.list_users(db, page=page, page_size=page_size)
            return ResponseModel(
                data={
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "items": [_user_to_info(u) for u in users],
                }
            )
    except Exception as e:
        logger.exception("列出用户失败")
        return ResponseModel(code=500, message=f"列出用户失败: {e}")


@router.post("/users", response_model=ResponseModel)
async def create_user(
    request: AdminCreateUserRequest,
    _admin=Depends(get_current_admin),
) -> ResponseModel:
    """管理员创建新用户"""
    try:
        with get_db_session() as db:
            # 检查用户名是否已存在
            existing = UserCRUD.get_by_username(db, request.username)
            if existing:
                return ResponseModel(code=400, message=f"用户名已存在: {request.username}")

            user = UserCRUD.create(
                db,
                username=request.username,
                password_hash=hash_password(request.password),
                role=request.role,
            )
            logger.info("管理员创建用户: %s (role=%s)", user.username, user.role)
            return ResponseModel(data=_user_to_info(user))
    except Exception as e:
        logger.exception("创建用户失败")
        return ResponseModel(code=500, message=f"创建用户失败: {e}")


@router.put("/users/{user_id}", response_model=ResponseModel)
async def update_user(
    user_id: str,
    request: AdminUpdateUserRequest,
    _admin=Depends(get_current_admin),
) -> ResponseModel:
    """管理员更新用户（重置密码/禁用启用/改角色）"""
    try:
        with get_db_session() as db:
            password_hash = None
            if request.password:
                password_hash = hash_password(request.password)

            user = UserCRUD.update(
                db,
                user_id=user_id,
                password_hash=password_hash,
                is_active=request.is_active,
                role=request.role,
            )
            if not user:
                return ResponseModel(code=404, message="用户不存在")

            changes = []
            if request.password:
                changes.append("密码已重置")
            if request.is_active is not None:
                changes.append("启用" if request.is_active else "禁用")
            if request.role is not None:
                changes.append(f"角色→{request.role}")

            logger.info("管理员更新用户 %s: %s", user.username, ", ".join(changes))
            return ResponseModel(data=_user_to_info(user))
    except Exception as e:
        logger.exception("更新用户失败")
        return ResponseModel(code=500, message=f"更新用户失败: {e}")


@router.delete("/users/{user_id}", response_model=ResponseModel)
async def delete_user(
    user_id: str,
    _admin=Depends(get_current_admin),
) -> ResponseModel:
    """管理员删除用户及其所有数据"""
    try:
        with get_db_session() as db:
            user = UserCRUD.get(db, user_id)
            if not user:
                return ResponseModel(code=404, message="用户不存在")
            if user.role == "admin":
                return ResponseModel(code=400, message="不能删除管理员账号")

            username = user.username
            UserCRUD.delete_cascade(db, user_id)
            logger.info("管理员删除用户 %s 及其所有数据", username)
            return ResponseModel(data={"deleted": True, "username": username})
    except Exception as e:
        logger.exception("删除用户失败")
        return ResponseModel(code=500, message=f"删除用户失败: {e}")

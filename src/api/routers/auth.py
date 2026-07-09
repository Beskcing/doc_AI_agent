"""认证路由：注册、登录、Token 刷新、获取当前用户"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.middleware.auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    verify_password,
)
from src.api.models import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserInfo,
)
from src.db.database import SessionLocal
from src.db.models import UserModel
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["认证"])


def _get_db() -> Session:
    """获取数据库会话（非 Depends 用法，手动管理）"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _validate_password_strength(password: str) -> None:
    """校验密码强度：≥8位，含大写、小写、数字"""
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="密码至少需要 8 位",
        )
    has_upper = any(c.isupper() for c in password)
    has_lower = any(c.islower() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_upper and has_lower and has_digit):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="密码需包含大写字母、小写字母和数字",
        )


@router.post("/register", response_model=TokenResponse)
def register(req: RegisterRequest):
    """用户注册：用户名+密码 → 创建账号 → 返回 Token"""
    _validate_password_strength(req.password)

    db = SessionLocal()
    try:
        # 检查用户名是否已存在
        existing = db.query(UserModel).filter(UserModel.username == req.username).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户名已存在",
            )

        # 创建用户
        user = UserModel(
            username=req.username,
            password_hash=hash_password(req.password),
            role="user",
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        logger.info("新用户注册: %s (id=%s)", user.username, user.id)

        # 签发 Token
        access_token = create_access_token(user.id, user.username, user.role)
        refresh_token = create_refresh_token(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={"id": user.id, "username": user.username, "role": user.role},
        )
    finally:
        db.close()


@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """用户登录：用户名+密码验证 → 返回 Token"""
    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.username == req.username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被禁用，请联系管理员",
            )
        if not verify_password(req.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误",
            )

        logger.info("用户登录: %s", user.username)

        access_token = create_access_token(user.id, user.username, user.role)
        refresh_token = create_refresh_token(user.id)

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={"id": user.id, "username": user.username, "role": user.role},
        )
    finally:
        db.close()


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(req: RefreshRequest):
    """刷新 Token：用 Refresh Token 换新的 Access Token"""
    payload = decode_token(req.refresh_token)

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请使用 Refresh Token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的 Refresh Token",
        )

    db = SessionLocal()
    try:
        user = db.query(UserModel).filter(UserModel.id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="账号已被禁用",
            )

        new_access_token = create_access_token(user.id, user.username, user.role)
        new_refresh_token = create_refresh_token(user.id)

        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            user={"id": user.id, "username": user.username, "role": user.role},
        )
    finally:
        db.close()


@router.get("/me", response_model=UserInfo)
def get_me(current_user: UserModel = Depends(get_current_user)):
    """获取当前登录用户信息"""
    return UserInfo(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )

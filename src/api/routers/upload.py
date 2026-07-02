"""文件上传路由"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, File, UploadFile

from src.api.models import ResponseModel, UploadResponse
from src.utils.file_utils import ensure_dir
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/upload", tags=["上传"])

# 上传文件存储目录
UPLOAD_DIR = Path("data/uploads")
ensure_dir(UPLOAD_DIR)

# 允许的文件扩展名
ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt"}


@router.post("", response_model=ResponseModel)
async def upload_file(file: UploadFile = File(...)) -> ResponseModel:
    """上传文件"""
    # 验证文件扩展名
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        return ResponseModel(code=400, message=f"不支持的文件格式: {ext}，支持: {', '.join(ALLOWED_EXTENSIONS)}")

    # 生成唯一上传 ID
    upload_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{upload_id}{ext}"

    try:
        # 保存文件
        contents = await file.read()
        with open(file_path, "wb") as f:
            f.write(contents)

        file_size = os.path.getsize(file_path)

        return ResponseModel(
            data=UploadResponse(
                upload_id=upload_id,
                filename=file.filename or "unknown",
                file_size=file_size,
                content_type=file.content_type or "application/octet-stream",
            ),
        )
    except Exception as e:
        logger.exception("文件上传失败: %s", file.filename)
        return ResponseModel(code=500, message=f"文件上传失败: {e}")

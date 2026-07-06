"""任务管理路由"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, HTMLResponse

from src.api.models import (
    ApplyTemplateRequest,
    BatchCreateTaskRequest,
    CreateTaskRequest,
    ResponseModel,
    SaveStyleToTemplateRequest,
    TaskListResponse,
    TaskStatus,
)
from src.api.services.task_manager import task_manager
from src.utils.logger import get_logger

logger = get_logger(__name__)

# 上传文件存储目录
UPLOAD_DIR = Path("data/uploads")
OUTPUT_DIR = Path("data/output")

router = APIRouter(prefix="/api/tasks", tags=["任务"])


def _resolve_original_filename(upload_id: str, fallback: str) -> str:
    """Bug#1 修复：从上传元数据文件中恢复原始文件名"""
    meta_path = UPLOAD_DIR / f"{upload_id}.meta"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return meta.get("original_filename", fallback)
        except (json.JSONDecodeError, OSError):
            pass
    return fallback


@router.post("", response_model=ResponseModel)
async def create_task(request: CreateTaskRequest) -> ResponseModel:
    """创建排版任务"""
    try:
        # 查找上传的文件
        upload_id = request.upload_id
        file_path = None
        filename = upload_id
        for ext in (".pdf", ".md", ".txt"):
            candidate = UPLOAD_DIR / f"{upload_id}{ext}"
            if candidate.exists():
                file_path = str(candidate)
                filename = candidate.name
                break

        # Bug#1 修复：恢复原始文件名
        filename = _resolve_original_filename(upload_id, filename)

        task = task_manager.create_task(
            upload_id=upload_id,
            filename=filename,
            standard=request.standard,
            use_rag=request.use_rag,
            llm_model=request.llm_model,
            custom_config={
                **(request.custom_config or {}),
                "file_path": file_path,
                "template_id": request.template_id,
            },
        )
        # 提交异步处理
        task_manager.submit_task(task.id)
        return ResponseModel(data=task_manager.to_info_dict(task))
    except Exception as e:
        logger.exception("创建任务失败")
        return ResponseModel(code=500, message=f"创建任务失败: {e}")


@router.post("/batch", response_model=ResponseModel)
async def batch_create_tasks(request: BatchCreateTaskRequest) -> ResponseModel:
    """批量创建排版任务

    为每个 upload_id 创建独立任务，共享排版配置。
    """
    try:
        created_tasks = []
        for item in request.items:
            # 查找上传的文件
            file_path = None
            filename = item.filename or item.upload_id
            for ext in (".pdf", ".md", ".txt"):
                candidate = UPLOAD_DIR / f"{item.upload_id}{ext}"
                if candidate.exists():
                    file_path = str(candidate)
                    filename = candidate.name
                    break

            # Bug#1 修复：恢复原始文件名
            filename = _resolve_original_filename(item.upload_id, filename)

            task = task_manager.create_task(
                upload_id=item.upload_id,
                filename=filename,
                standard=request.standard,
                use_rag=request.use_rag,
                llm_model=request.llm_model,
                custom_config={
                    **(request.custom_config or {}),
                    "file_path": file_path,
                    "template_id": request.template_id,
                },
            )
            task_manager.submit_task(task.id)
            created_tasks.append(task_manager.to_info_dict(task))

        return ResponseModel(data={"tasks": created_tasks, "count": len(created_tasks)})
    except Exception as e:
        logger.exception("批量创建任务失败")
        return ResponseModel(code=500, message=f"批量创建任务失败: {e}")


@router.get("/stats", response_model=ResponseModel)
async def get_task_stats() -> ResponseModel:
    """获取任务统计信息（Dashboard 用）"""
    try:
        stats = task_manager.get_stats()
        recent = task_manager.get_recent_tasks(limit=5)
        return ResponseModel(data={
            "stats": stats,
            "recent_tasks": [task_manager.to_info_dict(t) for t in recent],
        })
    except Exception as e:
        logger.exception("获取统计失败")
        return ResponseModel(code=500, message=f"获取统计失败: {e}")


@router.get("", response_model=ResponseModel)
async def list_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    status: TaskStatus | None = Query(default=None),
) -> ResponseModel:
    """获取任务列表"""
    try:
        tasks, total = task_manager.list_tasks(
            page=page, page_size=page_size, status=status.value if status else None
        )
        return ResponseModel(
            data=TaskListResponse(
                total=total,
                page=page,
                page_size=page_size,
                items=[task_manager.to_info_dict(t) for t in tasks],
            ),
        )
    except Exception as e:
        logger.exception("获取任务列表失败")
        return ResponseModel(code=500, message=f"获取任务列表失败: {e}")


@router.get("/{task_id}", response_model=ResponseModel)
async def get_task(task_id: str) -> ResponseModel:
    """获取任务详情"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    return ResponseModel(data=task_manager.to_detail_dict(task))


@router.get("/{task_id}/status", response_model=ResponseModel)
async def get_task_status(task_id: str) -> ResponseModel:
    """获取任务状态（SSE 轮询用）"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    return ResponseModel(data=task_manager.to_info_dict(task))


@router.post("/{task_id}/cancel", response_model=ResponseModel)
async def cancel_task(task_id: str) -> ResponseModel:
    """取消任务"""
    if task_manager.cancel_task(task_id):
        return ResponseModel(data={"cancelled": True})
    return ResponseModel(code=400, message="任务不存在或已完成/失败")


@router.post("/{task_id}/retry", response_model=ResponseModel)
async def retry_task(task_id: str) -> ResponseModel:
    """重试失败/取消的任务"""
    try:
        task = task_manager.retry_task(task_id)
        if not task:
            return ResponseModel(code=400, message="任务不存在或状态不允许重试")
        task_manager.submit_task(task_id)
        return ResponseModel(data=task_manager.to_info_dict(task))
    except Exception as e:
        logger.exception("重试任务失败")
        return ResponseModel(code=500, message=f"重试失败: {e}")


@router.delete("/{task_id}", response_model=ResponseModel)
async def delete_task(task_id: str) -> ResponseModel:
    """删除任务"""
    if task_manager.delete_task(task_id):
        return ResponseModel(data={"deleted": True})
    return ResponseModel(code=400, message="任务不存在或正在处理中，无法删除")


@router.get("/{task_id}/download", response_model=ResponseModel)
async def download_result(task_id: str) -> ResponseModel:
    """获取下载信息"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")
    if task.status != "completed":
        return ResponseModel(code=400, message="任务尚未完成")
    return ResponseModel(
        data={
            "download_url": f"/api/tasks/{task_id}/download/file",
            "filename": task.filename,
            "result_path": task.result_path,
        },
    )


@router.get("/{task_id}/download/file")
async def download_file(task_id: str):
    """下载结果文件"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    # 查找结果文件
    result_path = None
    if task.result_path and Path(task.result_path).exists():
        result_path = Path(task.result_path)
    else:
        # 在 output 目录中查找
        task_output_dir = OUTPUT_DIR / task_id
        if task_output_dir.exists():
            # 查找 .docx 或 .md 文件
            for pattern in ("*.docx", "*.md"):
                files = list(task_output_dir.glob(pattern))
                if files:
                    result_path = files[0]
                    break

    if not result_path or not result_path.exists():
        raise HTTPException(status_code=404, detail="结果文件不存在")

    # Bug#1 修复：下载时使用原始文件名而非 UUID 文件名
    original_stem = Path(task.filename).stem if task.filename else task_id
    download_name = f"{original_stem}_排版结果.docx"

    return FileResponse(
        path=str(result_path),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{task_id}/download/mineru-docx")
async def download_mineru_docx(task_id: str):
    """下载 MinerU 提供的原始 DOCX 文件

    MinerU 线上 API 支持 extra_formats=["docx"] 时，
    会在解析结果 ZIP 中包含原始排版 DOCX 文件。
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    docx_path = task_manager.get_mineru_docx_path(task_id)
    if not docx_path:
        raise HTTPException(status_code=404, detail="MinerU 未提供 DOCX 文件或文件已不存在")

    docx_file = Path(docx_path)
    # 使用原文件名，格式化为 <原始PDF名>_MinerU.docx
    original_stem = Path(task.filename).stem
    download_name = f"{original_stem}_MinerU.docx"

    return FileResponse(
        path=str(docx_file),
        filename=download_name,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.get("/{task_id}/preview", response_model=ResponseModel)
async def preview_result(task_id: str) -> ResponseModel:
    """预览任务结果"""
    task = task_manager.get_task(task_id)
    if not task:
        return ResponseModel(code=404, message="任务不存在")

    markdown_preview = task.cleaned_markdown_preview

    # 降级逻辑：如果数据库中的预览内容过短（旧任务被截断），
    # 尝试从输出目录的 cleaned.md 文件读取完整内容
    if not markdown_preview or len(markdown_preview) <= 2000:
        cleaned_md_path = Path("data/output") / task_id / "cleaned.md"
        if cleaned_md_path.exists():
            markdown_preview = cleaned_md_path.read_text(encoding="utf-8")
            # 同步更新数据库（BUG 修复：移除不必要的 update_status 空操作调用）
            from src.db.database import SessionLocal
            db = SessionLocal()
            try:
                from src.db.crud import TaskCRUD
                t = TaskCRUD.get(db, task_id)
                if t:
                    t.cleaned_markdown_preview = markdown_preview
                    db.commit()
            finally:
                db.close()

    return ResponseModel(
        data={
            "markdown_preview": markdown_preview,
            "style_config": task.style_config_preview,
        },
    )


@router.get("/{task_id}/preview/docx")
async def preview_docx(task_id: str):
    """预览最终 Word 文档（返回 HTML）"""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    # BUG 修复：在线程池中执行 Pandoc 转换，避免阻塞事件循环
    html = await run_in_threadpool(task_manager.get_docx_html_preview, task_id)
    if not html:
        raise HTTPException(status_code=404, detail="Word 文件不存在或转换失败")

    return HTMLResponse(content=html)


@router.get("/{task_id}/preview/mineru-docx")
async def preview_mineru_docx(task_id: str):
    """预览 MinerU 原始 Word 文档（返回 HTML）

    展示 MinerU 解析后的原始排版效果，未经国标样式渲染。
    """
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    if task.status != "completed":
        raise HTTPException(status_code=400, detail="任务尚未完成")

    # BUG 修复：在线程池中执行 Pandoc 转换，避免阻塞事件循环
    html = await run_in_threadpool(task_manager.get_mineru_docx_html_preview, task_id)
    if not html:
        raise HTTPException(status_code=404, detail="MinerU 原始 DOCX 不存在或转换失败")

    return HTMLResponse(content=html)


@router.post("/{task_id}/apply-template", response_model=ResponseModel)
async def apply_template_to_task(task_id: str, request: ApplyTemplateRequest) -> ResponseModel:
    """对已完成任务重新应用样式模板

    接收 template_id 或直接传入 style_config，重新渲染 DOCX。
    """
    try:
        # 确定样式配置
        if request.template_id:
            # 从 DB 获取模板
            from src.db.crud import StyleTemplateCRUD
            from src.db.database import SessionLocal

            db = SessionLocal()
            try:
                template = StyleTemplateCRUD.get(db, request.template_id)
                if not template:
                    return ResponseModel(code=404, message="模板不存在")
                style_config = template.style_config
            finally:
                db.close()
        elif request.style_config:
            style_config = request.style_config
        else:
            return ResponseModel(code=400, message="需提供 template_id 或 style_config")

        # BUG 修复：在线程池中执行样式渲染，避免阻塞事件循环
        result_path = await run_in_threadpool(
            task_manager.apply_template_to_task, task_id, style_config,
            True, request.source,
        )
        return ResponseModel(data={
            "result_path": result_path,
            "style_config": style_config,
        })
    except Exception as e:
        logger.exception("应用模板失败")
        return ResponseModel(code=500, message=f"应用模板失败: {e}")


@router.post("/{task_id}/upload-corrected-docx", response_model=ResponseModel)
async def upload_corrected_docx(task_id: str, file: UploadFile = File(...)) -> ResponseModel:
    """上传用户手动修正后的 DOCX 文件（功能1：用户直接修正DOC）

    流程：
    1. 接收用户在 Word 中手动修改后的 DOCX 文件
    2. 使用 DocxStyleExtractor 从中提取样式
    3. 用提取的样式重新渲染 DOCX
    4. 记录样式调整历史（功能4）
    """
    ext = Path(file.filename or "").suffix.lower()
    if ext != ".docx":
        return ResponseModel(code=400, message=f"仅支持 .docx 格式，收到: {ext}")

    try:
        # 保存上传的文件
        import uuid as uuid_mod
        upload_id = str(uuid_mod.uuid4())
        corrected_path = UPLOAD_DIR / f"{upload_id}_corrected.docx"
        contents = await file.read()
        with open(corrected_path, "wb") as f:
            f.write(contents)

        # 在线程池中执行样式提取和重新渲染
        result = await run_in_threadpool(
            task_manager.upload_corrected_docx, task_id, str(corrected_path)
        )

        logger.info("任务 %s: 修正后 DOCX 上传处理完成", task_id)
        return ResponseModel(data=result)
    except Exception as e:
        logger.exception("上传修正 DOCX 失败")
        return ResponseModel(code=500, message=f"处理修正 DOCX 失败: {e}")


@router.post("/{task_id}/save-style-to-template", response_model=ResponseModel)
async def save_style_to_template(task_id: str, request: SaveStyleToTemplateRequest) -> ResponseModel:
    """将当前任务的样式配置保存为模板（功能3：调整回写）

    用户修正样式后，可将调整后的 style_config 保存为新模板或更新已有模板。
    """
    try:
        from src.db.crud import StyleTemplateCRUD
        from src.db.database import SessionLocal

        db = SessionLocal()
        try:
            if request.template_id:
                # 更新已有模板
                template = StyleTemplateCRUD.update(
                    db, request.template_id,
                    name=request.template_name,
                    style_config=request.style_config,
                    description=request.description,
                )
                if not template:
                    return ResponseModel(code=404, message="模板不存在")
                logger.info("任务 %s: 样式已更新到模板 %s", task_id, template.id)
            else:
                # 创建新模板
                template = StyleTemplateCRUD.create(
                    db,
                    name=request.template_name,
                    style_config=request.style_config,
                    description=request.description or f"从任务 {task_id} 保存",
                )
                logger.info("任务 %s: 样式已保存为新模板 %s", task_id, template.id)

            return ResponseModel(data={
                "template_id": template.id,
                "template_name": template.name,
            })
        finally:
            db.close()
    except Exception as e:
        logger.exception("保存样式到模板失败")
        return ResponseModel(code=500, message=f"保存失败: {e}")


@router.get("/{task_id}/style-history", response_model=ResponseModel)
async def get_style_history(task_id: str) -> ResponseModel:
    """获取任务的样式调整历史（功能4：迭代学习）"""
    try:
        from src.db.crud import StyleAdjustmentHistoryCRUD
        from src.db.database import SessionLocal

        db = SessionLocal()
        try:
            records = StyleAdjustmentHistoryCRUD.list_by_task(db, task_id)
            return ResponseModel(data={
                "items": [
                    {
                        "id": r.id,
                        "task_id": r.task_id,
                        "source": r.source,
                        "before_config": r.before_config,
                        "after_config": r.after_config,
                        "diff_summary": r.diff_summary,
                        "standard": r.standard,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    }
                    for r in records
                ],
                "total": len(records),
            })
        finally:
            db.close()
    except Exception as e:
        logger.exception("获取样式调整历史失败")
        return ResponseModel(code=500, message=f"获取历史失败: {e}")

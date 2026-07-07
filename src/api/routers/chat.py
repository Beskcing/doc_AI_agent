"""对话排版路由

支持多轮对话 + 上下文窗口管理 + 会话持久化。
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.api.models import (
    ChatMessageInfo,
    ChatRequest,
    ChatResponse,
    ChatSessionInfo,
    ChatStreamRequest,
    ContentEditRequest,
    CreateSessionRequest,
    ResponseModel,
)
from src.config import AppConfig
from src.db.crud import ChatMessageCRUD, ChatSessionCRUD
from src.db.database import SessionLocal
from src.llm_client import LLMClient
from src.utils.json_validator import safe_parse_llm_json
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["对话排版"])

# 全局配置
_config = AppConfig.load()

# 上下文窗口配置
MAX_CONTEXT_TURNS = 6  # 最多保留最近 N 轮对话（1轮=1条user+1条assistant）
MAX_TOKEN_BUDGET = 6000  # 上下文 token 预算（估算值，按字符数/2近似）


def _estimate_tokens(text: str) -> int:
    """估算文本的 token 数量（中文约 1.5 字/token，英文约 4 字符/token）"""
    return len(text) // 2


def _build_context_messages(
    history_messages: list[dict],
    current_style_config: dict,
    prompt_template: str,
) -> list[dict]:
    """构建上下文窗口消息列表

    策略：状态压缩法
    - 系统提示词 + 当前样式配置（固定）
    - 最近 N 轮对话（动态，受 token 预算限制）
    - 更早的对话被截断

    Args:
        history_messages: 历史消息列表 [{"role": "user"|"assistant", "content": "..."}]
        current_style_config: 当前样式配置
        prompt_template: 提示词模板

    Returns:
        构建好的消息列表
    """
    # 1. 系统提示词 + 当前样式配置
    system_content = prompt_template.replace(
        "{current_style_config}",
        json.dumps(current_style_config, ensure_ascii=False, indent=2),
    )
    system_content = system_content.replace("{context}", "无额外上下文")

    messages = [{"role": "system", "content": system_content}]

    # 2. 从最近的消息开始，向前选取，直到超出 token 预算
    # 先反转消息列表，从最新的开始
    reversed_msgs = list(reversed(history_messages))

    selected = []
    used_tokens = _estimate_tokens(system_content)

    for msg in reversed_msgs:
        msg_tokens = _estimate_tokens(msg["content"])
        if used_tokens + msg_tokens > MAX_TOKEN_BUDGET:
            break
        selected.append(msg)
        used_tokens += msg_tokens

    # 3. 恢复顺序（从旧到新）
    selected.reverse()

    # 4. 如果有被截断的旧消息，添加一条摘要提示
    total_history = len(history_messages)
    included = len(selected)
    if included < total_history:
        truncated_count = total_history - included
        summary_hint = {
            "role": "system",
            "content": f"[注意：之前有 {truncated_count} 条对话已被省略，样式配置已包含所有历史修改结果]",
        }
        messages.append(summary_hint)

    # 5. 添加选中的历史消息
    messages.extend(selected)

    return messages


# ────────── 会话管理 ──────────


@router.get("/sessions", response_model=ResponseModel)
async def list_sessions(page: int = 1, page_size: int = 50) -> ResponseModel:
    """获取会话列表"""
    db = SessionLocal()
    try:
        sessions, total = ChatSessionCRUD.list_sessions(db, page, page_size)
        items = []
        for s in sessions:
            msg_count = ChatMessageCRUD.count_messages(db, s.id)
            items.append(
                ChatSessionInfo(
                    id=s.id,
                    title=s.title,
                    style_config=s.style_config or {},
                    message_count=msg_count,
                    created_at=s.created_at,
                    updated_at=s.updated_at,
                )
            )
        return ResponseModel(
            data={"total": total, "page": page, "page_size": page_size, "items": [i.model_dump() for i in items]}
        )
    finally:
        db.close()


@router.post("/sessions", response_model=ResponseModel)
async def create_session(request: CreateSessionRequest) -> ResponseModel:
    """创建新会话"""
    db = SessionLocal()
    try:
        session = ChatSessionCRUD.create(db, title=request.title, style_config=request.style_config)
        return ResponseModel(
            data=ChatSessionInfo(
                id=session.id,
                title=session.title,
                style_config=session.style_config or {},
                message_count=0,
                created_at=session.created_at,
                updated_at=session.updated_at,
            ).model_dump()
        )
    finally:
        db.close()


@router.get("/sessions/{session_id}", response_model=ResponseModel)
async def get_session(session_id: str) -> ResponseModel:
    """获取会话详情（含消息列表）"""
    db = SessionLocal()
    try:
        session = ChatSessionCRUD.get(db, session_id)
        if not session:
            return ResponseModel(code=404, message="会话不存在")

        messages = ChatMessageCRUD.list_messages(db, session_id)
        msg_items = [
            ChatMessageInfo(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                style_config_snapshot=m.style_config_snapshot,
                created_at=m.created_at,
            ).model_dump()
            for m in messages
        ]

        return ResponseModel(
            data={
                "session": ChatSessionInfo(
                    id=session.id,
                    title=session.title,
                    style_config=session.style_config or {},
                    message_count=len(messages),
                    created_at=session.created_at,
                    updated_at=session.updated_at,
                ).model_dump(),
                "messages": msg_items,
            }
        )
    finally:
        db.close()


@router.delete("/sessions/{session_id}", response_model=ResponseModel)
async def delete_session(session_id: str) -> ResponseModel:
    """删除会话"""
    db = SessionLocal()
    try:
        success = ChatSessionCRUD.delete(db, session_id)
        if success:
            return ResponseModel(data={"deleted": session_id})
        return ResponseModel(code=404, message="会话不存在")
    finally:
        db.close()


@router.get("/sessions/{session_id}/messages", response_model=ResponseModel)
async def get_messages(session_id: str) -> ResponseModel:
    """获取会话的消息列表"""
    db = SessionLocal()
    try:
        messages = ChatMessageCRUD.list_messages(db, session_id)
        items = [
            ChatMessageInfo(
                id=m.id,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                style_config_snapshot=m.style_config_snapshot,
                created_at=m.created_at,
            ).model_dump()
            for m in messages
        ]
        return ResponseModel(data={"items": items})
    finally:
        db.close()


# ────────── 对话（多轮） ──────────


@router.post("/style", response_model=ResponseModel)
async def chat_style(request: ChatRequest) -> ResponseModel:
    """对话修改排版样式（多轮对话）

    用户用自然语言描述修改需求，LLM 根据当前样式配置和历史对话生成修改后的配置。
    支持会话持久化，可恢复历史对话。
    """
    llm = None
    try:
        llm = LLMClient(_config.llm)
    except Exception as e:
        logger.warning("LLM 初始化失败: %s", e)
        return ResponseModel(code=500, message=f"LLM 不可用: {e}")

    # 加载提示词模板
    prompt_path = Path(_config.paths.prompts_dir) / "style_chat_prompt.md"
    if not prompt_path.exists():
        return ResponseModel(code=500, message="对话提示词文件不存在")
    prompt_template = prompt_path.read_text(encoding="utf-8")

    db = SessionLocal()
    user_msg_id = None  # 记录刚保存的用户消息 ID，异常时回滚
    auto_created_session = False  # 是否在本请求中自动创建了会话
    try:
        # 1. 获取或创建会话
        session_id = request.session_id
        if session_id:
            session = ChatSessionCRUD.get(db, session_id)
            if not session:
                return ResponseModel(code=404, message="会话不存在")
        else:
            # 自动创建新会话
            session = ChatSessionCRUD.create(
                db,
                title=request.message[:20] + "..." if len(request.message) > 20 else request.message,
                style_config=request.current_style_config,
            )
            session_id = session.id
            auto_created_session = True

        # 2. 保存用户消息（记录 ID 用于异常回滚）
        user_msg = ChatMessageCRUD.create(db, session_id=session_id, role="user", content=request.message)
        user_msg_id = user_msg.id

        # 3. 获取历史消息（用于上下文窗口）
        db_messages = ChatMessageCRUD.list_messages(db, session_id)
        history = [{"role": m.role, "content": m.content} for m in db_messages]

        # 4. 构建上下文窗口消息
        context_messages = _build_context_messages(
            history_messages=history,
            current_style_config=request.current_style_config,
            prompt_template=prompt_template,
        )

        # 5. 替换最后一条 user 消息中的占位符（用户指令）
        # 系统提示词中的 {message} 需要替换为当前用户消息
        for msg in context_messages:
            if msg["role"] == "system" and "{message}" in msg["content"]:
                msg["content"] = msg["content"].replace("{message}", request.message)

        # 6. 调用 LLM（多轮）
        response_text = llm.invoke_messages(context_messages).content
        logger.debug("对话排版 LLM 响应: %s...", response_text[:200])

        # 7. 解析 JSON 响应
        result = safe_parse_llm_json(response_text)
        reply = result.get("reply", "已修改样式配置")
        updated_config = result.get("style_config", request.current_style_config)

        # 8. 保存 AI 回复消息（带样式快照）
        ChatMessageCRUD.create(
            db,
            session_id=session_id,
            role="assistant",
            content=reply,
            style_config_snapshot=updated_config,
        )

        # 9. 更新会话的样式配置
        ChatSessionCRUD.update_style_config(db, session_id, updated_config)

        # 10. 如果是第一条消息，用消息内容更新会话标题
        msg_count = ChatMessageCRUD.count_messages(db, session_id)
        if msg_count <= 2:
            title = request.message[:30] + "..." if len(request.message) > 30 else request.message
            ChatSessionCRUD.update_title(db, session_id, title)

        logger.info("对话排版成功: session=%s, reply=%s...", session_id, reply[:50])
        return ResponseModel(
            data=ChatResponse(
                reply=reply,
                updated_style_config=updated_config,
                session_id=session_id,
            ).model_dump()
        )
    except Exception as e:
        logger.exception("对话排版失败")
        # 异常回滚：删除孤立用户消息以保持对话状态一致
        if user_msg_id:
            try:
                ChatMessageCRUD.delete_message(db, user_msg_id)
                logger.info("已回滚用户消息 %s", user_msg_id)
            except Exception as cleanup_e:
                logger.warning("回滚用户消息失败: %s", cleanup_e)
        # 异常回滚：如果是自动创建的会话且尚无有效消息，删除空会话
        if auto_created_session and session_id:
            try:
                ChatSessionCRUD.delete(db, session_id)
                logger.info("已回滚自动创建的空会话 %s", session_id)
            except Exception as cleanup_e:
                logger.warning("回滚空会话失败: %s", cleanup_e)
        return ResponseModel(code=500, message=f"对话排版失败: {e}")
    finally:
        db.close()


# ────────── 对话内容编辑 ──────────


@router.post("/stream")
async def chat_stream(request: ChatStreamRequest):
    """流式对话（SSE）

    逐块返回 LLM 响应，供前端实时显示。
    """
    import json as json_mod

    try:
        llm = LLMClient(_config.llm)
    except Exception as e:
        logger.warning("LLM 初始化失败: %s", e)
        return ResponseModel(code=500, message=f"LLM 不可用: {e}")

    def event_generator():
        try:
            for chunk in llm.stream(request.message, request.system_prompt):
                yield f"data: {json_mod.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json_mod.dumps({'done': True})}\n\n"
        except Exception as e:
            logger.exception("流式对话失败")
            yield f"data: {json_mod.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/content", response_model=ResponseModel)
async def chat_edit_content(request: ContentEditRequest) -> ResponseModel:
    """通过 LLM 对话修改文档内容

    用户发送修改指令，LLM 修改文档 Markdown 内容并重新生成 DOCX。
    """
    from fastapi.concurrency import run_in_threadpool
    from src.api.services.task_manager import task_manager

    try:
        result = await run_in_threadpool(
            task_manager.update_content_via_llm,
            task_id=request.task_id,
            message=request.message,
            session_id=request.session_id,
        )
        return ResponseModel(data=result)
    except ValueError as e:
        return ResponseModel(code=400, message=str(e))
    except Exception as e:
        logger.exception("对话内容编辑失败")
        return ResponseModel(code=500, message=f"对话内容编辑失败: {e}")

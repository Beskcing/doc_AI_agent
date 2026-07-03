"""对话排版路由"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from src.api.models import ChatRequest, ChatResponse, ResponseModel
from src.config import AppConfig
from src.llm_client import LLMClient
from src.utils.json_validator import safe_parse_llm_json
from src.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/chat", tags=["对话排版"])

# 全局配置
_config = AppConfig.load()


@router.post("/style", response_model=ResponseModel)
async def chat_style(request: ChatRequest) -> ResponseModel:
    """对话修改排版样式

    用户用自然语言描述修改需求，LLM 根据当前样式配置生成修改后的配置。
    """
    llm = None
    try:
        llm = LLMClient(_config.llm)
    except Exception as e:
        logger.warning("LLM 初始化失败: %s", e)
        return ResponseModel(code=500, message=f"LLM 不可用: {e}")

    # 加载提示词
    prompt_path = Path(_config.paths.prompts_dir) / "style_chat_prompt.md"
    if not prompt_path.exists():
        return ResponseModel(code=500, message="对话提示词文件不存在")
    prompt_template = prompt_path.read_text(encoding="utf-8")

    try:
        # 填充提示词
        prompt = prompt_template.replace(
            "{current_style_config}",
            json.dumps(request.current_style_config, ensure_ascii=False, indent=2),
        )
        prompt = prompt.replace("{context}", request.context or "无额外上下文")
        prompt = prompt.replace("{message}", request.message)

        # 调用 LLM
        response_text = llm.invoke(prompt)
        logger.debug("对话排版 LLM 响应: %s...", response_text[:200])

        # 解析 JSON 响应
        result = safe_parse_llm_json(response_text)

        reply = result.get("reply", "已修改样式配置")
        updated_config = result.get("style_config", request.current_style_config)

        logger.info("对话排版成功: reply=%s...", reply[:50])
        return ResponseModel(data=ChatResponse(
            reply=reply,
            updated_style_config=updated_config,
        ))
    except Exception as e:
        logger.exception("对话排版失败")
        return ResponseModel(code=500, message=f"对话排版失败: {e}")

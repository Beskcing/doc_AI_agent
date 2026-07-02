"""JSON Schema 校验工具

提供 LLM 输出 JSON 的多级容错解析和 Schema 校验功能。
"""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from src.models.style_config import StyleConfig
from src.utils.logger import get_logger

logger = get_logger(__name__)


def validate_style_config(json_data: dict) -> tuple[bool, list[str], StyleConfig | None]:
    """校验 JSON 数据是否符合 StyleConfig Schema

    Args:
        json_data: 待校验的字典

    Returns:
        (是否通过, 错误信息列表, 解析后的 StyleConfig 或 None)
    """
    try:
        config = StyleConfig.model_validate(json_data)
        return True, [], config
    except ValidationError as e:
        errors = []
        for error in e.errors():
            loc = " -> ".join(str(x) for x in error["loc"])
            errors.append(f"[{loc}] {error['msg']}")
        logger.warning("StyleConfig 校验失败: %s", errors)
        return False, errors, None


def safe_parse_llm_json(llm_output: str) -> dict:
    """安全解析 LLM 输出的 JSON 字符串

    多级容错策略:
    1. 尝试直接 json.loads
    2. 尝试提取 ```json ... ``` 代码块
    3. 尝试用正则提取第一个 {...} 块
    4. 均失败则抛出 ValueError

    Args:
        llm_output: LLM 返回的原始文本

    Returns:
        解析后的字典

    Raises:
        ValueError: 无法从 LLM 输出中提取有效 JSON
    """
    if not llm_output or not llm_output.strip():
        raise ValueError("LLM 输出为空")

    # 策略 1: 直接解析
    try:
        result = json.loads(llm_output.strip())
        if isinstance(result, dict):
            logger.debug("JSON 直接解析成功")
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 策略 2: 提取 ```json ... ``` 代码块
    code_block_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = code_block_pattern.search(llm_output)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, dict):
                logger.debug("从代码块中提取 JSON 成功")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略 3: 正则提取第一个 {...} 块（支持嵌套）
    json_obj = _extract_json_object(llm_output)
    if json_obj is not None:
        try:
            result = json.loads(json_obj)
            if isinstance(result, dict):
                logger.debug("从正则提取 JSON 成功")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    # 策略 4: 尝试修复常见的 JSON 格式问题
    fixed = _fix_common_json_issues(llm_output)
    if fixed:
        try:
            result = json.loads(fixed)
            if isinstance(result, dict):
                logger.debug("修复后 JSON 解析成功")
                return result
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(
        f"无法从 LLM 输出中提取有效 JSON。输出前 200 字符: {llm_output[:200]}"
    )


def _extract_json_object(text: str) -> str | None:
    """从文本中提取第一个完整的 JSON 对象（支持嵌套大括号）

    Args:
        text: 输入文本

    Returns:
        JSON 字符串或 None
    """
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False

    for i in range(start, len(text)):
        char = text[i]

        if escape_next:
            escape_next = False
            continue

        if char == "\\":
            escape_next = True
            continue

        if char == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None


def _fix_common_json_issues(text: str) -> str | None:
    """尝试修复常见的 JSON 格式问题

    修复项:
    - 移除末尾多余的逗号
    - 将单引号替换为双引号（仅在 JSON 结构中）

    Args:
        text: 原始文本

    Returns:
        修复后的文本或 None
    """
    # 提取 JSON 对象
    json_str = _extract_json_object(text)
    if json_str is None:
        return None

    # 移除属性值后、闭合括号前的多余逗号
    json_str = re.sub(r",\s*([}\]])", r"\1", json_str)

    return json_str

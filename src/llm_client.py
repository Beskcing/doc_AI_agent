"""LLM 统一调用封装

支持 Qwen (DashScope) 和 GLM (智谱) 双 Provider 切换。
所有 LLM 调用通过此模块统一入口，确保输出校验和错误处理一致。
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.config import LLMConfig
from src.utils.json_validator import safe_parse_llm_json
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LLMClient:
    """统一 LLM 调用客户端"""

    def __init__(self, config: LLMConfig, provider: str | None = None):
        """初始化 LLM 客户端

        Args:
            config: LLM 配置
            provider: 指定 provider，为 None 时使用 default_provider
        """
        self.config = config
        self.provider = provider or config.default_provider
        self._chat_model = self._build_chat_model()

    def _build_chat_model(self) -> ChatOpenAI:
        """根据配置创建 LangChain ChatModel

        Qwen 和 GLM 都兼容 OpenAI API 格式。

        Returns:
            ChatOpenAI 实例
        """
        prov_config = self.config.get_provider_config(self.provider)
        api_key = self.config.get_api_key(self.provider)

        if not api_key:
            logger.warning("未设置 %s 的 API Key，LLM 调用可能失败", self.provider)

        return ChatOpenAI(
            model=prov_config.model,
            openai_api_key=api_key,
            openai_api_base=prov_config.base_url,
            temperature=prov_config.temperature,
            max_tokens=prov_config.max_tokens,
        )

    def invoke(self, prompt: str, system_prompt: str | None = None) -> str:
        """调用 LLM 并返回文本响应

        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词（可选）

        Returns:
            LLM 响应文本
        """
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        logger.debug("LLM 调用: provider=%s, prompt_len=%d", self.provider, len(prompt))

        response = self._chat_model.invoke(messages)
        return response.content

    def invoke_with_schema(
        self,
        prompt: str,
        output_schema: type[BaseModel],
        system_prompt: str | None = None,
        max_retries: int = 2,
    ) -> BaseModel:
        """调用 LLM 并用 Pydantic 模型校验输出 JSON

        流程:
        1. 调用 LLM 获取文本响应
        2. 安全解析 JSON（多级容错）
        3. Pydantic Schema 校验
        4. 校验失败时重试（最多 max_retries 次）

        Args:
            prompt: 用户提示词
            output_schema: Pydantic 模型类
            system_prompt: 系统提示词
            max_retries: 最大重试次数

        Returns:
            校验通过的 Pydantic 模型实例

        Raises:
            ValueError: 多次重试后仍无法获得有效输出
        """
        # 获取 Schema 的 JSON Schema 描述
        schema_desc = output_schema.model_json_schema()

        # 在提示词中附加 JSON Schema 约束
        schema_prompt = f"\n\n请严格按照以下 JSON Schema 输出，不要添加任何额外文字：\n{schema_desc}"
        full_prompt = prompt + schema_prompt

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                response_text = self.invoke(full_prompt, system_prompt)
                logger.debug("LLM 响应 (尝试 %d/%d): %s...", attempt + 1, max_retries + 1, response_text[:100])

                # 安全解析 JSON
                json_data = safe_parse_llm_json(response_text)

                # Pydantic 校验
                result = output_schema.model_validate(json_data)
                logger.info("LLM 输出校验通过 (尝试 %d)", attempt + 1)
                return result

            except Exception as e:
                last_error = e
                logger.warning("LLM 输出校验失败 (尝试 %d/%d): %s", attempt + 1, max_retries + 1, e)

                if attempt < max_retries:
                    # 在重试时提供更明确的指导
                    full_prompt = (
                        f"{prompt}\n\n"
                        f"上一次的输出格式不正确，错误信息: {e}\n"
                        f"请重新输出合法的 JSON，严格遵循以下 Schema:\n{schema_desc}\n"
                        f"直接输出 JSON，不要添加任何解释或代码块标记。"
                    )

        raise ValueError(f"LLM 输出 {max_retries + 1} 次校验均失败: {last_error}")

    def load_prompt(self, prompt_name: str, prompts_dir: str | Path = "prompts") -> str:
        """从 prompts/ 目录加载提示词模板

        Args:
            prompt_name: 提示词文件名（不含路径）
            prompts_dir: 提示词目录

        Returns:
            提示词文本

        Raises:
            FileNotFoundError: 提示词文件不存在
        """
        prompt_path = Path(prompts_dir) / prompt_name
        if not prompt_path.exists():
            raise FileNotFoundError(f"提示词文件不存在: {prompt_path}")
        return prompt_path.read_text(encoding="utf-8")

    def switch_provider(self, provider: str) -> None:
        """切换 LLM Provider

        Args:
            provider: 新的 provider 名称
        """
        self.provider = provider
        self._chat_model = self._build_chat_model()
        logger.info("已切换 LLM Provider: %s", provider)

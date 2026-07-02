"""条件路由函数

定义 LangGraph 工作流中的条件分支逻辑。
"""

from __future__ import annotations

from src.workflows.state import FormattingState


def route_after_validation(state: FormattingState) -> str:
    """校验结果路由

    根据 style_config 的校验结果决定下一步：
    - pass: 校验通过，进入渲染阶段
    - retry: 校验失败但未超过重试次数，回退重新提取样式
    - fail: 超过重试次数，进入失败处理

    Args:
        state: 当前工作流状态

    Returns:
        路由方向: "pass" / "retry" / "fail"
    """
    if state.get("validation_passed"):
        return "pass"

    retry_count = state.get("retry_count", 0)
    if retry_count >= 3:
        return "fail"

    return "retry"

"""端到端工作流测试（使用 Mock LLM）"""

from unittest.mock import MagicMock

from src.workflows.conditions import route_after_validation
from src.workflows.state import FormattingState


class TestRouteAfterValidation:
    """条件路由测试"""

    def test_pass_on_valid(self):
        """校验通过走 pass"""
        state: FormattingState = {"validation_passed": True, "retry_count": 0}
        assert route_after_validation(state) == "pass"

    def test_retry_on_invalid(self):
        """校验失败且未超重试次数走 retry"""
        state: FormattingState = {"validation_passed": False, "retry_count": 1}
        assert route_after_validation(state) == "retry"

    def test_fail_on_max_retries(self):
        """超过重试次数走 fail"""
        state: FormattingState = {"validation_passed": False, "retry_count": 3}
        assert route_after_validation(state) == "fail"

    def test_retry_on_missing_fields(self):
        """缺失字段默认走 retry"""
        state: FormattingState = {}
        assert route_after_validation(state) == "retry"


class TestWorkflowIntegration:
    """工作流集成测试（不依赖真实 LLM）"""

    def test_markdown_cleaning_pipeline(self, sample_markdown):
        """Markdown 清洗管线"""
        from src.tools.html_table_preserver import HTMLTablePreserver
        from src.tools.markdown_cleaner import MarkdownCleaner

        preserver = HTMLTablePreserver()
        cleaner = MarkdownCleaner()

        # 保护表格
        protected, table_map = preserver.protect(sample_markdown)

        # 预处理
        cleaned, changes = cleaner.pre_clean(protected)

        # 恢复表格
        final = preserver.restore(cleaned, table_map)

        # 验证
        assert "<table>" in final
        assert len(changes) > 0
        assert "# 国家标准示例" in final

    def test_style_config_validation(self, sample_style_config_dict):
        """样式配置校验"""
        from src.utils.json_validator import validate_style_config

        passed, errors, config = validate_style_config(sample_style_config_dict)
        assert passed
        assert config is not None
        assert config.page_layout.paper_size == "A4"
        assert len(config.heading_styles) == 2

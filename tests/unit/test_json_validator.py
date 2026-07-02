"""JSON 校验工具单元测试"""

import pytest

from src.utils.json_validator import safe_parse_llm_json, validate_style_config


class TestSafeParseLLMJson:
    """safe_parse_llm_json 测试"""

    def test_direct_json(self):
        """直接解析合法 JSON"""
        result = safe_parse_llm_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_code_block_json(self):
        """从代码块中提取 JSON"""
        text = '```json\n{"key": "value"}\n```'
        result = safe_parse_llm_json(text)
        assert result == {"key": "value"}

    def test_nested_json(self):
        """嵌套 JSON 提取"""
        text = '前文 {"a": {"b": 1}} 后文'
        result = safe_parse_llm_json(text)
        assert result == {"a": {"b": 1}}

    def test_trailing_comma(self):
        """修复末尾多余逗号"""
        text = '{"a": 1, "b": 2,}'
        result = safe_parse_llm_json(text)
        assert result == {"a": 1, "b": 2}

    def test_empty_input(self):
        """空输入抛出异常"""
        with pytest.raises(ValueError):
            safe_parse_llm_json("")

    def test_invalid_json(self):
        """无法解析时抛出异常"""
        with pytest.raises(ValueError):
            safe_parse_llm_json("这不是 JSON")


class TestValidateStyleConfig:
    """validate_style_config 测试"""

    def test_valid_config(self, sample_style_config_dict):
        """合法配置校验通过"""
        passed, errors, config = validate_style_config(sample_style_config_dict)
        assert passed
        assert len(errors) == 0
        assert config is not None

    def test_invalid_config(self):
        """缺少必填字段校验失败"""
        passed, errors, config = validate_style_config({})
        assert not passed
        assert len(errors) > 0
        assert config is None

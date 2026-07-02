"""Bad Case 回归测试"""

from src.tools.html_table_preserver import HTMLTablePreserver
from src.tools.markdown_cleaner import MarkdownCleaner
from src.utils.json_validator import safe_parse_llm_json


class TestBrokenTableRecovery:
    """HTML 表格断表恢复"""

    def test_unclosed_table_tag(self):
        """未闭合的 table 标签"""
        preserver = HTMLTablePreserver()
        broken = "<table><tr><td>cell1</td><td>cell2</tr></table>"
        is_valid, issues = preserver.validate_table_integrity(broken)
        assert not is_valid
        assert any("td" in issue for issue in issues)


class TestHeavyOCRMNoise:
    """高 OCR 噪声文档"""

    def test_garbled_chars_cleaned(self):
        """乱码字符清理"""
        cleaner = MarkdownCleaner()
        text = "正常内容\ufffd\x00\x01噪声内容\ufffd"
        result, count = cleaner._clean_garbled_chars(text)
        assert "\ufffd" not in result
        assert "正常内容" in result

    def test_fullwidth_numbers_in_context(self):
        """上下文中的全角数字"""
        cleaner = MarkdownCleaner()
        text = "标准编号 ＧＢ/Ｔ ９７０４"
        result, _ = cleaner._fullwidth_to_halfwidth(text)
        assert "GB/T" in result
        assert "9704" in result


class TestHeadingHierarchy:
    """标题层级问题"""

    def test_heading_without_space(self):
        """标题 # 后无空格"""
        cleaner = MarkdownCleaner()
        text = "#一级标题\n##二级标题\n###三级标题"
        result, count = cleaner._normalize_headings(text)
        assert "# 一级标题" in result
        assert "## 二级标题" in result
        assert "### 三级标题" in result

    def test_heading_level_jump(self):
        """标题层级跳跃（h1 直接到 h3）不报错"""
        cleaner = MarkdownCleaner()
        text = "# 一级\n### 三级"
        result, _ = cleaner.pre_clean(text)
        assert "# 一级" in result
        assert "### 三级" in result


class TestLLMJsonMalformed:
    """LLM 输出畸形 JSON"""

    def test_json_with_markdown_wrapper(self):
        """JSON 被 Markdown 代码块包裹"""
        text = '这是结果：\n```json\n{"key": "value"}\n```\n以上。'
        result = safe_parse_llm_json(text)
        assert result == {"key": "value"}

    def test_json_with_trailing_commas(self):
        """JSON 末尾有多余逗号"""
        text = '{"a": [1, 2, 3,],}'
        result = safe_parse_llm_json(text)
        assert result == {"a": [1, 2, 3]}

    def test_deeply_nested_json(self):
        """深层嵌套 JSON"""
        text = '前文 {"a": {"b": {"c": {"d": 1}}}} 后文'
        result = safe_parse_llm_json(text)
        assert result["a"]["b"]["c"]["d"] == 1

    def test_json_with_chinese_values(self):
        """JSON 包含中文值"""
        text = '{"font": "仿宋_GB2312", "note": "依据检索到的规范"}'
        result = safe_parse_llm_json(text)
        assert result["font"] == "仿宋_GB2312"

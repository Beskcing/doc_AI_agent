"""Markdown 清洗工具单元测试"""

from src.tools.markdown_cleaner import MarkdownCleaner


class TestMarkdownCleaner:
    """MarkdownCleaner 规则化预处理测试"""

    def setup_method(self):
        self.cleaner = MarkdownCleaner()

    def test_fullwidth_to_halfwidth(self):
        """全角数字/字母转半角"""
        text = "１２３ ＡＢＣ ａｂｃ"
        result, count = self.cleaner._fullwidth_to_halfwidth(text)
        assert "123" in result
        assert "ABC" in result
        assert "abc" in result
        assert count > 0

    def test_fullwidth_punctuation(self):
        """全角标点转半角"""
        text = "内容（说明）"
        result, count = self.cleaner._fullwidth_to_halfwidth(text)
        assert "(" in result
        assert ")" in result

    def test_clean_extra_spaces(self):
        """多余空格清理"""
        text = "这是  一段  文字"
        result, count = self.cleaner._clean_extra_spaces(text)
        assert "这是 一段 文字" in result
        assert count > 0

    def test_clean_extra_spaces_preserve_code_block(self):
        """代码块内空格不被清理"""
        text = "```python\nx  =  1\n```\n普通  文字"
        result, count = self.cleaner._clean_extra_spaces(text)
        assert "x  =  1" in result
        assert "普通 文字" in result

    def test_fix_ocr_line_breaks(self):
        """OCR 断行修复"""
        text = "这是一段被截断的\n文字需要合并"
        result, count = self.cleaner._fix_ocr_line_breaks(text)
        assert "被截断的文字" in result or "被截断的\n文字" not in result
        assert count > 0

    def test_fix_ocr_line_breaks_preserve_endings(self):
        """正常结尾的行不合并"""
        text = "这是完整的句子。\n这是下一段。"
        result, count = self.cleaner._fix_ocr_line_breaks(text)
        assert result == text

    def test_normalize_headings(self):
        """标题格式统一"""
        text = "#标题\n## 正常标题"
        result, count = self.cleaner._normalize_headings(text)
        assert "# 标题" in result
        assert count > 0

    def test_clean_garbled_chars(self):
        """乱码字符清理"""
        text = "正常文字\ufffd乱码\x00控制"
        result, count = self.cleaner._clean_garbled_chars(text)
        assert "\ufffd" not in result
        assert "\x00" not in result
        assert count > 0

    def test_fix_list_format(self):
        """列表格式修复"""
        text = "-项目1\n*项目2"
        result, count = self.cleaner._fix_list_format(text)
        assert "- 项目1" in result
        assert "* 项目2" in result

    def test_pre_clean_full_pipeline(self):
        """完整预处理管线"""
        text = "１２３\n\n#标题\n\n这是  一段  文字"
        result, changes = self.cleaner.pre_clean(text)
        assert "123" in result
        assert "# 标题" in result
        assert len(changes) > 0

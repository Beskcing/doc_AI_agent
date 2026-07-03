"""HTML 表格保护工具单元测试"""

from src.tools.html_table_preserver import HTMLTablePreserver


class TestHTMLTablePreserver:
    """HTMLTablePreserver 测试"""

    def setup_method(self):
        self.preserver = HTMLTablePreserver()

    def test_protect_single_table(self):
        """单个表格保护"""
        md = "前文\n<table><tr><td>cell</td></tr></table>\n后文"
        result, mapping = self.preserver.protect(md)

        assert "<table>" not in result
        assert "@@TABLE_PLACEHOLDER_0@@" in result
        assert len(mapping) == 1
        assert "<table>" in list(mapping.values())[0]

    def test_protect_multiple_tables(self):
        """多个表格保护"""
        md = (
            "<table><tr><td>A</td></tr></table>\n"
            "中间文本\n"
            "<table><tr><td>B</td></tr></table>"
        )
        result, mapping = self.preserver.protect(md)

        assert len(mapping) == 2
        assert "<table>" not in result

    def test_protect_no_tables(self):
        """无表格文本"""
        md = "普通文本，没有表格"
        result, mapping = self.preserver.protect(md)

        assert result == md
        assert len(mapping) == 0

    def test_restore(self):
        """恢复表格"""
        original = "<table><tr><td>cell</td></tr></table>"
        md = f"前文\n{original}\n后文"

        protected, mapping = self.preserver.protect(md)
        restored = self.preserver.restore(protected, mapping)

        assert restored == md

    def test_validate_table_integrity_valid(self):
        """完整表格校验"""
        table = "<table><tr><th>H</th></tr><tr><td>D</td></tr></table>"
        is_valid, issues = self.preserver.validate_table_integrity(table)
        assert is_valid
        assert len(issues) == 0

    def test_validate_table_integrity_broken(self):
        """破损表格校验"""
        table = "<table><tr><td>cell</tr></table>"  # 缺少 </td>
        is_valid, issues = self.preserver.validate_table_integrity(table)
        assert not is_valid
        assert len(issues) > 0

    def test_count_tables(self):
        """表格计数"""
        md = "<table></table> text <table></table>"
        assert self.preserver.count_tables(md) == 2

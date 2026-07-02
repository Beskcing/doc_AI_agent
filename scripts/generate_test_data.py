"""测试数据生成脚本

使用 MinerU 解析示例 PDF，生成测试 fixture。
如果 MinerU 未安装，生成示例 Markdown 作为替代。

用法:
    python -m scripts.generate_test_data
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.file_utils import ensure_dir, write_text_file
from src.utils.logger import get_logger, setup_logging

logger = get_logger(__name__)


SAMPLE_MARKDOWN = """# 党政机关公文格式

## 1 范围

本标准规定了党政机关公文通用的纸张要求、印制要求、格式各要素的编排规则。

本标准适用于各级党政机关制发的公文。其他机关和单位的公文可以参照执行。

## 2 规范性引用文件

下列文件对于本文件的应用是必不可少的。

<table>
<tr><th>序号</th><th>标准编号</th><th>标准名称</th></tr>
<tr><td>1</td><td>GB/T 148</td><td>印刷、书写和绘图纸幅面尺寸</td></tr>
<tr><td>2</td><td>GB 3100</td><td>国际单位制及其应用</td></tr>
<tr><td>3</td><td>GB 3101</td><td>有关量、单位和符号的一般原则</td></tr>
</table>

## 3 术语和定义

### 3.1 字 word

标示公文中横向距离的长度单位。在本标准中，一字指一个汉字宽度的距离。

### 3.2 行 line

标示公文中纵向距离的长度单位。在本标准中，一行指一个汉字的高度加 3 号汉字高度的 7/8 距离。

## 4 公文用纸主要技术指标

公文用纸一般使用纸张定量为 60g/m² ～ 80g/m² 的胶版印刷纸或复印纸。

纸张白度 80% ～ 90%，横向耐折度 ≥ 15 次，不透明度 ≥ 85%。

## 5 公文用纸幅面尺寸及版面要求

### 5.1 幅面尺寸

公文用纸采用 GB/T 148 中规定的 A4 型纸，其成品幅面尺寸为：

$$210mm \\times 297mm$$

### 5.2 版面

#### 5.2.1 页边与版心尺寸

公文用纸天头（上白边）为 $37mm \\pm 1mm$，公文用纸订口（左白边）为 $28mm \\pm 1mm$。

版心尺寸为 $156mm \\times 225mm$。

#### 5.2.2 字体和字号

如无特殊说明，公文中文字的颜色均为黑色。

正文使用仿宋_GB2312 三号字体，一般每面排 22 行，每行排 28 个字。

![图1 版心示意图](images/page_layout.png)

## 6 公文格式各要素编排规则

### 6.1 公文标题

标题由发文机关名称、事由和文种组成。一般用 2 号小标宋体字。

### 6.2 主送机关

编排于标题下空一行位置，居左顶格，回行时仍顶格。

### 6.3 正文

公文首页必须显示正文。一般用 3 号仿宋体字，编排于主送机关名称下一行。

每个自然段左空二字，回行顶格。
"""


def main():
    setup_logging()

    fixtures_dir = Path("tests/fixtures")
    bad_cases_dir = fixtures_dir / "bad_cases"
    ensure_dir(fixtures_dir)
    ensure_dir(bad_cases_dir)

    logger.info("生成测试数据...")

    # 1. 生成示例 MinerU 输出 Markdown
    write_text_file(
        fixtures_dir / "sample_mineru_output.md",
        SAMPLE_MARKDOWN,
    )
    logger.info("已生成: tests/fixtures/sample_mineru_output.md")

    # 2. 生成示例样式配置
    import json

    sample_config = {
        "page_layout": {
            "paper_size": "A4",
            "margin_top_cm": 3.7,
            "margin_bottom_cm": 3.5,
            "margin_left_cm": 2.8,
            "margin_right_cm": 2.6,
        },
        "heading_styles": [
            {
                "level": 1,
                "font": {"family": "方正小标宋简体", "size_pt": 22, "bold": False},
                "alignment": "center",
                "line_spacing": 2.0,
            },
            {
                "level": 2,
                "font": {"family": "黑体", "size_pt": 16, "bold": True},
                "alignment": "left",
                "line_spacing": 1.5,
            },
            {
                "level": 3,
                "font": {"family": "楷体", "size_pt": 16, "bold": True},
                "alignment": "left",
                "line_spacing": 1.5,
            },
        ],
        "body_style": {
            "font": {"family": "仿宋_GB2312", "size_pt": 16},
            "line_spacing": 1.5,
            "first_line_indent_chars": 2,
            "alignment": "justify",
        },
        "table_style": {
            "border_style": "three-line",
            "border_width_pt": 1.0,
            "header_font": {"family": "黑体", "size_pt": 12, "bold": True},
            "body_font": {"family": "仿宋_GB2312", "size_pt": 10.5},
            "header_bold": True,
            "rag_note": "依据国标 GB/T 9704，表头加粗，使用三线表",
        },
        "rag_sources": ["GB/T 9704-2012 党政机关公文格式"],
    }

    write_text_file(
        fixtures_dir / "expected_style_config.json",
        json.dumps(sample_config, ensure_ascii=False, indent=2),
    )
    logger.info("已生成: tests/fixtures/expected_style_config.json")

    # 3. 生成 Bad Case 文件
    broken_table = """# 破损表格测试

<table>
<tr><th>列A</th><th>列B</th>
<tr><td>数据1</td><td>数据2</td></tr>
</table>
"""
    write_text_file(bad_cases_dir / "broken_table.md", broken_table)

    ocr_noise = """# 高 OCR 噪声测试

１２３４５６７８９０

这是壹段包含  多余空格  和
被截断的
文字。

#标题格式错误
##另一个错误标题

正常文字\ufffd乱码\x00内容

-列表项没有空格
*另一个列表项
"""
    write_text_file(bad_cases_dir / "ocr_noise.md", ocr_noise)

    missing_heading = """# 一级标题

这是正文内容。

### 三级标题（跳过了二级）

这是三级标题下的内容。

##### 五级标题（跳过了四级）

内容继续。
"""
    write_text_file(bad_cases_dir / "missing_heading.md", missing_heading)

    logger.info("已生成 Bad Case 文件")
    logger.info("测试数据生成完成！")


if __name__ == "__main__":
    main()

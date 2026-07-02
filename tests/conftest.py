"""pytest 全局 fixtures"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.config import AppConfig


@pytest.fixture
def project_root() -> Path:
    """项目根目录"""
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def fixtures_dir() -> Path:
    """测试数据目录"""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def bad_cases_dir() -> Path:
    """Bad Case 测试数据目录"""
    return Path(__file__).resolve().parent / "fixtures" / "bad_cases"


@pytest.fixture
def default_config() -> AppConfig:
    """默认配置"""
    return AppConfig.load()


@pytest.fixture
def sample_markdown() -> str:
    """示例 Markdown 文本（模拟 MinerU 输出）"""
    return """# 国家标准示例

## 1 范围

本标准规定了党政机关公文的格式要求。适用于各级党政机关制发的公文。

## 2 规范性引用文件

下列文件对于本文件的应用是必不可少的。

<table>
<tr><th>序号</th><th>标准编号</th><th>标准名称</th></tr>
<tr><td>1</td><td>GB/T 9704-2012</td><td>党政机关公文格式</td></tr>
<tr><td>2</td><td>GB/T 7713-1987</td><td>科学技术报告编写格式</td></tr>
</table>

## 3 术语和定义

### 3.1 公文

党政机关实施领导、履行职能、处理公务的具有特定效力和规范体式的文书。

### 3.2 版心尺寸

公文用纸的图文区域尺寸，标准为 156mm × 225mm。

## 4 格式要求

正文使用仿宋_GB2312 三号字体，每页 22 行，每行 28 个字。

公式示例：

$$E = mc^2$$

行内公式：$\\alpha + \\beta = \\gamma$

![图1](images/figure1.png)
"""


@pytest.fixture
def sample_style_config_dict() -> dict:
    """示例样式配置字典"""
    return {
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
                "font": {"family": "黑体", "size_pt": 22, "bold": True},
                "alignment": "center",
                "line_spacing": 2.0,
            },
            {
                "level": 2,
                "font": {"family": "黑体", "size_pt": 16, "bold": True},
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
            "border_style": "single",
            "border_width_pt": 0.5,
            "header_font": {"family": "黑体", "size_pt": 12, "bold": True},
            "body_font": {"family": "仿宋_GB2312", "size_pt": 10.5},
            "header_bold": True,
        },
        "rag_sources": ["国标排版规范_v2.0_第3章"],
    }

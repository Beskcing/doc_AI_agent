# 样式提取提示词

你是一个国标排版规范专家。请根据以下信息和检索到的排版规范，生成完整的排版样式配置。

## 文档信息

- 文档类型：{document_type}
- 适用标准：{detected_standard}
- 特殊元素：{special_elements}

## RAG 检索到的排版规范

{rag_context}

## 样式生成要求

请生成完整的排版样式 JSON 配置，包含以下部分：

### 1. 页面布局 (page_layout)
- 纸张大小（默认 A4）
- 页边距（上/下/左/右，单位厘米）
- 页眉/页脚距离

### 2. 标题样式 (heading_styles)
- 各级标题的字体、字号、对齐方式
- 标题编号格式

### 3. 正文样式 (body_style)
- 字体（如仿宋_GB2312）、字号（如三号/16pt）
- 行距、首行缩进

### 4. 表格样式 (table_style)
- 边框样式和线宽
- 表头字体（加粗）
- 表格正文字体

### 5. RAG 来源 (rag_sources)
- 引用的规范文档名称

## 输出格式

请输出严格的 JSON 格式，不要添加任何解释性文字或代码块标记。所有尺寸单位使用磅（pt），页边距使用厘米（cm）。

示例结构：
```json
{
  "page_layout": {
    "paper_size": "A4",
    "margin_top_cm": 3.7,
    "margin_bottom_cm": 3.5,
    "margin_left_cm": 2.8,
    "margin_right_cm": 2.6
  },
  "heading_styles": [
    {
      "level": 1,
      "font": {"family": "黑体", "size_pt": 22, "bold": true},
      "alignment": "center",
      "line_spacing": 2.0
    }
  ],
  "body_style": {
    "font": {"family": "仿宋_GB2312", "size_pt": 16},
    "line_spacing": 1.5,
    "first_line_indent_chars": 2,
    "alignment": "justify"
  },
  "table_style": {
    "border_style": "single",
    "border_width_pt": 0.5,
    "header_font": {"family": "黑体", "size_pt": 12, "bold": true},
    "body_font": {"family": "仿宋_GB2312", "size_pt": 10.5},
    "header_bold": true
  },
  "rag_sources": ["国标排版规范_v2.0"]
}
```

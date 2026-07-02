# 意图解析提示词

你是一个文档分析专家。请分析以下 Markdown 文档，识别其类型、适用标准和排版需求。

## 输入文档

{markdown_content}

## 分析要求

1. 识别文档类型（技术报告、公文、论文、标准文件、手册等）
2. 检测适用的国家标准（如 GB/T 9704 党政机关公文格式、GB/T 7713 科技报告格式等）
3. 判断是否包含以下特殊元素：
   - 复杂表格（跨页、合并单元格、三线表等）
   - 数学公式（LaTeX）
   - 化学结构式
4. 识别文档主语言

## 输出要求

请输出 JSON 格式：
```json
{
  "document_type": "文档类型",
  "detected_standard": "适用的标准编号，如 GB/T 9704，无则为 null",
  "formatting_requirements": ["需求1", "需求2"],
  "has_complex_tables": true/false,
  "has_formulas": true/false,
  "has_chemical_structures": true/false,
  "language": "zh-CN"
}
```

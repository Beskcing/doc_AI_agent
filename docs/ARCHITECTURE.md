# 架构设计文档

## 系统概述

企业级国标文档排版智能体（Document Formatting Agent）是一个自动化文档处理系统，负责将 MinerU 解析的国标扫描件 Markdown 文件转化为符合国标排版规范的 Word 文档。

## 核心设计原则

1. **架构解耦（防幻觉铁律）**：LLM 只输出结构化数据（JSON/Markdown），严禁直接生成 Word XML 或 python-docx 代码
2. **RAG 驱动**：排版规范通过向量知识库检索，确保参数准确无幻觉
3. **管线化**：工作流由 LangGraph 编排，每个节点职责单一、可独立测试

## 技术栈

| 组件 | 技术 | 职责 |
|------|------|------|
| 工作流编排 | LangGraph | 状态机驱动的多步工作流 |
| LLM | Qwen / GLM | 意图分析、内容审查、样式提取 |
| 向量数据库 | Chroma | 排版规范知识库存储 |
| 检索 | BM25 + 向量 (RRF) | 混合检索确保专有名词精确命中 |
| PDF 解析 | MinerU | PDF → Markdown（含 OCR） |
| 格式转换 | Pandoc | Markdown → DOCX |
| 样式渲染 | python-docx | 应用国标排版样式 |

## 工作流状态图

```
parse_input → analyze_intent → review_content → extract_style → validate_output
                                                                    │
                                                       ┌────────────┼────────────┐
                                                       ▼            ▼            ▼
                                                   render_docx   retry(≤3)   handle_failure
                                                       │
                                                      END
```

## 数据流

```
PDF ──► MinerUParser ──► 原始 Markdown
                              │
                              ▼
                    HTMLTablePreserver.protect()
                              │
                              ▼
                    IntentAnalysis (LLM + RAG)
                              │
                              ▼
                    MarkdownCleaner (规则 + LLM)
                              │
                              ▼
                    StyleExtraction (LLM + RAG)
                              │
                              ▼
                    JSON Schema 校验 (Pydantic)
                              │
                              ▼
                    PandocConverter (MD → DOCX)
                              │
                              ▼
                    DocxStyler (应用 StyleConfig)
                              │
                              ▼
                    HTMLTablePreserver.restore()
                              │
                              ▼
                         最终 Word 文档
```

## 模块结构

```
src/
├── config.py              # 全局配置加载器
├── llm_client.py          # LLM 统一调用封装
├── models/                # Pydantic 数据模型
│   ├── style_config.py    # 排版样式配置 Schema
│   └── document_schema.py # 文档结构数据模型
├── tools/                 # 工具链（纯 Python，无 LLM）
│   ├── mineru_parser.py   # MinerU PDF 解析
│   ├── html_table_preserver.py  # HTML 表格占位符保护
│   ├── markdown_cleaner.py      # Markdown 两阶段清洗
│   ├── pandoc_converter.py      # Pandoc 格式转换
│   └── docx_styler.py           # python-docx 样式渲染
├── rag/                   # RAG 知识库系统
│   ├── embedding_factory.py     # Embedding 模型工厂
│   ├── document_loader.py       # 规范文档加载器
│   ├── chunking_strategy.py     # 语义切片策略
│   ├── hybrid_retriever.py      # BM25+向量混合检索
│   └── knowledge_base_config.py # Chroma 知识库管理
├── workflows/             # LangGraph 工作流
│   ├── state.py           # 状态定义
│   ├── conditions.py      # 条件路由
│   └── doc_formatting_graph.py  # 主工作流
└── utils/                 # 工具函数
    ├── json_validator.py  # JSON Schema 校验
    ├── file_utils.py      # 文件 I/O
    └── logger.py          # 统一日志
```

## RAG 知识库

### 切片策略
- Chunk Size: 600-800 字符
- Overlap: 15%
- 优先按章节标题边界切分
- 保护专有名词（"仿宋_GB2312"、"OMML"等）不被截断

### 混合检索
- BM25 关键词检索（权重 0.3）：精确匹配专有名词
- Chroma 向量检索（权重 0.7）：语义相似性
- RRF (Reciprocal Rank Fusion) 分数融合

### 知识库内容
- GB/T 9704-2012 党政机关公文格式
- GB/T 7713-1987 科学技术报告编写格式
- 字体规范（仿宋_GB2312、黑体、楷体使用场景）
- 页面布局规范（A4 纸张、页边距、版心尺寸）
- 表格排版规范（三线表、边框样式）

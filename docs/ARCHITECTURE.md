# 架构设计文档

## 系统概述

企业级国标文档排版智能体（Document Formatting Agent）是一个多用户 SaaS 平台，自动化处理 PDF/Markdown 文档，通过 LLM + RAG 提取排版样式，生成符合国标规范的 Word 文档。系统支持内容编辑、排版审查、对话式排版、样式模板管理等完整工作流。

## 核心设计原则

1. **架构解耦（防幻觉铁律）**：LLM 只输出结构化数据（JSON/Markdown），严禁直接生成 Word XML 或 python-docx 代码
2. **RAG 驱动**：排版规范通过向量知识库检索，确保参数准确无幻觉
3. **管线化**：工作流由 LangGraph 编排，每个节点职责单一、可独立测试
4. **多用户隔离**：所有数据按 `user_id` 隔离，文件系统与数据库双维度隔离
5. **异步优先**：耗时任务通过 Celery 异步执行，支持任务取消与进度追踪

## 技术栈

| 组件 | 技术 | 职责 |
|------|------|------|
| 工作流编排 | LangGraph | 状态机驱动的多步工作流 |
| LLM | Qwen / GLM | 意图分析、内容审查、样式提取、全文审查 |
| 向量数据库 | Chroma | 排版规范知识库存储 |
| 检索 | BM25 + 向量 (RRF) | 混合检索确保专有名词精确命中 |
| PDF 解析 | MinerU | PDF → Markdown + DOCX（含 OCR / 公式识别） |
| 格式转换 | Pandoc | Markdown → DOCX（回退路径） |
| 样式渲染 | python-docx | 应用国标排版样式 |
| 后端框架 | FastAPI | REST API + JWT 认证 + 静态文件服务 |
| 前端 | React + Vite + Ant Design | SPA 单页应用 |
| 数据库 | SQLite / PostgreSQL | SQLAlchemy 2.0 ORM + Alembic 迁移 |
| 异步任务 | Celery + Redis / ThreadPoolExecutor | 异步管线执行（支持降级） |
| 认证 | JWT + bcrypt | 用户注册/登录/角色权限 |

## 系统架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (React + Vite)                       │
│  登录/注册 │ 任务管理 │ 内容编辑 │ 排版审查 │ 对话排版 │ 管理面板  │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP + JWT
┌──────────────────────────▼──────────────────────────────────────┐
│                     FastAPI REST API 层                          │
│  ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐ │
│  │  auth   │ │  tasks │ │ review │ │  chat  │ │   admin      │ │
│  │  认证   │ │  任务  │ │  审查  │ │  对话  │ │   管理       │ │
│  └─────────┘ └────────┘ └────────┘ └────────┘ └──────────────┘ │
│  ┌─────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌──────────────┐ │
│  │ upload  │ │templates│ │   kb   │ │ config │ │  formatters  │ │
│  │  上传   │ │  模板  │ │ 知识库 │ │  配置  │ │  格式注册表  │ │
│  └─────────┘ └────────┘ └────────┘ └────────┘ └──────────────┘ │
│                     限流中间件 (100 req/min)                      │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Service 业务层                               │
│  PipelineService │ ContentEditService │ DocxReviewService        │
│  PreviewService  │ TaskManager        │ ServiceDeps              │
└───────┬──────────────────┬────────────────────┬─────────────────┘
        │                  │                    │
┌───────▼───────┐  ┌──────▼───────┐  ┌────────▼────────┐
│  LangGraph    │  │  工具链       │  │  RAG 知识库      │
│  工作流引擎   │  │  tools/      │  │  Chroma + BM25   │
│  (管线模式)   │  │  (纯Python)  │  │  混合检索         │
└───────────────┘  └──────────────┘  └─────────────────┘
        │
┌───────▼───────────────────────────────────────────────────────┐
│  数据层                                                         │
│  SQLAlchemy ORM (9表) │ Alembic 迁移 │ 文件系统 (user_id 隔离) │
└────────────────────────────────────────────────────────────────┘
```

## 数据流

```
PDF/MD 输入
    │
    ▼
MinerU 解析 ──► 原始 Markdown + DOCX（含原始排版）
    │
    ▼
HTMLTablePreserver.protect() ──► HTML 表格占位符保护
    │
    ▼
IntentAnalysis (LLM + RAG) ──► 文档类型/标准号/特殊元素识别
    │
    ▼
MarkdownCleaner (规则 + LLM) ──► OCR 瑕疵清洗
    │
    ▼
ContentNormalizer ──► 日期合并/拆分标题合并/TOC删除/双空格修正
    │
    ▼
StyleExtraction (LLM + RAG + few-shot) ──► 样式 JSON 配置
    │
    ▼
JSON Schema 校验 (Pydantic) ──► 通过/重试(≤3次)/失败
    │
    ▼
文档渲染（优先 MinerU DOCX → DocxNormalizer → DocxStyler）
         （回退 Pandoc MD→DOCX → DocxStyler）
    │
    ▼
最终 Word 文档 + 清洗日志 + 样式报告
```

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

## 模块结构

```
src/
├── config.py                    # 全局配置加载器 (YAML + Pydantic)
├── llm_client.py                # LLM 统一调用封装 (多 Provider 支持)
│
├── api/                         # REST API 层
│   ├── main.py                  # FastAPI 应用入口 (CORS/限流/静态文件/SPA fallback)
│   ├── models.py                # API 请求/响应 Pydantic 模型
│   ├── middleware/
│   │   └── auth.py              # JWT 签发/验证 + bcrypt + 依赖注入
│   ├── routers/                 # 路由层 (10 个路由模块)
│   │   ├── auth.py              # 注册/登录/Token 刷新
│   │   ├── admin.py             # 管理员: 用户 CRUD / 级联删除
│   │   ├── upload.py            # 文件上传
│   │   ├── tasks.py             # 任务创建/查询/取消/下载
│   │   ├── review.py            # 排版审查: 快速审查/深度审查/修正
│   │   ├── chat.py              # 对话式排版
│   │   ├── templates.py         # 样式模板管理
│   │   ├── kb.py                # 知识库文档管理
│   │   ├── config.py            # 系统配置管理
│   │   └── formatters.py        # 格式规范注册表查询
│   └── services/                # 业务逻辑层
│       ├── service_deps.py      # 依赖注入容器 (LLM/RAG/配置)
│       ├── pipeline_service.py  # 管线编排服务
│       ├── pipeline_task.py     # Celery 异步任务 (ThreadPoolExecutor 降级)
│       ├── task_manager.py      # 任务状态管理
│       ├── content_edit_service.py  # 内容编辑服务 (Markdown/HTML → DOCX)
│       ├── docx_review_service.py   # 排版审查服务 (快速/深度审查 + 修正)
│       └── preview_service.py   # 预览服务
│
├── tools/                       # 工具链（纯 Python，无 LLM 调用）
│   ├── mineru_parser.py         # MinerU PDF 解析入口
│   ├── mineru_api_client.py     # MinerU 在线 API 客户端
│   ├── pandoc_converter.py      # Pandoc MD → DOCX 转换
│   ├── html_table_preserver.py  # HTML 表格占位符保护/还原
│   ├── html_to_pipe.py          # HTML → Pipe 格式转换
│   ├── markdown_cleaner.py      # Markdown 两阶段清洗 (规则 + LLM)
│   ├── content_normalizer.py    # Markdown 内容规整 (日期/标题/TOC)
│   ├── content_pattern_matcher.py   # 内容模式匹配 (正则规则库)
│   ├── docx_styler.py           # python-docx 国标样式渲染
│   ├── docx_style_extractor.py  # DOCX 样式提取
│   ├── docx_text_extractor.py   # DOCX 全文提取 (审查用)
│   ├── docx_normalizer.py       # DOCX 内容规整 (日期合并/标题合并)
│   ├── docx_review_marker.py    # 审查标记渲染 (HTML 标记版)
│   ├── gbt_docx_formatter.py    # GB/T 文档格式化工具
│   └── formatters/              # 格式规范注册系统
│       ├── base.py              # 格式规范基类
│       ├── registry.py          # 注册表 (自动发现 + 手动注册)
│       ├── gbt_1_1.py           # GB/T 1.1 格式规范实现
│       └── _example_custom.py   # 自定义格式规范示例
│
├── rag/                         # RAG 知识库系统
│   ├── embedding_factory.py     # Embedding 模型工厂 (DashScope/OpenAI)
│   ├── document_loader.py       # 规范文档加载器
│   ├── chunking_strategy.py     # 语义切片策略 (600-800字符/15%重叠)
│   ├── hybrid_retriever.py      # BM25+向量混合检索 (RRF 融合)
│   └── knowledge_base_config.py # Chroma 知识库管理
│
├── db/                          # 数据层
│   ├── database.py              # 数据库引擎/会话工厂
│   ├── session.py               # 会话管理
│   ├── models.py                # ORM 模型 (9 张表)
│   └── crud.py                  # CRUD 操作 (Task/User/Style/KB/Review 等)
│
├── models/                      # Pydantic 数据模型
│   ├── style_config.py          # 排版样式配置 Schema
│   └── document_schema.py       # 文档结构/意图分析模型
│
├── workflows/                   # LangGraph 工作流
│   ├── state.py                 # FormattingState 状态定义
│   ├── conditions.py            # 条件路由 (validate_output 分支)
│   └── doc_formatting_graph.py  # 主工作流图 (7 节点)
│
├── tasks/                       # 异步任务
│   ├── celery_app.py            # Celery 应用配置
│   └── pipeline_task.py         # 管线异步任务定义
│
└── utils/                       # 工具函数
    ├── logger.py                # 统一日志 (YAML 配置)
    ├── file_utils.py            # 文件 I/O + 用户目录隔离
    ├── json_validator.py        # JSON Schema 校验
    └── text_diff.py             # 文本差异比较
```

## 数据库模型

| 表名 | 模型 | 说明 |
|------|------|------|
| tasks | TaskModel | 排版任务（状态/进度/结果路径） |
| users | UserModel | 用户（username/password_hash/role/is_active） |
| style_templates | StyleTemplateModel | 样式模板（系统预置 + 个人，standard 字段绑定标准号） |
| chat_sessions | ChatSessionModel | 对话会话 |
| chat_messages | ChatMessageModel | 对话消息（含样式快照） |
| style_adjustment_history | StyleAdjustmentHistoryModel | 样式调整历史（few-shot 学习用） |
| kb_documents | KbDocumentModel | 知识库文档 |
| system_config | SystemConfigModel | 系统配置（单条记录） |
| task_reviews | TaskReviewModel | 任务审查结果（issues JSON） |

## 认证与权限

- **认证方式**：JWT Bearer Token + bcrypt 密码哈希
- **角色**：`user`（普通用户）/ `admin`（管理员）
- **依赖注入**：`get_current_user` / `get_current_admin` 从 Token 解析用户
- **数据隔离**：所有查询通过 `user_id` 过滤，文件按 `data/{uploads,output}/{user_id}/` 组织
- **管理员特权**：用户 CRUD（级联删除）、知识库管理、系统配置、全局任务视图

## 异步任务架构

```
API 请求 → Celery (Redis Broker) → Worker 执行管线
                │
                └── 降级: ThreadPoolExecutor (无 Redis 时自动切换)
```

- 任务状态实时更新（progress / current_step / status）
- 支持任务取消（Celery revoke / ThreadPoolExecutor future.cancel）
- 文件 I/O 按用户隔离

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

## 前端架构

```
frontend/src/
├── main.tsx           # 入口
├── App.tsx            # 路由配置 + 布局
├── pages/             # 页面组件 (10 个)
│   ├── LoginPage / RegisterPage      # 认证
│   ├── TaskListPage / TaskDetailPage # 任务管理
│   ├── ChatPage                      # 对话排版
│   ├── TemplatePage                  # 样式模板
│   ├── KnowledgeBasePage             # 知识库
│   ├── SystemConfigPage              # 系统配置
│   ├── AdminUsersPage                # 用户管理 (admin)
│   └── ProfilePage                   # 个人中心
├── components/        # 通用组件
├── services/api.ts    # API 调用封装 (axios + JWT 拦截器)
└── stores/            # 状态管理 (zustand)
```

## 部署架构

### Docker 部署
```
docker-compose.yml
├── backend   (FastAPI + Celery Worker)
├── frontend  (Nginx 静态文件)
├── postgres  (PostgreSQL)
├── redis     (Celery Broker)
└── nginx     (反向代理)
```

### 文件存储结构
```
data/
├── uploads/{user_id}/     # 用户上传文件
├── output/{user_id}/      # 排版输出文件
├── templates/             # 样式模板 DOCX
└── app.db                 # SQLite 数据库
```
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

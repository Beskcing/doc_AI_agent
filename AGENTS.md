# AGENTS.md - 国标文档排版智能体工程规范
 本仓库用于开发"企业级文档结构化与排版智能体"。人类负责定义意图、约束和审查标准；Agent 负责实现逻辑、编写工具代码、测试与文档维护。

## Product (产品定义)
构建一个高可用、零幻觉的企业级文档排版智能体：
 - 核心能力：解析 MinerU 输出的 Markdown，清洗 OCR 瑕疵，结合 RAG 规范库提取样式，最终生成符合国标要求的 Word 文档。
 - 技术栈：LangChain/LangGraph (编排) + Qwen/GLM (LLM) + MinerU/MarkItDown (解析) + Pandoc/python-docx (渲染) + FastAPI (Web API) + React/Ant Design (前端) + SQLite/SQLAlchemy (数据库)。
 - 知识库：基于向量数据库（Chroma）构建的排版规范 RAG 系统。

## Start Here (开发起点)
 - 架构设计：`docs/ARCHITECTURE.md`
 - 智能体提示词：`prompts/system_prompt.md`
 - 工作流定义：`src/workflows/doc_formatting_graph.py`
 - 工具链代码：`src/tools/` (包含 mineru_parser.py, mineru_api_client.py, pandoc_converter.py, docx_styler.py, markdown_cleaner.py, html_table_preserver.py)
 - RAG 知识库配置：`src/rag/knowledge_base_config.py`
 - Web API 服务：`src/api/main.py` (FastAPI 入口)
 - API 路由：`src/api/routers/` (upload.py, tasks.py, kb.py, config.py)
 - 数据库模型：`src/db/models.py` (TaskModel, KbDocumentModel, SystemConfigModel)
 - 前端项目：`frontend/` (React + Vite + TypeScript + Ant Design)
 - 后台任务管理：`src/api/services/task_manager.py`
 - 配置文件：`configs/settings.yaml`, `configs/llm_config.yaml`, `configs/logging.yaml`
 - 测试用例集：`tests/` (unit/ + bad_case/ + integration/ + e2e/)

## 启动方式
 - 后端 API 服务：`python -m scripts.run_server --port 8000 --reload`
 - 前端开发服务器：`cd frontend && npm run dev`
 - CLI 管线：`python -m scripts.run_pipeline --input doc.pdf --output output.docx`
 - 初始化 RAG 知识库：`python -m scripts.init_knowledge_base`
 - 运行测试：`python -m pytest tests/ -v`
 - E2E 测试：`python tests/e2e/test_e2e_full.py`

## Agent Operating Rules (智能体操作规则)
在协助开发此项目时，必须严格遵守以下工程规范：
1. 架构解耦原则（防幻觉铁律）：
 - 严禁让 LLM 直接生成 Word XML 或 python-docx 渲染代码。
 - LLM 只能输出结构化数据（JSON/Markdown），所有文件 I/O 和样式渲染必须由传统的 Python 工具函数执行。
2. RAG 集成规范：
 - 知识库切片（Chunking）必须保留语义完整性，技术文档建议 Chunk Size 设为 600-800，Overlap 设为 15%。
 - 必须实现混合检索（BM25 + 向量检索），确保专有名词（如"仿宋_GB2312"、"OMML"）精准命中。
 - 检索结果必须注入到 LLM 的上下文中，并在输出时提供来源追溯（rag_sources）。
3. 代码与测试规范：
 - 优先提交小型 Pull Request。
 - 任何涉及 MinerU 解析或 Pandoc 转换的代码修改，必须附带至少一个 PDF 测试用例。
 - 核心渲染函数（如 `apply_gb_style`）必须有单元测试覆盖主路径和异常路径。
 - 前端代码必须通过 TypeScript 编译（`tsc --noEmit`）无错误。
 - 后端 API 变更必须同步更新 E2E 测试（`tests/e2e/test_e2e_full.py`）。
4. 数据库规范：
 - 使用 SQLAlchemy 2.0 ORM，所有模型定义在 `src/db/models.py`。
 - CRUD 操作封装在 `src/db/crud.py`，路由层不直接操作数据库。
 - 数据库初始化在应用启动时自动执行（`init_db()`）。
5. 文档同步更新：
 - 行为或工具链发生变更时，必须同步更新 `AGENTS.md` 和相关文档。
 - 新增的排版规则需同步更新至 RAG 知识库。

## Definition of Done (完成标准)
 一个功能被视为"完成"，必须满足：
 - [ ] LLM 输出的 JSON 格式稳定，且能通过 JSON Schema 校验。
 - [ ] RAG 检索到的规范准确无误，无幻觉。
 - [ ] Pandoc 转换无报错，HTML 表格和 LaTeX 公式正确映射。
 - [ ] python-docx 成功应用样式，生成的 Word 文档通过人工或自动化排版校验。
 - [ ] 所有代码通过 Lint 检查，测试覆盖率达到 80% 以上。
 - [ ] 前端 TypeScript 编译无错误，生产构建成功。
 - [ ] E2E 测试全部通过（`python tests/e2e/test_e2e_full.py`）。
 - [ ] MinerU 线上 API 解析正常，Markdown 提取完整。
 - [ ] 数据库持久化正常，重启服务后数据不丢失。

## 项目结构
```
doc_ai_agent/
├── AGENTS.md                    # 工程规范（本文件）
├── docs/ARCHITECTURE.md         # 架构设计文档
├── pyproject.toml               # Python 项目配置
├── requirements.txt             # 依赖清单
├── .env.example                 # 环境变量模板
├── configs/                     # 配置文件
│   ├── settings.yaml            # 全局配置
│   ├── llm_config.yaml          # LLM Provider 配置
│   └── logging.yaml             # 日志配置
├── prompts/                     # LLM 提示词
│   ├── system_prompt.md
│   ├── intent_parsing_prompt.md
│   ├── content_review_prompt.md
│   └── style_extraction_prompt.md
├── src/
│   ├── config.py                # 配置加载器
│   ├── llm_client.py            # LLM 统一调用封装
│   ├── models/                  # Pydantic 数据模型
│   │   ├── style_config.py
│   │   └── document_schema.py
│   ├── tools/                   # 工具链
│   │   ├── mineru_parser.py     # PDF 解析器（online/local 双模式）
│   │   ├── mineru_api_client.py # MinerU 线上 API 客户端
│   │   ├── html_table_preserver.py
│   │   ├── markdown_cleaner.py
│   │   ├── pandoc_converter.py
│   │   └── docx_styler.py
│   ├── rag/                     # RAG 知识库
│   │   ├── embedding_factory.py
│   │   ├── document_loader.py
│   │   ├── chunking_strategy.py
│   │   ├── knowledge_base_config.py
│   │   └── hybrid_retriever.py
│   ├── workflows/               # LangGraph 工作流
│   │   ├── state.py
│   │   ├── conditions.py
│   │   └── doc_formatting_graph.py
│   ├── api/                     # FastAPI Web API
│   │   ├── main.py              # 应用入口
│   │   ├── models.py            # API 数据模型
│   │   ├── routers/             # API 路由
│   │   │   ├── upload.py
│   │   │   ├── tasks.py
│   │   │   ├── kb.py
│   │   │   └── config.py
│   │   └── services/
│   │       └── task_manager.py  # 后台任务管理
│   ├── db/                      # 数据库
│   │   ├── database.py          # 连接和会话
│   │   ├── models.py            # ORM 模型
│   │   └── crud.py              # CRUD 封装
│   └── utils/                   # 工具函数
│       ├── logger.py
│       ├── json_validator.py
│       └── file_utils.py
├── frontend/                    # React 前端项目
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── components/
│       │   └── AppLayout.tsx    # 企业后台管理布局
│       ├── pages/
│       │   ├── Dashboard.tsx    # 工作台
│       │   ├── UploadPage.tsx   # 文档上传
│       │   ├── TasksPage.tsx    # 任务管理
│       │   ├── TaskDetailPage.tsx
│       │   ├── KbPage.tsx       # 知识库管理
│       │   └── ConfigPage.tsx   # 系统配置
│       ├── services/
│       │   └── api.ts           # API 请求封装
│       └── stores/
│           └── appStore.ts      # Zustand 状态管理
├── scripts/                     # 脚本
│   ├── run_pipeline.py          # CLI 管线入口
│   ├── run_server.py            # API 服务启动
│   ├── init_knowledge_base.py   # 知识库初始化
│   └── generate_test_data.py    # 测试数据生成
├── knowledge_data/
│   └── raw_docs/                # 排版规范原始文档
├── tests/                       # 测试
│   ├── conftest.py
│   ├── unit/                    # 单元测试
│   ├── bad_case/                # Bad Case 回归测试
│   ├── integration/             # 集成测试
│   └── e2e/                     # 端到端测试
└── data/                        # 运行时数据
    ├── app.db                   # SQLite 数据库
    ├── uploads/                 # 上传文件
    └── output/                  # 输出文件
```

## MinerU 解析配置

PDF 解析支持两种模式，通过 `configs/settings.yaml` 中 `mineru.mode` 配置：

| 模式 | 说明 | 依赖 |
|------|------|------|
| `online` (默认) | 调用 MinerU 线上精准解析 API，无需本地安装 SDK | `requests`，需配置 `MINERU_API_TOKEN` |
| `local` | 使用本地 MinerU (magic-pdf) SDK 解析 | `magic-pdf` (可选依赖) |

### 环境变量
- `MINERU_API_TOKEN`: MinerU 线上 API Token，从 https://mineru.net/apiManage 获取

### 模型版本
- `vlm` (默认): 视觉语言模型，推荐使用
- `pipeline`: 默认管道模型
- `MinerU-HTML`: HTML 文件专用

### API 客户端
- `src/tools/mineru_api_client.py`: 封装线上 API 全流程（上传→轮询→下载ZIP→提取Markdown）
- `src/tools/mineru_parser.py`: 统一解析器入口，支持 online/local 双模式切换
# AGENTS.md - 国标文档排版智能体工程规范

企业级文档结构化与排版智能体：解析 MinerU 输出的 Markdown → 清洗 OCR 瑕疵 → RAG 检索排版规范 → LLM 提取样式 → 生成国标 Word 文档。

## 技术栈
LangChain/LangGraph (编排) + Qwen/GLM (LLM) + MinerU (PDF解析) + Pandoc/python-docx (渲染) + FastAPI (API) + React/Ant Design (前端) + SQLite/SQLAlchemy (DB) + Chroma (RAG向量库)

## 启动方式
- Docker 部署：`docker compose up -d`（构建并启动前后端）
- 后端 API：`python -m scripts.run_server --port 8000`
- 前端开发：`cd frontend && npm run dev`
- CLI 管线：`python -m scripts.run_pipeline --input doc.pdf --output output.docx`
- 初始化 RAG：`python -m scripts.init_knowledge_base`
- 运行测试：`python -m pytest tests/ -v`

## 关键路径
- 工作流：`src/workflows/doc_formatting_graph.py` | LLM 封装：`src/llm_client.py`
- 工具链：`src/tools/` (mineru_parser, pandoc_converter, docx_styler, markdown_cleaner, html_table_preserver)
- RAG：`src/rag/` | API：`src/api/` | DB：`src/db/` | 前端：`frontend/`
- 提示词：`prompts/` | 配置：`configs/settings.yaml` | 架构文档：`docs/ARCHITECTURE.md`

## 工程规范

1. **架构解耦（防幻觉铁律）**：LLM 只输出 JSON/Markdown，文件 I/O 和样式渲染由 Python 工具函数执行，严禁 LLM 生成 Word XML。
2. **RAG 集成**：Chunk Size 600-800 / Overlap 15%，必须混合检索（BM25 + 向量），输出提供 rag_sources 来源追溯。
3. **代码与测试**：MinerU/Pandoc 改动须附 PDF 测试用例，核心渲染函数须有单元测试，前端须通过 `tsc --noEmit`，API 变更同步更新 E2E 测试。
4. **数据库**：SQLAlchemy 2.0 ORM，模型在 `src/db/models.py`，CRUD 在 `src/db/crud.py`，路由层不直接操作 DB。
5. **文档同步**：行为/工具链变更时更新 AGENTS.md，新增排版规则更新至 RAG 知识库。
6. **Git 提交（强制）**：每次变更后 `git add -A` + `git commit`（前缀 `feat:/fix:/refactor:/docs:`）+ 更新 AGENTS.md + `git push origin master`。远程：`https://github.com/Beskcing/doc_AI_agent.git`
7. **变更前讨论（强制）**：每次想要修改或增加功能时，必须先与用户讨论方案、达成一致后，方可开始编码。严禁未经讨论直接动手改代码。

## MinerU 配置
通过 `configs/settings.yaml` 的 `mineru.mode` 切换：`online`（默认，线上 API，需 `MINERU_API_TOKEN`）或 `local`（magic-pdf SDK）。模型版本默认 `vlm`。客户端：`src/tools/mineru_api_client.py`，统一入口：`src/tools/mineru_parser.py`。

### 完成标准
- LLM JSON 输出通过 Schema 校验，RAG 检索无幻觉
- Pandoc 转换无报错，HTML 表格/LaTeX 公式正确映射
- python-docx 样式应用成功，文档通过排版校验
- 测试覆盖率 ≥ 90%，E2E 全部通过
- 前端 TypeScript 编译无错误，MinerU 解析正常，DB 持久化正常

## 变更记录

| 日期 | 类型 | 摘要 |
|------|------|------|
| 2026-07-07 | fix | TinyMCE v8配置项名称修正: font_family_formats/font_size_formats/toolbar fontsize按钮(非fontsizeselect) |
| 2026-07-07 | fix | TinyMCE toolbar按钮名称从fontsize改为fontsizeselect+空格分隔fontsize_formats格式显示中文字号 |
| 2026-07-07 | fix | SPA fallback拦截API路由修复(main.py路由顺序)+init_db空迁移表修复 |
| 2026-07-07 | test | Loop Engineering Docker全测试: API 59/62通过(95.2%)+前端7页浏览器自动化全通过 |
| 2026-07-07 | feat | 工程化P0: llm_client重试+超时+LLMResponse token计数+流式输出+CLI管线同步PipelineService |
| 2026-07-07 | refactor | 工程化P1: 路由层2大SessionLocal清理为get_db_session+配置Schema校验+Alembic迁移初始化 |
| 2026-07-07 | feat | 工程化P2: Ruff lint全通过+pre-commit hooks+全局异常处理+Dockerfile |
| 2026-07-07 | feat | 工程化P3: GitHub Actions CI+限流中间件+Makefile |
| 2026-07-07 | feat | Docker多阶段构建+前端编译+python:3.12-slim+pandoc+docker-compose一键启动+后端SPA静态文件挂载 |
| 2026-07-07 | config | LLM Provider从Qwen切换为智谱AI(GLM-4)，默认模型glm-4 |
| 2026-07-07 | fix | 对话LLM失败时自动回滚孤立用户消息，ChatMessageCRUD新增delete方法 |
| 2026-07-07 | feat | html_to_pipe支持colspan/rowspan合并单元格 |
| 2026-07-07 | perf | hybrid_retriever _find_doc_index O(n)→O(1)哈希索引 |
| 2026-07-07 | fix | markdown_cleaner 分段LLM审查+全角标点保留 |
| 2026-07-07 | feat | docx_styler 5种新角色处理(封面/前言/附录标题/附录条款/表格标题)+内容模式识别后备 |
| 2026-07-07 | refactor | TaskManager 门面拆分：新增PipelineService/PreviewService/ContentEditService/ServiceDeps+DB会话管理器，1742→300行 |
| 2026-07-06 | feat | PDF对比预览+分页加载(109页PDF响应从55MB降至1MB) |
| 2026-07-06 | fix | Loop Engineering V6全面测试82项98.8%通过 |
| 2026-07-06 | feat | 文档内容编辑(TinyMCE富文本+LLM对话修改+双模式) |
| 2026-07-06 | feat | 四大智能排版(修正DOC/自动匹配模板/调整回写/迭代学习) |
| 2026-07-06 | feat | 模板管理页+样式修正+附录样式分离 |
| 2026-07-06 | fix | React 19+antd v5兼容补丁+上传文件名修复 |
| 2026-07-03 | feat | 多轮对话+上下文窗口管理(状态压缩法) |
| 2026-07-03 | feat | 对话排版+模板上传提取+模板CRUD |
| 2026-07-03 | feat | MinerU原始DOCX优先管线+批量上传+样式提取全面增强 |
| 2026-07-03 | fix | 全栈测试6个Bug修复(Loop Engineering首轮) |

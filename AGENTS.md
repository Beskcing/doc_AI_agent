# AGENTS.md - 国标文档排版智能体工程规范

企业级文档结构化与排版智能体：解析 MinerU 输出的 Markdown → 清洗 OCR 瑕疵 → RAG 检索排版规范 → LLM 提取样式 → 生成国标 Word 文档。

## 技术栈
LangChain/LangGraph (编排) + Qwen/GLM (LLM) + MinerU (PDF解析) + Pandoc/python-docx (渲染) + FastAPI (API) + React/Ant Design (前端) + SQLite/SQLAlchemy (DB) + Chroma (RAG向量库)

## 启动方式
- 后端 API：`python -m scripts.run_server --port 8000 --reload`
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

## MinerU 配置
通过 `configs/settings.yaml` 的 `mineru.mode` 切换：`online`（默认，线上 API，需 `MINERU_API_TOKEN`）或 `local`（magic-pdf SDK）。模型版本默认 `vlm`。客户端：`src/tools/mineru_api_client.py`，统一入口：`src/tools/mineru_parser.py`。

## 完成标准
- [ ] LLM JSON 输出通过 Schema 校验，RAG 检索无幻觉
- [ ] Pandoc 转换无报错，HTML 表格/LaTeX 公式正确映射
- [ ] python-docx 样式应用成功，文档通过排版校验
- [ ] 测试覆盖率 ≥ 80%，E2E 全部通过
- [ ] 前端 TypeScript 编译无错误，MinerU 解析正常，DB 持久化正常

## 变更记录

| 日期 | 类型 | 摘要 |
|------|------|------|
| 2026-07-03 | fix | Web API 路径接入真实 LLM 调用：新增意图分析/LLM样式提取/RAG检索，替换硬编码模拟数据，启用 Markdown 两阶段 LLM 智能审查 |
| 2026-07-03 | fix | 修复预览内容截断：完整 cleaned.md 文件持久化，DOCX→HTML 改轻量 fragment，前端移除高度限制 |
| 2026-07-03 | feat | 新增任务删除、Word 预览（DOCX→HTML iframe）、Markdown 完整渲染（react-markdown + remark-gfm） |
| 2026-07-03 | fix | 全栈测试修复：RAG raw_docs_dir 属性缺失、HTML 表格占位符被 LLM 清除（改用纯文本标记+跳过含占位符的 LLM 审查）、Pandoc TeX math \tag 不支持、DOCX 预览图片 404（--embed-resources）、前端时间格式化（dayjs）、配置页浮点精度 |
| 2026-07-03 | fix | 安装 dashscope SDK，RAG 知识库混合检索（BM25+向量）完全打通 |

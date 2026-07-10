# AGENTS.md - 国标文档排版智能体工程规范

企业级文档结构化与排版智能体：解析 MinerU 输出的 Markdown → 清洗 OCR 瑕疵 → RAG 检索排版规范 → LLM 提取样式 → 生成国标 Word 文档。

**多用户 SaaS 架构**：支持用户注册/登录（JWT + bcrypt），基于角色的权限控制（user/admin），用户级数据隔离（文件系统 + DB），管理员可管理用户账号及全局数据。

## 技术栈
LangChain/LangGraph (编排) + Qwen/GLM (LLM) + MinerU (PDF解析) + Pandoc/python-docx (渲染) + FastAPI (API) + React/Ant Design (前端) + SQLite/PostgreSQL (DB) + SQLAlchemy 2.0 ORM + Chroma (RAG向量库) + Celery + Redis (异步任务) + JWT + bcrypt (认证) + Alembic (迁移)

## 启动方式
- Docker 部署：`docker compose up -d`（构建并启动前后端 + PostgreSQL + Redis + Celery）
- 后端 API：`python -m scripts.run_server --port 8000`
- 前端开发：`cd frontend && npm run dev`
- CLI 管线：`python -m scripts.run_pipeline --input doc.pdf --output output.docx`
- 初始化 RAG：`python -m scripts.init_knowledge_base`
- Celery Worker：`python -m scripts.run_worker`（异步任务队列）
- 数据库迁移：`alembic upgrade head`
- 运行测试：`python -m pytest tests/ -v`

> **首次使用**：系统默认无用户，需手动创建管理员账号。Web UI 支持注册或通过 API 创建。默认管理员：`admin / Admin@123`（如已删除需重新创建）。

## 关键路径
- 工作流：`src/workflows/doc_formatting_graph.py` | LLM 封装：`src/llm_client.py`
- 工具链：`src/tools/` (mineru_parser, pandoc_converter, docx_styler, gbt_docx_formatter, markdown_cleaner, html_table_preserver, content_normalizer, content_pattern_matcher, docx_normalizer)
- Formatter 注册系统：`src/tools/formatters/` (base/registry/gbt_1_1, 支持用户通过 Python 脚本注册自定义格式规范)
- 格式规范分类匹配：`src/db/crud.py` StyleTemplateCRUD.match_by_standard() 三级策略(精确→模糊→名称), 模板 standard 字段显式绑定标准号
- RAG：`src/rag/` | API：`src/api/` (含 formatters 路由查询注册表) | DB：`src/db/` | 前端：`frontend/`
- 认证鉴权：`src/api/middleware/auth.py` (JWT签发/验证 + bcrypt密码 + get_current_user/get_current_admin 依赖注入)
- 管理员路由：`src/api/routers/admin.py` (用户CRUD/级联删除, get_current_admin 保护)
- 用户数据隔离：`src/utils/file_utils.py` (按 user_id 目录隔离上传/输出) | `src/db/crud.py` UserCRUD (级联删除)
- 异步任务：`src/api/services/celery_app.py` + `src/api/services/pipeline_task.py` (Celery + ThreadPoolExecutor 降级)
- 提示词：`prompts/` | 配置：`configs/settings.yaml` | 文档：`docs/USER_GUIDE.md` (使用) `docs/DEV_GUIDE.md` (开发) `docs/ARCHITECTURE.md` (架构)

## 工程规范

1. **架构解耦（防幻觉铁律）**：LLM 只输出 JSON/Markdown，文件 I/O 和样式渲染由 Python 工具函数执行，严禁 LLM 生成 Word XML。
2. **RAG 集成**：Chunk Size 600-800 / Overlap 15%，必须混合检索（BM25 + 向量），输出提供 rag_sources 来源追溯。
3. **多用户隔离**：所有用户数据通过 `user_id` 隔离，文件系统按 `data/{uploads,output}/{user_id}/` 组织，路由层通过 `get_current_user` 依赖注入自动过滤。管理员通过 `role == "admin"` 获得全局视图。
4. **代码与测试**：MinerU/Pandoc 改动须附 PDF 测试用例，核心渲染函数须有单元测试，前端须通过 `tsc --noEmit`，API 变更同步更新 E2E 测试。
5. **数据库**：SQLAlchemy 2.0 ORM，模型在 `src/db/models.py`（含 8 张表：tasks/chat_sessions/chat_messages/style_templates/style_adjustment_history/kb_documents/system_config/users），CRUD 在 `src/db/crud.py`，路由层不直接操作 DB。
6. **文档同步**：行为/工具链变更时更新 AGENTS.md，新增排版规则更新至 RAG 知识库。
7. **Git 提交（强制）**：每次变更后 `git add -A` + `git commit`（前缀 `feat:/fix:/refactor:/docs:`）+ 更新 AGENTS.md + `git push origin master`。远程：`https://github.com/Beskcing/doc_AI_agent.git`
8. **变更前讨论（强制）**：每次想要修改或增加功能时，必须先与用户讨论方案、达成一致后，方可开始编码。严禁未经讨论直接动手改代码。
9. **测试文件不入库**：`tests/` 目录下的测试文件、fixtures、分析脚本、E2E 用例均不纳入 Git 版本管理。测试文件仅供本地开发调试使用。

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
| 2026-07-09 | feat | 磁盘管理与清理: 新增GET /api/tasks/disk-usage + POST /api/tasks/cleanup API + 前端Dashboard磁盘用量卡片+清理按钮 + MinerU解压后自动删除冗余_origin.pdf + debug.keep_intermediate_files配置控制中间产物保留 |
| 2026-07-09 | fix | 补全GB/T 1.1标准选项: StandardOption新增GBT_1_1 + config API新增GB/T 1.1 + 前端默认选择GB/T 1.1 + CLI默认标准改为GB/T 1.1, 解决用户无法选择GB/T 1.1导致排版降级DocxStyler的问题 |
| 2026-07-09 | feat | 知识库文档查看/编辑功能: 新增GET/PUT /api/kb/content/{doc_id} API + 前端KbPage查看编辑弹窗 + SPA fallback改用404异常处理器解决路由冲突 |
| 2026-07-08 | fix | Loop Engineering V7全面测试: 修复Formatters路由SPA fallback拦截+create_task文件校验+TemplatesPage stale state, 新增74项自动化测试 |
| 2026-07-08 | fix | TaskDetailPage修正样式React State时序Bug修复(inline API调用避免stale closure) |
| 2026-07-08 | fix | TemplatesPage手动创建extractedConfig空指针崩溃修复(添加null校验+友好提示) |
| 2026-07-07 | fix | TinyMCE v8配置项名称修正: font_family_formats/font_size_formats/toolbar fontsize按钮(非fontsizeselect) |
| 2026-07-07 | fix | TinyMCE toolbar按钮名称从fontsize改为fontsizeselect+空格分隔fontsize_formats格式显示中文字号 |
| 2026-07-07 | fix | SPA fallback拦截API路由修复(main.py路由顺序)+init_db空迁移表修复 |
| 2026-07-07 | test | Loop Engineering Docker全测试: API 59/62通过(95.2%)+前端7页浏览器自动化全通过 |
| 2026-07-07 | feat | 工程化P0: llm_client重试+超时+LLMResponse token计数+流式输出+CLI管线同步PipelineService |
| 2026-07-07 | refactor | 工程化P1: 路由层2大SessionLocal清理为get_db_session+配置Schema校验+Alembic迁移初始化 |
| 2026-07-07 | feat | 工程化P2: Ruff lint全通过+pre-commit hooks+全局异常处理+Dockerfile |
| 2026-07-07 | feat | 工程化P3: GitHub Actions CI+限流中间件+Makefile |
| 2026-07-07 | feat | Docker多阶段构建+前端编译+python:3.12-slim+pandoc+docker-compose一键启动+后端SPA静态文件挂载 |
| 2026-07-08 | feat | DocxNormalizer: DOCX层内容规整(日期合并/拆分标题合并/TOC删除/双空格修正), MinerU DOCX优先+Pandoc降级 |
| 2026-07-08 | feat | gbt技能内联：新增content_normalizer(日期合并/标题合并/TOC删除/双空格)+DocxStyler增强(图片居中/docDefaults/新角色) |
| 2026-07-08 | feat | Formatter注册系统: BaseDocxFormatter基类+Registry自动发现+标准号映射, 用户添加Python脚本即可注册新格式规范 |
| 2026-07-08 | fix | Pipeline自动匹配模板Bug修复: 注册Formatter标准跳过模板匹配, 避免绕过GbtDocxFormatter路径 |
| 2026-07-07 | config | LLM Provider从Qwen切换为智谱AI(GLM-4)，默认模型glm-4 |
| 2026-07-08 | feat | 格式规范分类重构: StyleTemplateModel添加standard字段+Alembic迁移+三级匹配策略(精确→模糊→名称)+模板CRUD支持标准号+文件名智能推断 |
| 2026-07-08 | feat | Pipeline路由优先级显式化: 手动选择>Formatter>自动匹配模板, applied_format来源追溯记录(formatter/template/llm) |
| 2026-07-08 | feat | 前端TemplatesPage样式编辑器增强: 新增段落格式面板(行距类型/段间距/缩进/分页控制)+封面/前言/附录面板可编辑(字体/字号/加粗/对齐) |
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
| 2026-07-09 | feat | 管理员账号创建(admin/Admin@123) + 遗留任务文件迁移到admin目录 + 测试数据清理 |
| 2026-07-09 | feat | Nginx 反向代理配置 (nginx.conf) — 支持自定义域名部署 + HTTPS/SSL |
| 2026-07-09 | feat | 管理员功能补全: 用户账号管理API(CRUD/重置密码/禁用/级联删除) + 管理员全局数据视图(tasks/chat/stats/disk-usage路由admin分支) |
| 2026-07-09 | docs | 文档全面更新: AGENTS.md(多用户SaaS架构/技术栈/关键路径) + USER_GUIDE.md(账号认证章节/管理员功能章节) + DEV_GUIDE.md(SaaS多用户开发模式/认证鉴权/Celery异步/Frontend认证) |

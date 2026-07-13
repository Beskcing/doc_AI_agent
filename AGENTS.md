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
- 工具链：`src/tools/` (mineru_parser / pandoc_converter / docx_styler / gbt_docx_formatter / markdown_cleaner / content_normalizer / docx_normalizer / docx_text_extractor 等)
- Formatter 注册系统：`src/tools/formatters/` (base/registry/gbt_1_1, 支持用户通过 Python 脚本注册自定义格式规范)
- 格式规范分类匹配：`src/db/crud.py` StyleTemplateCRUD.match_by_standard() 三级策略(精确→模糊→名称), 模板 standard 字段显式绑定标准号
- RAG：`src/rag/` | API：`src/api/` (含 formatters 路由查询注册表) | DB：`src/db/` | 前端：`frontend/`
- 认证鉴权：`src/api/middleware/auth.py` (JWT签发/验证 + bcrypt密码 + get_current_user/get_current_admin 依赖注入)
- 管理员路由：`src/api/routers/admin.py` (用户CRUD/级联删除, get_current_admin 保护)
- 用户数据隔离：`src/utils/file_utils.py` (按 user_id 目录隔离上传/输出) | `src/db/crud.py` UserCRUD (级联删除)
- 异步任务：`src/api/services/celery_app.py` + `src/api/services/pipeline_task.py` (Celery + ThreadPoolExecutor 降级)
- 排版后审查：`src/api/services/docx_review_service.py` (DocxReviewService) | `src/api/routers/review.py` | `src/utils/text_diff.py` | `src/tools/docx_text_extractor.py`
- 提示词：`prompts/` | 配置：`configs/settings.yaml` | 文档：`docs/` (USER_GUIDE / DEV_GUIDE / ARCHITECTURE)

## 工程规范

1. **架构解耦（防幻觉铁律）**：LLM 只输出 JSON/Markdown，文件 I/O 和样式渲染由 Python 工具函数执行，严禁 LLM 生成 Word XML。
2. **RAG 集成**：Chunk Size 600-800 / Overlap 15%，必须混合检索（BM25 + 向量），输出提供 rag_sources 来源追溯。
3. **多用户隔离**：所有用户数据通过 `user_id` 隔离，文件系统按 `data/{uploads,output}/{user_id}/` 组织，路由层通过 `get_current_user` 依赖注入自动过滤。管理员通过 `role == "admin"` 获得全局视图。
4. **代码与测试**：MinerU/Pandoc 改动须附 PDF 测试用例，核心渲染函数须有单元测试，前端须通过 `tsc --noEmit`，API 变更同步更新 E2E 测试。
5. **数据库**：SQLAlchemy 2.0 ORM，模型在 `src/db/models.py`（含 9 张表：tasks/chat_sessions/chat_messages/style_templates/style_adjustment_history/kb_documents/system_config/users/task_reviews），CRUD 在 `src/db/crud.py`，路由层不直接操作 DB。
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

> 完整变更历史见 `docs/DEV_GUIDE.md`

| 日期 | 类型 | 摘要 |
|------|------|------|
| 2026-07-13 | perf | 审查标记HTML预览性能优化: DocxReviewService增加类级别_html_cache缓存, generate_marked_html首次生成后缓存结果, 修正/重新审查操作自动清除缓存, 后续切换Tab响应<100ms |
| 2026-07-13 | feat | 内容编辑改用排版后DOCX: ContentEditService.get_content_html改用task.result_path(formatted_styled.docx), 前端按钮文字从'MinerU原始'改为'排版后' |
| 2026-07-13 | fix | 审查标记HTML预览tooltip修复: 将tooltip内容从HTML格式改为纯文本(\n换行), CSS white-space改为pre-line, 解决attr(data-tooltip)双转义导致显示原始标签的问题; 同步移除_build_marked_html中未使用的type_colors和severity_colors变量 |
| 2026-07-13 | fix | 审查标记面板补全latex类型: issueTypeColors/issueTypeLabels添加latex:'LaTeX残留'(cyan), 两个审查Tab的筛选下拉框均补全latex选项 |
| 2026-07-13 | feat | 审查标记与AI修正完整实现: DocxReviewMarker(DOCX黄色高亮+Word批注+lxml注入comments.xml+zip打包), HTML标记预览API(带tooltip气泡+postMessage点击联动), 标记版DOCX下载(FileResponse+JWT认证), 单条/批量AI修正API(_idx索引映射), 重新审查API(POST requick), 前端独立「审查标记与修正」Tab(左侧iframe预览60%+右侧问题列表40%+筛选排序+AI修正/手动修改/忽略按钮+批量修正+重新审查) |
| 2026-07-12 | feat | 深度审查新增LaTeX公式残留审查维度: _QUICK_CHECK_PATTERNS添加50+个LaTeX命令正则(含$$/$分隔符/常用命令/希腊字母/环境/字体/运算符/修饰符), _build_summary新增latex_residue统计字段, 表格内LaTeX也能被审查覆盖 |
| 2026-07-10 | fix | TinyMCE编辑器无法加载: main.py新增/tinymce静态文件挂载, 修复SPA fallback拦截导致返回index.html而非JS的问题 |
| 2026-07-10 | fix | DOCX下载失败(401): TaskDetailPage下载改用fetch+Blob携带JWT token, 替换window.open(不会带Authorization头) |
| 2026-07-10 | feat | 管理员用户管理前端页面: AdminUsersPage(表格+创建/编辑弹窗+删除+启用禁用) + api.ts 4个管理API + App路由/admin/users + AppLayout菜单集成 |
| 2026-07-10 | fix | Docker Alembic迁移修复: env.py通过DATABASE_URL环境变量覆盖alembic.ini硬编码SQLite, 容器内alembic正确连接PostgreSQL |
| 2026-07-10 | fix | Docker部署依赖补全: pyproject.toml添加psycopg2-binary/celery/redis/bcrypt |
| 2026-07-10 | fix | quick_review Unicode检测正扩充合法字符范围(拉丁/希腊/数学符号等), 消除技术文档100%误报 |
| 2026-07-10 | feat | 排版后LLM全文审查: DocxTextExtractor+TextDiff+DocxReviewService(quick_review+deep_review)+TaskReviewModel+前端审查面板 |
| 2026-07-09 | feat | 知识库文档查看/编辑: GET/PUT /api/kb/content API + 前端弹窗编辑器 |

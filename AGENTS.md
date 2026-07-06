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
| 2026-07-03 | feat | 批量上传/批量解析、MinerU原始DOCX预览、管线改用MinerU原始DOCX作为样式基础（非PDF回退Pandoc）、去除MD转Word主步骤（保留代码） |
| 2026-07-03 | feat | 新增 MinerU 原始 DOCX 下载功能：解析时请求 extra_formats=["docx"]，任务完成后可下载 MinerU 原始排版 DOCX |
| 2026-07-03 | fix | 全栈测试修复：RAG raw_docs_dir 属性缺失、HTML 表格占位符被 LLM 清除（改用纯文本标记+跳过含占位符的 LLM 审查）、Pandoc TeX math \tag 不支持、DOCX 预览图片 404（--embed-resources）、前端时间格式化（dayjs）、配置页浮点精度 |
| 2026-07-03 | fix | 安装 dashscope SDK，RAG 知识库混合检索（BM25+向量）完全打通 |
| 2026-07-03 | feat | 新增对话排版模式：LLM对话修改样式+表单编辑器、Word模板上传与格式提取(docx_style_extractor)、样式模板管理(CRUD+DB持久化)、模板应用于新任务和已有任务 |
| 2026-07-03 | fix | Loop Engineering 全面测试修复6个Bug：Bug#1上传原始文件名丢失(改用.meta元数据文件)、Bug#2知识库同名文件覆盖(改用UUID存储)、Bug#3知识库删除不清理物理文件、Bug#4知识库重建索引空操作(接入真实KB初始化)、Bug#5任务列表轮询间隔不随状态变化、Bug#6任务详情终态后仍高频轮询+下载文件名修复 |
| 2026-07-03 | feat | 新增多轮对话+上下文窗口管理：ChatSession/ChatMessage DB持久化、会话CRUD API、LLMClient多轮消息支持、上下文窗口状态压缩法(最近N轮+token预算截断)、前端会话列表侧栏+历史恢复+新建/切换/删除会话 |
| 2026-07-03 | feat | 全面增强DOCX样式提取：读取doc.styles样式定义表作为基线、修复东亚字体提取路径(rPr/rFonts)、多段落采样取最常见样式、完整表格边框(6边)/对齐/背景色/四边内边距/表头跨页重复/垂直对齐、新增list_style/footnote_style/caption_style/header_footer_style提取、段落格式新增左右缩进/keep_together/widow_control/行距类型 |
| 2026-07-03 | fix | Loop Engineering 全面功能测试修复6个Bug：Bug#1 apply-template/DOCX预览同步阻塞FastAPI事件循环(改用run_in_threadpool)、Bug#2 KB文档chunk_count始终为0(从retriever.documents metadata统计)、Bug#3 KB上传文档status误设为indexed(改为pending)、Bug#4 Dashboard每次轮询显示loading闪烁(仅首次加载显示)、Bug#5 preview端点不必要的update_status空调用(移除) |
| 2026-07-06 | fix | Loop Engineering 全面测试修复3个Bug：Bug#1 取消任务竞态条件(update_status阻止processing覆盖cancelled+_process_task开头检查cancelled+异常处理检查cancelled)、Bug#2 _default_style_config()键名与StyleConfig模型不匹配(body→body_style/heading→heading_styles/table→table_style/字体值改为FontConfig字典)、Bug#3 test_full_manual.py轮询超时太短(120s→360s)；修正test_bugfix_verify.py键名检查(body→body_style)；新增test_chat_template.py和test_cancel_race.py测试脚本 |
| 2026-07-06 | fix | 修复前端按钮全部失效：React 19与antd v5不兼容导致onClick事件不触发，安装@ant-design/v5-patch-for-react-19兼容补丁(main.tsx引入)；修复UploadPage上传按钮originFileObj为undefined静默返回(f.originFileObj ?? f) |
| 2026-07-06 | feat | 新增Word文档样式模板提取：从GB/T 14454.13-2008CN.docx提取完整排版模板(封面/前言/1~5级条款/正文/表格/列表/注释/页眉页脚)，基于内容模式+格式特征推断条款层级，输出StyleConfig兼容JSON |
| 2026-07-06 | feat | 新增模板注册脚本(scripts/register_template.py)：将预提取JSON模板通过API注册到DB，创建任务时可指定template_id跳过LLM样式提取 |
| 2026-07-06 | feat | 新增模板管理页面(TemplatesPage)：模板列表/上传docx提取/查看详情/编辑样式配置(JSON+表单)/删除；侧边栏新增「模板管理」菜单(/templates)；任务详情页新增「修正样式」功能(加载当前style_config→表单/JSON编辑→重新渲染DOCX) |
| 2026-07-06 | fix | 增强DocxStyleExtractor样式提取完整性：新增内容模式识别标题级别(正则匹配国标条款编号1~5级)、新增封面/前言样式提取方法、正文采样排除封面和标题段落避免污染；ChatPage样式编辑器新增封面/前言可编辑面板 |
| 2026-07-06 | fix | 修正附录样式提取：附录标题(加粗)与普通一级标题(不加粗)分离为独立样式、新增附录内条款识别(A.1/B.1字母前缀)、新增表格标题样式(表B.1居中)、正文采样排除附录标题/条款/表格标题段落；模板JSON新增appendix_title_style/appendix_clause_style/table_caption_style |
| 2026-07-06 | feat | 四大智能排版能力上线：①用户直接修正DOC(下载DOCX→Word手动修改→重新上传→DocxStyleExtractor提取样式→重新渲染)；②自动匹配模板(意图解析阶段检测标准号→DB中按数字关键词匹配模板→自动跳过LLM提取)；③调整回写(修正样式Modal新增「保存到模板」按钮→更新已有模板或另存为新模板)；④迭代学习(DB新增style_adjustment_history表记录每次调整前后的diff→LLM样式提取提示词注入历史调整few-shot示例→AI持续学习用户偏好) |
| 2026-07-06 | fix | Loop Engineering 真实数据全流程测试修复3个Bug：Bug#1 task_manager.py中template_id变量未定义先使用(NameError导致任务必定失败→将template_id=config.get('template_id')移至自动匹配模板逻辑之前)、Bug#2 run_server.py缺少reload_excludes配置(MinerU输出文件触发watchfiles频繁重载导致任务中断→排除data/knowledge_data/logs/frontend/tests/__pycache__目录)、Bug#3 知识库API缺少stats和search路由(新增GET /api/kb/stats统计接口+POST /api/kb/search混合检索接口+前端api.ts同步新增getKbStats/searchKb)；新增KbSearchRequest模型；24项全流程验证测试全部通过 |
| 2026-07-06 | fix | Loop Engineering 深度测试46项全部通过(100%)：修复Bug#1 Markdown预览大文件卡死浏览器(react-markdown直接渲染400KB+内容阻塞主线程→截断到50000字符+Alert提示文档较大+建议下载Word获取完整内容)；新增test_deep_loop.py深度测试脚本覆盖8大功能模块(上传→任务流程/模板管理/对话排版/知识库/批量操作/样式修正/任务管理/系统配置) |
| 2026-07-06 | feat | 新增文档内容编辑功能：①后端内容更新API(GET/PUT /api/tasks/{task_id}/content，支持Markdown/HTML双格式输入，保存并重新生成DOCX)；②HTML内容接口(GET /api/tasks/{task_id}/content/html，Pandoc Markdown→HTML供富文本编辑器加载)；③LLM对话修改内容(POST /api/chat/content，LLM根据用户指令修改Markdown内容并重新渲染DOCX)；④前端TinyMCE富文本编辑器(DocEditor组件，Word风格所见即所得，支持标题/字体/表格/列表编辑)；⑤TaskDetailPage新增「内容编辑」Tab(Markdown编辑/DOC富文本编辑双模式切换)；⑥ChatPage新增「内容编辑」模式(与样式编辑并列，选择任务后通过LLM对话修改文档内容)；⑦改进Pandoc转换(生成reference.docx模板+--reference-doc+--standalone参数)；14项E2E测试全部通过 |
| 2026-07-06 | fix | Loop Engineering 真实PDF全流程测试48项全部通过(100%)：修复Bug#1 LLM对话内容编辑大文档JSON截断(update_content_via_llm将402911字符完整内容注入提示词导致LLM输出超出token限制→大文档>10000字符改用diff模式：仅发送文档首尾摘要+用户指令，LLM输出append/replace/insert操作指令，后端应用diff修改；小文档保留全量模式；JSON解析失败时回退为追加模式)；新增test_loop_v4.py测试脚本覆盖15大功能模块(健康检查/配置/上传/任务生命周期/预览下载/内容编辑/模板CRUD/应用模板/保存样式/对话排版/对话内容/知识库/任务管理/批量任务/清理) |
| 2026-07-06 | fix | 前端全页面浏览器实测修复4个Bug：Bug#1 TinyMCE npm包import(tinymce/themes/silver/theme等)在模块加载时访问未定义的tinymce全局变量导致页面空白崩溃→移除所有npm import仅用tinymceScriptSrc从public目录加载+DocEditor改用React.lazy懒加载；Bug#2 TinyMCE不存在的undoeditor插件引用→移除(undo/redo为内置功能)；Bug#3 知识库页面创建时间显示原始ISO格式(2026-07-06T14:03:59.669158)→添加dayjs格式化render；Bug#4 antd v5 Spin的tip属性在无children时警告→改为Spin+独立div文本布局(TaskDetailPage/ChatPage/TemplatesPage三处修复) |
| 2026-07-06 | refactor | 内容编辑流程重构：PDF解析后不再使用Pandoc转换生成DOCX。①get_content_html改为优先加载MinerU原始DOCX→HTML(保留原始排版)，回退cleaned.md→HTML；②新增_html_to_docx方法使用htmldocx库(HTML→DOCX无需Pandoc)，失败回退Pandoc(_html_to_docx_pandoc)；③update_content Markdown模式改为使用MinerU原始DOCX作为基础(不再调用_convert_to_docx/Pandoc)，仅重新应用样式；④update_content_via_llm同样改为MinerU DOCX作为基础；⑤前端按钮文案区分模式(Markdown/DOC)、新增Alert说明编辑流程、ChatPage提示信息更新；⑥新增htmldocx>=0.0.6依赖 |

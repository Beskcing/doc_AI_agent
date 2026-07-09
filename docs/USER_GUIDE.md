# 国标文档排版智能体 — 使用文档

## 一、系统概述

国标文档排版智能体是一款企业级 PDF → 国标 Word 全自动排版系统。上传 PDF 文件，选择排版规范，系统自动完成解析、清洗、样式提取、渲染，输出符合国标格式的 Word 文档。

**多用户 SaaS**：支持用户注册/登录，每人独立数据（任务、对话、模板），管理员可管理全部用户及全局数据。

### 核心能力

| 能力 | 说明 |
|------|------|
| PDF 解析 | MinerU 引擎，支持 OCR、表格、公式识别，输出 Markdown + 原始 DOCX |
| 内容清洗 | 规则预处理 + LLM 智能审查，修正 OCR 瑕疵、合并拆分标题、删除 TOC |
| 样式渲染 | 三条路径：硬编码 Formatter / 模板驱动 / LLM 生成，按条件自动路由 |
| 格式规范 | 内置 GB/T 1.1 硬编码 Formatter，支持模板注册扩展任意标准 |
| 对话编辑 | 多轮对话 + TinyMCE 富文本编辑器，AI 辅助调整内容 |
| 多用户 | 注册/登录，JWT 认证，数据隔离，管理员全局管理 |

### 三条排版路径速览

```
用户上传 PDF + 选择标准
          │
          ├── 选了 GB/T 1.1 + 无模板 ──→ GbtDocxFormatter 硬编码（最精准）
          │
          ├── 选了模板 ──→ 模板样式驱动 DocxStyler（模板优先）
          │
          └── 其他标准 + 无模板 ──→ LLM + RAG 生成样式（通用兜底）
```

## 二、账号与登录

### 2.1 注册

首次使用需要注册账号：

1. 访问 `http://localhost:8000`，自动跳转登录页
2. 点击「立即注册」
3. 填写用户名（3-20 位字母数字下划线）和密码（8-64 位，含大小写字母和数字）
4. 注册成功后自动登录

### 2.2 登录

输入已注册的用户名和密码，点击「登录」。Token 有效期 30 分钟，过期后需重新登录。

### 2.3 默认管理员

系统预置管理员账号：

| 用户名 | 密码 | 角色 |
|--------|------|------|
| `admin` | `Admin@123` | 管理员 |

管理员可查看所有用户的任务、对话、模板，并可管理用户账号（创建/重置密码/禁用/删除）。详见第十节。

> 如管理员账号不存在，可通过后端 API 创建：
> ```python
> python -c "from src.db.crud import UserCRUD; from src.db.session import get_db_session; from src.api.middleware.auth import hash_password; db=get_db_session().__enter__(); UserCRUD.create(db, 'admin', hash_password('Admin@123'), 'admin')"
> ```

### 2.4 角色与权限

| 角色 | 任务 | 对话 | 模板 | 知识库 | 系统配置 | 用户管理 |
|------|:---:|:---:|:---:|:---:|:---:|:---:|
| **user** (普通用户) | 自己的 | 自己的 | 自己的 | 只读 | 不可见 | 不可见 |
| **admin** (管理员) | 全局 | 全局 | 全部 | 管理 | 管理 | 管理 |

### 2.5 数据隔离说明

系统基于 `user_id` 实现严格的多用户数据隔离：

- **数据库**：所有业务表（tasks/chat_sessions/chat_messages/style_templates/style_adjustment_history）均按 `user_id` 过滤，每个用户仅能看到自己的数据
- **文件系统**：上传文件存储于 `data/uploads/{user_id}/`，输出文件存储于 `data/output/{user_id}/{task_id}/`，互不可见
- **管理员特权**：管理员（`role=admin`）不受 `user_id` 过滤限制，可查看和操作所有用户的数据
- **全局共享**：`kb_documents`（知识库文档）和 `system_config`（系统配置）为全局表，所有用户共享，不属于任何用户

---

## 三、快速上手

### 3.1 环境要求

| 组件 | 要求 |
|------|------|
| Python | 3.10+ |
| Node.js | 18+ |
| Pandoc | 3.1+（Docker 已内置） |
| MinerU | API Token（`.env` 中配置 `MINERU_API_TOKEN`） |

### 3.2 启动方式

**Docker 一键启动（推荐）：**

```bash
docker compose up -d
```

- 后端 API：`http://localhost:8000`
- 前端界面：`http://localhost:8000`（SPA 由后端托管）
- API 文档：`http://localhost:8000/docs`

**手动开发启动：**

```bash
# 终端 1：后端
pip install -r requirements.txt
python -m scripts.run_server --port 8000

# 终端 2：前端
cd frontend
npm install
npm run dev
```

前端开发服务器：`http://localhost:5173`

### 3.3 第一次排版（Web UI）

1. 打开浏览器访问 `http://localhost:8000`
2. **注册或登录**（首次使用需先注册账号）
3. 点击左侧「上传排版」菜单
3. 拖入 PDF 文件（支持批量），点击「上传」
4. 在配置面板中：
   - **排版规范**：选择「标准化工作导则 (GB/T 1.1)」
   - **样式模板**：留空（不选）
   - **使用 RAG 知识库**：关掉（GB/T 1.1 路径不需要）
   - **LLM 模型**：默认 `glm-4`
5. 点击「提交任务」
6. 跳转到任务列表页，等待处理完成
7. 点击任务查看结果，下载排版后的 Word 文档

### 3.4 CLI 快速排版

```bash
# 基本用法
python -m scripts.run_pipeline --input doc.pdf --output output.docx

# 指定标准
python -m scripts.run_pipeline --input doc.pdf --standard "GB/T 1.1"

# 同时输出样式配置 JSON 和清洗后 Markdown
python -m scripts.run_pipeline \
  --input doc.pdf \
  --output output.docx \
  --standard "GB/T 1.1" \
  --output-json style.json \
  --output-markdown cleaned.md

# 仅提取样式不渲染（调试用）
python -m scripts.run_pipeline --input doc.md --skip-render --output-json style.json

# 指定 LLM Provider
python -m scripts.run_pipeline --input doc.pdf --provider glm

# 禁用 RAG
python -m scripts.run_pipeline --input doc.pdf --no-rag
```

**CLI 参数说明：**

| 参数 | 简写 | 必填 | 默认值 | 说明 |
|------|------|:---:|--------|------|
| `--input` | `-i` | Y | — | 输入文件（PDF 或 Markdown） |
| `--output` | `-o` | N | `data/output/output.docx` | 输出 Word 文件路径 |
| `--standard` | `-s` | N | `GB/T 1.1` | 目标标准编号 |
| `--provider` | `-p` | N | 配置文件默认值 | LLM Provider（qwen / glm） |
| `--config` | `-c` | N | `configs/settings.yaml` | 配置文件路径 |
| `--output-json` | — | N | — | 额外输出 style_config JSON |
| `--output-markdown` | — | N | — | 额外输出清洗后 Markdown |
| `--skip-render` | — | N | — | 跳过渲染（仅输出 JSON/Markdown） |
| `--no-rag` | — | N | — | 禁用 RAG 知识库 |
| `--verbose` | `-v` | N | — | 详细日志输出 |

---

## 四、标准选择与排版路径

### 4.1 三条路径对比

| 特性 | Formatter 硬编码 | 模板驱动 | LLM + RAG |
|------|:---:|:---:|:---:|
| **触发条件** | GB/T 1.1 + 无模板 + PDF输入 | 选择了模板 | 其他标准 + 无模板 |
| **样式来源** | `gbt_1_1.py` 硬编码 | 模板 DOCX 提取的 JSON | LLM 根据 RAG 检索结果生成 |
| **精准度** | 最高（无幻觉） | 取决于模板质量 | 取决于 LLM + RAG 覆盖度 |
| **可定制** | 需修改 Python 代码 | 上传任意 DOCX | 调整 Prompt + 知识库 |
| **RAG 依赖** | 不依赖 | 不依赖 | 建议开启 |
| **applied_format** | `"source": "formatter"` | `"source": "template"` | `"source": "llm"` |

### 4.2 GB/T 1.1 正确操作步骤

确保走 Formatter 硬编码路径（最精准），必须同时满足三个条件：

1. ✅ **输入 PDF 文件**（非 Markdown）
2. ✅ **排版规范选「标准化工作导则 (GB/T 1.1)」**
3. ✅ **不选样式模板**（留空）

> ⚠️ 如果选了 `custom` 或选了模板，管线将降级到 DocxStyler/LLM 路径，排版效果不可控。

**验证是否走对路径：** 排版完成后查看任务详情，`applied_format` 字段应为：

```json
{
  "source": "formatter",
  "name": "GB/T 1.1 标准化工作导则",
  "id": "gbt_1.1"
}
```

如果是 `{"source": "llm"}`，说明条件不满足，未走 Formatter 路径。

### 4.3 选择模板的操作步骤

1. 先在「模板管理」页面上传并保存模板（参考第四节）
2. 在「上传排版」页面的「样式模板」下拉框中选择模板
3. 排版规范可任意选择（模板优先级高于标准选择）

> ⚠️ 选择模板后，管线不走 Formatter，格式完全由模板决定。适合没有注册 Formatter 的标准。

### 4.4 选择知识库（RAG）的作用

知识库仅在 **LLM + RAG 路径** 有效（其他标准 + 无模板 + 无 Formatter）。RAG 检索排版规范片段作为 LLM Prompt 上下文，帮助 LLM 生成更准确的样式参数。

**当前不需要知识库的场景：**
- GB/T 1.1（Formatter 硬编码）
- 选了模板（模板驱动）

**需要知识库的场景：**
- 排 GB/T 9704 或 GB/T 7713 文档，且无模板可用

知识库内容在 `knowledge_data/raw_docs/` 目录，运行以下命令初始化：

```bash
python -m scripts.init_knowledge_base
```

---

## 五、模板管理

### 5.1 上传 DOCX 提取样式

1. 访问「模板管理」页面
2. 点击「上传模板」按钮，选择 `.docx` 文件
3. 系统自动调用 `DocxStyleExtractor` 提取样式配置
4. 弹出创建弹窗，预填模板名称（从文件名推断）和标准号

**系统提取的内容：**

| 样式类别 | 提取内容 |
|----------|----------|
| 页面布局 | 纸张大小、上下左右边距、页眉页脚距离、页码格式 |
| 封面样式 | 字体、字号、加粗、对齐 |
| 前言样式 | 同上 |
| 标题样式 | 1~6 级标题的字体、字号、加粗、缩进 |
| 正文样式 | 字体、字号、行距、首行缩进、对齐 |
| 表格样式 | 边框样式、宽度、颜色、对齐、表头重复 |
| 附录样式 | 附录标题、附录条款格式 |
| 段落格式 | 行距类型（固定/最小/多倍）、段前段后、左右缩进、分页控制 |

**提取原理：** 直接读取 DOCX 底层 XML（`w:rPr`/`w:pPr` 等元素），无 LLM 参与，保证精度。多段落采样取众数，避免单一段落偏差。

### 5.2 编辑器面板说明

上传提取后，弹出编辑面板包含以下可折叠区域：

- **页面布局**：纸张类型、四边距
- **封面样式**：字体、字号、加粗、对齐
- **前言样式**：同上
- **附录标题 / 附录条款**：同上
- **各级标题**：1~N 级标题分别编辑
- **正文样式**：字体、字号、行距、首行缩进、对齐
- **表格样式**：边框、对齐
- **段落格式**：行距类型（固定值/最小值/多倍行距）、段间距、左右缩进、分页控制
- **原始 JSON**：直接编辑 JSON 配置

用户可以逐项检查和调整，确认无误后保存。

### 5.3 保存与应用模板

1. 在编辑弹窗中填写模板名称、描述、标准号
2. 点击「保存」
3. 模板出现在列表中，可在「上传排版」页面的下拉框中选择使用

### 5.4 CLI 批量注册模板

当有预提取好的样式 JSON 文件时，可通过 `scripts/register_template.py` 批量注册：

```bash
# 前提：后端已启动
python scripts/register_template.py
```

脚本读取 `data/templates/GB_T_14454_13_2008_style.json`，通过 API 保存到数据库。如需批量注册多个模板，修改脚本中的路径和名称，或编写循环脚本遍历目录。

---

## 六、知识库管理

### 6.1 知识库的作用

知识库是基于 Chroma 向量数据库的排版规范检索系统。它仅在 **LLM + RAG 路径**（无 Formatter、无模板）发挥作用：

- 从排版规范原文中检索相关段落
- 作为 LLM Prompt 的上下文注入
- 帮助 LLM 生成符合规范的样式参数

### 6.2 添加排版规范文档

1. 将国标排版规范文档（Markdown 格式）放入 `knowledge_data/raw_docs/` 目录
2. 运行初始化脚本重建向量索引：

```bash
python -m scripts.init_knowledge_base
```

### 6.3 检索配置

在 `configs/settings.yaml` 中配置：

```yaml
rag:
  chroma_path: "knowledge_data/chroma_db"
  collection_name: "formatting_standards"
  chunk_size: 700              # 文档分块大小（字符）
  chunk_overlap_ratio: 0.15    # 分块重叠比例
  embedding_provider: "dashscope"
  embedding_model: "text-embedding-v3"
  top_k: 5                     # 检索返回条数
  bm25_weight: 0.3             # BM25 检索权重
  vector_weight: 0.7           # 向量检索权重
```

混合检索（BM25 + 向量，RRF 融合）确保专有名词精确命中。

---

## 七、对话排版

在「对话排版」页面，可以通过自然语言与 AI 交互调整文档格式：

- 上传 DOCX 文件作为参考模板
- 描述想要的格式效果（如"正文用宋体 10.5pt 两端对齐首行缩进 2 字符"）
- AI 解析意图后生成样式配置
- 支持多轮对话逐步细化

对话过程中提取的样式配置可以保存为模板，后续在普通排版中使用。

---

## 八、文档内容编辑

### 8.1 双模式编辑

排版完成后，在任务详情页可直接编辑文档内容：

- **富文本模式**：TinyMCE 所见即所得编辑器，支持中文排版
- **对话模式**：用自然语言描述修改意图，AI 执行修改

### 8.2 对比预览

任务详情页提供 PDF 原始文件与排版结果的并排对比，支持：

- 分页加载（大型文档按需取页，减少内存占用）
- 同步滚动
- 页码导航

---

## 九、管理员功能

### 9.1 用户管理 API

管理员通过 API 管理用户账号（前端管理页面后续上线）：

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/users` | 分页列出所有用户 |
| `POST` | `/api/admin/users` | 创建新用户 |
| `PUT` | `/api/admin/users/{id}` | 更新用户（重置密码/禁用/改角色） |
| `DELETE` | `/api/admin/users/{id}` | 删除用户及级联数据 |

**创建用户示例：**

```bash
# 获取管理员 token
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin@123"}'

# 用返回的 token 创建用户
curl -X POST http://localhost:8000/api/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"username":"newuser","password":"Pass1234","role":"user"}'
```

**重置密码示例：**

```bash
curl -X PUT http://localhost:8000/api/admin/users/<USER_ID> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{"password":"NewPass567"}'
```

### 9.2 管理员全局视图

管理员登录后，前端页面自动展示全局数据：

- **工作台**：全局任务统计（全部用户汇总）
- **任务列表**：所有用户的任务
- **对话列表**：所有用户的会话
- **磁盘用量**：全局磁盘占用

### 9.3 安全限制

- 普通用户访问 `/api/admin/*` 返回 403
- 不可删除管理员账号
- 禁用用户无法登录（即时生效）
- `kb_documents` 和 `system_config` 为全局共享，删除用户不影响

---

## 十、常见问题

### Q1: 排版结果不符合预期

按以下顺序排查：

1. **确认走的路径**：查看 `applied_format` 字段
   - `"source": "formatter"` → 检查标准是否选对
   - `"source": "template"` → 检查模板样式是否正确
   - `"source": "llm"` → 说明条件不满足，降级了

2. **Formater 路径问题**：
   - 确认为 PDF 输入（非 Markdown）
   - 确认标准选了 `GB/T 1.1`（非 `custom`）
   - 确认未选择模板

3. **模板路径问题**：
   - 在模板管理页查看提取的样式是否准确
   - 检查模板 DOCX 源文件格式是否规范

### Q2: 模板提取的样式不准确

- 模板 DOCX 本身格式必须规范（所有正文段落格式一致）
- 提取器取多段落众数，如果正文混用多种格式，结果可能不准
- 上传后在编辑面板中逐项检查并修正

### Q3: MinerU 解析失败

- 检查 `.env` 中 `MINERU_API_TOKEN` 是否正确
- 检查 PDF 文件是否损坏（尝试用浏览器打开）
- 查看日志 `logs/doc_ai_agent.log`

### Q4: 如何确认走了正确的路径

排版完成后，在任务详情中查看配置信息：

```json
// 正确：Formatter 路径
"applied_format": {
  "source": "formatter",
  "name": "GB/T 1.1 标准化工作导则",
  "id": "gbt_1.1"
}

// 正确：模板路径
"applied_format": {
  "source": "template",
  "name": "我的模板",
  "id": "xxx-xxx-xxx"
}

// 降级：LLM 路径
"applied_format": {
  "source": "llm"
}
```

### Q5: 前端报 TypeScript 编译错误

```bash
cd frontend
npm run tsc -- --noEmit
```

常见原因：antd 版本与 React 19 兼容性问题，已在项目中打补丁修复。

### Q6: 如何指定 LLM 模型

Web UI 在「上传排版」页面的「LLM 模型」下拉框中选择。CLI 通过 `--provider` 参数指定。

当前支持的 provider：
- `glm`：智谱 AI GLM-4（默认）
- `qwen`：通义千问 Plus

### Q7: Docker 部署后前端无法访问

确认 `docker-compose.yml` 中后端挂载了前端 `dist` 目录，且 `main.py` 中 SPA fallback 路由在 API 路由之后。

### Q8: 管理员账号密码忘了怎么办

通过 Python 命令行重置：

```bash
python -c "from src.db.crud import UserCRUD; from src.db.session import get_db_session; from src.api.middleware.auth import hash_password; db=get_db_session().__enter__(); UserCRUD.update(db, '<ADMIN_ID>', password_hash=hash_password('NewPass123'))"
```

### Q9: 如何创建额外的管理员

通过管理员 API：

```bash
curl -X POST http://localhost:8000/api/admin/users \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -d '{"username":"admin2","password":"AdminPass456","role":"admin"}'
```

### Q10: Windows 下运行 Python 脚本中文乱码

在脚本首行添加 `# -*- coding: utf-8 -*-` 编码声明。

# 国标文档排版智能体 — 迭代优化文档

## 一、架构总览

### 1.1 模块依赖图

```
┌─────────────────────────────────────────────────────────────────┐
│                        前端 (React + Ant Design)                 │
│  LoginPage / AuthGuard / AppLayout (role-based menu)            │
│  UploadPage / TasksPage / ChatPage / TemplatesPage / KbPage     │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP REST API (JWT Bearer)
┌──────────────────────────▼──────────────────────────────────────┐
│                    FastAPI 路由层                                │
│  routers/auth.py   routers/admin.py   routers/upload.py         │
│  routers/review.py   routers/tasks.py  routers/chat.py              │
│  routers/templates.py  routers/kb.py   routers/config.py            │
│  routers/formatters.py                                              │
│                                                                  │
│  middleware/auth.py — JWT verify / get_current_user/admin       │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     服务层                                       │
│  PipelineService ── 核心排版流程                                 │
│  PreviewService  ── PDF/DOCX 预览                                │
│  ContentEditService ── 文档内容编辑 (MD/HTML → DOCX 合并)        │
│  DocxReviewService ── 排版审查 (快速规则 + 深度 LLM)            │
│  TaskManager     ── 任务状态管理 + 异步分发                      │
│  ServiceDeps     ── LLM/RAG/Prompts 依赖注入                     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     工具链                                       │
│  mineru_parser │ docx_style_extractor │ docx_styler              │
│  gbt_docx_formatter │ markdown_cleaner │ pandoc_converter       │
│  content_normalizer │ html_table_preserver │ docx_normalizer    │
│  formatters/ ── 可扩展 Formatter 注册系统                        │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   基础设施                                       │
│  LLM Client (GLM-4/Qwen) │ RAG (Chroma + BM25)                  │
│  DB (SQLite/PostgreSQL)  │ Celery + Redis (异步)                │
│  JWT + bcrypt (认证)     │ Alembic (迁移)                        │
│  LangGraph 工作流         │ 用户隔离文件系统                     │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 数据流全景

```
PDF 文件
   │
   ▼
MinerUParser (PDF → Markdown + 原始DOCX)
   │
   ├──→ mineru_docx_path (关键！决定是否走 Formatter 路径)
   │
   ▼
IntentAnalysis (LLM: 识别文档类型/标准/特殊元素)
   │
   ▼
MarkdownCleaner (规则 + LLM 审查 + ContentNormalizer)
   │
   ▼
┌── Style Extraction ──┐
│  有模板 → 读DB模板JSON │
│  无模板 → LLM+RAG生成  │  ← 结果可能被 Formatter 覆盖
└──────────────────────┘
   │
   ▼
┌── 管线路由 (pipeline_service.py L148-217) ──┐
│                                               │
│  有 mineru_docx?                               │
│    ├── 无模板 + 有注册Formatter → Formatter    │
│    ├── 无模板 + 无Formatter     → DocxStyler   │
│    └── 有模板                   → DocxStyler   │
│                                               │
│  无 mineru_docx?                               │
│    └── Pandoc降级 → DocxStyler                 │
└───────────────────────────────────────────────┘
   │
   ▼
DocxStyler / GbtDocxFormatter → 输出 DOCX
   │
   ▼
最终 Word 文档
```

### 1.3 管线路由优先级

```
手动选择模板  >  注册 Formatter  >  自动匹配模板  >  LLM 生成
     │                │                  │              │
  "template"      "formatter"        "template"       "llm"
```

路由逻辑位于 `src/api/services/pipeline_service.py` 的 `process_task()` 方法（L91-233）。

### 1.4 关键文件索引

| 文件 | 职责 |
|------|------|
| `src/api/services/pipeline_service.py` | 核心管线路由 + 所有排版分支 |
| `src/api/services/celery_app.py` | Celery 应用配置（Redis broker/backend） |
| `src/api/services/pipeline_task.py` | Celery 异步任务（含 ThreadPoolExecutor 降级） |
| `src/api/middleware/auth.py` | JWT 认证中间件（签发/验证/依赖注入） |
| `src/api/routers/auth.py` | 用户注册/登录/Token 刷新 API |
| `src/api/routers/admin.py` | 管理员 API（用户 CRUD + 级联删除） |
| `src/db/crud.py` | 数据访问层（含 UserCRUD / TaskCRUD / ChatSessionCRUD 等） |
| `src/db/models.py` | 9 张表 ORM 模型（含 UserModel / TaskReviewModel） |
| `src/utils/file_utils.py` | 文件系统工具（按 user_id 隔离的路径） |
| `src/api/services/docx_review_service.py` | 排版审查服务（快速/深度审查 + 修正 + HTML 缓存） |
| `src/api/services/content_edit_service.py` | 内容编辑服务（MD/HTML → DOCX 合并保留格式） |
| `src/api/routers/review.py` | 排版审查 API（快速/深度审查/修正/批量修正） |
| `src/tools/docx_text_extractor.py` | DOCX 全文提取（审查用） |
| `src/tools/docx_review_marker.py` | 审查标记渲染（HTML 标记版） |
| `src/utils/text_diff.py` | 文本差异比较（审查用） |
| `src/tools/formatters/registry.py` | Formatter 自动发现 + 注册表 |
| `src/tools/formatters/base.py` | Formatter 抽象基类 |
| `src/tools/formatters/gbt_1_1.py` | GB/T 1.1 硬编码格式化器 |
| `src/tools/docx_style_extractor.py` | 模板 DOCX 样式提取器 |
| `src/tools/docx_styler.py` | 通用样式渲染器 |
| `src/tools/docx_normalizer.py` | DOCX 内容规整 |
| `src/tools/content_normalizer.py` | Markdown 层内容规整 |
| `src/api/routers/templates.py` | 模板 CRUD API |
| `src/api/models.py` | API 模型 + StandardOption 枚举 + 认证模型 |
| `frontend/src/App.tsx` | 前端路由 + AuthGuard 守卫 |
| `frontend/src/pages/LoginPage.tsx` | 登录/注册页面 |
| `frontend/src/components/AppLayout.tsx` | 布局组件（含 role-based 菜单） |
| `frontend/src/services/api.ts` | Axios 封装（自动 Bearer token + 401 刷新） |
| `frontend/src/pages/UploadPage.tsx` | 上传页面 + 标准选择器 |
| `frontend/src/pages/TemplatesPage.tsx` | 模板管理页面 + 编辑器面板 |
| `configs/settings.yaml` | 全局配置（LLM/RAG/MinerU 等） |
| `prompts/style_extraction_prompt.md` | LLM 样式提取 Prompt |
| `prompts/intent_parsing_prompt.md` | 意图分析 Prompt |

---

## 二、新增 Formatter（硬编码标准格式）

### 2.1 何时用此路径

当某个国标标准的排版规范**明确且固定**，无需依赖 LLM 或用户模板时，推荐实现硬编码 Formatter。优势：

- 零幻觉，排版结果可预测
- 不依赖 RAG 知识库
- 不受 LLM 输出质量波动影响
- 性能最优（无 LLM 调用）

### 2.2 BaseDocxFormatter 基类

`src/tools/formatters/base.py`：

```python
class BaseDocxFormatter(ABC):
    standard_id: str = ""       # 注册表 key（如 "gbt_9704"）
    display_name: str = ""      # 显示名称（如 "GB/T 9704 党政机关公文格式"）

    @abstractmethod
    def process(self, input_path: str, output_path: str) -> StyleReport:
        """对 DOCX 文件执行格式修正

        Args:
            input_path: 输入 DOCX 路径（MinerU 原始输出）
            output_path: 输出 DOCX 路径

        Returns:
            StyleReport 包含：
            - success: bool          是否成功
            - paragraphs_styled: int 应用样式段落数
            - tables_styled: int     应用样式表格数
            - headings_styled: int   应用样式标题数
            - warnings: list[str]    警告信息
            - output_path: str       输出文件路径
        """
        ...
```

子类**必须**实现 `process()` 方法。可选的辅助方法：
- `_apply_page_setup(doc)` — 页面设置
- `_apply_default_fonts(doc)` — 文档默认字体
- `_normalize_content(doc)` — 内容规整
- `_classify_paragraph(...)` — 段落角色分类
- `_apply_*_format(...)` — 各类角色格式应用
- `_format_tables(doc)` — 表格格式修正
- `_center_images(doc)` — 图片居中

参考 `gbt_1_1.py`（976 行）的完整实现。

### 2.3 注册机制

**1. 使用 `@register_formatter` 装饰器：**

```python
from src.tools.formatters.base import BaseDocxFormatter
from src.tools.formatters.registry import register_formatter
from src.models.document_schema import StyleReport

@register_formatter
class Gbt9704Formatter(BaseDocxFormatter):
    standard_id = "gbt_9704"
    display_name = "GB/T 9704 党政机关公文格式"

    def process(self, input_path: str, output_path: str) -> StyleReport:
        # 格式化逻辑
        ...
        return StyleReport(
            success=True,
            paragraphs_styled=120,
            tables_styled=5,
            output_path=output_path,
        )
```

**2. 放入 `src/tools/formatters/` 目录：**

```
src/tools/formatters/
├── __init__.py
├── base.py
├── registry.py
├── gbt_1_1.py          ← 现有
└── gbt_9704.py         ← 新增（自动发现）
```

**3. 自动发现机制：**

`registry.py` 的 `_ensure_discovered()` 在首次调用时自动扫描 `formatters/` 目录，用 `pkgutil.iter_modules` 查找所有模块（跳过 `_` 开头和 `test_` 开头），`importlib.import_module` 加载。装饰器 `@register_formatter` 在模块导入时自动执行注册。

无需手动配置任何注册表文件。

### 2.4 standard_id 命名规范

`_standard_to_registry_key()` 转换规则（`pipeline_service.py` L557-569）：

```python
key = standard.lower()       # 全小写
       .replace("/", "")     # 去掉斜杠
       .replace(" ", "_")    # 空格 → 下划线
       .replace("-", "_")    # 横杠 → 下划线
while "__" in key:
    key = key.replace("__", "_")  # 压缩重复下划线
return key.strip("_")
```

**映射示例：**

| 用户选择的标准 | `standard_id` |
|:---|:---|
| `GB/T 1.1` | `gbt_1.1` |
| `GB/T 9704` | `gbt_9704` |
| `GB 5009.225` | `gb_5009.225` |
| `GB/T 7713` | `gbt_7713` |

### 2.5 前后端标准选项同步

新增 Formatter 后，必须同步补全两处：

**后端 `src/api/models.py`：**

```python
class StandardOption(str, Enum):
    GBT_1_1 = "GB/T 1.1"
    GBT_9704 = "GB/T 9704"
    GBT_7713 = "GB/T 7713"
    GBT_5009 = "GB 5009.225"       # ← 新增
    CUSTOM = "custom"
```

**前端 `frontend/src/pages/UploadPage.tsx`：**

```typescript
const [standards, setStandards] = useState([
    { value: 'GB/T 1.1', label: '标准化工作导则 (GB/T 1.1)' },
    { value: 'GB/T 9704', label: '党政机关公文格式' },
    { value: 'GB/T 7713', label: '科技报告编写格式' },
    { value: 'GB 5009.225', label: '食品标准 (GB 5009.225)' },  // ← 新增
    { value: 'custom', label: '自定义规范' },
])
```

### 2.6 完整示例：新增 GB/T 9704 Formatter

```python
# 文件：src/tools/formatters/gbt_9704.py
"""GB/T 9704 DOCX 格式修正器

党政机关公文格式（代替 GB/T 9704—1999）
"""
from docx import Document
from src.tools.formatters.base import BaseDocxFormatter
from src.tools.formatters.registry import register_formatter
from src.models.document_schema import StyleReport

@register_formatter
class Gbt9704Formatter(BaseDocxFormatter):
    standard_id = "gbt_9704"
    display_name = "GB/T 9704 党政机关公文格式"

    def process(self, input_path: str, output_path: str) -> StyleReport:
        doc = Document(input_path)

        self._apply_page_setup(doc)
        self._apply_default_fonts(doc)

        # 逐段分类并应用样式
        for para in doc.paragraphs:
            role = self._classify_paragraph(doc, para)
            if role == "heading":
                self._apply_heading_format(doc, para)
            elif role == "body":
                self._apply_body_format(doc, para)
            # ... 更多角色

        self._format_tables(doc)
        doc.save(output_path)

        return StyleReport(
            success=True,
            paragraphs_styled=len(doc.paragraphs),
            tables_styled=len(doc.tables),
            output_path=output_path,
        )

    def _apply_body_format(self, doc, para):
        """正文：仿宋 16pt，两端对齐，首行缩进 2 字符"""
        # ... 实现
        pass

    # ... 更多辅助方法
```

---

## 三、新增标准支持（LLM + RAG 路径）

### 3.1 何时走此路径

当标准没有注册 Formatter，且用户未选择模板时，管线降级到 LLM + RAG 路径。适合：

- 标准格式变化多、难以硬编码
- 快速支持新标准，无需开发
- 用户可自定义 Prompt 调整行为

### 3.2 补充知识库文档

1. 准备标准排版规范 Markdown 文档，放入 `knowledge_data/raw_docs/`
2. 文档应包含：字体规范、字号规范、标题格式、正文格式、表格规范、页边距等
3. 运行初始化：

```bash
python -m scripts.init_knowledge_base
```

**文档格式建议：**

```markdown
# GB/T 9704 党政机关公文格式

## 页面设置
- 纸张：A4（210mm × 297mm）
- 上边距：37mm ± 1mm
- 下边距：35mm ± 1mm
- 左边距：28mm ± 1mm
- 右边距：26mm ± 1mm

## 字体规范
- 正文：仿宋_GB2312，3号字（16pt）
- 一级标题：黑体，3号字（16pt）
- 二级标题：楷体_GB2312，3号字（16pt）

## 段落格式
- 正文：两端对齐，首行缩进 2 字符
- 行距：固定值 28 磅
...
```

### 3.3 调优样式提取 Prompt

`prompts/style_extraction_prompt.md` 中的关键占位符：

| 占位符 | 来源 | 说明 |
|--------|------|------|
| `{document_type}` | LLM 意图分析 | 文档类型描述 |
| `{detected_standard}` | 用户选择或 LLM 检测 | 目标标准号 |
| `{special_elements}` | LLM 意图分析 | 特殊元素（表格/公式/化学式） |
| `{rag_context}` | RAG 检索结果 | 排版规范原文片段 |
| `{few_shot_examples}` | 数据库中匹配的模板示例 | Few-shot 样例 |

### 3.4 RAG 调优参数

`configs/settings.yaml` 中：

```yaml
rag:
  chunk_size: 700              # 调大→更多上下文但可能稀释精度
  chunk_overlap_ratio: 0.15    # 调大→减少信息断层
  top_k: 5                     # 调大→更多参考片段
  bm25_weight: 0.3             # 调大→更重视关键词匹配
  vector_weight: 0.7           # 调大→更重视语义匹配
```

---

## 四、样式提取器优化

### 4.1 DocxStyleExtractor 提取原理

`src/tools/docx_style_extractor.py`（1640 行）直接从 DOCX XML 提取样式，无 LLM 参与：

| 提取方法 | 策略 | 关键代码 |
|----------|------|----------|
| `_extract_page_layout` | 读 section 属性 | `section.page_width / page_height` |
| `_extract_cover_style` | 前 20 段中找 ≥14pt + 居中 | `_is_cover_or_preface()` 启发式 |
| `_extract_preface_style` | 精确匹配「前言」「引言」 | 全文扫描 |
| `_extract_heading_styles` | 先读样式定义表，降级正则匹配 | `HEADING_STYLE_MAP` + `classify_heading_level_by_content` |
| `_extract_body_style` | 样式表 Normal + 全文档众数 | `Counter` 取 `most_common` |
| `_extract_table_style` | 所有表格众数 | 边框/对齐/单元格属性 |
| `_extract_font_from_paragraph` | 读 `w:rPr/w:rFonts` 的 `eastAsia`/`ascii` | 深层 XML 解析 |

### 4.2 已知局限

| 局限 | 说明 | 改进方向 |
|------|------|----------|
| 封面检测 | 仅靠字号+对齐，可能漏判 | 增加关键字匹配（"国家标准"/"GB"） |
| 标题级别 | 依赖样式名或正则，无样式时可能误判 | 引入字体/字号作为辅助判断 |
| 正文字体 | 直接格式覆盖样式定义的情况未处理 | 增加 inline formatting vs style 优先级判断 |
| 表格不一致 | 取众数，不同表格格式差异被忽略 | 表格分角色（数据表/说明表） |
| 首行缩进 | 依赖 `first_line_indent` 字段 | 无缩进的文档需人工补充 |

### 4.3 段落角色识别增强

当前角色分类依赖硬编码规则。如需扩展，修改：

- `src/tools/content_pattern_matcher.py` — 正则模式定义
- `src/tools/docx_style_extractor.py` — `_classify_heading_level_by_content()` 等方法

---

## 五、管线性能优化

### 5.1 MinerU 解析优化

```yaml
# configs/settings.yaml
mineru:
  mode: "online"              # online 比 local 更稳定
  model_version: "vlm"        # vlm 质量最高
  poll_interval: 5            # 轮询间隔（秒），避免频繁请求
  poll_timeout: 600           # 大文件可能需要更长时间
```

MinerU 是管线中最耗时的环节（大 PDF 可能 5~10 分钟），建议：

- 缓存已解析结果：相同文件不重复解析
- 批量上传时并发提交 MinerU 任务

### 5.2 LLM 调用合并

当前管线至少 3 次 LLM 调用：
1. 意图分析（`_analyze_intent`）
2. Markdown 审查（`MarkdownCleaner`）
3. 样式提取（`_generate_style_config`）

优化方向：
- Formatter 路径跳过步骤 3（已实现，L164 覆盖 `style_config`）
- 合并步骤 1+3 为一次调用（需调整 Prompt）
- 小文档可跳过意图分析（用默认值）

### 5.3 大文档分页处理

前端 PDF 预览已实现分页加载（`PreviewService`），后端可考虑：

- DOCX 渲染分页处理（100+ 页文档避免内存溢出）
- Markdown 清洗分段处理（当前 `markdown_content[:3000]` 只取前 3000 字做意图分析）

---

## 六、测试与质量保障

### 6.1 测试结构

```
tests/
├── unit/           # 单元测试
│   ├── test_style_config.py
│   ├── test_markdown_cleaner.py
│   ├── test_content_normalizer.py
│   ├── test_docx_style_extractor.py
│   ├── test_pipeline_service.py
│   └── test_gbt_formatter.py
├── integration/    # 集成测试
│   ├── test_api.py
│   └── test_pipeline.py
├── e2e/            # E2E 测试
│   └── ... (32 个文件)
├── fixtures/       # 测试数据
│   ├── sample.pdf
│   └── ...
└── conftest.py     # Pytest 全局配置
```

### 6.2 运行测试

```bash
# 全部测试
python -m pytest tests/ -v

# 单元测试
python -m pytest tests/unit/ -v

# 单个文件
python -m pytest tests/unit/test_gbt_formatter.py -v

# 覆盖率
python -m pytest tests/ --cov=src --cov-report=html
```

### 6.3 Formatter 测试用例模板

```python
# tests/unit/test_gbt_9704_formatter.py
import pytest
from src.tools.formatters.gbt_9704 import Gbt9704Formatter


class TestGbt9704Formatter:
    def test_standard_id(self):
        fmt = Gbt9704Formatter()
        assert fmt.standard_id == "gbt_9704"

    def test_page_setup(self, tmp_path):
        # 准备测试 DOCX → 执行 process → 验证输出
        ...
```

### 6.4 排版结果自动化比对

编写验证脚本，检查输出 DOCX 的关键格式点：

```python
def verify_gbt_output(docx_path: str) -> dict:
    """验证 DOCX 是否符合 GB/T 1.1 规范"""
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(docx_path)
    issues = []

    # 1. 页面
    s = doc.sections[0]
    w = s.page_width / 36000
    h = s.page_height / 36000
    if abs(w - 210) > 1 or abs(h - 297) > 1:
        issues.append(f"页面尺寸异常: {w:.0f}x{h:.0f}mm")

    # 2. 正文格式
    for p in doc.paragraphs:
        # 根据角色验证字体/字号/对齐/缩进
        ...

    return {"pass": len(issues) == 0, "issues": issues}
```

### 6.5 前端编译检查

```bash
cd frontend
npm run tsc -- --noEmit   # TypeScript 编译检查
npm run lint              # ESLint 检查
```

---

## 七、数据库与迁移

### 7.1 数据模型

核心表位于 `src/db/models.py`（共 9 张表）：

| 表名 | 说明 | user_id 隔离 |
|------|------|:---:|
| `users` | 用户账号（username/password_hash/role/is_active） | — |
| `tasks` | 排版任务 | Y |
| `task_reviews` | 排版后审查结果（quick_review + deep_review） | Y |
| `chat_sessions` | 对话会话 | Y |
| `chat_messages` | 对话消息（级联 session） | Y |
| `style_templates` | 样式模板（user_id=NULL 为系统预置） | Y |
| `style_adjustment_history` | 样式调整历史 | Y |
| `kb_documents` | 知识库文档（全局共享） | — |
| `system_config` | 系统配置（全局单条记录） | — |

### 7.2 Alembic 迁移

**本地开发（SQLite）：**

```bash
# 生成迁移脚本
alembic revision --autogenerate -m "描述"

# 执行迁移
alembic upgrade head

# 回滚
alembic downgrade -1
```

**Docker 部署（PostgreSQL）：**

`migrations/env.py` 已配置从 `DATABASE_URL` 环境变量读取数据库连接（Docker Compose 自动注入），覆盖 `alembic.ini` 的默认 SQLite 连接。容器启动时 `init_db()` 自动执行 `alembic upgrade head`。

> 如果数据库已通过 `create_all` 降级方案创建了表，导致 alembic 报 `already exists` 错误，执行 `alembic stamp head` 标记当前状态后，后续迁移即可正常进行。

### 7.3 模板标准号匹配策略

`StyleTemplateCRUD.match_by_standard()` 三级匹配（`src/db/crud.py`）：

1. **精确匹配**：`standard` 字段与目标标准号完全一致
2. **模糊匹配**：去除空格/符号后比较（如 `GB/T1.1` ↔ `GBT 1.1`）
3. **名称匹配**：标准号关键词在模板名称中出现

---

## 八、SaaS 多用户开发模式

### 8.1 多用户数据隔离总览

系统通过三层隔离实现多用户 SaaS 架构：

```
┌───────────────────────────────────────┐
│         前端 (JWT Bearer Token)        │
│  每个请求自动携带 Authorization 头     │
└───────────────┬───────────────────────┘
                │
┌───────────────▼───────────────────────┐
│       FastAPI 中间件 (auth.py)         │
│  get_current_user() → 从 JWT 提取用户  │
│  注入到路由参数 current_user           │
└───────────────┬───────────────────────┘
                │
     ┌──────────┼──────────┐
     ▼          ▼          ▼
┌─────────┐ ┌──────┐ ┌──────────┐
│  DB 层   │ │文件层│ │ 路由层   │
│user_id  │ │user_ │ │role==    │
│WHERE    │ │id/   │ │"admin"? │
│过滤     │ │目录  │ │全局:自己 │
└─────────┘ └──────┘ └──────────┘
```

**隔离粒度：**

| 层级 | 实现位置 | 机制 |
|------|---------|------|
| 数据库 | `src/db/crud.py` 各 CRUD 的 `list_*` 方法 | `user_id=xxx` 查询过滤 |
| 文件系统 | `src/utils/file_utils.py` | `data/uploads/{user_id}/` 和 `data/output/{user_id}/` 目录隔离 |
| 路由 | `src/api/routers/*.py` | `Depends(get_current_user)` 注入 + `role=="admin"` 判断 |

### 8.2 认证鉴权开发模式

#### JWT 认证流程

```
用户登录 → POST /api/auth/login
    │
    ▼
验证 bcrypt 密码 → 检查 is_active
    │
    ▼
签发 JWT: access_token (30min) + refresh_token (7d)
payload: { sub: user_id, username, role }
    │
    ▼
前端存储 token → axios interceptor 自动注入 Authorization: Bearer {token}
    │
    ▼
get_current_user() 从 HTTPBearer 提取 token → decode JWT → 查 DB → 返回 UserModel
```

**关键代码位置：**

| 组件 | 文件 | 行/方法 |
|------|------|--------|
| Token 签发 | `src/api/middleware/auth.py` | `create_access_token()` / `create_refresh_token()` |
| Token 验证 | `src/api/middleware/auth.py` | `decode_token()` |
| 密码哈希 | `src/api/middleware/auth.py` | `hash_password()` / `verify_password()` — bcrypt cost=12 |
| 用户依赖注入 | `src/api/middleware/auth.py` | `get_current_user()` — 从 HTTPBearer 提取 token，返回 UserModel |
| 管理员依赖注入 | `src/api/middleware/auth.py` | `get_current_admin()` — 额外校验 `role=="admin"`，否则 403 |
| 路由使用 | `src/api/routers/*.py` | `current_user: UserModel = Depends(get_current_user)` |

#### 给新路由添加认证

```python
from src.api.middleware.auth import get_current_user, get_current_admin
from src.db.models import UserModel

# 普通用户可访问（自动按 user_id 过滤）
@router.get("/my-resource")
async def list_my_resource(
    current_user: UserModel = Depends(get_current_user),
):
    user_id = None if current_user.role == "admin" else current_user.id
    with get_db_session() as db:
        items, total = MyCRUD.list_items(db, user_id=user_id)
    return ResponseModel(data={"items": items, "total": total})

# 仅管理员可访问
@router.delete("/admin/resource/{id}")
async def admin_delete(
    resource_id: str,
    _admin: UserModel = Depends(get_current_admin),  # 非 admin 自动 403
):
    ...
```

**Admin 全局视图标准模式：**

```python
# 在所有列表/统计路由中使用此模式
user_id = None if current_user.role == "admin" else current_user.id
```

`user_id=None` 传给 CRUD 方法时表示"查全部"，`user_id=xxx` 表示"只看自己的"。

### 8.3 管理员路由开发模式

管理员路由集中于 `src/api/routers/admin.py`，所有端点受 `get_current_admin` 保护。

**创建管理员 API 端点模板：**

```python
from src.api.middleware.auth import get_current_admin, hash_password

@router.post("/admin/resource")
async def admin_create(
    request: SomeRequest,
    _admin: UserModel = Depends(get_current_admin),  # 仅管理员
):
    ...
```

**级联删除模式**（删除用户时同步清理所有关联数据）：

```python
# src/db/crud.py → UserCRUD.delete_cascade()
def delete_cascade(db: Session, user_id: str):
    db.query(ChatMessageModel).filter(...).delete()
    db.query(ChatSessionModel).filter(...).delete()
    db.query(TaskModel).filter(...).delete()
    db.query(StyleTemplateModel).filter(...).delete()
    db.query(StyleAdjustmentHistoryModel).filter(...).delete()
    db.query(UserModel).filter(UserModel.id == user_id).delete()
    db.commit()
```

**安全规则：**

- 不可删除 `role="admin"` 的用户（广告 API 返回 403）
- 全局表 `kb_documents` / `system_config` 不参与级联删除
- 文件系统数据需额外调用 `shutil.rmtree()` 清理

### 8.4 Celery 异步任务队列

#### 架构

```
FastAPI 路由 → TaskManager.submit_task()
                    │
                    ├── Celery 可用？─→ process_pipeline_task.delay(task_id) → Redis Queue
                    │                                                              │
                    └── Celery 不可用？─→ ThreadPoolExecutor.submit()               ▼
                                                              │            Celery Worker
                                                              │            (4 副本)
                                                              ▼                │
                                                       task_manager.process_task(task_id)
```

#### 关键文件

| 文件 | 职责 |
|------|------|
| `src/tasks/celery_app.py` | Celery 实例配置（Redis broker, result backend, 序列化/时区/重试） |
| `src/tasks/pipeline_task.py` | 排版任务定义（`@celery_app.task(max_retries=3, retry_delay=60)`） |
| `scripts/run_worker.py` | Worker 启动脚本 |
| `src/api/services/task_manager.py` L390-410 | 任务提交 + 降级分发 |

#### 启动 Worker

```bash
# 单 Worker
python -m scripts.run_worker

# 或者 docker-compose 自动启动 4 副本
# docker compose up -d → celery-worker-{1..4}

# 指定并发数
celery -A src.tasks.celery_app worker --concurrency=4
```

#### 降级机制

当 Redis 不可用时，`submit_task()` 自动降级为 `ThreadPoolExecutor` 同步执行：

```python
# src/api/services/task_manager.py
def _submit_via_celery_or_thread(task_id: str):
    if _celery_available:
        process_pipeline_task.delay(task_id)  # 异步
    else:
        THREAD_POOL.submit(task_manager.process_task, task_id)  # 线程池
```

### 8.5 文件系统用户隔离

`src/utils/file_utils.py` 提供两个核心函数：

```python
# 用户上传隔离
get_user_upload_dir(user_id) → data/uploads/{user_id}/

# 用户输出隔离
get_user_output_dir(user_id, task_id="") → data/output/{user_id}/{task_id}/
```

**目录结构示例：**

```
data/
├── uploads/
│   ├── user_a_id/           ← 用户 A 的上传文件
│   │   ├── abc123.pdf
│   │   └── abc123.meta
│   └── user_b_id/           ← 用户 B 的上传文件
│       └── def456.pdf
├── output/
│   ├── user_a_id/
│   │   └── task_001/        ← 任务输出（.docx/.md/.json）
│   └── user_b_id/
│       └── task_002/
└── templates/               ← 模板文件（全局，不属于用户）
```

**磁盘用量统计** 支持按 user_id 隔离：

```python
# task_manager.py
def get_disk_usage(user_id: str | None = None) -> dict:
    uploads_path = f"data/uploads/{user_id}/" if user_id else "data/uploads/"
    output_path = f"data/output/{user_id}/" if user_id else "data/output/"
    # 统计各目录大小
```

### 8.6 前端认证模式

#### 路由守卫（AuthGuard）

`frontend/src/App.tsx` 中 `AuthGuard` 组件保护所有需要登录的路由：

```tsx
// 未登录 → 重定向到 /login
// 已登录 → 渲染子路由
<AuthGuard>
  <AppLayout>
    <Routes>...</Routes>
  </AppLayout>
</AuthGuard>
```

#### Axios 拦截器

`frontend/src/services/api.ts` 的双拦截器模式：

```typescript
// 请求拦截器：自动注入 Bearer Token
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token');
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// 响应拦截器：401 → 自动刷新 token 或重定向登录
api.interceptors.response.use(
  response => response,
  async error => {
    if (error.response?.status === 401 && !error.config._retry) {
      // 尝试 refresh_token 刷新
      // 失败则清除 token 跳转 /login
    }
  }
);
```

#### 角色菜单渲染

`frontend/src/components/AppLayout.tsx` 根据 `userRole === 'admin'` 条件渲染菜单：

```typescript
const menuItems = [
  { key: '/dashboard', label: '工作台' },
  { key: '/upload', label: '上传排版' },
  { key: '/tasks', label: '任务列表' },
  { key: '/chat', label: '对话排版' },
  { key: '/templates', label: '模板管理' },
  // 仅管理员可见
  ...(userRole === 'admin' ? [
    { key: '/kb', label: '知识库' },
    { key: '/config', label: '系统配置' },
  ] : []),
];
```

### 8.7 数据库迁移与用户数据

Alembic 迁移链（`migrations/versions/`）：

```
base → 5e132870e319 (初始建表)
     → 820ed49c4fca (添加 style_templates.standard 字段)
     → 3a7f1c2d4e5f (新增 users 表 + 各表 user_id 列) ← SaaS 改造
     → 08deb19fab7e (新增 task_reviews 表)          ← 排版审查
```

**新增业务表时加入 user_id：**

```python
# Alembic 迁移脚本
op.create_table(
    "new_table",
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("user_id", sa.String(36), nullable=False, index=True),  # ← 必须
    ...
)

# ORM 模型
class NewModel(Base):
    __tablename__ = "new_table"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=...)
    user_id: Mapped[str] = mapped_column(String(36), index=True)  # ← 必须
    created_by: Mapped["UserModel"] = relationship("UserModel")
```

**新增 CRUD 时加入 user_id 过滤：**

```python
@staticmethod
def list_new_items(db: Session, page: int, page_size: int, user_id: str | None = None):
    query = db.query(NewModel)
    if user_id is not None:          # None = 管理员全局视图
        query = query.filter(NewModel.user_id == user_id)
    return query.offset((page-1)*page_size).limit(page_size).all()
```

---

## 九、变更记录

| 日期 | 类型 | 摘要 |
|------|------|------|
| 2026-07-13 | fix | 审查修正/内容编辑格式保留: `_replace_text_in_docx` 重写跨 run 替换逻辑(保留字体/字号/加粗), `_merge_docx_content` 新增(保留 sectPr 页面布局), HTML 缓存 + 失效机制 |
| 2026-07-12 | feat | 深度审查新增 LaTeX 公式残留审查维度: `_QUICK_CHECK_PATTERNS` 添加 50+ 个 LaTeX 命令正则, `_build_summary` 新增 `latex_residue` 统计字段 |
| 2026-07-10 | fix | TinyMCE 编辑器无法加载: `main.py` 新增 `/tinymce` 静态文件挂载 |
| 2026-07-10 | fix | DOCX 下载失败(401): TaskDetailPage 下载改用 fetch+Blob 携带 JWT token |
| 2026-07-10 | feat | 管理员用户管理前端页面: AdminUsersPage + api.ts 4个管理 API + 路由集成 |
| 2026-07-10 | fix | Docker Alembic迁移修复: env.py 读取 DATABASE_URL 环境变量, Docker 容器内 alembic 正确连接 PostgreSQL |
| 2026-07-10 | fix | Docker 部署依赖补全: pyproject.toml 添加 psycopg2-binary/celery/redis/bcrypt |
| 2026-07-10 | fix | 排版后审查误报修复: quick_review 异常 Unicode 正则扩充合法字符范围(拉丁扩展/希腊字母/数学运算符等), 消除技术文档 100% 误报 |
| 2026-07-10 | feat | 排版后 LLM 全文审查: DocxTextExtractor + TextDiff 增量对比 + DocxReviewService(quick_review 规则 + deep_review LLM 分块) + TaskReviewModel + 前端审查面板 |
| 2026-07-09 | feat | 多用户 SaaS 架构改造: JWT + bcrypt 认证, 7 表 user_id 隔离, PostgreSQL 支持, Celery + Redis 异步队列, 文件系统按 user_id 目录隔离, 前端 LoginPage/AuthGuard/role-based 菜单, 管理员全局视图 |
| 2026-07-09 | feat | 管理员功能补全: 用户账号管理 API (CRUD/重置密码/禁用/级联删除), 管理员全局数据视图 (tasks/chat/stats/disk-usage 路由 admin 分支) |
| 2026-07-09 | docs | 文档全面更新: AGENTS.md/USER_GUIDE.md/DEV_GUIDE.md 三个文档的 SaaS 多用户章节补全 |
| 2026-07-08 | fix | GbtDocxFormatter `_is_standard_name_line` 正则 `\s{2,}` → `\s+` |
| 2026-07-08 | fix | `_standard_to_registry_key` 去掉 `.replace(".", "_")`，修复 `gbt_1.1` → `gbt_1_1` 映射错误 |
| 2026-07-08 | fix | TaskDetailPage 修正样式 React State 时序 Bug |
| 2026-07-08 | fix | TemplatesPage 手动创建 extractedConfig 空指针崩溃修复 |
| 2026-07-08 | feat | DocxNormalizer: DOCX 层内容规整 |
| 2026-07-08 | feat | Formatter 注册系统: BaseDocxFormatter + Registry 自动发现 |
| 2026-07-08 | feat | 格式规范分类重构: StyleTemplateModel 添加 standard 字段 + 三级匹配 |
| 2026-07-08 | feat | Pipeline 路由优先级显式化: applied_format 来源追溯 |
| 2026-07-08 | feat | 前端 TemplatesPage 样式编辑器增强 |
| 2026-07-07 | feat | 工程化 P0~P3: 重试/超时/CI/限流/Dockerfile/Makefile |
| 2026-07-07 | refactor | TaskManager 门面拆分: PipelineService/PreviewService/ContentEditService |
| 2026-07-07 | config | LLM Provider 从 Qwen 切换为智谱 AI (GLM-4) |
| 2026-07-06 | feat | PDF 对比预览 + 分页加载 |
| 2026-07-06 | feat | 文档内容编辑 (TinyMCE + LLM 对话) |
| 2026-07-06 | feat | 四大智能排版 + 模板管理 + 附录样式分离 |

---

## 十、常见开发问题

### Q1: 新增 Formatter 后未生效

1. 确认文件在 `src/tools/formatters/` 目录下（非子目录）
2. 确认类有 `@register_formatter` 装饰器
3. 确认 `standard_id` 与 `_standard_to_registry_key()` 输出一致
4. 确认前后端标准选项已同步补全
5. 重启后端服务（模块自动发现仅在首次调用时触发）

### Q2: _generate_style_config 调了但结果未被使用

这是预期行为：Formatter 路径在 L146 调了 `_generate_style_config`，但 L164 用 `_default_style_config()` 覆盖，实际不使用 LLM 生成的结果。

### Q3: Pre-commit hooks 报错

```bash
# 手动运行
pre-commit run --all-files
ruff check src/ tests/ scripts/ --fix
```

`.pre-commit-config.yaml` 配置了 Ruff lint + format 检查。

### Q4: 新增业务表如何加入 user_id 隔离

1. **模型**：`src/db/models.py` 中新表添加 `user_id = mapped_column(String(36), index=True)`
2. **迁移**：`alembic revision --autogenerate -m "new_table_add_user_id"` → `alembic upgrade head`
3. **CRUD**：`list_*` 方法添加 `user_id: str | None` 参数，非 None 时 WHERE 过滤
4. **路由**：使用 `user_id = None if current_user.role == "admin" else current_user.id` 模式

### Q5: 管理员 API 返回 403 怎么办

1. 确认路由使用了 `Depends(get_current_admin)`（而非 `get_current_user`）
2. 确认登录用户的 `role` 字段为 `"admin"`
3. 检查 JWT token 中是否包含 `role` 字段（可在 https://jwt.io 解码查看）

### Q6: Celery Worker 不处理任务

```bash
# 检查 Redis 是否运行
redis-cli ping

# 手动启动 Worker 查看日志
celery -A src.tasks.celery_app worker --loglevel=info

# 检查是否有积压任务
celery -A src.tasks.celery_app inspect active
```

降级方案：系统自动检测 Celery 可用性，不可用时使用 ThreadPoolExecutor 同步执行。

### Q7: Alembic 迁移与已有数据冲突

如果数据库已有表（通过 `create_all` 创建），但 Alembic 迁移脚本尝试 `create_table`：

```bash
# 将当前数据库状态标记为已迁移（跳过已存在的表）
alembic stamp head

# 后续新增迁移正常进行
```

### Q8: 用户密码哈希/验证在哪里

`src/api/middleware/auth.py`：

```python
import bcrypt

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
```

cost=12 在安全性与性能之间取得平衡（每次哈希约 200-300ms）。

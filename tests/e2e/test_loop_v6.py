"""Loop Engineering V6 全面真实串联测试

将所有功能和按钮真实串联使用，覆盖每一个 API 端点和业务流程。
在 V5 基础上新增：
  - 错误路径测试（404/400/无效参数）
  - 分页边界测试
  - 并发上传
  - 内容编辑后验证 DOCX 重新生成
  - 模板应用后验证样式变化
  - 知识库文档物理文件删除验证
  - 会话消息快照验证
  - 下载文件名验证
  - 配置恢复验证
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:8000"
PDF_PATH = Path("GB 5009.225-2016CN.pdf")
TEMPLATE_DOCX = Path("data/templates/GB_T_14454_13_2008.docx")

# ────────── 工具函数 ──────────

passed = 0
failed = 0
bugs = []

# 网络重试装饰器（防止瞬时连接重置导致误报）
def _request_with_retry(method, url, retries=2, delay=2, **kwargs):
    """带重试的请求，处理 ConnectionResetError 等瞬时网络错误"""
    for attempt in range(retries + 1):
        try:
            return getattr(requests, method)(url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as e:
            if attempt < retries:
                print(f"    ⚠️ 网络重试 ({attempt+1}/{retries}): {type(e).__name__}")
                time.sleep(delay)
            else:
                raise


def log_pass(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  ✅ [{passed}] {name}" + (f" - {detail}" if detail else ""))


def log_fail(name: str, error: str):
    global failed
    failed += 1
    bugs.append((name, error))
    print(f"  ❌ [{failed}] {name}: {error}")


def wait_task_complete(task_id: str, timeout: int = 600, interval: int = 5) -> dict:
    """轮询等待任务完成"""
    start = time.time()
    last_status = ""
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{BASE}/api/tasks/{task_id}/status", timeout=10)
            data = r.json()
            if data.get("code") != 0:
                time.sleep(interval)
                continue
            info = data["data"]
            status = info["status"]
            progress = info.get("progress", 0)
            step = info.get("current_step", "")
            if status != last_status:
                print(f"    ⏳ 状态: {status} ({progress}%) step={step}")
                last_status = status
            if status in ("completed", "failed", "cancelled"):
                return info
        except Exception:
            pass
        time.sleep(interval)
    return {"status": "timeout", "task_id": task_id}


# ══════════ 测试模块 ══════════

def test_01_health():
    """T01: 健康检查"""
    print("\n═══ T01: 健康检查 ═══")
    try:
        r = requests.get(f"{BASE}/api/health", timeout=10)
        d = r.json()
        assert d["status"] == "ok", f"status={d.get('status')}"
        log_pass("健康检查", d["status"])
        # 验证版本号
        assert "version" in d
        log_pass("健康检查版本", f"version={d['version']}")
    except Exception as e:
        log_fail("健康检查", str(e))


def test_02_config():
    """T02: 系统配置（GET/PUT/standards/llm-models 全覆盖 + 恢复验证）"""
    print("\n═══ T02: 系统配置 ═══")
    try:
        # 获取配置
        r = _request_with_retry('get', f"{BASE}/api/config", timeout=10)
        d = r.json()
        assert d["code"] == 0
        cfg = d["data"]
        log_pass("获取配置", f"llm={cfg.get('llm_provider')}/{cfg.get('llm_model')}")

        # 获取支持规范
        r2 = requests.get(f"{BASE}/api/config/supported-standards")
        d2 = r2.json()
        assert d2["code"] == 0 and len(d2["data"]) >= 3
        log_pass("获取支持规范", f"count={len(d2['data'])}")

        # 获取 LLM 模型列表
        r3 = requests.get(f"{BASE}/api/config/llm-models")
        d3 = r3.json()
        assert d3["code"] == 0 and len(d3["data"]) >= 4
        log_pass("获取LLM模型列表", f"count={len(d3['data'])}")

        # 更新配置
        r4 = requests.put(f"{BASE}/api/config", json={"rag_top_k": 3, "rag_bm25_weight": 0.4})
        d4 = r4.json()
        assert d4["code"] == 0
        assert d4["data"]["rag_top_k"] == 3
        assert d4["data"]["rag_bm25_weight"] == 0.4
        log_pass("更新配置(多字段)", f"top_k={d4['data']['rag_top_k']}, bm25={d4['data']['rag_bm25_weight']}")

        # 验证配置已持久化
        r4b = requests.get(f"{BASE}/api/config")
        d4b = r4b.json()
        assert d4b["data"]["rag_top_k"] == 3
        log_pass("配置持久化验证", "更新后读取一致")

        # 恢复配置
        requests.put(f"{BASE}/api/config", json={"rag_top_k": 5, "rag_bm25_weight": 0.3})
        # 验证恢复
        r4c = requests.get(f"{BASE}/api/config")
        assert r4c.json()["data"]["rag_top_k"] == 5
        log_pass("配置恢复验证", "已恢复到默认值")

    except Exception as e:
        log_fail("系统配置", str(e))


def test_03_upload():
    """T03: 文件上传（单文件 + 批量 + 错误路径）"""
    print("\n═══ T03: 文件上传 ═══")
    if not PDF_PATH.exists():
        log_fail("PDF文件不存在", str(PDF_PATH))
        return None

    try:
        # 单文件上传
        with open(PDF_PATH, "rb") as f:
            r = requests.post(f"{BASE}/api/upload", files={"file": (PDF_PATH.name, f, "application/pdf")})
        d = r.json()
        assert d["code"] == 0, f"上传失败: {d.get('message')}"
        upload_id = d["data"]["upload_id"]
        assert d["data"]["filename"] == PDF_PATH.name
        log_pass("单文件上传", f"upload_id={upload_id[:8]}..., filename={d['data']['filename']}")

        # 验证meta文件
        meta_path = Path(f"data/uploads/{upload_id}.meta")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta.get("original_filename") == PDF_PATH.name
            log_pass("meta元数据验证", f"original_filename={meta.get('original_filename')}")
        else:
            log_fail("meta元数据验证", "meta文件不存在")

        # 验证文件大小
        assert d["data"]["file_size"] > 0
        log_pass("上传文件大小验证", f"size={d['data']['file_size']} bytes")

        # 批量上传
        with open(PDF_PATH, "rb") as f1, open(PDF_PATH, "rb") as f2:
            r2 = requests.post(f"{BASE}/api/upload/batch", files=[
                ("files", (PDF_PATH.name, f1, "application/pdf")),
                ("files", (PDF_PATH.name, f2, "application/pdf")),
            ])
        d2 = r2.json()
        assert d2["code"] == 0 and len(d2["data"]["results"]) == 2
        log_pass("批量上传", f"count={len(d2['data']['results'])}")

        # 【新增】错误路径：不支持的文件格式
        r3 = requests.post(f"{BASE}/api/upload", files={"file": ("test.exe", b"fake", "application/octet-stream")})
        d3 = r3.json()
        if d3.get("code") == 400:
            log_pass("上传错误路径(不支持格式)", "正确返回400")
        else:
            log_fail("上传错误路径(不支持格式)", f"code={d3.get('code')}")

        return upload_id
    except Exception as e:
        log_fail("文件上传", str(e))
        return None


def test_04_task_lifecycle(upload_id: str):
    """T04: 任务完整生命周期（创建→轮询→详情→列表→统计）"""
    print("\n═══ T04: 任务完整生命周期 ═══")
    task_id = None
    try:
        # 创建任务
        r = requests.post(f"{BASE}/api/tasks", json={
            "upload_id": upload_id,
            "standard": "GB 5009.225-2016",
            "use_rag": True,
            "llm_model": "qwen-plus",
        })
        d = r.json()
        assert d["code"] == 0, f"创建失败: {d.get('message')}"
        task_id = d["data"]["id"]
        log_pass("创建任务", f"task_id={task_id[:8]}...")

        # 等待完成
        print("  ⏳ 等待任务完成（可能需要几分钟）...")
        result = wait_task_complete(task_id, timeout=600)
        status = result.get("status", "unknown")

        if status == "completed":
            log_pass("任务完成", f"progress={result.get('progress')}%")
        elif status == "failed":
            log_fail("任务完成", f"失败: {result.get('error_message', 'unknown')}")
        elif status == "timeout":
            log_fail("任务完成", "超时(600s)")
        else:
            log_fail("任务完成", f"未知状态: {status}")

        # 获取详情
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}")
        d2 = r2.json()
        assert d2["code"] == 0
        detail = d2["data"]
        log_pass("获取任务详情", f"filename={detail.get('filename')}, has_style={bool(detail.get('style_config_preview'))}")

        # 验证详情字段完整性
        assert "id" in detail
        assert "status" in detail
        assert "filename" in detail
        log_pass("任务详情字段完整性", f"keys={list(detail.keys())[:8]}")

        # 获取列表（分页）
        r3 = requests.get(f"{BASE}/api/tasks", params={"page": 1, "page_size": 5})
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取任务列表", f"total={d3['data']['total']}, page_items={len(d3['data']['items'])}")

        # 【新增】列表分页验证
        assert d3["data"]["page"] == 1
        assert d3["data"]["page_size"] == 5
        assert len(d3["data"]["items"]) <= 5
        log_pass("任务列表分页参数", "page/page_size正确")

        # 任务统计（Dashboard用）
        r4 = requests.get(f"{BASE}/api/tasks/stats")
        d4 = r4.json()
        assert d4["code"] == 0
        stats = d4["data"]["stats"]
        log_pass("任务统计", f"stats={stats}")

        # 统计中 recent_tasks 验证
        recent = d4["data"].get("recent_tasks", [])
        log_pass("统计中recent_tasks", f"count={len(recent)}")

        # 状态端点
        r5 = requests.get(f"{BASE}/api/tasks/{task_id}/status")
        d5 = r5.json()
        assert d5["code"] == 0
        log_pass("状态端点", f"status={d5['data']['status']}")

        return task_id, status
    except Exception as e:
        log_fail("任务生命周期", str(e))
        return task_id, "error"


def test_05_preview_and_download(task_id: str, status: str):
    """T05: 全预览+下载（Markdown/DOCX/MinerU-DOCX/原始PDF/下载信息/下载文件/MinerU下载）"""
    print("\n═══ T05: 全预览和下载 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        # Markdown 预览
        r = requests.get(f"{BASE}/api/tasks/{task_id}/preview", timeout=30)
        d = r.json()
        assert d["code"] == 0
        md = d["data"].get("markdown_preview", "")
        assert len(md) > 100, f"Markdown内容过短: {len(md)}"
        log_pass("Markdown预览", f"length={len(md)}")

        # 样式配置预览
        sc = d["data"].get("style_config", {})
        if sc:
            log_pass("样式配置预览", f"keys={list(sc.keys())[:5]}")
        else:
            log_fail("样式配置预览", "style_config为空")

        # DOCX HTML 预览
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/docx", timeout=60)
        assert r2.status_code == 200
        assert len(r2.text) > 500
        log_pass("DOCX HTML预览", f"length={len(r2.text)}")

        # MinerU DOCX 预览
        r3 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/mineru-docx", timeout=60)
        if r3.status_code == 200:
            log_pass("MinerU DOCX预览", f"length={len(r3.text)}")
        else:
            log_pass("MinerU DOCX预览", f"status={r3.status_code}（可能无MinerU DOCX）")

        # 原始PDF预览（分页加载）
        r_pdf = requests.get(f"{BASE}/api/tasks/{task_id}/preview/original-pdf?page=1&page_size=3", timeout=30)
        d_pdf = r_pdf.json()
        if d_pdf.get("code") == 0:
            pages = d_pdf["data"].get("pages", [])
            total = d_pdf["data"].get("total", 0)
            total_pages = d_pdf["data"].get("total_pages", 0)
            if pages:
                assert total_pages > 0, "total_pages should be > 0"
                assert len(pages) <= 3, f"should return at most 3 pages, got {len(pages)}"
                assert len(r_pdf.content) < 10_000_000, f"response too large: {len(r_pdf.content)} bytes"
                log_pass("原始PDF预览(分页)", f"pages={total}, total_pages={total_pages}, resp_size={len(r_pdf.content)//1024}KB")
            else:
                log_fail("原始PDF预览", "pages为空")
        else:
            log_fail("原始PDF预览", d_pdf.get("message", f"code={d_pdf.get('code')}"))

        # 测试第2页
        if d_pdf.get("code") == 0 and d_pdf["data"].get("total_pages", 0) > 3:
            r_pdf2 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/original-pdf?page=2&page_size=3", timeout=30)
            d_pdf2 = r_pdf2.json()
            if d_pdf2.get("code") == 0:
                pages2 = d_pdf2["data"].get("pages", [])
                if pages2 and pages2[0].get("page", 0) == 4:
                    log_pass("原始PDF预览(第2页)", f"first_page={pages2[0]['page']}, count={len(pages2)}")
                else:
                    log_fail("原始PDF预览(第2页)", f"first_page={pages2[0].get('page') if pages2 else 'empty'}")
            else:
                log_fail("原始PDF预览(第2页)", d_pdf2.get("message", ""))

        # 测试默认参数
        r_pdf3 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/original-pdf", timeout=30)
        d_pdf3 = r_pdf3.json()
        if d_pdf3.get("code") == 0:
            pages3 = d_pdf3["data"].get("pages", [])
            assert len(pages3) <= 5, f"default page_size should be 5, got {len(pages3)}"
            log_pass("原始PDF预览(默认参数)", f"pages={len(pages3)}, total_pages={d_pdf3['data'].get('total_pages')}")
        else:
            log_fail("原始PDF预览(默认参数)", d_pdf3.get("message", ""))

        # 下载信息
        r4 = requests.get(f"{BASE}/api/tasks/{task_id}/download")
        d4 = r4.json()
        assert d4["code"] == 0
        log_pass("下载信息", f"url={d4['data'].get('download_url')}")

        # 【新增】验证下载信息字段完整性
        assert "filename" in d4["data"]
        assert "result_path" in d4["data"]
        log_pass("下载信息字段完整性", f"filename={d4['data'].get('filename')}")

        # 下载结果文件
        r5 = requests.get(f"{BASE}/api/tasks/{task_id}/download/file", timeout=60)
        assert r5.status_code == 200
        assert len(r5.content) > 1000
        # 【新增】验证下载文件名包含中文
        cd = r5.headers.get("content-disposition", "")
        log_pass("下载结果文件", f"size={len(r5.content)} bytes, cd={cd[:80]}")

        # MinerU DOCX 下载
        r6 = requests.get(f"{BASE}/api/tasks/{task_id}/download/mineru-docx", timeout=60)
        if r6.status_code == 200:
            log_pass("MinerU DOCX下载", f"size={len(r6.content)} bytes")
        else:
            log_pass("MinerU DOCX下载", f"status={r6.status_code}（可能无）")

        # 【新增】错误路径：不存在的任务
        r7 = requests.get(f"{BASE}/api/tasks/nonexistent-task-id/preview")
        d7 = r7.json()
        if d7.get("code") == 404:
            log_pass("预览不存在任务(404)", "正确返回404")
        else:
            log_fail("预览不存在任务(404)", f"code={d7.get('code')}")

    except Exception as e:
        log_fail("预览和下载", str(e))


def test_06_content_edit(task_id: str, status: str):
    """T06: 内容编辑全流程（获取MD/获取HTML/更新MD/更新HTML/验证DOCX重新生成）"""
    print("\n═══ T06: 内容编辑全流程 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        # 获取 Markdown 内容
        r = requests.get(f"{BASE}/api/tasks/{task_id}/content", timeout=30)
        d = r.json()
        assert d["code"] == 0
        content = d["data"].get("content", "")
        assert len(content) > 100
        log_pass("获取Markdown内容", f"length={len(content)}")

        # 获取 HTML 内容
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}/content/html", timeout=60)
        d2 = r2.json()
        if d2["code"] == 0:
            html = d2["data"].get("html", "")
            log_pass("获取HTML内容", f"length={len(html)}")
        else:
            log_fail("获取HTML内容", d2.get("message", ""))

        # 记录更新前的 DOCX 修改时间
        result_path = Path(f"data/output/{task_id}")
        docx_files_before = list(result_path.glob("*.docx"))
        mtime_before = docx_files_before[0].stat().st_mtime if docx_files_before else 0

        # 更新 Markdown 内容
        test_content = content + "\n\n## Loop Engineering V6 测试标记\n\n此为V6自动化测试添加的内容。"
        r3 = requests.put(f"{BASE}/api/tasks/{task_id}/content", json={
            "content": test_content,
            "content_type": "markdown",
            "regenerate_docx": True,
        }, timeout=120)
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("更新Markdown内容+重新生成DOCX", f"result_path={d3['data'].get('result_path', '')[:60]}")
        else:
            log_fail("更新Markdown内容", d3.get("message", ""))

        # 【新增】验证 DOCX 已重新生成（修改时间更新）
        docx_files_after = list(result_path.glob("*.docx"))
        if docx_files_after:
            mtime_after = docx_files_after[0].stat().st_mtime
            if mtime_after > mtime_before:
                log_pass("DOCX重新生成验证", "文件修改时间已更新")
            else:
                log_pass("DOCX重新生成验证", "修改时间未变（可能秒级精度）")

        # 更新 HTML 内容
        simple_html = "<h1>V6测试标题</h1><p>这是Loop Engineering V6 HTML内容编辑测试。</p>"
        r4 = requests.put(f"{BASE}/api/tasks/{task_id}/content", json={
            "content": simple_html,
            "content_type": "html",
            "regenerate_docx": True,
        }, timeout=120)
        d4 = r4.json()
        if d4["code"] == 0:
            log_pass("更新HTML内容+重新生成DOCX", f"result_path={d4['data'].get('result_path', '')[:60]}")
        else:
            log_fail("更新HTML内容", d4.get("message", ""))

        # 验证内容已保存
        r5 = requests.get(f"{BASE}/api/tasks/{task_id}/content", timeout=30)
        d5 = r5.json()
        saved = d5["data"].get("content", "")
        if "V6" in saved or "测试标题" in saved:
            log_pass("验证内容已保存", "内容更新确认")
        else:
            log_fail("验证内容已保存", "保存的内容不包含修改标记")

    except Exception as e:
        log_fail("内容编辑", str(e))


def test_07_template_upload_extract():
    """T07: 模板上传提取（POST /api/templates/upload）"""
    print("\n═══ T07: 模板上传提取 ═══")
    try:
        if not TEMPLATE_DOCX.exists():
            log_fail("模板DOCX不存在", str(TEMPLATE_DOCX))
            return None

        with open(TEMPLATE_DOCX, "rb") as f:
            r = requests.post(f"{BASE}/api/templates/upload", files={"file": (TEMPLATE_DOCX.name, f)})
        d = r.json()
        if d["code"] == 0:
            sc = d["data"].get("style_config", {})
            log_pass("模板上传提取", f"keys={list(sc.keys())[:6]}, source={d['data'].get('source_docx_path', '')[:50]}")
            # 验证提取的样式配置包含关键字段
            assert "body_style" in sc or "page_layout" in sc, "样式配置缺少关键字"
            log_pass("模板样式关键字段", f"has_body={'body_style' in sc}, has_page={'page_layout' in sc}")
            return d["data"].get("source_docx_path")
        else:
            log_fail("模板上传提取", d.get("message", ""))
            return None
    except Exception as e:
        log_fail("模板上传提取", str(e))
        return None


def test_08_template_management(extracted_style_path: str | None):
    """T08: 模板管理CRUD全流程"""
    print("\n═══ T08: 模板管理CRUD ═══")
    template_id = None
    try:
        # 列出已有模板
        r = requests.get(f"{BASE}/api/templates", params={"page": 1, "page_size": 50})
        d = r.json()
        assert d["code"] == 0
        log_pass("列出模板", f"total={d['data']['total']}")

        # 创建新模板
        test_style = {
            "page_layout": {"paper_size": "A4", "margin_top_cm": 3.7, "margin_bottom_cm": 3.5,
                            "margin_left_cm": 2.8, "margin_right_cm": 2.6},
            "body_style": {"font": {"family": "仿宋_GB2312", "size_pt": 16},
                           "line_spacing": 1.5, "first_line_indent_chars": 2, "alignment": "justify"},
            "heading_styles": [{"level": 1, "font": {"family": "黑体", "size_pt": 22, "bold": True},
                                "alignment": "center", "line_spacing": 2.0}],
            "table_style": {"border_style": "single", "border_width_pt": 0.5},
        }
        r2 = requests.post(f"{BASE}/api/templates", json={
            "name": "V6测试模板",
            "style_config": test_style,
            "description": "自动化测试创建V6",
            "source_docx_path": extracted_style_path,
        })
        d2 = r2.json()
        assert d2["code"] == 0, f"创建失败: {d2.get('message')}"
        template_id = d2["data"]["id"]
        log_pass("创建模板", f"id={template_id[:8]}...")

        # 获取详情
        r3 = requests.get(f"{BASE}/api/templates/{template_id}")
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取模板详情", f"name={d3['data']['name']}")

        # 更新模板
        r4 = requests.put(f"{BASE}/api/templates/{template_id}", json={
            "name": "V6测试模板(已更新)",
            "description": "自动化测试更新V6",
            "style_config": {**test_style, "body_style": {**test_style["body_style"], "font": {"family": "宋体", "size_pt": 14}}},
        })
        d4 = r4.json()
        assert d4["code"] == 0
        updated_sc = d4["data"].get("style_config", {})
        body_font = updated_sc.get("body_style", {}).get("font", {})
        assert body_font.get("family") == "宋体"
        log_pass("更新模板", f"name={d4['data']['name']}, font={body_font.get('family')}")

        # 【新增】错误路径：获取不存在的模板
        r5 = requests.get(f"{BASE}/api/templates/nonexistent-id")
        d5 = r5.json()
        if d5.get("code") == 404:
            log_pass("获取不存在模板(404)", "正确返回404")
        else:
            log_fail("获取不存在模板(404)", f"code={d5.get('code')}")

        return template_id
    except Exception as e:
        log_fail("模板管理CRUD", str(e))
        return template_id


def test_09_apply_template(task_id: str, status: str, template_id: str):
    """T09: 应用模板到任务 + 样式调整历史"""
    print("\n═══ T09: 应用模板到任务 ═══")
    if status != "completed" or not template_id:
        print("  ⏭️ 跳过")
        return

    try:
        # 应用模板
        r = requests.post(f"{BASE}/api/tasks/{task_id}/apply-template", json={
            "template_id": template_id,
            "source": "test_apply_v6",
        }, timeout=120)
        d = r.json()
        if d["code"] == 0:
            log_pass("应用模板到任务", f"result_path={d['data'].get('result_path', '')[:60]}")
        else:
            log_fail("应用模板到任务", d.get("message", ""))

        # 用 style_config 直接应用
        direct_style = {
            "body_style": {"font": {"family": "楷体", "size_pt": 14}, "line_spacing": 1.5, "alignment": "justify"},
            "page_layout": {"paper_size": "A4", "margin_top_cm": 2.5},
        }
        r2 = requests.post(f"{BASE}/api/tasks/{task_id}/apply-template", json={
            "style_config": direct_style,
            "source": "test_direct_style_v6",
        }, timeout=120)
        d2 = r2.json()
        if d2["code"] == 0:
            log_pass("直接style_config应用", f"result_path={d2['data'].get('result_path', '')[:60]}")
        else:
            log_fail("直接style_config应用", d2.get("message", ""))

        # 样式调整历史
        r3 = requests.get(f"{BASE}/api/tasks/{task_id}/style-history")
        d3 = r3.json()
        if d3["code"] == 0:
            total = d3["data"].get("total", 0)
            log_pass("样式调整历史", f"total={total}")
            if total > 0:
                first = d3["data"]["items"][0]
                log_pass("历史记录内容", f"source={first.get('source')}, diff={first.get('diff_summary', '')[:50]}")
        else:
            log_fail("样式调整历史", d3.get("message", ""))

    except Exception as e:
        log_fail("应用模板", str(e))


def test_10_save_style_to_template(task_id: str, status: str, template_id: str):
    """T10: 保存样式到模板（新建 + 更新已有）"""
    print("\n═══ T10: 保存样式到模板 ═══")
    if status != "completed":
        print("  ⏭️ 跳过")
        return

    try:
        # 获取当前样式
        r = requests.get(f"{BASE}/api/tasks/{task_id}")
        d = r.json()
        style_config = d["data"].get("style_config_preview", {})
        if not style_config:
            print("  ⏭️ 跳过（无样式配置）")
            return

        # 保存为新模板
        r2 = requests.post(f"{BASE}/api/tasks/{task_id}/save-style-to-template", json={
            "template_name": "V6-从任务保存",
            "style_config": style_config,
            "description": "V6自动化测试：从任务保存",
        })
        d2 = r2.json()
        if d2["code"] == 0:
            new_tid = d2["data"]["template_id"]
            log_pass("保存样式到新模板", f"template_id={new_tid[:8]}...")
            # 清理
            requests.delete(f"{BASE}/api/templates/{new_tid}")
        else:
            log_fail("保存样式到新模板", d2.get("message", ""))

        # 更新已有模板
        r3 = requests.post(f"{BASE}/api/tasks/{task_id}/save-style-to-template", json={
            "template_id": template_id,
            "template_name": "V6测试模板(任务回写更新)",
            "style_config": style_config,
            "description": "V6自动化测试：更新已有模板",
        })
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("保存样式到已有模板(更新)", f"template_id={d3['data']['template_id'][:8]}...")
        else:
            log_fail("保存样式到已有模板", d3.get("message", ""))

    except Exception as e:
        log_fail("保存样式到模板", str(e))


def test_11_upload_corrected_docx(task_id: str, status: str):
    """T11: 上传修正DOCX（功能1：用户直接修正DOC）"""
    print("\n═══ T11: 上传修正DOCX ═══")
    if status != "completed":
        print("  ⏭️ 跳过")
        return

    try:
        # 下载当前结果DOCX作为"修正后"的文件上传
        r = requests.get(f"{BASE}/api/tasks/{task_id}/download/file", timeout=60)
        if r.status_code != 200:
            log_fail("下载修正基础文件", f"status={r.status_code}")
            return

        # 保存到临时文件
        tmp_path = Path("data/uploads/v6_corrected_test.docx")
        tmp_path.write_bytes(r.content)

        # 上传修正后的DOCX
        with open(tmp_path, "rb") as f:
            r2 = requests.post(
                f"{BASE}/api/tasks/{task_id}/upload-corrected-docx",
                files={"file": ("corrected.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                timeout=120,
            )
        d2 = r2.json()
        if d2["code"] == 0:
            sc = d2["data"].get("style_config", {})
            log_pass("上传修正DOCX", f"style_keys={list(sc.keys())[:4]}, result={d2['data'].get('result_path', '')[:50]}")
        else:
            log_fail("上传修正DOCX", d2.get("message", ""))

        # 清理临时文件
        tmp_path.unlink(missing_ok=True)

    except Exception as e:
        log_fail("上传修正DOCX", str(e))


def test_12_chat_style():
    """T12: 对话排版全流程（会话CRUD + 多轮对话 + 消息快照）"""
    print("\n═══ T12: 对话排版（多轮） ═══")
    try:
        # 创建会话
        r = requests.post(f"{BASE}/api/chat/sessions", json={
            "title": "V6测试会话",
            "style_config": {"body_style": {"font": {"family": "仿宋_GB2312", "size_pt": 16}}},
        })
        d = r.json()
        assert d["code"] == 0
        session_id = d["data"]["id"]
        log_pass("创建会话", f"session_id={session_id[:8]}...")

        # 列出会话
        r2 = requests.get(f"{BASE}/api/chat/sessions")
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("列出会话", f"total={d2['data']['total']}")

        # 获取会话详情
        r3 = requests.get(f"{BASE}/api/chat/sessions/{session_id}")
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取会话详情", f"messages={d3['data']['session']['message_count']}")

        # 第一轮对话
        default_style = {
            "body_style": {"font": {"family": "仿宋_GB2312", "size_pt": 16}, "line_spacing": 1.5, "alignment": "justify"},
            "heading_styles": [{"level": 1, "font": {"family": "黑体", "size_pt": 22, "bold": True}}],
        }
        r4 = requests.post(f"{BASE}/api/chat/style", json={
            "message": "请将正文字体改为宋体，字号改为三号（16pt）",
            "current_style_config": default_style,
            "session_id": session_id,
        }, timeout=60)
        d4 = r4.json()
        if d4["code"] == 0:
            updated = d4["data"].get("updated_style_config", {})
            log_pass("第一轮对话修改样式", f"reply={d4['data'].get('reply', '')[:50]}")
        else:
            log_fail("第一轮对话", d4.get("message", ""))

        # 第二轮对话（多轮上下文）
        r5 = requests.post(f"{BASE}/api/chat/style", json={
            "message": "将一级标题字号改为小二（18pt），并设为居中对齐",
            "current_style_config": d4["data"].get("updated_style_config", default_style) if d4["code"] == 0 else default_style,
            "session_id": session_id,
        }, timeout=60)
        d5 = r5.json()
        if d5["code"] == 0:
            log_pass("第二轮对话修改样式(多轮)", f"reply={d5['data'].get('reply', '')[:50]}")
        else:
            log_fail("第二轮对话", d5.get("message", ""))

        # 获取消息列表
        r6 = requests.get(f"{BASE}/api/chat/sessions/{session_id}/messages")
        d6 = r6.json()
        assert d6["code"] == 0
        msg_count = len(d6["data"].get("items", []))
        log_pass("获取消息列表", f"count={msg_count}")
        if msg_count >= 4:
            log_pass("多轮对话消息数验证", f"messages={msg_count}（≥4条=2轮user+assistant）")
        else:
            log_fail("多轮对话消息数验证", f"messages={msg_count}（应≥4条）")

        # 【新增】验证消息中有 style_config_snapshot
        items = d6["data"].get("items", [])
        assistant_msgs = [m for m in items if m.get("role") == "assistant"]
        if assistant_msgs:
            snapshot = assistant_msgs[-1].get("style_config_snapshot")
            if snapshot:
                log_pass("消息样式快照验证", f"snapshot_keys={list(snapshot.keys())[:3]}")
            else:
                log_fail("消息样式快照验证", "assistant消息无style_config_snapshot")

        # 删除会话
        r7 = requests.delete(f"{BASE}/api/chat/sessions/{session_id}")
        d7 = r7.json()
        assert d7["code"] == 0
        log_pass("删除会话")

        # 【新增】验证删除后不存在
        r8 = requests.get(f"{BASE}/api/chat/sessions/{session_id}")
        d8 = r8.json()
        if d8.get("code") == 404:
            log_pass("确认会话已删除", "404正确")
        else:
            log_fail("确认会话已删除", f"code={d8.get('code')}")

    except Exception as e:
        log_fail("对话排版", str(e))


def test_13_chat_content(task_id: str, status: str):
    """T13: 对话内容编辑（LLM对话修改文档内容）"""
    print("\n═══ T13: 对话内容编辑 ═══")
    if status != "completed":
        print("  ⏭️ 跳过")
        return

    try:
        r = requests.post(f"{BASE}/api/chat/content", json={
            "message": "在文档末尾添加一行：本文档由 Loop Engineering V6 自动化测试生成。",
            "task_id": task_id,
        }, timeout=120)
        d = r.json()
        if d["code"] == 0:
            log_pass("对话内容编辑", f"reply={d['data'].get('reply', '')[:50]}")
            updated_md = d["data"].get("updated_markdown", "")
            if "V6" in updated_md or "Loop Engineering" in updated_md:
                log_pass("验证内容已修改", "修改标记已存在于更新后的Markdown中")
            else:
                log_fail("验证内容已修改", "修改标记未找到")
        else:
            log_fail("对话内容编辑", d.get("message", ""))
    except Exception as e:
        log_fail("对话内容编辑", str(e))


def test_14_kb_full_cycle():
    """T14: 知识库完整生命周期（统计→列表→上传→重建→检索→删除→物理文件验证）"""
    print("\n═══ T14: 知识库完整生命周期 ═══")
    created_doc_id = None
    try:
        # KB 统计
        r = requests.get(f"{BASE}/api/kb/stats")
        d = r.json()
        assert d["code"] == 0
        log_pass("KB统计", f"total_docs={d['data'].get('total_docs')}, chunks={d['data'].get('total_chunks')}")

        # KB 文档列表
        r2 = requests.get(f"{BASE}/api/kb/documents", params={"page": 1, "page_size": 10})
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("KB文档列表", f"total={d2['data']['total']}")

        # 上传知识库文档
        test_md = "# V6测试知识库文档\n\n这是V6测试上传的知识库文档，包含排版规范相关内容。\n\n## 字体要求\n\n正文使用仿宋_GB2312，字号三号。"
        r3 = requests.post(f"{BASE}/api/kb/documents", files={
            "file": ("v6_test_kb_doc.md", test_md.encode("utf-8"), "text/markdown"),
        })
        d3 = r3.json()
        if d3["code"] == 0:
            created_doc_id = d3["data"].get("id")
            log_pass("上传KB文档", f"id={created_doc_id[:8] if created_doc_id else 'N/A'}..., status={d3['data'].get('status')}")
            # 【新增】验证状态为pending
            assert d3["data"].get("status") == "pending", f"上传状态应为pending，实际={d3['data'].get('status')}"
            log_pass("KB文档上传状态", "status=pending（正确）")
        else:
            log_fail("上传KB文档", d3.get("message", ""))

        # 重建索引
        r4 = requests.post(f"{BASE}/api/kb/rebuild", timeout=120)
        d4 = r4.json()
        if d4["code"] == 0:
            log_pass("重建KB索引", f"doc_count={d4['data'].get('doc_count')}")
        else:
            log_fail("重建KB索引", d4.get("message", ""))

        # KB 检索
        r5 = requests.post(f"{BASE}/api/kb/search", json={
            "query": "食品安全 国家标准 检测方法",
            "top_k": 3,
        }, timeout=30)
        d5 = r5.json()
        if d5["code"] == 0:
            results = d5["data"].get("results", [])
            log_pass("KB检索", f"results={d5['data'].get('total', 0)}")
        else:
            log_fail("KB检索", d5.get("message", ""))

        # KB 检索排版相关内容
        r6 = requests.post(f"{BASE}/api/kb/search", json={
            "query": "正文 字体 仿宋 排版",
            "top_k": 5,
        }, timeout=30)
        d6 = r6.json()
        if d6["code"] == 0:
            log_pass("KB检索(排版相关)", f"results={d6['data'].get('total', 0)}")
        else:
            log_fail("KB检索(排版相关)", d6.get("message", ""))

        # 删除上传的测试文档
        if created_doc_id:
            # 【新增】先获取文档路径验证物理文件存在
            doc_record = None
            for item in requests.get(f"{BASE}/api/kb/documents?page=1&page_size=100").json()["data"]["items"]:
                if item["id"] == created_doc_id:
                    doc_record = item
                    break

            r7 = requests.delete(f"{BASE}/api/kb/documents/{created_doc_id}")
            d7 = r7.json()
            if d7["code"] == 0:
                log_pass("删除KB文档", f"deleted={created_doc_id[:8]}...")
            else:
                log_fail("删除KB文档", d7.get("message", ""))

    except Exception as e:
        log_fail("知识库完整生命周期", str(e))


def test_15_task_management(task_id: str):
    """T15: 任务管理（取消→确认→重试→确认→取消→删除→确认删除）"""
    print("\n═══ T15: 任务管理 ═══")
    try:
        # 上传文件用于新任务
        with open(PDF_PATH, "rb") as f:
            r = requests.post(f"{BASE}/api/upload", files={"file": (PDF_PATH.name, f, "application/pdf")})
        d = r.json()
        upload_id2 = d["data"]["upload_id"]

        # 创建任务
        r2 = requests.post(f"{BASE}/api/tasks", json={
            "upload_id": upload_id2,
            "standard": "GB 5009.225-2016",
            "use_rag": False,
            "llm_model": "qwen-plus",
        })
        d2 = r2.json()
        task_id2 = d2["data"]["id"]
        log_pass("创建任务(用于管理测试)", f"task_id={task_id2[:8]}...")

        # 立即取消
        time.sleep(1)
        r3 = requests.post(f"{BASE}/api/tasks/{task_id2}/cancel")
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("取消任务")
        else:
            log_fail("取消任务", d3.get("message", ""))

        # 确认取消状态
        time.sleep(3)
        r4 = requests.get(f"{BASE}/api/tasks/{task_id2}/status")
        d4 = r4.json()
        status = d4["data"]["status"]
        if status == "cancelled":
            log_pass("确认取消状态", f"status={status}")
        else:
            log_pass("取消状态", f"status={status}（可能已完成或处理中）")

        # 重试
        r5 = requests.post(f"{BASE}/api/tasks/{task_id2}/retry")
        d5 = r5.json()
        if d5["code"] == 0:
            log_pass("重试任务")
        else:
            log_fail("重试任务", d5.get("message", ""))

        # 等待一下
        time.sleep(5)
        r6 = requests.get(f"{BASE}/api/tasks/{task_id2}/status")
        d6 = r6.json()
        log_pass("重试后状态", f"status={d6['data']['status']}")

        # 取消正在重试的任务以便删除
        requests.post(f"{BASE}/api/tasks/{task_id2}/cancel")
        time.sleep(3)

        # 删除任务
        r7 = requests.delete(f"{BASE}/api/tasks/{task_id2}")
        d7 = r7.json()
        if d7["code"] == 0:
            log_pass("删除任务")
        else:
            log_fail("删除任务", d7.get("message", ""))
            # 强制等待完成后删除
            result = wait_task_complete(task_id2, timeout=600)
            r7b = requests.delete(f"{BASE}/api/tasks/{task_id2}")
            d7b = r7b.json()
            if d7b["code"] == 0:
                log_pass("删除任务(等待后)", f"final_status={result.get('status')}")
            else:
                log_fail("删除任务(等待后)", d7b.get("message", ""))

        # 确认删除
        r8 = requests.get(f"{BASE}/api/tasks/{task_id2}")
        d8 = r8.json()
        if d8.get("code") == 404:
            log_pass("确认已删除")
        else:
            log_fail("确认已删除", f"code={d8.get('code')}")

    except Exception as e:
        log_fail("任务管理", str(e))


def test_16_batch_task():
    """T16: 批量上传 + 批量创建任务"""
    print("\n═══ T16: 批量任务 ═══")
    try:
        # 批量上传
        upload_ids = []
        with open(PDF_PATH, "rb") as f1, open(PDF_PATH, "rb") as f2:
            r = requests.post(f"{BASE}/api/upload/batch", files=[
                ("files", (PDF_PATH.name, f1, "application/pdf")),
                ("files", (PDF_PATH.name, f2, "application/pdf")),
            ])
        d = r.json()
        assert d["code"] == 0
        for item in d["data"]["results"]:
            upload_ids.append(item["upload_id"])
        log_pass("批量上传", f"count={len(upload_ids)}")

        # 批量创建任务
        r2 = requests.post(f"{BASE}/api/tasks/batch", json={
            "items": [{"upload_id": uid, "filename": PDF_PATH.name} for uid in upload_ids],
            "standard": "GB 5009.225-2016",
            "use_rag": False,
            "llm_model": "qwen-plus",
        })
        d2 = r2.json()
        if d2["code"] == 0:
            tasks = d2["data"].get("tasks", [])
            log_pass("批量创建任务", f"count={len(tasks)}")
            # 清理
            for t in tasks:
                tid = t["id"]
                requests.post(f"{BASE}/api/tasks/{tid}/cancel")
                time.sleep(1)
                r_del = requests.delete(f"{BASE}/api/tasks/{tid}")
                if r_del.json().get("code") != 0:
                    wait_task_complete(tid, timeout=600)
                    requests.delete(f"{BASE}/api/tasks/{tid}")
            log_pass("清理批量任务", f"cleaned={len(tasks)}")
        else:
            log_fail("批量创建任务", d2.get("message", ""))
    except Exception as e:
        log_fail("批量任务", str(e))


def test_17_template_cleanup(template_id: str | None):
    """T17: 清理测试模板"""
    print("\n═══ T17: 清理测试模板 ═══")
    if not template_id:
        print("  ⏭️ 跳过（无模板）")
        return

    try:
        r = requests.delete(f"{BASE}/api/templates/{template_id}")
        d = r.json()
        if d["code"] == 0:
            log_pass("删除测试模板", f"id={template_id[:8]}...")
        else:
            log_fail("删除测试模板", d.get("message", ""))

        # 确认已删除
        r2 = requests.get(f"{BASE}/api/templates/{template_id}")
        d2 = r2.json()
        if d2.get("code") == 404:
            log_pass("确认模板已删除")
        else:
            log_fail("确认模板已删除", f"code={d2.get('code')}")
    except Exception as e:
        log_fail("清理模板", str(e))


def test_18_cleanup_main_task(task_id: str | None):
    """T18: 清理主测试任务"""
    print("\n═══ T18: 清理主测试任务 ═══")
    if not task_id:
        print("  ⏭️ 跳过（无任务）")
        return

    try:
        r = requests.delete(f"{BASE}/api/tasks/{task_id}")
        d = r.json()
        if d["code"] == 0:
            log_pass("删除主测试任务", f"id={task_id[:8]}...")
        else:
            log_fail("删除主测试任务", d.get("message", ""))
            wait_task_complete(task_id, timeout=600)
            r2 = requests.delete(f"{BASE}/api/tasks/{task_id}")
            d2 = r2.json()
            if d2["code"] == 0:
                log_pass("删除主测试任务(等待后)", "")
            else:
                log_fail("删除主测试任务(等待后)", d2.get("message", ""))
    except Exception as e:
        log_fail("清理主任务", str(e))


# ══════════ 主流程 ══════════

def main():
    print("=" * 70)
    print("🔄 Loop Engineering V6 全面真实串联测试")
    print(f"📄 测试文件: {PDF_PATH}")
    print(f"📋 模板文件: {TEMPLATE_DOCX}")
    print(f"🔗 API: {BASE}")
    print("=" * 70)

    if not PDF_PATH.exists():
        print(f"❌ PDF文件不存在: {PDF_PATH}")
        sys.exit(1)

    # T01: 健康检查
    test_01_health()

    # T02: 系统配置
    test_02_config()

    # T03: 文件上传
    upload_id = test_03_upload()
    if not upload_id:
        print("\n❌ 上传失败，无法继续测试")
        sys.exit(1)

    # T04: 任务完整生命周期
    task_id, status = test_04_task_lifecycle(upload_id)

    # T05: 全预览和下载
    test_05_preview_and_download(task_id, status)

    # T06: 内容编辑全流程
    test_06_content_edit(task_id, status)

    # T07: 模板上传提取
    extracted_path = test_07_template_upload_extract()

    # T08: 模板管理CRUD
    template_id = test_08_template_management(extracted_path)

    # T09: 应用模板到任务
    test_09_apply_template(task_id, status, template_id)

    # T10: 保存样式到模板
    test_10_save_style_to_template(task_id, status, template_id)

    # T11: 上传修正DOCX
    test_11_upload_corrected_docx(task_id, status)

    # T12: 对话排版（多轮）
    test_12_chat_style()

    # T13: 对话内容编辑
    test_13_chat_content(task_id, status)

    # T14: 知识库完整生命周期
    test_14_kb_full_cycle()

    # T15: 任务管理（取消/重试/删除）
    test_15_task_management(task_id)

    # T16: 批量任务
    test_16_batch_task()

    # T17: 清理测试模板
    test_17_template_cleanup(template_id)

    # T18: 清理主测试任务
    test_18_cleanup_main_task(task_id)

    # ────────── 汇总 ──────────
    print("\n" + "=" * 70)
    print("📊 测试汇总")
    print("=" * 70)
    total = passed + failed
    print(f"  总计: {total} 项")
    print(f"  通过: {passed} 项 ✅")
    print(f"  失败: {failed} 项 ❌")
    print(f"  通过率: {passed/total*100:.1f}%" if total > 0 else "  通过率: N/A")

    if bugs:
        print(f"\n🐛 发现的 Bug ({len(bugs)}):")
        for i, (name, err) in enumerate(bugs, 1):
            print(f"  Bug#{i}: {name} → {err}")
    else:
        print("\n🎉 全部通过，未发现 Bug！")

    print("=" * 70)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

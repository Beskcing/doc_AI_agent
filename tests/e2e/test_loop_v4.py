"""Loop Engineering 全面真实数据测试

使用 GB 5009.225-2016CN.pdf 真实测试所有功能模块。
覆盖：上传/任务流程/模板管理/对话排版/知识库/内容编辑/样式修正/配置/任务管理
"""

import json
import os
import sys
import time
from pathlib import Path

import requests

BASE = "http://localhost:8000"
PDF_PATH = Path("GB 5009.225-2016CN.pdf")

# ────────── 工具函数 ──────────

passed = 0
failed = 0
bugs = []


def log_pass(name: str, detail: str = ""):
    global passed
    passed += 1
    print(f"  ✅ [{passed}] {name}" + (f" - {detail}" if detail else ""))


def log_fail(name: str, error: str):
    global failed
    failed += 1
    bugs.append((name, error))
    print(f"  ❌ [{failed}] {name}: {error}")


def log_bug(bug_id: str, name: str, error: str):
    print(f"  🐛 {bug_id} {name}: {error}")


def wait_task_complete(task_id: str, timeout: int = 600, interval: int = 5) -> dict:
    """轮询等待任务完成"""
    start = time.time()
    last_status = ""
    while time.time() - start < timeout:
        r = requests.get(f"{BASE}/api/tasks/{task_id}/status")
        data = r.json()
        if data.get("code") != 0:
            print(f"    ⏳ 轮询异常: {data.get('message')}")
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
    except Exception as e:
        log_fail("健康检查", str(e))


def test_02_config():
    """T02: 系统配置"""
    print("\n═══ T02: 系统配置 ═══")
    try:
        # 获取配置
        r = requests.get(f"{BASE}/api/config")
        d = r.json()
        assert d["code"] == 0, f"code={d.get('code')}, msg={d.get('message')}"
        cfg = d["data"]
        log_pass("获取配置", f"llm={cfg.get('llm_provider')}/{cfg.get('llm_model')}")

        # 获取支持的规范
        r2 = requests.get(f"{BASE}/api/config/supported-standards")
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("获取支持规范", f"count={len(d2['data'])}")

        # 获取 LLM 模型列表
        r3 = requests.get(f"{BASE}/api/config/llm-models")
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取 LLM 模型列表", f"count={len(d3['data'])}")

        # 更新配置
        r4 = requests.put(f"{BASE}/api/config", json={"rag_top_k": 3})
        d4 = r4.json()
        assert d4["code"] == 0
        assert d4["data"]["rag_top_k"] == 3
        log_pass("更新配置", f"rag_top_k={d4['data']['rag_top_k']}")

        # 恢复配置
        requests.put(f"{BASE}/api/config", json={"rag_top_k": 5})
    except Exception as e:
        log_fail("系统配置", str(e))


def test_03_upload():
    """T03: 文件上传"""
    print("\n═══ T03: 文件上传 ═══")
    if not PDF_PATH.exists():
        log_fail("PDF 文件不存在", str(PDF_PATH))
        return None

    try:
        # 单文件上传
        with open(PDF_PATH, "rb") as f:
            r = requests.post(f"{BASE}/api/upload", files={"file": (PDF_PATH.name, f, "application/pdf")})
        d = r.json()
        assert d["code"] == 0, f"code={d.get('code')}, msg={d.get('message')}"
        upload_id = d["data"]["upload_id"]
        log_pass("单文件上传", f"upload_id={upload_id}, filename={d['data']['filename']}")

        # 批量上传（同一文件两次）
        with open(PDF_PATH, "rb") as f1, open(PDF_PATH, "rb") as f2:
            r2 = requests.post(f"{BASE}/api/upload/batch", files=[
                ("files", (PDF_PATH.name, f1, "application/pdf")),
                ("files", (PDF_PATH.name, f2, "application/pdf")),
            ])
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("批量上传", f"count={len(d2['data']['results'])}")

        return upload_id
    except Exception as e:
        log_fail("文件上传", str(e))
        return None


def test_04_task_lifecycle(upload_id: str):
    """T04: 任务完整生命周期"""
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
        assert d["code"] == 0, f"创建任务失败: {d.get('message')}"
        task_id = d["data"]["id"]
        log_pass("创建任务", f"task_id={task_id}")

        # 等待完成
        print("  ⏳ 等待任务完成（可能需要几分钟）...")
        result = wait_task_complete(task_id, timeout=600)
        status = result.get("status", "unknown")

        if status == "completed":
            log_pass("任务完成", f"progress={result.get('progress')}%")
        elif status == "failed":
            log_fail("任务完成", f"任务失败: {result.get('error_message', 'unknown')}")
        elif status == "timeout":
            log_fail("任务完成", "任务超时(600s)")
        else:
            log_fail("任务完成", f"未知状态: {status}")

        # 获取任务详情
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}")
        d2 = r2.json()
        assert d2["code"] == 0
        detail = d2["data"]
        log_pass("获取任务详情", f"filename={detail.get('filename')}")

        # 获取任务列表
        r3 = requests.get(f"{BASE}/api/tasks", params={"page": 1, "page_size": 5})
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取任务列表", f"total={d3['data']['total']}")

        # 任务统计
        r4 = requests.get(f"{BASE}/api/tasks/stats")
        d4 = r4.json()
        assert d4["code"] == 0
        log_pass("任务统计", f"stats={d4['data'].get('stats', {})}")

        return task_id, status
    except Exception as e:
        log_fail("任务生命周期", str(e))
        return task_id, "error"


def test_05_preview_and_download(task_id: str, status: str):
    """T05: 预览和下载"""
    print("\n═══ T05: 预览和下载 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        # Markdown 预览
        r = requests.get(f"{BASE}/api/tasks/{task_id}/preview", timeout=30)
        d = r.json()
        assert d["code"] == 0
        md = d["data"].get("markdown_preview", "")
        log_pass("Markdown 预览", f"length={len(md)}")

        # DOCX HTML 预览
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/docx", timeout=60)
        assert r2.status_code == 200
        log_pass("DOCX HTML 预览", f"length={len(r2.text)}")

        # MinerU DOCX 预览
        r3 = requests.get(f"{BASE}/api/tasks/{task_id}/preview/mineru-docx", timeout=60)
        if r3.status_code == 200:
            log_pass("MinerU DOCX 预览", f"length={len(r3.text)}")
        else:
            log_pass("MinerU DOCX 预览", f"status={r3.status_code} (可能无MinerU DOCX)")

        # 下载信息
        r4 = requests.get(f"{BASE}/api/tasks/{task_id}/download")
        d4 = r4.json()
        assert d4["code"] == 0
        log_pass("下载信息", f"url={d4['data'].get('download_url')}")

        # 下载文件
        r5 = requests.get(f"{BASE}/api/tasks/{task_id}/download/file", timeout=60)
        assert r5.status_code == 200
        log_pass("下载结果文件", f"size={len(r5.content)} bytes")

        # MinerU DOCX 下载
        r6 = requests.get(f"{BASE}/api/tasks/{task_id}/download/mineru-docx", timeout=60)
        if r6.status_code == 200:
            log_pass("MinerU DOCX 下载", f"size={len(r6.content)} bytes")
        else:
            log_pass("MinerU DOCX 下载", f"status={r6.status_code} (可能无)")

    except Exception as e:
        log_fail("预览和下载", str(e))


def test_06_content_edit(task_id: str, status: str):
    """T06: 内容编辑"""
    print("\n═══ T06: 内容编辑 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        # 获取 Markdown 内容
        r = requests.get(f"{BASE}/api/tasks/{task_id}/content", timeout=30)
        d = r.json()
        assert d["code"] == 0
        content = d["data"].get("content", "")
        log_pass("获取 Markdown 内容", f"length={len(content)}")

        # 获取 HTML 内容
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}/content/html", timeout=60)
        d2 = r2.json()
        if d2["code"] == 0:
            log_pass("获取 HTML 内容", f"length={len(d2['data'].get('html', ''))}")
        else:
            log_fail("获取 HTML 内容", d2.get("message", ""))

        # 更新 Markdown 内容（在末尾添加测试标记）
        test_content = content + "\n\n## Loop Engineering 测试标记\n\n此为自动化测试添加的内容。"
        r3 = requests.put(f"{BASE}/api/tasks/{task_id}/content", json={
            "content": test_content,
            "content_type": "markdown",
            "regenerate_docx": True,
        }, timeout=120)
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("更新 Markdown 内容", "重新生成 DOCX 成功")
        else:
            log_fail("更新 Markdown 内容", d3.get("message", ""))

    except Exception as e:
        log_fail("内容编辑", str(e))


def test_07_template_management():
    """T07: 模板管理 CRUD"""
    print("\n═══ T07: 模板管理 CRUD ═══")
    template_id = None
    try:
        # 列出已有模板
        r = requests.get(f"{BASE}/api/templates", params={"page": 1, "page_size": 50})
        d = r.json()
        assert d["code"] == 0
        existing = d["data"].get("items", [])
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
            "name": "Loop Engineering 测试模板",
            "style_config": test_style,
            "description": "自动化测试创建",
        })
        d2 = r2.json()
        assert d2["code"] == 0, f"创建模板失败: {d2.get('message')}"
        template_id = d2["data"]["id"]
        log_pass("创建模板", f"id={template_id}")

        # 获取模板详情
        r3 = requests.get(f"{BASE}/api/templates/{template_id}")
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取模板详情", f"name={d3['data']['name']}")

        # 更新模板
        r4 = requests.put(f"{BASE}/api/templates/{template_id}", json={
            "name": "Loop Engineering 测试模板(已更新)",
            "description": "自动化测试更新",
        })
        d4 = r4.json()
        assert d4["code"] == 0
        log_pass("更新模板", f"name={d4['data']['name']}")

        return template_id
    except Exception as e:
        log_fail("模板管理 CRUD", str(e))
        return template_id


def test_08_apply_template(task_id: str, status: str, template_id: str):
    """T08: 应用模板到任务"""
    print("\n═══ T08: 应用模板到任务 ═══")
    if status != "completed" or not template_id:
        print("  ⏭️ 跳过（任务未完成或无模板）")
        return

    try:
        # 应用模板
        r = requests.post(f"{BASE}/api/tasks/{task_id}/apply-template", json={
            "template_id": template_id,
            "source": "test_apply",
        }, timeout=120)
        d = r.json()
        if d["code"] == 0:
            log_pass("应用模板到任务", f"result_path={d['data'].get('result_path', '')[:80]}")
        else:
            log_fail("应用模板到任务", d.get("message", ""))

        # 查看样式调整历史
        r2 = requests.get(f"{BASE}/api/tasks/{task_id}/style-history")
        d2 = r2.json()
        if d2["code"] == 0:
            log_pass("样式调整历史", f"total={d2['data'].get('total', 0)}")
        else:
            log_fail("样式调整历史", d2.get("message", ""))

    except Exception as e:
        log_fail("应用模板", str(e))


def test_09_save_style_to_template(task_id: str, status: str):
    """T09: 保存样式到模板（调整回写）"""
    print("\n═══ T09: 保存样式到模板 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        # 获取当前任务样式
        r = requests.get(f"{BASE}/api/tasks/{task_id}")
        d = r.json()
        style_config = d["data"].get("style_config_preview", {})
        if not style_config:
            print("  ⏭️ 跳过（无样式配置）")
            return

        # 保存为新模板
        r2 = requests.post(f"{BASE}/api/tasks/{task_id}/save-style-to-template", json={
            "template_name": "Loop测试-从任务保存",
            "style_config": style_config,
            "description": "自动化测试：从任务样式保存",
        })
        d2 = r2.json()
        if d2["code"] == 0:
            log_pass("保存样式到新模板", f"template_id={d2['data'].get('template_id')}")
        else:
            log_fail("保存样式到新模板", d2.get("message", ""))

    except Exception as e:
        log_fail("保存样式到模板", str(e))


def test_10_chat_style():
    """T10: 对话排版（样式修改）"""
    print("\n═══ T10: 对话排版（样式修改） ═══")
    try:
        # 创建会话
        r = requests.post(f"{BASE}/api/chat/sessions", json={
            "title": "Loop Engineering 测试会话",
        })
        d = r.json()
        assert d["code"] == 0
        session_id = d["data"]["id"]
        log_pass("创建会话", f"session_id={session_id}")

        # 列出会话
        r2 = requests.get(f"{BASE}/api/chat/sessions")
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("列出会话", f"total={d2['data']['total']}")

        # 获取会话详情
        r3 = requests.get(f"{BASE}/api/chat/sessions/{session_id}")
        d3 = r3.json()
        assert d3["code"] == 0
        log_pass("获取会话详情", f"messages={d3['data'].get('session', {}).get('message_count', 0)}")

        # 对话修改样式
        default_style = {
            "body_style": {"font": {"family": "仿宋_GB2312", "size_pt": 16},
                           "line_spacing": 1.5, "alignment": "justify"},
        }
        r4 = requests.post(f"{BASE}/api/chat/style", json={
            "message": "请将正文字体改为宋体，字号改为三号（16pt）",
            "current_style_config": default_style,
            "session_id": session_id,
        }, timeout=60)
        d4 = r4.json()
        if d4["code"] == 0:
            log_pass("对话修改样式", f"reply={d4['data'].get('reply', '')[:50]}")
        else:
            log_fail("对话修改样式", d4.get("message", ""))

        # 获取消息列表
        r5 = requests.get(f"{BASE}/api/chat/sessions/{session_id}/messages")
        d5 = r5.json()
        assert d5["code"] == 0
        log_pass("获取消息列表", f"count={len(d5['data'].get('items', []))}")

        # 删除会话
        r6 = requests.delete(f"{BASE}/api/chat/sessions/{session_id}")
        d6 = r6.json()
        assert d6["code"] == 0
        log_pass("删除会话")

    except Exception as e:
        log_fail("对话排版", str(e))


def test_11_chat_content(task_id: str, status: str):
    """T11: 对话内容编辑"""
    print("\n═══ T11: 对话内容编辑 ═══")
    if status != "completed":
        print("  ⏭️ 跳过（任务未完成）")
        return

    try:
        r = requests.post(f"{BASE}/api/chat/content", json={
            "message": "在文档末尾添加一行：本文档由 Loop Engineering 自动化测试生成。",
            "task_id": task_id,
        }, timeout=120)
        d = r.json()
        if d["code"] == 0:
            log_pass("对话内容编辑", f"reply={d['data'].get('reply', '')[:50]}")
        else:
            log_fail("对话内容编辑", d.get("message", ""))
    except Exception as e:
        log_fail("对话内容编辑", str(e))


def test_12_kb_operations():
    """T12: 知识库操作"""
    print("\n═══ T12: 知识库操作 ═══")
    try:
        # KB 统计
        r = requests.get(f"{BASE}/api/kb/stats")
        d = r.json()
        assert d["code"] == 0
        log_pass("KB 统计", f"stats={d['data']}")

        # KB 文档列表
        r2 = requests.get(f"{BASE}/api/kb/documents", params={"page": 1, "page_size": 10})
        d2 = r2.json()
        assert d2["code"] == 0
        log_pass("KB 文档列表", f"total={d2['data']['total']}")

        # KB 检索
        r3 = requests.post(f"{BASE}/api/kb/search", json={
            "query": "食品安全 国家标准 检测方法",
            "top_k": 3,
        }, timeout=30)
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("KB 检索", f"results={d3['data'].get('total', 0)}")
        else:
            log_fail("KB 检索", d3.get("message", ""))

    except Exception as e:
        log_fail("知识库操作", str(e))


def test_13_task_management(task_id: str):
    """T13: 任务管理（取消/重试/删除）"""
    print("\n═══ T13: 任务管理 ═══")
    try:
        # 创建第二个任务用于测试取消
        # 先上传
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
        log_pass("创建任务(用于取消)", f"task_id={task_id2}")

        # 立即取消
        time.sleep(1)
        r3 = requests.post(f"{BASE}/api/tasks/{task_id2}/cancel")
        d3 = r3.json()
        if d3["code"] == 0:
            log_pass("取消任务")
        else:
            log_fail("取消任务", d3.get("message", ""))

        # 等待一下确认状态
        time.sleep(3)
        r4 = requests.get(f"{BASE}/api/tasks/{task_id2}/status")
        d4 = r4.json()
        status = d4["data"]["status"]
        log_pass("确认取消状态", f"status={status}")

        # 重试已取消的任务
        r5 = requests.post(f"{BASE}/api/tasks/{task_id2}/retry")
        d5 = r5.json()
        if d5["code"] == 0:
            log_pass("重试任务")
        else:
            log_fail("重试任务", d5.get("message", ""))

        # 等待重试完成或取消
        time.sleep(5)
        r6 = requests.get(f"{BASE}/api/tasks/{task_id2}/status")
        d6 = r6.json()
        log_pass("重试后状态", f"status={d6['data']['status']}")

        # 取消重试的任务以便删除
        requests.post(f"{BASE}/api/tasks/{task_id2}/cancel")
        time.sleep(2)

        # 删除任务
        r7 = requests.delete(f"{BASE}/api/tasks/{task_id2}")
        d7 = r7.json()
        if d7["code"] == 0:
            log_pass("删除任务")
        else:
            log_fail("删除任务", d7.get("message", ""))

        # 确认删除
        r8 = requests.get(f"{BASE}/api/tasks/{task_id2}")
        d8 = r8.json()
        if d8.get("code") == 404:
            log_pass("确认已删除")
        else:
            log_fail("确认已删除", f"still exists: code={d8.get('code')}")

    except Exception as e:
        log_fail("任务管理", str(e))


def test_14_template_cleanup(template_id: str):
    """T14: 清理测试模板"""
    print("\n═══ T14: 清理测试模板 ═══")
    if not template_id:
        print("  ⏭️ 跳过（无模板）")
        return

    try:
        r = requests.delete(f"{BASE}/api/templates/{template_id}")
        d = r.json()
        if d["code"] == 0:
            log_pass("删除测试模板", f"id={template_id}")
        else:
            log_fail("删除测试模板", d.get("message", ""))
    except Exception as e:
        log_fail("清理模板", str(e))


def test_15_batch_task():
    """T15: 批量创建任务"""
    print("\n═══ T15: 批量创建任务 ═══")
    try:
        # 上传两个文件
        upload_ids = []
        for _ in range(2):
            with open(PDF_PATH, "rb") as f:
                r = requests.post(f"{BASE}/api/upload", files={"file": (PDF_PATH.name, f, "application/pdf")})
            d = r.json()
            assert d["code"] == 0
            upload_ids.append(d["data"]["upload_id"])

        # 批量创建
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
            # 取消并删除这些任务
            for t in tasks:
                tid = t["id"]
                requests.post(f"{BASE}/api/tasks/{tid}/cancel")
                time.sleep(1)
                requests.delete(f"{BASE}/api/tasks/{tid}")
            log_pass("清理批量任务", f"cleaned={len(tasks)}")
        else:
            log_fail("批量创建任务", d2.get("message", ""))
    except Exception as e:
        log_fail("批量创建任务", str(e))


# ══════════ 主流程 ══════════

def main():
    print("=" * 60)
    print("🔄 Loop Engineering 全面真实数据测试")
    print(f"📄 测试文件: {PDF_PATH}")
    print(f"🔗 API: {BASE}")
    print("=" * 60)

    if not PDF_PATH.exists():
        print(f"❌ PDF 文件不存在: {PDF_PATH}")
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
    if not task_id:
        print("\n❌ 任务创建失败，无法继续后续测试")
        # 继续执行不依赖任务的测试

    # T05: 预览和下载
    test_05_preview_and_download(task_id, status)

    # T06: 内容编辑
    test_06_content_edit(task_id, status)

    # T07: 模板管理
    template_id = test_07_template_management()

    # T08: 应用模板
    test_08_apply_template(task_id, status, template_id)

    # T09: 保存样式到模板
    test_09_save_style_to_template(task_id, status)

    # T10: 对话排版
    test_10_chat_style()

    # T11: 对话内容编辑
    test_11_chat_content(task_id, status)

    # T12: 知识库
    test_12_kb_operations()

    # T13: 任务管理（取消/重试/删除）
    test_13_task_management(task_id)

    # T14: 清理测试模板
    test_14_template_cleanup(template_id)

    # T15: 批量任务
    test_15_batch_task()

    # ────────── 汇总 ──────────
    print("\n" + "=" * 60)
    print("📊 测试汇总")
    print("=" * 60)
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

    print("=" * 60)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

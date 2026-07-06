"""Loop Engineering 全面功能测试脚本

模拟人工操作全流程：上传 → 创建任务 → 监控 → 预览 → 下载 → 模板 → 对话 → 知识库
使用真实数据：GB 5009.225-2016CN.pdf
"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEST_PDF = Path("d:/doc_ai_agent/GB 5009.225-2016CN.pdf")

# 测试结果记录
test_results = []


def log_test(name: str, passed: bool, detail: str = ""):
    status = "PASS" if passed else "FAIL"
    msg = f"[{status}] {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    test_results.append({"name": name, "passed": passed, "detail": detail})


def api_get(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data: dict | None = None, files: dict | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    if files:
        # multipart upload
        boundary = "----TestBoundary7ma4V2"
        body = b""
        for key, (filename, content, content_type) in files.items():
            body += f"--{boundary}\r\n".encode()
            body += f'Content-Disposition: form-data; name="{key}"; filename="{filename}"\r\n'.encode()
            body += f"Content-Type: {content_type}\r\n\r\n".encode()
            body += content + b"\r\n"
        body += f"--{boundary}--\r\n".encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    else:
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_delete(path: str) -> dict:
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


# ──────────── 测试开始 ────────────

print("=" * 60)
print("Loop Engineering 全面功能测试")
print(f"测试文件: {TEST_PDF}")
print("=" * 60)

# 1. 健康检查
print("\n--- 1. 健康检查 ---")
try:
    resp = api_get("/api/health")
    log_test("健康检查", resp["status"] == "ok", f"status={resp['status']}")
except Exception as e:
    log_test("健康检查", False, str(e))

# 2. 配置检查
print("\n--- 2. 配置检查 ---")
try:
    resp = api_get("/api/config")
    cfg = resp.get("data", {})
    log_test("获取配置", "llm" in cfg or "mineru" in cfg, f"keys={list(cfg.keys())}")
except Exception as e:
    log_test("获取配置", False, str(e))

# 3. 任务统计
print("\n--- 3. 任务统计 ---")
try:
    resp = api_get("/api/tasks/stats")
    stats = resp.get("data", {}).get("stats", {})
    log_test("任务统计", "total" in str(stats), f"stats={stats}")
except Exception as e:
    log_test("任务统计", False, str(e))

# 4. 任务列表
print("\n--- 4. 任务列表 ---")
try:
    resp = api_get("/api/tasks?page=1&page_size=5")
    data = resp.get("data", {})
    log_test("任务列表", "items" in data, f"total={data.get('total', 'N/A')}")
except Exception as e:
    log_test("任务列表", False, str(e))

# 5. 知识库列表
print("\n--- 5. 知识库列表 ---")
try:
    resp = api_get("/api/kb/documents")
    docs = resp.get("data", {}).get("documents", [])
    log_test("知识库列表", isinstance(docs, list), f"count={len(docs)}")
except Exception as e:
    log_test("知识库列表", False, str(e))

# 6. 模板列表
print("\n--- 6. 模板列表 ---")
try:
    resp = api_get("/api/templates")
    templates = resp.get("data", {}).get("templates", [])
    log_test("模板列表", isinstance(templates, list), f"count={len(templates)}")
except Exception as e:
    log_test("模板列表", False, str(e))

# 7. 上传 PDF
print("\n--- 7. 上传 PDF ---")
upload_id = None
try:
    pdf_content = TEST_PDF.read_bytes()
    resp = api_post("/api/upload", files={
        "file": ("GB 5009.225-2016CN.pdf", pdf_content, "application/pdf")
    })
    data = resp.get("data", {})
    upload_id = data.get("upload_id")
    log_test("上传PDF", bool(upload_id), f"upload_id={upload_id}, size={data.get('file_size')}")
except Exception as e:
    log_test("上传PDF", False, str(e))

# 8. 创建排版任务
print("\n--- 8. 创建排版任务 ---")
task_id = None
if upload_id:
    try:
        resp = api_post("/api/tasks", data={
            "upload_id": upload_id,
            "standard": "GB 5009.225-2016CN",
            "use_rag": True,
            "llm_model": "qwen-plus",
        })
        data = resp.get("data", {})
        task_id = data.get("id")
        log_test("创建任务", bool(task_id), f"task_id={task_id}, status={data.get('status')}")
    except Exception as e:
        log_test("创建任务", False, str(e))

# 9. 监控任务进度
print("\n--- 9. 监控任务进度 ---")
if task_id:
    max_wait = 600  # 10 分钟
    waited = 0
    last_status = ""
    while waited < max_wait:
        try:
            resp = api_get(f"/api/tasks/{task_id}/status")
            data = resp.get("data", {})
            status = data.get("status", "unknown")
            progress = data.get("progress", 0)
            step = data.get("current_step", "")

            if status != last_status:
                print(f"  [{waited}s] status={status}, progress={progress}%, step={step}")
                last_status = status

            if status in ("completed", "failed", "cancelled"):
                break
            time.sleep(5)
            waited += 5
        except Exception as e:
            print(f"  [ERROR] {e}")
            time.sleep(5)
            waited += 5

    final_resp = api_get(f"/api/tasks/{task_id}") if task_id else {}
    final_data = final_resp.get("data", {})
    log_test(
        "任务完成",
        final_data.get("status") == "completed",
        f"status={final_data.get('status')}, error={final_data.get('error_message', 'None')}"
    )

    # 如果失败，记录详细错误
    if final_data.get("status") == "failed":
        log_test("失败原因", False, f"error_message={final_data.get('error_message')}")

# 10. 预览结果
print("\n--- 10. 预览结果 ---")
if task_id:
    try:
        resp = api_get(f"/api/tasks/{task_id}/preview")
        data = resp.get("data", {})
        md_preview = data.get("markdown_preview", "")
        style_cfg = data.get("style_config", {})
        log_test("预览结果", len(md_preview) > 0, f"md_len={len(md_preview)}, has_style={bool(style_cfg)}")
    except Exception as e:
        log_test("预览结果", False, str(e))

# 11. 下载结果
print("\n--- 11. 下载结果 ---")
if task_id:
    try:
        resp = api_get(f"/api/tasks/{task_id}/download")
        data = resp.get("data", {})
        log_test("下载信息", bool(data.get("download_url")), f"url={data.get('download_url')}")
    except Exception as e:
        log_test("下载结果", False, str(e))

# 12. 汇总结果
print("\n" + "=" * 60)
print("测试结果汇总")
print("=" * 60)
passed = sum(1 for r in test_results if r["passed"])
failed = sum(1 for r in test_results if not r["passed"])
print(f"通过: {passed}, 失败: {failed}, 总计: {len(test_results)}")
for r in test_results:
    if not r["passed"]:
        print(f"  [FAIL] {r['name']}: {r['detail']}")

print("\n测试完成。")

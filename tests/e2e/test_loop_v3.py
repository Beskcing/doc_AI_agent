"""Loop Engineering 第三轮验证测试

验证所有 Bug 修复 + 新增知识库 stats/search 路由
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://localhost:8000"
TASK_ID = "d1239779-a34f-4dd6-a5a3-0692a8973439"

test_results = []


def log_test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    msg = f"[{status}] {name}"
    if detail:
        msg += f": {detail}"
    print(msg)
    test_results.append({"name": name, "passed": passed, "detail": detail})


def api_get(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_post(path, data=None, files=None):
    url = f"{BASE_URL}{path}"
    if files:
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

    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def api_delete(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


print("=" * 60)
print("Loop Engineering 第三轮验证测试")
print("=" * 60)

# ──────────── 1. 健康检查 ────────────
print("\n--- 1. 健康检查 ---")
try:
    resp = api_get("/api/health")
    log_test("健康检查", resp["status"] == "ok")
except Exception as e:
    log_test("健康检查", False, str(e))

# ──────────── 2. 配置检查 ────────────
print("\n--- 2. 配置检查 ---")
try:
    resp = api_get("/api/config")
    cfg = resp.get("data", {})
    log_test("获取配置", bool(cfg), f"keys={list(cfg.keys())[:5]}")
except Exception as e:
    log_test("获取配置", False, str(e))

# ──────────── 3. 任务统计和列表 ────────────
print("\n--- 3. 任务统计和列表 ---")
try:
    resp = api_get("/api/tasks/stats")
    stats = resp.get("data", {}).get("stats", {})
    log_test("任务统计", "total" in str(stats), f"stats={stats}")
except Exception as e:
    log_test("任务统计", False, str(e))

try:
    resp = api_get("/api/tasks?page=1&page_size=5")
    data = resp.get("data", {})
    log_test("任务列表", "items" in data, f"total={data.get('total', 'N/A')}")
except Exception as e:
    log_test("任务列表", False, str(e))

# ──────────── 4. 知识库功能（新增 stats/search） ────────────
print("\n--- 4. 知识库功能 ---")
try:
    resp = api_get("/api/kb/documents")
    data = resp.get("data", {})
    docs = data.get("items", [])
    log_test("知识库文档列表", isinstance(docs, list), f"count={len(docs)}")
except Exception as e:
    log_test("知识库文档列表", False, str(e))

# 新增：知识库统计
try:
    resp = api_get("/api/kb/stats")
    stats = resp.get("data", {})
    log_test("知识库统计(新)", "total_docs" in stats, f"stats={stats}")
except Exception as e:
    log_test("知识库统计(新)", False, str(e))

# 新增：知识库检索
try:
    resp = api_post("/api/kb/search", data={
        "query": "国标文档排版规范 标题格式",
        "top_k": 3
    })
    data = resp.get("data", {})
    results = data.get("results", [])
    log_test("知识库检索(新)", isinstance(results, list), f"count={len(results)}")
except Exception as e:
    log_test("知识库检索(新)", False, str(e))

# ──────────── 5. 模板管理 ────────────
print("\n--- 5. 模板管理 ---")
try:
    resp = api_get("/api/templates")
    data = resp.get("data", {})
    templates = data.get("items", [])
    log_test("模板列表", isinstance(templates, list), f"count={len(templates)}")
except Exception as e:
    log_test("模板列表", False, str(e))

# ──────────── 6. 已完成任务详情 ────────────
print("\n--- 6. 已完成任务详情 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}")
    data = resp.get("data", {})
    log_test("任务详情", data.get("status") == "completed",
             f"status={data.get('status')}, result={data.get('result_path', 'None')[:50]}")
except Exception as e:
    log_test("任务详情", False, str(e))

# ──────────── 7. 下载功能 ────────────
print("\n--- 7. 下载功能 ---")
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/download/file"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
        log_test("下载文件", len(content) > 1000, f"size={len(content)} bytes")
except Exception as e:
    log_test("下载文件", False, str(e))

# MinerU DOCX 下载
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/download/mineru-docx"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
        log_test("MinerU DOCX下载", len(content) > 1000, f"size={len(content)} bytes")
except Exception as e:
    log_test("MinerU DOCX下载", False, str(e))

# ──────────── 8. 预览功能 ────────────
print("\n--- 8. 预览功能 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/preview")
    data = resp.get("data", {})
    md = data.get("markdown_preview", "")
    sc = data.get("style_config", {})
    log_test("Markdown预览", len(md) > 100, f"md_len={len(md)}")
    log_test("样式配置预览", bool(sc), f"keys={list(sc.keys())[:5] if sc else []}")
except Exception as e:
    log_test("预览功能", False, str(e))

# DOCX HTML 预览
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/preview/docx"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode()
        log_test("DOCX HTML预览", len(html) > 1000, f"html_len={len(html)}")
except Exception as e:
    log_test("DOCX HTML预览", False, str(e))

# ──────────── 9. 对话功能（修正调用方式） ────────────
print("\n--- 9. 对话功能 ---")
session_id = None
try:
    # 创建会话
    resp = api_post("/api/chat/sessions", data={
        "title": "验证测试对话"
    })
    data = resp.get("data", {})
    session_id = data.get("id")
    log_test("创建对话会话", bool(session_id), f"session_id={session_id}")
except Exception as e:
    log_test("创建对话会话", False, str(e))

if session_id:
    try:
        # 正确调用方式：POST /api/chat/style
        resp = api_post("/api/chat/style", data={
            "message": "请将正文字体改为宋体，字号改为14磅",
            "current_style_config": {
                "page_layout": {"paper_size": "A4", "margin_top_cm": 3.7},
                "body_style": {
                    "font": {"family": "仿宋_GB2312", "size_pt": 16},
                    "line_spacing": 1.5,
                    "first_line_indent_chars": 2,
                    "alignment": "justify"
                }
            },
            "session_id": session_id
        })
        data = resp.get("data", {})
        reply = data.get("reply", "")
        updated = data.get("updated_style_config", {})
        log_test("对话修改样式", bool(reply), f"reply_len={len(reply)}, has_config={bool(updated)}")
    except Exception as e:
        log_test("对话修改样式", False, str(e))

    # 获取会话消息
    try:
        resp = api_get(f"/api/chat/sessions/{session_id}/messages")
        data = resp.get("data", {})
        items = data.get("items", [])
        log_test("获取对话历史", isinstance(items, list), f"count={len(items)}")
    except Exception as e:
        log_test("获取对话历史", False, str(e))

# 会话列表
try:
    resp = api_get("/api/chat/sessions")
    data = resp.get("data", {})
    items = data.get("items", [])
    log_test("会话列表", isinstance(items, list), f"count={len(items)}")
except Exception as e:
    log_test("会话列表", False, str(e))

# ──────────── 10. 样式调整历史 ────────────
print("\n--- 10. 样式调整历史 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/style-history")
    data = resp.get("data", {})
    items = data.get("items", [])
    log_test("样式历史", isinstance(items, list), f"count={data.get('total', 0)}")
except Exception as e:
    log_test("样式历史", False, str(e))

# ──────────── 11. 重新应用模板 ────────────
print("\n--- 11. 重新应用模板 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}")
    task_detail = resp.get("data", {})
    current_style = task_detail.get("style_config_preview", {})

    if current_style:
        resp = api_post(f"/api/tasks/{TASK_ID}/apply-template", data={
            "style_config": current_style,
            "source": "verify_reapply"
        })
        data = resp.get("data", {})
        log_test("重新应用模板", bool(data.get("result_path")), f"result={data.get('result_path', 'None')[:50]}")
    else:
        log_test("重新应用模板", False, "no style_config")
except Exception as e:
    log_test("重新应用模板", False, str(e))

# ──────────── 12. 任务管理（取消/重试/删除） ────────────
print("\n--- 12. 任务管理 ---")
cancel_task_id = None
try:
    pdf_path = Path("d:/doc_ai_agent/GB 5009.225-2016CN.pdf")
    pdf_content = pdf_path.read_bytes()
    resp = api_post("/api/upload", files={
        "file": ("GB 5009.225-2016CN.pdf", pdf_content, "application/pdf")
    })
    upload_id = resp.get("data", {}).get("upload_id")

    resp = api_post("/api/tasks", data={
        "upload_id": upload_id,
        "standard": "GB 5009.225-2016CN",
        "use_rag": True,
    })
    cancel_task_id = resp.get("data", {}).get("id")
    log_test("创建取消测试任务", bool(cancel_task_id), f"task_id={cancel_task_id}")

    # 等待几秒后取消
    time.sleep(5)
    resp = api_post(f"/api/tasks/{cancel_task_id}/cancel")
    data = resp.get("data", {})
    log_test("取消任务", data.get("cancelled") == True, f"resp={data}")
except Exception as e:
    log_test("取消任务", False, str(e))

# 重试
if cancel_task_id:
    try:
        resp = api_post(f"/api/tasks/{cancel_task_id}/retry")
        data = resp.get("data", {})
        log_test("重试任务", data.get("status") == "pending", f"status={data.get('status')}")
    except Exception as e:
        log_test("重试任务", False, str(e))

    # 等一下再取消然后删除
    time.sleep(3)
    try:
        api_post(f"/api/tasks/{cancel_task_id}/cancel")
        time.sleep(2)
    except:
        pass
    try:
        resp = api_delete(f"/api/tasks/{cancel_task_id}")
        data = resp.get("data", {})
        log_test("删除任务", data.get("deleted") == True, f"resp={data}")
    except Exception as e:
        log_test("删除任务", False, str(e))

# ──────────── 汇总 ────────────
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

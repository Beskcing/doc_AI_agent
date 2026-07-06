"""Loop Engineering 第二轮全面功能测试

测试：下载/预览/模板管理/对话排版/知识库/样式调整/取消重试删除
"""

import json
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = "http://localhost:8000"
TASK_ID = "d1239779-a34f-4dd6-a5a3-0692a8973439"  # 已完成任务

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


def api_post(path, data=None, files=None, raw=False):
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
        if raw:
            return resp.read()
        return json.loads(resp.read().decode())


def api_delete(path):
    url = f"{BASE_URL}{path}"
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_put(path, data=None):
    url = f"{BASE_URL}{path}"
    body = json.dumps(data or {}).encode()
    req = urllib.request.Request(url, data=body, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


print("=" * 60)
print("Loop Engineering 第二轮全面功能测试")
print("=" * 60)

# ──────────── 1. 下载功能 ────────────
print("\n--- 1. 下载功能 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/download")
    data = resp.get("data", {})
    log_test("下载信息", bool(data.get("download_url")), f"url={data.get('download_url')}")
except Exception as e:
    log_test("下载信息", False, str(e))

# 实际下载文件
try:
    raw = api_post(f"/api/tasks/{TASK_ID}/download/file", raw=True)
    # 实际上 download/file 是 GET
    pass
except:
    pass

# 用 GET 下载文件
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/download/file"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
        log_test("下载文件", len(content) > 1000, f"size={len(content)} bytes")
except Exception as e:
    log_test("下载文件", False, str(e))

# ──────────── 2. 预览功能 ────────────
print("\n--- 2. 预览功能 ---")
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

# MinerU DOCX 预览
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/preview/mineru-docx"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        html = resp.read().decode()
        log_test("MinerU DOCX预览", len(html) > 1000, f"html_len={len(html)}")
except Exception as e:
    log_test("MinerU DOCX预览", False, str(e))

# MinerU DOCX 下载
try:
    url = f"{BASE_URL}/api/tasks/{TASK_ID}/download/mineru-docx"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=60) as resp:
        content = resp.read()
        log_test("MinerU DOCX下载", len(content) > 1000, f"size={len(content)} bytes")
except Exception as e:
    log_test("MinerU DOCX下载", False, str(e))

# ──────────── 3. 样式调整历史 ────────────
print("\n--- 3. 样式调整历史 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/style-history")
    data = resp.get("data", {})
    log_test("样式历史", isinstance(data.get("items"), list), f"count={data.get('total', 0)}")
except Exception as e:
    log_test("样式历史", False, str(e))

# ──────────── 4. 应用模板（重新渲染） ────────────
print("\n--- 4. 应用模板（重新渲染） ---")
try:
    # 使用当前任务的 style_config 重新应用
    resp = api_get(f"/api/tasks/{TASK_ID}")
    task_detail = resp.get("data", {})
    current_style = task_detail.get("style_config_preview", {})

    if current_style:
        resp = api_post(f"/api/tasks/{TASK_ID}/apply-template", data={
            "style_config": current_style,
            "source": "test_reapply"
        })
        data = resp.get("data", {})
        log_test("重新应用模板", bool(data.get("result_path")), f"result={data.get('result_path', 'None')}")
    else:
        log_test("重新应用模板", False, "no style_config available")
except Exception as e:
    log_test("重新应用模板", False, str(e))

# ──────────── 5. 保存样式到模板 ────────────
print("\n--- 5. 保存样式到模板 ---")
template_id = None
try:
    resp = api_get(f"/api/tasks/{TASK_ID}")
    task_detail = resp.get("data", {})
    current_style = task_detail.get("style_config_preview", {})

    if current_style:
        resp = api_post(f"/api/tasks/{TASK_ID}/save-style-to-template", data={
            "template_name": "测试模板_GB5009",
            "style_config": current_style,
            "description": "从测试任务保存的模板"
        })
        data = resp.get("data", {})
        template_id = data.get("template_id")
        log_test("保存样式到模板", bool(template_id), f"template_id={template_id}")
    else:
        log_test("保存样式到模板", False, "no style_config")
except Exception as e:
    log_test("保存样式到模板", False, str(e))

# ──────────── 6. 模板列表和详情 ────────────
print("\n--- 6. 模板列表和详情 ---")
try:
    resp = api_get("/api/templates")
    templates = resp.get("data", {}).get("templates", [])
    log_test("模板列表", isinstance(templates, list), f"count={len(templates)}")

    if template_id:
        resp = api_get(f"/api/templates/{template_id}")
        tpl_data = resp.get("data", {})
        log_test("模板详情", bool(tpl_data.get("id")), f"name={tpl_data.get('name', 'N/A')}")
except Exception as e:
    log_test("模板管理", False, str(e))

# ──────────── 7. 知识库功能 ────────────
print("\n--- 7. 知识库功能 ---")
try:
    resp = api_get("/api/kb/documents")
    docs = resp.get("data", {}).get("documents", [])
    log_test("知识库文档列表", isinstance(docs, list), f"count={len(docs)}")

    # 知识库统计
    resp = api_get("/api/kb/stats")
    stats = resp.get("data", {})
    log_test("知识库统计", isinstance(stats, dict), f"stats={stats}")
except Exception as e:
    log_test("知识库功能", False, str(e))

# 知识库检索
try:
    resp = api_post("/api/kb/search", data={
        "query": "国标文档排版规范 标题格式",
        "top_k": 3
    })
    results = resp.get("data", {}).get("results", [])
    log_test("知识库检索", isinstance(results, list), f"count={len(results)}")
except Exception as e:
    log_test("知识库检索", False, str(e))

# ──────────── 8. 对话功能 ────────────
print("\n--- 8. 对话功能 ---")
session_id = None
try:
    # 创建会话
    resp = api_post("/api/chat/sessions", data={
        "task_id": TASK_ID,
        "title": "测试对话"
    })
    data = resp.get("data", {})
    session_id = data.get("id") or data.get("session_id")
    log_test("创建对话会话", bool(session_id), f"session_id={session_id}")
except Exception as e:
    log_test("创建对话会话", False, str(e))

if session_id:
    try:
        # 发送消息
        resp = api_post(f"/api/chat/sessions/{session_id}/messages", data={
            "content": "请将正文字体改为宋体，字号改为14磅"
        })
        data = resp.get("data", {})
        log_test("发送对话消息", bool(data.get("response") or data.get("reply") or data.get("content")),
                 f"response_len={len(str(data.get('response', '')))}")
    except Exception as e:
        log_test("发送对话消息", False, str(e))

    # 获取会话消息列表
    try:
        resp = api_get(f"/api/chat/sessions/{session_id}/messages")
        data = resp.get("data", {})
        messages = data.get("messages", [])
        log_test("获取对话历史", isinstance(messages, list), f"count={len(messages)}")
    except Exception as e:
        log_test("获取对话历史", False, str(e))

# 会话列表
try:
    resp = api_get("/api/chat/sessions")
    sessions = resp.get("data", {}).get("sessions", [])
    log_test("会话列表", isinstance(sessions, list), f"count={len(sessions)}")
except Exception as e:
    log_test("会话列表", False, str(e))

# ──────────── 9. 配置功能 ────────────
print("\n--- 9. 配置功能 ---")
try:
    resp = api_get("/api/config")
    cfg = resp.get("data", {})
    log_test("获取配置", bool(cfg), f"keys={list(cfg.keys())[:5]}")
except Exception as e:
    log_test("获取配置", False, str(e))

try:
    resp = api_get("/api/config/supported-standards")
    standards = resp.get("data", [])
    log_test("支持规范列表", isinstance(standards, list), f"count={len(standards)}")
except Exception as e:
    log_test("支持规范列表", False, str(e))

try:
    resp = api_get("/api/config/llm-models")
    models = resp.get("data", [])
    log_test("LLM模型列表", isinstance(models, list), f"count={len(models)}")
except Exception as e:
    log_test("LLM模型列表", False, str(e))

# ──────────── 10. 任务管理（取消/重试/删除） ────────────
print("\n--- 10. 任务管理 ---")
# 创建一个新任务用于取消测试
cancel_task_id = None
try:
    # 重新上传 PDF
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
    time.sleep(3)
    resp = api_post(f"/api/tasks/{cancel_task_id}/cancel")
    data = resp.get("data", {})
    log_test("取消任务", data.get("cancelled") == True, f"resp={data}")
except Exception as e:
    log_test("取消任务", False, str(e))

# 重试取消的任务
if cancel_task_id:
    try:
        resp = api_post(f"/api/tasks/{cancel_task_id}/retry")
        data = resp.get("data", {})
        log_test("重试任务", data.get("status") == "pending", f"status={data.get('status')}")
    except Exception as e:
        log_test("重试任务", False, str(e))

# 删除任务
if cancel_task_id:
    try:
        # 先取消（如果正在处理）
        try:
            api_post(f"/api/tasks/{cancel_task_id}/cancel")
            time.sleep(2)
        except:
            pass
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

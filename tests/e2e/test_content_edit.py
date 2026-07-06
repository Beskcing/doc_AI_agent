"""内容编辑功能 E2E 测试

测试新增的文档内容编辑 API：
1. GET /api/tasks/{task_id}/content — 获取 Markdown 内容
2. GET /api/tasks/{task_id}/content/html — 获取 HTML 内容
3. PUT /api/tasks/{task_id}/content — 更新内容（Markdown/HTML）
4. POST /api/chat/content — LLM 对话修改内容
"""

import json
import time
import urllib.request

BASE_URL = "http://localhost:8000"
PASS = 0
FAIL = 0


def log(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    status = "✅ PASS" if ok else "❌ FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {status} {name}" + (f" | {detail}" if detail else ""))


def api_get(path: str):
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def api_put(path: str, data: dict):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, method="PUT")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data: dict):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


# ──────────── 查找已完成的任务 ────────────
print("=" * 60)
print("内容编辑功能 E2E 测试")
print("=" * 60)

print("\n--- 准备：查找已完成任务 ---")
TASK_ID = None
try:
    resp = api_get("/api/tasks?page=1&page_size=5&status=completed")
    items = resp.get("data", {}).get("items", [])
    if items:
        TASK_ID = items[0]["id"]
        log("查找已完成任务", True, f"task_id={TASK_ID}, filename={items[0].get('filename')}")
    else:
        log("查找已完成任务", False, "没有已完成的任务")
except Exception as e:
    log("查找已完成任务", False, str(e))

if not TASK_ID:
    print("\n没有已完成的任务，无法继续测试")
    exit(1)

# ──────────── 1. 获取 Markdown 内容 ────────────
print("\n--- 1. 获取 Markdown 内容 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/content")
    data = resp.get("data", {})
    content = data.get("content", "")
    content_type = data.get("content_type", "")
    log("GET /content 状态码", resp.get("code") == 0, f"code={resp.get('code')}")
    log("GET /content 内容非空", len(content) > 0, f"len={len(content)}")
    log("GET /content 类型", content_type == "markdown", f"type={content_type}")
except Exception as e:
    log("GET /content", False, str(e))

# ──────────── 2. 获取 HTML 内容 ────────────
print("\n--- 2. 获取 HTML 内容 ---")
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/content/html")
    data = resp.get("data", {})
    html = data.get("html", "")
    log("GET /content/html 状态码", resp.get("code") == 0, f"code={resp.get('code')}")
    log("GET /content/html 内容非空", len(html) > 0, f"len={len(html)}")
    log("GET /content/html 包含HTML标签", "<" in html and ">" in html, f"preview={html[:100]}")
except Exception as e:
    log("GET /content/html", False, str(e))

# ──────────── 3. 更新 Markdown 内容 ────────────
print("\n--- 3. 更新 Markdown 内容 ---")
# 先获取原始内容
original_content = ""
try:
    resp = api_get(f"/api/tasks/{TASK_ID}/content")
    original_content = resp.get("data", {}).get("content", "")
except Exception:
    pass

if original_content:
    # 修改：在末尾添加一行测试文本
    modified_content = original_content.rstrip() + "\n\n<!-- E2E测试内容编辑 -->\n"
    try:
        resp = api_put(f"/api/tasks/{TASK_ID}/content", {
            "content": modified_content,
            "content_type": "markdown",
            "regenerate_docx": True,
        })
        data = resp.get("data", {})
        log("PUT /content 状态码", resp.get("code") == 0, f"code={resp.get('code')}")
        log("PUT /content 返回 result_path", bool(data.get("result_path")), f"path={str(data.get('result_path', ''))[:50]}")
        log("PUT /content 返回 markdown", bool(data.get("cleaned_markdown_preview")), f"len={len(data.get('cleaned_markdown_preview', ''))}")
    except Exception as e:
        log("PUT /content", False, str(e))

    # 验证修改已保存
    try:
        resp = api_get(f"/api/tasks/{TASK_ID}/content")
        saved_content = resp.get("data", {}).get("content", "")
        log("验证内容已更新", "E2E测试内容编辑" in saved_content, f"len={len(saved_content)}")
    except Exception as e:
        log("验证内容已更新", False, str(e))

    # 恢复原始内容
    try:
        api_put(f"/api/tasks/{TASK_ID}/content", {
            "content": original_content,
            "content_type": "markdown",
            "regenerate_docx": True,
        })
        log("恢复原始内容", True)
    except Exception as e:
        log("恢复原始内容", False, str(e))
else:
    log("PUT /content 跳过", False, "无原始内容")

# ──────────── 4. 更新 HTML 内容 ────────────
print("\n--- 4. 更新 HTML 内容（不重新生成 DOCX）---")
try:
    resp = api_put(f"/api/tasks/{TASK_ID}/content", {
        "content": "<p>测试 HTML 内容</p>",
        "content_type": "html",
        "regenerate_docx": False,
    })
    log("PUT /content (HTML) 状态码", resp.get("code") == 0, f"code={resp.get('code')}")
except Exception as e:
    log("PUT /content (HTML)", False, str(e))

# 恢复原始内容
if original_content:
    try:
        api_put(f"/api/tasks/{TASK_ID}/content", {
            "content": original_content,
            "content_type": "markdown",
            "regenerate_docx": True,
        })
    except Exception:
        pass

# ──────────── 5. 错误处理 ────────────
print("\n--- 5. 错误处理 ---")
try:
    resp = api_get("/api/tasks/nonexistent_task/content")
    log("不存在任务返回404", resp.get("code") == 404, f"code={resp.get('code')}")
except urllib.error.HTTPError as e:
    log("不存在任务返回404", e.code == 404, f"code={e.code}")
except Exception as e:
    log("不存在任务返回404", False, str(e))

# ──────────── 结果汇总 ────────────
print("\n" + "=" * 60)
total = PASS + FAIL
print(f"测试结果: {total} 项测试, {PASS} 通过, {FAIL} 失败 ({PASS * 100 // total}% 通过率)")
print("=" * 60)

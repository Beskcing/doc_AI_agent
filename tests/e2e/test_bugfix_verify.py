"""修复验证测试 — 验证所有 Bug 修复"""
import urllib.request
import json
import time
from pathlib import Path

BASE = "http://localhost:8000"
results = []

def log(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def api_post(path, data=None):
    if data is None:
        data = {}
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def api_put(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                 headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def upload_file(file_path):
    boundary = "----TestBoundary12345"
    file_data = Path(file_path).read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{Path(file_path).name}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/api/upload", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

print("=" * 60)
print("Bug 修复验证测试")
print("=" * 60)

# ─── 1. 上传 MD 文件并创建任务 ───
print("\n─── 1. 上传 MD + 创建任务 ───")
test_md = Path("tests/fixtures/sample_doc.md")
if not test_md.exists():
    test_md.write_text("# 测试文档\n\n## 1 范围\n\n本标准规定了文档排版要求。\n", encoding="utf-8")

result = upload_file(test_md)
log("MD上传", result["code"] == 0)
upload_id = result["data"]["upload_id"]

result = api_post("/api/tasks", {
    "upload_id": upload_id,
    "standard": "GB/T 9704",
    "use_rag": True,
    "llm_model": "qwen-plus",
})
log("创建任务", result["code"] == 0)
task_id = result["data"]["id"]

# Bug#2: file_size_mb 应该有值
log("Bug#2: file_size_mb 已设置", result["data"].get("file_size_mb") is not None,
    f"size={result['data'].get('file_size_mb')}MB")

# ─── 2. 等待任务完成 ───
print("\n─── 2. 等待任务完成 ───")
for i in range(20):
    result = api_get(f"/api/tasks/{task_id}/status")
    status = result["data"]["status"]
    progress = result["data"]["progress"]
    if status in ("completed", "failed"):
        break
    time.sleep(1)

log("任务完成", status == "completed", f"status={status}, progress={progress}")

# ─── 3. 验证 Bug 修复 ───
print("\n─── 3. 验证 Bug 修复 ───")
detail = api_get(f"/api/tasks/{task_id}")["data"]

# Bug#1: completed_at
log("Bug#1: completed_at 已设置", detail.get("completed_at") is not None,
    f"completed_at={detail.get('completed_at')}")

# Bug#3: result_path
log("Bug#3: result_path 已设置", detail.get("result_path") is not None,
    f"result_path={detail.get('result_path')}")

# Bug#4: style_config_preview
log("Bug#4: style_config_preview 已设置", detail.get("style_config_preview") is not None)
style_cfg = detail.get("style_config_preview", {})
if style_cfg:
    log("  style_config 含 page_layout", "page_layout" in style_cfg)
    log("  style_config 含 body_style", "body_style" in style_cfg)
    log("  style_config 含 rag_sources", "rag_sources" in style_cfg)

# Bug#5: 下载文件 (HTTP状态码)
print("\n─── 4. 验证下载 ───")
try:
    req = urllib.request.Request(f"{BASE}/api/tasks/{task_id}/download/file")
    with urllib.request.urlopen(req, timeout=10) as resp:
        content = resp.read()
        log("Bug#5: 下载成功", len(content) > 0, f"size={len(content)} bytes")
except urllib.error.HTTPError as e:
    log("Bug#5: 下载返回正确HTTP状态", e.code in (404, 400), f"HTTP {e.code}")

# 下载不存在任务的文件
try:
    req = urllib.request.Request(f"{BASE}/api/tasks/nonexistent/download/file")
    urllib.request.urlopen(req, timeout=5)
    log("Bug#5: 不存在任务下载", False, "应该返回HTTP 404")
except urllib.error.HTTPError as e:
    log("Bug#5: 不存在任务返回HTTP 404", e.code == 404, f"HTTP {e.code}")

# ─── 5. 预览 ───
print("\n─── 5. 验证预览 ───")
preview = api_get(f"/api/tasks/{task_id}/preview")["data"]
log("预览有 markdown 内容", preview.get("markdown_preview") is not None,
    f"len={len(preview.get('markdown_preview') or '')}")
log("预览有 style_config", preview.get("style_config") is not None)

# ─── 6. 配置更新 (Bug#7) ───
print("\n─── 6. 验证配置更新 ───")
result = api_put("/api/config", {"output_dir": "data/output", "rag_top_k": 10})
log("Bug#7: 配置含 output_dir", result["data"].get("output_dir") == "data/output")
log("配置含 rag_top_k", result["data"].get("rag_top_k") == 10)

# ─── 7. 重试测试 ───
print("\n─── 7. 验证重试 ───")
# 创建一个会失败的任务
result = api_post("/api/tasks", {
    "upload_id": "nonexistent-upload-id",
    "standard": "GB/T 9704",
    "use_rag": False,
    "llm_model": "qwen-plus",
})
failed_task_id = result["data"]["id"]
time.sleep(3)  # 等待失败
status = api_get(f"/api/tasks/{failed_task_id}/status")["data"]
log("无效任务应失败", status["status"] == "failed", f"status={status['status']}")

if status["status"] == "failed":
    # 重试
    result = api_post(f"/api/tasks/{failed_task_id}/retry")
    log("重试任务", result["code"] == 0, f"status={result['data'].get('status')}")

    # 检查 completed_at 被清除
    detail = api_get(f"/api/tasks/{failed_task_id}")["data"]
    log("重试后 completed_at 已清除", detail.get("completed_at") is None)

# ─── 汇总 ───
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed
print(f"结果: {passed}/{total} 通过, {failed} 失败")
if failed:
    for r in results:
        if not r["passed"]:
            print(f"  FAIL: {r['name']}")
print("=" * 60)

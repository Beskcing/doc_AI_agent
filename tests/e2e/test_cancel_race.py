"""取消任务竞态条件验证测试

验证 Bug#1 修复：取消任务后，后台线程异常不再覆盖 cancelled 状态。
"""
import urllib.request
import json
import time
from pathlib import Path

BASE = "http://localhost:8000"

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

def upload_file(file_path):
    boundary = "----CancelTest12345"
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
print("取消任务竞态条件验证测试")
print("=" * 60)

# 1. 上传文件
test_md = Path("data/test_cancel.md")
test_md.write_text("# 测试取消\n\n这是一段测试内容用于验证取消功能。", encoding="utf-8")

result = upload_file(str(test_md))
upload_id = result["data"]["upload_id"]
print(f"[1] 上传成功: upload_id={upload_id[:8]}...")

# 2. 创建任务
result = api_post("/api/tasks", {
    "upload_id": upload_id,
    "standard": "GB/T 9704",
    "use_rag": True,
    "llm_model": "qwen-plus",
})
task_id = result["data"]["id"]
print(f"[2] 创建任务: task_id={task_id[:8]}..., status={result['data']['status']}")

# 3. 立即取消
result = api_post(f"/api/tasks/{task_id}/cancel")
print(f"[3] 取消任务: code={result['code']}, cancelled={result['data'].get('cancelled')}")

# 4. 等待几秒，让后台线程处理
print("[4] 等待 5 秒，让后台线程处理...")
time.sleep(5)

# 5. 检查状态是否仍为 cancelled（而非 failed）
result = api_get(f"/api/tasks/{task_id}")
status = result["data"]["status"]
error = result["data"].get("error_message")
print(f"[5] 最终状态: status={status}, error={error}")

if status == "cancelled":
    print("\n[PASS] 取消任务状态保持为 cancelled，竞态条件已修复！")
else:
    print(f"\n[FAIL] 取消任务状态被覆盖为 {status}，竞态条件仍存在！")
    if error:
        print(f"  错误信息: {error}")

# 清理
test_md.unlink(missing_ok=True)
print("\n=== 测试完成 ===")

"""PDF 上传测试 — 使用真实 GB 5009.225-2016CN.pdf"""
import urllib.request
import json
import time
from pathlib import Path

BASE = "http://localhost:8000"
PDF = Path("GB 5009.225-2016CN.pdf")

# 上传 PDF
boundary = "----PdfBoundary12345"
file_data = PDF.read_bytes()
body = (
    f"--{boundary}\r\n"
    f'Content-Disposition: form-data; name="file"; filename="{PDF.name}"\r\n'
    f"Content-Type: application/pdf\r\n\r\n"
).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
req = urllib.request.Request(
    f"{BASE}/api/upload", data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
with urllib.request.urlopen(req, timeout=60) as resp:
    result = json.loads(resp.read().decode())
    upload_id = result["data"]["upload_id"]
    file_size = result["data"]["file_size"]
    print(f"PDF上传成功: upload_id={upload_id[:8]}..., size={file_size/1024/1024:.2f}MB")

# 创建任务
data = json.dumps({
    "upload_id": upload_id,
    "standard": "GB/T 9704",
    "use_rag": True,
    "llm_model": "qwen-plus",
}).encode()
req = urllib.request.Request(f"{BASE}/api/tasks", data=data,
                             headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=10) as resp:
    result = json.loads(resp.read().decode())
    task_id = result["data"]["id"]
    file_size_mb = result["data"].get("file_size_mb")
    print(f"任务创建: task_id={task_id[:8]}..., file_size_mb={file_size_mb}")

# 轮询状态（最多120秒）
for i in range(40):
    r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}/status", timeout=5)
    d = json.loads(r.read().decode())["data"]
    status = d["status"]
    progress = d["progress"]
    step = d.get("current_step", "")
    print(f"  [{i*3}s] status={status} progress={progress} step={step}")
    if status in ("completed", "failed"):
        break
    time.sleep(3)

if status == "failed":
    r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}", timeout=5)
    d = json.loads(r.read().decode())["data"]
    print(f"失败原因: {d.get('error_message')}")
elif status == "completed":
    r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}", timeout=5)
    d = json.loads(r.read().decode())["data"]
    print(f"完成! completed_at={d.get('completed_at')}")
    print(f"  result_path={d.get('result_path')}")
    print(f"  markdown_preview_len={len(d.get('cleaned_markdown_preview') or '')}")
    print(f"  style_config={d.get('style_config_preview') is not None}")
else:
    print(f"仍在处理中: status={status} (MinerU API 解析耗时较长)")
    print("可以稍后在 /tasks 页面查看结果")

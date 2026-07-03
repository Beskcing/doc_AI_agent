"""快速检查任务状态"""
import urllib.request
import json

BASE = "http://localhost:8000"

# 检查所有任务
r = urllib.request.urlopen(f"{BASE}/api/tasks?page=1&page_size=10", timeout=5)
data = json.loads(r.read().decode())
for item in data["data"]["items"]:
    print(f"  id={item['id'][:8]}... status={item['status']} progress={item['progress']} "
          f"step={item.get('current_step','')} completed_at={item.get('completed_at')} "
          f"file_size_mb={item.get('file_size_mb')}")

# 检查第一个 processing 任务的详情
for item in data["data"]["items"]:
    if item["status"] == "processing":
        r2 = urllib.request.urlopen(f"{BASE}/api/tasks/{item['id']}", timeout=5)
        d2 = json.loads(r2.read().decode())["data"]
        print(f"\n  详情: result_path={d2.get('result_path')} "
              f"markdown_preview_len={len(d2.get('cleaned_markdown_preview') or '')} "
              f"error={d2.get('error_message')}")
        break

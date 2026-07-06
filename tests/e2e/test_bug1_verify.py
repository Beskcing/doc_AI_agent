"""快速验证 Bug#1 修复：对话内容编辑大文档 JSON 截断"""
import requests
import sys

BASE = "http://localhost:8000"

# 找一个已完成的任务
r = requests.get(f"{BASE}/api/tasks", params={"page": 1, "page_size": 5})
d = r.json()
tasks = d["data"]["items"]
completed = [t for t in tasks if t["status"] == "completed"]
if not completed:
    print("No completed task found")
    sys.exit(1)

task_id = completed[0]["id"]
print(f"Testing with task: {task_id}")

# 测试对话内容编辑
r2 = requests.post(f"{BASE}/api/chat/content", json={
    "message": "在文档末尾添加一行：本文档由 Loop Engineering 自动化测试验证修复。",
    "task_id": task_id,
}, timeout=120)
d2 = r2.json()
print(f"code: {d2['code']}")
if d2["code"] == 0:
    print(f"reply: {d2['data'].get('reply', '')}")
    print("SUCCESS!")
else:
    print(f"FAILED: {d2.get('message', '')}")

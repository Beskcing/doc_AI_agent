"""检查已完成任务的详细字段"""
import urllib.request
import json

BASE = "http://localhost:8000"

r = urllib.request.urlopen(f"{BASE}/api/tasks?page=1&page_size=10", timeout=5)
data = json.loads(r.read().decode())

for item in data["data"]["items"]:
    if item["status"] == "completed":
        r2 = urllib.request.urlopen(f"{BASE}/api/tasks/{item['id']}", timeout=5)
        d2 = json.loads(r2.read().decode())["data"]
        print(f"id={d2['id'][:8]}...")
        print(f"  current_step={d2.get('current_step')}")
        print(f"  completed_at={d2.get('completed_at')}")
        print(f"  result_path={d2.get('result_path')}")
        print(f"  markdown_preview_len={len(d2.get('cleaned_markdown_preview') or '')}")
        print(f"  style_config={d2.get('style_config_preview')}")
        print(f"  file_size_mb={d2.get('file_size_mb')}")
        
        # 测试下载
        try:
            r3 = urllib.request.urlopen(f"{BASE}/api/tasks/{d2['id']}/download", timeout=5)
            d3 = json.loads(r3.read().decode())
            print(f"  download: code={d3['code']} msg={d3.get('message')}")
        except Exception as e:
            print(f"  download ERROR: {e}")
        break

# 测试预览
print("\n--- 预览测试 ---")
for item in data["data"]["items"]:
    if item["status"] == "completed":
        try:
            r4 = urllib.request.urlopen(f"{BASE}/api/tasks/{item['id']}/preview", timeout=5)
            d4 = json.loads(r4.read().decode())
            print(f"  preview code={d4['code']}")
            print(f"  markdown_preview_len={len(d4['data'].get('markdown_preview') or '')}")
            print(f"  style_config={d4['data'].get('style_config')}")
        except Exception as e:
            print(f"  preview ERROR: {e}")
        break

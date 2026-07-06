"""监控任务进度"""
import urllib.request
import json
import time

task_id = "d1239779-a34f-4dd6-a5a3-0692a8973439"
last_status = ""
waited = 0

while waited < 600:
    req = urllib.request.Request(f"http://localhost:8000/api/tasks/{task_id}/status")
    resp = urllib.request.urlopen(req, timeout=30)
    data = json.loads(resp.read().decode())["data"]
    status = data.get("status", "unknown")
    progress = data.get("progress", 0)
    step = data.get("current_step", "")
    if status != last_status:
        print(f"[{waited}s] status={status}, progress={progress}%, step={step}")
        last_status = status
    if status in ("completed", "failed", "cancelled"):
        break
    time.sleep(5)
    waited += 5

# 获取最终详情
req = urllib.request.Request(f"http://localhost:8000/api/tasks/{task_id}")
resp = urllib.request.urlopen(req, timeout=30)
detail = json.loads(resp.read().decode())["data"]
print(f"Final: status={detail['status']}, error={detail.get('error_message', 'None')}")
print(f"result_path={detail.get('result_path', 'None')}")
if detail.get("style_config_preview"):
    sc = detail["style_config_preview"]
    print(f"style_config keys: {list(sc.keys())[:10]}")

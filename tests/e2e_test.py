"""端到端流程测试: 上传 -> 创建任务 -> 等待处理 -> 预览 -> 下载"""

import json
import os
import time
import urllib.request

BASE = "http://localhost:8001"
UPLOAD_DIR = "data/uploads"
OUTPUT_DIR = "data/output"


def e2e_test():
    print("=" * 60)
    print("端到端流程测试")
    print("=" * 60)

    # Step 1: Upload a test file
    print("\n[Step 1] 上传测试文件...")
    test_content = "# 测试文档\n\n## 第1章 概述\n\n这是一段测试正文内容，用于验证文档排版流程。\n\n## 第2章 技术要求\n\n### 2.1 基本要求\n\n产品应符合以下基本要求。\n\n### 2.2 性能指标\n\n性能指标如下表所示。"
    test_path = "data/test_e2e.md"
    os.makedirs("data", exist_ok=True)
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(test_content)

    # Upload via multipart
    boundary = "----TestBoundary"
    import io

    body = io.BytesIO()
    body.write(f"--{boundary}\r\n".encode())
    body.write(b'Content-Disposition: form-data; name="file"; filename="test_e2e.md"\r\n')
    body.write(b"Content-Type: text/markdown\r\n\r\n")
    body.write(test_content.encode())
    body.write(f"\r\n--{boundary}--\r\n".encode())

    req = urllib.request.Request(f"{BASE}/api/upload", data=body.getvalue())
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    req.method = "POST"
    r = urllib.request.urlopen(req, timeout=30)
    upload_resp = json.loads(r.read())
    print(f"  上传结果: code={upload_resp.get('code')}")
    upload_data = upload_resp.get("data", {})
    upload_id = upload_data.get("upload_id") or upload_data.get("id")
    if not upload_id:
        print("  FAIL: 未获取到 upload_id")
        print(f"  Response: {json.dumps(upload_resp, ensure_ascii=False)[:500]}")
        return
    print(f"  upload_id: {upload_id}")

    # Step 2: Create task
    print("\n[Step 2] 创建排版任务...")
    task_data = json.dumps({"upload_id": upload_id, "standard": "custom", "use_rag": False}).encode()
    req = urllib.request.Request(
        f"{BASE}/api/tasks", data=task_data, headers={"Content-Type": "application/json"}, method="POST"
    )
    r = urllib.request.urlopen(req, timeout=30)
    task_resp = json.loads(r.read())
    print(f"  创建结果: code={task_resp.get('code')}")
    if task_resp.get("code") != 0:
        print(f"  FAIL: {task_resp.get('message')}")
        return
    task_id = task_resp["data"]["id"]
    print(f"  task_id: {task_id}")

    # Step 3: Wait for processing
    print("\n[Step 3] 等待任务处理...")
    max_wait = 120
    for i in range(max_wait // 2):
        time.sleep(2)
        r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}", timeout=30)
        task_info = json.loads(r.read())["data"]
        status = task_info["status"]
        progress = task_info.get("progress", 0)
        step = task_info.get("current_step", "")
        print(f"  [{i*2}s] status={status} progress={progress}% step={step}")
        if status in ("completed", "failed", "cancelled"):
            break
    else:
        print("  WARN: 任务超时未完成")

    if status == "failed":
        print(f"  FAIL: 任务失败 - {task_info.get('error_message', '')}")
        return
    if status != "completed":
        print(f"  WARN: 任务状态 = {status}")
        return

    # Step 4: Preview
    print("\n[Step 4] 获取预览...")
    r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}/preview", timeout=30)
    preview = json.loads(r.read())
    md_preview = preview.get("data", {}).get("markdown_preview", "")
    style_config = preview.get("data", {}).get("style_config", {})
    print(f"  Markdown预览: {len(md_preview)} 字符")
    print(f"  样式配置: {json.dumps(style_config, ensure_ascii=False)[:200]}")

    # Step 5: Download
    print("\n[Step 5] 下载排版结果...")
    r = urllib.request.urlopen(f"{BASE}/api/tasks/{task_id}/download", timeout=30)
    download_info = json.loads(r.read())
    print(f"  下载信息: code={download_info.get('code')}")
    dl_data = download_info.get("data", {})
    print(f"  结果路径: {dl_data.get('result_path', 'N/A')}")
    print(f"  文件名: {dl_data.get('filename', 'N/A')}")

    # Step 6: Verify result file exists
    print("\n[Step 6] 验证结果文件...")
    result_path = dl_data.get("result_path", "")
    if result_path and os.path.exists(result_path):
        size = os.path.getsize(result_path)
        print(f"  PASS: 结果文件存在, 大小={size} bytes")
    else:
        print(f"  WARN: 结果文件不存在: {result_path}")

    print("\n" + "=" * 60)
    print("端到端测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    e2e_test()

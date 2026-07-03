"""MinerU 线上 API 集成验证脚本

测试流程: 上传 MD 文件 → 创建任务 → 查询状态 → 验证 Markdown 预览
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8000"


def main():
    # 1. 上传 Markdown 文件
    print("=== 1. 上传文件 ===")
    boundary = "----TestBoundary1234"
    file_content = b"# Test Document\n\nThis is a test markdown file for MinerU integration.\n\n## Section 1\n\nContent here.\n"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="test_doc.md"\r\n'
        "Content-Type: text/markdown\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"  upload_id: {result['data']['upload_id']}")
        print(f"  filename: {result['data']['filename']}")
        upload_id = result["data"]["upload_id"]

    # 2. 创建任务
    print("\n=== 2. 创建任务 ===")
    data = json.dumps({
        "upload_id": upload_id,
        "standard": "GB/T 9704",
        "use_rag": True,
        "llm_model": "qwen-plus",
    }).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/tasks",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        print(f"  task_id: {result['data']['id']}")
        print(f"  filename: {result['data']['filename']}")
        print(f"  status: {result['data']['status']}")
        task_id = result["data"]["id"]

    # 3. 等待处理完成
    print("\n=== 3. 等待任务处理 ===")
    for i in range(15):
        time.sleep(1)
        req = urllib.request.Request(f"{BASE_URL}/api/tasks/{task_id}")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            status = result["data"]["status"]
            progress = result["data"]["progress"]
            step = result["data"]["current_step"]
            print(f"  [{i+1}s] status={status}, progress={progress}%, step={step}")
            if status in ("completed", "failed"):
                break

    # 4. 验证结果
    print("\n=== 4. 验证结果 ===")
    req = urllib.request.Request(f"{BASE_URL}/api/tasks/{task_id}/preview")
    with urllib.request.urlopen(req) as resp:
        result = json.loads(resp.read().decode())
        preview = result["data"].get("markdown_preview", "")
        print(f"  markdown_preview (前 200 字符): {preview[:200]}")
        print(f"  preview length: {len(preview)}")

    if status == "completed" and len(preview) > 0:
        print("\n=== 验证通过 ===")
    else:
        print(f"\n=== 验证失败: status={status}, preview_empty={len(preview)==0} ===")


if __name__ == "__main__":
    main()

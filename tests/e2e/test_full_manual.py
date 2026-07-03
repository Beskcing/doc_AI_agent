"""全面端到端测试脚本 — 模拟人工操作全流程

使用真实 PDF 文件 (GB 5009.225-2016CN.pdf) 测试所有 API 接口，
模拟用户从前端点击每个按钮的完整操作链路。

Loop Engineering: 测试 → 发现Bug → 修复 → 回归验证
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8000"
PDF_PATH = Path("GB 5009.225-2016CN.pdf")

# 测试结果记录
results: list[dict] = []
bug_list: list[dict] = []


def log_test(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    if not passed:
        bug_list.append({"name": name, "detail": detail})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def api_get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_post(path: str, data: dict | None = None, is_json: bool = True) -> dict:
    if data is None:
        data = {}
    if is_json:
        body = json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
    else:
        body = data
        headers = {}
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_put(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body, headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def api_delete(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())


def upload_file(file_path: Path) -> dict:
    """上传文件（multipart/form-data）"""
    boundary = "----TestBoundary12345"
    file_data = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/upload",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def upload_kb_doc(file_path: Path) -> dict:
    """上传知识库文档"""
    boundary = "----KbBoundary12345"
    file_data = file_path.read_bytes()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"\r\n'
        f"Content-Type: text/markdown\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/kb/documents",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def main():
    print("=" * 60)
    print("全面端到端测试 — 模拟人工操作全流程")
    print(f"测试文档: {PDF_PATH}")
    print(f"文件大小: {PDF_PATH.stat().st_size / 1024 / 1024:.2f} MB")
    print("=" * 60)

    # ════════════════════════════════════════════════════
    # 1. 健康检查
    # ════════════════════════════════════════════════════
    print("\n─── 1. 健康检查 ───")
    try:
        result = api_get("/api/health")
        log_test("健康检查", result["status"] == "ok", f"status={result.get('status')}")
    except Exception as e:
        log_test("健康检查", False, str(e))

    # ════════════════════════════════════════════════════
    # 2. Dashboard 统计接口
    # ════════════════════════════════════════════════════
    print("\n─── 2. Dashboard 统计接口 ───")
    try:
        result = api_get("/api/tasks/stats")
        data = result["data"]
        stats = data["stats"]
        log_test("统计接口返回", "total" in stats, f"total={stats.get('total')}")
        log_test("统计包含各状态", all(k in stats for k in ["pending", "processing", "completed", "failed", "cancelled"]))
        log_test("最近任务列表", "recent_tasks" in data, f"count={len(data.get('recent_tasks', []))}")
    except Exception as e:
        log_test("统计接口", False, str(e))

    # ════════════════════════════════════════════════════
    # 3. 配置接口
    # ════════════════════════════════════════════════════
    print("\n─── 3. 系统配置接口 ───")
    try:
        result = api_get("/api/config")
        cfg = result["data"]
        log_test("获取配置", "llm_provider" in cfg, f"provider={cfg.get('llm_provider')}")
        log_test("配置含 supported_formats", "supported_formats" in cfg, f"formats={cfg.get('supported_formats')}")
        log_test("配置含 output_dir", "output_dir" in cfg, f"output_dir={cfg.get('output_dir')}")
    except Exception as e:
        log_test("获取配置", False, str(e))

    try:
        result = api_get("/api/config/supported-standards")
        log_test("排版规范列表", len(result["data"]) >= 3, f"count={len(result['data'])}")
    except Exception as e:
        log_test("排版规范列表", False, str(e))

    try:
        result = api_get("/api/config/llm-models")
        log_test("LLM模型列表", len(result["data"]) >= 2, f"count={len(result['data'])}")
    except Exception as e:
        log_test("LLM模型列表", False, str(e))

    # 测试更新配置
    try:
        result = api_put("/api/config", {"rag_top_k": 8})
        log_test("更新配置", result["code"] == 0, f"top_k={result['data'].get('rag_top_k')}")
    except Exception as e:
        log_test("更新配置", False, str(e))

    # ════════════════════════════════════════════════════
    # 4. 知识库管理
    # ════════════════════════════════════════════════════
    print("\n─── 4. 知识库管理 ───")
    try:
        result = api_get("/api/kb/documents?page=1&page_size=10")
        log_test("知识库文档列表", result["code"] == 0, f"total={result['data'].get('total')}")
    except Exception as e:
        log_test("知识库文档列表", False, str(e))

    # 上传知识库文档
    kb_test_md = Path("knowledge_data/raw_docs/gbt_9704_2012.md")
    if kb_test_md.exists():
        try:
            result = upload_kb_doc(kb_test_md)
            log_test("上传知识库文档", result["code"] == 0, f"name={result['data'].get('name')}")
            kb_doc_id = result["data"].get("id")
        except Exception as e:
            log_test("上传知识库文档", False, str(e))
            kb_doc_id = None
    else:
        log_test("上传知识库文档", False, "测试文件不存在")
        kb_doc_id = None

    # 重建索引
    try:
        result = api_post("/api/kb/rebuild")
        log_test("重建知识库索引", result["code"] == 0)
    except Exception as e:
        log_test("重建知识库索引", False, str(e))

    # 删除知识库文档
    if kb_doc_id:
        try:
            result = api_delete(f"/api/kb/documents/{kb_doc_id}")
            log_test("删除知识库文档", result["code"] == 0)
        except Exception as e:
            log_test("删除知识库文档", False, str(e))

    # ════════════════════════════════════════════════════
    # 5. 文件上传 (真实PDF)
    # ════════════════════════════════════════════════════
    print("\n─── 5. 文件上传 (真实PDF) ───")
    upload_id = None
    if PDF_PATH.exists():
        try:
            result = upload_file(PDF_PATH)
            log_test("PDF上传成功", result["code"] == 0, f"upload_id={result['data'].get('upload_id', '')[:8]}...")
            upload_id = result["data"].get("upload_id")
            file_size = result["data"].get("file_size", 0)
            log_test("文件大小正确", file_size > 0, f"size={file_size / 1024 / 1024:.2f}MB")
        except Exception as e:
            log_test("PDF上传", False, str(e))
    else:
        log_test("PDF文件存在", False, f"路径不存在: {PDF_PATH}")

    # ════════════════════════════════════════════════════
    # 6. 创建任务
    # ════════════════════════════════════════════════════
    print("\n─── 6. 创建排版任务 ───")
    task_id = None
    if upload_id:
        try:
            result = api_post("/api/tasks", {
                "upload_id": upload_id,
                "standard": "GB/T 9704",
                "use_rag": True,
                "llm_model": "qwen-plus",
            })
            log_test("创建任务", result["code"] == 0, f"task_id={result['data'].get('id', '')[:8]}...")
            task_id = result["data"].get("id")
            log_test("任务初始状态", result["data"].get("status") == "pending", f"status={result['data'].get('status')}")
        except Exception as e:
            log_test("创建任务", False, str(e))
    else:
        log_test("创建任务", False, "缺少 upload_id")

    # ════════════════════════════════════════════════════
    # 7. 任务列表
    # ════════════════════════════════════════════════════
    print("\n─── 7. 任务列表 ───")
    try:
        result = api_get("/api/tasks?page=1&page_size=5")
        log_test("任务列表", result["code"] == 0, f"total={result['data'].get('total')}")
        items = result["data"].get("items", [])
        log_test("任务列表非空", len(items) > 0)
    except Exception as e:
        log_test("任务列表", False, str(e))

    # 状态筛选
    try:
        result = api_get("/api/tasks?page=1&page_size=5&status=completed")
        log_test("状态筛选", result["code"] == 0)
    except Exception as e:
        log_test("状态筛选", False, str(e))

    # ════════════════════════════════════════════════════
    # 8. 任务详情与状态轮询
    # ════════════════════════════════════════════════════
    print("\n─── 8. 任务详情与状态轮询 ───")
    if task_id:
        # 获取详情
        try:
            result = api_get(f"/api/tasks/{task_id}")
            log_test("任务详情", result["code"] == 0)
            detail = result["data"]
            log_test("详情含 markdown_preview", "cleaned_markdown_preview" in detail)
            log_test("详情含 current_step", "current_step" in detail)
            log_test("详情含 result_path", "result_path" in detail)
        except Exception as e:
            log_test("任务详情", False, str(e))

        # 轮询状态（最多等 120 秒）
        print("  轮询任务状态 (最多120秒)...")
        final_status = None
        for i in range(40):  # 40 * 3s = 120s
            try:
                result = api_get(f"/api/tasks/{task_id}/status")
                final_status = result["data"]["status"]
                progress = result["data"]["progress"]
                step = result["data"].get("current_step", "")
                if final_status in ("completed", "failed", "cancelled"):
                    break
                time.sleep(3)
            except Exception as e:
                log_test("状态轮询", False, str(e))
                break

        if final_status:
            log_test("任务最终状态", final_status in ("completed", "failed", "cancelled"),
                     f"status={final_status}, progress={progress}, step={step}")

        # 如果完成，检查 completed_at
        if final_status == "completed":
            try:
                result = api_get(f"/api/tasks/{task_id}")
                completed_at = result["data"].get("completed_at")
                log_test("completed_at 已设置", completed_at is not None, f"completed_at={completed_at}")
            except Exception as e:
                log_test("completed_at 检查", False, str(e))

            # 检查 result_path
            try:
                result = api_get(f"/api/tasks/{task_id}")
                result_path = result["data"].get("result_path")
                log_test("result_path 已设置", result_path is not None, f"result_path={result_path}")
            except Exception as e:
                log_test("result_path 检查", False, str(e))

            # 预览
            try:
                result = api_get(f"/api/tasks/{task_id}/preview")
                log_test("任务预览", result["code"] == 0)
                preview_md = result["data"].get("markdown_preview")
                log_test("预览有内容", preview_md is not None and len(preview_md) > 0,
                         f"len={len(preview_md) if preview_md else 0}")
            except Exception as e:
                log_test("任务预览", False, str(e))

            # 下载
            try:
                result = api_get(f"/api/tasks/{task_id}/download")
                log_test("下载信息", result["code"] == 0, f"url={result['data'].get('download_url')}")
            except Exception as e:
                log_test("下载信息", False, str(e))
        elif final_status == "failed":
            try:
                result = api_get(f"/api/tasks/{task_id}")
                error_msg = result["data"].get("error_message")
                log_test("失败任务有错误信息", error_msg is not None, f"error={error_msg}")
            except Exception as e:
                log_test("失败任务检查", False, str(e))

            # 重试
            try:
                result = api_post(f"/api/tasks/{task_id}/retry")
                log_test("任务重试", result["code"] == 0, f"status={result['data'].get('status')}")
            except Exception as e:
                log_test("任务重试", False, str(e))
    else:
        log_test("任务详情轮询", False, "缺少 task_id")

    # ════════════════════════════════════════════════════
    # 9. 取消任务测试
    # ════════════════════════════════════════════════════
    print("\n─── 9. 取消任务测试 ───")
    # 创建一个新任务然后取消
    if upload_id:
        try:
            result = api_post("/api/tasks", {
                "upload_id": upload_id,
                "standard": "GB/T 9704",
                "use_rag": False,
                "llm_model": "qwen-plus",
            })
            cancel_task_id = result["data"].get("id")
            # 立即取消
            result = api_post(f"/api/tasks/{cancel_task_id}/cancel")
            log_test("取消任务", result["code"] == 0)
        except Exception as e:
            log_test("取消任务", False, str(e))

    # ════════════════════════════════════════════════════
    # 10. 错误处理测试
    # ════════════════════════════════════════════════════
    print("\n─── 10. 错误处理测试 ───")
    # 不存在的任务
    try:
        result = api_get("/api/tasks/nonexistent-id")
        log_test("不存在的任务返回404", result["code"] == 404)
    except Exception as e:
        log_test("不存在的任务", False, str(e))

    # 不支持的文件格式
    try:
        boundary = "----ErrBoundary12345"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="test.exe"\r\n'
            "Content-Type: application/octet-stream\r\n\r\n"
        ).encode() + b"fake content" + f"\r\n--{boundary}--\r\n".encode()
        req = urllib.request.Request(
            f"{BASE_URL}/api/upload",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
        log_test("不支持的文件格式返回400", result["code"] == 400)
    except Exception as e:
        log_test("不支持的文件格式", False, str(e))

    # ════════════════════════════════════════════════════
    # 汇总
    # ════════════════════════════════════════════════════
    print("\n" + "=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    print(f"测试结果: {passed}/{total} 通过, {failed} 失败")

    if bug_list:
        print(f"\n发现 {len(bug_list)} 个 Bug:")
        for i, bug in enumerate(bug_list, 1):
            print(f"  Bug #{i}: {bug['name']} — {bug['detail']}")
    else:
        print("\n未发现 Bug")

    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

"""全面端到端测试脚本

模拟人工使用流程，测试所有 API 接口，发现并记录 Bug。
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8000"

# 测试结果记录
results: list[dict] = []


def log_test(name: str, passed: bool, detail: str = "") -> None:
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed, "detail": detail})
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))


def api_get(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req) as resp:
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
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_put(path: str, data: dict) -> dict:
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE_URL}{path}", data=body,
                                 headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_delete(path: str) -> dict:
    req = urllib.request.Request(f"{BASE_URL}{path}", method="DELETE")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def api_upload(path: str, file_path: str) -> dict:
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(file_path)
    with open(file_path, "rb") as f:
        file_content = f.read()
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE_URL}{path}", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ──────────────────────────────────────────
# Test 1: 健康检查
# ──────────────────────────────────────────
def test_health():
    try:
        result = api_get("/api/health")
        assert result["status"] == "ok"
        log_test("健康检查", True)
    except Exception as e:
        log_test("健康检查", False, str(e))


# ──────────────────────────────────────────
# Test 2: 文件上传
# ──────────────────────────────────────────
def test_upload():
    # 创建测试文件
    test_file = Path("data/test_upload.md")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text("# 测试文档\n\n这是一段测试内容。", encoding="utf-8")

    try:
        result = api_upload("/api/upload", str(test_file))
        assert result["code"] == 0
        assert "upload_id" in result["data"]
        assert result["data"]["filename"] == "test_upload.md"
        log_test("文件上传", True, f"upload_id={result['data']['upload_id']}")
        return result["data"]["upload_id"]
    except Exception as e:
        log_test("文件上传", False, str(e))
        return None


# ──────────────────────────────────────────
# Test 3: 上传不支持的文件格式
# ──────────────────────────────────────────
def test_upload_unsupported():
    test_file = Path("data/test_unsupported.exe")
    test_file.write_text("fake", encoding="utf-8")
    try:
        result = api_upload("/api/upload", str(test_file))
        # 应该返回错误
        assert result["code"] != 0
        log_test("上传不支持格式拒绝", True, f"正确拒绝: {result['message']}")
    except urllib.error.HTTPError as e:
        # FastAPI 可能直接返回 HTTP 错误
        log_test("上传不支持格式拒绝", True, f"HTTP {e.code}")
    except Exception as e:
        log_test("上传不支持格式拒绝", False, str(e))
    finally:
        test_file.unlink(missing_ok=True)


# ──────────────────────────────────────────
# Test 4: 创建任务
# ──────────────────────────────────────────
def test_create_task(upload_id: str):
    try:
        result = api_post("/api/tasks", {
            "upload_id": upload_id,
            "standard": "GB/T 9704",
            "use_rag": True,
            "llm_model": "qwen-plus",
        })
        assert result["code"] == 0
        assert "id" in result["data"]
        assert result["data"]["status"] == "pending"
        log_test("创建任务", True, f"task_id={result['data']['id']}")
        return result["data"]["id"]
    except Exception as e:
        log_test("创建任务", False, str(e))
        return None


# ──────────────────────────────────────────
# Test 5: 任务列表
# ──────────────────────────────────────────
def test_list_tasks():
    try:
        result = api_get("/api/tasks?page=1&page_size=10")
        assert result["code"] == 0
        assert "total" in result["data"]
        assert "items" in result["data"]
        log_test("任务列表", True, f"total={result['data']['total']}")
    except Exception as e:
        log_test("任务列表", False, str(e))


# ──────────────────────────────────────────
# Test 6: 任务详情
# ──────────────────────────────────────────
def test_task_detail(task_id: str):
    try:
        result = api_get(f"/api/tasks/{task_id}")
        assert result["code"] == 0
        assert result["data"]["id"] == task_id
        log_test("任务详情", True, f"status={result['data']['status']}")
    except Exception as e:
        log_test("任务详情", False, str(e))


# ──────────────────────────────────────────
# Test 7: 任务状态轮询（等待完成）
# ──────────────────────────────────────────
def test_task_polling(task_id: str):
    try:
        max_wait = 30
        for i in range(max_wait):
            result = api_get(f"/api/tasks/{task_id}/status")
            status = result["data"]["status"]
            progress = result["data"]["progress"]
            if status in ("completed", "failed"):
                break
            time.sleep(1)
        assert status == "completed", f"最终状态: {status}"
        assert progress == 100
        log_test("任务轮询完成", True, f"status={status}, progress={progress}")
    except Exception as e:
        log_test("任务轮询完成", False, str(e))


# ──────────────────────────────────────────
# Test 8: 任务下载
# ──────────────────────────────────────────
def test_task_download(task_id: str):
    try:
        result = api_get(f"/api/tasks/{task_id}/download")
        assert result["code"] == 0
        assert "download_url" in result["data"]
        log_test("任务下载", True)
    except Exception as e:
        log_test("任务下载", False, str(e))


# ──────────────────────────────────────────
# Test 9: 任务预览
# ──────────────────────────────────────────
def test_task_preview(task_id: str):
    try:
        result = api_get(f"/api/tasks/{task_id}/preview")
        assert result["code"] == 0
        log_test("任务预览", True)
    except Exception as e:
        log_test("任务预览", False, str(e))


# ──────────────────────────────────────────
# Test 10: 获取不存在的任务
# ──────────────────────────────────────────
def test_nonexistent_task():
    try:
        result = api_get("/api/tasks/nonexistent-id-12345")
        assert result["code"] == 404
        log_test("不存在任务返回404", True)
    except Exception as e:
        log_test("不存在任务返回404", False, str(e))


# ──────────────────────────────────────────
# Test 11: 知识库文档列表
# ──────────────────────────────────────────
def test_kb_list():
    try:
        result = api_get("/api/kb/documents?page=1&page_size=10")
        assert result["code"] == 0
        log_test("知识库文档列表", True, f"total={result['data']['total']}")
    except Exception as e:
        log_test("知识库文档列表", False, str(e))


# ──────────────────────────────────────────
# Test 12: 上传知识库文档
# ──────────────────────────────────────────
def test_kb_upload():
    test_file = Path("data/test_kb_doc.md")
    test_file.write_text("# 测试规范文档\n\n## 1 范围\n\n测试内容。", encoding="utf-8")
    try:
        result = api_upload("/api/kb/documents", str(test_file))
        assert result["code"] == 0
        assert "id" in result["data"]
        log_test("知识库文档上传", True, f"id={result['data']['id']}")
        return result["data"]["id"]
    except Exception as e:
        log_test("知识库文档上传", False, str(e))
        return None
    finally:
        test_file.unlink(missing_ok=True)


# ──────────────────────────────────────────
# Test 13: 删除知识库文档
# ──────────────────────────────────────────
def test_kb_delete(doc_id: str):
    try:
        result = api_delete(f"/api/kb/documents/{doc_id}")
        assert result["code"] == 0
        log_test("知识库文档删除", True)
    except Exception as e:
        log_test("知识库文档删除", False, str(e))


# ──────────────────────────────────────────
# Test 14: 重建知识库
# ──────────────────────────────────────────
def test_kb_rebuild():
    try:
        result = api_post("/api/kb/rebuild")
        assert result["code"] == 0
        log_test("知识库重建", True)
    except Exception as e:
        log_test("知识库重建", False, str(e))


# ──────────────────────────────────────────
# Test 15: 获取系统配置
# ──────────────────────────────────────────
def test_config_get():
    try:
        result = api_get("/api/config")
        assert result["code"] == 0
        assert "llm_provider" in result["data"]
        assert "rag_bm25_weight" in result["data"]
        log_test("获取系统配置", True)
    except Exception as e:
        log_test("获取系统配置", False, str(e))


# ──────────────────────────────────────────
# Test 16: 更新系统配置
# ──────────────────────────────────────────
def test_config_update():
    try:
        result = api_put("/api/config", {
            "rag_top_k": 10,
            "max_file_size_mb": 100,
        })
        assert result["code"] == 0
        assert result["data"]["rag_top_k"] == 10
        assert result["data"]["max_file_size_mb"] == 100
        log_test("更新系统配置", True)
    except Exception as e:
        log_test("更新系统配置", False, str(e))


# ──────────────────────────────────────────
# Test 17: 获取支持的规范
# ──────────────────────────────────────────
def test_supported_standards():
    try:
        result = api_get("/api/config/supported-standards")
        assert result["code"] == 0
        assert len(result["data"]) > 0
        log_test("获取排版规范列表", True, f"count={len(result['data'])}")
    except Exception as e:
        log_test("获取排版规范列表", False, str(e))


# ──────────────────────────────────────────
# Test 18: 获取 LLM 模型列表
# ──────────────────────────────────────────
def test_llm_models():
    try:
        result = api_get("/api/config/llm-models")
        assert result["code"] == 0
        assert len(result["data"]) > 0
        log_test("获取LLM模型列表", True, f"count={len(result['data'])}")
    except Exception as e:
        log_test("获取LLM模型列表", False, str(e))


# ──────────────────────────────────────────
# Test 19: 配置持久化验证
# ──────────────────────────────────────────
def test_config_persistence():
    """验证配置更新后再次读取是否一致"""
    try:
        # 更新
        api_put("/api/config", {"rag_top_k": 8})
        # 重新读取
        result = api_get("/api/config")
        assert result["data"]["rag_top_k"] == 8
        log_test("配置持久化验证", True)
    except Exception as e:
        log_test("配置持久化验证", False, str(e))


# ──────────────────────────────────────────
# Test 20: 任务过滤
# ──────────────────────────────────────────
def test_task_filter():
    try:
        result = api_get("/api/tasks?page=1&page_size=10&status=completed")
        assert result["code"] == 0
        for item in result["data"]["items"]:
            assert item["status"] == "completed"
        log_test("任务状态过滤", True, f"completed count={result['data']['total']}")
    except Exception as e:
        log_test("任务状态过滤", False, str(e))


# ──────────────────────────────────────────
# Test 21: 前端构建产物检查
# ──────────────────────────────────────────
def test_frontend_build():
    dist_dir = Path("frontend/dist")
    try:
        assert dist_dir.exists(), "frontend/dist 目录不存在"
        assert (dist_dir / "index.html").exists(), "index.html 不存在"
        # 检查 JS 资源
        js_files = list(dist_dir.glob("assets/*.js"))
        assert len(js_files) > 0, "无 JS 资源文件"
        log_test("前端构建产物", True, f"JS files={len(js_files)}")
    except Exception as e:
        log_test("前端构建产物", False, str(e))


# ──────────────────────────────────────────
# Main
# ──────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("文档排版智能体 - 全面端到端测试")
    print("=" * 60)
    print()

    # 1. 健康检查
    test_health()

    # 2. 文件上传
    upload_id = test_upload()

    # 3. 上传不支持格式
    test_upload_unsupported()

    # 4. 创建任务
    if upload_id:
        task_id = test_create_task(upload_id)
    else:
        task_id = None

    # 5. 任务列表
    test_list_tasks()

    # 6. 任务详情
    if task_id:
        test_task_detail(task_id)

    # 7. 任务轮询
    if task_id:
        test_task_polling(task_id)

    # 8. 任务下载
    if task_id:
        test_task_download(task_id)

    # 9. 任务预览
    if task_id:
        test_task_preview(task_id)

    # 10. 不存在的任务
    test_nonexistent_task()

    # 11. 知识库文档列表
    test_kb_list()

    # 12. 上传知识库文档
    kb_doc_id = test_kb_upload()

    # 13. 删除知识库文档
    if kb_doc_id:
        test_kb_delete(kb_doc_id)

    # 14. 重建知识库
    test_kb_rebuild()

    # 15. 获取配置
    test_config_get()

    # 16. 更新配置
    test_config_update()

    # 17. 排版规范列表
    test_supported_standards()

    # 18. LLM 模型列表
    test_llm_models()

    # 19. 配置持久化
    test_config_persistence()

    # 20. 任务过滤
    test_task_filter()

    # 21. 前端构建
    test_frontend_build()

    # 汇总
    print()
    print("=" * 60)
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    failed = total - passed
    print(f"总计: {total} | 通过: {passed} | 失败: {failed}")
    print("=" * 60)

    if failed > 0:
        print("\n失败项:")
        for r in results:
            if not r["passed"]:
                print(f"  - {r['name']}: {r['detail']}")

    sys.exit(0 if failed == 0 else 1)

"""Loop Engineering 后端全面测试脚本"""

import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0
ERRORS = []


def test(name, url, method="GET", data=None, expect_status=200, expect_code=0, check_fn=None):
    global PASS, FAIL
    try:
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(
            url, data=body, headers={"Content-Type": "application/json"} if body else {}, method=method
        )
        r = urllib.request.urlopen(req, timeout=30)
        status = r.status
        content = r.read().decode()
        content_type = r.headers.get("content-type", "")

        if status != expect_status:
            FAIL += 1
            msg = f"  FAIL {name}: status={status} expected={expect_status}"
            ERRORS.append(msg)
            print(msg)
            return

        if "json" in content_type:
            resp = json.loads(content)
            code = resp.get("code", -1)
            if check_fn:
                check_fn(resp, name)
            elif code != expect_code:
                FAIL += 1
                msg = f"  FAIL {name}: code={code} expected={expect_code}, msg={resp.get('message','')}"
                ERRORS.append(msg)
                print(msg)
                return
        PASS += 1
        print(f"  PASS {name} (status={status})")
    except urllib.error.HTTPError as e:
        if e.code != expect_status:
            FAIL += 1
            msg = f"  FAIL {name}: HTTPError status={e.code} expected={expect_status}"
            ERRORS.append(msg)
            print(msg)
        else:
            PASS += 1
            print(f"  PASS {name} (status={e.code}, expected error)")
    except Exception as e:
        FAIL += 1
        msg = f"  FAIL {name}: Exception {type(e).__name__}: {e}"
        ERRORS.append(msg)
        print(msg)


print("=" * 60)
print("Loop Engineering 后端全面测试")
print("=" * 60)

# ─── 健康检查 ───
print("\n[Health] 健康检查")
test("Health check", f"{BASE}/api/health", expect_code=-1)  # health doesn't use ResponseModel code field

# ─── 配置 ───
print("\n[Config] 配置管理")
test("Get config", f"{BASE}/api/config")
test("Update config", f"{BASE}/api/config", method="PUT", data={"llm_model": "glm-4"})

# ─── 上传 ───
print("\n[Upload] 上传管理")
test("Upload - no file (validation)", f"{BASE}/api/upload", method="POST", expect_status=422)

# ─── 任务管理 ───
print("\n[Tasks] 任务管理")
test("Get task stats", f"{BASE}/api/tasks/stats")
test("Get task list", f"{BASE}/api/tasks?page=1&page_size=10")
test("Get nonexistent task", f"{BASE}/api/tasks/nonexistent-id", expect_code=404)
test("Create task - missing fields", f"{BASE}/api/tasks", method="POST", data={}, expect_status=422)

# Bug #2 验证：不存在的 upload_id
print("\n[Bug#2] create_task upload_id 校验")
existing_tasks_resp = json.loads(urllib.request.urlopen(f"{BASE}/api/tasks/stats").read())
existing_tasks = existing_tasks_resp.get("data", {}).get("recent_tasks", [])
test(
    "Create task - valid upload_id",
    f"{BASE}/api/tasks",
    method="POST",
    data={"upload_id": existing_tasks[0]["upload_id"], "standard": "custom"}
    if existing_tasks
    else {"upload_id": "test", "standard": "custom"},
)

# ─── 模板管理 ───
print("\n[Templates] 模板管理")
test("List templates", f"{BASE}/api/templates?page=1&page_size=10")
test("Get nonexistent template", f"{BASE}/api/templates/nonexistent-id", expect_code=404)

# ─── 对话排版 ───
print("\n[Chat] 对话排版")
test("List chat sessions", f"{BASE}/api/chat/sessions")
test("Create chat session", f"{BASE}/api/chat/sessions", method="POST", data={"task_id": None})

# ─── 知识库 ───
print("\n[KB] 知识库")
test("KB stats", f"{BASE}/api/kb/stats")
test("KB documents list", f"{BASE}/api/kb/documents")
test("KB search (empty query)", f"{BASE}/api/kb/search", method="POST", data={"query": "", "top_k": 5}, expect_code=400)
test("KB search (valid)", f"{BASE}/api/kb/search", method="POST", data={"query": "字体", "top_k": 3})

# ─── Formatters (Bug #1) ───
print("\n[Bug#1] Formatters API")


def check_formatters(resp, name):
    global PASS, FAIL
    # formatters should return JSON, not HTML
    if "data" not in resp or not isinstance(resp.get("data"), list):
        FAIL += 1
        msg = f"  FAIL {name}: response doesn't contain formatters list. data type: {type(resp.get('data'))}"
        ERRORS.append(msg)
        print(msg)
        return


test("Formatters list", f"{BASE}/api/formatters", check_fn=check_formatters)

# ─── 预览 ───
print("\n[Preview] 任务预览")
if existing_tasks:
    task_id = existing_tasks[0]["id"]
    test("Task preview", f"{BASE}/api/tasks/{task_id}/preview")
    test("Task download metadata", f"{BASE}/api/tasks/{task_id}/download")
    test("Task cancel (completed)", f"{BASE}/api/tasks/{task_id}/cancel", method="POST")

# ─── 结果 ───
print("\n" + "=" * 60)
print(f"测试结果: {PASS} 通过 / {FAIL} 失败 / {PASS+FAIL} 总计")
if ERRORS:
    print("\n失败详情:")
    for e in ERRORS:
        print(e)
print("=" * 60)

# 返回退出码
sys.exit(0 if FAIL == 0 else 1)

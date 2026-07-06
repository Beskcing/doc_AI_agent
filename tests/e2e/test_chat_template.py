"""对话排版 + 模板管理 API 测试"""
import urllib.request
import json
import time

BASE = "http://localhost:8000"
results = []

def log(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append({"name": name, "passed": passed})
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))

def api_get(path):
    req = urllib.request.Request(f"{BASE}{path}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())

def api_post(path, data=None):
    if data is None:
        data = {}
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())

def api_put(path, data):
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}{path}", data=body,
                                 headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

def api_delete(path):
    req = urllib.request.Request(f"{BASE}{path}", method="DELETE")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode())

# ════════════════════════════════════════════════════
print("=" * 60)
print("对话排版 + 模板管理 API 测试")
print("=" * 60)

# ─── 1. 样式模板管理 ───
print("\n─── 1. 样式模板管理 ───")

# 创建模板
try:
    result = api_post("/api/templates", {
        "name": "测试模板",
        "style_config": {
            "page_layout": {"paper_size": "A4", "margin_top_cm": 3.7},
            "body_style": {"font": {"family": "仿宋", "size_pt": 16}},
            "heading_styles": [{"level": 1, "font": {"family": "黑体", "size_pt": 22}}],
        },
        "description": "测试用模板",
    })
    log("创建模板", result["code"] == 0, f"id={result['data'].get('id', '')[:8]}...")
    template_id = result["data"].get("id")
except Exception as e:
    log("创建模板", False, str(e))
    template_id = None

# 获取模板列表
try:
    result = api_get("/api/templates?page=1&page_size=10")
    log("模板列表", result["code"] == 0, f"total={result['data'].get('total')}")
except Exception as e:
    log("模板列表", False, str(e))

# 获取模板详情
if template_id:
    try:
        result = api_get(f"/api/templates/{template_id}")
        log("模板详情", result["code"] == 0, f"name={result['data'].get('name')}")
    except Exception as e:
        log("模板详情", False, str(e))

    # 更新模板
    try:
        result = api_put(f"/api/templates/{template_id}", {
            "name": "更新后的模板",
            "description": "更新描述",
        })
        log("更新模板", result["code"] == 0, f"name={result['data'].get('name')}")
    except Exception as e:
        log("更新模板", False, str(e))

# ─── 2. 对话排版 ───
print("\n─── 2. 对话排版 ───")

# 创建会话
try:
    result = api_post("/api/chat/sessions", {
        "title": "测试对话",
        "style_config": {"page_layout": {"paper_size": "A4"}},
    })
    log("创建会话", result["code"] == 0, f"id={result['data'].get('id', '')[:8]}...")
    session_id = result["data"].get("id")
except Exception as e:
    log("创建会话", False, str(e))
    session_id = None

# 获取会话列表
try:
    result = api_get("/api/chat/sessions?page=1&page_size=10")
    log("会话列表", result["code"] == 0, f"total={result['data'].get('total')}")
except Exception as e:
    log("会话列表", False, str(e))

# 获取会话详情
if session_id:
    try:
        result = api_get(f"/api/chat/sessions/{session_id}")
        log("会话详情", result["code"] == 0, f"title={result['data']['session'].get('title')}")
    except Exception as e:
        log("会话详情", False, str(e))

# 对话修改样式（需要 LLM）
print("\n  对话修改样式 (调用 LLM)...")
try:
    result = api_post("/api/chat/style", {
        "message": "将正文字体改为宋体，字号改为14磅",
        "current_style_config": {
            "page_layout": {"paper_size": "A4"},
            "body_style": {"font": {"family": "仿宋", "size_pt": 16}},
        },
        "session_id": session_id,
    })
    log("对话修改样式", result["code"] == 0, f"reply={result['data'].get('reply', '')[:50]}...")
    
    # 检查返回的 style_config
    if result["code"] == 0:
        updated_config = result["data"].get("updated_style_config", {})
        log("返回更新后的样式配置", updated_config is not None and len(updated_config) > 0,
            f"keys={list(updated_config.keys())[:5]}")
except Exception as e:
    log("对话修改样式", False, str(e))

# 获取会话消息
if session_id:
    try:
        result = api_get(f"/api/chat/sessions/{session_id}/messages")
        log("获取会话消息", result["code"] == 0, f"count={len(result['data'].get('items', []))}")
    except Exception as e:
        log("获取会话消息", False, str(e))

# ─── 3. 清理 ───
print("\n─── 3. 清理测试数据 ───")

# 删除会话
if session_id:
    try:
        result = api_delete(f"/api/chat/sessions/{session_id}")
        log("删除会话", result["code"] == 0)
    except Exception as e:
        log("删除会话", False, str(e))

# 删除模板
if template_id:
    try:
        result = api_delete(f"/api/templates/{template_id}")
        log("删除模板", result["code"] == 0)
    except Exception as e:
        log("删除模板", False, str(e))

# ─── 汇总 ───
print("\n" + "=" * 60)
total = len(results)
passed = sum(1 for r in results if r["passed"])
failed = total - passed
print(f"测试结果: {passed}/{total} 通过, {failed} 失败")
if failed:
    for r in results:
        if not r["passed"]:
            print(f"  FAIL: {r['name']}")
print("=" * 60)

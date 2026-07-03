"""全面 API 验证 - 包括新增接口"""
import urllib.request
import json

BASE = "http://localhost:8000"

endpoints = [
    ("GET", "/api/health", None),
    ("GET", "/api/tasks?page=1&page_size=5", None),
    ("GET", "/api/tasks/stats", None),
    ("GET", "/api/config", None),
    ("GET", "/api/config/supported-standards", None),
    ("GET", "/api/config/llm-models", None),
    ("GET", "/api/kb/documents?page=1&page_size=5", None),
]

all_ok = True
for method, path, data in endpoints:
    try:
        req = urllib.request.Request(f"{BASE}{path}", method=method)
        if data:
            req.data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            code = result.get("code")
            has_data = result.get("data") is not None
            print(f"[OK] {method} {path} -> code={code}, has_data={has_data}")
    except Exception as e:
        all_ok = False
        print(f"[ERR] {method} {path} -> {e}")

# 测试 stats 返回结构
try:
    req = urllib.request.Request(f"{BASE}/api/tasks/stats")
    with urllib.request.urlopen(req, timeout=5) as resp:
        result = json.loads(resp.read().decode())
        data = result["data"]
        print(f"\n[Stats] keys: {list(data.keys())}")
        print(f"  stats: {data['stats']}")
        print(f"  recent_tasks count: {len(data['recent_tasks'])}")
except Exception as e:
    print(f"[ERR] stats detail: {e}")

print(f"\n{'='*40}")
print(f"Result: {'ALL PASS' if all_ok else 'HAS ERRORS'}")

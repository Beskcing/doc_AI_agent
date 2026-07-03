"""快速 API 健康检查"""
import urllib.request
import json

BASE = "http://localhost:8000"

endpoints = [
    ("GET", "/api/health", None),
    ("GET", "/api/tasks?page=1&page_size=5", None),
    ("GET", "/api/config", None),
    ("GET", "/api/config/supported-standards", None),
    ("GET", "/api/config/llm-models", None),
    ("GET", "/api/kb/documents?page=1&page_size=5", None),
]

for method, path, data in endpoints:
    try:
        req = urllib.request.Request(f"{BASE}{path}", method=method)
        if data:
            req.data = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read().decode())
            code = result.get("code")
            print(f"[OK] {method} {path} -> code={code}")
    except Exception as e:
        print(f"[ERR] {method} {path} -> {e}")

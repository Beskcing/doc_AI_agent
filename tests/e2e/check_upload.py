"""Quick upload test to check response format"""
import json
import urllib.request
from pathlib import Path

BASE_URL = "http://localhost:8000"
TEST_PDF = Path("d:/doc_ai_agent/GB 5009.225-2016CN.pdf")

# Upload
boundary = "----TestBoundary123"
with open(TEST_PDF, "rb") as f:
    file_data = f.read()

body = f"--{boundary}\r\n".encode()
body += f'Content-Disposition: form-data; name="file"; filename="{TEST_PDF.name}"\r\n'.encode()
body += b"Content-Type: application/octet-stream\r\n\r\n"
body += file_data
body += b"\r\n"
body += f"--{boundary}--\r\n".encode()

req = urllib.request.Request(
    f"{BASE_URL}/api/upload",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}
)
resp = urllib.request.urlopen(req, timeout=120)
data = json.loads(resp.read().decode())
print("Upload response:")
print(json.dumps(data, indent=2, ensure_ascii=False))

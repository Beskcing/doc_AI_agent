"""检查 MinerU content_list JSON 中的图片引用"""
from pathlib import Path
import json

d = Path("data/output/c57b430c-0b0c-405f-8173-b69b7fd5670f")
f = d / "a30781bd-46f9-46b4-9e05-521ee5c194ae_content_list.json"

data = json.loads(f.read_text(encoding="utf-8"))
if isinstance(data, list):
    print(f"Content list: {len(data)} items")
    # Count types
    types = {}
    for item in data:
        t = item.get("type", "unknown")
        types[t] = types.get(t, 0) + 1
    print(f"Types: {types}")
    
    # Show first 5 of each type
    for t in types:
        print(f"\n--- {t} ---")
        for item in data:
            if item.get("type") == t:
                print(f"  {str(item)[:200]}")
                break
else:
    print(f"Data type: {type(data)}")
    print(list(data.keys())[:10] if isinstance(data, dict) else "N/A")
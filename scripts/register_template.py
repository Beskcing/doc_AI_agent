"""将 GB/T 14454.13-2008 样式模板注册到系统

读取预提取的 JSON 模板，通过 API 保存到数据库，
使其在创建任务时可通过 template_id 选择使用。
"""
import json
import sys
import urllib.request
from pathlib import Path

BASE = "http://localhost:8000"
JSON_PATH = Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008_style.json")

def main():
    # 1. 读取 JSON
    if not JSON_PATH.exists():
        print(f"ERROR: 找不到 {JSON_PATH}")
        sys.exit(1)

    with open(JSON_PATH, "r", encoding="utf-8") as f:
        style_config = json.load(f)

    print(f"已读取模板 JSON: {JSON_PATH}")
    print(f"  包含: {len(style_config.get('heading_styles', []))} 级标题样式")
    print(f"  正文样式: {'有' if style_config.get('body_style') else '无'}")
    print(f"  表格样式: {'有' if style_config.get('table_style') else '无'}")
    print()

    # 2. 通过 API 保存模板
    payload = {
        "name": "GB/T 14454.13-2008 香料羰值和羰基化合物含量的测定",
        "description": "从 GB/T 14454.13-2008CN.docx 提取的排版模板。"
                       "封面16pt加粗居中；前言标题16pt居中不加粗；"
                       "各级条款(1~5级)宋体10.5pt不加粗无缩进；"
                       "正文首行缩进2字符；表格单线边框0.5pt不加粗。",
        "style_config": style_config,
        "source_docx_path": str(Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008.docx")),
    }

    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}/api/templates",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"ERROR: API 调用失败: {e}")
        sys.exit(1)

    if result.get("code") not in (0, 200) and result.get("data") is None:
        print(f"ERROR: API 返回错误: {result}")
        sys.exit(1)

    data = result.get("data", result)
    template_id = data.get("id", "unknown")
    template_name = data.get("name", "unknown")

    print(f"模板注册成功!")
    print(f"  ID:   {template_id}")
    print(f"  名称: {template_name}")
    print()
    print(f"使用方式:")
    print(f"  创建任务时传入 template_id=\"{template_id}\" 即可使用该模板样式")
    print(f"  或在前端「模板管理」页面中选择该模板")

    return template_id


if __name__ == "__main__":
    main()

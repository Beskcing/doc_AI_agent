"""从 GB_T 14454.13-2008CN.docx 提取样式模板"""
import glob
import json
import sys
from pathlib import Path

# 找到 docx 文件
files = glob.glob("D:/SP*/**/GB_T 14454.13-2008CN.docx", recursive=True)
if not files:
    print("ERROR: 找不到 GB_T 14454.13-2008CN.docx")
    sys.exit(1)

docx_path = files[0]
print(f"找到文件: {docx_path}")
print()

# 复制到项目目录
import shutil
target = Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008.docx")
shutil.copy2(docx_path, target)
print(f"已复制到: {target}")
print()

# 提取样式
sys.path.insert(0, "d:/doc_ai_agent")
from src.tools.docx_style_extractor import DocxStyleExtractor

extractor = DocxStyleExtractor()
result = extractor.extract(str(docx_path))

# 输出完整结果
print("=" * 60)
print("提取结果（JSON）")
print("=" * 60)
print(json.dumps(result, indent=2, ensure_ascii=False))

# 保存结果
output_path = Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008_style.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(result, f, indent=2, ensure_ascii=False)
print(f"\n样式配置已保存到: {output_path}")

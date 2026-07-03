"""检查 MinerU 输出的 Markdown 格式"""
from pathlib import Path
import re

md = Path("data/output/c57b430c-0b0c-405f-8173-b69b7fd5670f/full.md").read_text(encoding="utf-8")

# Images
md_imgs = re.findall(r'!\[(.*?)\]\((.*?)\)', md)
html_imgs = re.findall(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', md, re.IGNORECASE)
print(f"Markdown images: {len(md_imgs)}")
for alt, path in md_imgs[:3]:
    print(f"  ![{alt[:30]}]({path[:80]})")
print(f"HTML img tags: {len(html_imgs)}")
for p in html_imgs[:3]:
    print(f"  src={p[:80]}")

# Tables
tables = re.findall(r'<table[\s>].*?</table>', md, re.DOTALL | re.IGNORECASE)
print(f"\nHTML tables: {len(tables)}")
for i, t in enumerate(tables[:3]):
    print(f"  Table {i}: {len(t)} chars")
    print(f"    First 150: {t[:150]}")

# Markdown pipe tables
pipe_tables = re.findall(r'\|.*\|', md)
print(f"\nPipe table lines: {len(pipe_tables)}")

# Check if images exist
img_dir = Path("data/output/c57b430c-0b0c-405f-8173-b69b7fd5670f/images")
imgs = list(img_dir.glob("*"))
print(f"\nImage files on disk: {len(imgs)}")
if imgs:
    print(f"  First 3: {[i.name for i in imgs[:3]]}")

# Check image path format
if md_imgs:
    alt, path = md_imgs[0]
    full = Path("data/output/c57b430c-0b0c-405f-8173-b69b7fd5670f") / path
    print(f"\nFirst image full path: {full}")
    print(f"  Exists: {full.exists()}")
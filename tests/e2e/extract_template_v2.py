"""从 GB_T 14454.13-2008CN.docx 提取完整样式模板

该文档所有段落使用 Normal 样式，条款层级通过字体大小、加粗、对齐、缩进和内容模式区分。
本脚本通过内容模式匹配 + 格式采样，推断各级条款样式。
"""
import glob
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, "d:/doc_ai_agent")

from docx import Document
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from src.tools.docx_style_extractor import DocxStyleExtractor, _emu_to_pt

# 找到 docx 文件
files = glob.glob("D:/SP*/**/GB_T 14454.13-2008CN.docx", recursive=True)
docx_path = files[0]
doc = Document(str(docx_path))

# ============================================================
# 第一步：用基础提取器获取页面布局、表格、页眉页脚等
# ============================================================
base_extractor = DocxStyleExtractor()
base_result = base_extractor.extract(docx_path)

# ============================================================
# 第二步：基于内容模式 + 格式推断条款层级
# ============================================================

ALIGNMENT_MAP = {
    WD_ALIGN_PARAGRAPH.LEFT: "left",
    WD_ALIGN_PARAGRAPH.CENTER: "center",
    WD_ALIGN_PARAGRAPH.RIGHT: "right",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "justify",
}


def get_paragraph_info(p):
    """提取段落的完整格式信息"""
    text = p.text.strip()
    if not text:
        return None

    # 字体
    fonts = []
    east_asia_fonts = []
    sizes = []
    bolds = []
    for run in p.runs:
        if run.font.name:
            fonts.append(run.font.name)
        if run.font.size:
            sizes.append(_emu_to_pt(run.font.size))
        if run.font.bold is not None:
            bolds.append(run.font.bold)
        try:
            rpr = run._element.find(qn("w:rPr"))
            if rpr is not None:
                rf = rpr.find(qn("w:rFonts"))
                if rf is not None:
                    ea = rf.get(qn("w:eastAsia"))
                    if ea:
                        east_asia_fonts.append(ea)
        except:
            pass

    font_family = Counter(fonts).most_common(1)[0][0] if fonts else None
    ea_family = Counter(east_asia_fonts).most_common(1)[0][0] if east_asia_fonts else None
    font_size = Counter(sizes).most_common(1)[0][0] if sizes else None
    is_bold = Counter(bolds).most_common(1)[0][0] if bolds else None

    # 对齐
    align = None
    if p.alignment is not None:
        align = ALIGNMENT_MAP.get(p.alignment, "left")

    # 行距
    line_spacing = 1.0
    pf = p.paragraph_format
    if pf and pf.line_spacing is not None:
        if isinstance(pf.line_spacing, float):
            line_spacing = float(pf.line_spacing)

    # 首行缩进
    first_indent_chars = 0
    if pf and pf.first_line_indent:
        indent_pt = _emu_to_pt(pf.first_line_indent)
        fs = font_size if font_size else 10.5
        if fs > 0:
            first_indent_chars = round(indent_pt / fs, 1)

    # 段前段后
    space_before = 0
    space_after = 0
    if pf:
        if pf.space_before is not None:
            space_before = _emu_to_pt(pf.space_before)
        if pf.space_after is not None:
            space_after = _emu_to_pt(pf.space_after)

    return {
        "text": text,
        "font_family": font_family,
        "east_asia_family": ea_family,
        "font_size": font_size,
        "bold": is_bold,
        "alignment": align,
        "line_spacing": line_spacing,
        "first_indent_chars": first_indent_chars,
        "space_before": space_before,
        "space_after": space_after,
    }


# 收集所有非空段落信息
all_paras = []
for p in doc.paragraphs:
    info = get_paragraph_info(p)
    if info:
        all_paras.append(info)


def classify_heading_level(text):
    """根据内容模式判断条款层级

    返回:
        "title" - 文档标题
        "heading_1" - 一级条款 (如 "1 范围", "前言", "附录A")
        "heading_2" - 二级条款 (如 "4.1 原理", "4.2 试剂")
        "heading_3" - 三级条款 (如 "4.2.1 氢氧化钠")
        "heading_4" - 四级条款 (如 "4.4.4.1")
        "body" - 正文
        "note" - 注释
        "list_item" - 列表项 (——开头)
    """
    text = text.strip()

    # 文档标题特征
    if text.startswith("中华人民共和国国家标准"):
        return "title"
    if re.match(r'^GB/?T?\s*\d+', text) and len(text) < 100:
        return "title"

    # 前言/引言
    if text in ("前 言", "前言", "引 言", "引言"):
        return "heading_1"

    # 附录标题
    if re.match(r'^附录[A-Z]\s*[（(]', text):
        return "heading_1"
    if re.match(r'^附录[A-Z]\s*$', text):
        return "heading_1"

    # 一级条款: "1 范围", "2 规范性引用文件", "3 术语和定义"
    if re.match(r'^\d+\s+\S', text) and not re.match(r'^\d+\.\d+', text):
        return "heading_1"

    # "第一法", "第二法", "第三法"
    if re.match(r'^第[一二三四五六七八九十]+法\s', text):
        return "heading_1"

    # 四级条款: "4.4.4.1", "4.4.4.2"
    if re.match(r'^\d+\.\d+\.\d+\.\d+\s', text):
        return "heading_4"

    # 三级条款: "4.2.1", "4.3.1", "5.3.1"
    if re.match(r'^\d+\.\d+\.\d+\s', text):
        return "heading_3"

    # 二级条款: "4.1", "4.2", "5.1"
    if re.match(r'^\d+\.\d+\s', text):
        return "heading_2"

    # 注释
    if re.match(r'^注\d?[：:]', text):
        return "note"
    if text.startswith("注："):
        return "note"

    # 列表项
    if text.startswith("——"):
        return "list_item"

    # 试验报告
    if text == "试验报告应包括：" or text == "试验报告应包括：":
        return "body"

    return "body"


# 分类所有段落
classified = {"title": [], "heading_1": [], "heading_2": [], "heading_3": [],
              "heading_4": [], "body": [], "note": [], "list_item": []}

for info in all_paras:
    level = classify_heading_level(info["text"])
    classified[level].append(info)

# ============================================================
# 第三步：为每个层级取最常见的格式（作为样式模板）
# ============================================================

def make_style(infos, level, default_size=10.5):
    """从一组段落信息中提取最常见样式"""
    if not infos:
        return None

    fonts = [i["font_family"] for i in infos if i["font_family"]]
    ea_fonts = [i["east_asia_family"] for i in infos if i["east_asia_family"]]
    sizes = [i["font_size"] for i in infos if i["font_size"]]
    bolds = [i["bold"] for i in infos if i["bold"] is not None]
    aligns = [i["alignment"] for i in infos if i["alignment"]]
    ls = [i["line_spacing"] for i in infos]
    indents = [i["first_indent_chars"] for i in infos]
    sb = [i["space_before"] for i in infos]
    sa = [i["space_after"] for i in infos]

    def most_common(lst, default=None):
        return Counter(lst).most_common(1)[0][0] if lst else default

    font_family = most_common(fonts, "宋体")
    ea_family = most_common(ea_fonts, font_family)

    return {
        "level": level,
        "font": {
            "family": font_family,
            "east_asia_family": ea_family,
            "size_pt": most_common(sizes, default_size),
            "bold": most_common(bolds, False),
            "italic": False,
            "underline": False,
            "strikethrough": False,
            "color_hex": "#000000",
        },
        "alignment": most_common(aligns, "justify"),
        "line_spacing": most_common(ls, 1.0),
        "line_spacing_pt": None,
        "line_spacing_rule": "multiple",
        "space_before_pt": most_common(sb, 0),
        "space_after_pt": most_common(sa, 0),
        "first_line_indent_chars": most_common(indents, 0),
        "left_indent_cm": 0,
        "right_indent_cm": 0,
        "keep_together": False,
        "keep_with_next": level is not None and level != "body",
        "widow_control": True,
    }


# 构建 heading_styles
heading_styles = []
for level_num, key in [(1, "heading_1"), (2, "heading_2"), (3, "heading_3"), (4, "heading_4")]:
    style = make_style(classified[key], level_num)
    if style:
        heading_styles.append(style)

# 正文样式
body_style = make_style(classified["body"], None)
if body_style:
    del body_style["level"]

# 注释样式
note_style = make_style(classified["note"], None)

# 列表样式
list_style = make_style(classified["list_item"], None)

# ============================================================
# 第四步：组装完整模板
# ============================================================

template = {
    "page_layout": base_result["page_layout"],
    "heading_styles": heading_styles,
    "body_style": body_style,
    "table_style": base_result["table_style"],
    "list_style": list_style,
    "footnote_style": base_result.get("footnote_style"),
    "caption_style": base_result.get("caption_style"),
    "header_footer_style": base_result["header_footer_style"],
    "note_style": note_style,
    "rag_sources": [],
    "source_document": "GB/T 14454.13-2008",
    "extraction_note": "文档所有段落均使用Normal样式，条款层级通过内容模式+格式特征推断",
}

# ============================================================
# 第五步：输出和保存
# ============================================================

print("=" * 60)
print("段落分类统计:")
print("=" * 60)
for key, items in classified.items():
    print(f"  {key}: {len(items)} 段")
    if items:
        for item in items[:3]:
            print(f"    - {item['text'][:50]}")

print()
print("=" * 60)
print("完整样式模板 (JSON)")
print("=" * 60)
print(json.dumps(template, indent=2, ensure_ascii=False))

# 保存
output_path = Path("d:/doc_ai_agent/data/templates/GB_T_14454_13_2008_style.json")
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(template, f, indent=2, ensure_ascii=False)

print(f"\n样式模板已保存到: {output_path}")

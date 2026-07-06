"""精细分析 GB_T 14454.13-2008CN.docx 每个段落的完整格式"""
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
from src.tools.docx_style_extractor import _emu_to_pt, _emu_to_cm

files = glob.glob("D:/SP*/**/GB_T 14454.13-2008CN.docx", recursive=True)
doc = Document(files[0])

ALIGN_MAP = {
    WD_ALIGN_PARAGRAPH.LEFT: "LEFT",
    WD_ALIGN_PARAGRAPH.CENTER: "CENTER",
    WD_ALIGN_PARAGRAPH.RIGHT: "RIGHT",
    WD_ALIGN_PARAGRAPH.JUSTIFY: "JUSTIFY",
}

def full_analysis(p, idx):
    """完整分析一个段落"""
    text = p.text.strip()
    if not text:
        return None
    
    style_name = p.style.name if p.style else "None"
    
    # ---- 段落级格式 ----
    pf = p.paragraph_format
    
    # 对齐
    align = "inherit"
    if p.alignment is not None:
        align = ALIGN_MAP.get(p.alignment, str(p.alignment))
    
    # 行距
    ls_val = "inherit"
    ls_type = "inherit"
    if pf and pf.line_spacing is not None:
        if isinstance(pf.line_spacing, float):
            ls_val = f"{pf.line_spacing}x"
            ls_type = "multiple"
        else:
            try:
                ls_val = f"{_emu_to_pt(pf.line_spacing)}pt"
                ls_type = "exact"
            except:
                ls_val = str(pf.line_spacing)
    
    # 段前段后
    sb = "inherit"
    sa = "inherit"
    if pf:
        if pf.space_before is not None:
            sb = f"{_emu_to_pt(pf.space_before)}pt"
        if pf.space_after is not None:
            sa = f"{_emu_to_pt(pf.space_after)}pt"
    
    # 首行缩进
    fi = "inherit"
    if pf and pf.first_line_indent:
        fi = f"{_emu_to_pt(pf.first_line_indent)}pt"
    
    # 左/右缩进
    li = ri = "inherit"
    if pf:
        if pf.left_indent is not None:
            li = f"{_emu_to_cm(pf.left_indent)}cm"
        if pf.right_indent is not None:
            ri = f"{_emu_to_cm(pf.right_indent)}cm"
    
    # 大纲级别
    outline = "None"
    try:
        pPr = p._element.find(qn("w:pPr"))
        if pPr is not None:
            ol = pPr.find(qn("w:outlineLvl"))
            if ol is not None:
                outline = ol.get(qn("w:val"))
    except:
        pass
    
    # ---- Run级格式（逐run） ----
    run_details = []
    for run in p.runs:
        rd = {"text": run.text[:30]}
        
        # 字体
        if run.font.name:
            rd["font"] = run.font.name
        if run.font.size:
            rd["size"] = f"{_emu_to_pt(run.font.size)}pt"
        if run.font.bold is not None:
            rd["bold"] = run.font.bold
        if run.font.italic is not None:
            rd["italic"] = run.font.italic
        
        # 东亚字体
        try:
            rpr = run._element.find(qn("w:rPr"))
            if rpr is not None:
                rf = rpr.find(qn("w:rFonts"))
                if rf is not None:
                    ea = rf.get(qn("w:eastAsia"))
                    if ea:
                        rd["ea_font"] = ea
                    ascii_f = rf.get(qn("w:ascii"))
                    if ascii_f:
                        rd["ascii_font"] = ascii_f
                    hAnsi = rf.get(qn("w:hAnsi"))
                    if hAnsi:
                        rd["hAnsi_font"] = hAnsi
        except:
            pass
        
        run_details.append(rd)
    
    # 从样式继承的字体
    style_font = "N/A"
    style_ea = "N/A"
    style_size = "N/A"
    style_bold = "N/A"
    try:
        if p.style and p.style.font:
            if p.style.font.name:
                style_font = p.style.font.name
            if p.style.font.size:
                style_size = f"{_emu_to_pt(p.style.font.size)}pt"
            if p.style.font.bold is not None:
                style_bold = p.style.font.bold
        # 从样式XML
        if p.style and p.style.element:
            rpr = p.style.element.find(qn("w:rPr"))
            if rpr is not None:
                rf = rpr.find(qn("w:rFonts"))
                if rf is not None:
                    ea = rf.get(qn("w:eastAsia"))
                    if ea:
                        style_ea = ea
    except:
        pass
    
    return {
        "idx": idx,
        "style": style_name,
        "text": text[:80],
        "align": align,
        "line_spacing": ls_val,
        "ls_type": ls_type,
        "space_before": sb,
        "space_after": sa,
        "first_indent": fi,
        "left_indent": li,
        "right_indent": ri,
        "outline": outline,
        "style_font": style_font,
        "style_ea": style_ea,
        "style_size": style_size,
        "style_bold": style_bold,
        "runs": run_details,
    }

# 分析所有段落
results = []
for i, p in enumerate(doc.paragraphs):
    info = full_analysis(p, i)
    if info:
        results.append(info)

# 输出关键段落
print("=" * 80)
print("关键段落格式分析（封面 + 前言 + 前几级条款）")
print("=" * 80)

# 封面区域（前15个非空段落）
print("\n--- 封面区域 ---")
for r in results[:15]:
    print(f"\n[{r['idx']:3d}] style={r['style']}, outline={r['outline']}")
    print(f"      align={r['align']}, ls={r['line_spacing']}, sb={r['space_before']}, sa={r['space_after']}")
    print(f"      first_indent={r['first_indent']}, left_indent={r['left_indent']}")
    print(f"      style_font={r['style_font']}, style_ea={r['style_ea']}, style_size={r['style_size']}, style_bold={r['style_bold']}")
    print(f"      text: {r['text']}")
    for j, rd in enumerate(r['runs']):
        print(f"      run[{j}]: font={rd.get('font','?')}, ea={rd.get('ea_font','?')}, size={rd.get('size','?')}, bold={rd.get('bold','?')}, text='{rd['text']}'")

# 前言 + 前几级条款
print("\n--- 前言 + 条款区域 ---")
for r in results[15:50]:
    print(f"\n[{r['idx']:3d}] style={r['style']}, outline={r['outline']}")
    print(f"      align={r['align']}, ls={r['line_spacing']}, sb={r['space_before']}, sa={r['space_after']}")
    print(f"      first_indent={r['first_indent']}, left_indent={r['left_indent']}")
    print(f"      style_font={r['style_font']}, style_ea={r['style_ea']}, style_size={r['style_size']}, style_bold={r['style_bold']}")
    print(f"      text: {r['text']}")
    for j, rd in enumerate(r['runs'][:3]):
        print(f"      run[{j}]: font={rd.get('font','?')}, ea={rd.get('ea_font','?')}, size={rd.get('size','?')}, bold={rd.get('bold','?')}, text='{rd['text']}'")

# 统计各级条款的格式
print("\n" + "=" * 80)
print("条款层级格式统计")
print("=" * 80)

def classify(text):
    text = text.strip()
    if text.startswith("中华人民共和国国家标准"):
        return "封面-国名"
    if re.match(r'^GB/?T?\s*\d+', text):
        return "封面-标准号"
    if re.match(r'^\d+\s+\S', text) and not re.match(r'^\d+\.\d+', text):
        return "一级条款(X)"
    if re.match(r'^\d+\.\d+\s', text) and not re.match(r'^\d+\.\d+\.\d+', text):
        return "二级条款(X.Y)"
    if re.match(r'^\d+\.\d+\.\d+\s', text) and not re.match(r'^\d+\.\d+\.\d+\.\d+', text):
        return "三级条款(X.Y.Z)"
    if re.match(r'^\d+\.\d+\.\d+\.\d+\s', text):
        return "四级条款(X.Y.Z.W)"
    if text in ("前 言", "前言"):
        return "前言标题"
    if re.match(r'^附录[A-Z]', text):
        return "附录标题"
    if re.match(r'^第[一二三四五六七八九十]+法\s', text):
        return "法标题"
    if re.match(r'^注\d?[：:]', text) or text.startswith("注："):
        return "注释"
    if text.startswith("——"):
        return "列表项"
    return "正文"

# 按分类统计格式
from collections import defaultdict
category_formats = defaultdict(lambda: {"sizes": [], "bolds": [], "aligns": [], "indents": [], "fonts": [], "ea_fonts": []})

for r in results:
    cat = classify(r['text'])
    for rd in r['runs']:
        if 'size' in rd:
            category_formats[cat]["sizes"].append(rd['size'])
        if 'bold' in rd:
            category_formats[cat]["bolds"].append(rd['bold'])
        if 'font' in rd:
            category_formats[cat]["fonts"].append(rd['font'])
        if 'ea_font' in rd:
            category_formats[cat]["ea_fonts"].append(rd['ea_font'])
    if r['align'] != "inherit":
        category_formats[cat]["aligns"].append(r['align'])
    if r['first_indent'] != "inherit":
        category_formats[cat]["indents"].append(r['first_indent'])

for cat in ["封面-国名", "封面-标准号", "前言标题", "一级条款(X)", "二级条款(X.Y)", 
            "三级条款(X.Y.Z)", "四级条款(X.Y.Z.W)", "正文", "注释", "列表项"]:
    if cat not in category_formats:
        continue
    f = category_formats[cat]
    print(f"\n{cat}:")
    print(f"  字体: {Counter(f['fonts']).most_common(3)}")
    print(f"  东亚字体: {Counter(f['ea_fonts']).most_common(3)}")
    print(f"  字号: {Counter(f['sizes']).most_common(3)}")
    print(f"  加粗: {Counter(f['bolds']).most_common(3)}")
    print(f"  对齐: {Counter(f['aligns']).most_common(3)}")
    print(f"  首行缩进: {Counter(f['indents']).most_common(3)}")

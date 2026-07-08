---
name: gbt
description: >-
  Analyzes and corrects formatting of GB/T (Chinese national standard) DOCX files.
  Analyzes: extracts fonts, sizes, paragraph formatting, heading hierarchy, tables,
  page setup. Corrects: applies standard GB/T formatting (A4, 宋体+TNR, 10.5pt body,
  JUSTIFY with 21pt indent, centered preface/headings, numbered headings with two
  spaces). Features: dynamic cover detection, TOC auto-removal, body space
  normalization, pre-cover amendment support, date line merging, split heading
  merging (e.g. '3.1.1' + '白兰地 brandy' → '3.1.1  白兰地 brandy'), appendix title
  merging (e.g. '附录 A' + '培养基和试剂' → '附录 A  培养基和试剂'). Use when the user
  wants to analyze GB/T document formatting, adjust/fix DOCX formatting to match
  national standard conventions, or both analyze and correct in a single workflow.
---

# GB/T DOCX Format Analyzer & Corrector

## Overview

This skill analyzes and corrects the formatting of GB/T (Guojia Biaozhun / Chinese
national standard) DOCX files. It produces format analysis reports (JSON + Markdown)
and can apply standard GB/T formatting to unformatted or incorrectly formatted DOCX
files.

## When to Use

- The user asks to **analyze** the formatting of DOCX files in a folder.
- The user wants to **adjust / fix / correct** a DOCX file to match GB/T standard format.
- The user wants to **both analyze and correct** in a single workflow.
- The user wants to compare formatting across multiple national standard files.
- The user wants to generate a format specification from existing DOCX documents.

## Quick Start

### Analyze only
```bash
python .qoder/skills/gbt/scripts/analyze_docx.py --input "D:/Qwork/gbt" --output "D:/Qwork/gbt/output" --verbose
```

### Correct only
```bash
python .qoder/skills/gbt/scripts/format_gbt.py "input.docx" -o "output.docx"
```

### Analyze → Correct → Verify (full workflow)
```bash
# Step 1: Analyze current format
python .qoder/skills/gbt/scripts/analyze_docx.py --single "input.docx" --output "output_analysis" --verbose

# Step 2: Apply GB/T formatting
python .qoder/skills/gbt/scripts/format_gbt.py "input.docx" -o "output.docx"

# Step 3: Verify result
python .qoder/skills/gbt/scripts/analyze_docx.py --single "output.docx" --output "output_verify" --verbose
```

## How to Run

Run the analyzer script against a folder containing DOCX files:

```bash
python .qoder/skills/gbt/scripts/analyze_docx.py --input "D:/Qwork/gbt" --output "D:/Qwork/gbt/output" --verbose
```

### Arguments

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | `.` | Folder containing DOCX files (searched recursively) |
| `--output` | `./output` | Output directory for JSON and Markdown reports |
| `--single` | (none) | Analyze a single DOCX file instead of a folder |
| `--max-runs` | `5` | Max runs to detail per paragraph (controls output size) |
| `--verbose` | off | Print progress to stdout |

### Output

- `output/json/<filename>.json` — Full structured format data per document
- `output/markdown/<filename>.md` — Readable format summary per document
- `output/summary.md` — Cross-document comparison summary

## What It Analyzes

The analyzer extracts these format dimensions from each DOCX:

1. **Page Setup** — page size (EMU + pt), orientation, margins, header/footer
   distance, gutter, inferred paper size (A4/A3/Letter)
2. **Document Defaults** — docDefaults rPr/pPr (default fonts and paragraph
   spacing inherited by all content)
3. **Styles** — all defined styles (name, type, built-in, default flag) plus
   detailed Normal style inspection (fonts, size, spacing)
4. **Fonts** — per run: ascii font, east-Asian font (w:eastAsia, critical for
   Chinese documents), hAnsi, cs, theme references; aggregated font usage
   summary across the document
5. **Font Sizes** — per run size in EMU, pt, and raw half-points (w:sz/w:szCs);
   size distribution histogram
6. **Paragraph Formatting** — alignment, first-line indent, left/right indent,
   space before/after, line spacing and rule
7. **Run Formatting** — bold, italic, underline, strikethrough, color (RGB),
   vertical alignment (superscript/subscript)
8. **Heading Hierarchy** — heading level inferred from numbered text prefix
   (1, 3.1, 4.1.1) combined with zero first-line indent; full outline tree
9. **Tables** — style, dimensions, header row formatting (bold, fonts, size),
   body sample formatting, borders, cell margins
10. **Format Patterns** — heuristic detection of cover block, preface block,
    body block with their characteristic formatting

## Key Technical Notes

- **East-Asian fonts**: python-docx's `run.font.name` returns only the Latin
  (ascii) font. The Chinese font name (e.g. SimSun/HeiTi/KaiTi) is stored in
  the `w:eastAsia` attribute of `w:rFonts` and must be read directly from XML.
- **Encoding**: All output files are written as UTF-8. Console output is ASCII
  only to avoid mojibake on GBK Windows terminals.
- **Heading detection**: GB/T documents do not use Word Heading styles. Heading
  level is inferred from a numeric prefix regex plus zero first-line indent.
- **EMU conversions**: 1 pt = 12700 EMU; font half-points: pt = value / 2.

## Format Correction

The `format_gbt.py` script applies standard GB/T formatting to any DOCX file.
It is designed to fix documents that have lost formatting (e.g. MinerU output,
converted PDFs, or manually authored files with inconsistent styles).

### What It Corrects

| Dimension | Applied Value |
|-----------|--------------|
| Page size | A4 portrait (595×842 pt) |
| Margins | 25mm all sides (left/right/top/bottom) |
| Normal style | 宋体 (SimSun) + Times New Roman, 10.5pt |
| Global spacing | Space before/after = 0pt, single line spacing |
| Cover block | 16pt bold, left aligned (编号→TNR, 标题→黑体, 机构→宋体) |
| 前言 title | 16pt 黑体, CENTER |
| Numbered headings | 10.5pt 宋体+TNR, not bold, JUSTIFY, **two spaces** after number |
| Method headings | 10.5pt 宋体+TNR, not bold, CENTER |
| Appendix headings | 10.5pt 宋体+TNR, not bold, **JUSTIFY** (两端对齐) |
| Body text | 10.5pt 宋体+TNR, JUSTIFY, first-line indent 21pt (2 chars) |
| Table captions | 10.5pt 宋体+TNR, not bold, **CENTER**, merged with title if split |
| Figure captions | 10.5pt 宋体+TNR, not bold, **CENTER** |
| Tables | Centered alignment, Table Grid style, headers **not bold** |
| Images | Centered alignment for all image paragraphs |
| Date merge | Combines "发布" + "实施" lines into one paragraph |
| TOC removal | Auto-detects and removes 目次/目录 between cover and preface |
| Space normalization | Collapses multi-spaces, strips leading/trailing in body text |
| Pre-cover titles | 16pt 宋体 bold, CENTER (GB/T number lines, 一、二、三… sections) |
| Pre-cover body | 10.5pt 宋体+TNR, JUSTIFY, first-line indent 21pt |
| Split heading merge | Merges split headings: '3.1.1' + '白兰地 brandy' → '3.1.1  白兰地 brandy' |
| Appendix title merge | Merges appendix titles: '附录 A' + '培养基和试剂' → '附录 A  培养基和试剂' |

### Paragraph Classification

The script uses **dynamic cover detection** — it scans for "中华人民共和国国家标准"
to locate the cover start, rather than hardcoding indices. This supports documents
with pre-cover content (e.g. amendment notices).

Classification pipeline:
1. `find_cover_start()` — locates cover by scanning for "中华人民共和国国家标准"
2. `merge_date_paragraphs()` — dynamically finds adjacent "发布"/"实施" paragraphs
3. `remove_toc()` — detects and removes 目次/目录 sections before 前言
4. `merge_split_headings()` — merges split headings into single lines:
   - **Appendix titles**: '附录 A' + '培养基和试剂' → '附录 A  培养基和试剂'
   - **Numbered headings**: '3.1.1' + '白兰地 brandy' → '3.1.1  白兰地 brandy'
   - Supports patterns: `\d+.\d+`, `[A-Z].\d+`, etc.
5. `classify_paragraph(text, index, paragraphs, cover_start)` — classifies each paragraph:
   - **Pre-cover title**: GB/T number lines, 一、二、三… sections → 16pt bold, CENTER
   - **Pre-cover body**: Other pre-cover content → 10.5pt, JUSTIFY, 21pt indent
   - **Cover**: 5 paragraphs starting at `cover_start` (after date merge)
   - **前言 title**: At `cover_start + 5` ("前言" or "前 言")
   - **前言 body**: Dynamically extends until first numbered heading or "1  范围"
   - **Body title**: Standard name repeated before chapter 1 (content-based detection)
   - **Numbered**: Headings matching `^\d+(\.\d+)*\s+` (e.g. "1  范围")
   - **第X法**: Method headings (e.g. "第一法 密度瓶法")
   - **附录 X**: Appendix headings
   - **表 X.Y**: Table captions
   - Everything else: Body text

### Script Arguments

| Flag | Description |
|------|-------------|
| `input` (positional) | Input DOCX file path |
| `--output`, `-o` | Output DOCX file path (default: `input`_formatted.docx) |

## GB/T Standard Format Specification

Reference values derived from analyzing multiple official GB/T documents:

- **Body font**: 宋体 (SimSun) + Times New Roman, 10.5pt (五号)
- **Cover font**: 16pt (三号) bold, mixed 宋体/黑体/TNR per element
- **Alignment**: JUSTIFY for body and numbered headings, CENTER for preface/
  method titles and table/figure captions, **JUSTIFY for appendix titles**, LEFT for cover
- **First-line indent**: 21pt (exactly 2 characters at 10.5pt) for body text;
  0pt for headings, cover, preface
- **Heading numbering**: No Word heading styles; levels inferred from numeric
  prefix. Number followed by **two spaces** before text.
- **Spacing**: 0pt before/after all paragraphs; single line spacing (1.0×)
- **Tables**: Centered alignment, Table Grid style; headers **not bold**
- **Table captions**: CENTER aligned, not bold, auto-merged if split across lines
- **Figure captions**: CENTER aligned, not bold
- **Images**: All image paragraphs centered
- **Body spaces**: Multi-spaces collapsed, leading/trailing stripped;
  heading two-space separators preserved
- **TOC**: Auto-removed if present between cover and preface
- **Split headings**: Auto-merged when number is on one line and text on next
  (e.g. '3.1.1' + '白兰地 brandy' → '3.1.1  白兰地 brandy')
- **Appendix titles**: Merged into single line with double-space separator
  (e.g. '附录 A' + '培养基和试剂' → '附录 A  培养基和试剂')
- **Pre-cover titles**: 16pt 宋体 bold, CENTER (GB/T number lines, 一、二、三…)
- **Pre-cover body**: 10.5pt 宋体+TNR, JUSTIFY, 21pt indent

## Dependencies

- Python 3.8+
- python-docx (>= 1.0)
- lxml (>= 4.0)

Both are typically pre-installed in the Qoder environment.

## Interpreting Results

- Check `fonts_summary` in JSON for the set of fonts actually used (vs. the
  default declared in styles which may be overridden at run level).
- The `headings_outline` gives the document structure even without Word styles.
- The `format_patterns` section identifies cover/preface/body conventions.
- Use `summary.md` to compare formatting across all files at a glance.

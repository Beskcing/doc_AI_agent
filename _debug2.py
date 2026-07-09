"""Debug body_title classification"""

import re

from src.tools.formatters.gbt_1_1 import GbtDocxFormatter

fmt = GbtDocxFormatter()
orig_classify = fmt._classify_paragraph
orig_is_std = fmt._is_standard_name_line


def debug_is_std(text, index, paragraphs):
    result = orig_is_std(text, index, paragraphs)
    if index == 28:
        for j in range(index + 1, min(index + 5, len(paragraphs))):
            nt = paragraphs[j].text.strip()
            if nt:
                m = re.match(r"^\d+\s{2,}[\u4e00-\u9fff]", nt)
                print(f"  _is_std_name_line: para[{j}]={repr(nt[:30])} regex={bool(m)} result={result}")
                break
    return result


fmt._is_standard_name_line = debug_is_std


def debug_classify(text, index, paragraphs, cover_start=0):
    if index == 28:
        ts = text.strip()
        endswith_period = ts.endswith("\u3002")
        endswith_semi = ts.endswith("\uff1b")
        print(f"  text={repr(ts[:40])}")
        print(f"  len<30: {len(ts) < 30}")
        print(f"  endswith_period: {endswith_period}")
        print(f"  endswith_semi: {endswith_semi}")
        print(f"  is_numbered: {fmt._is_numbered_heading(ts)}")
        print(f"  is_method: {fmt._is_method_heading(ts)}")
        print(f"  is_appendix: {fmt._is_appendix_heading(ts)}")
        print(f"  re_match_1s: {bool(re.match(r'^1\s+\S', ts))}")
    cls = orig_classify(text, index, paragraphs, cover_start)
    if index == 28:
        print(f"  FINAL cls={cls}")
    return cls


fmt._classify_paragraph = debug_classify

result = fmt.process(
    "data/output/e91a5193-1962-4bbe-809e-68034b1c7ec3/full.docx",
    "data/output/e91a5193-1962-4bbe-809e-68034b1c7ec3/formatted_d2.docx",
)
print("Stats:", fmt._stats)

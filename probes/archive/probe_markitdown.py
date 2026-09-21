"""Does markitdown fix the corrupted-CID-font problem that PyMuPDF hit?

markitdown uses pdfminer.six/pdfplumber; PyMuPDF uses its own parser. If BOTH
produce the same garbage, the fault is the PDF's missing ToUnicode CMap, no
text-layer extractor can fix it, and OCR becomes mandatory — that is a parse-layer
architecture decision, not a tooling preference.

Second question, equally load-bearing: does markitdown preserve PAGE boundaries?
Citation needs them. If the converter returns one flat string, it cannot be the
only parser for documents we intend to cite.

Only non-personal documents are used; metrics are aggregate codepoint counts, not
content.
"""
import os
import re
import time

import pymupdf
from markitdown import MarkItDown

DL = os.path.join(os.path.expanduser("~"), "Downloads")
CASES = [
    ("中国能源统计年鉴_胡汉舟_总编_四、能源消费.pdf", "was 23.6% junk under PyMuPDF"),
    ("地方政府税收竞争对区域绿色发展的影响_杨刻霞.pdf", "was 1.5% junk, on content words"),
    ("1_2023年度企业政策汇编 -最新.pdf", "pure scan, 0 chars/page"),
    ("中国省域绿色发展的空间格局及其演变特征_王勇.pdf", "control: expected clean"),
]


def census(s):
    ns = [c for c in s if not c.isspace()]
    pua = sum(1 for c in ns if 0xE000 <= ord(c) <= 0xF8FF)
    exta = sum(1 for c in ns if 0x3400 <= ord(c) <= 0x4DBF)
    repl = sum(1 for c in ns if ord(c) == 0xFFFD)
    return len(ns), pua, exta, repl


md = MarkItDown()
print(f"{'document':30} {'engine':10} {'chars':>8} {'junk%':>7} {'sec':>6}  pages?")
print("-" * 78)

for name, note in CASES:
    path = os.path.join(DL, name)
    if not os.path.exists(path):
        print(f"{name[:30]:30} MISSING")
        continue
    short = re.sub(r"\.pdf$", "", name)[:28]

    try:
        doc = pymupdf.open(path)
        npages = doc.page_count
        t0 = time.time()
        mu_text = "".join(p.get_text() for p in doc)
        mu_t = time.time() - t0
        doc.close()
        n, pua, exta, repl = census(mu_text)
        pct = 100 * (pua + exta + repl) / max(n, 1)
        print(f"{short:30} {'pymupdf':10} {n:8} {pct:6.2f}% {mu_t:6.2f}  n/a ({npages}p)")
    except Exception as e:
        print(f"{short:30} {'pymupdf':10} ERROR {type(e).__name__}")

    try:
        t0 = time.time()
        out = md.convert(path).text_content
        mi_t = time.time() - t0
        n, pua, exta, repl = census(out)
        pct = 100 * (pua + exta + repl) / max(n, 1)
        # does the output carry any page delimiter markitdown could cite by?
        page_marks = len(re.findall(r"(?mi)^#+\s*page\s*\d+|\x0c|<!--\s*page", out))
        print(f"{'':30} {'markitdown':10} {n:8} {pct:6.2f}% {mi_t:6.2f}  {page_marks} marks")
    except Exception as e:
        print(f"{'':30} {'markitdown':10} ERROR {type(e).__name__}: {str(e)[:40]}")
    print(f"{'':30} note: {note}")

print("-" * 78)
print("junk% = PUA + CJK-Ext-A + U+FFFD share of non-space chars")

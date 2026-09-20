"""Did markitdown really FIX the CID mapping, or just dodge my junk detector?

0% PUA/Ext-A is not proof of correctness — characters can map to valid-but-wrong
codepoints, which no codepoint-range census can catch. The only honest test is to
look for words that must appear in this document, and for the specific glyphs
PyMuPDF was known to produce.
"""
import os

import pymupdf
from markitdown import MarkItDown

PATH = os.path.join(
    os.path.expanduser("~"), "Downloads",
    "地方政府税收竞争对区域绿色发展的影响_杨刻霞.pdf",
)

EXPECT = ["政策", "税收", "竞争", "区域", "绿色", "发展", "政府", "影响", "环境"]
KNOWN_BAD = ["䎟", "䎚", "䈓", "䍚"]  # PyMuPDF's mis-maps for 政 争 域 展

doc = pymupdf.open(PATH)
mu = "".join(p.get_text() for p in doc)
doc.close()
mi = MarkItDown().convert(PATH).text_content

print(f"{'token':10} {'pymupdf':>9} {'markitdown':>11}")
print("-" * 34)
for w in EXPECT:
    print(f"{w:10} {mu.count(w):9} {mi.count(w):11}")
print("-" * 34)
print("known mis-mapped glyphs (0 = recovered):")
for w in KNOWN_BAD:
    print(f"{w:10} {mu.count(w):9} {mi.count(w):11}")

print("\n--- pymupdf, first 220 non-space chars ---")
print("".join(mu.split())[:220])
print("\n--- markitdown, first 220 non-space chars ---")
print("".join(mi.split())[:220])

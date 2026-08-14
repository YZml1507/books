"""Plato Republic: find the 10 BOOK headings and verify structure.

Goal: confirm that the only addressable structure is BOOK I-X (10 books),
with NO Stephanus pagination (measured: 0 occurrences of 'Stephanus' or
'\d{2,3}[a-e]' in any format).

If confirmed, Plato gets a one-level address: scheme='plato_book',
addr1=book_number (1-10), addr2=NULL.
"""
import re
from pathlib import Path

t = (Path("data/raw_ext/generality") / "plato-republic" / "pg1497.txt").read_text(encoding="utf-8", errors="replace")
m = re.search(r"\*\*\* START.*?\*\*\*", t, re.S)
body = t[m.end():]
m2 = re.search(r"\*\*\* END", body)
body = body[:m2.start()]

# Find all BOOK headings on their own line
bk = list(re.finditer(r"(?m)^\s*BOOK\s+([IVX]+)\.?\s*$", body))
print(f"BOOK own-line headings: {len(bk)}")
for i, b in enumerate(bk):
    # Show context: what's the heading and what follows
    print(f"  [{i}] @{b.start()} BOOK {b.group(1)}")

# Check: are there 10 distinct books?
nums = sorted(set(b.group(1) for b in bk), key=lambda s: {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,"X":10}[s])
print(f"distinct BOOK numerals: {nums}")

# Also check for CONTENTS / TOC
toc = re.search(r"(?m)^\s*CONTENTS\s*$", body, re.I)
print(f"TOC 'CONTENTS' own-line: {bool(toc)}")

# And the Jowett analysis / introduction
intro = re.search(r"(?m)^\s*INTRODUCTION\s*$", body, re.I)
print(f"'INTRODUCTION' own-line: {bool(intro)}")

# Confirm zero Stephanus
st = len(re.findall(r"[Ss]tephanus", body))
nnna = len(re.findall(r"\b\d{2,3}\s?[a-e]\b", body))
print(f"'Stephanus' in body: {st}; NNNa-e in body: {nnna}")

# Also in html
h = (Path("data/raw_ext/generality") / "plato-republic" / "pg1497.html").read_text(encoding="utf-8", errors="replace")
st_h = len(re.findall(r"[Ss]tephanus", h))
nnna_h = len(re.findall(r"\b\d{2,3}\s?[a-e]\b", h))
print(f"HTML 'Stephanus': {st_h}; HTML NNNa-e: {nnna_h}")

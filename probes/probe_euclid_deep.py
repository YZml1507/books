"""Euclid Elements: deep recon of html structure.

Measured (probe_tier23_deep.py):
  html chars=1,825,013
  PROP. (any): 202   (roman numerals, I-VI books × propositions)
  Cor. (corollary): 154
  BOOK I: 1 occurrence
  D[EÉ]FINITION: 67
  <img: 638   (diagrams)
  epub parts: 18

Goal: determine the real proposition structure.
Is it 202 = sum of propositions across 6 books?
Canonical: Euclid Elements I-VI has 48+14+37+16+25+33 = 173 propositions.
202 - 173 = 29 extra. Maybe Cor. counted, or TOC entries.

Let's extract all PROP. markers with their roman numerals and see the distribution.
"""
import re
from pathlib import Path

h = (Path("data/raw_ext/generality") / "euclid-elements" / "pg21076.html").read_text(encoding="utf-8", errors="replace")
print(f"html chars: {len(h)}")

# Strip tags but keep text
t = re.sub(r"<[^>]+>", " ", h)
t = re.sub(r"&[a-zA-Z#0-9]+;", " ", t)
t = re.sub(r"\s+", " ", t).strip()
print(f"stripped text chars: {len(t)}")

# All PROP. with roman numerals
props = re.findall(r"PROP\.\s*([IVXLC]+)\.?", t)
print(f"\nPROP. roman numerals: {len(props)}")
from collections import Counter
pc = Counter(props)
print("distribution by roman numeral:")
for rom in sorted(pc.keys(), key=lambda s: {"I":1,"II":2,"III":3,"IV":4,"V":5,"VI":6,"VII":7,"VIII":8,"IX":9,"X":10,"XI":11,"XII":12,"XIII":13,"XIV":14,"XV":15,"XVI":16,"XVII":17,"XVIII":18,"XIX":19,"XX":20,"XXI":21,"XXII":22,"XXIII":23,"XXIV":24,"XXV":25,"XXVI":26,"XXVII":27,"XXVIII":28,"XXIX":29,"XXX":30,"XXXI":31,"XXXII":32,"XXXIII":33,"XXXIV":34,"XXXV":35,"XXXVI":36,"XXXVII":37,"XXXVIII":38,"XXXIX":39,"XL":40,"XLI":41,"XLII":42,"XLIII":43,"XLIV":44,"XLV":45,"XLVI":46,"XLVII":47,"XLVIII":48}.get(s, 999)):
    print(f"  {rom:>6}: {pc[rom]}")

# Also check "PROPOSITION" spelled out
prop_full = re.findall(r"PROPOSITION\s+([IVXLC]+)", t)
print(f"\nPROPOSITION roman: {len(prop_full)}")
pc2 = Counter(prop_full)
for rom, n in sorted(pc2.items()):
    print(f"  {rom}: {n}")

# Check BOOK headings
books = re.findall(r"BOOK\s+([IVXLC]+)", t)
print(f"\nBOOK roman: {len(books)}")
pc3 = Counter(books)
for rom, n in sorted(pc3.items()):
    print(f"  {rom}: {n}")

# Find the actual structure: each book has PROPOSITION I, II, III, ... up to some max
# Let's look at the first 5000 chars of stripped text
print(f"\n=== first 2000 chars of stripped text ===")
print(t[:2000])

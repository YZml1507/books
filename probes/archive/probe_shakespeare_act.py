"""Shakespeare: why 76 ACT I own-line for ~38 plays?
Check if each ACT I appears twice (TOC + body), or if plays repeat.
"""
import re
from pathlib import Path

t = (Path("data/raw_ext/generality") / "shakespeare" / "pg100.txt").read_text(encoding="utf-8", errors="replace")
m = re.search(r"\*\*\* START.*?\*\*\*", t, re.S)
b0 = m.end()
m2 = re.search(r"\*\*\* END", t)
b = t[b0:m2.start()]

# All ACT I own-line positions
acts_i = list(re.finditer(r"(?m)^\s*ACT\s+I\.?\s*$", b))
print(f"ACT I own-line: {len(acts_i)}")
for i, a in enumerate(acts_i):
    pos = a.start() + b0
    # look 200 chars back for a play title
    chunk = b[max(0, a.start()-800):a.start()]
    caps = re.findall(r"(?m)^\s*([A-Z][A-Z\s,'\-—.]{4,60})\s*$", chunk)
    last_cap = caps[-1].strip() if caps else "?"
    print(f"  [{i:<3}] @{pos:<8} prev_cap={last_cap[:50]!r}")

# Also: how many ACT (any roman) own-line total?
all_acts = list(re.finditer(r"(?m)^\s*ACT\s+[IVXL]+\.?\s*$", b))
print(f"\nALL ACT own-line: {len(all_acts)}")
# Count ACT V (only plays with 5 acts)
acts_v = list(re.finditer(r"(?m)^\s*ACT\s+V\.?\s*$", b))
print(f"ACT V own-line: {len(acts_v)}")

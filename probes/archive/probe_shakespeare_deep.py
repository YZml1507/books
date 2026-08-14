"""Closer look at Shakespeare structure.

Find: play titles, ACT/SCENE within each play, poems with no act/scene.
"""
import re
from pathlib import Path

ROOT = Path("data/raw_ext/generality")
t = (ROOT / "shakespeare" / "pg100.txt").read_text(encoding="utf-8", errors="replace")

# body
m = re.search(r"\*\*\* START.*?\*\*\*", t, re.S)
b0 = m.end()
m2 = re.search(r"\*\*\* END", t)
b1 = m2.start()
b = t[b0:b1]

# Find TOC
lines = b.splitlines()
toc0 = next((i for i, l in enumerate(lines[:200]) if l.strip().lower() in ("contents", "contents.")), -1)
print(f"TOC line={toc0}")

# Print TOC entries
toc_entries = []
for i, l in enumerate(lines[toc0+1:toc0+400]):
    s = l.rstrip()
    if not s:
        continue
    toc_entries.append((i + toc0 + 1, s))
    if len(toc_entries) >= 60:
        break

print("=== TOC entries (first 60 non-blank) ===")
for ln, s in toc_entries:
    print(f"  L{ln:<5} {s!r}")

# Now find all ACT/SCENE in body and print first few with context
print("\n=== First 10 ACT lines with context ===")
acts = list(re.finditer(r"(?m)^(\s*ACT\s+[IVXL]+\.?)\s*$", b))
for a in acts[:10]:
    print(f"  @{a.start()+b0} {a.group(0)!r}")

print("\n=== First 10 SCENE lines with context ===")
scenes = list(re.finditer(r"(?m)^(\s*SCENE\s+[IVXL]+\.?\s*.*)$", b))
for s in scenes[:10]:
    print(f"  @{s.start()+b0} {s.group(0)[:80]!r}")

# What's between TOC end and first ACT? Find play titles
# Play titles are often ALL CAPS on their own line, or title case
# Let's look for the pattern: title line, then ACT/SCENE
# First, find where TOC ends (first play title after TOC)
# The TOC entries are indented with spaces; let's look at what follows

# Count: how many distinct plays have ACT I?
acts_i = re.findall(r"(?m)^\s*ACT\s+I\.?\s*$", b)
print(f"\nACT I (own line): {len(acts_i)}")

# Print lines around first few ACT I to find play titles
print("\n=== Context before each ACT I (first 5) ===")
acts_i_matches = list(re.finditer(r"(?m)^\s*ACT\s+I\.?\s*$", b))
for a in acts_i_matches[:5]:
    start = max(0, a.start() - 500)
    chunk = b[start:a.start()]
    # last ALL-CAPS line before ACT I
    caps = re.findall(r"(?m)^\s*([A-Z][A-Z\s,'\-—.]{4,60})\s*$", chunk)
    print(f"  @{a.start()+b0}: last ALL-CAPS before = {caps[-1] if caps else 'NONE'!r}")

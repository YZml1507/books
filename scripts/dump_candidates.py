"""Print fold candidates from the diagnosis run as ready-to-paste dict entries.

Kept as a file rather than an inline -c because these are machine-PROPOSED pairs, not
approved ones: they still need a human to reject genuine word differences (the run
proposed 億->意, which are different words, not orthographic variants).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
path = os.path.join(ROOT, "data", "catalog", "yao_diagnosis.json")
d = json.load(open(path, encoding="utf-8"))

fc = d.get("fold_candidates") or d.get("variant_candidates") or {}
print(f"total {len(fc)} candidate pairs\n")
entries = []
for key, n in sorted(fc.items(), key=lambda kv: -kv[1]):
    a, b = key.split("->")
    entries.append((a, b, n))

print("# by attestation count")
for a, b, n in entries[:40]:
    print(f'    "{a}": "{b}",   # U+{ord(a):04X} -> U+{ord(b):04X}  x{n}')

print(f"\n# compact, all {len(entries)}")
flat = [f'"{a}": "{b}",' for a, b, _ in entries]
for i in range(0, len(flat), 6):
    print("    " + " ".join(flat[i:i + 6]))

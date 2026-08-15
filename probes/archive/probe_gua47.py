"""P-01: is KR1a0006 卦47 上六 a SECOND OCR-damaged region, or something else?

It surfaced only after D-020 fixed the address window: it had been classified
`span-overextended-A` (contiguity 0.337) and became `text-damage` (contiguity 0.199,
lenA 845 / lenB 462). The verdict is a threshold call at 0.25, so it must not be reported as
damage on the strength of the label alone.

The discriminator is the one D-012 established for 卦61: OCR damage substitutes
VISUALLY SIMILAR characters throughout, so the two witnesses disagree in scattered small ways
while remaining recognisably the same passage. A span that merely covers more ground shows one
long common run plus a tail.

Printed side by side below, with the per-character disagreements listed, so the call is made
on the text rather than on the number.
"""
from __future__ import annotations

import difflib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.quality import addresses_of  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
bodies = {w: work_body(RAW, w) for w in ("KR1a0001", "KR1a0006", "KR1a0007")}
pol = derive_polarity(bodies)
ta = addresses_of(bodies["KR1a0006"], pol)
tb = addresses_of(bodies["KR1a0007"], pol)

for key in [(47, "上六"), (61, "上九")]:
    a, b = ta.get(key), tb.get(key)
    print("=" * 78)
    print(f"卦{key[0]} {key[1]}   KR1a0006 len={len(a or '')}   KR1a0007 len={len(b or '')}")
    print("=" * 78)
    if not a or not b:
        print("  missing in one witness")
        continue
    print(f"\n  [KR1a0006] {a[:220]}")
    print(f"\n  [KR1a0007] {b[:220]}")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    blocks = [bl for bl in sm.get_matching_blocks() if bl.size]
    print(f"\n  matching blocks: {len(blocks)}   longest={max(bl.size for bl in blocks)}"
          f"   covered={sum(bl.size for bl in blocks)}/{len(a)}")
    subs = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1) and (i2 - i1) <= 3:
            for k in range(i2 - i1):
                if a[i1 + k] != b[j1 + k]:
                    subs.append((a[i1 + k], b[j1 + k]))
    print(f"  1-3 char substitutions (the OCR signature): {len(subs)}")
    print(f"    {subs[:24]}")
    big = [(tag, i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes()
           if tag != "equal" and max(i2 - i1, j2 - j1) > 20]
    print(f"  large non-equal runs (>20 chars): {len(big)}  {big[:6]}")

print("""
=== how to read this ===
卦61 is the known-positive control: many scattered 1-char substitutions of visually similar
characters (青/音, 輪/翰, 届/居, 筆/華) and no single long common run.
If 卦47 instead shows FEW substitutions and one or two LARGE runs, then its low contiguity
comes from one witness carrying extra material — not from damage — and calling it
`text-damage` is a threshold artefact that should be recorded as such.
""")

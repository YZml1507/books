"""Split the `outside` bucket: 十翼 cross-references vs 卦變 diagram entries.

`gua_spans()` returns every symbol not on the LIS chain in one bucket. Two very different
things are in there:
  * 十翼 (繫辭/說卦/序卦/雜卦) cite hexagrams out of order in running prose.
  * 朱熹's 卦變圖 in KR1a0031/0032 is a TABLE — 124-ish symbols, and the earlier probe
    showed entries as short as 2 raw chars (`䷂屯` alone). These express 卦↔卦 transformation
    relations and are a distinct unit type, not noise.

Distinguishing signal to test: diagram entries should be very short and densely packed;
十翼 references should sit inside long prose runs.
"""
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORKS = ["KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]

for w in WORKS:
    raw = work_body(RAW, w)
    spans, outside = gua_spans(raw)
    marks = [(m.start(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    kept_pos = {s.start for s in spans}
    off = [(p, g) for p, g in marks if p not in kept_pos]

    print(f"\n{'='*72}\n{w}: {len(spans)} spans on chain, {len(off)} off chain")
    if not off:
        continue

    # gap to the next symbol, whichever chain it is on
    all_pos = sorted(p for p, _ in marks)
    gaps = []
    for p, g in off:
        i = all_pos.index(p)
        nxt = all_pos[i + 1] if i + 1 < len(all_pos) else len(raw)
        gaps.append((nxt - p, p, g))
    gaps.sort()
    short = [x for x in gaps if x[0] <= 12]
    long_ = [x for x in gaps if x[0] > 12]
    print(f"  gap<=12 chars (table-like): {len(short)}")
    print(f"  gap >12 chars (prose-like): {len(long_)}")
    if gaps:
        print(f"  gap median={gaps[len(gaps)//2][0]}  min={gaps[0][0]}  max={gaps[-1][0]}")

    for label, group in (("TABLE-LIKE", short[:6]), ("PROSE-LIKE", long_[:6])):
        if not group:
            continue
        print(f"  --- {label} samples ---")
        for gap, p, g in group:
            txt = clean(raw[p:p + min(gap + 30, 70)], keep_notes=True).text
            print(f"    卦{g:2} gap={gap:5}  {txt[:46]!r}")

    # do the off-chain symbols cluster positionally?
    n = len(raw)
    dec = Counter(min(9, p * 10 // n) for p, _ in off)
    print("  decile spread: " + " ".join(f"d{d}={dec.get(d,0)}" for d in range(10)))

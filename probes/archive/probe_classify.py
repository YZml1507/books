"""Does classify_offchain() actually separate 圖 from 十翼?

Expected from the measured layout: KR1a0031/0032 should be almost entirely 圖 (the 卦變
table at the front); KR1a0006/0007/0016 almost entirely 十翼 (prose citations at the back).
If the density threshold is right, the split should be near-total in both directions.
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans  # noqa: E402
from guji.anchors import classify_offchain  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")

print(f"{'work':10} {'onchain':>8} {'圖':>5} {'正文':>5} {'十翼':>5}  "
      f"{'卦 total':>9}  lost 卦")
print("-" * 68)
for w in ("KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"):
    raw = work_body(RAW, w)
    spans, _ = gua_spans(raw)
    cls = classify_offchain(raw)
    c = Counter(cls.values())
    on = {s.number for s in spans}
    # which 卦 exist only as off-chain 正文, i.e. are missing from the index entirely?
    from guji.anchors import gua_number
    offbody = {gua_number(raw[p]) for p, k in cls.items() if k == "正文"}
    lost = sorted(offbody - on)
    print(f"{w:10} {len(spans):8} {c.get('圖',0):5} {c.get('正文',0):5} "
          f"{c.get('十翼',0):5} {len(on | offbody):9}  {lost}")

print("\n=== samples per class ===")
for w in ("KR1a0031", "KR1a0006"):
    raw = work_body(RAW, w)
    cls = classify_offchain(raw)
    print(f"\n{w}:")
    shown = {"圖": 0, "正文": 0, "十翼": 0}
    for p in sorted(cls):
        k = cls[p]
        if shown[k] >= 3:
            continue
        shown[k] += 1
        txt = clean(raw[p:p + 60], keep_notes=True).text
        print(f"  [{k}] @{p:7} {txt[:44]!r}")

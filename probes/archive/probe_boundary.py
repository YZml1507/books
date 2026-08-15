"""What character actually sits at the 九三 address boundary in KR1a0006?

Units open with 「三君子終…」 rather than 「九三君子終…」, so the boundary is one character
past the label start. Measure it instead of reasoning about the coordinate systems.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
bodies = {w: work_body(RAW, w) for w in ("KR1a0001", "KR1a0006")}
pol = derive_polarity(bodies)

raw = bodies["KR1a0006"]
spans, _ = gua_spans(raw)
s = next(x for x in spans if x.number == 1)
seg = raw[s.start:s.end]
view = clean(seg, keep_notes=False)
hits = extract_yao(seg, yao_names(pol[1]), jing=view)

print(f"span {s.start}..{s.end}   cleaned 經 len={len(view.text)}")
print(f"cleaned head: {view.text[:60]}")
print()
for label in ("初九", "九二", "九三", "九四"):
    rng = hits.get(label)
    if not rng:
        print(f"{label}: not located")
        continue
    ci = rng[0]
    a = view.origin(ci)
    print(f"{label}: cleaned_idx={ci} cleaned[{ci}:{ci+6}]={view.text[ci:ci+6]!r}")
    print(f"        origin={a}  seg[{a}:{a+8}]={seg[a:a+8]!r}")
    print(f"        offsets[{ci}]={view.offsets[ci]} offsets[{ci+1}]={view.offsets[ci+1]}")
    probe = seg.rfind(label, max(0, a - 6), a + len(label))
    print(f"        rfind({label!r}, {max(0,a-6)}, {a+len(label)}) -> {probe}")
    if probe >= 0:
        print(f"        seg[{probe}:{probe+8}]={seg[probe:probe+8]!r}")

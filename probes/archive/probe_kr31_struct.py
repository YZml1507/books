"""Where do KR1a0031's 爻 spans come from? The diff probe showed 0031's extracted
爻辭 spans are far SHORTER than 0032's (e.g. 卦32 上六 -> just 振怕凶, 3 chars, even
though it is the last 爻 of the 卦 and should run to the next 卦 symbol).

That smells structural, not orthographic. Dump the raw neighbourhood.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import gua_spans  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")


def files(work):
    import glob
    return sorted(glob.glob(os.path.join(RAW, work, "*.txt")))


for w in ("KR1a0031", "KR1a0032"):
    print("=" * 78)
    print(w)
    print("=" * 78)
    for p in files(w):
        txt = open(p, encoding="utf-8").read()
        head = re.sub(r"\s+", " ", txt[:220])
        syms = [gua_number(m.group()) for m in HEX_RE.finditer(txt)]
        print(f"  {os.path.basename(p):22} {len(txt):7} chars  syms={len(syms):4} "
              f"{syms[:8]}{'...' if len(syms) > 8 else ''}")
        print(f"     head: {head[:180]}")
    print()

# ---- where does 卦32 live in each edition, and how long is its span? ----
print("=" * 78)
print("span lengths per 卦, 0031 vs 0032")
print("=" * 78)
bodies = {w: work_body(RAW, w) for w in ("KR1a0031", "KR1a0032")}
sp = {}
for w, raw in bodies.items():
    spans, outside = gua_spans(raw)
    sp[w] = {s.number: s for s in spans}
print(f"{'卦':>4} {'0031 len':>9} {'0032 len':>9}  ratio")
for g in range(1, 65):
    a = sp["KR1a0031"].get(g)
    b = sp["KR1a0032"].get(g)
    la = (a.end - a.start) if a else 0
    lb = (b.end - b.start) if b else 0
    flag = ""
    if lb and la and la / lb < 0.5:
        flag = "  <== 0031 span much shorter"
    if not la:
        flag = "  <== 0031 MISSING"
    print(f"{g:>4} {la:>9} {lb:>9}  {la/lb if lb else 0:5.2f}{flag}")

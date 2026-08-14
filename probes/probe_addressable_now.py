"""Can EXISTING code address the works currently stored with scheme=NULL?

Correcting my own claim: I said 40.2% of the index "has no validation path" and implied new
acquisitions might be needed. Q2 of probe_internal_witness.py falsified that — all 22 works
carry >=20 distinct 卦 names, and two carry Unicode hexagram symbols. So the question is not
"fetch more" but "does our current machinery already reach them".

Test it directly rather than argue: run the real gua_spans() over each and see what happens.
KR3g0030 京氏易傳 has 62 symbols with 60 distinct, which is close to a full King Wen chain, so
if the existing LIS segmentation works anywhere outside 易類 it should work there.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import HEX_RE, clean, extract_yao, gua_number, gua_spans, yao_names  # noqa: E402
from guji.ingest import derive_gua_names  # noqa: E402
from guji.variants import fold  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ZY = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ZY}
pol = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], pol)
NAMES = derive_gua_names(bodies["KR1a0001"])

CAND = ["KR3g0030", "KR3g0015", "KR3g0029", "KR1a0030", "KR1a0003", "KR3g0018"]

print("=" * 78)
print("A — existing gua_spans() applied unchanged to non-易類 works")
print("=" * 78)
print(f"{'work':10} {'symbols':>8} {'LIS spans':>10} {'distinct 卦':>12} {'off-chain':>10}")
print("-" * 78)
for w in CAND:
    raw = work_body(RAW, w)
    syms = [gua_number(m.group()) for m in HEX_RE.finditer(raw)]
    if not syms:
        print(f"{w:10} {0:>8} {'-':>10} {'-':>12} {'-':>10}   (no symbols; name-based only)")
        continue
    spans, off = gua_spans(raw)
    print(f"{w:10} {len(syms):>8} {len(spans):>10} {len({s.number for s in spans}):>12} "
          f"{len(off):>10}")

print("\n" + "=" * 78)
print("B — KR3g0030 京氏易傳: does a span actually contain that 卦's material?")
print("=" * 78)
raw = work_body(RAW, "KR3g0030")
spans, off = gua_spans(raw)
ok = bad = 0
for s in spans[:14]:
    seg = clean(raw[s.start:s.end], keep_notes=True).text
    nm = NAMES.get(s.number, "")
    present = nm and nm in seg[:40]
    ok += bool(present)
    bad += (not present)
    print(f"  卦{s.number:2} {nm or '?':4} anchor={s.page_anchor or '-':28} "
          f"name_in_head={bool(present)}  {seg[:34]}")
print(f"\n  first 14 spans: name found in span head {ok}, not found {bad}")

print("\n" + "=" * 78)
print("C — name-based 卦 addressing for works WITHOUT symbols")
print("=" * 78)
# 焦氏易林 is organised as 卦-per-section: each 卦 name heads a block of rhymed text.
# Test whether names appear in King Wen order often enough for an LIS chain.
for w in ("KR3g0029", "KR3g0018", "KR1a0030"):
    body = re.sub(r"<pb:[^>]+>|[¶\s　]", "", fold(work_body(RAW, w)))
    seq = []
    for m in re.finditer("|".join(re.escape(n) for n in NAMES.values() if n), body):
        g = next((k for k, v in NAMES.items() if v == m.group()), None)
        if g:
            seq.append(g)
    # how long is the longest increasing run, as a crude orderedness signal?
    from guji.anchors import _longest_increasing
    lis = _longest_increasing(seq) if seq else []
    print(f"  {w:10} name occurrences {len(seq):6}  LIS length {len(lis):5}  "
          f"ordered-ness {100.0*len(lis)/max(len(seq),1):5.1f}%")

print("\n" + "=" * 78)
print("D — the 31 verbatim 爻辭 quotations: are they usable as witnesses?")
print("=" * 78)


def cl(s):
    return re.sub(r"<pb:[^>]+>|[¶\s　/()（）「」『』《》，。、：；？！·○]", "", fold(s))


probes = [(g, lb, cl(t)[:10]) for g, e in gold.items() for lb, t in e.items()
          if len(cl(t)) >= 6]
for w in ["KR3g0030", "KR3g0031", "KR3g0042", "KR1a0030"]:
    body = cl(work_body(RAW, w))
    found = [(g, lb, t) for g, lb, t in probes if t in body]
    print(f"\n  {w}: {len(found)} quotations")
    for g, lb, t in found[:3]:
        at = body.find(t)
        print(f"    卦{g}{lb}  …{body[max(0,at-18):at+len(t)+8]}…")

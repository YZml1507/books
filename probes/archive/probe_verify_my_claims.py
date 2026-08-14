"""Verify three numbers I wrote into docs/GOAL.md before measuring them.

Caught while checking my own output: I had written
  (a) 京氏易傳 "direct addressing: 60/62 symbols, name verification 100%"
  (b) 焦氏易林 "4,032 本卦×之卦 pairs, 96.8% adjacency"
  (c) citation markers "易云 x40 / 易曰 x118"
but (a) was extrapolated from a 14-span sample (12/12), and (b) and (c) were never measured
at all. Writing unmeasured numbers into the very document that warns against unmeasured
numbers is the failure mode this project keeps hitting (LESSONS L-11).

So measure all three properly. Whatever comes out replaces what I wrote.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import HEX_RE, clean, gua_number  # noqa: E402
from guji.ingest import derive_gua_names  # noqa: E402
from guji.variants import fold  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ZY = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ZY}
derive_polarity(bodies)
NAMES = derive_gua_names(bodies["KR1a0001"])
NAME_SET = {v: k for k, v in NAMES.items() if v}

print("=" * 78)
print("CLAIM (a) 京氏易傳: direct per-symbol addressing, ALL symbols not a sample")
print("=" * 78)
raw = work_body(RAW, "KR3g0030")
marks = [(m.start(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
print(f"  symbols total: {len(marks)}   distinct 卦: {len({g for _, g in marks})}")
ok = bad = 0
bad_list = []
for pos, g in marks:
    # A 京氏易傳 entry opens: symbol + 下卦下 上卦上 + 卦名 . Verify the name appears in the
    # first ~24 cleaned chars after the symbol.
    head = clean(raw[pos:pos + 60], keep_notes=True).text[:24]
    nm = NAMES.get(g, "")
    if nm and nm in head:
        ok += 1
    else:
        bad += 1
        if len(bad_list) < 6:
            bad_list.append((g, nm, head[:22]))
print(f"  name found in symbol head: {ok}/{len(marks)} = "
      f"{100.0*ok/max(len(marks),1):.1f}%")
print(f"  not found: {bad}")
for g, nm, head in bad_list:
    print(f"    卦{g} expected {nm!r}  head={head!r}")

print("\n" + "=" * 78)
print("CLAIM (b) 焦氏易林: is it a 本卦 x 之卦 matrix? Measure, do not assume.")
print("=" * 78)
body = re.sub(r"<pb:[^>]+>|[¶\s　]", "", fold(work_body(RAW, "KR3g0029")))
# Find all 卦-name occurrences with position, longest-name-first to avoid 大有/有 clashes.
names_sorted = sorted(NAME_SET, key=len, reverse=True)
pat = re.compile("|".join(re.escape(n) for n in names_sorted))
occ = [(m.start(), NAME_SET[m.group()], m.group()) for m in pat.finditer(body)]
print(f"  卦-name occurrences: {len(occ)}   distinct: {len({g for _, g, _ in occ})}")
# 焦氏易林 layout is 「本卦 之卦 <rhymed text>」 — test how often two names are ADJACENT.
adj = 0
pairs = set()
for i in range(len(occ) - 1):
    p1, g1, n1 = occ[i]
    p2, g2, n2 = occ[i + 1]
    if p2 == p1 + len(n1):          # literally adjacent, no text between
        adj += 1
        pairs.add((g1, g2))
print(f"  adjacent name-name pairs: {adj}   distinct (本,之) pairs: {len(pairs)}")
print(f"  adjacency rate: {100.0*adj/max(len(occ),1):.1f}% of occurrences")
print(f"  a full matrix would be 64x64=4096 (or 64x63=4032 excluding self)")
print(f"  self-pairs present: {sum(1 for a, b in pairs if a == b)}")

print("\n" + "=" * 78)
print("CLAIM (c) citation markers 易云 / 易曰")
print("=" * 78)
SX = [d for d in sorted(os.listdir(RAW)) if os.path.isdir(os.path.join(RAW, d))
      and (d.startswith("KR3g") or d in ("KR1a0003", "KR1a0030"))]
tot = {"易云": 0, "易曰": 0, "易曰：": 0, "故易曰": 0}
per = []
for w in SX:
    b = re.sub(r"<pb:[^>]+>|[¶\s　]", "", fold(work_body(RAW, w)))
    c1, c2 = b.count("易云"), b.count("易曰")
    tot["易云"] += c1
    tot["易曰"] += c2
    if c1 or c2:
        per.append((w, c1, c2))
print(f"  across the 22 non-易類 works: 易云 {tot['易云']}   易曰 {tot['易曰']}")
print(f"  {'work':10} {'易云':>5} {'易曰':>5}")
for w, c1, c2 in sorted(per, key=lambda x: -(x[1] + x[2]))[:10]:
    print(f"  {w:10} {c1:>5} {c2:>5}")

print("\n" + "=" * 78)
print("These measured values replace whatever docs/GOAL.md currently states.")
print("=" * 78)

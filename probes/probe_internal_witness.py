"""Is the 40.2% really unvalidatable, or does the corpus already contain its own witnesses?

I told the user those 22 works have no validation path and might need "cross-citation or a
cross-book citation network", implying new acquisitions. That claim deserves checking before
anyone plans around it, because cross-citation does NOT require new books if the works
already quote material we hold in verified form.

Three concrete questions, all answerable from disk:

  Q1  Do the 術數 works quote 周易 爻辭 verbatim? Those 爻辭 are already verified against
      KR1a0001 (itself now upstream-verified), so any quotation is a free witness AND makes
      the quoting unit canonically addressable.
  Q2  Do they carry 卦 names or hexagram symbols? That would give them a 卦-level address,
      turning `scheme=NULL` works into `scheme='zhouyi'` ones.
  Q3  Do they quote EACH OTHER? Shared long strings between two works form an internal
      witness pair with no external dependency.

If Q1/Q2 come back positive, my earlier statement was wrong and no new books are needed for
this purpose.
"""
import os
import re
import sys
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.ingest import derive_gua_names  # noqa: E402
from guji.variants import fold  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ZY = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
ALL = sorted(d for d in os.listdir(RAW) if os.path.isdir(os.path.join(RAW, d)))
SX = [w for w in ALL if w.startswith("KR3g")] + ["KR1a0003", "KR1a0030"]

bodies = {w: work_body(RAW, w) for w in ALL}
pol = derive_polarity({w: bodies[w] for w in ZY})
gold = derive_gold(bodies["KR1a0001"], pol)
NAMES = derive_gua_names(bodies["KR1a0001"])
print(f"gold 卦 {len(gold)}   卦 names {len(NAMES)}")


def clean(s):
    return re.sub(r"<pb:[^>]+>|[¶\s　/()（）「」『』《》，。、：；？！·○]", "", fold(s))


CL = {w: clean(b) for w, b in bodies.items()}

print("\n" + "=" * 78)
print("Q1 — do the unvalidated works quote 周易 爻辭 verbatim?")
print("=" * 78)
# Use 爻辭 of length >= 6 as probes: long enough to be a real quotation, not coincidence.
probes = []
for g, entry in gold.items():
    for label, txt in entry.items():
        t = clean(txt)[:10]
        if len(t) >= 6:
            probes.append((g, label, t))
print(f"probe 爻辭 (>=6 chars): {len(probes)}")

hits = defaultdict(list)
for w in SX:
    body = CL[w]
    for g, label, t in probes:
        if t in body:
            hits[w].append((g, label, t))
print(f"\n{'work':10} {'quoted 爻辭':>12}  {'distinct 卦':>11}  examples")
print("-" * 78)
tot = 0
for w in SX:
    hs = hits.get(w, [])
    tot += len(hs)
    if hs:
        guas = sorted({g for g, _, _ in hs})
        ex = "; ".join(f"卦{g}{lb}={t[:8]}" for g, lb, t in hs[:2])
        print(f"{w:10} {len(hs):>12}  {len(guas):>11}  {ex}")
print("-" * 78)
print(f"works with >=1 verbatim 爻辭 quotation: {len(hits)}/{len(SX)}   total {tot}")

print("\n" + "=" * 78)
print("Q2 — do they carry 卦 names or hexagram symbols (i.e. an addressable structure)?")
print("=" * 78)
print(f"{'work':10} {'卦符':>6} {'distinct':>9} {'卦名 hits':>10} {'distinct':>9}")
print("-" * 52)
structural = []
for w in SX:
    raw, body = bodies[w], CL[w]
    syms = [gua_number(m.group()) for m in HEX_RE.finditer(raw)]
    nm = Counter()
    for g, n in NAMES.items():
        if n and len(n) >= 1:
            c = body.count(n)
            if c:
                nm[g] = c
    if syms or len(nm) >= 20:
        structural.append(w)
    print(f"{w:10} {len(syms):>6} {len(set(syms)):>9} {sum(nm.values()):>10} {len(nm):>9}")
print("-" * 52)
print(f"works with hexagram symbols or >=20 distinct 卦 names: {len(structural)}")
print(f"  {structural}")

print("\n" + "=" * 78)
print("Q3 — do the works quote EACH OTHER? (internal witness pairs, no new books)")
print("=" * 78)
# Shared 12-grams between works. Sample to keep it cheap.
def grams(s, n=12, step=7):
    return {s[i:i + n] for i in range(0, max(len(s) - n, 0), step)}


G = {w: grams(CL[w]) for w in ALL}
pairs = []
for i, a in enumerate(ALL):
    for b in ALL[i + 1:]:
        inter = G[a] & G[b]
        if len(inter) >= 5:
            pairs.append((len(inter), a, b, list(inter)[:2]))
pairs.sort(reverse=True)
print(f"pairs sharing >=5 sampled 12-grams: {len(pairs)}")
for n, a, b, ex in pairs[:14]:
    print(f"  {n:5}  {a:10} ~ {b:10}  e.g. {ex[0][:14]!r}")

print("\n" + "=" * 78)
print("VERDICT")
print("=" * 78)
print(f"  quoting 周易 爻辭       : {len(hits)}/{len(SX)} works")
print(f"  addressable structure  : {len(structural)}/{len(SX)} works")
print(f"  internal witness pairs : {len(pairs)}")
print("  If these are non-zero, cross-citation validation needs NO new acquisitions.")

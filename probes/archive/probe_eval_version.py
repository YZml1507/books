"""Why does check_quality report 17 shared addresses for KR1a0031/0032 but 358 for
KR1a0006/0007, when both pairs have ~380 located 爻 each?

Reason for asking: building the G1 version-awareness questions produced ~295 divergent
addresses for the 31/32 pair from data/raw/, which cannot coexist with "17 shared".
One of the two numbers is wrong, and if it is the gate's, then G3's evidence for that
pair is far weaker than the ledger claims — the gate would be printing
"median coverage 1.000, below 0.60: 0" after comparing almost nothing.

Also checks fold() idempotence, because a FOLD value that is itself a FOLD key would make
fold(fold(x)) != fold(x) and silently break every gold-witness comparison.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.quality import addresses_of  # noqa: E402
from guji.variants import FOLD, fold  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORKS = ("KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032")

print("=== 1. fold() idempotence: no FOLD value may also be a FOLD key ===")
chains = {k: v for k, v in FOLD.items() if v in FOLD}
print(f"  FOLD pairs {len(FOLD)}   values that are also keys: {len(chains)}  {chains}")
bad = [c for c in FOLD if fold(fold(c)) != fold(c)]
print(f"  chars where fold(fold(c)) != fold(c): {len(bad)}  {bad}")

bodies = {w: work_body(RAW, w) for w in WORKS}
polarity = derive_polarity(bodies)

print("\n=== 2. addresses_of() per work: key count and text-length distribution ===")
tabs = {}
for w in WORKS:
    t = addresses_of(bodies[w], polarity)
    tabs[w] = t
    lens = sorted(len(v) for v in t.values())
    ge20 = sum(1 for x in lens if x >= 20)
    med = lens[len(lens) // 2] if lens else 0
    print(f"  {w}  keys={len(t):4d}  len>=20: {ge20:4d}  median len={med:6d}  "
          f"min={lens[0] if lens else 0}  max={lens[-1] if lens else 0}")

print("\n=== 3. shared keys per pair, before vs after the min_len=20 filter ===")
for a, b in (("KR1a0006", "KR1a0007"), ("KR1a0031", "KR1a0032")):
    ta, tb = tabs[a], tabs[b]
    shared = set(ta) & set(tb)
    kept = [k for k in shared if len(ta[k]) >= 20]
    print(f"  {a} vs {b}:  keys A={len(ta)} B={len(tb)}  shared={len(shared)}  "
          f"survive len(A)>=20: {len(kept)}   FILTERED OUT: {len(shared) - len(kept)}")
    short = sorted((len(ta[k]), k) for k in shared if len(ta[k]) < 20)[:8]
    if short:
        print(f"    shortest A texts among shared: {[(n, f'卦{k[0]}{k[1]}') for n, k in short]}")

print("\n=== 4. is the 經-only view the culprit? compare keep_notes True vs False ===")
for w in ("KR1a0031", "KR1a0032", "KR1a0006"):
    raw = bodies[w]
    spans, _ = gua_spans(raw)
    tot_j = tot_v = n = 0
    for s in spans:
        if s.number not in polarity:
            continue
        seg = raw[s.start:s.end]
        tot_j += len(clean(seg, keep_notes=False).text)
        tot_v += len(clean(seg, keep_notes=True).text)
        n += 1
    print(f"  {w}  spans={n}  經-only chars={tot_j:,}  with-notes chars={tot_v:,}  "
          f"ratio={tot_j / max(tot_v, 1):.3f}")

print("\n=== 5. my raw-derived 經-only table (what the eval bank used) ===")
mine = {}
for w in WORKS:
    raw = bodies[w]
    table = {}
    spans, _ = gua_spans(raw)
    for s in spans:
        if s.number not in polarity:
            continue
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=False)
        hits = extract_yao(seg, yao_names(polarity[s.number]), jing=view)
        for label, rng in hits.items():
            if rng and (s.number, label) not in table:
                table[(s.number, label)] = view.text[rng[0] + len(label):rng[1]]
    mine[w] = table
    lens = sorted(len(v) for v in table.values())
    print(f"  {w}  keys={len(table):4d}  median len={lens[len(lens) // 2] if lens else 0}")

sh = set(mine["KR1a0031"]) & set(mine["KR1a0032"])
print(f"\n  31/32 shared (my table): {len(sh)}")

print("\n=== 6. where do 31 and 32 first differ at a shared address? ===")
buckets = Counter()
early = []
for k in sorted(sh):
    a, b = fold(mine["KR1a0031"][k]), fold(mine["KR1a0032"][k])
    if len(a) < 6 or len(b) < 6:
        continue
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    if i >= min(len(a), len(b)):
        buckets["identical prefix (one is a prefix of the other)"] += 1
        continue
    buckets[f"first diff at {'0-9' if i < 10 else '10-29' if i < 30 else '30+'}"] += 1
    if i < 30:
        early.append((i, k, a[max(0, i - 6):i + 6], b[max(0, i - 6):i + 6]))
for kk, v in sorted(buckets.items()):
    print(f"  {kk:48s} {v}")
print(f"\n  early divergences (first diff < 30 chars): {len(early)}")
for i, k, aa, bb in sorted(early)[:14]:
    print(f"    卦{k[0]:>2}{k[1]:4s} @{i:2d}  31={aa!r:22s} 32={bb!r}")

print("\n=== 7. the documented 異文 pairs that must NOT be folded: where are they? ===")
for var, canon in (("稊", "梯"), ("梯", "稊"), ("跛", "破"), ("破", "跛")):
    hits = []
    for w in WORKS:
        for k, v in mine[w].items():
            if var in v:
                hits.append((w, f"卦{k[0]}{k[1]}"))
    print(f"  {var}: {len(hits)} address-texts  {hits[:6]}")

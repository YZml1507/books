"""Does quality.addresses_of() under-report the text at an address, and does fixing it
un-blind the cross-edition gate for KR1a0031/0032?

Measured symptom (probes/probe_eval_version.py):

    KR1a0031  keys=377  but only 17 have len>=20   median len 9
    KR1a0032  keys=380         380 have len>=20    median len 69
    -> cross_edition_coverage(31, 32) drops 360 of 377 shared addresses to the min_len
       filter and prints "median coverage 1.000, below 0.60: 0" after comparing 4.5% of
       the pair. That is a gate reporting perfection over almost nothing.

Cause: addresses_of() takes the window from the 爻位 label to the LAST 經 CHARACTER before
the next label (r1 = jing.origin(end - 1)), then reads that window out of the with-notes
view. Where the 注 is parenthesised (KR1a0031/0032), every note therefore falls outside
the window and the returned text is 爻辭-only — 8 chars. Where the 注 is inline text rather
than parenthesised (KR1a0007 prints a literal 注 marker), the note is inside the 經-only
view already and DOES get returned — 79 chars. So the function's output silently means
different things per edition, while its docstring says "經+注 text" for both.

v2: take the window from this label's raw offset to the NEXT LABEL's raw offset (or the
span end), so an address covers everything printed between the two 爻位 — which is what
"the text at this address" has to mean for a cross-edition comparison to be meaningful.

PRE-REGISTERED acceptance criteria for the fix (fixed before running this probe):
  1. 31/32 shared addresses surviving min_len must rise from 17 to > 300.
  2. 06/07 shared must stay >= 358, and its median coverage must stay >= 0.95 (the
     "B embeds A near-verbatim" precondition must survive).
  3. 卦61 上九 must still be classified text-damage (the gate's known-positive control).
If 2 or 3 fails, the fix is REJECTED and reverted, per §3 of docs/GOAL.md.
"""
from __future__ import annotations

import bisect
import difflib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.quality import AddressDiff, addresses_of  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
PAIRS = (("KR1a0006", "KR1a0007"), ("KR1a0031", "KR1a0032"))
WORKS = sorted({"KR1a0001", *[w for p in PAIRS for w in p]})


def addresses_of_v2(raw: str, polarity: dict[int, tuple[int, ...]]) -> dict[tuple, str]:
    """Label-to-label window, read out of the with-notes view."""
    out: dict[tuple, str] = {}
    seen: set[int] = set()
    spans, _ = gua_spans(raw)
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=True)
        jing = clean(seg, keep_notes=False)
        hits = extract_yao(seg, yao_names(polarity[s.number]), jing=jing)
        marks = sorted((v[0], k) for k, v in hits.items() if v)
        for n, (pos, label) in enumerate(marks):
            r0 = jing.origin(pos)
            if n + 1 < len(marks):
                r1 = jing.origin(marks[n + 1][0])
            else:
                r1 = s.end
            if r0 < 0:
                continue
            v0 = bisect.bisect_left(view.offsets, r0)
            v1 = bisect.bisect_left(view.offsets, r1) if r1 >= 0 else len(view.text)
            out[(s.number, label)] = view.text[v0:v1]
    return out


def compare(ta, tb, min_len=20):
    out = []
    for key in sorted(set(ta) & set(tb)):
        a, b = ta[key], tb[key]
        if len(a) < min_len:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        blocks = sm.get_matching_blocks()
        out.append(AddressDiff(key[0], key[1], sum(bl.size for bl in blocks) / len(a),
                               len(a), len(b), a, b,
                               max((bl.size for bl in blocks), default=0)))
    out.sort(key=lambda d: d.coverage)
    return out


bodies = {w: work_body(RAW, w) for w in WORKS}
pol = derive_polarity(bodies)

for name, fn in (("v1 (current)", addresses_of), ("v2 (label-to-label)", addresses_of_v2)):
    print(f"\n{'=' * 78}\n{name}")
    tabs = {w: fn(bodies[w], pol) for w in WORKS}
    for w in WORKS:
        lens = sorted(len(v) for v in tabs[w].values())
        print(f"  {w}  keys={len(tabs[w]):4d}  len>=20:{sum(1 for x in lens if x >= 20):4d}"
              f"  median={lens[len(lens) // 2] if lens else 0:6d}  max={lens[-1] if lens else 0:,}")
    for a, b in PAIRS:
        diffs = compare(tabs[a], tabs[b])
        covs = sorted(d.coverage for d in diffs)
        med = covs[len(covs) // 2] if covs else 0.0
        low = [d for d in diffs if d.coverage < 0.60 and d.gua != 64]
        ctl = [d for d in low if d.gua == 61 and d.verdict == "text-damage"]
        print(f"\n  {a} vs {b}: compared={len(diffs)}  median coverage={med:.3f}  "
              f"below 0.60 (excl 卦64)={len(low)}")
        by = {}
        for d in low:
            by.setdefault(d.verdict, []).append(f"卦{d.gua}{d.yao}")
        for v, ks in sorted(by.items()):
            print(f"      {v:22s} {len(ks):3d}  {' '.join(ks[:10])}"
                  f"{' …' if len(ks) > 10 else ''}")
        if (a, b) == ("KR1a0006", "KR1a0007"):
            print(f"      CONTROL 卦61 上九 text-damage detected: "
                  f"{'YES' if ctl else 'NO — gate would break'}")
            for d in ctl:
                print(f"        coverage {d.coverage:.3f} contiguity {d.contiguity:.3f} "
                      f"lenA={d.len_a} lenB={d.len_b}")

print(f"\n{'=' * 78}\nv2 sample: what an address text looks like after the fix")
t31 = addresses_of_v2(bodies["KR1a0031"], pol)
t32 = addresses_of_v2(bodies["KR1a0032"], pol)
for key in [(28, "九二"), (54, "初九"), (1, "九三")]:
    if key in t31 and key in t32:
        print(f"\n  卦{key[0]}{key[1]}")
        print(f"    31: {t31[key][:150]}")
        print(f"    32: {t32[key][:150]}")

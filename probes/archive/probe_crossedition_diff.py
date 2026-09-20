"""Detect corruption by cross-edition disagreement at a shared canonical address.

Why this beats rarity scoring: probes/probe_corrupt.py ranked the known-bad KR1a0006 中孚
window only 599th of 88,530 (below its own 99.5th-percentile threshold), and its top hits
were false positives — 太玄經's 音義 glossary (`廬偈音傑…音吪動也`) is legitimately full of
unattested bigrams. Rarity cannot separate "OCR junk" from "glossary".

Cross-edition diff can, because it uses an independent witness. KR1a0007 (註疏) embeds
王弼's 注 verbatim alongside 孔穎達's 疏, so at any (卦, 爻) the KR1a0006 text should appear
almost verbatim inside KR1a0007. Where a pair that normally agrees ~verbatim suddenly does
not, one of the two is damaged — and this is exactly what the 卦/爻 join key was built for
(D-005), so it costs nothing new.

Control: the detector must rank 卦61 中孚 at or near the top, or it is not a detector.
"""
import difflib
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
A, B = "KR1a0006", "KR1a0007"      # 王弼注  vs  王弼注+孔穎達疏
bodies = {w: work_body(RAW, w) for w in ["KR1a0001", A, B]}
polarity = derive_polarity(bodies)


def by_address(work):
    """-> {(卦, 爻): 經+注 text} using the shared alignment layer."""
    raw = bodies[work]
    spans, _ = gua_spans(raw)
    out, seen = {}, set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        exp = yao_names(polarity[s.number])
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=True)
        jing = clean(seg, keep_notes=False)
        hits = extract_yao(seg, exp, jing=jing)
        marks = sorted((v[0], k) for k, v in hits.items() if v)
        for n, (pos, label) in enumerate(marks):
            end = marks[n + 1][0] if n + 1 < len(marks) else len(jing.text)
            # map 經 coords -> raw -> with-notes coords
            r0 = jing.origin(pos)
            r1 = jing.origin(end - 1) if end - 1 < len(jing.offsets) else s.end
            v0 = next((i for i, o in enumerate(view.offsets) if o >= r0), 0)
            v1 = next((i for i, o in enumerate(view.offsets) if o >= r1), len(view.text))
            out[(s.number, label)] = view.text[v0:v1]
    return out


ta, tb = by_address(A), by_address(B)
common = sorted(set(ta) & set(tb))
print(f"{A}: {len(ta)} addresses   {B}: {len(tb)}   shared: {len(common)}")

rows = []
for key in common:
    a, b = ta[key], tb[key]
    if len(a) < 20:
        continue
    # How much of A's text is recoverable inside B? A is a SUBSET of B by construction,
    # so use the longest-matching-block ratio rather than symmetric similarity.
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    covered = sum(bl.size for bl in sm.get_matching_blocks())
    rows.append((covered / len(a), key, len(a), len(b), a))

rows.sort()
print("\n=== addresses where 王弼注 is LEAST recoverable inside 註疏 ===")
print(f"  {'cover':>6} {'卦':>4} {'爻':6} {'lenA':>6} {'lenB':>6}  KR1a0006 text")
for cov, (g, label), la, lb, a in rows[:16]:
    print(f"  {cov:6.3f} {g:4} {label:6} {la:6} {lb:6}  {a[:46]}")

import statistics  # noqa: E402
covs = [r[0] for r in rows]
print(f"\n  median coverage {statistics.median(covs):.3f}   mean {statistics.mean(covs):.3f}")
print(f"  addresses below 0.60: {sum(1 for c in covs if c < 0.60)}")

print("\n=== control: rank of the hand-found corrupt region (卦61 九五 / 上九) ===")
for rank, (cov, key, la, lb, a) in enumerate(rows, 1):
    if key[0] == 61 and key[1] in ("九五", "上九"):
        print(f"  rank {rank}/{len(rows)}  卦61 {key[1]}  coverage {cov:.3f}  "
              f"(top {100.0*rank/len(rows):.2f}%)")

print("\n=== detail: 卦61 中孚 九五 side by side ===")
for label in ("九五", "上九"):
    k = (61, label)
    if k in ta and k in tb:
        print(f"\n  [{label}] KR1a0006: {ta[k][:120]}")
        print(f"  [{label}] KR1a0007: {tb[k][:120]}")

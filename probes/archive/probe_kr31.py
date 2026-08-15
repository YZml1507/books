"""Diff KR1a0031 against KR1a0032 (same work, two editions) per 爻.

Question: why does 0031 verify 353/377 while 0032 verifies 374/380?
Approach: run the exact same pipeline over both, classify each 爻 with the same
classifier diagnose_yao.py uses, and print only the cells where the two editions
DISAGREE. Anything failing in both is a property of the work, not of 0031.
"""
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORKS = ["KR1a0031", "KR1a0032"]
PARTICLES = ("曰", "云", "者", "注", "疏", "傳")


def classify(gold: str, actual: str) -> tuple[str, str]:
    """Copy of scripts/diagnose_yao.py:classify so this probe cannot drift from it
    by importing a module-level side effect (that script runs work at import time)."""
    if not actual:
        return "absent", ""
    head = gold[:6]
    if head in actual:
        return "ok", ""
    for p in PARTICLES:
        if actual.startswith(p) and head in actual[: len(p) + len(head) + 4]:
            return "inserted", p
    i = 0
    while i < min(len(gold), len(actual)) and gold[i] == actual[i]:
        i += 1
    if i < len(gold) and i < len(actual):
        rest = gold[i + 1:i + 6]
        if not rest or rest in actual[i + 1:i + 12]:
            return "variant", f"{actual[i]}->{gold[i]} after {gold[:i]}"
        return "differs", f"{actual[i]}!={gold[i]} after {gold[:i]}"
    if i >= 3:
        return "abridged", gold[:i]
    pos, ok = 0, True
    for ch in head:
        at = actual.find(ch, pos)
        if at == -1:
            ok = False
            break
        pos = at + 1
    if ok:
        return "note_split", actual[:pos][:24]
    if gold[:3] and gold[:3] in actual:
        return "strict", gold[:3]
    return "absent", actual[:20]


bodies = {w: work_body(RAW, w) for w in ["KR1a0001"] + WORKS}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)

# cells[(gua, label)][work] = (category, evidence, actual)
cells: dict[tuple, dict] = {}
for w in WORKS:
    raw = bodies[w]
    spans, outside = gua_spans(raw)
    print(f"{w}: files spans={len(spans)} outside={len(outside)} chars={len(raw)}")
    seen = set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        expected = yao_names(polarity[s.number])
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=False)
        hits = extract_yao(seg, expected, jing=view)
        for label in expected:
            rng = hits.get(label)
            want = gold.get(s.number, {}).get(label)
            if not want:
                continue
            if not rng:
                cells.setdefault((s.number, label), {})[w] = ("UNLOCATED", "", "")
                continue
            actual = view.text[rng[0] + len(label):rng[1]]
            cat, ev = classify(want, actual)
            cells.setdefault((s.number, label), {})[w] = (cat, ev, actual)

print()
tot = Counter()
for (g, label), byw in cells.items():
    for w in WORKS:
        c = byw.get(w, ("MISSING", "", ""))[0]
        tot[(w, c)] += 1
for w in WORKS:
    row = {c: n for (ww, c), n in tot.items() if ww == w}
    print(f"{w}: {row}")

print("\n" + "=" * 78)
print("CELLS WHERE 0031 FAILS BUT 0032 IS OK  (the 0031-specific gap)")
print("=" * 78)
only31 = []
for (g, label), byw in sorted(cells.items()):
    c31 = byw.get("KR1a0031", ("MISSING", "", ""))
    c32 = byw.get("KR1a0032", ("MISSING", "", ""))
    if c31[0] != "ok" and c32[0] == "ok":
        only31.append((g, label, c31, c32))
print(f"count = {len(only31)}\n")
for g, label, c31, c32 in only31:
    want = gold[g][label]
    print(f"卦{g} {label}   [{c31[0]}] {c31[1]}")
    print(f"  gold : {want[:40]}")
    print(f"  0031 : {c31[2][:40]}")
    print(f"  0032 : {c32[2][:40]}")

print("\n" + "=" * 78)
print("FAILS IN BOTH EDITIONS (property of the work, not of 0031)")
print("=" * 78)
both = [(g, l, a, b) for (g, l), byw in sorted(cells.items())
        if (a := byw.get("KR1a0031", ("MISSING", "", "")))[0] != "ok"
        and (b := byw.get("KR1a0032", ("MISSING", "", "")))[0] != "ok"]
print(f"count = {len(both)}\n")
for g, label, a, b in both:
    print(f"卦{g} {label}   0031=[{a[0]}] {a[1]}   0032=[{b[0]}] {b[1]}")

print("\n" + "=" * 78)
print("CELLS WHERE 0032 FAILS BUT 0031 IS OK")
print("=" * 78)
only32 = [(g, l, a, b) for (g, l), byw in sorted(cells.items())
          if (a := byw.get("KR1a0031", ("MISSING", "", "")))[0] == "ok"
          and (b := byw.get("KR1a0032", ("MISSING", "", "")))[0] != "ok"]
print(f"count = {len(only32)}")
for g, label, a, b in only32:
    print(f"卦{g} {label}   0032=[{b[0]}] {b[1]}")

"""Split KR1a0031's 25 unique failures into: foldable 異體字 / real 校勘 variance / defect.

The point is to NOT chase 93.6% -> 95% by folding whatever makes the number move. D-006
already established that 差異 between 原本 and 別本 本義 is the evidence this system exists
to preserve. So each failure gets a verdict with a reason, and only glyph variants are
eligible for variants.FOLD.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.variants import FOLD, NOT_VARIANTS  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
bodies = {w: work_body(RAW, w) for w in ["KR1a0001", "KR1a0031", "KR1a0032"]}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)

raw = bodies["KR1a0031"]
spans, _ = gua_spans(raw)
seen = set()

print("=== every char-level divergence in KR1a0031, with same-position sibling form ===")
print(f"{'卦':>4} {'爻':6} {'kr31':>6} {'kr01':>6} {'kr32':>6}  verdict")
print("-" * 60)


def sibling_form(g, label, i):
    """What KR1a0032 has at the same position, if it has this 爻 at all."""
    sraw = bodies["KR1a0032"]
    sspans, _ = gua_spans(sraw)
    sseen = set()
    for s in sspans:
        if s.number != g or s.number in sseen:
            continue
        sseen.add(s.number)
        exp = yao_names(polarity[s.number])
        seg = sraw[s.start:s.end]
        v = clean(seg, keep_notes=False)
        h = extract_yao(seg, exp, jing=v)
        r = h.get(label)
        if r:
            a = v.text[r[0] + len(label):r[1]]
            return a[i] if i < len(a) else ""
    return ""


unlocated = []
rows = []
for s in spans:
    if s.number not in polarity or s.number in seen:
        continue
    seen.add(s.number)
    exp = yao_names(polarity[s.number])
    seg = raw[s.start:s.end]
    view = clean(seg, keep_notes=False)
    hits = extract_yao(seg, exp, jing=view)
    for label in exp:
        rng = hits.get(label)
        want = gold.get(s.number, {}).get(label)
        if not want:
            continue
        if not rng:
            unlocated.append((s.number, label, want))
            continue
        actual = view.text[rng[0] + len(label):rng[1]]
        if want[:6] in actual:
            continue
        i = 0
        while i < min(len(want), len(actual)) and want[i] == actual[i]:
            i += 1
        if i >= min(len(want), len(actual)):
            rows.append((s.number, label, "", want[i:i + 3], "", "TRUNCATED/abridged"))
            continue
        a, b = actual[i], want[i]
        sib = sibling_form(s.number, label, i)
        # A glyph variant should be same-word: the rest of the phrase must line up after it.
        rest_ok = want[i + 1:i + 5] and want[i + 1:i + 5] in actual[i + 1:i + 8]
        if (b, a) in NOT_VARIANTS or (a, b) in NOT_VARIANTS:
            verdict = "REJECTED (recorded not-a-variant)"
        elif a in FOLD:
            verdict = "already folded — check direction"
        elif not rest_ok:
            verdict = "校勘 variance (phrase diverges, not one glyph)"
        elif sib and sib == b:
            verdict = "FOLD candidate (sibling has canonical form)"
        else:
            verdict = "FOLD candidate (single glyph, phrase aligns)"
        rows.append((s.number, label, a, b, sib, verdict))

for g, label, a, b, sib, verdict in rows:
    print(f"{g:>4} {label:6} {a or '-':>6} {b or '-':>6} {sib or '-':>6}  {verdict}")

print(f"\n=== {len(unlocated)} unlocated 爻 — these are parse defects, not variance ===")
for g, label, want in unlocated:
    exp = yao_names(polarity[g])
    s = next(x for x in spans if x.number == g)
    view = clean(raw[s.start:s.end], keep_notes=False)
    print(f"\n  卦{g} {label}  gold={want[:20]}")
    print(f"    span {s.end - s.start} chars, anchor {s.page_anchor}")
    print(f"    labels present in span: {[l for l in exp if l in view.text]}")
    print(f"    missing: {[l for l in exp if l not in view.text]}")
    # where does the gold text actually sit?
    at = view.text.find(want[:6])
    print(f"    gold head at {at} in span" + (
        f", context {view.text[max(0,at-14):at+10]!r}" if at >= 0 else " (absent)"))

print("\n=== proposed additions to variants.FOLD ===")
prop = {}
for g, label, a, b, sib, verdict in rows:
    if verdict.startswith("FOLD candidate") and a and b:
        prop[(a, b)] = prop.get((a, b), 0) + 1
for (a, b), n in sorted(prop.items(), key=lambda kv: -kv[1]):
    print(f'    "{a}": "{b}",   # U+{ord(a):04X} -> U+{ord(b):04X}  x{n}')

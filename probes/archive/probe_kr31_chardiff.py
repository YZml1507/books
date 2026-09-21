"""Complete character-level diff of every 爻辭 in KR1a0031 / KR1a0032 against gold.

The classifier only reports the FIRST divergence per cell and stops, so it cannot give a
complete candidate list. Here every cell is aligned with difflib and every substitution
is recorded, together with:
  * whether the OTHER edition of the same work agrees with gold at that spot
    (0032 agrees + 0031 differs  => the defect is 0031's, not the work's)
  * whether 0031's OWN 注 / 象傳 uses the canonical form elsewhere
    (self-contradiction => digitisation corruption, NOT a variant to fold)

Also checks the pending "second attestation" for 怕->恆 and 凖->隼 in other works,
and why 卦39 is off the LIS chain in both editions.
"""
import difflib
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.variants import FOLD, NOT_VARIANTS  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ALL}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)


def cells(work):
    """{(卦, 爻位): actual cleaned 經 text after the label}"""
    raw = bodies[work]
    spans, _ = gua_spans(raw)
    out, seen = {}, set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        expected = yao_names(polarity[s.number])
        view = clean(raw[s.start:s.end], keep_notes=False)
        hits = extract_yao(raw[s.start:s.end], expected, jing=view)
        for label in expected:
            rng = hits.get(label)
            if rng:
                out[(s.number, label)] = view.text[rng[0] + len(label):rng[1]]
    return out


c31, c32 = cells("KR1a0031"), cells("KR1a0032")

subs: dict[tuple, list] = defaultdict(list)   # (corpus_char, gold_char) -> [(卦,爻,ctx)]
drops: list = []                              # gold char absent from 0031
adds: list = []                               # extra char in 0031

for (g, label), want in sorted(
        ((k, gold[k[0]][k[1]]) for k in c31 if k[1] in gold.get(k[0], {}))):
    have = c31[(g, label)]
    # compare only over the gold length; the tail is commentary
    a, b = want, have[:len(want) + 6]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace" and (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                gc, cc = a[i1 + k], b[j1 + k]
                if gc != cc:
                    subs[(cc, gc)].append((g, label, a[max(0, i1 + k - 3):i1 + k + 3]))
        elif tag == "delete":
            drops.append((g, label, a[i1:i2], a[max(0, i1 - 4):i2 + 4]))
        elif tag == "insert":
            adds.append((g, label, b[j1:j2], a[max(0, i1 - 4):i1 + 4]))
        elif tag == "replace":
            subs[(b[j1:j2], a[i1:i2])].append((g, label, a[max(0, i1 - 3):i2 + 3]))

print("#" * 78)
print("ALL substitutions 0031-經 vs gold, with cross-checks")
print("#" * 78)
print("agree32 = 0032 has the gold char here (so the defect is 0031's alone)")
print("self31  = 0031 itself uses the gold char somewhere in its own text\n")
print(f"{'corpus':>6} {'gold':>5} {'n':>3} {'agree32':>8} {'self31':>7}  cells")
rows = []
for (cc, gc), where in sorted(subs.items(), key=lambda kv: -len(kv[1])):
    if len(cc) != 1 or len(gc) != 1:
        continue
    agree32 = sum(1 for g, label, _ in where
                  if (g, label) in c32 and gc in c32[(g, label)][:len(gold[g][label]) + 6])
    self31 = bodies["KR1a0031"].count(gc)
    cnt31 = bodies["KR1a0031"].count(cc)
    nv = (cc, gc) in NOT_VARIANTS or (gc, cc) in NOT_VARIANTS
    infold = FOLD.get(cc)
    rows.append((cc, gc, len(where), agree32, self31, cnt31, nv, infold, where))
    tag = " NOT_VARIANTS" if nv else (f" already folds->{infold}" if infold else "")
    print(f"{cc:>6} {gc:>5} {len(where):>3} {agree32:>8} {self31:>7}  "
          f"{[(g, l) for g, l, _ in where]}{tag}")
    print(f"       U+{ord(cc):04X}->U+{ord(gc):04X}   count in 0031: {cc}={cnt31} {gc}={self31}"
          f"   in 0032: {cc}={bodies['KR1a0032'].count(cc)} {gc}={bodies['KR1a0032'].count(gc)}")

print("\n" + "#" * 78)
print("characters PRESENT in gold but MISSING from 0031's 經 (real omissions)")
print("#" * 78)
for g, label, gone, ctx in drops:
    in32 = (g, label) in c32 and gone in c32[(g, label)]
    print(f"  卦{g} {label}: dropped {gone!r} from ...{ctx}...   0032 has it: {in32}")

print("\n" + "#" * 78)
print("extra characters in 0031's 經 not in gold (insertions)")
print("#" * 78)
for g, label, extra, ctx in adds:
    print(f"  卦{g} {label}: inserted {extra!r} near ...{ctx}...")

print("\n" + "#" * 78)
print("second-attestation check for the two pairs variants.py left pending")
print("#" * 78)
for ch, canon in (("怕", "恆"), ("凖", "隼")):
    print(f"\n--- {ch} (U+{ord(ch):04X}) ---")
    for w in ALL:
        raw = bodies[w]
        hits = [m.start() for m in re.finditer(re.escape(ch), raw)]
        if not hits:
            continue
        print(f"  {w}: {len(hits)} occurrences")
        for at in hits[:6]:
            ctx = re.sub(r"<pb:[^>]*>|[¶\n]", "", raw[max(0, at - 18):at + 18])
            print(f"     ...{ctx}...")

print("\n" + "#" * 78)
print("why is 卦39 off the LIS chain in BOTH editions?")
print("#" * 78)
for w in ("KR1a0031", "KR1a0032"):
    raw = bodies[w]
    marks = [(m.start(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    seq = [n for _, n in marks]
    # show the neighbourhood of every 卦39 symbol in the symbol sequence
    for i, (pos, n) in enumerate(marks):
        if n == 39:
            print(f"  {w}: 卦39 symbol #{i} at raw {pos}, neighbours in symbol order: "
                  f"{seq[max(0,i-3):i+4]}")
            ctx = re.sub(r"<pb:[^>]*>|[¶\n]", "", raw[max(0, pos - 40):pos + 40])
            print(f"       ...{ctx}...")

print("\n" + "#" * 78)
print("does 0031's 經傳分離 layout put 象傳/繫辭 inside 卦64's span?")
print("#" * 78)
for w in ("KR1a0031", "KR1a0032"):
    spans, _ = gua_spans(bodies[w])
    s64 = next((s for s in spans if s.number == 64), None)
    if s64:
        seg = bodies[w][s64.start:s64.end]
        print(f"  {w}: 卦64 span = {len(seg)} chars; contains 繫辭={'繫辭' in seg} "
              f"說卦={'說卦' in seg or '説卦' in seg} 象曰={seg.count('象曰')}")

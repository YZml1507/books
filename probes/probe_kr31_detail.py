"""Three loose ends from the fix simulation.

1. 卦39 蹇 is off the LIS chain in BOTH editions. FIX-C assumed a wrong symbol; the
   diagram block uses the correct ䷦. So what actually precedes 蹇 in the body?
2. FIX-B (mislabel repair) located +1 爻 in KR1a0006 and KR1a0016 without verifying it.
   Which cells, and is the attribution defensible or a guess? D-006 forbids guessing.
3. FIX-A gained +1 in KR1a0016 as well as +9 in KR1a0031. Which cell, and via which pair?
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.variants import FOLD  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ALL}

print("=" * 88)
print("1. what precedes 蹇's 卦辭 in the body of each edition?")
print("=" * 88)
for w in ALL:
    raw = bodies[w]
    for m in re.finditer(r"蹇[^䷀-䷿]{0,3}利西南", raw):
        lo = max(0, m.start() - 46)
        seg = raw[lo:m.start() + 14]
        cps = " ".join(f"{c}=U+{ord(c):04X}" for c in raw[max(0, m.start() - 6):m.start()])
        print(f"  {w} @{m.start()}: ...{seg!r}")
        print(f"      6 chars before 蹇: {cps}")
        syms = [(mm.start(), gua_number(mm.group())) for mm in HEX_RE.finditer(raw)]
        nearest = [ (p, n) for p, n in syms if p < m.start() ][-2:]
        after = [ (p, n) for p, n in syms if p > m.start() ][:2]
        print(f"      nearest symbols before: {nearest}   after: {after}")

print("\n" + "=" * 88)
print("2/3. per-cell effect of the mislabel repair and of the new folds")
print("=" * 88)

ALL_LABELS = [f"{a}{b}" for b in ("九", "六") for a in ("初", "上")] + \
             [f"{p}{n}" for p in ("九", "六") for n in ("二", "三", "四", "五")] + \
             ["用九", "用六"]
FIX_A = {"眀": "明", "𠖇": "冥", "収": "收", "蘓": "蘇", "𤨏": "瑣", "眈": "耽", "怕": "恆"}


def extract_repaired(seg_raw, expected, jing, repair):
    view = jing
    text = view.text
    found, cursor, prev, fired = {}, 0, None, {}
    for label in expected:
        at = text.find(label, cursor)
        if at == -1 and repair:
            best = None
            for tok in ALL_LABELS:
                if tok in expected and tok != prev:
                    continue
                p = text.find(tok, cursor)
                if p != -1 and (best is None or p < best[0]):
                    best = (p, tok)
            if best:
                at, tok = best
                found[label] = at
                fired[label] = tok
                cursor = at + len(tok)
                prev = label
                continue
        if at == -1:
            continue
        found[label] = at
        cursor = at + len(label)
        prev = label
    result = {}
    ordered = sorted((v, k) for k, v in found.items())
    for n, (pos, label) in enumerate(ordered):
        end = ordered[n + 1][0] if n + 1 < len(ordered) else len(text)
        result[label] = (pos, end)
    for label in expected:
        result.setdefault(label, None)
    return result, fired


def run(fix_a, repair):
    saved = dict(FOLD)
    if fix_a:
        FOLD.update(FIX_A)
    try:
        polarity = derive_polarity(bodies)
        gold = derive_gold(bodies["KR1a0001"], polarity)
        rows = {}
        for w in ALL[1:]:
            raw = bodies[w]
            spans, _ = gua_spans(raw)
            seen = set()
            for s in spans:
                if s.number not in polarity or s.number in seen:
                    continue
                seen.add(s.number)
                exp = yao_names(polarity[s.number])
                seg = raw[s.start:s.end]
                view = clean(seg, keep_notes=False)
                hits, fired = extract_repaired(seg, exp, view, repair)
                for label in exp:
                    rng = hits.get(label)
                    want = gold.get(s.number, {}).get(label)
                    if not rng:
                        rows[(w, s.number, label)] = ("UNLOCATED", "", "")
                        continue
                    actual = view.text[rng[0] + len(label):rng[1]]
                    ok = bool(want) and want[:6] in actual
                    rows[(w, s.number, label)] = (
                        "ok" if ok else "FAIL", fired.get(label, ""), actual[:30])
            # end spans
        return rows
    finally:
        FOLD.clear()
        FOLD.update(saved)


base = run(False, False)
only_b = run(False, True)
only_a = run(True, False)

print("\n--- cells the MISLABEL REPAIR changed ---")
for k in sorted(set(base) | set(only_b)):
    b, r = base.get(k, ("-", "", "")), only_b.get(k, ("-", "", ""))
    if b[0] != r[0]:
        w, g, label = k
        print(f"  {w} 卦{g} {label}: {b[0]} -> {r[0]}"
              f"{'  (repair matched token ' + r[1] + ')' if r[1] else ''}")
        print(f"      text now: {r[2]!r}")

print("\n--- cells the NEW FOLDS changed ---")
for k in sorted(set(base) | set(only_a)):
    b, r = base.get(k, ("-", "", "")), only_a.get(k, ("-", "", ""))
    if b[0] != r[0]:
        w, g, label = k
        print(f"  {w} 卦{g} {label}: {b[0]} -> {r[0]}   text: {r[2]!r}")

print("\n" + "=" * 88)
print("safety: do the new folds collide with characters already in use?")
print("=" * 88)
for a, b in FIX_A.items():
    tgt_existing = [k for k, v in FOLD.items() if v == b]
    tot = sum(bodies[w].count(a) for w in ALL)
    print(f"  {a} -> {b}: total corpus occurrences of {a} = {tot}; "
          f"pairs already folding to {b}: {tgt_existing or 'none'}; "
          f"{a} already in FOLD as -> {FOLD.get(a, 'no')}")

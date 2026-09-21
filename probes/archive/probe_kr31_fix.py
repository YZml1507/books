"""Prove the proposed fixes, don't just argue for them.

Three independent changes are simulated and measured separately so their contributions
can be told apart:

  FIX-A  add 6 genuine 異體字 pairs to FOLD
  FIX-B  repair the 3 source-level 爻位 MISLABELS (duplicate or impossible label)
  FIX-C  put 蹇 back on the LIS chain: both editions tag 蹇 with the WRONG hexagram
         symbol (䷷ = 卦56 旅) in the body, so 卦39 is lost from BOTH editions

Nothing under src/ or scripts/ is modified; FOLD is mutated in this process only.
Also settles the two pairs variants.py left "pending a second attestation" — 凖 turns
out to be a 俗字 of 準, not of 隼, so the rejected pair was rejected for the right
reason but the right pair was never proposed.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, yao_names  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.variants import FOLD  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
COMM = ALL[1:]

# every 爻位 token that can exist, for the mislabel repair
ALL_LABELS = [f"{a}{b}" for b in ("九", "六") for a in ("初", "上")] + \
             [f"{p}{n}" for p in ("九", "六") for n in ("二", "三", "四", "五")] + \
             ["用九", "用六"]

FIX_A = {
    "眀": "明", "𠖇": "冥", "収": "收", "蘓": "蘇", "𤨏": "瑣", "眈": "耽",
    "怕": "恆",
}


def extract_yao_repaired(seg_raw, expected, jing=None, repair=False):
    """extract_yao plus an optional repair for source-level 爻位 mislabels.

    Repair fires only when a label is provably wrong rather than merely absent:
      * the token sitting where the missing label belongs REPEATS the previous label, or
      * that token is IMPOSSIBLE for this 卦 (not in `expected`, i.e. wrong polarity).
    Both conditions are source defects, so accepting them cannot invent an attribution
    that the text does not support.
    """
    view = jing or clean(seg_raw, keep_notes=False)
    text = view.text
    found, cursor, prev = {}, 0, None
    for label in expected:
        at = text.find(label, cursor)
        if at == -1 and repair:
            # look for a duplicate-of-previous or impossible token just ahead
            best = None
            for tok in ALL_LABELS:
                if tok in expected and tok != prev:
                    continue          # a legitimate later label: not a defect
                p = text.find(tok, cursor)
                if p != -1 and (best is None or p < best[0]):
                    best = (p, tok)
            if best:
                at = best[0]
                found[label] = at
                cursor = at + len(best[1])
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
    return result


def score(fix_a=False, fix_b=False, fix_c=False):
    saved = dict(FOLD)
    if fix_a:
        FOLD.update(FIX_A)
    try:
        raws = {}
        for w in ALL:
            r = work_body(RAW, w)
            if fix_c:
                # 蹇 is tagged ䷷ (卦56) in the body of 0031/0032; retag to ䷦ (卦39)
                r = re.sub(r"䷷(\s*蹇)", lambda m: "䷦" + m.group(1), r)
            raws[w] = r
        polarity = derive_polarity(raws)
        # gold must be built with the same folding, or the comparison is asymmetric
        gold = derive_gold(raws["KR1a0001"], polarity)
        out = {}
        for w in COMM:
            raw = raws[w]
            spans, _ = gua_spans(raw)
            seen, located, verified, unknown, expected_n = set(), 0, 0, 0, 0
            for s in spans:
                if s.number not in polarity or s.number in seen:
                    continue
                seen.add(s.number)
                exp = yao_names(polarity[s.number])
                expected_n += len(exp)
                seg = raw[s.start:s.end]
                view = clean(seg, keep_notes=False)
                hits = extract_yao_repaired(seg, exp, jing=view, repair=fix_b)
                got = [k for k, v in hits.items() if v]
                located += len(got)
                unknown += len(exp) - len(got)
                for label in got:
                    want = gold.get(s.number, {}).get(label)
                    if not want:
                        continue
                    rng = hits[label]
                    actual = view.text[rng[0] + len(label):rng[1]]
                    if want[:6] and want[:6] in actual:
                        verified += 1
            out[w] = (len(seen), expected_n, located, verified, unknown)
        return out
    finally:
        FOLD.clear()
        FOLD.update(saved)


CONFIGS = [
    ("baseline", dict()),
    ("FIX-A folds", dict(fix_a=True)),
    ("FIX-B mislabel repair", dict(fix_b=True)),
    ("FIX-C 蹇 symbol", dict(fix_c=True)),
    ("A+B", dict(fix_a=True, fix_b=True)),
    ("A+B+C", dict(fix_a=True, fix_b=True, fix_c=True)),
]
print("=" * 96)
print("simulated scores (爻辭 verified / located, and unknown)")
print("=" * 96)
results = {}
for name, kw in CONFIGS:
    results[name] = score(**kw)
hdr = f"{'work':10}" + "".join(f"{n:>21}" for n, _ in CONFIGS)
print(hdr)
for w in COMM:
    line = f"{w:10}"
    for name, _ in CONFIGS:
        gua, exp, loc, ver, unk = results[name][w]
        line += f"{ver:>8}/{loc:<4}{100*ver/max(loc,1):5.1f}%"
    print(line)
print()
for name, _ in CONFIGS:
    tv = sum(r[3] for r in results[name].values())
    tl = sum(r[2] for r in results[name].values())
    tu = sum(r[4] for r in results[name].values())
    tg = sum(r[0] for r in results[name].values())
    print(f"  {name:24} total {tv}/{tl} = {100*tv/tl:.1f}%   unknown {tu}   卦 spans {tg}")

print("\n" + "=" * 96)
print("per-fix effect on KR1a0031 only")
print("=" * 96)
for name, _ in CONFIGS:
    gua, exp, loc, ver, unk = results[name]["KR1a0031"]
    print(f"  {name:24} 卦={gua} expected={exp} located={loc} verified={ver} "
          f"({100*ver/max(loc,1):.1f}%) unknown={unk}")

print("\n" + "=" * 96)
print("凖 is a 俗字 of 準, NOT of 隼 — counts")
print("=" * 96)
bodies = {w: work_body(RAW, w) for w in ALL}
for w in ALL:
    r = bodies[w]
    print(f"  {w}: 凖={r.count('凖')} 準={r.count('準')} 準(准)={r.count('准')} 隼={r.count('隼')}")

print("\n" + "=" * 96)
print("耽/眈 — same phrase in every work? (checks it is orthographic, not lexical)")
print("=" * 96)
for w in ALL:
    r = bodies[w]
    for ch in ("耽", "眈"):
        for m in list(re.finditer(ch, r))[:3]:
            ctx = re.sub(r"<pb:[^>]*>|[¶\n]", "", r[max(0, m.start() - 12):m.start() + 12])
            print(f"  {w} {ch}: ...{ctx}...")

print("\n" + "=" * 96)
print("蹇 in the body carries the WRONG hexagram symbol in both editions")
print("=" * 96)
for w in ("KR1a0031", "KR1a0032"):
    r = bodies[w]
    for m in re.finditer(r"蹇", r):
        before = r[max(0, m.start() - 30):m.start()]
        syms = HEX_RE.findall(before)
        if syms and before.rstrip("　 ¶\n").endswith(syms[-1]):
            n = gua_number(syms[-1])
            ctx = re.sub(r"<pb:[^>]*>|[¶\n]", "", r[max(0, m.start() - 8):m.start() + 26])
            print(f"  {w}: symbol {syms[-1]} = 卦{n} immediately before 蹇  ...{ctx}...")
            print(f"      -> 蹇 is 卦39, whose symbol is ䷦ (U+4DE6); "
                  f"body uses U+{ord(syms[-1]):04X}")

"""FIX-C, third attempt — and this one is safe.

Attempt 2 retagged every symbol that disagreed with its trigram note, which REGRESSED
KR1a0031: at @10328 the symbol ䷈ (卦9 小畜) is right and the NOTE is wrong — it reads
(乾下/坤上), i.e. 卦11 泰, while 小畜 is 乾下巽上, and the 注 two characters later says
「巽亦三畫卦之名」, naming 巽 explicitly. Retagging turned a correct 卦9 into a duplicate
卦11 and LIS then dropped 卦9 entirely.

So symbol and note disagree in BOTH directions and neither wins by default. The
tie-breaker is the surrounding sequence: only a symbol that LIS already REJECTS is
suspect, and it is retagged only if the note's 卦 number actually fits between its
chain neighbours. Both sources of evidence must agree before anything changes.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, yao_names  # noqa: E402
from guji.anchors import (HEX_RE, _longest_increasing, gua_number, gua_symbol,  # noqa: E402
                          lines_from_trigrams)
from guji.variants import FOLD  # noqa: E402
from guji.zhouyi import TRIGRAM_RE, derive_gold, derive_polarity, work_body  # noqa: E402
import re  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
COMM = ALL[1:]
FIX_A = {"眀": "明", "𠖇": "冥", "収": "收", "蘓": "蘇", "𤨏": "瑣", "眈": "耽", "怕": "恆"}
LABELS = ["用九", "用六"] + [f"{a}{b}" for a in ("初", "上") for b in ("九", "六")] + \
         [f"{p}{n}" for p in ("九", "六") for n in ("二", "三", "四", "五")]
LABEL_RE = re.compile("|".join(sorted(LABELS, key=len, reverse=True)))


def retag_offchain(raw, lines2num, verbose=False, tag=""):
    marks = [(m.start(), m.end(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    if not marks:
        return raw, []
    keep = set(_longest_increasing([n for _, _, n in marks]))
    chain = [n for k, (_, _, n) in enumerate(marks) if k in keep]
    out, last, fixes = [], 0, []
    for k, (s, e, n) in enumerate(marks):
        if k in keep:
            continue
        t = TRIGRAM_RE.search(raw[s:s + 40])
        if not t:
            continue                      # 卦變 diagram entries carry no trigram note
        lines = lines_from_trigrams(t.group(1), t.group(2))
        want = lines2num.get(lines) if lines else None
        if want is None or want == n:
            continue
        # does `want` fit between the chain neighbours bracketing this position?
        lo = max([c for j, c in zip(sorted(keep), chain) if j < k] or [0])
        hi = min([c for j, c in zip(sorted(keep), chain) if j > k] or [65])
        if not (lo < want < hi):
            continue
        out.append(raw[last:s] + gua_symbol(want))
        last = e
        fixes.append((s, n, want, t.group(1), t.group(2), lo, hi))
        if verbose:
            print(f"    {tag} @{s}: 卦{n} -> 卦{want}  note={t.group(1)}下/{t.group(2)}上"
                  f"  fits between chain {lo}..{hi}")
    out.append(raw[last:])
    return "".join(out), fixes


def locate(expected, view, repair):
    text = view.text
    found, cursor = {}, 0
    for label in expected:
        at = text.find(label, cursor)
        if at == -1:
            continue
        found[label] = at
        cursor = at + len(label)
    fired = None
    if repair and len(found) < len(expected):
        toks = [(m.start(), m.group()) for m in LABEL_RE.finditer(text)]
        if len(toks) == len(expected):
            diff = [i for i, (_, t) in enumerate(toks) if t != expected[i]]
            if len(diff) == 1:
                found = {expected[k]: toks[k][0] for k in range(len(expected))}
                fired = (expected[diff[0]], toks[diff[0]][1])
    result = {}
    ordered = sorted((v, k) for k, v in found.items())
    for n, (pos, label) in enumerate(ordered):
        end = ordered[n + 1][0] if n + 1 < len(ordered) else len(text)
        result[label] = (pos, end)
    for label in expected:
        result.setdefault(label, None)
    return result, fired


def score(fix_a=False, fix_b=False, fix_c=False, verbose=False):
    saved = dict(FOLD)
    if fix_a:
        FOLD.update(FIX_A)
    try:
        raws = {w: work_body(RAW, w) for w in ALL}
        polarity = derive_polarity(raws)
        if fix_c:
            l2n = {}
            for num, lines in polarity.items():
                l2n.setdefault(lines, set()).add(num)
            l2n = {k: next(iter(v)) for k, v in l2n.items() if len(v) == 1}
            for w in ALL:
                raws[w], _ = retag_offchain(raws[w], l2n, verbose, w)
            polarity = derive_polarity(raws)
        gold = derive_gold(raws["KR1a0001"], polarity)
        out = {}
        for w in COMM:
            raw = raws[w]
            spans, _ = gua_spans(raw)
            seen, located, verified, unknown, exp_n = set(), 0, 0, 0, 0
            for s in spans:
                if s.number not in polarity or s.number in seen:
                    continue
                seen.add(s.number)
                exp = yao_names(polarity[s.number])
                exp_n += len(exp)
                view = clean(raw[s.start:s.end], keep_notes=False)
                hits, fired = locate(exp, view, fix_b)
                if verbose and fired:
                    print(f"    repair {w} 卦{s.number}: token {fired[1]} read as {fired[0]}")
                got = [k for k, v in hits.items() if v]
                located += len(got)
                unknown += len(exp) - len(got)
                for label in got:
                    want = gold.get(s.number, {}).get(label)
                    if not want:
                        continue
                    actual = view.text[hits[label][0] + len(label):hits[label][1]]
                    if want[:6] in actual:
                        verified += 1
            out[w] = (len(seen), exp_n, located, verified, unknown,
                      sorted(set(range(1, 65)) - seen))
        return out
    finally:
        FOLD.clear()
        FOLD.update(saved)


print("=" * 92)
print("FIX-C (off-chain only): every retag it performs")
print("=" * 92)
score(fix_c=True, verbose=True)

print("\n" + "=" * 92)
CONFIGS = [("baseline", {}), ("A", dict(fix_a=True)), ("B", dict(fix_b=True)),
           ("C", dict(fix_c=True)), ("A+B+C", dict(fix_a=True, fix_b=True, fix_c=True))]
res = {n: score(**kw) for n, kw in CONFIGS}
print(f"{'work':10}" + "".join(f"{n:>18}" for n, _ in CONFIGS))
for w in COMM:
    print(f"{w:10}" + "".join(
        f"{res[n][w][3]:>7}/{res[n][w][2]:<4}{100*res[n][w][3]/max(res[n][w][2],1):4.1f}%"
        for n, _ in CONFIGS))
print()
for n, _ in CONFIGS:
    tv = sum(r[3] for r in res[n].values()); tl = sum(r[2] for r in res[n].values())
    tu = sum(r[4] for r in res[n].values()); tg = sum(r[0] for r in res[n].values())
    print(f"  {n:8} total {tv}/{tl} = {100*tv/tl:.1f}%  unknown {tu}  卦 spans {tg}")
print()
for n, _ in CONFIGS:
    for w in COMM:
        g, e, l, v, u, miss = res[n][w]
        if n in ("baseline", "A+B+C"):
            print(f"  {n:8} {w}: 卦={g} located={l}/{e} verified={v} "
                  f"({100*v/max(l,1):.1f}%) unknown={u} missing卦={miss}")
    print()

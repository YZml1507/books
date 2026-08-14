"""Final measurement, separating fold candidates by KIND rather than by yield.

A1  pure 異體字 that move the score            (眀 𠖇 収 蘓 𤨏 眈)
A2  A1 + 異體字 that do NOT move the score, because the differing character sits beyond
    the 6-character head the verifier checks. They are still real variants and still
    belong in the table; their invisibility is a property of the metric, not of the text.
A3  A2 + 怕->恆, which is NOT an 異體字 but a transcription corruption. Kept separate so
    the decision to include it is explicit.

Reported so the team lead can accept A1/A2 without being forced to accept A3.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, yao_names  # noqa: E402
from guji.anchors import (HEX_RE, _longest_increasing, gua_number, gua_symbol,  # noqa: E402
                          lines_from_trigrams)
from guji.variants import FOLD  # noqa: E402
from guji.zhouyi import TRIGRAM_RE, derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
COMM = ALL[1:]

A1 = {"眀": "明", "𠖇": "冥", "収": "收", "蘓": "蘇", "𤨏": "瑣", "眈": "耽"}
A2_EXTRA = {"嵗": "歲", "歳": "歲", "朶": "朵", "簮": "簪", "靣": "面", "閴": "闃",
            "愠": "慍", "兹": "茲", "𬒮": "袂", "蔾": "藜", "凖": "準"}
A3_EXTRA = {"怕": "恆"}

LABELS = ["用九", "用六"] + [f"{a}{b}" for a in ("初", "上") for b in ("九", "六")] + \
         [f"{p}{n}" for p in ("九", "六") for n in ("二", "三", "四", "五")]
LABEL_RE = re.compile("|".join(sorted(LABELS, key=len, reverse=True)))


def retag_offchain(raw, l2n):
    marks = [(m.start(), m.end(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    if not marks:
        return raw
    keep = sorted(_longest_increasing([n for _, _, n in marks]))
    keepset = set(keep)
    chain = {k: marks[k][2] for k in keep}
    out, last = [], 0
    for k, (s, e, n) in enumerate(marks):
        if k in keepset:
            continue
        t = TRIGRAM_RE.search(raw[s:s + 40])
        if not t:
            continue
        lines = lines_from_trigrams(t.group(1), t.group(2))
        want = l2n.get(lines) if lines else None
        if want is None or want == n:
            continue
        lo = max([c for j, c in chain.items() if j < k] or [0])
        hi = min([c for j, c in chain.items() if j > k] or [65])
        if not (lo < want < hi):
            continue
        out.append(raw[last:s] + gua_symbol(want))
        last = e
    out.append(raw[last:])
    return "".join(out)


def locate(expected, view, repair):
    text = view.text
    found, cursor = {}, 0
    for label in expected:
        at = text.find(label, cursor)
        if at == -1:
            continue
        found[label] = at
        cursor = at + len(label)
    if repair and len(found) < len(expected):
        toks = [(m.start(), m.group()) for m in LABEL_RE.finditer(text)]
        if len(toks) == len(expected):
            diff = [i for i, (_, t) in enumerate(toks) if t != expected[i]]
            if len(diff) == 1:
                found = {expected[k]: toks[k][0] for k in range(len(expected))}
    result = {}
    ordered = sorted((v, k) for k, v in found.items())
    for n, (pos, label) in enumerate(ordered):
        result[label] = (pos, ordered[n + 1][0] if n + 1 < len(ordered) else len(text))
    for label in expected:
        result.setdefault(label, None)
    return result


def score(extra=None, fix_b=False, fix_c=False):
    saved = dict(FOLD)
    if extra:
        FOLD.update(extra)
    try:
        raws = {w: work_body(RAW, w) for w in ALL}
        polarity = derive_polarity(raws)
        if fix_c:
            l2n = {}
            for num, lines in polarity.items():
                l2n.setdefault(lines, set()).add(num)
            l2n = {k: next(iter(v)) for k, v in l2n.items() if len(v) == 1}
            raws = {w: retag_offchain(r, l2n) for w, r in raws.items()}
            polarity = derive_polarity(raws)
        gold = derive_gold(raws["KR1a0001"], polarity)
        out = {}
        for w in COMM:
            raw = raws[w]
            spans, _ = gua_spans(raw)
            seen, loc, ver, unk, expn = set(), 0, 0, 0, 0
            for s in spans:
                if s.number not in polarity or s.number in seen:
                    continue
                seen.add(s.number)
                exp = yao_names(polarity[s.number])
                expn += len(exp)
                view = clean(raw[s.start:s.end], keep_notes=False)
                hits = locate(exp, view, fix_b)
                got = [k for k, v in hits.items() if v]
                loc += len(got)
                unk += len(exp) - len(got)
                for label in got:
                    want = gold.get(s.number, {}).get(label)
                    if want and want[:6] in view.text[
                            hits[label][0] + len(label):hits[label][1]]:
                        ver += 1
            out[w] = (len(seen), expn, loc, ver, unk)
        return out
    finally:
        FOLD.clear()
        FOLD.update(saved)


A2 = {**A1, **A2_EXTRA}
A3 = {**A2, **A3_EXTRA}
CONFIGS = [
    ("baseline", dict()),
    ("A1", dict(extra=A1)),
    ("A2", dict(extra=A2)),
    ("A3", dict(extra=A3)),
    ("A1+B+C", dict(extra=A1, fix_b=True, fix_c=True)),
    ("A2+B+C", dict(extra=A2, fix_b=True, fix_c=True)),
    ("A3+B+C", dict(extra=A3, fix_b=True, fix_c=True)),
]
res = {n: score(**kw) for n, kw in CONFIGS}
print("=" * 108)
print("爻辭 verified / located")
print("=" * 108)
print(f"{'work':10}" + "".join(f"{n:>14}" for n, _ in CONFIGS))
for w in COMM:
    print(f"{w:10}" + "".join(
        f"{100*res[n][w][3]/max(res[n][w][2],1):9.1f}%   " for n, _ in CONFIGS))
print()
for n, _ in CONFIGS:
    tv = sum(r[3] for r in res[n].values()); tl = sum(r[2] for r in res[n].values())
    tu = sum(r[4] for r in res[n].values()); tg = sum(r[0] for r in res[n].values())
    lo = min(100 * r[3] / max(r[2], 1) for r in res[n].values())
    print(f"  {n:9} total {tv}/{tl} = {100*tv/tl:.1f}%   worst work {lo:.1f}%   "
          f"unknown {tu}   卦 spans {tg}/320")
print()
for n, _ in CONFIGS:
    g, e, l, v, u = res[n]["KR1a0031"]
    print(f"  KR1a0031 {n:9} 卦={g}/64 located={l}/{e} verified={v} "
          f"({100*v/max(l,1):.1f}%) unknown={u}")

print("\n" + "=" * 108)
print("regression check: does any work get WORSE than baseline under A3+B+C?")
print("=" * 108)
for w in COMM:
    b, f = res["baseline"][w], res["A3+B+C"][w]
    print(f"  {w}: verified {b[3]}->{f[3]}  located {b[2]}->{f[2]}  "
          f"卦 {b[0]}->{f[0]}  unknown {b[4]}->{f[4]}  "
          f"{'OK' if f[3] >= b[3] and f[0] >= b[0] else 'REGRESSION'}")

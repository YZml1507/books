"""Corrected FIX-B and FIX-C, measured.

FIX-C (was wrong first time round): both editions DO mis-tag 蹇. The trigram note sits
between the symbol and the 卦 name — `䷷(艮下/坎上)蹇` — so my first regex missed it.
  KR1a0031 writes 蹇 as ䷷ U+4DF7 = 卦56 旅
  KR1a0032 writes 蹇 as ䷮ U+4DEE = 卦47 困
  correct is                  ䷦ U+4DE6 = 卦39
Both are refuted by the adjacent note (艮下/坎上), which IS 卦39. So the repair needs no
external table: invert the corpus-derived symbol->trigram map and trust the note.

FIX-B (was too loose): the first rule fired on a cross-referenced 初六 in KR1a0006 卦61
and KR1a0016 卦40, inventing attributions — precisely what D-006 forbids. Tighter rule:
only remap when the span's 爻位 token sequence has exactly the expected LENGTH and differs
from the canonical sequence in exactly ONE position. A cross-reference makes the sequence
too long, so the rule declines instead of guessing.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, yao_names  # noqa: E402
from guji.anchors import HEX_RE, gua_number, gua_symbol, lines_from_trigrams  # noqa: E402
from guji.variants import FOLD  # noqa: E402
from guji.zhouyi import TRIGRAM_RE, derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
COMM = ALL[1:]
FIX_A = {"眀": "明", "𠖇": "冥", "収": "收", "蘓": "蘇", "𤨏": "瑣", "眈": "耽", "怕": "恆"}

LABELS = ["用九", "用六"] + [f"{a}{b}" for a in ("初", "上") for b in ("九", "六")] + \
         [f"{p}{n}" for p in ("九", "六") for n in ("二", "三", "四", "五")]
LABEL_RE = re.compile("|".join(sorted(LABELS, key=len, reverse=True)))


def retag_symbols(raw, sym2lines):
    """Where a hexagram symbol's implied trigram pair contradicts the note printed
    beside it, trust the note. Uses only the corpus-derived map."""
    lines2num = {}
    for num, lines in sym2lines.items():
        lines2num.setdefault(lines, set()).add(num)
    lines2num = {k: next(iter(v)) for k, v in lines2num.items() if len(v) == 1}
    out, fixes = [], []
    last = 0
    for m in HEX_RE.finditer(raw):
        n = gua_number(m.group())
        t = TRIGRAM_RE.search(raw[m.start():m.start() + 40])
        if not t:
            continue
        lines = lines_from_trigrams(t.group(1), t.group(2))
        if not lines:
            continue
        want = lines2num.get(lines)
        if want is None or want == n:
            continue
        out.append(raw[last:m.start()] + gua_symbol(want))
        last = m.end()
        fixes.append((m.start(), n, want, t.group(1), t.group(2)))
    out.append(raw[last:])
    return "".join(out), fixes


def locate(seg_raw, expected, view, repair):
    """Ordered 爻位 search, plus the tight one-substitution repair."""
    text = view.text
    found, cursor, prev = {}, 0, None
    for label in expected:
        at = text.find(label, cursor)
        if at == -1:
            continue
        found[label] = at
        cursor = at + len(label)
        prev = label
    fired = None
    if repair and len(found) < len(expected):
        toks = [(m.start(), m.group()) for m in LABEL_RE.finditer(text)]
        if len(toks) == len(expected):
            diff = [i for i, (_, t) in enumerate(toks) if t != expected[i]]
            if len(diff) == 1:
                i = diff[0]
                found = {expected[k]: toks[k][0] for k in range(len(expected))}
                fired = (expected[i], toks[i][1])
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
            for w in ALL:
                raws[w], fixes = retag_symbols(raws[w], polarity)
                if verbose and fixes:
                    for pos, was, now, lo, up in fixes:
                        print(f"    {w} @{pos}: symbol 卦{was} -> 卦{now} "
                              f"(note says {lo}下/{up}上)")
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
                seg = raw[s.start:s.end]
                view = clean(seg, keep_notes=False)
                hits, fired = locate(seg, exp, view, fix_b)
                if verbose and fired:
                    print(f"    repair {w} 卦{s.number}: source token {fired[1]} "
                          f"read as {fired[0]}")
                got = [k for k, v in hits.items() if v]
                located += len(got)
                unknown += len(exp) - len(got)
                for label in got:
                    want = gold.get(s.number, {}).get(label)
                    if not want:
                        continue
                    rng = hits[label]
                    actual = view.text[rng[0] + len(label):rng[1]]
                    if want[:6] in actual:
                        verified += 1
            out[w] = (len(seen), exp_n, located, verified, unknown)
        return out
    finally:
        FOLD.clear()
        FOLD.update(saved)


print("=" * 92)
print("FIX-C: symbols whose printed trigram note contradicts them")
print("=" * 92)
score(fix_c=True, verbose=True)

print("\n" + "=" * 92)
print("FIX-B (tight): every repair the rule fires")
print("=" * 92)
score(fix_b=True, verbose=True)

print("\n" + "=" * 92)
print("scores")
print("=" * 92)
CONFIGS = [("baseline", {}), ("A", dict(fix_a=True)), ("B", dict(fix_b=True)),
           ("C", dict(fix_c=True)), ("A+B", dict(fix_a=True, fix_b=True)),
           ("A+B+C", dict(fix_a=True, fix_b=True, fix_c=True))]
res = {n: score(**kw) for n, kw in CONFIGS}
print(f"{'work':10}" + "".join(f"{n:>18}" for n, _ in CONFIGS))
for w in COMM:
    print(f"{w:10}" + "".join(
        f"{res[n][w][3]:>7}/{res[n][w][2]:<4}{100*res[n][w][3]/max(res[n][w][2],1):4.1f}%"
        for n, _ in CONFIGS))
print()
for n, _ in CONFIGS:
    tv = sum(r[3] for r in res[n].values())
    tl = sum(r[2] for r in res[n].values())
    tu = sum(r[4] for r in res[n].values())
    te = sum(r[1] for r in res[n].values())
    tg = sum(r[0] for r in res[n].values())
    print(f"  {n:8} total {tv}/{tl} = {100*tv/tl:.1f}%   expected {te}  "
          f"unknown {tu}   卦 spans {tg}")
print()
for n, _ in CONFIGS:
    g, e, l, v, u = res[n]["KR1a0031"]
    print(f"  KR1a0031 {n:8} 卦={g} expected={e} located={l} verified={v} "
          f"({100*v/max(l,1):.1f}%) unknown={u}")

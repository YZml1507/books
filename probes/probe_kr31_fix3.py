"""Last loose end: FIX-C adds 卦 spans to four works but NOT to KR1a0031 (still 63).
It retags two symbols there (卦9->卦11 and 卦56->卦39), so which 卦 does 0031 still lose,
and is the 卦9->卦11 retag genuine?
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import gua_spans  # noqa: E402
from guji.anchors import HEX_RE, gua_number, gua_symbol, lines_from_trigrams  # noqa: E402
from guji.zhouyi import TRIGRAM_RE, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
raws = {w: work_body(RAW, w) for w in ALL}
polarity = derive_polarity(raws)

print("=" * 88)
print("raw context of the two KR1a0031 symbol/note contradictions")
print("=" * 88)
for off in (10328, 26628):
    ctx = re.sub(r"<pb:[^>]*>|[¶\n]", "", raws["KR1a0031"][off - 30:off + 46])
    sym = raws["KR1a0031"][off]
    print(f"  @{off}: symbol {sym} U+{ord(sym):04X} = 卦{gua_number(sym)}")
    print(f"     ...{ctx}...")

lines2num = {}
for num, lines in polarity.items():
    lines2num.setdefault(lines, set()).add(num)
lines2num = {k: next(iter(v)) for k, v in lines2num.items() if len(v) == 1}
print(f"\n  trigram-pair -> 卦 inverse map is unique for {len(lines2num)}/64 pairs")


def retag(raw):
    out, last, fixes = [], 0, []
    for m in HEX_RE.finditer(raw):
        n = gua_number(m.group())
        t = TRIGRAM_RE.search(raw[m.start():m.start() + 40])
        if not t:
            continue
        lines = lines_from_trigrams(t.group(1), t.group(2))
        want = lines2num.get(lines) if lines else None
        if want is None or want == n:
            continue
        out.append(raw[last:m.start()] + gua_symbol(want))
        last = m.end()
        fixes.append((m.start(), n, want))
    out.append(raw[last:])
    return "".join(out), fixes


print("\n" + "=" * 88)
print("which 卦 each work loses, before and after retagging")
print("=" * 88)
for w in ALL:
    before = {s.number for s in gua_spans(raws[w])[0]}
    fixed, fixes = retag(raws[w])
    after = {s.number for s in gua_spans(fixed)[0]}
    print(f"  {w}: retags={len(fixes)}  missing before={sorted(set(range(1,65))-before)}"
          f"  after={sorted(set(range(1,65))-after)}")
    if w == "KR1a0031":
        marks = [gua_number(m.group()) for m in HEX_RE.finditer(fixed)]
        # only body symbols: skip the 卦變 diagram in file 000
        body_start = fixed.find("卷一")
        body = [gua_number(m.group()) for m in HEX_RE.finditer(fixed, body_start)]
        print(f"      body symbol sequence after retag: {body}")

"""KR1a0006 卦19 臨: three 爻位 labels reported absent. Is the edition incomplete, or is
my span wrong? "printed (nothing)" is exactly what a truncated span would also look like,
so it must be checked before being reported as a source anomaly.
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, gua_symbol, yao_names  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
bodies = {w: work_body(RAW, w) for w in ["KR1a0001", "KR1a0006", "KR1a0007"]}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)

for work, gua in (("KR1a0006", 19), ("KR1a0006", 61), ("KR1a0031", 61)):
    raw = bodies[work] if work in bodies else work_body(RAW, work)
    spans, _ = gua_spans(raw)
    s = next((x for x in spans if x.number == gua), None)
    exp = yao_names(polarity[gua])
    print(f"\n{'='*72}\n{work} 卦{gua} {gua_symbol(gua)}  expected {exp}")
    if not s:
        print("  span NOT FOUND")
        continue
    view = clean(raw[s.start:s.end], keep_notes=True)
    jing = clean(raw[s.start:s.end], keep_notes=False)
    print(f"  span {s.start}..{s.end} = {s.end-s.start} raw chars, "
          f"{len(view.text)} kept, anchor {s.page_anchor}")
    print(f"  labels found (with notes): "
          f"{ {l: view.text.count(l) for l in exp} }")
    print(f"  labels found (經 only)   : { {l: jing.text.count(l) for l in exp} }")
    print(f"\n  full span text (notes kept):\n  {view.text[:700]}")
    # Do the gold 爻辭 for the 'absent' labels appear anywhere in the span?
    print("\n  gold 爻辭 presence:")
    for l in exp:
        g = gold.get(gua, {}).get(l, "")
        if not g:
            continue
        where_j = jing.text.find(g[:6])
        where_v = view.text.find(g[:6])
        print(f"    {l:4} {g[:14]:16} 經@{where_j:5}  withnotes@{where_v:5}")
    # Is the next span's start plausible? Compare with KR1a0007 for the same 卦.
    if work == "KR1a0006":
        o = gua_spans(bodies["KR1a0007"])[0]
        so = next((x for x in o if x.number == gua), None)
        if so:
            ov = clean(bodies["KR1a0007"][so.start:so.end], keep_notes=True)
            print(f"\n  KR1a0007 same 卦: {len(ov.text)} chars, labels "
                  f"{ {l: ov.text.count(l) for l in exp} }")

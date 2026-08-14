"""KR1a0031 verifies 353/377 (93.6%) while its sibling KR1a0032 does 374/380 (98.4%).

Same work (朱熹 本義), same 底本 family (WYG), so the gap should be structural rather than
textual. Classify KR1a0031's failures per category and diff them against KR1a0032's on the
SAME (卦, 爻) so anything shared by both is excluded as a property of the work rather than
of this edition's parsing.
"""
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402
from diagnose_yao import classify  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
PAIR = ["KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ["KR1a0001"] + PAIR}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)


def failures(w):
    raw = bodies[w]
    spans, _ = gua_spans(raw)
    seen = set()
    out = {}
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
                out[(s.number, label)] = ("unlocated", "", "")
                continue
            actual = view.text[rng[0] + len(label):rng[1]]
            cat, ev = classify(want, actual)
            if cat != "ok":
                out[(s.number, label)] = (cat, want, actual)
    return out


f31, f32 = failures("KR1a0031"), failures("KR1a0032")
print(f"KR1a0031 failures {len(f31)}   KR1a0032 failures {len(f32)}")
print(f"categories 31: {Counter(v[0] for v in f31.values()).most_common()}")
print(f"categories 32: {Counter(v[0] for v in f32.values()).most_common()}")

only31 = {k: v for k, v in f31.items() if k not in f32}
shared = {k: v for k, v in f31.items() if k in f32}
print(f"\nshared with sibling (property of the WORK): {len(shared)}")
print(f"unique to KR1a0031 (property of THIS parse): {len(only31)}")
print(f"  categories: {Counter(v[0] for v in only31.values()).most_common()}")

print("\n=== the ones unique to KR1a0031 ===")
for (g, label), (cat, want, actual) in sorted(only31.items())[:30]:
    print(f"\n  卦{g} {label}  [{cat}]")
    print(f"    gold  : {want[:34]}")
    print(f"    actual: {actual[:60]}")
    print(f"    sib ok: {(g, label) not in f32}")

print("\n=== are the unique failures clustered by 卦? ===")
c = Counter(g for (g, _) in only31)
print(f"  {sorted(c.items())}")
print(f"  distinct 卦 affected: {len(c)}")

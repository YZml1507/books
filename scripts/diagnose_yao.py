"""Why does 爻辭 verification sit at 82-89% instead of >=95%?

Coverage is essentially solved (380/380 located in two works, 0 unknown). Accuracy is
not. Rather than loosening the check until the number looks good, classify every
located-but-unverified case so the fix is chosen from evidence:

  inserted   commentary writes 九三曰君子終日… — a particle between label and 爻辭
  variant    an 異體字 still missing from variants.FOLD
  abridged   commentary quotes only the head of the 爻辭
  note_split an inline 注 interrupts the 爻辭 mid-phrase
  strict     matches once punctuation/order is allowed for — my check was too tight
  absent     the 爻辭 genuinely is not there

Emits candidate variant pairs so variants.FOLD grows from measurement, per D-003.
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")
COMMENTARIES = ["KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
PARTICLES = ("曰", "云", "者", "注", "疏", "傳")


def classify(gold: str, actual: str) -> tuple[str, str]:
    """-> (category, evidence)"""
    if not actual:
        return "absent", ""
    head = gold[:6]
    if head in actual:
        return "ok", ""

    # particle inserted immediately after the 爻位 label
    for p in PARTICLES:
        if actual.startswith(p) and head in actual[: len(p) + len(head) + 4]:
            return "inserted", p

    # First divergence. No minimum-prefix guard: an earlier `i >= 3` requirement sent
    # every position-0 substitution to "absent", which is how 苞/包 and 既/旣 stayed
    # invisible for a whole round. A single substitution counts as a variant wherever it
    # sits, PROVIDED the remainder of the phrase then lines up — that proviso is what
    # separates a variant character from a genuinely different text.
    i = 0
    while i < min(len(gold), len(actual)) and gold[i] == actual[i]:
        i += 1
    if i < len(gold) and i < len(actual):
        rest = gold[i + 1:i + 6]
        if not rest or rest in actual[i + 1:i + 12]:
            return "variant", f"{actual[i]}->{gold[i]} after {gold[:i]}"
        return "differs", f"{actual[i]}!={gold[i]} after {gold[:i]}"
    if i >= 3:
        return "abridged", gold[:i]

    # 爻辭 present but not contiguous: all its characters appear in order
    pos, ok = 0, True
    for ch in head:
        at = actual.find(ch, pos)
        if at == -1:
            ok = False
            break
        pos = at + 1
    if ok:
        return "note_split", actual[:pos][:24]

    if gold[:3] and gold[:3] in actual:
        return "strict", gold[:3]
    return "absent", actual[:20]


bodies = {w: work_body(RAW, w) for w in ["KR1a0001"] + COMMENTARIES}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)
print(f"polarity {len(polarity)}/64   gold 卦 {len(gold)}/64")

cats: Counter = Counter()
variant_pairs: Counter = Counter()
samples: dict[str, list] = {}
total = ok_n = 0

for w in COMMENTARIES:
    raw = bodies[w]
    spans, _ = gua_spans(raw)
    seen = set()
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
            if not rng or not want:
                continue
            total += 1
            actual = view.text[rng[0] + len(label):rng[1]]
            cat, ev = classify(want, actual)
            if cat == "ok":
                ok_n += 1
                continue
            cats[cat] += 1
            if cat == "variant" and "->" in ev:
                variant_pairs[ev.split(" after ")[0]] += 1
            samples.setdefault(cat, [])
            if len(samples[cat]) < 4:
                samples[cat].append((w, s.number, label, want[:22], actual[:34]))

print(f"\ncompared {total}  ok {ok_n} ({100*ok_n/max(total,1):.1f}%)  "
      f"failed {total-ok_n}")
print(f"{'category':11} {'n':>5}  share")
for cat, n in cats.most_common():
    print(f"{cat:11} {n:5}  {100*n/max(total-ok_n,1):5.1f}% of failures")

for cat, rows in samples.items():
    print(f"\n--- {cat} ---")
    for w, g, label, want, actual in rows:
        print(f"  {w} 卦{g} {label}")
        print(f"    gold  : {want}")
        print(f"    actual: {actual}")

print("\n=== candidate variant pairs (corpus -> canonical) ===")
for pair, n in variant_pairs.most_common(24):
    a, b = pair.split("->")
    print(f"  {a} (U+{ord(a):04X}) -> {b} (U+{ord(b):04X})   x{n}")

with open(os.path.join(CAT, "yao_diagnosis.json"), "w", encoding="utf-8") as f:
    json.dump({"total": total, "ok": ok_n, "categories": dict(cats),
               "variant_candidates": dict(variant_pairs)}, f,
              ensure_ascii=False, indent=1)
print("\n-> data/catalog/yao_diagnosis.json")

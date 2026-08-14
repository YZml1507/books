"""Decide each KR1a0031 candidate on evidence, and test the 'source mislabels 爻位' claim.

Two questions, both answerable from the corpus:

1. For the 3 unlocated 爻: is the expected label ABSENT while some other label is
   DUPLICATED at exactly the position the gold 爻辭 sits? If so the edition mislabels the
   line, and the honest output is "source anomaly detected", not "unknown".

2. For each proposed fold: how often does the character occur corpus-wide, and in what
   company? A fold is a global rewrite of both corpus and query, so folding 悔->晦 to gain
   one 爻 would rewrite 亢龍有悔 as well. Frequency is the veto.
"""
import glob
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, gua_spans, yao_names  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
bodies = {w: work_body(RAW, w) for w in ["KR1a0001", "KR1a0031", "KR1a0032"]}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)

print("=== Q1: do the 3 unlocated 爻 coincide with a DUPLICATED sibling label? ===")
raw = bodies["KR1a0031"]
spans, _ = gua_spans(raw)
CASES = [(23, "六五"), (57, "九三"), (61, "九二")]
anomalies = []
for g, label in CASES:
    s = next(x for x in spans if x.number == g)
    view = clean(raw[s.start:s.end], keep_notes=False)
    exp = yao_names(polarity[g])
    counts = {l: view.text.count(l) for l in exp}
    want = gold[g][label][:8]
    at = view.text.find(want)
    before = view.text[max(0, at - 2):at] if at >= 0 else ""
    dup = [l for l, n in counts.items() if n > 1]
    print(f"\n  卦{g} expected {label}")
    print(f"    label counts   : {counts}")
    print(f"    duplicated     : {dup}")
    print(f"    gold 爻辭 preceded by: {before!r}   (should be {label!r})")
    ok = counts.get(label, 0) == 0 and before in dup
    print(f"    VERDICT: {'source mislabels this 爻' if ok else 'inconclusive'}")
    if ok:
        anomalies.append((g, label, before))

print("\n=== Q2: corpus frequency of each fold candidate (veto check) ===")
all_text = []
for d in sorted(os.listdir(RAW)):
    p = os.path.join(RAW, d)
    if os.path.isdir(p):
        for f in glob.glob(os.path.join(p, "*.txt")):
            all_text.append(re.sub(r"^#.*$", "", open(f, encoding="utf-8").read(),
                                   flags=re.M))
corpus = "".join(all_text)
print(f"  corpus {len(corpus):,} chars")
CAND = [("昊", "昃"), ("眀", "明"), ("悔", "晦"), ("𠖇", "冥"),
        ("冽", "洌"), ("収", "收"), ("極", "拯"), ("其", "有")]
print(f"\n  {'fold':>9} {'variant n':>10} {'canon n':>9}  {'ratio':>7}  contexts of the variant")
print("  " + "-" * 92)
for a, b in CAND:
    na, nb = corpus.count(a), corpus.count(b)
    ctx = Counter()
    for m in re.finditer(re.escape(a), corpus):
        w = re.sub(r"<pb:[^>]+>|[¶\s　/()（）]", "", corpus[m.start() - 3:m.start() + 4])
        if len(w) >= 4:
            ctx[w] += 1
    r = f"{na/nb:.3f}" if nb else "inf"
    print(f"  {a}->{b:>4} {na:10,} {nb:9,}  {r:>7}  {[c for c, _ in ctx.most_common(4)]}")

print("\n  Read: a HIGH variant count with UNRELATED contexts means the fold would rewrite")
print("  text that has nothing to do with the 爻辭 it was proposed for -> veto.")

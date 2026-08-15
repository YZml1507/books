"""Audit sunls2/zhouyi: how much is pre-modern text and how much is in-copyright commentary?

The repo is 繁體 and well organised, which makes it superficially the most attractive of the
five. But its per-卦 pages interleave four different kinds of material, and one of them names
a LIVING author:

    卦辭 / 象曰            pre-modern, public domain
    白話文解釋              modern paraphrase, authorship unstated
    邵雍河洛理數解卦        attributed to 邵雍 (1011-1077) but as presented is a modern compilation
    傅佩榮解卦手冊          傅佩榮 b. 1950 — IN COPYRIGHT

The repo has no LICENSE file (measured in external_manifest.json). Two distinct risks:

1. Licensing: ingesting in-copyright commentary from an unlicensed repo.
2. Worse for THIS project: a citation system that mixes 白話文 paraphrase with 經文 could
   return a modern paraphrase to a reader who asked for the classical text. That is the same
   failure class as the fabricated 有能乾○九乾 quotation, arriving through the front door.

So: quantify the mix, then check whether the pre-modern layer at least AGREES with our
corpus (which is the only part that could serve as a witness).
"""
import os
import re
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.variants import fold  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
DOCS = os.path.join(ROOT, "data", "external", "zhouyi", "zhouyi-main", "docs")

SECTIONS = ["白話文解釋", "邵雍河洛理數解卦", "傅佩榮解卦手冊", "象曰",
            "時運", "財運", "家宅", "傳統解卦", "北宋易學家邵雍解"]

pages = []
for d in sorted(os.listdir(DOCS)):
    p = os.path.join(DOCS, d, "index.md")
    if os.path.isdir(os.path.join(DOCS, d)) and os.path.exists(p):
        pages.append((d, open(p, encoding="utf-8", errors="replace").read()))
print(f"pages with a 卦 directory: {len(pages)}")

print("\n=== how many pages contain each section? ===")
cnt = Counter()
for _, t in pages:
    for s in SECTIONS:
        if s in t:
            cnt[s] += 1
for s in SECTIONS:
    print(f"  {s:18} {cnt[s]:4} / {len(pages)}")

total = sum(len(t) for _, t in pages)
print(f"\ntotal text: {total:,} chars across {len(pages)} pages")

print("\n=== IN-COPYRIGHT exposure: 傅佩榮 (b. 1950) ===")
fu_chars = 0
for _, t in pages:
    # crude but sufficient: text from the 傅佩榮 heading to the next bold heading block
    for m in re.finditer(r"\*\*傅佩榮解卦手冊\*\*", t):
        seg = t[m.end():m.end() + 1200]
        nxt = re.search(r"\n#|\*\*[^*]{2,12}解", seg)
        fu_chars += len(seg[:nxt.start()] if nxt else seg)
print(f"  pages naming 傅佩榮: {cnt['傅佩榮解卦手冊']}")
print(f"  approx chars under that heading: {fu_chars:,}  "
      f"({100.0*fu_chars/max(total,1):.1f}% of the repo's text)")
print("  repo LICENCE: none (see data/catalog/external_manifest.json)")

print("\n=== does the PRE-MODERN layer agree with our corpus? ===")
bodies = {w: work_body(RAW, w) for w in ["KR1a0001"]}
pol = derive_polarity({w: work_body(RAW, w) for w in
                       ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0031", "KR1a0032"]})
gold = derive_gold(bodies["KR1a0001"], pol)

CJK = re.compile(r"[一-鿿]")


def bare(s):
    return "".join(CJK.findall(fold(s)))


agree = disagree = absent = 0
examples = []
for d, t in pages:
    m = re.match(r"^(\d{2})\.", d)
    if not m:
        continue
    n = int(m.group(1))
    if n not in gold:
        continue
    page = bare(t)
    for label, want in gold[n].items():
        w = bare(want)[:8]
        if len(w) < 6:
            continue
        if w in page:
            agree += 1
        else:
            disagree += 1
            if len(examples) < 6:
                examples.append((n, label, w, page[:0]))
print(f"  gold 爻辭 heads found verbatim in the matching page: {agree}")
print(f"  not found: {disagree}")
print(f"  -> the classical layer is {100.0*agree/max(agree+disagree,1):.1f}% consistent "
      f"with our 底本 after variant folding")
if examples:
    print("  first few not found (may be 爻辭 the page omits, not a disagreement):")
    for n, label, w, _ in examples:
        print(f"    卦{n} {label} {w}")

print("\n=== VERDICT ===")
print("  Usable ONLY as a witness for the pre-modern layer, and only with the modern")
print("  commentary stripped. Not ingestable as a corpus: no licence + in-copyright")
print("  material + paraphrase interleaved with 經文 in the same file.")

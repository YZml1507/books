"""Is citation 0/30 a real index defect, or is my scorer comparing two different spaces?

scripts/eval_g1.py scored citation 0/30, every failure on KR1a0001 and none on any other
work. A defect that respects work boundaries that exactly is more likely to be in the
test than in the index — and this project has the precedent: G6 was first reported at
97.85% error because the test used a single-file offset against a concatenated-work
coordinate system (L-09). So this is checked before anything is "fixed".

Hypothesis: KR1a0001 is the only edition whose text carries punctuation (its 爻辭 print as
「九三：君子終日乾乾，夕惕若厲。无咎。」). unit.text keeps that punctuation, while the file side
was passed through clean(), which DROPS punctuation. Comparing the two then fails on
KR1a0001 alone, for a reason that has nothing to do with citation integrity.

Falsifiable prediction if the hypothesis is right:
  1. KR1a0001 unit texts contain chars from DROP; other works' do not (or far less).
  2. Cleaning BOTH sides makes every one of those 30 units recoverable.
  3. The failure count for other works stays 0 either way.
If prediction 2 fails, the hypothesis is wrong and the index really does have a defect.
"""
from __future__ import annotations

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.anchors import clean  # noqa: E402
from guji.variants import DROP, fold  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

print("=== 1. which works' unit.text carry DROP characters? ===")
rows = c.db.execute("SELECT work_id, text FROM unit").fetchall()
per = {}
for r in rows:
    n = sum(1 for ch in r["text"] if ch in DROP)
    d = per.setdefault(r["work_id"], [0, 0, 0])
    d[0] += 1
    d[1] += n
    d[2] += 1 if n else 0
for w in sorted(per):
    units, drops, withdrop = per[w]
    if drops:
        print(f"  {w}  units={units:5d}  DROP chars={drops:6d}  "
              f"units containing >=1: {withdrop:5d} ({withdrop / units:.1%})")
print("  (works absent from this list have zero DROP chars in unit.text)")

print("\n=== 2. a KR1a0001 unit verbatim, and the same text after clean() ===")
r = c.db.execute("SELECT file, text FROM unit WHERE work_id='KR1a0001' AND addr1=1 "
                 "AND addr2='九三'").fetchone()
print(f"  file      {r['file']}")
print(f"  raw text  {r['text']!r}")
print(f"  cleaned   {clean(r['text'], keep_notes=True).text!r}")


def recoverable(t: str, body: str) -> bool:
    i = 0
    for ch in body:
        if i < len(t) and ch == t[i]:
            i += 1
    return i == len(t)


print("\n=== 3. the 30 citation-question addresses: old check vs both-sides-cleaned ===")
import json
bank = json.load(open(os.path.join(ROOT, "data", "catalog", "eval_g1.json"),
                      encoding="utf-8"))
addrs = [(q["expect"]["addr1"], q["expect"]["addr2"]) for q in bank["questions"]
         if q["category"] == "citation"]
old_bad = new_bad = total = 0
per_work_bad = {}
cache = {}
for a1, a2 in addrs:
    for u in c.db.execute("SELECT work_id, file, text FROM unit WHERE scheme='zhouyi' "
                          "AND addr1=? AND addr2=?", (a1, a2)):
        key = (u["work_id"], u["file"])
        if key not in cache:
            p = os.path.join(RAW, *key)
            body = re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
            cache[key] = (clean(body, keep_notes=True).text, body)
        cleaned_body, _ = cache[key]
        total += 1
        if not recoverable(fold(u["text"]), cleaned_body):          # the old check
            old_bad += 1
            per_work_bad[u["work_id"]] = per_work_bad.get(u["work_id"], 0) + 1
        if not recoverable(clean(u["text"], keep_notes=True).text, cleaned_body):
            new_bad += 1
print(f"  units checked                     {total}")
print(f"  NOT recoverable, old check        {old_bad}   by work: {per_work_bad}")
print(f"  NOT recoverable, both sides clean {new_bad}")
print(f"\n  prediction 2 {'CONFIRMED' if new_bad == 0 else 'REFUTED — real defect'}")
c.close()

"""P-08 scouting: what breaks if the generality books enter the index?

`ingest.build()` walks data/raw/ only; Herodotus and Darwin sit in data/raw_ext/generality/.
Indexing them changes the work count 28 -> 30, and several gates assert against 28. Before
touching build(), enumerate exactly which assertions move, so the change is made with the
blast radius known rather than discovered afterwards.

Read-only: opens the index and reads the gate scripts, writes nothing.
"""
from __future__ import annotations

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402

print("=== 1. where do the two candidate works actually live? ===")
for slug in ("herodotus", "darwin-origin"):
    d = os.path.join(ROOT, "data", "raw_ext", "generality", slug)
    files = sorted(os.listdir(d)) if os.path.isdir(d) else []
    txt = [f for f in files if f.endswith(".txt")]
    print(f"  {slug:14} {len(files)} files, .txt: {txt}")

print("\n=== 2. what does data/raw/ look like (the shape build() expects)? ===")
raw = os.path.join(ROOT, "data", "raw")
sample = sorted(os.listdir(raw))[:3]
for w in sample:
    p = os.path.join(raw, w)
    if os.path.isdir(p):
        fs = sorted(os.listdir(p))
        print(f"  {w}: {len(fs)} files, e.g. {fs[:2]}")
print("  -> build() expects data/raw/<work_id>/*.txt with Kanripo <pb:> tags and ¶ separators")

print("\n=== 3. which gates hard-code 28 works? ===")
pats = [r"\b28\b", r"len\(.*works.*\)\s*==", r"works.*==\s*28"]
for rel in ("scripts/check_provenance.py", "scripts/verify_index.py",
            "scripts/assess_goals.py", "probes/probe_conservation.py",
            "scripts/build_index.py"):
    p = os.path.join(ROOT, rel)
    if not os.path.exists(p):
        continue
    txt = open(p, encoding="utf-8").read()
    hits = []
    for i, line in enumerate(txt.splitlines(), 1):
        if any(re.search(x, line) for x in pats):
            hits.append((i, line.strip()[:88]))
    print(f"\n  {rel}: {len(hits)} lines mention 28 / a work-count assertion")
    for i, line in hits[:6]:
        print(f"    L{i}: {line}")

print("\n=== 4. provenance: would the new works have manifest entries? ===")
import json
cm = json.load(open(os.path.join(ROOT, "data", "catalog", "corpus_manifest.json"),
                    encoding="utf-8"))
ids = {w["id"] for w in cm.get("works", [])}
print(f"  corpus_manifest works: {len(ids)}")
gm_path = os.path.join(ROOT, "data", "catalog", "generality_manifest.json")
if os.path.exists(gm_path):
    gm = json.load(open(gm_path, encoding="utf-8"))
    entries = gm if isinstance(gm, list) else (gm.get("works") or gm.get("books") or [])
    print(f"  generality_manifest entries: {len(entries)}")
    if entries:
        k = entries[0]
        print(f"  keys on first entry: {sorted(k.keys()) if isinstance(k, dict) else type(k)}")
        need = {"source_url", "zip_sha256", "fetched_at", "licence"}
        have = {e.get("id") or e.get("slug"): need & set(e) for e in entries
                if isinstance(e, dict)}
        for kk, vv in list(have.items())[:6]:
            print(f"    {kk}: has {sorted(vv)}  MISSING {sorted(need - vv)}")
else:
    print("  no generality_manifest.json — provenance would be absent (blocks §5 rule)")

print("\n=== 5. current index scheme mix, for comparison after the change ===")
c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))
for r in c.db.execute("SELECT scheme, count(*) n FROM unit GROUP BY scheme"):
    print(f"  {str(r['scheme']):10} {r['n']:6,}")
print(f"  works in index: {c.stats()['works']}")
c.close()

print("""
=== verdict for P-08 ===
The blocking question is NOT the parser — it is provenance and the coordinate system:

  * build() assumes Kanripo shape (<pb:> anchors, ¶ separators). Herodotus has NEITHER; it
    would produce units with page_anchor NULL, and verify_index T7 asserts every unit has an
    anchor. That assertion is correct for Kanripo and wrong as a global invariant — which is
    itself a finding: 「every unit has a page anchor」 is a property of ONE corpus, not of the
    system. Compare U-01: an assumption becomes visible only when a second corpus arrives.
  * §5 requires sha256 / source_url / fetched_at / licence per work before ingest. Whether
    that exists for these books is printed above.
""")

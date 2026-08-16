"""Validated vs merely indexed: the measurement that decides "add more books?"

The question "should we fetch more 古籍, or go deeper on 周易 first" is answerable with data
rather than taste. A work can be in one of several states, and only the last one means the
system has been shown to work on it:

    indexed          rows exist in `unit`
    addressed        has a canonical address (scheme + addr1), so cross-edition join works
    gold-scored      its 爻辭 were checked against an independent base text
    witness-covered  a second edition exists and was diffed against it at shared addresses
    asserted         an acceptance test in verify_index.py actually names it

If most of the corpus sits at `indexed`, adding more books grows the UNVALIDATED surface and
makes every quality number less meaningful. That would settle the question.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402

CAT = os.path.join(ROOT, "data", "catalog")
c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

works = {r["id"]: dict(r) for r in c.db.execute(
    "SELECT id, title, genre FROM work ORDER BY id")}
for wid in works:
    r = c.db.execute(
        "SELECT count(*) n, sum(addr1 IS NOT NULL) a, sum(addr2 IS NOT NULL) y "
        "FROM unit WHERE work_id=?", (wid,)).fetchone()
    works[wid].update(units=r["n"], addressed=r["a"] or 0, yao=r["y"] or 0)

# gold-scored
scored = set()
p = os.path.join(CAT, "alignment_score.json")
if os.path.exists(p):
    scored = set(json.load(open(p, encoding="utf-8")).get("summary", {}))

# witness-covered
witnessed = set()
p = os.path.join(CAT, "quality_report.json")
if os.path.exists(p):
    for k in json.load(open(p, encoding="utf-8")):
        witnessed |= set(k.split("|"))

# named in an acceptance test
vtext = open(os.path.join(ROOT, "scripts", "verify_index.py"), encoding="utf-8").read()
asserted = {w for w in works if w in vtext}

print(f"{'work':10} {'title':14} {'genre':6} {'units':>6} {'addr':>6} "
      f"{'gold':>5} {'witn':>5} {'test':>5}")
print("-" * 68)
tiers = {"indexed_only": [], "addressed": [], "validated": []}
for wid, w in works.items():
    g = "Y" if wid in scored else "-"
    n = "Y" if wid in witnessed else "-"
    a = "Y" if wid in asserted else "-"
    print(f"{wid:10} {(w['title'] or '')[:14]:14} {(w['genre'] or '')[:6]:6} "
          f"{w['units']:6} {w['addressed']:6} {g:>5} {n:>5} {a:>5}")
    if wid in scored or wid in witnessed:
        tiers["validated"].append(wid)
    elif w["addressed"]:
        tiers["addressed"].append(wid)
    else:
        tiers["indexed_only"].append(wid)

tot_units = sum(w["units"] for w in works.values())
val_units = sum(works[x]["units"] for x in tiers["validated"])
print("-" * 68)
print(f"\n=== states ===")
for k, v in tiers.items():
    u = sum(works[x]["units"] for x in v)
    print(f"  {k:14} {len(v):3} works  {u:6,} units  ({100.0*u/tot_units:5.1f}% of units)")

print(f"\n=== what this means for 'add more books?' ===")
print(f"  works whose text is validated by ANY independent check : "
      f"{len(tiers['validated'])}/{len(works)}")
print(f"  units in that set                                      : "
      f"{val_units:,}/{tot_units:,} ({100.0*val_units/tot_units:.1f}%)")
print(f"  works named by an acceptance test                       : "
      f"{len(asserted)}/{len(works)}")

# Western set: fetched but indexed?
gm = os.path.join(CAT, "generality_manifest.json")
if os.path.exists(gm):
    g = json.load(open(gm, encoding="utf-8"))
    print(f"\n=== non-古籍 set ===")
    print(f"  fetched: {len(g)}   indexed into corpus.db: "
          f"{sum(1 for x in g if x['slug'] in works)}")
    for t in (1, 2, 3):
        s = [x["slug"] for x in g if x["tier"] == t]
        print(f"  tier {t}: {len(s)}  {', '.join(s)}")

print(f"\n=== 周易 depth: what is still open on the best-covered work ===")
# Live status, not a stale snapshot: an earlier hardcoded list here claimed the `suspect`
# column and the G5 差异摘要 did not exist — both had already shipped (X-11, guji.compare)
# and the printed "still open" list was misleading (R18a). What follows is derived from the
# artifacts on disk plus the calibration gaps documented in the gate scripts themselves.
qr_low = 0
if os.path.exists(p):
    qr_low = sum(len(v["low"]) for v in json.load(open(p, encoding="utf-8")).values()
                 if isinstance(v, dict) and "low" in v)
open_items = [
    (f"{qr_low} divergent addresses flagged by the quality gate",
     "suspect reaches the citation (X-11), but the damaged readings are unrepaired source damage"),
    ("junk census has no calibrated threshold (Q-06)",
     "check_quality.py prints and records junk rate but never fails on it"),
    ("卦64 tail span differs per edition by convention",
     "excluded from low-coverage counting; exactly one known address"),
]
for a, b in open_items:
    print(f"  - {a:42} {b}")
c.close()

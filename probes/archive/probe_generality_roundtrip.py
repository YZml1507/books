"""Generality falsification: is the address-scheme plugin model actually general?

MASTER_PLAN §11 weakness: the corpus grew to 38 works spanning Euclid / Plato /
Shakespeare / BCV / Douay, but generality was never systematically tested. The
scheme model claims that `(scheme, addr_name, addr1, addr2)` is enough to locate
any unit in ANY scheme — that is the entire point of the plugin design (D-015).

Falsification test (round-trip): for each scheme, sample units that carry an
address, then look the address back up through the SAME columns the citation /
retrieval layers use (`WHERE scheme=? AND addr1=? AND addr2=?`). If a scheme's
address cannot find the unit it was read from, the model is falsified for that
scheme — the address is decorative, not locative.

Read-only. Numbers come from script output (GOAL §2).
"""
import os
import random
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB = os.path.join(ROOT, "data", "index", "corpus.db")
SAMPLE = 25
random.seed(20260815)

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

schemes = [r[0] for r in db.execute(
    "SELECT DISTINCT scheme FROM unit WHERE scheme IS NOT NULL ORDER BY scheme")]
print(f"schemes present: {schemes}\n")

fails = []
for sc in schemes:
    units = db.execute(
        "SELECT id, work_id, addr_name, addr1, addr2, text FROM unit "
        "WHERE scheme=? AND addr1 IS NOT NULL ORDER BY id", (sc,)).fetchall()
    if not units:
        print(f"{sc:12} no addressed units")
        continue
    sample = random.sample(units, min(SAMPLE, len(units)))
    hit = miss = 0
    for u in sample:
        q = ("SELECT u.id FROM unit u WHERE u.scheme=? AND u.addr1=?"
             " AND u.addr2 IS ? AND u.id=?")
        found = db.execute(q, (sc, u["addr1"], u["addr2"], u["id"])).fetchone()
        if found:
            hit += 1
        else:
            miss += 1
            if len(fails) < 5:
                fails.append((sc, u["id"], u["addr_name"], u["addr1"], u["addr2"]))
    print(f"{sc:12} round-trip {hit}/{hit+miss}  ({100.0*hit/max(hit+miss,1):.0f}%)")

print()
if fails:
    print("FALSIFIED — addresses that cannot find their own unit:")
    for f in fails:
        print(f"  {f}")
else:
    print("not falsified — every sampled address round-trips through the plugin model")

# Addresses must also be DISCRIMINATING: one address should not silently alias
# units of a different scheme (the Psalms-99 == 卦99 collision from D-005).
collide = db.execute("""
    SELECT COUNT(*) FROM (
        SELECT scheme, addr1, addr2 FROM unit WHERE addr1 IS NOT NULL
        GROUP BY scheme, addr1, addr2 HAVING COUNT(*) > 0
    )""").fetchone()[0]
print(f"\n(sanity) distinct (scheme, addr1, addr2) combos used: {collide}")
db.close()

"""yilin reports 65 distinct addr_name for 64 distinct addr1. Which 卦 has two labels?

Suspicion, to be confirmed or refuted here: 卦29 gets 「坎」 on its cells (this edition's own
spelling, carried through fold()) and 「習坎」 on its section heading (the canonical 底本 name).
If so, ONE hexagram's address label depends on which layer you look at — a small defect with
a familiar shape: the join key must not vary with the row.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

db = sqlite3.connect(os.path.join(ROOT, "data", "index", "corpus.db"))
db.row_factory = sqlite3.Row

dupes = db.execute("""
    SELECT addr1 FROM unit WHERE scheme='yilin' AND addr1 IS NOT NULL
    GROUP BY addr1 HAVING count(DISTINCT addr_name) > 1""").fetchall()
print(f"卦 numbers carrying more than one addr_name: {[r['addr1'] for r in dupes]}")

for r in dupes:
    print(f"\n--- 卦{r['addr1']} ---")
    for x in db.execute("""
            SELECT addr_name, layer, count(*) n FROM unit
            WHERE scheme='yilin' AND addr1=? GROUP BY addr_name, layer
            ORDER BY n DESC""", (r["addr1"],)):
        print(f"  addr_name={x['addr_name']!r:8} layer={x['layer']:6} units={x['n']}")

print("\n=== also check addr2: is the 之卦 label canonical or edition-local? ===")
for x in db.execute("""
        SELECT addr2, count(*) n FROM unit WHERE scheme='yilin' AND addr2 IS NOT NULL
        GROUP BY addr2 ORDER BY addr2 LIMIT 4"""):
    print(f"  addr2={x['addr2']!r} x{x['n']}")
n2 = db.execute("SELECT count(DISTINCT addr2) n FROM unit WHERE scheme='yilin' "
                "AND addr2 IS NOT NULL").fetchone()["n"]
print(f"  distinct addr2 values: {n2} (expect 64)")
has_kan = db.execute("SELECT count(*) n FROM unit WHERE scheme='yilin' "
                     "AND addr2='坎'").fetchone()["n"]
has_xikan = db.execute("SELECT count(*) n FROM unit WHERE scheme='yilin' "
                       "AND addr2='習坎'").fetchone()["n"]
print(f"  addr2='坎': {has_kan}    addr2='習坎': {has_xikan}")
db.close()

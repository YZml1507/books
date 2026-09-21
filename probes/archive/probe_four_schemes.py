"""Are the four address schemes actually DIFFERENT shapes, or four spellings of one shape?

「系统通用」 is the claim at stake, and counting schemes does not support it: four parsers over
four books with the same underlying address shape would prove only that the code was copied
four times. U-01 established the honest way to ask this — try to break the schema and see
whether it holds — so this probe compares the schemes' SHAPES against the column model
`(scheme, addr_name, addr1, addr2)` and reports what each one stresses.

Read-only.
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402

c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

print("=" * 78)
print("shape of each address scheme, as actually stored")
print("=" * 78)
rows = c.db.execute("""
    SELECT scheme, count(*) units,
           count(DISTINCT addr_name) names,
           count(DISTINCT addr1) a1,
           count(DISTINCT addr2) a2,
           sum(addr2 IS NULL) a2_null,
           min(addr1) lo, max(addr1) hi
    FROM unit GROUP BY scheme ORDER BY units DESC""").fetchall()
print(f"{'scheme':10} {'units':>7} {'names':>6} {'addr1':>6} {'addr2':>6} "
      f"{'a2 NULL':>8}  addr1 range")
for r in rows:
    print(f"{str(r['scheme']):10} {r['units']:7,} {r['names']:6} {r['a1']:6} "
          f"{r['a2']:6} {r['a2_null']:8,}  {r['lo']}..{r['hi']}")

print("\n=== what is addr2, per scheme? this is where the shapes differ ===")
for scheme in ("zhouyi", "yilin"):
    vals = [r["addr2"] for r in c.db.execute(
        "SELECT DISTINCT addr2 FROM unit WHERE scheme=? AND addr2 IS NOT NULL "
        "ORDER BY addr2 LIMIT 8", (scheme,))]
    numeric = all(str(v).isdigit() for v in vals) if vals else None
    print(f"  {scheme:8} sample {vals}")
    print(f"           numeric? {numeric}  -> "
          f"{'an ordinal' if numeric else 'a LABEL, so TEXT is required not INTEGER'}")

print("""
=== the four shapes, and what each one stresses in the column model ===

  zhouyi   addr_name=卦名  addr1=卦號 1..64   addr2=爻位 LABEL (九三 / 用九)
           Stresses: addr2 cannot be an INTEGER. 用九 and 用六 are real addressable units
           with no numeric position. This is why addr2 is TEXT.

  bcv      addr_name=book  addr1=chapter      addr2=verse (ordinal)
           Stresses: THREE levels in two columns + a name. Also the only scheme whose
           addr_name space is open (66 books) rather than a fixed 64.

  yilin    addr_name=本卦  addr1=本卦號        addr2=之卦 NAME
           Stresses: addr1 and addr2 are TWO POSITIONS OF THE SAME KIND OF ENTITY, not
           container+position. A 64x64 matrix, not a hierarchy. This is the shape that
           would have been impossible under the old 卦/爻 column schema even though it is
           also about 卦.

  booksec  addr_name=BOOK  addr1=book         addr2=section
           Stresses: addr2 UNUSED at one level (Darwin: 14 chapters, addr2 NULL) while the
           same scheme uses it at another (Herodotus: 763 sections). One scheme, two depths.

Four different shapes, one unchanged set of columns. That is the return on D-016 — and the
reason the count of schemes is not the evidence; the DISSIMILARITY is.
""")

print("=== NULL addr2 is a first-class value, not a gap ===")
for r in c.db.execute("""
        SELECT scheme, layer, count(*) n FROM unit
        WHERE addr1 IS NOT NULL AND addr2 IS NULL
        GROUP BY scheme, layer ORDER BY n DESC LIMIT 6"""):
    print(f"  {r['scheme']:8} layer={r['layer']:6} {r['n']:5,} units addressed to a "
          f"container with no finer position")
c.close()

"""Check which works have all-NULL page_anchor (unanchored)."""
import sqlite3
c = sqlite3.connect("data/index/corpus.db")
r = c.execute("""
    SELECT work_id, count(*) n, sum(page_anchor IS NULL) no_anchor
    FROM unit GROUP BY work_id
    ORDER BY work_id
""").fetchall()
print("works with ALL units unanchored (no_anchor == n):")
for wid, n, no_anchor in r:
    if no_anchor == n:
        print(f"  {wid:<30} n={n}  no_anchor={no_anchor}")
print()
print("works with SOME units unanchored (partial):")
for wid, n, no_anchor in r:
    if 0 < no_anchor < n:
        print(f"  {wid:<30} n={n}  no_anchor={no_anchor}")

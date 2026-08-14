"""G4: multi-hop retrieval over source-printed links, with the chain displayed.

    python scripts/eval_g4.py

Criterion: 「多跳检索：由 A 单元发现的实体触发 B 单元检索，链路可展示」.

The links are NOT inferred. 焦氏易林 annotates cells with 「A之B」, meaning this cell's 林辭 also
stands at that cell — an editorial cross-reference printed in the book. Extracting it is
reading, so the link table lives in corpus.db as Source knowledge; a similarity-derived link
would belong in knowledge.db instead (D-023). That distinction is the point of G8 and this is
the first place it does real work.

Pre-registered acceptance criteria (fixed before the first run):
  1. >= 300 links extracted, and 100% of them resolve to a real (本卦, 之卦) cell that exists
     in the index. A dangling link is a citation to nothing.
  2. Every link's source text must ACTUALLY CONTAIN the printed reference — asserting on the
     returned text, not on the row count (§3).
  3. A 2-hop traversal must be demonstrable and the chain printable, with every hop carrying
     its own citation.
  4. The traversal must terminate: no infinite walk on a cycle.
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.variants import fold  # noqa: E402

c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))
fails = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


print("=" * 78)
print("G4: multi-hop over source-printed cross-references")
print("=" * 78)

n_links = c.db.execute("SELECT count(*) n FROM link").fetchone()["n"]
kinds = c.db.execute("SELECT kind, count(*) n FROM link GROUP BY kind").fetchall()
print(f"\nlinks: {n_links}   kinds: {[(r['kind'], r['n']) for r in kinds]}")

print("\n=== 1. every link resolves to a real unit on both ends ===")
dangling = c.db.execute("""
    SELECT count(*) n FROM link l
    LEFT JOIN unit s ON s.id = l.src_unit
    LEFT JOIN unit d ON d.id = l.dst_unit
    WHERE s.id IS NULL OR d.id IS NULL""").fetchone()["n"]
check("no dangling link", dangling == 0, f"{dangling} dangling")
check("enough links to be a graph", n_links >= 300, f"{n_links} links")

print("\n=== 2. the printed reference really occurs in the source unit's text ===")
# The link was read out of a 注 attached to the cell. So the reference string must appear in
# SOME unit at the source address — assert against text, never against the row count.
rows = c.db.execute("""
    SELECT l.id, l.note, l.src_unit, l.dst_unit,
           s.addr1 s1, s.addr2 s2, s.work_id, d.addr1 d1, d.addr2 d2
    FROM link l JOIN unit s ON s.id = l.src_unit JOIN unit d ON d.id = l.dst_unit
    LIMIT 400""").fetchall()
# addr2 is the CANONICAL 卦名 (the cross-work join key), but the source text prints THIS
# EDITION's spelling — 焦氏易林 writes 坎 where the 底本 writes 習坎. So the support test must
# accept either form, or it would fail on 卦29 alone and the failure would look like a broken
# link rather than an orthographic difference. Both spellings are derived, not typed: the
# canonical set from KR1a0001's headings, the aliases from yilin.NAME_ALIASES.
from guji.ingest import derive_gua_names  # noqa: E402
from guji.yilin import NAME_ALIASES, name_table  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

_canon = derive_gua_names(work_body(os.path.join(ROOT, "data", "raw"), "KR1a0001"))
_alts: dict[str, set[str]] = {}
for _num, _nm in _canon.items():
    _alts.setdefault(fold(_nm), set()).add(fold(_nm))
for _alias, _num in NAME_ALIASES.items():
    if _num in _canon:
        _alts.setdefault(fold(_canon[_num]), set()).add(fold(_alias))
del name_table

bad = []
for r in rows:
    at_src = c.db.execute(
        "SELECT text FROM unit WHERE work_id=? AND addr1=? AND addr2=?",
        (r["work_id"], r["s1"], r["s2"])).fetchall()
    blob = fold("".join(x["text"] for x in at_src))
    want = fold(str(r["d2"]))
    forms = _alts.get(want, {want})
    if not any(f in blob for f in forms):
        bad.append((r["id"], r["note"], sorted(forms), blob[:40]))
check("link target is named in the source cell's own text", not bad,
      f"{len(bad)} of {len(rows)} checked links not textually supported")
for b in bad[:4]:
    print(f"      link {b[0]} note={b[1]!r} target={b[2]!r} not in {b[3]!r}")

print("\n=== 3. a 2-hop chain, with a citation at every hop ===")
seed = c.db.execute("""
    SELECT l.src_unit FROM link l
    JOIN link l2 ON l2.src_unit = l.dst_unit
    LIMIT 1""").fetchone()
if not seed:
    check("a 2-hop chain exists", False, "no unit with an outgoing link whose target also links")
else:
    start = seed["src_unit"]
    seen = {start}
    chain = [start]
    cur = start
    for _ in range(4):
        nxt = c.db.execute("SELECT dst_unit, note FROM link WHERE src_unit=? "
                           "AND dst_unit NOT IN (SELECT value FROM json_each(?)) LIMIT 1",
                           (cur, __import__("json").dumps(list(seen)))).fetchone()
        if not nxt:
            break
        cur = nxt["dst_unit"]
        seen.add(cur)
        chain.append(cur)
    print(f"      chain length {len(chain)} units")
    for i, uid in enumerate(chain):
        h = c.db.execute("""
            SELECT u.work_id, w.title, u.addr_name, u.addr1, u.addr2, u.page_anchor,
                   u.file, u.layer, u.text
            FROM unit u JOIN work w ON w.id = u.work_id WHERE u.id=?""",
                         (uid,)).fetchone()
        print(f"        hop {i}: {h['title']} {h['addr_name']}之{h['addr2']} "
              f"@{h['page_anchor']} ({h['file']})")
        print(f"                {h['text'][:64]}")
    check("2-hop traversal with displayable chain", len(chain) >= 3,
          f"{len(chain)} hops")

print("\n=== 4. traversal terminates on a cycle ===")
# Walk with a visited set, bounded. A cycle must not hang.
def walk(uid: int, depth: int = 6) -> list[int]:
    seen_, out, frontier = {uid}, [uid], [uid]
    for _ in range(depth):
        nxt = []
        for u in frontier:
            for r in c.db.execute("SELECT dst_unit FROM link WHERE src_unit=?", (u,)):
                if r["dst_unit"] not in seen_:
                    seen_.add(r["dst_unit"])
                    out.append(r["dst_unit"])
                    nxt.append(r["dst_unit"])
        frontier = nxt
        if not frontier:
            break
    return out

cyc = c.db.execute("SELECT a.src_unit u FROM link a JOIN link b "
                   "ON b.src_unit = a.dst_unit AND b.dst_unit = a.src_unit "
                   "LIMIT 1").fetchone()
if cyc:
    reach = walk(cyc["u"])
    check("cycle does not hang the walk", len(reach) > 1,
          f"mutual pair found at unit {cyc['u']}, reached {len(reach)} units")
else:
    any_src = c.db.execute("SELECT src_unit u FROM link LIMIT 1").fetchone()
    reach = walk(any_src["u"]) if any_src else []
    check("bounded walk terminates", bool(reach), f"reached {len(reach)} units")

print("\n=== reach distribution: how much of the matrix is connected? ===")
srcs = c.db.execute("SELECT count(DISTINCT src_unit) n FROM link").fetchone()["n"]
dsts = c.db.execute("SELECT count(DISTINCT dst_unit) n FROM link").fetchone()["n"]
cells = c.db.execute("SELECT count(*) n FROM unit WHERE scheme='yilin' "
                     "AND layer='林辭'").fetchone()["n"]
print(f"  yilin cells {cells:,}   cells with an outgoing link {srcs}   "
      f"cells targeted {dsts}")

print("\n" + "=" * 78)
print("G4 = PASS" if not fails else f"G4 = FAIL: {fails}")
c.close()
sys.exit(1 if fails else 0)

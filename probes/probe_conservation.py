"""Text conservation: does the index still contain every CJK char of the source?

The merge rewrite cut units 35,978 -> 8,611. A drop that large is either the intended
effect (fuller blocks) or silent data loss, and unit counts cannot tell the two apart.
So compare CJK multisets: source vs index, per work.

Losses that are EXPECTED and must be accounted for explicitly:
  * `&KR0658;`-style entity refs for glyphs with no code point (D-003) — their letters are
    ASCII, so they do not enter the CJK count anyway.
  * nothing else. Any CJK char in the source must appear in some unit.
"""
import collections
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.ingest import load_work  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")


def cjk(s: str) -> collections.Counter:
    return collections.Counter(c for c in s
                               if "一" <= c <= "鿿" or ord(c) > 0xFFFF)


db = sqlite3.connect(os.path.join(ROOT, "data", "index", "corpus.db"))
db.row_factory = sqlite3.Row
works = [r[0] for r in db.execute("SELECT id FROM work ORDER BY id")]

print(f"{'work':10} {'src_cjk':>9} {'idx_cjk':>9} {'delta':>8} {'missing':>8} {'extra':>7}")
print("-" * 56)
tot_src = tot_idx = tot_missing = tot_extra = 0
worst = []
for w in works:
    raw, _ = load_work(RAW, w)
    src = cjk(raw)
    idx = collections.Counter()
    for r in db.execute("SELECT text FROM unit WHERE work_id=?", (w,)):
        idx += cjk(r["text"])
    missing = src - idx      # chars the index lacks
    extra = idx - src        # chars the index invented
    ns, ni = sum(src.values()), sum(idx.values())
    nm, nx = sum(missing.values()), sum(extra.values())
    tot_src += ns
    tot_idx += ni
    tot_missing += nm
    tot_extra += nx
    print(f"{w:10} {ns:9} {ni:9} {ni-ns:8} {nm:8} {nx:7}")
    if nm or nx:
        worst.append((w, missing.most_common(6), extra.most_common(6)))
print("-" * 56)
print(f"{'TOTAL':10} {tot_src:9} {tot_idx:9} {tot_idx-tot_src:8} {tot_missing:8} {tot_extra:7}")
print(f"\nmissing rate {100.0*tot_missing/tot_src:.4f}%   "
      f"invented rate {100.0*tot_extra/tot_src:.4f}%")

for w, miss, ext in worst[:6]:
    print(f"\n  {w} missing={miss}")
    print(f"  {w} extra  ={ext}")

print("\n=== duplication: index should not contain a char many times over ===")
print("(ratio > 1 means text is emitted more than once; 注 nested in 經 would do that)")
print(f"  overall ratio {tot_idx/tot_src:.4f}")

print("\n=== contiguity: raw_start..raw_end must bound the text it claims ===")
bad = 0
checked = 0
for w in works:
    raw, _ = load_work(RAW, w)
    for r in db.execute("SELECT raw_start, raw_end, text FROM unit WHERE work_id=? "
                        "ORDER BY raw_start LIMIT 400", (w,)):
        checked += 1
        window = cjk(raw[r["raw_start"]:r["raw_end"]])
        if cjk(r["text"]) - window:
            bad += 1
print(f"  {checked} units checked, {bad} whose text is not inside its own raw range")
db.close()

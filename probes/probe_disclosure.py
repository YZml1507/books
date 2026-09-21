"""X-10 / X-11: what exactly would a `contiguous` and a `suspect` column say?

The ledger claims 2,134 of 4,000 sampled units (53%) are an ordered SUBSEQUENCE of their
raw_start..raw_end range rather than a contiguous substring, because merge_units joins 經
runs across an interleaved 注. Citation-honest, but the reader is not told that material was
skipped. Before adding a column, measure it exactly rather than trusting the figure:

  1. exact counts over ALL units, not a 4,000 sample, per work and per layer;
  2. how big the skipped material actually is (a 1-char gap and a 900-char gap are not the
     same disclosure);
  3. whether `contiguous` is derivable at INGEST time without a second pass over the raw
     body — if it is not cheap, the column is not worth it;
  4. for X-11: which units overlap a known-damaged region, from quality_report.json, so
     `suspect` is populated from the existing gate rather than from a new guess.

Pre-registered: if `contiguous` turns out to be ~100% or ~0%, the column carries no
information and X-10 should be REJECTED rather than implemented for its own sake.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.evalset import in_space, raw_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

print("=== 1. contiguous vs subsequence, EXACT over every unit ===")
rows = c.db.execute("SELECT id, work_id, file, raw_start, raw_end, layer, addr2, text "
                    "FROM unit ORDER BY work_id, raw_start").fetchall()
bodies: dict[str, str] = {}
stat = Counter()
per_work: dict[str, Counter] = {}
per_layer: dict[str, Counter] = {}
gaps: list[tuple[int, str, int, str]] = []
neither = []
for r in rows:
    w = r["work_id"]
    if w not in bodies:
        bodies[w] = raw_body(RAW, w)
    win = in_space(bodies[w][r["raw_start"]:r["raw_end"]], "folded_notes")
    t = in_space(r["text"], "folded_notes")
    pw = per_work.setdefault(w, Counter())
    pl = per_layer.setdefault(r["layer"], Counter())
    if not t:
        stat["empty"] += 1
        continue
    if t in win:
        stat["contiguous"] += 1
        pw["contiguous"] += 1
        pl["contiguous"] += 1
        continue
    i = 0
    for ch in win:
        if i < len(t) and ch == t[i]:
            i += 1
    if i == len(t):
        stat["subsequence"] += 1
        pw["subsequence"] += 1
        pl["subsequence"] += 1
        skipped = len(win) - len(t)
        gaps.append((skipped, w, r["id"], r["layer"]))
    else:
        stat["neither"] += 1
        pw["neither"] += 1
        pl["neither"] += 1
        if len(neither) < 5:
            neither.append((w, r["file"], r["raw_start"], t[:40], win[:60]))

tot = sum(stat.values())
for k in ("contiguous", "subsequence", "neither", "empty"):
    print(f"  {k:12s} {stat[k]:6,}  {stat[k] / max(tot, 1):6.1%}")
print(f"  total        {tot:6,}")
if neither:
    print("  !! units whose text is NOT recoverable from their own range:")
    for n in neither:
        print(f"     {n[0]}/{n[1]}@{n[2]}  want={n[3]}  win={n[4]}")

print("\n=== 2. per work / per layer ===")
print(f"  {'work':10s} {'contig':>7} {'subseq':>7} {'neither':>8}  subseq%")
for w in sorted(per_work):
    d = per_work[w]
    n = d["contiguous"] + d["subsequence"] + d["neither"]
    print(f"  {w:10s} {d['contiguous']:7,} {d['subsequence']:7,} {d['neither']:8,}"
          f"  {d['subsequence'] / max(n, 1):6.1%}")
print(f"\n  {'layer':10s} {'contig':>7} {'subseq':>7} {'neither':>8}  subseq%")
for lay in sorted(per_layer):
    d = per_layer[lay]
    n = d["contiguous"] + d["subsequence"] + d["neither"]
    print(f"  {lay:10s} {d['contiguous']:7,} {d['subsequence']:7,} {d['neither']:8,}"
          f"  {d['subsequence'] / max(n, 1):6.1%}")

print("\n=== 3. HOW MUCH is skipped (this decides whether disclosure is meaningful) ===")
gaps.sort(reverse=True)
if gaps:
    sizes = sorted(g[0] for g in gaps)
    def pct(p):
        return sizes[min(int(len(sizes) * p), len(sizes) - 1)]
    print(f"  skipped chars: min={sizes[0]}  p25={pct(.25)}  median={pct(.5)}  "
          f"p75={pct(.75)}  p90={pct(.9)}  max={sizes[-1]}")
    print(f"  units skipping >= 1 char: {sum(1 for s in sizes if s >= 1):,}")
    print(f"  units skipping >= 20 chars: {sum(1 for s in sizes if s >= 20):,}")
    print(f"  units skipping >= 100 chars: {sum(1 for s in sizes if s >= 100):,}")
    print("  largest skips:")
    for s, w, uid, lay in gaps[:6]:
        print(f"    {s:6,} chars  {w} unit {uid} layer={lay}")

print("\n=== 4. is `contiguous` derivable at ingest time? ===")
# merge_units is the only place a gap can be introduced: it fuses same-key runs that are
# separated by other material. So a unit is non-contiguous exactly when it absorbed a run
# that did not start where the previous one ended. That is knowable during the merge, with
# no second pass over the raw body.
print("  merge_units joins runs with the SAME (file, layer, 卦, 爻) key, skipping whatever")
print("  sits between them. So non-contiguity is decidable inside the merge loop:")
print("    a block is non-contiguous iff, when absorbing the next run, run.start != block.end")
print("  -> derivable at ingest, O(1) per merge, no extra pass. Column is cheap.")

print("\n=== 5. X-11: which units overlap a KNOWN damaged region? ===")
qp = os.path.join(ROOT, "data", "catalog", "quality_report.json")
q = json.load(open(qp, encoding="utf-8")) if os.path.exists(qp) else {}
flagged = []
for pair, d in q.items():
    # R228z续3：quality_report.json 后来混进了非 work|addr 键（汇总/meta），
    # 裸 split('|') 直接崩——历史遗留 B-011，见到非对键跳过。
    if "|" not in pair:
        continue
    a, b = pair.split("|")
    for low in d["low"]:
        flagged.append((a, low["gua"], low["yao"], low["verdict"], low["coverage"]))
print(f"  quality_report.json flags {len(flagged)} (work, 卦, 爻) addresses:")
for a, g, y, v, cov in flagged:
    n = c.db.execute("SELECT count(*) n FROM unit WHERE work_id=? AND addr1=? AND addr2=?",
                     (a, g, y)).fetchone()["n"]
    print(f"    {a} 卦{g:>2}{y:4s} {v:22s} coverage={cov:.3f}  units at that address: {n}")
tot_flagged = sum(c.db.execute("SELECT count(*) n FROM unit WHERE work_id=? AND addr1=? "
                               "AND addr2=?", (a, g, y)).fetchone()["n"]
                  for a, g, y, _, _ in flagged)
print(f"  -> a `suspect` column would mark {tot_flagged} units out of {tot:,} "
      f"({tot_flagged / max(tot, 1):.2%})")
print("  NOTE: 卦19 (KR1a0006 missing text, 335 vs 1804 chars) is recorded in")
print("  quality_report only via its 爻 rows; check whether it appears above at all.")
c.close()

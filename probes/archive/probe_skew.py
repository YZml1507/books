"""Prove the offset skew in ingest._iter_pieces and measure how many units it corrupts.

Hypothesis: _iter_pieces yields the RAW offset of a piece but the STRIPPED text of that
piece. parse_units then computes address-boundary cuts in raw coordinates and applies them
as indices into the stripped text. Every Kanripo piece begins with "\\n" (the separator is
"¶\\n"), so the skew is >= 1 for essentially every piece, and larger when a <pb:> tag
sits inside.

Predicted symptoms:
  1. a unit addressed 爻=X begins at the SECOND char of the label X  (documented in D-008
     as cosmetic)
  2. the leaked first char of the NEXT label lands at the end of the previous unit, after
     the note text that follows it  -> `有能乾○九乾惕厲之象` in KR1a0032  (NOT cosmetic:
     the quoted passage contains characters the source does not have there)
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import PB_RE  # noqa: E402
from guji.ingest import AddrIndex, ZHOUYI_WORKS, load_work  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORKS = [w for w in ZHOUYI_WORKS if os.path.isdir(os.path.join(RAW, w))]
polarity = derive_polarity({w: work_body(RAW, w) for w in WORKS})

print("=== 1. skew per piece (chars removed before the piece's first kept char) ===")
print(f"{'work':10} {'pieces':>7} {'skew>0':>7} {'%':>6} {'max':>5}  {'cuts_inside':>11} "
      f"{'cuts_misplaced':>14}")
print("-" * 74)
total_bad = 0
for w in WORKS:
    raw, _ = load_work(RAW, w)
    addr = AddrIndex(raw, polarity, True)
    pieces = skewed = cuts_in = cuts_bad = 0
    mx = 0
    pos = 0
    for piece in raw.split("¶"):
        start = pos
        pos += len(piece) + 1
        stripped = PB_RE.sub("", piece).strip().strip("　")
        if not stripped:
            continue
        pieces += 1
        # skew = offset of the first kept char inside the raw piece
        skew = piece.find(stripped[0]) if stripped else 0
        # more robust: length of the prefix removed by pb-stripping + strip()
        m = re.match(r"(?:<pb:[^>]+>|[\s　¶])*", piece)
        skew = len(m.group()) if m else 0
        if skew:
            skewed += 1
            mx = max(mx, skew)
        bs = addr.boundaries_within(start, start + len(piece))
        for b in bs:
            cuts_in += 1
            if skew:  # the cut index (b-start) lands `skew` chars too far right
                cuts_bad += 1
    total_bad += cuts_bad
    pct = 100.0 * skewed / pieces if pieces else 0
    print(f"{w:10} {pieces:7} {skewed:7} {pct:5.1f}% {mx:5}  {cuts_in:11} {cuts_bad:14}")
print("-" * 74)
print(f"total misplaced address cuts: {total_bad}")

print("\n=== 2. the KR1a0032 乾九三 case, char by char ===")
raw, _ = load_work(RAW, "KR1a0032")
addr = AddrIndex(raw, polarity, True)
i = raw.find("性體剛健")          # 性體剛健
lo, hi = i - 200, i + 260
pos = 0
for piece in raw.split("¶"):
    start = pos
    pos += len(piece) + 1
    if start + len(piece) < lo or start > hi:
        continue
    stripped = PB_RE.sub("", piece).strip().strip("　")
    if not stripped:
        continue
    m = re.match(r"(?:<pb:[^>]+>|[\s　¶])*", piece)
    skew = len(m.group()) if m else 0
    bs = addr.boundaries_within(start, start + len(piece))
    print(f"\n  piece @{start} skew={skew} raw={piece[:70]!r}")
    for b in bs:
        cut_wrong = b - start
        cut_right = cut_wrong - skew
        print(f"    boundary raw@{b} -> addr {addr.lookup(b)}")
        print(f"      cut used  ={cut_wrong:3}  splits stripped as "
              f"{stripped[max(0,cut_wrong-6):cut_wrong]!r} | "
              f"{stripped[cut_wrong:cut_wrong+6]!r}")
        print(f"      cut needed={cut_right:3}  would split as "
              f"{stripped[max(0,cut_right-6):cut_right]!r} | "
              f"{stripped[cut_right:cut_right+6]!r}")

print("\n=== 3. does the corruption reach the shipped index? ===")
import sqlite3  # noqa: E402

db = sqlite3.connect(os.path.join(ROOT, "data", "index", "corpus.db"))
db.row_factory = sqlite3.Row
r = db.execute("SELECT text, page_anchor FROM unit WHERE work_id='KR1a0032' AND gua=1 "
               "AND yao='九三'").fetchall()
for row in r:
    print(f"  indexed: {row['text'][:120]}")
    print(f"  source has 有能乾乾惕: "
          f"{'有能乾乾惕' in raw.replace('¶','').replace(chr(10),'')}")

print("\n=== 4. invariant: a 爻-addressed unit should START with its 爻位 label ===")
print(f"{'work':10} {'checked':>8} {'starts_with_label':>18} {'off_by_one':>11}")
print("-" * 52)
for w in WORKS:
    rows = db.execute(
        "SELECT gua, yao, text, min(raw_start) FROM unit WHERE work_id=? AND yao IS NOT NULL"
        " GROUP BY gua, yao ORDER BY gua, min(raw_start)", (w,)).fetchall()
    ok = off1 = 0
    for row in rows:
        t, y = row["text"], row["yao"]
        if t.startswith(y):
            ok += 1
        elif len(y) > 1 and t.startswith(y[1:]):
            off1 += 1
    if rows:
        print(f"{w:10} {len(rows):8} {ok:18} {off1:11}")
db.close()

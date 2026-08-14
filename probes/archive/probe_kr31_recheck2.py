"""The three withdrawn claims, retested correctly.

clean() FOLDS as it goes, so a needle taken from the raw text can miss in the cleaned
view purely because the needle itself was never folded (恒->恆, 懐->懷). That is my bug,
not the corpus's. Fold both sides and retest. Same lesson as variants.py's opening
comment: an asymmetric fold application is a silent correctness bug.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, fold  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
WORKS = ["KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in WORKS}
views = {w: clean(r, keep_notes=True).text for w, r in bodies.items()}

CLAIMS = [
    ("卦5 初九", "利用怕 vs 利用恆", "需于郊不犯難行也利用恒无咎"),
    ("卦56 六二", "旅即懷 vs 旅即次懷", "即次則安懐資則裕"),
    ("卦51 六三", "震蘓蘓行 vs 震蘇蘇震行", "蘇蘇緩散自失之状"),
]
print("=" * 88)
print("retest with the needle FOLDED (clean() folds; the needle must too)")
print("=" * 88)
for cell, what, needle in CLAIMS:
    f = fold(needle)
    print(f"\n{cell}  ({what})")
    print(f"  needle raw   : {needle!r}")
    print(f"  needle folded: {f!r}")
    for w in WORKS:
        print(f"    {w}: in cleaned view = {f in views[w]}")

print("\n" + "=" * 88)
print("卦51 六三: does KR1a0031 write 蘇 anywhere, or only 蘓?")
print("=" * 88)
for w in WORKS:
    r = bodies[w]
    print(f"  {w}: 蘓(U+8613)={r.count('蘓')}  蘇(U+8607)={r.count('蘇')}")
    for m in list(re.finditer("[蘓蘇]", r))[:6]:
        print(f"      {m.group()} @{m.start()}: "
              f"...{re.sub(r'<pb:[^>]*>|[¶\n]', '', r[m.start()-14:m.start()+18])}...")

print("\n" + "=" * 88)
print("卦51 六三 in full: 0031 經 vs 0031 注 vs 0032")
print("=" * 88)
for w in WORKS:
    r = bodies[w]
    at = r.find("蘓") if w == "KR1a0031" else r.find("蘇蘇")
    if at != -1:
        print(f"  {w}: ...{re.sub(r'<pb:[^>]*>|[¶\n]', '', r[max(0,at-30):at+150])}...")

print("\n" + "=" * 88)
print("KR1a0006 卦62 小過: why FIX-C cannot recover it")
print("=" * 88)
r = work_body(RAW, "KR1a0006")
at = 55179
print(f"  @{at}: ...{re.sub(r'<pb:[^>]*>|[¶\n]', '', r[at:at+60])}...")
print("  note reads 良下/震上 — 良 is not a trigram name, so lines_from_trigrams returns")
print("  None and the retag declines. This is the same source error D-006 already records")
print("  for 卦12. FIX-C is correctly conservative here rather than guessing 艮.")

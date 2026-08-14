"""Detect silently corrupted regions inside the Kanripo corpus itself.

Motivation, found by hand: KR1a0006 卦61 中孚 reads

    丸五有孚寧如无咎窣如者駝韋信之蘇也麨中請以相交之時層専但峽為窶拘之王信何可舍故有孚擊如乃得无槃也
    上九翰青登于天貞凶輪高飛也狀音堵昔莊而寳才從之謂也届卦之上處信芝絃信終剛唐志罵內

where the text should read 九五有孚攣如无咎 … 上九翰音登于天貞凶 翰高飛也. 丸/九, 青/音,
輪/翰, 窣/攣 are visually-similar substitutions: the OCR signature, not woodblock variance.
D-001 established this failure mode for PDFs; the finding here is that it is ALSO present
in Kanripo plain text, which the project had been treating as clean ground truth.

Detector must not need a language model (no GPU, 7.4 GB RAM). Approach: character BIGRAM
plausibility against the rest of the corpus. Classical Chinese is highly repetitive, so a
window of genuine text has mostly bigrams attested elsewhere; an OCR-mangled window is full
of bigrams that occur nowhere else.

Validation strategy matters more than the score: the detector is calibrated on the ONE
region known to be bad and must then rank it at the top. A detector tuned until the number
looks good, without a known-positive control, proves nothing.
"""
import collections
import glob
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.variants import fold  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
CJK = re.compile(r"[一-鿿𠀀-𯨟]")


def text_of(work):
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt"))))


def cjk_only(s):
    return "".join(CJK.findall(fold(s)))


works = sorted(d for d in os.listdir(RAW) if os.path.isdir(os.path.join(RAW, d)))
print(f"loading {len(works)} works …")
clean_text = {w: cjk_only(text_of(w)) for w in works}
total = sum(len(t) for t in clean_text.values())
print(f"  {total:,} CJK chars")

# Corpus-wide bigram counts. Built once over everything, so a work is scored against the
# whole corpus including itself — a bigram unique to a corrupt window still counts 1.
big = collections.Counter()
uni = collections.Counter()
for t in clean_text.values():
    uni.update(t)
    big.update(t[i:i + 2] for i in range(len(t) - 1))
print(f"  {len(uni):,} distinct chars, {len(big):,} distinct bigrams")

WIN = 60


def score(s):
    """Fraction of the window's bigrams that occur only ONCE corpus-wide (i.e. only here).
    Also returns the rare-character fraction, which catches single-char OCR junk."""
    if len(s) < 12:
        return 0.0, 0.0
    bs = [s[i:i + 2] for i in range(len(s) - 1)]
    hapax = sum(1 for b in bs if big[b] <= 1)
    rare = sum(1 for c in s if uni[c] <= 2)
    return hapax / len(bs), rare / len(s)


print(f"\n=== windows of {WIN} chars ranked by unattested-bigram rate ===")
rows = []
for w, t in clean_text.items():
    for i in range(0, len(t) - WIN, WIN // 2):
        h, r = score(t[i:i + WIN])
        rows.append((h, r, w, i, t[i:i + WIN]))
rows.sort(reverse=True)
print(f"  scored {len(rows):,} windows")
print(f"\n  {'hapax':>6} {'rare':>6} {'work':10} {'at':>8}  text")
for h, r, w, i, s in rows[:14]:
    print(f"  {h:6.3f} {r:6.3f} {w:10} {i:8}  {s[:52]}")

# --- known-positive control -------------------------------------------------------
print("\n=== control: where does the hand-found corrupt region rank? ===")
target = "有孚寧如无咎"
found = False
for rank, (h, r, w, i, s) in enumerate(rows, 1):
    if target in s:
        pct = 100.0 * rank / len(rows)
        print(f"  KR1a0006 中孚 window found at rank {rank}/{len(rows)} "
              f"(top {pct:.3f}%), hapax={h:.3f} rare={r:.3f}")
        found = True
        break
if not found:
    print("  NOT FOUND — the detector misses the one region known to be bad")

print("\n=== per-work corruption rate (windows above the 99.5th percentile) ===")
cut = rows[int(len(rows) * 0.005)][0]
print(f"  threshold hapax >= {cut:.3f}")
per = collections.Counter()
tot = collections.Counter()
for h, r, w, i, s in rows:
    tot[w] += 1
    if h >= cut:
        per[w] += 1
print(f"  {'work':10} {'flagged':>8} {'windows':>8} {'rate':>7}")
for w in sorted(tot, key=lambda k: -per[k] / max(tot[k], 1)):
    if per[w]:
        print(f"  {w:10} {per[w]:8} {tot[w]:8} {100.0*per[w]/tot[w]:6.2f}%")

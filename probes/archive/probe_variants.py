"""Variant characters: does searching 傳 find 𫝊? Does 說 find 説? This decides normalization."""
import glob
import os
import re
import unicodedata

# canonical corpus (R18a: was a single-dirname probes/data/raw path that
# matched no existing directory — the historical scratch fetcher output)
BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")


def whole(repo):
    t = "".join(open(p, encoding="utf-8").read() for p in sorted(glob.glob(os.path.join(BASE, repo, "*.txt"))))
    return re.sub(r"<pb:[^>]+>|[¶\s　/]|&\w+;", "", t)


t7 = whole("KR1a0007")
t1 = whole("KR1a0001")
t6 = whole("KR1a0006")

pairs = [
    ("傳", "𫝊"),   # trad vs rare variant used in WYG
    ("勢", "𫝑"),
    ("象", "𧰼"),
    ("弘", "𢎞"),
    ("隸", "𨽻"),
    ("類", "𩔖"),
    ("玄", "𤣥"),
    ("說", "説"),   # both in BMP, differ by one stroke
    ("眞", "真"),
    ("內", "内"),
    ("彖", "彖"),
]
print("=== raw counts per form, in KR1a0007 (WYG 注疏) ===")
for a, b in pairs:
    ca, cb = t7.count(a), t7.count(b)
    flag = "  <-- BOTH PRESENT, search will split" if ca and cb else ("  <-- only variant form!" if cb and not ca else "")
    print(f"  {a} (U+{ord(a):04X}) = {ca:4}   |   {b} (U+{ord(b):04X}) = {cb:4}{flag}")

print("\n=== does Unicode NFKC collapse them? ===")
for a, b in pairs:
    na, nb = unicodedata.normalize("NFKC", a), unicodedata.normalize("NFKC", b)
    print(f"  {a} vs {b}: NFKC equal? {na == nb}   (NFKC({b})={nb!r})")

print("\n=== practical impact: a user searching 「傳」 in 注疏 ===")
print(f"  hits on 傳 alone      : {t7.count('傳')}")
print(f"  hits on 𫝊 alone      : {t7.count('𫝊')}")
print(f"  true total            : {t7.count('傳') + t7.count('𫝊')}")
miss = t7.count("𫝊") / max(t7.count("傳") + t7.count("𫝊"), 1)
print(f"  -> naive search misses {100*miss:.0f}% of real occurrences")

print("\n=== simplified vs traditional across corpora (the daizhige problem) ===")
for label, t in (("KR1a0001 tls", t1), ("KR1a0006 SBCK", t6), ("KR1a0007 WYG", t7)):
    simp = sum(t.count(c) for c in "关强这传说学变经过发对")
    trad = sum(t.count(c) for c in "關強這傳說學變經過發對")
    print(f"  {label:16} simplified-form hits={simp:5}  traditional-form hits={trad:5}")

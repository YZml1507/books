"""Survey EVERY anchor type available for 卦/爻 attribution, across all 易類 works.

My earlier 0%-markup finding was wrong: it only matched KR1a0001's 《X第N》 form and
missed at least three other anchor kinds visible in KR1a0006. Before designing the
alignment algorithm, enumerate what actually exists rather than assuming.

Candidate anchors, cheapest and most reliable first:
  A. Unicode hexagram symbols U+4DC0-U+4DFF  — unambiguous if present
  B. juan headers like 周易上經乾傳第一
  C. trigram composition notes like (乾下/乾上)
  D. 《X第N》 gua headings
  E. 爻位 tokens 初九/九二/…/用六
"""
import glob
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

WORKS = ["KR1a0001", "KR1a0003", "KR1a0006", "KR1a0007",
         "KR1a0016", "KR1a0030", "KR1a0031", "KR1a0032"]

# U+4DC0..U+4DFF = the 64 hexagram symbols, in canonical King Wen order
HEX_RE = re.compile(r"[䷀-䷿]")
HEADER_RE = re.compile(r"周易[上下]?經?([^\s傳]{1,3})傳第([一二三四五六七八九十]+)")
TRIGRAM_RE = re.compile(r"[（(]([^（()）/]{1,3})下\s*/\s*([^（()）/]{1,3})上[）)]")
GUA_HEAD_RE = re.compile(r"《([^》]{1,4})第([一二三四五六七八九十]+)》")
YAO_RE = re.compile(r"初九|初六|九二|六二|九三|六三|九四|六四|九五|六五|上九|上六|用九|用六")


def load(work):
    out = {}
    for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt"))):
        raw = open(p, encoding="utf-8").read()
        out[os.path.basename(p)] = raw
    return out


print(f"{'work':10} {'files':>5} {'hexsym':>7} {'distinct':>8} {'header':>7} "
      f"{'trigram':>8} {'《X第N》':>8} {'爻位':>6}")
print("-" * 74)

detail = {}
for w in WORKS:
    files = load(w)
    if not files:
        print(f"{w:10} MISSING")
        continue
    allraw = "".join(files.values())
    body = re.sub(r"^#.*$", "", allraw, flags=re.M)

    hexs = HEX_RE.findall(body)
    heads = HEADER_RE.findall(allraw)
    tris = TRIGRAM_RE.findall(body)
    guas = GUA_HEAD_RE.findall(body)
    yaos = YAO_RE.findall(body)

    detail[w] = {"hex": hexs, "head": heads, "tri": tris, "gua": guas, "yao": yaos}
    print(f"{w:10} {len(files):5} {len(hexs):7} {len(set(hexs)):8} {len(heads):7} "
          f"{len(tris):8} {len(guas):8} {len(yaos):6}")

print("-" * 74)

# --- what do the headers actually look like? ---
print("\n=== juan headers, sample per work ===")
for w, d in detail.items():
    if d["head"]:
        s = "、".join(f"{a}傳第{b}" for a, b in d["head"][:8])
        print(f"  {w}: {len(d['head'])} found -> {s}")

print("\n=== trigram composition notes, sample ===")
for w, d in detail.items():
    if d["tri"]:
        s = "、".join(f"{a}下/{b}上" for a, b in d["tri"][:8])
        print(f"  {w}: {len(d['tri'])} found -> {s}")

print("\n=== hexagram symbols: which works carry them, and in what order? ===")
for w, d in detail.items():
    if d["hex"]:
        seq = d["hex"]
        codes = [f"U+{ord(c):04X}" for c in seq[:10]]
        print(f"  {w}: {len(seq)} total, {len(set(seq))} distinct")
        print(f"      first 10: {' '.join(codes)}")
        print(f"      as chars: {''.join(seq[:20])}")
        # canonical order check: U+4DC0 is 乾(1), so index = ord-0x4DC0+1
        nums = [ord(c) - 0x4DC0 + 1 for c in seq]
        print(f"      gua numbers: {nums[:20]}")

print("\n=== 爻位 token distribution (top) ===")
for w, d in detail.items():
    if d["yao"]:
        c = Counter(d["yao"])
        print(f"  {w}: {dict(c.most_common(6))}")

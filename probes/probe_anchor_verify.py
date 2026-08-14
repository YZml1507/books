"""Are the two independent 卦 keys mutually consistent, and can they segment the text?

Key 1: Unicode hexagram symbol U+4DC0+n-1 (n = King Wen number)
Key 2: trigram composition note (X下/Y上) — any trigram pair determines one hexagram

Both maps are DERIVED from adjacency in the corpus itself, never hardcoded, so a
disagreement is a real error signal rather than a transcription mistake of mine.

Then: can Key 1 segment KR1a0006/0007/0016 into per-卦 spans, and how much text is
left unattributed? That is the number that decides whether D-006 is solved.
"""
import glob
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")
os.makedirs(CAT, exist_ok=True)

HEX_RE = re.compile(r"[䷀-䷿]")
TRIGRAM_RE = re.compile(r"[（(]([^（()）/]{1,3})下\s*/?\s*([^（()）/]{1,3})上[）)]")
GUA_HEAD_RE = re.compile(r"《([^》]{1,4})第([一二三四五六七八九十]+)》")
YAO_ORDER = ["初九", "初六", "九二", "六二", "九三", "六三",
             "九四", "六四", "九五", "六五", "上九", "上六"]
YAO_RE = re.compile("|".join(YAO_ORDER) + "|用九|用六")


def gua_num(ch):
    return ord(ch) - 0x4DC0 + 1


def body_of(work):
    parts = []
    for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt"))):
        raw = open(p, encoding="utf-8").read()
        parts.append(re.sub(r"^#.*$", "", raw, flags=re.M))
    return "".join(parts)


SEQ_WORKS = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016"]
DIAGRAM_WORKS = ["KR1a0031", "KR1a0032"]
bodies = {w: body_of(w) for w in SEQ_WORKS + DIAGRAM_WORKS}

# ---------- 1. derive symbol -> trigram pair ----------
print("=== 1. symbol -> trigram pair, derived by adjacency ===")
sym2tri = defaultdict(Counter)
for w, body in bodies.items():
    for m in HEX_RE.finditer(body):
        window = body[m.start():m.start() + 40]
        t = TRIGRAM_RE.search(window)
        if t:
            sym2tri[m.group()][(t.group(1), t.group(2))] += 1

conflicts = {s: c for s, c in sym2tri.items() if len(c) > 1}
print(f"  symbols with a trigram note: {len(sym2tri)}")
print(f"  symbols with CONFLICTING notes: {len(conflicts)}")
for s, c in list(conflicts.items())[:6]:
    print(f"    {s} (卦{gua_num(s)}): {dict(c)}")

tri2sym = {}
tri_conflict = []
for s, c in sym2tri.items():
    pair = c.most_common(1)[0][0]
    if pair in tri2sym and tri2sym[pair] != s:
        tri_conflict.append((pair, tri2sym[pair], s))
    tri2sym[pair] = s
print(f"  distinct trigram pairs mapped: {len(tri2sym)}")
print(f"  pairs claimed by >1 symbol: {len(tri_conflict)}  {tri_conflict[:4]}")

# ---------- 2. derive number -> name from KR1a0001 ----------
print("\n=== 2. gua number -> name, derived from KR1a0001 headings ===")
num2name = defaultdict(Counter)
b1 = bodies["KR1a0001"]
for m in HEX_RE.finditer(b1):
    window = b1[max(0, m.start() - 60):m.start() + 60]
    h = GUA_HEAD_RE.search(window)
    if h:
        num2name[gua_num(m.group())][h.group(1)] += 1
clean = {n: c.most_common(1)[0][0] for n, c in num2name.items()}
print(f"  numbers named: {len(clean)}/64   distinct names: {len(set(clean.values()))}")
amb = {n: dict(c) for n, c in num2name.items() if len(c) > 1}
print(f"  ambiguous: {len(amb)}  {list(amb.items())[:3]}")
missing = [n for n in range(1, 65) if n not in clean]
print(f"  unnamed numbers: {missing}")

# ---------- 3. is the symbol sequence usable as a boundary marker? ----------
print("\n=== 3. symbol sequence shape per work ===")
for w in SEQ_WORKS + DIAGRAM_WORKS:
    nums = [gua_num(c) for c in HEX_RE.findall(bodies[w])]
    inv = sum(1 for a, b in zip(nums, nums[1:]) if b < a)
    dupes = [n for n, k in Counter(nums).items() if k > 1]
    kind = "SEQUENTIAL" if inv <= 5 else "NON-SEQUENTIAL (diagram?)"
    print(f"  {w}: n={len(nums):3} distinct={len(set(nums)):2} inversions={inv:3} "
          f"repeated={len(dupes):2}  -> {kind}")
    if 0 < inv <= 5:
        bad = [(i, nums[i], nums[i + 1]) for i in range(len(nums) - 1)
               if nums[i + 1] < nums[i]]
        print(f"      inversion sites (idx, from, to): {bad}")

# ---------- 4. segmentation coverage on the commentaries ----------
print("\n=== 4. can Key 1 segment the commentaries? ===")
seg_report = {}
for w in ["KR1a0006", "KR1a0007", "KR1a0016"]:
    body = bodies[w]
    pos = [(m.start(), gua_num(m.group())) for m in HEX_RE.finditer(body)]
    total = len(re.sub(r"[\s　¶/]", "", body))
    head = len(re.sub(r"[\s　¶/]", "", body[:pos[0][0]])) if pos else total
    spans = []
    for i, (st, g) in enumerate(pos):
        en = pos[i + 1][0] if i + 1 < len(pos) else len(body)
        spans.append((g, len(re.sub(r"[\s　¶/]", "", body[st:en]))))
    attributed = sum(n for _, n in spans)
    covered = len({g for g, _ in spans})
    sizes = sorted(n for _, n in spans)
    med = sizes[len(sizes) // 2] if sizes else 0
    print(f"  {w}: total={total:>7,} head_unattributed={head:>6,} "
          f"({100*head/total:4.1f}%)  attributed={100*attributed/total:5.1f}%")
    print(f"      spans={len(spans)} distinct卦={covered}/64 "
          f"median_span={med:,} max_span={sizes[-1]:,}")
    seg_report[w] = {"total": total, "head": head, "spans": len(spans),
                     "covered": covered, "median": med}

# ---------- 5. within-卦 爻位 ordering, using 乾 as the probe ----------
print("\n=== 5. 爻位 order inside the 乾 span (should be 初九→上九) ===")
for w in ["KR1a0006", "KR1a0007", "KR1a0016"]:
    body = bodies[w]
    pos = [(m.start(), gua_num(m.group())) for m in HEX_RE.finditer(body)]
    span = next(((st, pos[i + 1][0]) for i, (st, g) in enumerate(pos)
                 if g == 1 and i + 1 < len(pos)), None)
    if not span:
        print(f"  {w}: no 乾 span found")
        continue
    seq = YAO_RE.findall(body[span[0]:span[1]])
    first = []
    for y in seq:
        if y not in first:
            first.append(y)
    print(f"  {w}: {len(seq)} tokens, first-appearance order: {first}")

with open(os.path.join(CAT, "gua_anchors.json"), "w", encoding="utf-8") as f:
    json.dump({
        "num2name": clean,
        "trigram2num": {f"{a}下{b}上": gua_num(s) for (a, b), s in tri2sym.items()},
        "segmentation": seg_report,
    }, f, ensure_ascii=False, indent=1)
print("\nderived maps -> data/catalog/gua_anchors.json")

"""Is the inferred 卦 attribution actually CORRECT, or just present?

Validation strategy: KR1a0007 (WYG) juan headers sometimes name the 卦 range explicitly
(#+PROPERTY: JUAN ...). Where they do, compare against our inferred label. Also spot-check
by asking: do units attributed to 乾 actually mention 乾-specific vocabulary?
"""
import glob
import os
import re
from collections import Counter, defaultdict

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")
VARIANTS = {"𫝊": "傳", "𫝑": "勢", "𧰼": "象", "𢎞": "弘", "𨽻": "隸", "𩔖": "類",
            "𤣥": "玄", "説": "說", "眞": "真", "内": "內", "𥘉": "初", "𥙿": "裕",
            "𣏌": "杞", "𡵨": "岐", "𫉬": "獲"}
GUA_RE = re.compile(r"《([^》]{1,4})第([一二三四五六七八九十]+)》")


def fold(s):
    return "".join(VARIANTS.get(c, c) for c in s)


def clean(s):
    s = re.sub(r"<pb:[^>]+>|&\w+;", "", s)
    return re.sub(r"[¶\s　/「」『』《》，。、：；？！()]", "", fold(s))


# canonical phrases
canon = defaultdict(list)
order = []
for path in sorted(glob.glob(os.path.join(BASE, "KR1a0001", "*.txt"))):
    body = re.sub(r"^#.*$", "", open(path, encoding="utf-8").read(), flags=re.M)
    cur = None
    for line in re.sub(r"<pb:[^>]+>", "", body).split("¶"):
        g = GUA_RE.search(line)
        if g:
            cur = g.group(1)
            if cur not in order:
                order.append(cur)
            continue
        if cur:
            c = clean(line)
            if len(c) >= 5:
                canon[cur].append(c)

owner, dupes = {}, set()
for gua, ps in canon.items():
    for p in ps:
        if p in owner and owner[p] != gua:
            dupes.add(p)
        else:
            owner[p] = gua
for p in dupes:
    owner.pop(p, None)

# --- validation 1: does WYG juan header name a 卦 we can check against? ---
print("=== validation 1: juan headers in KR1a0007 that name 卦 ===")
checked = agree = 0
for path in sorted(glob.glob(os.path.join(BASE, "KR1a0007", "*.txt"))):
    raw = open(path, encoding="utf-8").read()
    juan = re.search(r"^#\+PROPERTY: JUAN (.+)$", raw, re.M)
    if not juan:
        continue
    jname = juan.group(1).strip()
    # does the juan title itself mention a known 卦 name?
    named = [g for g in order if g in jname and len(g) >= 1]
    if not named:
        continue
    body = re.sub(r"^#.*$", "", raw, flags=re.M)
    cur = None
    inferred = Counter()
    for line in re.sub(r"<pb:[^>]+>", "", body).split("¶"):
        c = clean(line)
        if not c:
            continue
        for p, gua in owner.items():
            if p in c:
                cur = gua
                break
        if cur:
            inferred[cur] += 1
    if not inferred:
        continue
    top = inferred.most_common(1)[0][0]
    checked += 1
    ok = top in named or any(n in top for n in named)
    agree += ok
    print(f"  {os.path.basename(path):22} JUAN={jname[:22]:22} header_says={named} inferred_top={top} {'OK' if ok else 'MISMATCH'}")
print(f"  -> agreement: {agree}/{checked}")

# --- validation 2: precision check on 乾. Units labelled 乾 should mention 乾 vocabulary ---
print("\n=== validation 2: precision of 乾 attribution in KR1a0007 ===")
QIAN_VOCAB = ["乾", "潛龍", "見龍", "飛龍", "亢龍", "君子終日", "天行健", "元亨利貞", "九三", "九五"]
labelled_qian = []
cur = None
for path in sorted(glob.glob(os.path.join(BASE, "KR1a0007", "*.txt"))):
    body = re.sub(r"^#.*$", "", open(path, encoding="utf-8").read(), flags=re.M)
    for line in re.sub(r"<pb:[^>]+>", "", body).split("¶"):
        c = clean(line)
        if not c:
            continue
        for p, gua in owner.items():
            if p in c:
                cur = gua
                break
        if cur == "乾":
            labelled_qian.append(c)
n = len(labelled_qian)
with_vocab = sum(1 for c in labelled_qian if any(v in c for v in QIAN_VOCAB))
print(f"  units labelled 乾: {n}")
print(f"  of those, containing 乾-specific vocabulary: {with_vocab} = {100*with_vocab/max(n,1):.1f}%")
print("  sample of units labelled 乾 WITHOUT 乾 vocabulary (possible carry-forward drift):")
bad = [c for c in labelled_qian if not any(v in c for v in QIAN_VOCAB)]
for c in bad[:6]:
    print(f"    - {c[:64]}")

# --- validation 3: how far does carry-forward drift? distance since last re-anchor ---
print("\n=== validation 3: carry-forward drift distance ===")
gaps = []
cur, since = None, 0
for path in sorted(glob.glob(os.path.join(BASE, "KR1a0007", "*.txt"))):
    body = re.sub(r"^#.*$", "", open(path, encoding="utf-8").read(), flags=re.M)
    for line in re.sub(r"<pb:[^>]+>", "", body).split("¶"):
        c = clean(line)
        if not c:
            continue
        hit = None
        for p, gua in owner.items():
            if p in c:
                hit = gua
                break
        if hit:
            gaps.append(since)
            cur, since = hit, 0
        else:
            since += 1
if gaps:
    gaps.sort()
    print(f"  re-anchor events: {len(gaps)}")
    print(f"  units between anchors: median={gaps[len(gaps)//2]}, p90={gaps[int(len(gaps)*0.9)]}, max={gaps[-1]}")
    print(f"  -> {'LOW RISK' if gaps[int(len(gaps)*0.9)] < 15 else 'DRIFT RISK: long unanchored stretches'}")

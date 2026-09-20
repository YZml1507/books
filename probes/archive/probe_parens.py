"""Are the 注 parentheses balanced? If not, the 經-only view is silently truncated.

Symptom that led here: KR1a0007's 坤 span keeps 初六..六四 but loses 六五 (黃裳元吉) and
上六 (龍戰于野), i.e. exactly the 爻 that come LATE in the span. An unclosed '(' would
leave the depth counter positive and drop every 經 passage after it — a silent,
position-dependent data loss, which is the worst kind.
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OPEN, CLOSE = "（(", "）)"
FOLD = {"濳": "潛", "羣": "群", "無": "无", "黄": "黃", "乗": "乘", "㓂": "寇"}
HEX_RE = re.compile(r"[䷀-䷿]")


def fold(s):
    return "".join(FOLD.get(c, c) for c in s)


def body(work):
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt")))
    )


print(f"{'work':10} {'opens':>7} {'closes':>7} {'delta':>6} {'max_depth':>9} "
      f"{'neg_events':>10}")
print("-" * 56)
bodies = {}
for w in ("KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"):
    raw = body(w)
    bodies[w] = raw
    o = sum(raw.count(c) for c in OPEN)
    c = sum(raw.count(ch) for ch in CLOSE)
    depth, maxd, neg = 0, 0, 0
    for ch in raw:
        if ch in OPEN:
            depth += 1
            maxd = max(maxd, depth)
        elif ch in CLOSE:
            depth -= 1
            if depth < 0:
                neg += 1
                depth = 0
    print(f"{w:10} {o:7} {c:7} {o-c:6} {maxd:9} {neg:10}")

print("-" * 56)
print("delta != 0 or max_depth > 1 means the naive depth counter is unsafe\n")

# --- where exactly does 坤 lose its late 爻 in KR1a0007? ---
raw = bodies["KR1a0007"]
pos = [(m.start(), ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(raw)]
kun = next(((s, pos[i + 1][0]) for i, (s, g) in enumerate(pos)
            if g == 2 and i + 1 < len(pos)), None)
seg = raw[kun[0]:kun[1]]
print(f"=== KR1a0007 坤 span: {len(seg):,} raw chars ===")
o = sum(seg.count(c) for c in OPEN)
c = sum(seg.count(ch) for ch in CLOSE)
print(f"  opens={o} closes={c} delta={o-c}")

# depth trace at each 爻辭 position
targets = [("初六", "履霜堅冰至"), ("六二", "直方大不習无不利"), ("六三", "含章可貞"),
           ("六四", "括囊无咎"), ("六五", "黃裳元吉"), ("上六", "龍戰于野"),
           ("用六", "利永貞")]
depths = []
depth = 0
for i, ch in enumerate(seg):
    if ch in OPEN:
        depth += 1
    elif ch in CLOSE:
        depth = max(0, depth - 1)
    depths.append(depth)

folded = fold(seg)
print(f"\n  {'爻':6} {'found':>6} {'raw_idx':>8} {'depth_there':>12}")
for yao, ph in targets:
    m = re.search(re.escape(fold(ph)), folded)
    if m:
        print(f"  {yao:6} {'yes':>6} {m.start():8} {depths[m.start()]:12}")
    else:
        print(f"  {yao:6} {'NO':>6} {'-':>8} {'-':>12}")

print("\n  depth at 10% steps through the span:")
step = max(1, len(seg) // 10)
print("   " + " ".join(f"{depths[i]:>3}" for i in range(0, len(seg), step)))

first_stuck = next((i for i in range(len(depths) - 1)
                    if depths[i] > 0 and all(d > 0 for d in depths[i:i + 400])), None)
if first_stuck is not None:
    print(f"\n  depth stays >0 for 400+ chars starting at raw idx {first_stuck}")
    print(f"  context: {seg[max(0,first_stuck-40):first_stuck+90]!r}")

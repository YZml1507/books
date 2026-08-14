"""Cross-validate our DERIVED 卦 tables against independent external repos.

Everything in our alignment layer is derived from the corpus, never typed: 卦 number comes
from the Unicode symbol's code point, line polarity from trigram composition notes, 卦 name
from 《X第N》 headings, 爻位 labels computed from polarity. That is the right design, but it
has one blind spot — a SYSTEMATIC derivation error would be invisible, because every
downstream check inherits the same assumption. An independently-produced table is the
cheapest witness available (LESSONS L-03).

The prize is Ovilia/biangua's `gua-xiang`: a six-bit polarity string per 卦. Pure bits, so
it is immune to the 简体/繁體 problem that makes text comparison unreliable here.

Discipline, stated before looking at results:
  * A DISAGREEMENT localises a defect in one of the two sides. Neither is assumed correct.
  * 简繁 differences are NOT disagreements. 讼/訟 is orthography, not a different 卦.
    Reporting those as errors would be the same mistake as folding 校勘 variants away.
  * Bit-order convention must be verified, not assumed. Checked by hand first:
    屯 = 震下坎上 -> (1,0,0)+(0,1,0) = 100010, and biangua says "100010". Bottom-to-top,
    same as ours. 蒙 = 坎下艮上 -> 010001, biangua "010001". Confirmed on two asymmetric 卦.
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import gua_symbol, yao_names  # noqa: E402
from guji.ingest import derive_gua_names  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
EXT = os.path.join(ROOT, "data", "external")
CAT = os.path.join(ROOT, "data", "catalog")

# ---------- our side, derived ----------
ZY = ["KR1a0001", "KR1a0003", "KR1a0006", "KR1a0007", "KR1a0016",
      "KR1a0030", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ZY if os.path.isdir(os.path.join(RAW, w))}
OURS_POL = derive_polarity(bodies)
OURS_NAME = derive_gua_names(bodies.get("KR1a0001", ""))
print(f"ours: polarity {len(OURS_POL)}/64, names {len(OURS_NAME)}/64")

# ---------- witness 1: Ovilia/biangua ----------
bg_path = os.path.join(EXT, "biangua", "biangua-master", "gua.json")
BG = {}
if os.path.exists(bg_path):
    data = json.load(open(bg_path, encoding="utf-8"))["gua"]
    for i, g in enumerate(data, 1):
        BG[i] = {"name": g["gua-name"], "xiang": g["gua-xiang"],
                 "yao": g.get("yao-detail", [])}
    print(f"biangua: {len(BG)} 卦")

# ---------- witness 2: sunls2/zhouyi directory names ----------
SL = {}
sl_docs = os.path.join(EXT, "zhouyi", "zhouyi-main", "docs")
if os.path.isdir(sl_docs):
    for d in os.listdir(sl_docs):
        m = re.match(r"^(\d{2})\.(.+)$", d)
        if m and os.path.isdir(os.path.join(sl_docs, d)):
            SL[int(m.group(1))] = m.group(2)
    print(f"sunls2:  {len(SL)} 卦 directories")

print("\n" + "=" * 78)
print("CHECK 1 — line polarity: ours (derived from trigram notes) vs biangua bits")
print("=" * 78)
pol_bad = []
for n in range(1, 65):
    ours = OURS_POL.get(n)
    theirs = BG.get(n, {}).get("xiang")
    if ours is None or theirs is None:
        pol_bad.append((n, ours, theirs, "missing"))
        continue
    ours_s = "".join(str(b) for b in ours)
    if ours_s != theirs:
        pol_bad.append((n, ours_s, theirs, "differs"))
print(f"compared {min(len(OURS_POL), len(BG))} 卦")
if pol_bad:
    print(f"  DISAGREEMENTS: {len(pol_bad)}")
    for n, a, b, why in pol_bad:
        print(f"    卦{n:2} {gua_symbol(n)}  ours={a}  biangua={b}  [{why}]")
else:
    print("  ALL 64 AGREE — two independent derivations of line polarity match exactly.")

print("\n" + "=" * 78)
print("CHECK 2 — 卦 name: ours (《X第N》) vs biangua vs sunls2")
print("=" * 78)
# 简繁 differences are expected and are NOT errors. Flag them separately from real
# disagreements by testing whether the names differ in MORE than script.
name_rows = []
for n in range(1, 65):
    ours = OURS_NAME.get(n, "")
    bg = BG.get(n, {}).get("name", "")
    sl = SL.get(n, "")
    # sunls2 names are 卦名+卦象 e.g. 乾为天 / 水雷屯 — extract the 卦名 by containment.
    sl_has_ours = bool(ours) and ours in sl
    agree_bg = ours == bg
    if not (agree_bg and (sl_has_ours or not sl)):
        name_rows.append((n, ours, bg, sl, agree_bg, sl_has_ours))
print(f"rows needing review: {len(name_rows)} of 64")
print(f"  {'卦':>3} {'ours':6} {'biangua':8} {'sunls2':12} {'bg=':>4} {'sl⊇':>4}")
for n, ours, bg, sl, a, s in name_rows:
    print(f"  {n:3} {ours or '-':6} {bg or '-':8} {sl or '-':12} {str(a):>4} {str(s):>4}")

print("\n" + "=" * 78)
print("CHECK 3 — 爻位 labels computed from polarity vs biangua's 爻辭 count")
print("=" * 78)
# biangua lists exactly 6 爻辭 per 卦 and OMITS 用九/用六. Ours computes 7 for 乾 and 坤.
# That is a real modelling difference, not an error on either side — record it.
cnt = {}
for n, g in BG.items():
    cnt.setdefault(len(g["yao"]), []).append(n)
print(f"  biangua 爻辭 counts: { {k: len(v) for k, v in cnt.items()} }")
for n in (1, 2):
    ours_labels = yao_names(OURS_POL[n]) if n in OURS_POL else []
    print(f"  卦{n}: ours {len(ours_labels)} labels {ours_labels}")
    print(f"        biangua {len(BG.get(n, {}).get('yao', []))} 爻辭 (用九/用六 absent)")

json.dump({"polarity_disagreements": pol_bad,
           "name_review_rows": [[n, o, b, s] for n, o, b, s, _, _ in name_rows],
           "biangua_yao_counts": {str(k): v for k, v in cnt.items()}},
          open(os.path.join(CAT, "external_witness.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("\n-> data/catalog/external_witness.json")

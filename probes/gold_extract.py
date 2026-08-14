"""Derive the gold 爻辭 FROM the base text instead of from my memory.

Three errors surfaced when the hand-written gold set was checked against KR1a0001:
  1. 屯 六二 as I wrote it scores 0 even in the base text — I dropped 匪寇婚媾.
  2. 坤 六五/上六 are present in the base text but not found in three commentaries.
  3. KR1a0031/0032 give a 2-character 屯 span — non-King-Wen symbol order.

So: extract each 爻辭 by reading the base text after each 爻位 token, diff it against
what I wrote, then locate the missing 坤 phrases in the raw commentary to decide
whether the cause is my phrasing, a variant character, or a truncated span.
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")

FOLD = {
    "濳": "潛", "羣": "群", "無": "无", "眞": "真", "內": "内", "黄": "黃",
    "兊": "兌", "兑": "兌", "㢲": "巽", "𫝊": "傳", "𤣥": "玄", "寜": "寧",
    "㑹": "會", "乆": "久", "徃": "往", "凶": "凶", "咎": "咎",
}
DROP = set(" \t\r\n¶　/「」『』《》，。、：；？！·．")
HEX_RE = re.compile(r"[䷀-䷿]")
YAO_RE = re.compile("初九|初六|九二|六二|九三|六三|九四|六四|九五|六五|上九|上六|用九|用六")

MY_GOLD = {
    1: {"初九": "潛龍勿用", "九二": "見龍在田利見大人",
        "九三": "君子終日乾乾夕惕若厲无咎", "九四": "或躍在淵无咎",
        "九五": "飛龍在天利見大人", "上九": "亢龍有悔", "用九": "見群龍无首吉"},
    2: {"初六": "履霜堅冰至", "六二": "直方大不習无不利", "六三": "含章可貞",
        "六四": "括囊无咎", "六五": "黃裳元吉", "上六": "龍戰于野其血玄黃",
        "用六": "利永貞"},
    3: {"初九": "磐桓利居貞", "六二": "屯如邅如乘馬班如女子貞不字",
        "六三": "即鹿无虞惟入于林中", "六四": "乘馬班如求婚媾",
        "六五": "屯其膏", "上九": "乘馬班如泣血漣如"},
}
EXPECT_YAO = {1: ["初九", "九二", "九三", "九四", "九五", "上九", "用九"],
              2: ["初六", "六二", "六三", "六四", "六五", "上六", "用六"],
              3: ["初九", "六二", "六三", "六四", "六五", "上九"]}
NAME = {1: "乾", 2: "坤", 3: "屯"}


def clean(s, drop_notes=True):
    out, depth, i, n = [], 0, 0, len(s)
    while i < n:
        if s.startswith("<pb:", i):
            j = s.find(">", i)
            i = n if j == -1 else j + 1
            continue
        ch = s[i]
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif (depth == 0 or not drop_notes) and ch not in DROP:
            out.append(FOLD.get(ch, ch))
        i += 1
    return "".join(out)


def body(work):
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt")))
    )


b1raw = body("KR1a0001")
pos1 = [(m.start(), ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(b1raw)]

print("=== 1. 爻辭 as the base text actually writes it ===")
derived = {}
for g in (1, 2, 3):
    span = next(((st, pos1[i + 1][0]) for i, (st, num) in enumerate(pos1)
                 if num == g and i + 1 < len(pos1)), None)
    seg = clean(b1raw[span[0]:span[1]])
    print(f"\n卦{g} {NAME[g]}  ({len(seg)} 經字)")
    print(f"  raw span: {seg[:110]}")
    marks = [(m.start(), m.group()) for m in YAO_RE.finditer(seg)]
    # keep the first occurrence of each expected 爻位, in canonical order
    got, used = {}, set()
    for st, tok in marks:
        if tok in EXPECT_YAO[g] and tok not in used:
            nxt = next((s for s, t in marks if s > st), len(seg))
            got[tok] = seg[st + len(tok):nxt]
            used.add(tok)
    derived[g] = got
    for y in EXPECT_YAO[g]:
        mine = MY_GOLD[g].get(y, "")
        theirs = got.get(y, "")
        ok = "==" if theirs.startswith(mine) or mine.startswith(theirs) else "!!"
        print(f"  {y} {ok} text={theirs[:44]!r}")
        if ok == "!!":
            print(f"        mine={mine!r}")

print("\n\n=== 2. where are 坤 六五/上六 in KR1a0007? ===")
b7raw = body("KR1a0007")
b7 = clean(b7raw, drop_notes=False)
pos7 = [(m.start(), ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(b7raw)]
kun = next(((st, pos7[i + 1][0]) for i, (st, num) in enumerate(pos7)
            if num == 2 and i + 1 < len(pos7)), None)
print(f"  坤 span in raw offsets: {kun}  (len={kun[1]-kun[0]:,} raw chars)")
nxt2 = [(i, num) for i, (st, num) in enumerate(pos7) if kun[0] <= st <= kun[1] + 200]
print(f"  symbols at/after 坤 start: {nxt2[:6]}")
for phrase in ("黃裳元吉", "龍戰于野", "履霜堅冰至", "直方大"):
    f = FOLD_P = "".join(FOLD.get(c, c) for c in phrase)
    hits = [m.start() for m in re.finditer(re.escape(f), b7)]
    inside = "?"
    print(f"  {phrase}: {len(hits)} hit(s) in whole work, first at cleaned idx {hits[:3]}")

print("\n=== 3. why is KR1a0031's 屯 span 2 chars? ===")
b31raw = body("KR1a0031")
pos31 = [(m.start(), ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(b31raw)]
seq = [num for _, num in pos31]
print(f"  first 24 symbol numbers: {seq[:24]}")
idx3 = [i for i, n in enumerate(seq) if n == 3]
print(f"  positions where 卦3 appears: {idx3[:8]}")
for i in idx3[:3]:
    st = pos31[i][0]
    en = pos31[i + 1][0] if i + 1 < len(pos31) else len(b31raw)
    print(f"    occurrence at idx {i}: neighbours {seq[max(0,i-2):i+3]}, "
          f"raw span {en-st} chars -> {clean(b31raw[st:en])[:50]!r}")

with open(os.path.join(CAT, "gold_yao_derived.json"), "w", encoding="utf-8") as f:
    json.dump({str(k): v for k, v in derived.items()}, f, ensure_ascii=False, indent=1)
print("\nderived 爻辭 -> data/catalog/gold_yao_derived.json")

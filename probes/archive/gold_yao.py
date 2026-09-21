"""Gold set for 爻-level attribution, and the two candidate anchoring methods.

Ground truth: the 爻辭 of 乾/坤/屯 as established texts. 屯 is included deliberately —
its 六二/六四/上九 all contain 乘馬班如, so a naive substring anchor MUST fail on it.
That is the point: measure the failure instead of assuming it away.

Method A: anchor on 爻位 tokens (初九/九二/…). Cheap. Expected to fail, because
          commentaries cross-reference other 卦's lines (六二 appears inside 乾).
Method B: anchor on the 爻辭 text the commentary structurally quotes before commenting.

All matching runs through the variant-folding table on BOTH sides, because the
commentaries write 濳 for 潛, 羣 for 群, 無 for 无.
"""
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
CAT = os.path.join(ROOT, "data", "catalog")

FOLD = {
    "濳": "潛", "羣": "群", "無": "无", "說": "説", "眞": "真", "內": "内",
    "兊": "兌", "兑": "兌", "㢲": "巽", "𫝊": "傳", "𤣥": "玄", "𢎞": "弘",
    "𨽻": "隸", "𩔖": "類", "𧰼": "象", "𫝑": "勢", "寜": "寧", "㑹": "會",
    "乆": "久", "尓": "爾", "凢": "凡", "羙": "美", "冨": "富", "徃": "往",
}

# 卦 number -> {爻位: 爻辭}. Canonical text; the tail of each phrase is what
# disambiguates 屯's three 乘馬班如 lines.
GOLD = {
    1: {  # 乾
        "初九": "潛龍勿用",
        "九二": "見龍在田利見大人",
        "九三": "君子終日乾乾夕惕若厲无咎",
        "九四": "或躍在淵无咎",
        "九五": "飛龍在天利見大人",
        "上九": "亢龍有悔",
        "用九": "見群龍无首吉",
    },
    2: {  # 坤
        "初六": "履霜堅冰至",
        "六二": "直方大不習无不利",
        "六三": "含章可貞",
        "六四": "括囊无咎",
        "六五": "黃裳元吉",
        "上六": "龍戰于野其血玄黃",
        "用六": "利永貞",
    },
    3: {  # 屯
        "初九": "磐桓利居貞",
        "六二": "屯如邅如乘馬班如女子貞不字",
        "六三": "即鹿无虞惟入于林中",
        "六四": "乘馬班如求婚媾",
        "六五": "屯其膏",
        "上九": "乘馬班如泣血漣如",
    },
}
GUA_NAME = {1: "乾", 2: "坤", 3: "屯"}
HEX_RE = re.compile(r"[䷀-䷿]")
YAO_RE = re.compile("初九|初六|九二|六二|九三|六三|九四|六四|九五|六五|上九|上六|用九|用六")
DROP = set(" \t\r\n¶　/「」『』《》，。、：；？！·．")


def fold(s):
    return "".join(FOLD.get(c, c) for c in s)


def clean_with_map(s, drop_notes=True):
    """Strip markup/punctuation (and parenthesised 注 if asked); keep an index map
    back into the original string so span boundaries stay citable."""
    out, idx, depth, i, n = [], [], 0, 0, len(s)
    while i < n:
        if s.startswith("<pb:", i):
            j = s.find(">", i)
            i = n if j == -1 else j + 1
            continue
        ch = s[i]
        if ch in "（(":
            depth += 1
            i += 1
            continue
        if ch in "）)":
            depth = max(0, depth - 1)
            i += 1
            continue
        if (depth == 0 or not drop_notes) and ch not in DROP:
            out.append(FOLD.get(ch, ch))
            idx.append(i)
        i += 1
    return "".join(out), idx


def body_of(work):
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(RAW, work, "*.txt")))
    )


# ---------- 0. is the gold set actually present in the base text? ----------
print("=== 0. validate gold 爻辭 against KR1a0001 (base text) ===")
base, _ = clean_with_map(body_of("KR1a0001"))
missing_gold = []
for g, yaos in GOLD.items():
    hits = {y: base.count(fold(t)) for y, t in yaos.items()}
    bad = {y: c for y, c in hits.items() if c == 0}
    print(f"  卦{g} {GUA_NAME[g]}: " + " ".join(f"{y}={c}" for y, c in hits.items()))
    if bad:
        missing_gold.append((g, bad))
        print(f"      NOT FOUND: {bad}")
print(f"  -> gold phrases absent from base text: {len(missing_gold)}")

# ---------- 1. locate the 卦 span, then compare Method A vs B ----------
WORKS = ["KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
report = {}
for w in WORKS:
    raw = body_of(w)
    pos = [(m.start(), ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(raw)]
    print(f"\n{'='*72}\n{w}")
    report[w] = {}
    for g in (1, 2, 3):
        # first span whose symbol is this 卦
        span = None
        for i, (st, num) in enumerate(pos):
            if num == g:
                en = pos[i + 1][0] if i + 1 < len(pos) else len(raw)
                span = (st, en)
                break
        if not span:
            print(f"  卦{g} {GUA_NAME[g]}: NO SYMBOL FOUND")
            report[w][g] = None
            continue
        seg = raw[span[0]:span[1]]
        jing, _ = clean_with_map(seg, drop_notes=True)   # 經 only
        full, _ = clean_with_map(seg, drop_notes=False)  # 經 + 注

        # Method A: 爻位 tokens
        toks = YAO_RE.findall(full)
        expected = set(GOLD[g])
        impossible = [t for t in toks if t not in expected]

        # Method B: 爻辭 quotations, searched in 經-only view
        found, order = {}, []
        for y, t in GOLD[g].items():
            c = jing.count(fold(t))
            found[y] = c
            if c:
                order.append((jing.find(fold(t)), y))
        order.sort()
        seq = [y for _, y in order]
        canon = [y for y in GOLD[g] if found.get(y)]
        in_order = seq == canon

        print(f"  卦{g} {GUA_NAME[g]}  span={len(jing):,} 經字 / {len(full):,} 經+注字")
        print(f"    A 爻位 tokens : {len(toks)} total, "
              f"{len(impossible)} impossible for this 卦 "
              f"{sorted(set(impossible))[:6]}")
        print(f"    B 爻辭 quotes : {sum(1 for c in found.values() if c)}"
              f"/{len(GOLD[g])} located  counts={found}")
        print(f"      order correct: {in_order}  {seq}")
        report[w][g] = {
            "span_jing": len(jing), "span_full": len(full),
            "tokens": len(toks), "impossible": sorted(set(impossible)),
            "located": {k: v for k, v in found.items()},
            "order_ok": in_order,
        }

with open(os.path.join(CAT, "gold_yao_report.json"), "w", encoding="utf-8") as f:
    json.dump({"gold": GOLD, "report": report}, f, ensure_ascii=False, indent=1)
print(f"\n{'='*72}\nreport -> data/catalog/gold_yao_report.json")

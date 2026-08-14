"""Verify the four hypotheses the raw dumps suggested, with counts not eyeballs.

H1. KR1a0031 is the 經傳分離 arrangement: 象傳 lives in separate 卷 (files 003+),
    so its 爻 spans carry NO 象曰. KR1a0032 interleaves 象曰, which quotes the 爻辭
    verbatim — giving the verifier a SECOND CHANCE that 0031 structurally cannot have.
    -> quantify how many of 0032's passes depend on the 象曰 quote.

H2. Three of 0031's failures are 爻位 MISLABELS in the source (卦23 六五 written 六四,
    卦57 九三 written 九二, 卦61 九二 written 九三). Those are the 3 "unknown".

H3. Several failures are glyph errors confined to 0031's 經 line and CONTRADICTED by
    0031's own 注 or its own 象傳 section. Intra-edition self-contradiction is the test
    that separates a transcription error from a real 異文.

H4. Five failures are genuine 異體字 absent from FOLD. Check codepoints + counts.
"""
import os
import re
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.anchors import HEX_RE, gua_number  # noqa: E402
from guji.variants import FOLD, NOT_VARIANTS  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ALL}
polarity = derive_polarity(bodies)
gold = derive_gold(bodies["KR1a0001"], polarity)

print("#" * 78)
print("H1  does 0032 pass thanks to the inline 象曰 quoting the 爻辭 back?")
print("#" * 78)
for w in ("KR1a0031", "KR1a0032"):
    raw = bodies[w]
    n_xiang = raw.count("象曰")
    spans, _ = gua_spans(raw)
    only_via_xiang = []
    pass_pre = pass_post = fail = 0
    seen = set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        expected = yao_names(polarity[s.number])
        view = clean(raw[s.start:s.end], keep_notes=False)
        hits = extract_yao(raw[s.start:s.end], expected, jing=view)
        for label in expected:
            rng, want = hits.get(label), gold.get(s.number, {}).get(label)
            if not rng or not want:
                continue
            actual = view.text[rng[0] + len(label):rng[1]]
            head = want[:6]
            pre = actual.split("象曰")[0]
            if head in pre:
                pass_pre += 1
            elif head in actual:
                pass_post += 1
                only_via_xiang.append((s.number, label, head, pre[:24]))
            else:
                fail += 1
    print(f"\n{w}: 象曰 occurrences in raw = {n_xiang}")
    print(f"  verified from the 爻辭 itself         : {pass_pre}")
    print(f"  verified ONLY via the trailing 象曰   : {pass_post}   <-- artifact")
    print(f"  failed                               : {fail}")
    for g, label, head, pre in only_via_xiang:
        print(f"    卦{g} {label}: gold head {head!r} absent from 爻辭 {pre!r}")

print("\n" + "#" * 78)
print("H2  爻位 mislabels in KR1a0031")
print("#" * 78)
CHECKS = [
    ("KR1a0031", 23, "六五", "貫魚以宫人寵"),
    ("KR1a0031", 57, "九三", "頻巽吝"),
    ("KR1a0031", 61, "九二", "鳴鶴在隂"),
]
for w, g, should, phrase in CHECKS:
    raw = bodies[w]
    at = raw.find(phrase)
    if at == -1:
        print(f"  卦{g}: phrase {phrase!r} not found")
        continue
    before = re.sub(r"<pb:[^>]*>|[¶\n]", "", raw[max(0, at - 14):at])
    print(f"  卦{g}: expected label {should}, source writes ...{before!r} + {phrase!r}")
    # what does the 注 say the position is?
    note = raw[at:at + 260]
    for pat in ("九居二", "居下之上", "五為衆隂之長", "五為眾隂之長", "九二", "六五"):
        if pat in note:
            print(f"        注 confirms position via {pat!r}")
            break

print("\n" + "#" * 78)
print("H3/H4  candidate pairs: codepoint, corpus counts, intra-0031 contradiction")
print("#" * 78)
# (corpus_char, canonical_char, the 卦/爻 where it appeared, a phrase proving 0031's own
#  注 or 象傳 uses the canonical form -- empty string means no internal contradiction)
CAND = [
    ("眀", "明", "卦36 初九 眀夷于飛", "六二明夷夷于左股"),
    ("𠖇", "冥", "卦46 上六 𠖇升", "昬𠖇不已者也"),
    ("収", "收", "卦48 上六 井収勿幕", ""),
    ("蘓", "蘇", "卦51 六三 震蘓蘓", ""),
    ("𤨏", "瑣", "卦56 初六 旅𤨏𤨏", ""),
    ("耊", "耋", "卦30 九三 大耊之嗟 (KR1a0032)", ""),
    ("怕", "恒", "卦5/32 利用怕, 浚怕, 振怕", "需于郊不犯難行也利用恒无咎"),
    ("昊", "昃", "卦30 九三 日昊之離", "日昃之離何可久也"),
    ("悔", "晦", "卦36 上六 不明悔", "不明其德以至於晦"),
    ("凖", "隼", "卦40 上六 公用射凖", "公用射隼以解悖也"),
    ("无", "元", "卦42 初九 大作无吉", "必元吉然後得无咎"),
    ("極", "拯", "卦59 初六 用極馬壯", "始渙而拯之為力既易"),
    ("耽", "眈", "卦27 六四 虎視耽耽", ""),
    ("冽", "洌", "卦48 九五 井冽寒泉食", "洌潔也"),
    ("已", "己", "卦26 初九 有厲利已", "有厲利己不犯災也"),
    ("其", "有", "卦63 六四 繻其衣袽", ""),
]
print(f"{'pair':>9} {'codepoints':>17}  {'in FOLD':>7} {'NOT_V':>5}  counts per work")
for a, b, where, contra in CAND:
    cps = f"U+{ord(a):04X}->U+{ord(b):04X}"
    inf = FOLD.get(a, "-")
    nv = "yes" if (a, b) in NOT_VARIANTS or (b, a) in NOT_VARIANTS else ""
    counts = " ".join(f"{w[-4:]}:{bodies[w].count(a)}/{bodies[w].count(b)}" for w in ALL)
    print(f"\n  {a}->{b}  {cps}  fold={inf} {nv:>4}")
    print(f"      where: {where}")
    print(f"      count corpus_char/canonical: {counts}")
    if contra:
        found = contra in bodies["KR1a0031"]
        print(f"      0031's own 注/象傳 writes canonical form: {found}  ({contra})")

print("\n" + "#" * 78)
print("extra: is 卦39 really absent from both editions? and 0031's file layout")
print("#" * 78)
for w in ("KR1a0031", "KR1a0032"):
    raw = bodies[w]
    nums = [gua_number(m.group()) for m in HEX_RE.finditer(raw)]
    c = Counter(nums)
    spans, outside = gua_spans(raw)
    got = {s.number for s in spans}
    print(f"  {w}: 卦39 symbol occurrences={c.get(39,0)}  on LIS chain={39 in got}")
    print(f"      missing from chain: {sorted(set(range(1,65)) - got)}")

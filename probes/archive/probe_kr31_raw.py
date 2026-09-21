"""Raw-text dumps for each 0031-specific failure, side by side with 0032.

The classifier says things like "貞 missing after 磐桓利居". Two very different causes
produce that: (a) the edition really lacks the character, (b) our clean() dropped it
because it sits inside a parenthesised 音訓 note. 原本周易本義 is the 經傳分離 arrangement
with 朱熹's phonetic glosses inline, so (b) is a live hypothesis. Only the raw bytes
can tell them apart.
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")

# (卦, 爻位, a probe string that should appear in the raw text near the failure)
CASES = [
    (3, "初九", "磐桓"), (3, "初九", "盤桓"),
    (5, "初九", "需于郊"),
    (23, "六五", "貫魚"),
    (26, "初九", "有厲利"),
    (27, "六四", "顛頤"), (27, "六四", "顚頤"),
    (30, "九三", "之離"),
    (32, "上六", "振"), (32, "六五", "其德貞婦人"), (32, "初六", "浚"),
    (35, "六五", "悔亡"),
    (36, "上六", "不明"), (36, "初九", "夷于飛"),
    (40, "上六", "公用射"),
    (42, "初九", "利用為大作"),
    (46, "上六", "升利于不息"),
    (48, "上六", "勿幕"), (48, "九五", "寒泉食"),
    (51, "六三", "行无眚"),
    (56, "六二", "其資得童僕"), (56, "初六", "斯其所取災"),
    (57, "九三", "巽吝"),
    (59, "初六", "馬壯吉"),
    (61, "九二", "鳴鶴"),
    (63, "九三", "高宗伐"), (63, "六四", "衣袽"),
]

bodies = {w: work_body(RAW, w) for w in ("KR1a0031", "KR1a0032")}

for gua, label, probe in CASES:
    print("=" * 78)
    print(f"卦{gua} {label}   probe={probe!r}")
    print("=" * 78)
    for w in ("KR1a0031", "KR1a0032"):
        raw = bodies[w]
        hits = [m.start() for m in re.finditer(re.escape(probe), raw)]
        if not hits:
            print(f"  [{w}] probe NOT FOUND in raw text")
            continue
        for at in hits[:2]:
            lo, hi = max(0, at - 60), min(len(raw), at + 90)
            ex = raw[lo:hi].replace("\n", "")
            print(f"  [{w}] raw@{at}: {ex}")
    print()

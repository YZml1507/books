"""Re-verify the one conclusion that used RAW substring matching.

The team lead reports Kanripo's ¶ can fall inside a token, so raw `find` yields spurious
misses. My category-(a) claim — "0031's 經 is contradicted by 0031's OWN 注/象傳, therefore
transcription corruption rather than 異文" — was tested with `phrase in raw`. That test can
only produce spurious FALSE, never spurious TRUE, so every True stands; but the Falses
need redoing on the cleaned view, where ¶, / and page markers are gone.

One False was already known and hand-corrected from the raw dump (極/拯, broken by a `/`).
This re-runs all of them mechanically.

Also checks whether the new classify_offchain already covers FIX-C, and whether the
proposed FIX-B/FIX-C would disturb ingest.AddrIndex.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import clean  # noqa: E402
from guji.anchors import classify_offchain  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
ALL = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"]
bodies = {w: work_body(RAW, w) for w in ALL}
# cleaned view WITH notes kept: the refutations live inside the parenthesised 注
views = {w: clean(r, keep_notes=True).text for w, r in bodies.items()}

# (卦爻, 0031's 經 reading, gold, the canonical form quoted by 0031's own 注 or 象傳)
CLAIMS = [
    ("卦30 九三", "日昊之離", "日昃之離", "日昃之離何可久也"),
    ("卦36 上六", "不明悔", "不明晦", "不明其德以至於晦"),
    ("卦40 上六", "公用射凖", "公用射隼", "公用射隼以解悖也"),
    ("卦42 初九", "大作无吉", "大作元吉", "必元吉然後得无咎"),
    ("卦59 初六", "用極馬壯", "用拯馬壯", "始渙而拯之為力既易"),
    ("卦5 初九", "利用怕", "利用恆", "需于郊不犯難行也利用恒无咎"),
    ("卦32 諸爻", "浚怕/怕其德/振怕", "恆", "怕亨尤咎利貞"),
    ("卦48 九五", "井冽寒泉食", "井洌", "洌潔也"),
    ("卦26 初九", "有厲利已", "利己", "有厲利己不犯災也"),
    ("卦3 初九", "磐桓利居利建侯", "…利居貞…", "其占利於居貞"),
    ("卦56 六二", "旅即懷其資", "旅即次懷", "即次則安懐資則裕"),
    ("卦63 九三", "高宗伐其鬼方", "高宗伐鬼方", "高宗伐鬼方之象也"),
    ("卦51 六三", "震蘓蘓行无眚", "震蘇蘇震行", "蘇蘇緩散自失之状"),
]
print("=" * 84)
print("category (a)/(c) refutations, re-tested on the CLEANED view of KR1a0031")
print("=" * 84)
print(f"{'cell':11} {'raw':>5} {'clean':>6}  refutation quoted by 0031 itself")
for cell, got, want, refute in CLAIMS:
    in_raw = refute in bodies["KR1a0031"]
    in_clean = refute in views["KR1a0031"]
    flag = "" if in_clean else "   <-- NOT FOUND even cleaned; claim withdrawn"
    print(f"{cell:11} {str(in_raw):>5} {str(in_clean):>6}  {refute!r}{flag}")
    if in_raw != in_clean:
        print(f"{'':11} {'':>5} {'':>6}  ^ raw miss was spurious (¶ or / inside the phrase)")

print("\n" + "=" * 84)
print("does classify_offchain already recover the 卦39 蹇 block? (FIX-C overlap)")
print("=" * 84)
for w in ("KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032"):
    cls = classify_offchain(bodies[w])
    zw = {p: k for p, k in cls.items() if k == "正文"}
    from collections import Counter
    print(f"  {w}: offchain={len(cls)} {dict(Counter(cls.values()))}")
    for p in sorted(zw):
        ctx = views[w][:0]  # placeholder to avoid confusion
        raw = bodies[w]
        import re as _re
        snippet = _re.sub(r"<pb:[^>]*>|[¶\n]", "", raw[p:p + 34])
        print(f"      正文 @{p}: {snippet}")

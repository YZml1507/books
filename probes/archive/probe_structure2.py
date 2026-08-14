"""Map the macro-layout of KR1a0007 before designing the span logic.

Discovery that forced this: the 坤 symbol-to-symbol span is 7,156 chars, yet 黃裳元吉
occurs 9 times across the work at scattered offsets. So 經 and 疏 are laid out in
separate passes and a symbol does NOT bound the commentary for its 卦.

Consequence: the earlier "94.9% attributed" figure measured only that characters fall
between consecutive symbols — not that they were attributed correctly. Same
coverage-vs-accuracy trap as the first attempt.

Here: locate every 乾/坤 爻辭 occurrence and every symbol, on one axis, and see the
shape of the document.
"""
import glob
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")

FOLD = {"濳": "潛", "羣": "群", "無": "无", "黄": "黃", "乗": "乘", "㓂": "寇",
        "眞": "真", "內": "内", "𫝊": "傳", "盤": "磐"}
DROP = set(" \t\r\n¶　/「」『』《》，。、：；？！·．")
HEX_RE = re.compile(r"[䷀-䷿]")

QIAN = ["潛龍勿用", "見龍在田利見大人", "君子終日乾乾夕惕若厲无咎",
        "或躍在淵无咎", "飛龍在天利見大人", "亢龍有悔", "見群龍无首吉"]
KUN = ["履霜堅冰至", "直方大不習无不利", "含章可貞", "括囊无咎",
       "黃裳元吉", "龍戰于野其血玄黃", "利永貞"]


def clean_map(s):
    out, idx, depth, i, n = [], [], 0, 0, len(s)
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
        elif ch not in DROP:
            out.append(FOLD.get(ch, ch))
            idx.append(i)
        i += 1
    return "".join(out), idx


def fold(s):
    return "".join(FOLD.get(c, c) for c in s)


for work in ("KR1a0007", "KR1a0006", "KR1a0016"):
    files = sorted(glob.glob(os.path.join(RAW, work, "*.txt")))
    raw = "".join(re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
                  for p in files)
    txt, imap = clean_map(raw)
    n = len(txt)
    print(f"\n{'='*74}\n{work}: {len(files)} files, {n:,} cleaned chars")

    syms = [(imap.index(m.start()) if m.start() in imap else None,
             ord(m.group()) - 0x4DC0 + 1) for m in HEX_RE.finditer(raw)]
    syms = [(p, g) for p, g in syms if p is not None]
    print(f"  symbols mapped into cleaned space: {len(syms)}")

    # decile histogram of where 乾 and 坤 爻辭 occur
    def hist(phrases, label):
        buckets = [0] * 10
        total = 0
        for ph in phrases:
            for m in re.finditer(re.escape(fold(ph)), txt):
                buckets[min(9, m.start() * 10 // n)] += 1
                total += 1
        bar = " ".join(f"{b:>3}" for b in buckets)
        print(f"  {label:4} {total:>3} hits by decile: {bar}")

    hist(QIAN, "乾")
    hist(KUN, "坤")
    sym_b = [0] * 10
    for p, g in syms:
        sym_b[min(9, p * 10 // n)] += 1
    print(f"  sym  {len(syms):>3} hits by decile: " + " ".join(f"{b:>3}" for b in sym_b))

    # how many distinct 卦 symbols per decile, and are they ascending within it?
    print("  decile detail (symbol 卦 numbers):")
    for d in range(10):
        lo, hi = d * n // 10, (d + 1) * n // 10
        got = [g for p, g in syms if lo <= p < hi]
        if got:
            asc = all(b >= a for a, b in zip(got, got[1:]))
            print(f"    d{d}: n={len(got):>2} {'ASC' if asc else 'mixed'} {got[:14]}")

    # where does the FIRST full 乾 爻辭 chain complete, vs the last?
    firsts = [re.search(re.escape(fold(p)), txt) for p in QIAN]
    if all(firsts):
        spans = [m.start() for m in firsts]
        print(f"  乾 first-occurrence offsets: {spans}")
        print(f"    ascending? {all(b > a for a, b in zip(spans, spans[1:]))}")
    lasts = []
    for p in QIAN:
        ms = [m.start() for m in re.finditer(re.escape(fold(p)), txt)]
        lasts.append(ms[-1] if ms else None)
    print(f"  乾 last-occurrence offsets:  {lasts}")

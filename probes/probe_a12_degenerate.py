"""A-12 span-degenerate investigation.

The cross-edition quality gate (quality.py) flags 5 addresses in KR1a0007 as
span-degenerate-B: the ordered 爻位 search matched 孔穎達's cross-reference to
the 爻位 inside a 括号注, rather than the 爻辭 itself. R-02 already rejected
"retry the next occurrence" (anchors._repair_degenerate). The task book suggests
a new candidate: exclude occurrences inside 括号注 (parenthesised commentary).

This probe:
  1. Locates the 5 span-degenerate addresses in KR1a0007.
  2. For each, shows what the current extract_yao matched (the cross-ref).
  3. Tests the "exclude 括号注" candidate: does the 爻辭 sit outside 括号注,
     and would restricting the search to non-括号注 text fix the degenerate spans?

All numbers come from script output, not memory (GOAL §2).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import clean, extract_yao, gua_spans, yao_names
from guji.ingest import ZHOUYI_WORKS
from guji.zhouyi import derive_polarity, work_body

RAW_DIR = os.path.join(ROOT, "data", "raw")
WORK = "KR1a0007"

# The 5 span-degenerate-B addresses from quality_report.json
# (measured: KR1a0006|KR1a0007 low entries with verdict span-degenerate-B)
DEGENERATE = [
    (46, "九二", "len_b=2"),
    (9, "九二", "len_b=5"),
    (9, "初九", "len_b=7"),
    (58, "九五", "len_b=10"),
    (46, "初六", "len_b=27"),
]


def load_work():
    files = sorted(f for f in os.listdir(os.path.join(RAW_DIR, WORK))
                   if f.endswith(".txt"))
    all_text = ""
    for f in files:
        all_text += open(os.path.join(RAW_DIR, WORK, f),
                         encoding="utf-8", errors="replace").read()
    return all_text


def main():
    all_text = load_work()
    # gua_spans returns a nested structure (tuple of lists per file, or list).
    # Flatten robustly.
    raw_spans = gua_spans(all_text)
    flat = []
    for item in raw_spans:
        if hasattr(item, "number"):
            flat.append(item)
        elif isinstance(item, (list, tuple)):
            for sub in item:
                if hasattr(sub, "number"):
                    flat.append(sub)
    print(f"loaded {len(all_text)} chars, {len(flat)} gua spans")

    # derive polarity for yao_names (polarity[卦] = 6-tuple of line polarity)
    zy_bodies = {WORK: work_body(RAW_DIR, WORK)}
    polarity = derive_polarity(zy_bodies)
    print(f"polarity for 卦9: {polarity.get(9)}")
    print(f"polarity for 卦46: {polarity.get(46)}")
    print(f"polarity for 卦58: {polarity.get(58)}")

    for gua_num, target_yao, note in DEGENERATE:
        spans = [s for s in flat if s.number == gua_num]
        if not spans:
            print(f"\n卦{gua_num}: NO SPAN FOUND")
            continue
        sp = spans[0]
        seg = all_text[sp.start:sp.end]
        expected = yao_names(polarity[gua_num])
        found = extract_yao(seg, expected)
        view = clean(seg, keep_notes=False)

        print(f"\n=== 卦{gua_num} — target {target_yao} ({note}) ===")
        print(f"expected 爻位: {expected}")
        print("found positions:")
        for yao in expected:
            pos = found.get(yao)
            if pos:
                s, e = pos
                mark = " <<< TARGET" if yao == target_yao else ""
                print(f"  {yao}: [{s}:{e}] len={e-s} "
                      f"text={view.text[s:e][:40]!r}{mark}")
            else:
                print(f"  {yao}: NOT FOUND")

        # Show the raw segment context around the target yao's position
        pos = found.get(target_yao)
        if pos:
            s, e = pos
            raw_pos = view.text[s:e] if s < len(view.text) else ""
            print(f"raw matched text: {raw_pos!r}")

        # Look at the full raw seg to understand 孔穎達's structure
        print(f"raw seg len: {len(seg)}")
        print(f"raw seg first 500 chars: {seg[:500]!r}")


if __name__ == "__main__":
    main()

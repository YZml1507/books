"""T5 A-12 local-strip candidates for quality.py::addresses_of.

N1 (global clean change) was rejected: it stripped the 经 view used by
addresses_of/extract_yao, dropping 69 comparable addresses (362 -> 293, T11 FAIL).
Task book asks for candidates that ONLY change quality.py::addresses_of locally.

Candidates simulated here (in memory, no source change):

  P1  cut every B address at the first 「注」 in its span text
      (naked-note start). Span end stays the next label otherwise.
  P2  P1 but only when 「注」 is NOT preceded by 彖/象 (structure content).
  P3  cut at the first 「注」 ONLY if the remaining head is shorter than the
      original by >= 3 chars AND the head looks like a 爻辭 (no 彖曰/象曰 yet).

Each candidate is scored the same way cross_edition_coverage + verify_index T11
do: compared count (>= 358), median coverage (>= 0.95), and the 5 EXPECTED
len_b values (want 卦58 九五 / 卦46 初六 to drop).
"""
import difflib
import os
import statistics
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.quality import addresses_of  # noqa: E402
from guji.zhouyi import derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
EXPECTED = {(46, "九二"), (9, "九二"), (9, "初九"), (58, "九五"), (46, "初六")}


def cut_first_zhù(t: str, require_head: bool = False) -> str:
    """P1: cut at the first 「注」 (naked-note marker)."""
    i = t.find("注")
    if i < 0:
        return t
    head = t[:i]
    if require_head and len(head) < 4:
        return t
    return head


def cut_not_structure(t: str) -> str:
    """P2: cut at first 「注」 unless preceded by 彖/象 structure content."""
    i = t.find("注")
    if i < 0:
        return t
    prev = t[max(0, i - 2):i]
    if "彖" in prev or "象" in prev:
        return t
    return t[:i]


def cut_yao_only(t: str) -> str:
    """P3: cut at first 「注」 only when the head is a plausible 爻辭
    (no 彖曰/象曰 inside the head) and the note is not tiny."""
    i = t.find("注")
    if i < 0:
        return t
    head = t[:i]
    if "彖曰" in head or "象曰" in head:
        return t
    if len(head) < 4:
        return t
    return head


# ---------------------------------------------------------------------------
# P4 / P5: SYMMETRIC stripping — A and B BOTH lose their notes, so the
# T11 comparison stays aligned. A's notes are parenthesised (KR1a0006 王弼注:
# 18 paren pairs in 卦58, zero 「注」 chars), so 经-only slicing removes them.
# B's 王弼 notes are naked (「注」-marked), so additionally cut at 「注」.
# ---------------------------------------------------------------------------
def addresses_of_jing(raw: str, polarity, strip_naked: bool = False):
    """Copy of addresses_of that slices the 经 view (keep_notes=False) instead
    of the with-notes view, optionally cutting B's naked notes at 「注」."""
    from guji.anchors import clean, extract_yao, gua_spans, yao_names
    spans, _ = gua_spans(raw)
    out: dict = {}
    seen: set = set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        exp = yao_names(polarity[s.number])
        seg = raw[s.start:s.end]
        jing = clean(seg, keep_notes=False)
        hits = extract_yao(seg, exp, jing=jing)
        marks = sorted((v[0], k) for k, v in hits.items() if v)
        for n, (pos, label) in enumerate(marks):
            if pos < 0:
                continue
            j1 = marks[n + 1][0] if n + 1 < len(marks) else len(jing.text)
            txt = jing.text[pos:j1]
            if strip_naked:
                i = txt.find("注")
                if i > 0:
                    txt = txt[:i]
            out[(s.number, label)] = txt
    return out


def score_jing(name, bodies, pol, strip_naked):
    """Score the symmetric (经-only) variant exactly like cross_edition_coverage."""
    ta = addresses_of_jing(bodies["KR1a0006"], pol, strip_naked=False)
    tb = addresses_of_jing(bodies["KR1a0007"], pol, strip_naked=strip_naked)
    out = []
    for key in sorted(set(ta) & set(tb)):
        a, b = ta[key], tb[key]
        if len(a) < 20:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        blocks = sm.get_matching_blocks()
        covered = sum(bl.size for bl in blocks)
        longest = max((bl.size for bl in blocks), default=0)
        subs = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and (i2 - i1) == (j2 - j1) and (i2 - i1) <= 3:
                subs += sum(1 for k in range(i2 - i1) if a[i1 + k] != b[j1 + k])
        out.append((key[0], key[1], covered / len(a), len(a), len(b), longest, subs))
    covs = [d[2] for d in out]
    exp = {}
    for d in out:
        if (d[0], d[1]) in EXPECTED:
            exp[(d[0], d[1])] = d[4]
    print(f"\n=== {name} ===")
    print(f"  compared={len(out)}  median_cov={statistics.median(covs):.3f}")
    print("  EXPECTED len_b: " + "  ".join(f"{g}{y}={exp.get((g, y), '?')}" for g, y in sorted(EXPECTED)))


CUTTERS = {
    "P1-cut-first-注": cut_first_zhù,
    "P2-not-after-structure": cut_not_structure,
    "P3-yao-head-only": cut_yao_only,
}


def score(name: str, cut, bodies, pol):
    ta = addresses_of(bodies["KR1a0006"], pol)
    tb = addresses_of(bodies["KR1a0007"], pol)
    tb = {k: (cut(v) if v else v) for k, v in tb.items()}

    out = []
    for key in sorted(set(ta) & set(tb)):
        a, b = ta[key], tb[key]
        if len(a) < 20:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        blocks = sm.get_matching_blocks()
        covered = sum(bl.size for bl in blocks)
        longest = max((bl.size for bl in blocks), default=0)
        subs = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and (i2 - i1) == (j2 - j1) and (i2 - i1) <= 3:
                subs += sum(1 for k in range(i2 - i1) if a[i1 + k] != b[j1 + k])
        out.append((key[0], key[1], covered / len(a), len(a), len(b), longest, subs))

    covs = [d[2] for d in out]
    exp = {}
    for d in out:
        if (d[0], d[1]) in EXPECTED:
            exp[(d[0], d[1])] = d[4]
    print(f"\n=== {name} ===")
    print(f"  compared={len(out)}  median_cov={statistics.median(covs):.3f}")
    print("  EXPECTED len_b: " + "  ".join(f"{g}{y}={exp.get((g, y), '?')}" for g, y in sorted(EXPECTED)))


def main():
    bodies = {w: work_body(RAW, w) for w in ["KR1a0006", "KR1a0007"]}
    pol = derive_polarity(bodies)

    # baseline (no cutting)
    score("BASELINE (no cut)", lambda t: t, bodies, pol)
    for name, fn in CUTTERS.items():
        score(name, fn, bodies, pol)
    # symmetric 经-only variants
    score_jing("P4-jing-only-B-no-naked", bodies, pol, strip_naked=False)
    score_jing("P5-jing-only-B-cut-naked", bodies, pol, strip_naked=True)


if __name__ == "__main__":
    main()

"""Corpus quality gates that need no language model and no external service.

The project had been treating Kanripo plain text as clean ground truth. It is not:
KR1a0006 卦61 中孚 is OCR-damaged, reading

    上九翰青登于天貞凶輪高飛也狀音堵昔莊而寳才從之謂也届卦之上處信芝絃信終剛唐志罵內喪筆美外揚

where the independent witness KR1a0007 has

    上九翰音登于天貞凶注翰高飛也飛音者音飛而實不從之謂也居卦之上處信之終信終則衰忠篤內喪華美外揚

青/音, 輪/翰, 届/居, 芝絃/之終, 筆/華 are visually-similar substitutions — the OCR signature
of D-001, in a source that carries no CID fonts at all.

Two detectors, and the difference between them is the lesson:

`rarity_scores` (character-bigram implausibility) FAILED its control. It ranked the known-bad
window 599th of 88,530 — below its own 99.5th percentile — and its top hits were all false
positives, because 太玄經's 音義 glossary (`廬偈音傑…音吪動也`) is legitimately full of
unattested bigrams. Kept in the codebase as a negative result, not as a gate.

`cross_edition_coverage` PASSED: rank 2 of 358, coverage 0.050 against a median of 0.991.
It works because it consults an independent witness instead of guessing from surface
statistics — and it costs nothing extra, since the 卦/爻 join key it needs already exists
for its own sake (D-005).

A quality gate without a known-positive control proves nothing. Both functions below are
calibrated against the 卦61 case and the calibration is asserted in scripts/verify_index.py.
"""
from __future__ import annotations

import collections
import difflib
import re
from dataclasses import dataclass

from .anchors import clean, extract_yao, gua_spans, yao_names
from .variants import fold

CJK_RE = re.compile(r"[一-鿿𠀀-𯨟]")


def cjk_only(s: str) -> str:
    return "".join(CJK_RE.findall(fold(s)))


# --------------------------------------------------------------------------------------
# Detector 1 (NEGATIVE RESULT — do not use as a gate)
# --------------------------------------------------------------------------------------
def rarity_scores(texts: dict[str, str], window: int = 60):
    """Unattested-bigram rate per window. Retained to document that it does NOT work.

    Measured: the one region known to be corrupt ranked 599/88,530, while 太玄經's phonetic
    glossary occupied every top slot. Classical Chinese glossaries and name lists are
    indistinguishable from OCR junk by surface rarity alone.
    """
    big: collections.Counter = collections.Counter()
    uni: collections.Counter = collections.Counter()
    cleaned = {w: cjk_only(t) for w, t in texts.items()}
    for t in cleaned.values():
        uni.update(t)
        big.update(t[i:i + 2] for i in range(len(t) - 1))
    out = []
    for w, t in cleaned.items():
        for i in range(0, max(len(t) - window, 0), window // 2):
            s = t[i:i + window]
            bs = [s[j:j + 2] for j in range(len(s) - 1)]
            if len(bs) < 11:
                continue
            out.append((sum(1 for b in bs if big[b] <= 1) / len(bs), w, i, s))
    out.sort(reverse=True)
    return out


# --------------------------------------------------------------------------------------
# Detector 2 (THE GATE)
# --------------------------------------------------------------------------------------
@dataclass
class AddressDiff:
    gua: int
    yao: str
    coverage: float      # fraction of A's text recoverable inside B
    len_a: int
    len_b: int
    text_a: str
    text_b: str
    longest_block: int = 0     # longest common run, in characters
    # Count of short, equal-length replacements — the OCR signature itself (D-012). Kept as
    # its own measurement because contiguity alone cannot tell "the same passage, miscut" from
    # "a different passage of similar length"; see `verdict`.
    substitutions: int = 0

    @property
    def contiguity(self) -> float:
        """longest common run / length of the shorter text.

        This is what separates the two failure modes, and length ratios alone got it wrong:
        KR1a0006 卦61 was first classified 'span-defect-B' purely because len_b was small,
        when in fact B was the correct length and A had over-extended — A's span swallowed
        卦62, whose hexagram symbol the edition misprints as ䷋ (卦12), the same source typo
        recorded in D-006, so LIS drops it and the span runs on.

        Scattered short matches  -> characters were substituted throughout (OCR damage).
        One long match + a tail   -> the texts agree, one span merely covers more ground.
        """
        short = min(self.len_a, self.len_b)
        return self.longest_block / short if short else 0.0

    @property
    def verdict(self) -> str:
        """Classify the divergence. `text-damage` requires the OCR SIGNATURE, not just low
        contiguity.

        Low contiguity was the sole test, and it produced a false positive that mattered:
        KR1a0006 卦47 上六 scored contiguity 0.199 and was reported `text-damage`, which put it
        in the `suspect` column, which made the answering layer REFUSE it (G7). It is not
        damaged. Measured side by side (probes/probe_gua47.py):

            卦47 上六   2 substitutions (纏/纒 orthographic, 困/因), longest common run 92
                       — KR1a0006's span simply runs on into 卦48 井, and KR1a0007 carries
                         音義/疏 apparatus the other lacks
            卦61 上九  19 substitutions, all visually similar (青/音 狀/飛 堵/者 寳/實 届/居
                       芝/之 絃/終 筆/華 …), longest common run 6 — genuine OCR damage

        So damage is "many small visually-similar swaps scattered through a passage the two
        witnesses otherwise share", and a long common run is evidence AGAINST it. Requiring
        >= 5 substitutions keeps the 卦61 control firing while releasing 卦47. Marking sound
        text as damaged is not a harmless excess of caution here: it withholds real evidence
        from a reader and it is invisible unless someone reads the passage.
        """
        if self.len_b < 30:
            return "span-degenerate-B"
        if self.len_a < 30:
            return "span-degenerate-A"
        if self.contiguity < 0.25 and self.substitutions >= 5:
            return "text-damage"
        return "span-overextended-A" if self.len_a > self.len_b else "span-overextended-B"


def addresses_of(raw: str, polarity: dict[int, tuple[int, ...]]) -> dict[tuple, str]:
    """{(卦, 爻): everything printed between this 爻位 and the next} for one work.

    The window runs from this label's raw offset to the NEXT LABEL's raw offset (span end
    for the last), and is then read out of the with-notes view.

    An earlier version ended the window at the last 經 CHARACTER before the next label
    (`r1 = jing.origin(end - 1)`), which made the function mean different things in
    different editions and nearly blinded the gate that depends on it:

      * where the 注 is parenthesised (KR1a0031/0032), every note fell OUTSIDE the window,
        so an address returned 爻辭-only — median 9 characters;
      * where the 注 is inline with a literal 注 marker (KR1a0007), the note was already
        inside the 經-only view and DID come back — median 102 characters.

    Consequence, measured (probes/probe_addresses_fix.py): cross_edition_coverage dropped
    360 of 377 shared KR1a0031/0032 addresses to its own min_len=20 filter and then
    reported "median coverage 1.000, below 0.60: 0" — a perfect score over 4.5% of the
    pair. The ledger read that as evidence for G3. It was not evidence of much.

    After the fix: 373 of 377 compared, median 0.985, and two real outliers surface
    (卦23六四, 卦61初九) which are the very addresses detect_mislabelled_yao already flags
    as misprinted 爻位 in KR1a0031 — two independent detectors agreeing.
    """
    spans, _ = gua_spans(raw)
    out: dict[tuple, str] = {}
    seen: set[int] = set()
    for s in spans:
        if s.number not in polarity or s.number in seen:
            continue
        seen.add(s.number)
        exp = yao_names(polarity[s.number])
        seg = raw[s.start:s.end]
        view = clean(seg, keep_notes=True)
        jing = clean(seg, keep_notes=False)
        hits = extract_yao(seg, exp, jing=jing)
        marks = sorted((v[0], k) for k, v in hits.items() if v)
        # 經 coords -> raw -> with-notes coords. Both views map back to raw offsets, so the
        # translation goes through raw and never through arithmetic on cleaned text.
        for n, (pos, label) in enumerate(marks):
            r0 = jing.origin(pos)
            if r0 < 0:
                continue
            r1 = jing.origin(marks[n + 1][0]) if n + 1 < len(marks) else s.end
            import bisect
            v0 = bisect.bisect_left(view.offsets, r0)
            v1 = bisect.bisect_left(view.offsets, r1) if r1 >= 0 else len(view.text)
            out[(s.number, label)] = view.text[v0:v1]
    return out


def cross_edition_coverage(raw_a: str, raw_b: str,
                           polarity: dict[int, tuple[int, ...]],
                           min_len: int = 20) -> list[AddressDiff]:
    """Compare two textually-dependent editions at every shared canonical address.

    Precondition: B embeds A near-verbatim (KR1a0007 註疏 embeds KR1a0006 王弼注). Measured
    median coverage 0.991 / mean 0.965 over 358 shared addresses, so a low value is a real
    outlier rather than ordinary edition variance.

    Returned ascending by coverage: the worst offenders first.
    """
    ta, tb = addresses_of(raw_a, polarity), addresses_of(raw_b, polarity)
    out: list[AddressDiff] = []
    for key in sorted(set(ta) & set(tb)):
        a, b = ta[key], tb[key]
        if len(a) < min_len:
            continue
        sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
        blocks = sm.get_matching_blocks()
        covered = sum(bl.size for bl in blocks)
        longest = max((bl.size for bl in blocks), default=0)
        # Short, equal-length replacements: one character swapped for another at the same
        # position. That is what a miscut woodblock character looks like; a span boundary
        # error looks like one big insert or delete instead.
        subs = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "replace" and (i2 - i1) == (j2 - j1) and (i2 - i1) <= 3:
                subs += sum(1 for k in range(i2 - i1) if a[i1 + k] != b[j1 + k])
        out.append(AddressDiff(key[0], key[1], covered / len(a), len(a), len(b),
                               a, b, longest, subs))
    out.sort(key=lambda d: d.coverage)
    return out

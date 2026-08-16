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

import bisect
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

# 5 卦/爻 addresses in KR1a0007 where span-degenerate-B is a property of the SOURCE
# edition (王弼 commentary glued flush to the 爻辭, no separator), not a parser defect.
# Measured in probes/probe_a12_degenerate.py (2026-08-14). See `AddressDiff.verdict` for
# the full per-address rationale and why the two candidate repairs each have a counter-
# example. Any NEW span-degenerate-B in KR1a0007 is a real defect and still fires.
EXPECTED_DEGENERATE: set[tuple[int, str]] = {
    (46, "九二"),
    (9, "九二"),
    (9, "初九"),
    (58, "九五"),
    (46, "初六"),
}


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
        EXPECTED_DEGENERATE documents the 5 卦/爻 addresses in KR1a0007 (註疏, 王弼+
        孔穎達) where span-degenerate-B is a property of the SOURCE edition, not a parser
        defect. Measured in probes/probe_a12_degenerate.py (2026-08-14, every number from
        script output):

            卦46 九二  len_b=2   — extract_yao matched 孔穎達疏「九二孚乃利用禴」 first; the
                      爻辭「孚乃利用禴无咎」 lives in the 疏, and the 爻位 label alone is all
                      that remains in the 經 view (2 chars).
            卦9  九二  len_b=5   — 爻辭「之牽復」(3) + 爻位「九二」(2) = 5, genuinely short 爻辭.
            卦9  初九  len_b=7   — 爻辭「之復自道固」(5) + 爻位「初九」(2) = 7, genuinely short 爻辭.
            卦58 九五  len_b=10  — 爻辭「孚于剝有厲」(6) + 爻位(2) + 「注」 + 1 注字 = 10; 王弼注
                      「注比于...」 is glued to the 爻辭 with no separator in this edition.
            卦46 初六  len_b=27  — 爻辭「允升大吉」(4) + 爻位(2) + 王弼注「注允當也巽卦三爻...」
                      (21) = 27; the 裸注 is glued to the 爻辭 with no separator.

        The root cause is 王弼's commentary being printed flush against the 爻辭 with NO
        separator (unlike 孔穎達's parenthesised �疏 `(正義曰...)`), so extract_yao runs the
        爻位→next 爻位 span and admits the 裸注 into the 經 view. R-02 already rejected
        "retry the next occurrence" (anchors._repair_degenerate) — it misfires on other
        editions. Two candidate repairs were measured and each has a counter-example:

          A. reject spans shorter than a 爻辭-length lower bound — 爻辭 as short as
             「履霜堅冰至」(6 chars) exist in the corpus, so a threshold either misses
             卦9 爻辭 (7 chars, genuine) or admits 卦46 裸注 (27 chars, glued).
          B. cut the span at the first 「注」 after the 爻辭 — rescues 卦58/46 初六 but
             卦46 九二 has no 裸注 to cut (its 爻辭 was seized by the 疏); and a 「注」
             inside 爻辭 text (e.g. 卦1 «注» interior) would be a false cut.

        Net: the 5 are not parser bugs fixable without a new false positive. They are
        marked EXPECTED so the gate stops reporting them as regressions; any NEW
        span-degenerate-B in KR1a0007 is a real defect and still fires. This is the U-08
        discipline applied to span-degenerate: surface the known, refuse to hide the new.
        """
        if (self.gua, self.yao) in EXPECTED_DEGENERATE:
            return "span-degenerate-B (EXPECTED)"
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


# --------------------------------------------------------------------------------------
# Detector 3 — junk census (PUA, CJK-Ext-A, U+FFFD, (cid:N) markers)
# --------------------------------------------------------------------------------------
# Q-06: a junk census must count `(cid:N)` markers, which are ASCII and therefore
# invisible to a pure code-point scan.  These markers are the loud-failure mode of
# markitdown on Identity-H subset fonts (D-001), the same failure mode that
# `probe_crosssource.py` already prints ad hoc.  Productised here so the quality
# gate can report a single junk rate per work rather than relying on a probe.

_CID_RE = re.compile(r"\(cid:\d+\)")


@dataclass
class JunkReport:
    work: str
    n_chars: int            # non-space chars scanned
    pua: int                # Private Use Area (U+E000..U+F8FF)
    ext_a: int              # CJK Extension A (U+3400..U+4DBF)
    repl: int               # U+FFFD replacement character
    cid: int                # count of (cid:N) markers
    junk_rate: float        # (pua + ext_a + repl + cid) / n_chars

    @property
    def junk(self) -> int:
        return self.pua + self.ext_a + self.repl + self.cid


def junk_census(text: str, work: str = "") -> JunkReport:
    """Count junk markers in `text`.

    Junk is defined as characters that cannot be legitimate Classical Chinese
    text but are common OCR/extraction artefacts:

      * PUA (U+E000..U+F8FF): un-mapped subset-font glyphs dumped to PUA.
      * CJK Ext A (U+3400..U+4DBF): rare in real modern text, common as
        mis-mapped output from Identity-H fonts.
      * U+FFFD: replacement character, the universal "could not decode" flag.
      * `(cid:N)` markers: ASCII strings emitted by markitdown when it cannot
        resolve a CID to a Unicode code point (Q-06).  These are invisible to
        a pure code-point census, which is exactly why they must be counted
        explicitly.
    """
    ns = [c for c in text if not c.isspace()]
    n = len(ns)
    pua = sum(1 for c in ns if 0xE000 <= ord(c) <= 0xF8FF)
    ext_a = sum(1 for c in ns if 0x3400 <= ord(c) <= 0x4DBF)
    repl = sum(1 for c in ns if ord(c) == 0xFFFD)
    cid = len(_CID_RE.findall(text))
    total = pua + ext_a + repl + cid
    return JunkReport(
        work=work, n_chars=n, pua=pua, ext_a=ext_a, repl=repl, cid=cid,
        junk_rate=(total / n) if n else 0.0,
    )

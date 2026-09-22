"""卦/爻 addressing for 周易 texts: the join key that makes cross-commentator
comparison possible.

Design forced by measurement, not preference:

* 卦 boundaries come from the Unicode hexagram symbols U+4DC0..U+4DFF, which appear
  in King Wen order in the main body of every commentary tested. This replaces the
  earlier phrase carry-forward approach, whose 84% "coverage" hid drift up to 610
  units and demonstrable misattribution.
* The 十翼 tail (繫辭/說卦/序卦/雜卦) re-cites hexagrams out of order, so the main body
  is the leading ascending run and the tail must be excluded rather than attributed.
* 爻 boundaries come from the 爻辭 the commentary structurally quotes, NOT from 爻位
  tokens: 六二 and 六五 occur inside 乾's span in KR1a0007 because 孔穎達 cross-references
  other 卦's lines, and 乾 has no yin lines at all.
* 爻位 tokens are additionally unsafe to scan globally: in 「初九潛龍勿用九二」 the
  substring 用九 matches across 勿用+九二, truncating the preceding 爻辭.
  Hence ordered, non-overlapping search.
* Anything not confidently attributed is returned as None. Unknown is a first-class
  value; guessing is what made the previous attempt unusable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .variants import DROP, FOLD, fold

HEX_RE = re.compile(r"[䷀-䷿]")
PB_RE = re.compile(r"<pb:([^>]+)>")

# 《升第四十六》-style headings announce the next 卦 and PRECEDE its hexagram
# symbol — a span ending at the next symbol would swallow this heading into the
# previous 卦's last 爻 (real bug: 卦45·上六 returned 「** 《升第四十六》」).
_HEADING_RE = re.compile(r"《[一-鿿]{1,4}第([一二三四五六七八九十]{1,4})》")
_NUMERALS = {c: i for i, c in enumerate("一二三四五六七八九十", 1)}


def _cn_number(s: str) -> int | None:
    """十一 -> 11, 三十七 -> 37. Only needs to cover 1..64."""
    if s in _NUMERALS:
        return _NUMERALS[s]
    if "十" not in s:
        return None
    tens, _, ones = s.partition("十")
    return _NUMERALS.get(tens, 1) * 10 + _NUMERALS.get(ones, 0)

# Bottom-to-top line polarity, 1 = yang (九), 0 = yin (六).
TRIGRAM_LINES = {
    "乾": (1, 1, 1), "坤": (0, 0, 0), "震": (1, 0, 0), "艮": (0, 0, 1),
    "離": (1, 0, 1), "坎": (0, 1, 0), "兌": (1, 1, 0), "巽": (0, 1, 1),
}
_POS_NAMES = ["初", "二", "三", "四", "五", "上"]


def gua_number(symbol: str) -> int:
    """U+4DC0 is 卦1 乾; King Wen order follows."""
    return ord(symbol) - 0x4DC0 + 1


def gua_symbol(number: int) -> str:
    return chr(0x4DC0 + number - 1)


def yao_names(lines: tuple[int, ...]) -> list[str]:
    """爻位 labels for a hexagram given its six line polarities, bottom to top.
    乾 additionally has 用九 and 坤 用六 — they are real addressable units."""
    names = []
    for i, pol in enumerate(lines):
        p = "九" if pol else "六"
        names.append(f"初{p}" if i == 0 else f"上{p}" if i == 5 else f"{p}{_POS_NAMES[i]}")
    if all(lines):
        names.append("用九")
    elif not any(lines):
        names.append("用六")
    return names


def lines_from_trigrams(lower: str, upper: str) -> tuple[int, ...] | None:
    lo, up = TRIGRAM_LINES.get(fold(lower)), TRIGRAM_LINES.get(fold(upper))
    return None if lo is None or up is None else lo + up


@dataclass
class Cleaned:
    """Text with markup removed, plus a map back to original offsets so every
    extracted span stays citable in the source file."""
    text: str
    offsets: list[int]

    def origin(self, i: int) -> int:
        return self.offsets[i] if 0 <= i < len(self.offsets) else -1


def clean(raw: str, keep_notes: bool = False) -> Cleaned:
    """Strip page markers, punctuation and layout. When keep_notes is False the
    parenthesised 注 is dropped, giving a 經-only view.

    Parenthesis nesting was verified balanced across the corpus (delta 0, max depth 1
    in all six works), so a depth counter is safe here — but it is still clamped at
    zero so a malformed source degrades instead of swallowing the rest of the file.
    """
    out: list[str] = []
    idx: list[int] = []
    depth = 0
    i, n = 0, len(raw)
    while i < n:
        if raw.startswith("<pb:", i):
            j = raw.find(">", i)
            i = n if j == -1 else j + 1
            continue
        ch = raw[i]
        if ch in "（(":
            depth += 1
        elif ch in "）)":
            depth = max(0, depth - 1)
        elif (depth == 0 or keep_notes) and ch not in DROP:
            out.append(FOLD.get(ch, ch))
            idx.append(i)
        i += 1
    return Cleaned("".join(out), idx)


@dataclass
class GuaSpan:
    number: int
    start: int          # raw offset, inclusive
    end: int            # raw offset, exclusive
    page_anchor: str | None   # nearest preceding <pb:> for citation


def _nearest_anchor(raw: str, at: int) -> str | None:
    last = None
    for m in PB_RE.finditer(raw, 0, at + 1):
        last = m.group(1)
    return last


def _longest_increasing(values: list[int]) -> list[int]:
    """Indices of a longest STRICTLY increasing subsequence, O(n log n)."""
    import bisect

    tails: list[int] = []      # tails[k] = index of smallest tail for length k+1
    prev: list[int] = [-1] * len(values)
    tail_vals: list[int] = []
    for i, v in enumerate(values):
        k = bisect.bisect_left(tail_vals, v)
        if k == len(tail_vals):
            tail_vals.append(v)
            tails.append(i)
        else:
            tail_vals[k] = v
            tails[k] = i
        prev[i] = tails[k - 1] if k > 0 else -1
    out: list[int] = []
    cur = tails[-1] if tails else -1
    while cur != -1:
        out.append(cur)
        cur = prev[cur]
    return out[::-1]


def gua_spans(raw: str) -> tuple[list[GuaSpan], list[int]]:
    """Segment the main body by hexagram symbol.

    Selection is a longest strictly increasing subsequence over the symbols' King Wen
    numbers, not a greedy leading run. Greedy failed on two real cases:
      * KR1a0007 carries a source typo (卦52 sitting between 17 and 19). Greedy accepted
        it, raised its high-water mark to 52, then rejected the genuine 19..51 that
        followed — 63 spans collapsed to 18.
      * KR1a0031/0032 put 朱熹's 卦變 diagram block BEFORE the sequential body, so there
        is no leading ascending run at all and greedy found 1 span out of 64.
    LIS discards isolated anomalies and whole out-of-order blocks without special-casing
    either. Strictness also drops repeated 卦 numbers, which greedy kept.

    Returns (spans, outside) where `outside` is every symbol not on the chosen chain:
    十翼 cross-references AND 卦變 diagram entries. Those two are different things and
    are not yet told apart — see docs/DECISIONS.md D-006.
    """
    marks = [(m.start(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    if not marks:
        return [], []

    keep = set(_longest_increasing([n for _, n in marks]))

    # The LAST span must not run to end-of-file. The 十翼 (繫辭/說卦/序卦/雜卦) follow the
    # final 卦, and letting the span swallow them attributes 十翼 prose to 卦64 as if it
    # were commentary on that hexagram. Stop at the first off-chain symbol that comes
    # after the last chain symbol instead.
    last_kept = max(keep) if keep else -1
    tail_at = next((p for j, (p, _) in enumerate(marks)
                    if j > last_kept and j not in keep), None)

    spans = []
    for k, (pos, num) in enumerate(marks):
        if k not in keep:
            continue
        nxt_pair = next(((p, marks[j][1]) for j, (p, _) in enumerate(marks)
                         if j > k and j in keep), None)
        if nxt_pair is None:
            nxt = tail_at if tail_at is not None else len(raw)
        else:
            nxt = nxt_pair[0]
            # The next 卦's own 《X第N》 heading sits between this span's symbol
            # and its symbol — cut the span at the heading so the title line is
            # not filed under this 卦's last 爻 (卦45·上六 read 「《升第四十六》」).
            _h = _HEADING_RE.search(raw, pos, nxt)
            if _h is not None and _cn_number(_h.group(1)) == nxt_pair[1]:
                # Back over the heading's decorations (「** 」markdown, <pb:>
                # page anchor, ¶/空白) — cutting at 《 leaves them inside this
                # span's tail where the stray title line still inherits 上六.
                _m2 = re.search(r"(?:<pb:[^>]+>|[\s*¶])*$",
                                raw[pos:_h.start()])
                nxt = _m2.start() + pos if _m2 else _h.start()
        spans.append(GuaSpan(num, pos, nxt, _nearest_anchor(raw, pos)))
    return spans, [n for k, (_, n) in enumerate(marks) if k not in keep]


_TRIGRAM_NOTE_RE = re.compile(
    r"^[䷀-䷿][（(]?[^（()）/]{1,3}下\s*/?\s*[^（()）/]{1,3}上[）)]?")


def classify_offchain(raw: str, window: int = 60,
                      dense: int = 4) -> dict[int, str]:
    """Label each off-chain hexagram symbol 圖 / 正文 / 十翼.

    Three kinds, not two. The first pass only distinguished 圖 from 十翼 and mislabelled
    the third: KR1a0031 @26628 was called 十翼 but reads
    `䷷艮下坎上蹇利西南不利東北利見大人貞吉蹇難也…` — that is the main commentary on 蹇卦,
    dropped by the LIS chain because its symbol repeats or sits out of order. Same for
    KR1a0006's 井卦 @42997 and 小過 @55179. Only text like
    `䷍大有之類是也卦體不由乎一爻則全以二體之義明之` is genuinely 十翼-style prose.

    Discriminator for 正文 is exact, not statistical: a main-body 卦 opens
    `symbol + (下卦下 上卦上)`, so a trigram composition note immediately after the symbol
    marks recoverable commentary rather than a citation.

    Discriminator for 圖 is symbol DENSITY, not gap size alone: in KR1a0031/0032, 124 of
    125 off-chain symbols sit in the first decile, 113 within 12 characters of the next
    symbol, forming runs like `䷖剝䷇比䷏豫䷎謙䷆師…`. Its caption text
    (`凡三陰三陽之卦各二十皆自泰否而來`) belongs to the same table. KR1a0006/0007 have zero
    such dense entries; theirs cluster in the LAST decile with gaps of 25-2400.

    Off-chain 正文 entries matter because they are addressable 卦 commentary currently
    absent from the index — a coverage loss, not noise.

    Returns {raw_offset: '圖'|'正文'|'十翼'} for off-chain symbols only.
    """
    marks = [(m.start(), gua_number(m.group())) for m in HEX_RE.finditer(raw)]
    if not marks:
        return {}
    spans, _ = gua_spans(raw)
    on_chain = {s.start for s in spans}
    positions = [p for p, _ in marks]
    out: dict[int, str] = {}
    for p, _g in marks:
        if p in on_chain:
            continue
        near = sum(1 for q in positions if p - window <= q <= p + window)
        if near >= dense:
            out[p] = "圖"
            continue
        window_txt = re.sub(r"<pb:[^>]+>|[¶\s　]", "", raw[p:p + 24])
        out[p] = "正文" if _TRIGRAM_NOTE_RE.match(window_txt) else "十翼"
    return out


def detect_mislabelled_yao(text: str, expected: list[str]) -> list[tuple[str, str]]:
    """Find 爻位 labels the EDITION got wrong: one expected label absent while another is
    duplicated (or an impossible label present).

    Measured in KR1a0031 (原本周易本義), which is why its 爻辭 score sits at 93.6% while the
    sibling KR1a0032 reaches 98.4% — three of its 爻 are misprinted, not mis-parsed:

        卦23 剝  六五 absent, 六四 twice   — 貫魚以宮人寵 is printed under 六四
        卦57 巽  九三 absent, 九二 twice   — 頻巽吝 is printed under 九二
        卦61 中孚 九二 absent, 九三 present — but 中孚 is 兌下艮上, its 3rd line is yin,
                                            so 九三 cannot exist in this 卦 at all

    Reporting these as source anomalies is the honest output. Silently attributing the
    text to the printed (wrong) label would corrupt the cross-edition join key, and
    calling it `unknown` discards a real, checkable finding about the edition.

    -> [(expected_label, printed_label_or_'')], empty when the edition is consistent.
    """
    counts = {l: text.count(l) for l in expected}
    missing = [l for l, n in counts.items() if n == 0]
    if not missing:
        return []
    dup = [l for l, n in counts.items() if n > 1]
    out = []
    for want in missing:
        # An impossible label is one whose polarity contradicts this 卦's line.
        i = expected.index(want)
        other = f"{'六' if want[-1] in '九' or want[0] == '九' else '九'}{want[-1]}" \
            if len(want) == 2 else ""
        flipped = ("初" + ("六" if want[1] == "九" else "九")) if want[0] == "初" else \
                  ("上" + ("六" if want[1] == "九" else "九")) if want[0] == "上" else other
        if flipped and flipped in text and flipped not in expected:
            out.append((want, flipped))
        elif dup:
            out.append((want, dup[0] if len(dup) == 1 else ",".join(dup)))
        else:
            out.append((want, ""))
        del i
    return out


def _repair_degenerate(text: str, expected: list[str], found: dict[str, int],
                       min_ratio: float = 0.15, floor: int = 30) -> dict[str, int]:
    """Retry labels whose span collapsed, because a collapsed span means the ordered search
    matched a CROSS-REFERENCE rather than the 爻辭 itself.

    Found by the cross-edition quality gate, not by the scorer: in KR1a0007 five addresses
    had spans of 1, 4, 6, 9 and 26 characters (卦46九二, 卦9初九, 卦9九二, 卦58九五, 卦46初六)
    because 孔穎達 cites the 爻位 in his discussion before quoting it. `validate_alignment`
    counted every one as "located", so coverage never revealed them (D-012).

    The criterion is deliberately NON-CIRCULAR: it compares a span against the median span
    of its own 卦 and never looks at the base text. Selecting positions by "which one best
    matches the 底本 爻辭" would make the accuracy metric confirm itself.

    Only forward retries are allowed, so the ordering guarantee that stops 用九 matching
    across 勿用+九二 still holds.

    *** MEASURED NEGATIVE RESULT — NOT WIRED IN. Kept as the record of an attempt. ***

        span-degenerate-B   5 -> 3     (卦46九二 and 卦9九二 fixed)
        text-damage         1 -> 2     (卦9九二 relocated to text matching nothing: contiguity 0.041)
        爻辭 verified     1824 -> 1823  (KR1a0016 lost one)

    It trades one error class for another and regresses the score, so it fails on its own
    terms. Retiring it here rather than deleting it, because the next attempt should know
    that "retry the next occurrence" is not sufficient: the correct next occurrence is not
    generally the one immediately following, and picking among candidates needs a signal
    that is neither the base text (circular) nor span length (insufficient).
    """
    if len(found) < 3:
        return found
    order = [l for l in expected if l in found]
    pos = [found[l] for l in order]
    spans = [pos[i + 1] - pos[i] for i in range(len(pos) - 1)]
    if not spans:
        return found
    med = sorted(spans)[len(spans) // 2]
    if med <= 0:
        return found
    limit = max(int(med * min_ratio), 1)
    if limit >= floor:
        limit = floor

    for i, label in enumerate(order[:-1]):
        span = found[order[i + 1]] - found[label]
        if span >= limit:
            continue
        # Try the next occurrence of THIS label, but it must stay before the following
        # label's position, otherwise the ordering would be violated.
        nxt = text.find(label, found[label] + len(label))
        ceiling = found[order[i + 1]]
        if nxt == -1 or nxt >= ceiling:
            # Instead move the FOLLOWING label forward: it is the one that matched early.
            fwd = text.find(order[i + 1], ceiling + len(order[i + 1]))
            after = found[order[i + 2]] if i + 2 < len(order) else len(text)
            if fwd != -1 and fwd < after:
                found[order[i + 1]] = fwd
            continue
        found[label] = nxt
    return found


def extract_yao(seg_raw: str, expected: list[str],
                jing: Cleaned | None = None) -> dict[str, tuple[int, int] | None]:
    """Locate each 爻 inside one 卦 span, searching for 爻位 labels in canonical order.

    Ordered search is what makes this safe: each label is sought only after the
    previous one, so 用九 cannot match across 勿用+九二, and a cross-referenced 六二
    inside 乾 is never consulted because 乾's expected list has no 六二.

    Returns {爻位: (start, end) in cleaned-經 coordinates} or None when not found.
    """
    view = jing or clean(seg_raw, keep_notes=False)
    text = view.text
    found: dict[str, int] = {}
    cursor = 0
    for label in expected:
        at = text.find(label, cursor)
        if at == -1:
            continue
        found[label] = at
        cursor = at + len(label)

    # NOT calling _repair_degenerate here: measured, it made things worse. See its docstring.

    result: dict[str, tuple[int, int] | None] = {}
    ordered = [(v, k) for k, v in found.items()]
    ordered.sort()
    for n, (pos, label) in enumerate(ordered):
        end = ordered[n + 1][0] if n + 1 < len(ordered) else len(text)
        result[label] = (pos, end)
    for label in expected:
        result.setdefault(label, None)
    return result

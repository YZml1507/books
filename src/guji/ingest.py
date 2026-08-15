"""Build the searchable index: 30 works -> SQLite + FTS5, with four address schemes.

The point of this module is that retrieval results carry a canonical address, so
"what do 王弼 and 朱熹 each say about 乾九三" is a lookup rather than a similarity search.

Address schemes:
  1. zhouyi: 卦/爻 structure (易類 works)
  2. yilin: 64x64 (本卦, 之卦) matrix — 焦氏易林 (KR3g0029)
  3. booksec: book/section — Herodotus (763 sections across Books I-IV)
  4. NULL: page anchors only — Darwin (14 chapters, 491 page markers)

    CORRECTION. This docstring previously read: "Only the 易類 works have a 卦/爻 structure.
    The 術數 works (六壬大全, 三命通會, 焦氏易林 …) do not, and their units get NULL addresses —
    that is correct, not a gap to be filled."

    The general claim stands for 六壬大全 and 三命通會, but naming 焦氏易林 among them was
    FALSE, and it was a self-fulfilling kind of false: the pipeline only attempted addressing
    for 易類 works, so this book had no addresses, and the absence of addresses was then read
    back as evidence that it has no structure. That is the circular reasoning of L-16, and the
    docstring is the place it was written down. Measured: 64 sections x 64 entries = 4,096,
    matching the book's own 提要 「六十四卦之變共四千九十有六」.
"""
from __future__ import annotations

import bisect
import glob
import json
import os
import re
import sqlite3
from dataclasses import dataclass

from . import booksec, douay, euclid, play, yilin
from .anchors import HEX_RE, classify_offchain, clean, extract_yao, gua_number, gua_spans, yao_names
from .variants import fold, segment_cjk
from .zhouyi import derive_gold, derive_polarity, work_body

PB_RE = re.compile(r"<pb:([^>]+)>")
NOTE_RE = re.compile(r"[（(]([^（()）]*)[）)]")

# 易類 works carry 卦/爻 structure; everything else is addressed only by page anchor.
#
# (title, base_layer, note_layer, attribution). base_layer is what sits OUTSIDE the
# parentheses — in every 易類 commentary that is the 經 being quoted, and the parenthesised
# material is the commentator's own 注. An earlier version labelled both with a single
# per-work layer, so in 王弼/程頤/朱熹 the quoted 經 was tagged 注 like the commentary around
# it; `--layer 經` then reached only KR1a0007 and, worse, merge_units happily fused 經 and
# 注 into one block because they compared equal on (file, layer, 卦, 爻).
ZHOUYI_WORKS = {
    "KR1a0001": ("周易正文", "經", "注", None),
    "KR1a0003": ("周易鄭康成註", "經", "注", "鄭玄"),
    "KR1a0006": ("周易註", "經", "注", "王弼"),
    "KR1a0007": ("周易註疏", "經", "注", "王弼+孔穎達"),
    "KR1a0016": ("伊川易傳", "經", "注", "程頤"),
    "KR1a0030": ("周易古占法", "正文", "注", "程迥"),
    "KR1a0031": ("原本周易本義", "經", "注", "朱熹"),
    "KR1a0032": ("別本周易本義", "經", "注", "朱熹"),
}


_GUA_HEADING_RE = re.compile(r"《([一-鿿]{1,4})第([一二三四五六七八九十]{1,4})》")
_NUMERALS = {c: i for i, c in enumerate("一二三四五六七八九十", 1)}


def _cn_number(s: str) -> int | None:
    """十一 -> 11, 二十 -> 20, 三十七 -> 37. Only needs to cover 1..64."""
    if s in _NUMERALS:
        return _NUMERALS[s]
    if "十" not in s:
        return None
    tens, _, ones = s.partition("十")
    t = _NUMERALS.get(tens, 1) if tens else 1
    o = _NUMERALS.get(ones, 0) if ones else 0
    return t * 10 + o


def derive_gua_names(base_raw: str) -> dict[int, str]:
    """卦 number -> name, read from KR1a0001's 《X第N》 headings.

    Derived, not typed: the heading states both the name and its King Wen number, so the
    mapping is checkable against the corpus and a transcription slip cannot enter here.
    Cross-checked against the hexagram symbol chain in build(); mismatches are reported.
    """
    out: dict[int, str] = {}
    for m in _GUA_HEADING_RE.finditer(base_raw):
        n = _cn_number(m.group(2))
        if n and 1 <= n <= 64:
            out.setdefault(n, m.group(1))
    return out


def load_work(raw_dir: str, work: str) -> tuple[str, list[tuple[int, str]]]:
    """Concatenated body plus (offset, filename) boundaries, so every unit can name
    the file it came from — a citation that cannot be traced to a file is not a citation.
    """
    parts: list[str] = []
    bounds: list[tuple[int, str]] = []
    at = 0
    for path in sorted(glob.glob(os.path.join(raw_dir, work, "*.txt"))):
        body = re.sub(r"^#.*$", "", open(path, encoding="utf-8").read(), flags=re.M)
        bounds.append((at, os.path.basename(path)))
        parts.append(body)
        at += len(body)
    return "".join(parts), bounds


class AddrIndex:
    """Maps a raw offset to (卦, 爻). Starts are precomputed once; an earlier draft
    rebuilt the key list on every lookup, which is O(n) per unit."""

    def __init__(self, raw: str, polarity: dict[int, tuple[int, ...]], is_zhouyi: bool):
        self.ranges: list[tuple[int, int, int, str | None]] = []
        self.starts: list[int] = []
        self.offchain: dict[int, str] = {}
        self.off_starts: list[int] = []
        self.off_gua: dict[int, int] = {}
        if not is_zhouyi:
            return
        spans, _ = gua_spans(raw)
        for s in spans:
            if s.number not in polarity:
                self.ranges.append((s.start, s.end, s.number, None))
                continue
            seg = raw[s.start:s.end]
            view = clean(seg, keep_notes=False)
            hits = extract_yao(seg, yao_names(polarity[s.number]), jing=view)
            marks = []
            for label, rng in hits.items():
                if not rng:
                    continue
                a = view.origin(rng[0])
                if a < 0:
                    continue
                # NB: do NOT try to re-find the label in the raw text to adjust this
                # offset. 爻位 labels are themselves split by woodblock line breaks —
                # KR1a0006 stores 九二 as 「九¶\n二見龍在田」, so `raw.rfind("九二")` returns
                # -1 there even though the label is present. Only the cleaned view has
                # the label contiguous, which is why the mapping goes through it.
                marks.append((s.start + a, label))
            marks.sort()
            cursor = s.start
            for k, (a, label) in enumerate(marks):
                if a > cursor:
                    self.ranges.append((cursor, a, s.number, None))
                b = marks[k + 1][0] if k + 1 < len(marks) else s.end
                self.ranges.append((a, b, s.number, label))
                cursor = b
            if cursor < s.end:
                self.ranges.append((cursor, s.end, s.number, None))
        self.ranges.sort()
        self.starts = [r[0] for r in self.ranges]

        # Off-chain symbols get their own layer so 卦變圖 entries are queryable as
        # diagram relations and 十翼 citations are not mistaken for 卦 commentary.
        self.offchain = classify_offchain(raw)
        self.off_starts = sorted(self.offchain)
        self.off_gua = {p: gua_number(raw[p]) for p in self.off_starts}

    def offchain_at(self, pos: int, reach: int = 400) -> tuple[str | None, int | None]:
        """-> (layer, 卦) if pos sits just after an off-chain symbol, else (None, None)."""
        if not self.off_starts:
            return None, None
        k = bisect.bisect_right(self.off_starts, pos) - 1
        if k < 0:
            return None, None
        p = self.off_starts[k]
        if pos - p > reach:
            return None, None
        return self.offchain[p], self.off_gua.get(p)

    def lookup(self, pos: int) -> tuple[int | None, str | None]:
        if not self.starts:
            return None, None
        k = bisect.bisect_right(self.starts, pos) - 1
        if k < 0:
            return None, None
        start, end, gua, yao = self.ranges[k]
        return (gua, yao) if start <= pos < end else (None, None)

    def boundaries_within(self, lo: int, hi: int) -> list[int]:
        """Address-change offsets strictly inside (lo, hi).

        A ¶ piece can straddle an address boundary: in KR1a0006 the run
        「…唯二五焉)九三君子終¶日乾乾夕惕若厲无咎」 puts 九三's label mid-piece, so attributing
        the whole piece by its START offset filed 「九三君子終」 under 九二 and left 王弼's
        乾九三 beginning at 「日乾乾」. Splitting at these offsets first fixes where a
        citation begins.
        """
        if not self.starts:
            return []
        i = bisect.bisect_right(self.starts, lo)
        return [s for s in self.starts[i:] if s < hi]


def parse_units(raw: str, bounds: list[tuple[int, str]], addr: AddrIndex,
                base_layer: str, note_layer: str = "注"):
    """Yield (file, raw_start, raw_end, page_anchor, gua, yao, layer, text).

    經 and 注 are emitted as separate units because comparing commentators requires
    filtering by layer, and Kanripo marks 注 with parentheses — machine-readable, so no
    heuristic is needed. Every offset goes through the Piece offset map, so a piece that
    opens with a note (or contains a <pb:> tag) does not shift subsequent offsets.
    """
    file_starts = [b[0] for b in bounds]

    def file_of(pos: int) -> str:
        k = bisect.bisect_right(file_starts, pos) - 1
        return bounds[max(k, 0)][1] if bounds else ""

    for piece in _iter_pieces(raw):
        p_lo, p_hi = piece.offsets[0], piece.offsets[-1] + 1
        # Cut at address boundaries so no fragment is filed under the preceding 爻.
        # The cut index is resolved through the piece's offset map, never by subtracting
        # the piece start from a raw offset — that subtraction was the skew bug.
        cuts = sorted({0, len(piece.text)} | {
            piece.index_of_raw(b) for b in addr.boundaries_within(p_lo, p_hi)})
        for ci in range(len(cuts) - 1):
            a, b = cuts[ci], cuts[ci + 1]
            sub = piece.text[a:b]
            if not sub.strip():
                continue
            sub_raw = piece.raw_at(a)
            gua, yao = addr.lookup(sub_raw)
            off_layer = None
            if gua is None:
                off_layer, off_gua = addr.offchain_at(sub_raw)
                if off_layer:
                    # 圖 entries carry a 卦 identity (which 卦 the row is about) but no 爻;
                    # 十翼 citations get the 卦 they cite. Both are addressable, and both
                    # are distinct from main-body commentary.
                    gua = off_gua
            # Emit base and note runs in POSITIONAL order. Emitting all base text first
            # and notes after put units out of source order, and since base and note used
            # to share one layer they then merged into a block whose text was reordered.
            for r_at, r_text, is_note in _runs(sub):
                txt = r_text.replace("/", "").strip()
                if not txt or not _has_cjk(txt):
                    continue          # 「○」 alone is an editorial separator, not content
                at = piece.raw_at(a + r_at)
                g2, y2 = addr.lookup(at)
                g2 = g2 if g2 is not None else gua
                y2 = y2 if y2 is not None else yao
                layer = note_layer if is_note else (off_layer or base_layer)
                yield (file_of(at), at, piece.raw_at(a + r_at + len(r_text)), anchor_of(piece),
                       g2, y2, layer, txt)


def _has_cjk(s: str) -> bool:
    return any("一" <= c <= "鿿" or ord(c) > 0xFFFF for c in s)


def anchor_of(piece: "Piece") -> str | None:
    return piece.anchor


def _runs(sub: str):
    """Split a fragment into alternating (offset, text, is_note) runs, in order.

    Parenthesis nesting was measured balanced across the corpus (delta 0, max depth 1),
    so a non-nested regex is sufficient here; unmatched openers degrade to base text
    rather than swallowing the remainder.
    """
    at = 0
    for m in NOTE_RE.finditer(sub):
        if m.start() > at:
            yield at, sub[at:m.start()], False
        yield m.start() + 1, m.group(1), True
        at = m.end()
    if at < len(sub):
        yield at, sub[at:], False


@dataclass
class Piece:
    """One ¶-delimited run with an explicit char -> raw-offset map.

    The map is the whole point. The previous version returned the piece's raw START
    offset together with its STRIPPED text, and callers indexed the stripped text with
    raw-derived numbers. Every Kanripo piece begins with a newline (the separator is
    「¶\\n」), so that skew was >= 1 for 100% of pieces (probes/probe_skew.py: 6233/6233,
    9478/9478, …) and up to 14 where a <pb:> tag sits inside the piece. Consequences,
    both measured, not theoretical:

      * 2,634 address-boundary cuts landed one or more chars too far right, so 0 of 1,872
        爻-addressed units began with their own 爻位 label — 1,850 began at its second
        character (「三君子終日…」 for 九三).
      * the leaked first char was carried into the PRECEDING unit, after that unit's note
        text, producing quotations absent from the source: KR1a0032 乾九三 was indexed as
        「…有能乾○九乾惕厲之象…」 where the source reads 「…有能乾乾惕厲之象…」.

    D-008 recorded symptom 1 as cosmetic and ruled out re-finding labels in the raw text.
    Ruling that out was right; concluding it was cosmetic was not. Carrying offsets fixes
    both symptoms without ever searching the raw text.
    """
    text: str
    offsets: list[int]        # offsets[i] = raw offset of text[i]
    anchor: str | None

    def index_of_raw(self, raw_pos: int) -> int:
        """First text index at or after raw_pos (bisect over a sorted list)."""
        return bisect.bisect_left(self.offsets, raw_pos)

    def raw_at(self, i: int) -> int:
        if i < len(self.offsets):
            return self.offsets[i]
        return self.offsets[-1] + 1 if self.offsets else 0


_SKIP_EDGE = " \t\r\n　"


def _iter_pieces(raw: str):
    """Walk the body in ¶-delimited pieces, tracking the page anchor and the raw offset
    of every retained character."""
    anchor = None
    pos = 0
    for piece in raw.split("¶"):
        start = pos
        pos += len(piece) + 1
        for m in PB_RE.finditer(piece):
            anchor = m.group(1)
        spans = []          # (text_char, raw_offset), pb tags removed
        i, n = 0, len(piece)
        while i < n:
            if piece.startswith("<pb:", i):
                j = piece.find(">", i)
                i = n if j == -1 else j + 1
                continue
            spans.append((piece[i], start + i))
            i += 1
        lo, hi = 0, len(spans)
        while lo < hi and spans[lo][0] in _SKIP_EDGE:
            lo += 1
        while hi > lo and spans[hi - 1][0] in _SKIP_EDGE:
            hi -= 1
        if hi > lo:
            kept = spans[lo:hi]
            yield Piece("".join(c for c, _ in kept), [o for _, o in kept], anchor)


def merge_units(units: list[tuple], raw: str, max_chars: int = 900,
                max_gap: int = 400) -> list[tuple]:
    """Join consecutive units sharing (file, layer, 卦, 爻) into one coherent block.

    Necessary because ¶ marks a woodblock LINE break, which lands mid-phrase: splitting
    on it alone yielded 王弼's 乾九三 as 「日乾乾夕惕若厲无咎」 (missing 君子終) and 朱熹's as
    the single character 「咎」. The address was right; the text was shredded. A citation
    has to quote a readable passage, so merge until the address changes.

    max_chars caps runaway merges (one 卦 of 疏 can exceed 80k chars) so a hit stays
    quotable; the page anchor kept is the FIRST one, which is where the passage begins.

    Merging is per-KEY, not strictly consecutive, because 經 and 注 now interleave: a
    woodblock line is 「經 (注) 經 (注)」, so the halves of one 爻辭 are separated by the note
    that sits between them. Consecutive-only merging left 經 shredded into fragments.

    max_gap bounds it: a block absorbs the next same-key run only if that run begins
    within max_gap raw chars of where the block currently ends. Without the bound, two
    passages thousands of chars apart could fuse into a single unit whose raw_start..
    raw_end no longer describes contiguous source — a citation that cannot be checked.

    Emits a 9th field, `skipped`: how many CONTENT characters fall inside the block's range
    without being part of its text (X-10, schema.sql `skipped_chars`). Accumulated here
    because this is the only place the information exists — deriving it later needs a second
    pass over the raw body.

    "Content" is the operative word, and counting raw offsets instead got it wrong: the raw
    gap between two consecutive runs is usually just the woodblock separator 「¶\\n」 or a
    stretch of punctuation, which no reader would call omitted material. Charging those to
    skipped_chars flagged 89.1% of units as non-contiguous when the measured figure is 54.1%
    (probes/probe_disclosure.py) — a disclosure that cries wolf on 35% of the corpus teaches
    readers to ignore it. So the gap is normalised through clean() first, exactly as the
    verification in verify_index.py T9 does, and only surviving characters are counted.
    `raw` is a required parameter for that reason: the count cannot be computed from offsets
    alone, and an optional one would let a caller silently get the wrong meaning.
    """
    open_blocks: dict[tuple, int] = {}       # key -> index into out
    out: list[tuple] = []
    for rec in units:
        f, a, b, anchor, gua, yao, layer, text = rec
        key = (f, layer, gua, yao)
        k = open_blocks.get(key)
        if k is not None:
            pf, pa, pb, panchor, pgua, pyao, player, ptext, pskip = out[k]
            if len(ptext) + len(text) <= max_chars and a - pb <= max_gap:
                gap = len(clean(raw[pb:a], keep_notes=True).text) if a > pb else 0
                out[k] = (pf, pa, b, panchor, pgua, pyao, player, ptext + text,
                          pskip + gap)
                continue
        open_blocks[key] = len(out)
        out.append((*rec, 0))
    out.sort(key=lambda r: r[1])      # blocks stay open, so restore raw order
    return out


def _ingest_yilin(db, work: str, raw: str, bounds: list[tuple[int, str]],
                  gua_names: dict[int, str], uid: int, stats) -> tuple[int, int]:
    """Index 焦氏易林 as 4,096 (本卦, 之卦) cells, then link the printed cross-references.

    Asserts 64 sections x 64 entries before writing anything. That single assertion is the
    guard against the failure that produced two rounds of fabricated numbers for this book: a
    missing name alias silently yields 63 sections and a plausible-looking 4,031 cells.
    """
    names = yilin.name_table(gua_names)
    names_by_num = dict(gua_names)          # 卦 number -> canonical 卦名, for addr_name
    p = yilin.parse_cells(raw, names)
    cells = p.cells
    n_sections = len({c.ben for c in cells})
    if n_sections != 64 or len(cells) != 4096:
        raise AssertionError(
            f"{work}: expected 64 sections x 64 entries = 4096, got {n_sections} sections / "
            f"{len(cells)} cells. A missing 卦名 alias produces exactly this, silently — "
            f"unclassified lines: {[t[:20] for _, t in p.other[:6]]}")

    if p.anomalies:
        print(f"[{work}] SOURCE ANOMALIES (edition defects, not parser errors):")
        for a in p.anomalies:
            print(f"  {a}")

    file_starts = [b[0] for b in bounds]

    def file_of(pos: int) -> str:
        k = bisect.bisect_right(file_starts, pos) - 1
        return bounds[max(k, 0)][1] if bounds else ""

    anchors = [(m.start(), m.group(1)) for m in PB_RE.finditer(raw)]
    a_starts = [a for a, _ in anchors]

    def anchor_of_pos(pos: int) -> str | None:
        k = bisect.bisect_right(a_starts, pos) - 1
        return anchors[k][1] if k >= 0 else None

    rows, fts = [], []
    index: dict[tuple[int, str], int] = {}
    for c in cells:
        uid += 1
        # First occurrence wins: the 艮 section prints 小過 twice (a real edition defect), so
        # the second cell keeps its own address but is not the link target for it.
        index.setdefault((c.ben, c.zhi), uid)
        # addr_name and addr2 are CANONICAL 卦名 from the 底本, not this edition's spelling.
        # The address is a cross-work JOIN KEY: if 焦氏易林 stores 「坎」 while the 周易 works
        # store 「習坎」, a query joining the two works on the name silently returns nothing.
        # Measured before fixing (probes/probe_yilin_name.py): 卦29 carried addr_name='坎' on
        # its 4,096-cell layer and '習坎' on its section heading — one hexagram, two labels,
        # depending on which row you looked at. The edition's own spelling is not lost; it is
        # still there in the unit's text, which is where an edition's orthography belongs.
        ben_label = names_by_num.get(c.ben, c.ben_name)
        zhi_label = names_by_num.get(c.zhi_num, c.zhi) if c.zhi_num else c.zhi
        rows.append((uid, work, file_of(c.start), c.start, c.end,
                     anchor_of_pos(c.start), "yilin", ben_label, c.ben, zhi_label,
                     "林辭", c.text, 0, None))
        fts.append((uid, segment_cjk(fold(c.text))))
        stats.units += 1
        stats.addressed += 1
        stats.yao_addressed += 1
        if anchor_of_pos(c.start):
            stats.anchored += 1
        # Each 注 becomes its own unit at the same address, exactly as 經/注 are separated in
        # the 易類 works. Folding them into the 林辭 text would put editorial matter inside a
        # quotation of the 林辭; dropping them would delete real content and break text
        # conservation. Both were rejected for those reasons.
        for n_off, n_text in c.notes:
            body = n_text.replace("/", "").strip()
            if not body or not _has_cjk(body):
                continue
            uid += 1
            rows.append((uid, work, file_of(n_off), n_off, n_off + len(n_text),
                         anchor_of_pos(n_off), "yilin", ben_label, c.ben, zhi_label,
                         "注", body, 0, None))
            fts.append((uid, segment_cjk(fold(body))))
            stats.units += 1
            stats.addressed += 1
            stats.yao_addressed += 1
            if anchor_of_pos(n_off):
                stats.anchored += 1
    # Section headings and front matter are units too. Not indexing them would delete real
    # text from a work that is supposed to be fully conserved (probe_conservation.py), and
    # 提要/原序 are exactly where the book states its own 4,096-cell structure.
    for off, line, ben_n in p.headings:
        body = line.replace("　", "").strip()
        if not body:
            continue
        uid += 1
        rows.append((uid, work, file_of(off), off, off + len(line), anchor_of_pos(off),
                     "yilin", names_by_num.get(ben_n), ben_n, None, "標題", body, 0, None))
        fts.append((uid, segment_cjk(fold(body))))
        stats.units += 1
        stats.addressed += 1
        if anchor_of_pos(off):
            stats.anchored += 1
    for off, line in p.other:
        body = line.replace("　", "").strip()
        if not body or not _has_cjk(body):
            continue
        uid += 1
        # No address: 提要/原序 are about the whole book, not about one cell. NULL stays a
        # first-class value rather than being attributed to whichever section is nearby.
        rows.append((uid, work, file_of(off), off, off + len(line), anchor_of_pos(off),
                     None, None, None, None, "正文", body, 0, None))
        fts.append((uid, segment_cjk(fold(body))))
        stats.units += 1
        if anchor_of_pos(off):
            stats.anchored += 1

    db.executemany("INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)", fts)

    links = []
    for cell, ben, zhi in yilin.cross_references(cells, names):
        src = index.get((cell.ben, cell.zhi))
        dst = index.get((ben, zhi))
        if src and dst and src != dst:
            links.append(("cross-reference", src, dst, f"{ben}之{zhi}"))
    db.executemany("INSERT INTO link (kind, src_unit, dst_unit, note) VALUES (?,?,?,?)",
                   links)
    return uid, len(cells)


@dataclass
class BuildStats:
    works: int
    units: int
    addressed: int      # units with a 卦
    yao_addressed: int  # units with a 卦 AND a 爻
    anchored: int       # units with a page anchor


def load_suspect(report_path: str) -> tuple[dict[tuple[str, int, str], str], dict]:
    """(work, 卦, 爻) -> quality verdict, read from data/catalog/quality_report.json.

    Read from the gate's own output rather than recomputed here, for two reasons: the
    detection needs an independent WITNESS edition (D-012) which only that gate assembles,
    and recomputing it would double build time on every rebuild of a corpus whose whole
    point is that a rebuild is cheap.

    The cost of that choice is staleness: a report from an older corpus would flag the wrong
    addresses. So the file's mtime and size are returned and written into build_meta, making
    staleness detectable instead of invisible — the same reason build_meta exists at all.
    Absent report -> no flags, and the build says so rather than failing.
    """
    if not os.path.exists(report_path):
        return {}, {"suspect_source": "MISSING — no flags applied"}
    st = os.stat(report_path)
    data = json.load(open(report_path, encoding="utf-8"))
    out: dict[tuple[str, int, str], str] = {}
    for pair, d in data.items():
        work_a = pair.split("|")[0]
        for low in d.get("low", []):
            out[(work_a, low["gua"], low["yao"])] = low["verdict"]
    import time as _t
    return out, {
        "suspect_source": os.path.basename(report_path),
        "suspect_mtime": _t.strftime("%Y-%m-%dT%H:%M:%S", _t.localtime(st.st_mtime)),
        "suspect_bytes": str(st.st_size),
        "suspect_addresses": str(len(out)),
    }


def build(db_path: str, raw_dir: str, manifest_path: str,
          gua_names: dict[int, str] | None = None,
          quality_report: str | None = None,
          ext_dir: str | None = None) -> BuildStats:
    """Create the index from scratch. Rebuilt rather than migrated: the corpus is 4.1M
    chars and a full build is seconds, so a stale-index bug is not worth risking.

    ext_dir: optional path to data/raw_ext/generality/ for booksec-addressed works
    (Herodotus, Darwin). If provided, those works are indexed using booksec.py.
    """
    if os.path.exists(db_path):
        os.remove(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    here = os.path.dirname(os.path.abspath(__file__))
    db.executescript(open(os.path.join(here, "schema.sql"), encoding="utf-8").read())

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    meta = {w["id"]: w for w in manifest.get("works", [])}

    if quality_report is None:
        quality_report = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(db_path)))), "catalog", "quality_report.json")
    suspect, suspect_meta = load_suspect(quality_report)

    # 卦 polarity and names are derived from the corpus, never hardcoded (D-006).
    zy_bodies = {w: work_body(raw_dir, w) for w in ZHOUYI_WORKS if
                 os.path.isdir(os.path.join(raw_dir, w))}
    polarity = derive_polarity(zy_bodies)
    # 卦 names: read out of KR1a0001's 《X第N》 headings (64 present, verified), not
    # hardcoded. The previous build wrote "" for every unit, leaving the column dead.
    names = gua_names or derive_gua_names(zy_bodies.get("KR1a0001", ""))

    works = sorted(d for d in os.listdir(raw_dir)
                   if os.path.isdir(os.path.join(raw_dir, d)))
    uid = 0
    stats = BuildStats(0, 0, 0, 0, 0)
    for w in works:
        raw, bounds = load_work(raw_dir, w)
        if not raw:
            continue
        m = meta.get(w, {})
        zy = ZHOUYI_WORKS.get(w)
        db.execute(
            "INSERT INTO work VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (w, m.get("title") or (zy[0] if zy else w), m.get("genre") or
             ("易類" if zy else None), m.get("edition"), zy[3] if zy else None,
             m.get("n_files"), m.get("n_chars"), m.get("source_url"),
             m.get("zip_sha256"),
             "none-stated" if m.get("licence_file_in_repo") is False else None,
             m.get("fetched_at")))
        # 焦氏易林 has its own scheme: a 64x64 matrix addressed (本卦, 之卦). Handled on a
        # separate path because its units are not ¶-pieces merged by address — each matrix
        # cell IS a unit, delimited by line-head position (see yilin.py).
        if w == yilin.WORK_ID:
            uid, n_cells = _ingest_yilin(db, w, raw, bounds, names, uid, stats)
            stats.works += 1
            yilin_cells = n_cells
            continue

        addr = AddrIndex(raw, polarity, w in ZHOUYI_WORKS)
        base_layer, note_layer = (zy[1], zy[2]) if zy else ("正文", "注")
        rows, fts = [], []
        scheme = "zhouyi" if zy else None
        for rec in merge_units(list(parse_units(raw, bounds, addr,
                                                base_layer, note_layer)), raw):
            uid += 1
            f, a, b, anch, gua, yao, lay, text, skipped = rec
            rows.append((uid, w, f, a, b, anch,
                         scheme if gua else None,
                         names.get(gua) if gua else None, gua, yao, lay, text,
                         skipped, suspect.get((w, gua, yao))))
            # &KR0658; is Kanripo's entity ref for 虩 (U+8679), used only by KR1a0006.
            # clean() never sees unit text (parse_units works on raw slices), so the
            # decode must happen here on the FTS feed. unit.text stays faithful to the
            # raw entity, keeping probe_conservation's CJK multiset unchanged.
            fts.append((uid, segment_cjk(fold(text.replace("&KR0658;", "虩")))))
            stats.units += 1
            if gua:
                stats.addressed += 1
                if yao:
                    stats.yao_addressed += 1
            if anch:
                stats.anchored += 1
        db.executemany("INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)", fts)
        stats.works += 1

    import time
    db.executemany("INSERT INTO build_meta VALUES (?,?)", [
        ("built_at", time.strftime("%Y-%m-%dT%H:%M:%S%z")),
        ("works", str(stats.works)), ("units", str(stats.units)),
        ("fold_pairs", str(len(fold.__globals__["FOLD"]))),
        *sorted(suspect_meta.items()),
    ])

    # Index booksec-addressed works from ext_dir (Herodotus, Darwin).
    if ext_dir and os.path.isdir(ext_dir):
        ext_manifest_path = os.path.join(os.path.dirname(manifest_path),
                                          "generality_manifest.json")
        if os.path.exists(ext_manifest_path):
            ext_manifest = json.load(open(ext_manifest_path, encoding="utf-8"))
            ext_meta = {e["slug"]: e for e in ext_manifest if isinstance(e, dict)}
        else:
            ext_meta = {}

        for slug in sorted(os.listdir(ext_dir)):
            slug_dir = os.path.join(ext_dir, slug)
            if not os.path.isdir(slug_dir):
                continue

            # Euclid ships only as .html/.epub (no .txt), so handle it before
            # the .txt precondition that would otherwise `continue` past it.
            if slug == "euclid-elements":
                html_files = [f for f in os.listdir(slug_dir) if f.endswith(".html")]
                if not html_files:
                    continue
                html_path = os.path.join(slug_dir, html_files[0])
                html = open(html_path, encoding="utf-8").read()
                props = euclid.parse_propositions(html)
                for prop in props:
                    uid += 1
                    db.execute(
                        "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, slug, os.path.basename(html_path), prop.start, prop.end, None,
                         "euclid", f"Book {prop.book}", prop.book, prop.roman, "正文", prop.text, 0, None))
                    db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                              (uid, segment_cjk(fold(prop.text))))
                stats.units += len(props)
                stats.addressed += len(props)
                m = ext_meta.get(slug, {})
                db.execute(
                    "INSERT INTO work VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (slug, m.get("title", slug), m.get("genre"), m.get("edition"), None,
                     len(html_files), len(html), m.get("source_url"),
                     m.get("file_sha256", {}).get(html_files[0]),
                     m.get("licence"), m.get("fetched_at")))
                stats.works += 1
                continue

            txt_files = [f for f in os.listdir(slug_dir) if f.endswith(".txt")]
            if not txt_files:
                continue
            txt_path = os.path.join(slug_dir, txt_files[0])
            raw = open(txt_path, encoding="utf-8").read()
            m = ext_meta.get(slug, {})

            # Determine scheme per slug.
            # - herodotus: booksec (book/section, 763 sections across Books I-IV)
            # - plato-republic: booksec BOOK-only (10 books, no sections — no Stephanus
            #   pagination in this Jowett text, measured: 0)
            # - homer-iliad-but / homer-iliad-pope: booksec BOOK-only (24 books each,
            #   no line numbers in either translation, measured: 0 right-margin numbers)
            # - shakespeare: play scheme (44 works = 38 plays + 6 poems)
            # - euclid-elements: euclid scheme (6 books, 170 propositions)
            # - darwin-origin: page anchors only (14 chapters, 491 page markers)
            scheme = None
            if slug == "herodotus":
                scheme = "booksec"
                sections = booksec.parse_sections(raw)
                for sec in sections:
                    uid += 1
                    db.execute(
                        "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, slug, txt_files[0], sec.start, sec.end, None,
                         "booksec", None, sec.book, sec.number, "正文", sec.text, 0, None))
                    db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                              (uid, segment_cjk(fold(sec.text))))
                stats.units += len(sections)
                stats.addressed += len(sections)
            elif slug in ("plato-republic", "homer-iliad-but", "homer-iliad-pope"):
                scheme = "booksec"
                spans = booksec.book_spans(raw)
                for sp in spans:
                    uid += 1
                    text = raw[sp.start:sp.text_end].strip()
                    db.execute(
                        "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, slug, txt_files[0], sp.start, sp.text_end, None,
                         "booksec", None, sp.number, None, "正文", text, 0, None))
                    db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                              (uid, segment_cjk(fold(text))))
                stats.units += len(spans)
                stats.addressed += len(spans)
            elif slug == "shakespeare":
                scheme = "play"
                plays = play.find_plays(raw)
                for p in plays:
                    if p.is_poem or not p.acts:
                        uid += 1
                        text = raw[p.start:p.end].strip()
                        db.execute(
                            "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (uid, slug, txt_files[0], p.start, p.end, None,
                             "play", p.title, p.ordinal, None, "正文", text, 0, None))
                        db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                                  (uid, segment_cjk(fold(text))))
                        stats.units += 1
                        stats.addressed += 1
                    else:
                        for act in p.acts:
                            for scene in act["scenes"]:
                                uid += 1
                                s_start = p.start + scene["start"]
                                s_end = p.start + scene["end"]
                                text = raw[s_start:s_end].strip()
                                addr2 = f"ACT {act['roman']} SCENE {scene['roman']}"
                                db.execute(
                                    "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                                    (uid, slug, txt_files[0], s_start, s_end, None,
                                     "play", p.title, p.ordinal, addr2, "正文", text, 0, None))
                                db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                                          (uid, segment_cjk(fold(text))))
                                stats.units += 1
                                stats.addressed += 1
            elif slug == "bible-douay":
                scheme = "bcv"
                verses = douay.parse_verses(raw)
                for v in verses:
                    uid += 1
                    db.execute(
                        "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (uid, slug, txt_files[0], v.raw_start, v.raw_end, None,
                         "bcv", v.bcv_book, v.chapter, str(v.verse), "正文",
                         v.text, 0, None))
                    db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                              (uid, segment_cjk(fold(v.text))))
                stats.units += len(verses)
                stats.addressed += len(verses)
            else:
                # Darwin and others: page anchors only, no canonical address
                # Split on page breaks or chapters as units
                pb_marks = list(re.finditer(r"\[Pg \d+\]|\[Page \d+\]", raw))
                if pb_marks:
                    for i, m in enumerate(pb_marks):
                        uid += 1
                        start = m.start()
                        end = pb_marks[i + 1].start() if i + 1 < len(pb_marks) else len(raw)
                        text = raw[start:end].strip()
                        if not text:
                            continue
                        db.execute(
                            "INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (uid, slug, txt_files[0], start, end, m.group(),
                             None, None, None, None, "正文", text, 0, None))
                        db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)",
                                  (uid, segment_cjk(fold(text))))
                        stats.units += 1
                        stats.anchored += 1

            # Insert work record
            db.execute(
                "INSERT INTO work VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (slug, m.get("title", slug), m.get("genre"), m.get("edition"), None,
                 len(txt_files), len(raw), m.get("source_url"),
                 m.get("file_sha256", {}).get(txt_files[0]),
                 m.get("licence"), m.get("fetched_at")))
            stats.works += 1

    db.commit()
    db.close()
    return stats

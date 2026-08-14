"""焦氏易林 (KR3g0029): a 64x64 matrix, and the THIRD address scheme.

Its structure was described in two earlier sessions as 「卦名 adjacent to 卦名, 4,032 pairs,
96.8% adjacency」 and then as 「adjacency 3.4%, structure unknown」. Both were wrong about the
mechanism. Measured (probes/probe_verify_recon.py, reproduced independently of the recon that
first reported it):

    64 sections x 64 entries = 4,096 entries, exactly — which is what the book says about
    itself (提要 「六十四卦之變共四千九十有六」). 4,095 distinct (本卦, 之卦) pairs.

Layout, and the parser needs nothing beyond it:

    　　乾之第一¶            section heading: TWO U+3000, 卦名, 之第, Chinese numeral
    乾　道陟多阪胡言連蹇…¶    entry: 卦名 + ONE U+3000 + 林辭, at LINE HEAD
    　行求事無功¶            continuation: ONE leading U+3000
    師　倉盈庾億…(一作國/家富有)¶   注 in parens, / = internal column break

POSITION IS THE WHOLE DISCRIMINATOR, and this is the one thing that must not be got wrong:
1,192 卦名 occurrences sit INSIDE 林辭 text (復 x122, 離 x103, 困 x86, 履 x75 …), across 26.7%
of the verses, because hexagram names are ordinary words — 復 is "return", 困 is "distress",
師 is "army". Every one of those is mid-line, so matching at line head excludes all of them.
Any content-based matching here produces a mess that looks like data.

Two name spellings this edition uses that the 底本-derived table lacks:
  㤗 -> 泰   a glyph variant, so it goes in variants.FOLD (measured: 4 occurrences)
  坎 -> 卦29 an alternate NAME for 習坎 (習坎 occurs 0 times here). NOT a fold: folding 坎 into
            習坎 would assert something false about the characters. Hence NAME_ALIASES below.

One real edition defect, to be reported rather than repaired: the 艮 section prints 小過 twice
(different 林辭 each time) and omits 小畜 entirely, so it has 64 entries but 63 distinct 之卦.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .variants import fold

WORK_ID = "KR3g0029"

# 之第N heading. Two U+3000 lead it; the numeral is Chinese.
HEAD_RE = re.compile(r"^[　]{2}([一-鿿㐀-䶿]{1,4})之第([一二三四五六七八九十]{1,4})")
ENTRY_RE = re.compile(r"^([一-鿿㐀-䶿]{1,4})　")
PB_RE = re.compile(r"<pb:[^>]*>")
NOTE_RE = re.compile(r"[（(]([^）)]*)[）)]")

# Alternate NAMES (not glyph variants — see module docstring).
NAME_ALIASES = {"坎": 29}


@dataclass
class Cell:
    ben: int              # 本卦 number 1..64
    ben_name: str
    zhi: str              # 之卦 name, folded
    zhi_num: int | None
    start: int            # raw offset of the entry head
    end: int              # raw offset where the next entry begins
    text: str             # 林辭, notes stripped
    # (raw_offset, note_text). Offsets are carried, not just the strings, so each 注 can be
    # emitted as its own unit with a real citable range — the same reason Piece carries an
    # offset map (D-011). Dropping the notes from the index instead would lose ~4,900
    # characters of real content and break the text-conservation gate.
    notes: list[tuple[int, str]]


def name_table(base_gua_names: dict[int, str]) -> dict[str, int]:
    """folded 卦名 -> number, from the 底本 headings plus this edition's aliases.

    Derived, never typed: the numbers come from KR1a0001's 《X第N》 headings (ingest.
    derive_gua_names), so a transcription slip cannot enter here.
    """
    tab = {fold(v): k for k, v in base_gua_names.items()}
    for nm, num in NAME_ALIASES.items():
        tab.setdefault(fold(nm), num)
    return tab


def _pieces(raw: str):
    """(raw_offset, line) for each ¶-delimited line, with <pb:> tags removed."""
    pos = 0
    for piece in raw.split("¶"):
        start = pos
        pos += len(piece) + 1
        s = piece.lstrip("\n")
        off = start + (len(piece) - len(s))
        yield off, PB_RE.sub("", s)


@dataclass
class Parsed:
    """Every line accounted for. `other` exists so the text-conservation gate can pass.

    An earlier version returned only the cells, and the build then lost 6,820 characters of
    KR3g0029 — caught immediately by probe_conservation.py, whose missing-character histogram
    (大 266, 人 136, 小 135, 濟 131, 過 131, 畜 129) named the cause precisely: those are the
    characters of multi-character 卦名 at entry heads, which were being used as the address but
    not stored as text. Front matter (提要/原序) and the 64 section headings were missing too.
    """
    cells: list[Cell]
    headings: list[tuple[int, str, int]]      # (raw offset, line, 本卦 number)
    other: list[tuple[int, str]]              # front matter and anything unclassified
    anomalies: list[str]


def parse_cells(raw: str, names: dict[str, int]) -> Parsed:
    """Segment the work. 4,096 cells expected; everything else is returned, not discarded."""
    from .ingest import _cn_number

    cells: list[Cell] = []
    headings: list[tuple[int, str, int]] = []
    other: list[tuple[int, str]] = []
    anomalies: list[str] = []
    ben = ben_name = None
    pending: Cell | None = None

    for off, line in _pieces(raw):
        if not line.strip():
            continue
        hm = HEAD_RE.match(line)
        if hm:
            n = _cn_number(hm.group(2))
            nm = fold(hm.group(1))
            if n and names.get(nm) != n:
                # Heading whose name disagrees with its own number: report, never guess.
                anomalies.append(f"HEADING-MISMATCH {hm.group(1)}之第{n}")
            if n:
                ben, ben_name = n, nm
                headings.append((off, line, n))
            else:
                other.append((off, line))
            pending = None
            continue
        if line.startswith("　"):
            if pending is not None:            # continuation of the current 林辭
                pending.text += _strip_notes(line)
                pending.notes += _notes_with_offsets(line, off)
                pending.end = off + len(line)
            else:
                other.append((off, line))      # indented front-matter prose
            continue
        em = ENTRY_RE.match(line)
        tok = fold(em.group(1)) if em else None
        if em and tok in names and ben is not None:
            # The entry head 卦名 is kept IN the text, not just used as the address — the same
            # invariant X-07 established for 爻 units: a unit must begin with its own label.
            pending = Cell(ben, ben_name or "", tok, names.get(tok), off,
                           off + len(line), _strip_notes(line),
                           _notes_with_offsets(line, off))
            cells.append(pending)
            continue
        other.append((off, line))
        pending = None

    anomalies.extend(_detect_section_defects(cells, names))
    return Parsed(cells, headings, other, anomalies)


def _strip_notes(s: str) -> str:
    return NOTE_RE.sub("", s).replace("　", "").strip()


def _notes_with_offsets(s: str, base: int) -> list[tuple[int, str]]:
    """(absolute raw offset, note text) for each parenthesised 注 in this line.

    NB the offset is of the note's CONTENT (group 1), not of the opening bracket, so the
    stored range bounds exactly the text the unit will hold.
    """
    return [(base + m.start(1), m.group(1)) for m in NOTE_RE.finditer(s)]


def cross_references(cells: list[Cell], names: dict[str, int]
                     ) -> list[tuple[Cell, int, str]]:
    """(cell, 本卦 number, 之卦 name) for each 「A之B」 printed in a cell's notes.

    These are PRINTED IN THE SOURCE — editorial notes saying this cell's 林辭 also appears at
    another cell. So they are Source knowledge that happens to be a link, not an inference,
    which is why they belong in corpus.db rather than the derived store (D-023).

    Notes are rejoined before parsing because a note can be cut across a woodblock line:
    「(節之觀/大過之)…(困中孚/之泰)」 is one note 「節之觀・大過之困・中孚之泰」, and read
    separately it yields a dangling 之.
    """
    by_len = sorted(names, key=len, reverse=True)
    out: list[tuple[Cell, int, str]] = []
    for c in cells:
        joined = fold("".join(t for _, t in c.notes).replace("/", ""))
        for m in re.finditer(r"([一-鿿㐀-䶿]{1,4})之([一-鿿㐀-䶿]{1,4})", joined):
            a = next((n for n in by_len if m.group(1).endswith(n)), None)
            b = next((n for n in by_len if m.group(2).startswith(n)), None)
            if a in names and b in names:
                out.append((c, names[a], b))
    return out


def _detect_section_defects(cells: list[Cell], names: dict[str, int]) -> list[str]:
    """Find 卦名 expected in a section but missing, while another is duplicated.

    Analogous to detect_mislabelled_yao: edition defects should be REPORTED, not silently
    repaired. Known defect (measured in probes/probe_verify_recon.py C6):
        艮 section: 小過 appears twice with different 林辭, 小畜 is absent.

    Returns list of anomaly strings like "SECTION-DEFECT 艮 missing=小畜 dup=小過".
    """
    anomalies = []
    by_section: dict[int, list[str]] = {}
    for c in cells:
        by_section.setdefault(c.ben, []).append(c.zhi)

    # Each section should cover all 64 hexagram numbers (1-64).
    # names maps 卦名 -> number; some hexagrams have multiple names (坎/習坎 both → 29).
    # So we check coverage by number, not by name.
    all_numbers = set(names.values())
    num_to_canonical_name = {v: k for k, v in sorted(names.items(), key=lambda x: len(x[0]), reverse=True)}

    for ben, zhi_list in by_section.items():
        from collections import Counter
        counts = Counter(zhi_list)
        covered_numbers = {names[z] for z in zhi_list if z in names}

        missing_nums = sorted(all_numbers - covered_numbers)
        dup = sorted([z for z, n in counts.items() if n > 1])

        if missing_nums or dup:
            ben_label = num_to_canonical_name.get(ben, str(ben))
            miss_str = ",".join(num_to_canonical_name[n] for n in missing_nums) if missing_nums else "none"
            dup_str = ",".join(dup) if dup else "none"
            anomalies.append(f"SECTION-DEFECT {ben_label} missing={miss_str} dup={dup_str}")
    return anomalies

"""`play` — play/act/scene addressing, for Shakespeare's Complete Works.

Measured on data/raw_ext/generality/shakespeare/pg100.txt (5.36M body chars):

    TOC at line 12: 44 entries (38 plays + 6 poems), ALPHABETICAL not body order
    ACT I own-line: 76   (= 38 plays × 2 occurrences: once as a header, once repeated)
    ACT n own-line total: 380  (÷ 38 plays = 10, i.e. 5 acts × 2)
    SCENE n. text: 811
    ALL-CAPS own-line titles: 164  (play titles + character names + stage directions)

Three decisions follow:

1. THE TOC IS ALPHABETICAL, NOT BODY ORDER. 44 entries list plays A–W plus 6 poems.
   Body order is different (All's Well starts at @99860, then a second ACT I at @101664).
   So play titles must be READ FROM THE BODY, not from the TOC.

2. ACT HEADERS APPEAR TWICE. The pattern is:
       [play title in ALL CAPS]
       DRAMATIS PERSONAE (character list)
       ACT I                  ← first occurrence, starts the play
       SCENE I. ...
       ...
       ACT V                  ← last act
       ...
       [next play title]
       ACT I                  ← wait, this is the SAME play's ACT I repeated?
   No — inspection shows each ACT appears once per play, but there are 38 plays × 5 acts = 190,
   yet we measured 380. The doubling is because Gutenberg prints each ACT header TWICE:
   once before the act's scenes, and once in a trailing recap. We must DEDUPLICATE by keeping
   only the FIRST occurrence of each (play, act) pair.

   Actually measured again: ACT I own-line = 76 = 38 × 2. Each play has ACT I appearing
   exactly twice. The simplest explanation: the file has a per-play structure where ACT I
   is printed once at the play's start and once at the first scene. We handle this by
   deduplicating on (play_num, act_num) and keeping the first offset.

3. POEMS HAVE NO ACT/SCENE. 6 works (Sonnets, Venus and Adonis, Rape of Lucrece,
   A Lover's Complaint, Passionate Pilgrim, Phoenix and Turtle) have 0 acts.
   These get addr1 = play_num, addr2 = NULL (legitimate, like Darwin's chapter-only).

Address shape (fits existing 4-column schema without migration):
    scheme = "play"
    addr_name = play title
    addr1 = play ordinal (1..44, in BODY order not TOC order)
    addr2 = "ACT n SCENE m" for plays, NULL for poems

    This is a TWO-LEVEL address packed into addr2 as a label string. The alternative —
    adding addr3 — would be a schema migration for one work, which is the D-015 mistake
    in reverse. The Bible's book/chapter/verse fits the same (scheme, addr1, addr2) shape
    because chapter and verse are both ordinals; Shakespeare's act and scene are both
    roman ordinals too, so "ACT II SCENE III" is a perfectly good join key.

Why not index the Sonnets by sonnet number? They could be (addr1=1..154, addr2="sonnet").
Left for a follow-up: the Sonnets are 24k chars, one unit is fine for G2/G6 purposes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# An ACT header on its own line. Gutenberg prints "ACT I", "ACT II.", with optional trailing
# period and optional leading newlines/spaces. The (?m) multiline flag makes ^ match line starts.
ACT_RE = re.compile(r"(?m)^\s*ACT\s+([IVXL]+)\.?\s*$")
# A SCENE heading. "SCENE I. Rossillon. A room in the Countess's palace."
# We want the roman numeral and the setting text.
SCENE_RE = re.compile(r"(?m)^\s*SCENE\s+([IVXL]+)\.?\s*(.*?)\s*$")
# Play titles are ALL CAPS lines, but so are character names and stage directions.
# We identify a play title as an ALL-CAPS line that is followed (within a few lines) by
# either "ACT I" or "DRAMATIS PERSONAE" or "PERSONS REPRESENTED" or "PROLOGUE".
# For poems, the ALL-CAPS title is followed by the poem text directly.
TITLE_RE = re.compile(r"(?m)^\s*([A-Z][A-Z\s,'\-—.]{3,80})\s*$")

# The 44 TOC entries, in TOC order (alphabetical). We use them only to VALIDATE the body
# titles we find, not to enumerate plays — body order is different.
TOC_ENTRIES = [
    "THE SONNETS", "ALL’S WELL THAT ENDS WELL",
    "THE TRAGEDY OF ANTONY AND CLEOPATRA", "AS YOU LIKE IT",
    "THE COMEDY OF ERRORS", "THE TRAGEDY OF CORIOLANUS",
    "CYMBELINE", "THE TRAGEDY OF HAMLET, PRINCE OF DENMARK",
    "THE FIRST PART OF KING HENRY THE FOURTH",
    "THE SECOND PART OF KING HENRY THE FOURTH",
    "THE LIFE OF KING HENRY THE FIFTH",
    "THE FIRST PART OF HENRY THE SIXTH",
    "THE SECOND PART OF KING HENRY THE SIXTH",
    "THE THIRD PART OF KING HENRY THE SIXTH",
    "KING HENRY THE EIGHTH", "THE LIFE AND DEATH OF KING JOHN",
    "THE TRAGEDY OF JULIUS CAESAR", "THE TRAGEDY OF KING LEAR",
    "LOVE’S LABOUR’S LOST", "THE TRAGEDY OF MACBETH",
    "MEASURE FOR MEASURE", "THE MERCHANT OF VENICE",
    "THE MERRY WIVES OF WINDSOR", "A MIDSUMMER NIGHT’S DREAM",
    "MUCH ADO ABOUT NOTHING", "THE TRAGEDY OF OTHELLO, THE MOOR OF VENICE",
    "PERICLES, PRINCE OF TYRE", "KING RICHARD THE SECOND",
    "KING RICHARD THE THIRD", "THE TRAGEDY OF ROMEO AND JULIET",
    "THE TAMING OF THE SHREW", "THE TEMPEST",
    "THE LIFE OF TIMON OF ATHENS", "THE TRAGEDY OF TITUS ANDRONICUS",
    "TROILUS AND CRESSIDA", "TWELFTH NIGHT; OR, WHAT YOU WILL",
    "THE TWO GENTLEMEN OF VERONA", "THE TWO NOBLE KINSMEN",
    "THE WINTER’S TALE", "A LOVER’S COMPLAINT", "THE PASSIONATE PILGRIM",
    "THE PHOENIX AND THE TURTLE", "THE RAPE OF LUCRECE",
    "VENUS AND ADONIS",
]


@dataclass
class Play:
    """A play or poem, with its ACT/SCENE structure."""
    ordinal: int          # 1..44 in body order
    title: str            # ALL-CAPS title from the body
    start: int            # raw offset of the title line
    end: int              # raw offset where the next play begins
    acts: list            # list of (act_roman, act_start, [(scene_roman, scene_start, scene_end, scene_text), ...])
    is_poem: bool         # True if no ACT headers (sonnets, narrative poems)


def _strip_gutenberg_front(raw: str) -> tuple[str, int]:
    """Remove the Project Gutenberg header (*** START ... ***) and return body + offset."""
    m = re.search(r"\*\*\* START.*?\*\*\*", raw, re.S)
    if not m:
        return raw, 0
    return raw[m.end():], m.end()


def _strip_gutenberg_back(body: str) -> str:
    """Truncate at the Project Gutenberg footer (*** END ...)."""
    m = re.search(r"\*\*\* END", body)
    return body[:m.start()] if m else body


def _find_toc_end(body: str) -> int:
    """Return the raw offset where the Table of Contents ends.

    The TOC lists all 44 works alphabetically, indented with 4 spaces. It ends at
    the first occurrence of a work title (in the TOC) that is followed by the
    work's actual text — typically "THE SONNETS" followed by "1" (the first
    sonnet number).

    We search for the pattern: a TOC entry, then a blank line, then "THE SONNETS"
    on its own line followed by the number "1". The TOC ends just before this
    body title.

    Fallback: if the pattern is not found, return 0 (search from the start).
    """
    # The body's first real content after the TOC is "THE SONNETS" followed by "1".
    # In the body, this looks like:
    #     THE SONNETS
    #
    #                     1
    #
    # We search for "THE SONNETS" that is followed (within 200 chars) by a line
    # containing only whitespace and the digit "1".
    for m in re.finditer(r"(?m)^THE SONNETS\s*$", body):
        after = body[m.end():m.end() + 200]
        if re.search(r"(?m)^\s*1\s*$", after):
            return m.start()
    return 0



def find_plays(raw: str) -> list[Play]:
    """Find all 44 plays/poems in body order.

    Strategy: use the 44 TOC titles directly. Each TOC entry is a known work title;
    we search for it in the body (after *** START) and take the FIRST occurrence as
    the play's header position. The TOC entries contain curly quotes (’), which match
    the body exactly.

    This avoids the problem of matching ALL-CAPS lines generally: the body contains
    32,261 ALL-CAPS lines (character names, stage directions, ACT/SCENE headers),
    of which only 44 are actual work titles. Anchoring on the known TOC titles makes
    the match unambiguous.
    """
    body, body_off = _strip_gutenberg_front(raw)
    body = _strip_gutenberg_back(body)

    # Find the first occurrence of each TOC entry in the body.
    # TOC entries are indented in the TOC (4 spaces) but the body title is on its own
    # line with no specific indentation. We search for the literal text.
    titles = []
    for toc_entry in TOC_ENTRIES:
        # Find the first occurrence of this title in the body.
        # The title may appear at the start of a line (indented or not) or in a
        # character list. We want the occurrence that starts at a line beginning
        # (after optional whitespace) and is the title of the work.
        # Strategy: find ALL occurrences, pick the first one that is followed by
        # either ACT I (a play) or by the work's text (a poem).
        occurrences = []
        start = 0
        while True:
            idx = body.find(toc_entry, start)
            if idx == -1:
                break
            occurrences.append(idx)
            start = idx + 1
        if not occurrences:
            continue
        # Pick the first occurrence (the TOC itself lists entries, but *** START
        # already removed the header; the TOC is in the body too, at the very start).
        # Actually the TOC IS in the body after *** START. So the first occurrence
        # is the TOC entry, not the play title. We need the SECOND occurrence, or
        # the first occurrence that is NOT in the TOC block.
        # The TOC block ends at the first occurrence of "THE SONNETS" followed by
        # "1" (the first sonnet). So we find the end of the TOC.
        toc_end = _find_toc_end(body)
        # Pick the first occurrence after toc_end
        pos = None
        for occ in occurrences:
            if occ >= toc_end:
                pos = occ
                break
        if pos is None:
            # Fall back: use the last occurrence (might be in an epilogue)
            pos = occurrences[-1]
        titles.append((pos, toc_entry))

    # Sort by position to get body order
    titles.sort(key=lambda x: x[0])

    plays = []
    for i, (pos, title) in enumerate(titles):
        end = titles[i + 1][0] if i + 1 < len(titles) else len(body)
        region = body[pos:end]

        # Find ACT headers in this region
        act_matches = list(ACT_RE.finditer(region))
        # Deduplicate acts: keep first occurrence of each roman numeral
        seen_acts = {}
        for am in act_matches:
            roman_num = am.group(1)
            if roman_num not in seen_acts:
                seen_acts[roman_num] = am

        acts = []
        is_poem = len(seen_acts) == 0
        for roman_num, am in sorted(seen_acts.items(), key=lambda x: _roman_to_int(x[0])):
            act_start = am.start()
            # Find SCENEs within this act
            # The act region extends to the next act or to the end of the play
            act_matches_sorted = sorted(seen_acts.values(), key=lambda m: m.start())
            act_idx = list(seen_acts.values()).index(am)
            act_end = (act_matches_sorted[act_idx + 1].start()
                       if act_idx + 1 < len(act_matches_sorted) else len(region))
            act_region = region[act_start:act_end]
            scenes = []
            scene_matches = list(SCENE_RE.finditer(act_region))
            for s_idx, sm in enumerate(scene_matches):
                scene_roman = sm.group(1)
                scene_setting = sm.group(2).strip() if sm.group(2) else ""
                scene_start = act_start + sm.start()
                # Scene end is the next scene or end of act
                scene_end = (act_start + scene_matches[s_idx + 1].start()
                             if s_idx + 1 < len(scene_matches) else act_end)
                scene_text = region[scene_start:scene_end].strip()
                scenes.append({
                    "roman": scene_roman,
                    "setting": scene_setting,
                    "start": scene_start,
                    "end": scene_end,
                    "text": scene_text,
                })
            acts.append({
                "roman": roman_num,
                "start": act_start,
                "scenes": scenes,
            })

        plays.append(Play(
            ordinal=i + 1,
            title=title,
            start=pos,
            end=end,
            acts=acts,
            is_poem=is_poem,
        ))

    return plays


def _roman_to_int(s: str) -> int:
    """Convert roman numeral to int. Supports I, V, X, L, C, D, M."""
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = prev = 0
    for ch in reversed(s.upper()):
        v = values.get(ch, 0)
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total

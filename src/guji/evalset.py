"""Normalisation spaces for the G1 evaluation set — one definition, two consumers.

scripts/derive_eval_g1.py builds gold witnesses out of data/raw/; scripts/eval_g1.py
re-verifies them against data/raw/. If those two scripts each carried their own idea of
"the same text", the bank would drift from its own verifier exactly the way the duplicated
fold table did (module docstring of variants.py: 坤 六五 was simultaneously present and
missing). So the spaces live here and both scripts import them.

THREE spaces are needed, and they are NOT interchangeable. Each of the three was forced by
a measured failure while building the bank:

  folded_notes    fold on, notes kept.  The general comparison space, and the right one
                  for proving a fabricated passage is ABSENT — absence has to be checked
                  over everything the corpus contains, notes included.

  folded_jing     fold on, parenthesised 注 dropped.  The space the 爻辭 gold set is
                  derived in (zhouyi.derive_gold -> clean(keep_notes=False)). A witness cut
                  from that view is NOT generally a substring of folded_notes: where the
                  raw reads 「AB(注)CD」 the 經-only view yields ABCD, which does not occur
                  in the notes-kept view at all. Six version-awareness questions were
                  reported INVALID for exactly this reason before the space was separated.

  unfolded_notes  fold OFF, notes kept.  Required by the fold-unification questions, and
                  the reason is not subtle: fold() maps 黄 -> 黃, so in ANY folded space the
                  variant spelling does not exist. Asking "does 黄 occur in KR1a0006" of a
                  folded body can only ever answer no. Two questions were INVALID from this.

Punctuation: every space drops variants.DROP. KR1a0001 prints 「九三：君子終日乾乾，夕惕若厲。」
and is the only edition that punctuates heavily (9,784 DROP chars over 100% of its units,
against 4 chars in KR1a0006). Comparing a punctuated unit.text against a DROP-stripped file
body scored citation 0/30 — a pure artefact of mixing two spaces, with no index defect
behind it (probes/probe_citation_space.py: 43 units unrecoverable mixed, 0 when both sides
are normalised alike). That is the same shape as L-09, where a single-file offset against a
concatenated-body coordinate system produced a 97.85% "error rate".
"""
from __future__ import annotations

import glob
import os
import re

from .variants import DROP, FOLD

SPACES = {
    "folded_notes": {"fold_chars": True, "keep_notes": True},
    "folded_jing": {"fold_chars": True, "keep_notes": False},
    "unfolded_notes": {"fold_chars": False, "keep_notes": True},
}


def normalize(raw: str, *, fold_chars: bool = True, keep_notes: bool = True) -> str:
    """Strip <pb:> markup, punctuation and layout; optionally drop 注 and fold 異體字.

    Deliberately mirrors anchors.clean() character for character, minus the offset map:
    the parenthesis depth counter is clamped at zero so a malformed source degrades
    instead of swallowing the rest of the file.
    """
    out: list[str] = []
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
            out.append((FOLD.get(ch, ch) if fold_chars else ch))
        i += 1
    return "".join(out)


def in_space(raw: str, space: str) -> str:
    return normalize(raw, **SPACES[space])


def raw_body(raw_dir: str, work: str) -> str:
    """Concatenated work body with Org-mode header lines removed.

    Same coordinate system as zhouyi.work_body and ingest.load_work: offsets are into the
    CONCATENATION, never into one file (L-09).

    Handles both data/raw (Kanripo works in subdirs) and data/raw_ext/generality (pg*.txt files).
    """
    work_dir = os.path.join(raw_dir, work)
    if os.path.isdir(work_dir):
        # Kanripo: multiple .txt files in work/
        return "".join(
            re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
            for p in sorted(glob.glob(os.path.join(work_dir, "*.txt"))))
    else:
        # generality works: look for pg*.txt in raw_dir/../raw_ext/generality/work/
        ext_dir = os.path.join(os.path.dirname(raw_dir), "raw_ext", "generality", work)
        if os.path.isdir(ext_dir):
            matches = glob.glob(os.path.join(ext_dir, "pg*.txt"))
            if matches:
                return open(matches[0], encoding="utf-8").read()
        return ""


_cache: dict[tuple[str, str], str] = {}


def body_in(raw_dir: str, work: str, space: str) -> str:
    """Cached: a full pass over 28 works in three spaces is ~12M chars of work."""
    key = (work, space)
    if key not in _cache:
        _cache[key] = in_space(raw_body(raw_dir, work), space)
    return _cache[key]


def works_on_disk(raw_dir: str) -> list[str]:
    return sorted(w for w in os.listdir(raw_dir)
                  if os.path.isdir(os.path.join(raw_dir, w)))

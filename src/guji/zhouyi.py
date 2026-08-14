"""周易-specific derivations shared by every script that touches this corpus.

Extracted into a module for the same reason variants.FOLD was: the 爻辭 gold set and
the 卦-polarity table were about to be copy-pasted into a second script, and a
duplicated derivation drifts exactly like a duplicated fold table did — one probe
found 坤 六五, the other did not, from the same bytes.

Nothing here is hardcoded from memory. Line polarity comes from the corpus's own
trigram notes; 爻辭 come from KR1a0001. A hand-written gold set was tried first and
was wrong twice (屯 六二 missing 匪寇婚媾, and 屯's 爻位 listed as 六五/上九 when the
hexagram is 震下坎上 and therefore has 九五/上六).
"""
from __future__ import annotations

import glob
import os
import re
from collections import Counter

from .anchors import HEX_RE, clean, extract_yao, gua_number, gua_spans, lines_from_trigrams, yao_names

TRIGRAM_RE = re.compile(r"[（(]([^（()）/]{1,3})下\s*/?\s*([^（()）/]{1,3})上[）)]")

# A 爻辭 in the 正文 layout runs until one of these section openers. 象曰 alone was not
# enough: 乾 用九 then swallowed 彖曰大哉乾元萬物 into the gold text.
GOLD_STOPS = ("象曰", "彖曰", "文言曰", "繫辭", "用九", "用六")

GUA_NAMES = {1: "乾", 2: "坤", 3: "屯"}


def work_body(raw_dir: str, work: str) -> str:
    """Concatenate a work's files with Org-mode header lines removed."""
    return "".join(
        re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
        for p in sorted(glob.glob(os.path.join(raw_dir, work, "*.txt")))
    )


def cut_gold(text: str) -> str:
    """Trim a 爻辭 at the first following section opener."""
    cut = len(text)
    for stop in GOLD_STOPS:
        at = text.find(stop)
        if at != -1:
            cut = min(cut, at)
    return text[:cut]


def derive_polarity(bodies: dict[str, str]) -> dict[int, tuple[int, ...]]:
    """卦 number -> six line polarities, voted from the corpus's trigram notes.

    Majority vote matters: 27 of 64 symbols carry conflicting notes, nearly all of them
    variant spellings of trigram names (兊/兌/兑, 巽/㢲), plus at least one genuine
    source error (卦12 annotated 良下震上, where 良 is not a trigram name at all).
    """
    votes: dict[int, Counter] = {}
    for raw in bodies.values():
        for m in HEX_RE.finditer(raw):
            g = gua_number(m.group())
            t = TRIGRAM_RE.search(raw[m.start():m.start() + 40])
            if not t:
                continue
            lines = lines_from_trigrams(t.group(1), t.group(2))
            if lines:
                votes.setdefault(g, Counter())[lines] += 1
    return {g: c.most_common(1)[0][0] for g, c in votes.items()}


def derive_gold(base_raw: str, polarity: dict[int, tuple[int, ...]]) -> dict[int, dict[str, str]]:
    """卦 number -> {爻位: 爻辭}, read out of the 正文."""
    gold: dict[int, dict[str, str]] = {}
    spans, _ = gua_spans(base_raw)
    for s in spans:
        if s.number not in polarity or s.number in gold:
            continue
        expected = yao_names(polarity[s.number])
        seg = base_raw[s.start:s.end]
        view = clean(seg, keep_notes=False)
        hits = extract_yao(seg, expected, jing=view)
        entry = {}
        for label in expected:
            rng = hits.get(label)
            if not rng:
                continue
            text = cut_gold(view.text[rng[0] + len(label):rng[1]])
            if text:
                entry[label] = text
        if entry:
            gold[s.number] = entry
    return gold

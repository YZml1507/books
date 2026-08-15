"""Derive the G1 evaluation bank from the RAW corpus — never from the index.

G1's criterion is "given a concept, the returned 原文 is right >= 95% of the time".
Making that executable needs a question bank whose gold answers cannot inherit a bug
from the thing under test. Three designs were compared (DECISIONS.md D-019):

  A  hand-written questions        REJECTED. This project's hand-written gold was wrong
                                   twice: 屯 六二 missing 匪寇婚媾, and 屯's 爻位 listed as
                                   六五/上九 when the 卦 is 震下坎上 and has 九五/上六.
  B  derive from the index and     REJECTED. Circular: the index is the system under
     check against the index       test, so a systematic indexing fault gets written
                                   into the gold and the eval passes anyway. That is
                                   exactly X-07 — the index emitted 有能乾○九乾 where the
                                   source reads 有能乾乾, and every count-based check
                                   passed it.
  C  derive from data/raw/ and     CHOSEN. Every gold answer is a string PROVEN to occur
     check against data/raw/       (or proven absent) in a named source file. The index
                                   is only ever the answerer, never the authority.

Output: data/catalog/eval_g1.json. scripts/eval_g1.py re-verifies every gold witness
against data/raw/ before scoring, so a bank that has gone stale reports INVALID rather
than silently passing.

Pre-registered before any result was looked at (§3: 判据必须在看数据之前定下):
TOP_K = 10, and the per-category targets stated in scripts/eval_g1.py.
"""
from __future__ import annotations

import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.anchors import clean, extract_yao, gua_spans, yao_names  # noqa: E402
from guji.evalset import body_in, works_on_disk  # noqa: E402
from guji.variants import FOLD, fold  # noqa: E402
from guji.zhouyi import derive_gold, derive_polarity, work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "catalog", "eval_g1.json")
BASE = "KR1a0001"
WORKS = ("KR1a0001", "KR1a0006", "KR1a0007", "KR1a0016", "KR1a0031", "KR1a0032")
SEED = 11
TOP_K = 10

CAPS = {"retrieval": 40, "retrieval_cross": 24, "retrieval_hard": 24,
        "citation": 30, "grounded_pos": 25, "grounded_neg": 30, "version": 24}

# 55 条概念级（白话转述）题：D-029 沉淀批，不手写新题（GOAL §4 T1 手写错过两次）。
# 查询是转述，不逐字存在于语料——gold 是地址，witness 是该地址的 經 文本（在 raw 里）。
sys.path.insert(0, os.path.join(ROOT, "probes"))
from probe_t7r_concept import PARAPHRASES  # noqa: E402
CAPS["retrieval_concept"] = len(PARAPHRASES)

def shortest_unique(phrase: str, hay: str, lo: int = 4, hi: int = 12) -> str | None:
    """Shortest window of `phrase` occurring exactly once in `hay`.

    Used to turn a 爻辭 into a QUERY that is not the whole answer. Uniqueness is measured
    in the 底本 only — a fragment may of course recur in the commentaries, and whether the
    right address still ranks in the top-K despite that is precisely what is being tested,
    not something to engineer away.
    """
    for size in range(lo, hi + 1):
        if size > len(phrase):
            break
        for i in range(len(phrase) - size + 1):
            w = phrase[i:i + size]
            if hay.count(w) == 1:
                return w
    return None


def transpose_mutant(phrase: str) -> str | None:
    """Swap one adjacent pair near the middle.

    Transposition, not substitution, on purpose: it preserves the character MULTISET, so
    a fabrication check that compares multisets (as probe_conservation.py once did) cannot
    see it. Reordering is the exact defect X-07 produced, so the adversarial case must be
    of that kind to be worth anything.
    """
    m = len(phrase) // 2
    for d in range(0, len(phrase) // 2):
        for i in (m + d, m - d):
            if 0 <= i < len(phrase) - 1 and phrase[i] != phrase[i + 1]:
                return phrase[:i] + phrase[i + 1] + phrase[i] + phrase[i + 2:]
    return None


def main() -> int:
    rnd = random.Random(SEED)
    bodies = {w: work_body(RAW, w) for w in WORKS}
    polarity = derive_polarity(bodies)
    gold = derive_gold(bodies[BASE], polarity)
    base_n = body_in(RAW, BASE, "folded_notes")

    # Per-work address -> raw-derived text, built with the same span/爻 logic the index
    # uses but read straight out of data/raw/. This is the cross-edition witness table.
    per_work: dict[str, dict[tuple[int, str], str]] = {}
    for w in WORKS:
        raw = bodies[w]
        table: dict[tuple[int, str], str] = {}
        spans, _ = gua_spans(raw)
        for s in spans:
            if s.number not in polarity:
                continue
            seg = raw[s.start:s.end]
            view = clean(seg, keep_notes=False)
            hits = extract_yao(seg, yao_names(polarity[s.number]), jing=view)
            for label, rng in hits.items():
                if rng and (s.number, label) not in table:
                    table[(s.number, label)] = view.text[rng[0] + len(label):rng[1]]
        per_work[w] = table

    qs: list[dict] = []
    addresses = sorted((g, y) for g, ys in gold.items() for y in ys)
    rnd.shuffle(addresses)

    # One concatenation of every work, used only to measure how CONTESTED a fragment is.
    # Difficulty selection may consult the corpus freely; what must never come from the
    # index is the GOLD. \x00 separators stop a match straddling two works.
    contested = "\x00".join(body_in(RAW, w, "folded_notes") for w in works_on_disk(RAW))

    def corpus_count(s: str) -> int:
        return contested.count(fold(s))

    def n_of(cat: str) -> int:
        return sum(1 for q in qs if q["category"] == cat)

    # ---- retrieval tier 1: a distinctive fragment must bring back its own address -----
    # The EASY tier, and labelled as such. A verbatim fragment is not what G1 means by
    # 概念; it establishes the floor, not the criterion.
    for g, y in addresses:
        if n_of("retrieval") >= CAPS["retrieval"]:
            break
        text = gold[g][y]
        if len(text) < 6:
            continue
        q = shortest_unique(text, base_n)
        if not q:
            continue
        qs.append({
            "id": f"R-{g:02d}-{y}", "category": "retrieval", "kind": "verbatim",
            "query": q,
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y, "top_k": TOP_K},
            "gold_witness": {"work": BASE, "text": q, "space": "folded_notes",
                             "why": "fragment occurs exactly once in the 底本"},
            "note": f"底本 爻辭 {text[:20]}  corpus occurrences={corpus_count(q)}",
        })

    # ---- retrieval tier 2: the same address in a DIFFERENT witness --------------------
    # Harder for a real reason: the commentaries spell the 爻辭 with 異體字 (濳龍勿用 for
    # 潛龍勿用, 黄 for 黃), split it across woodblock lines, and interleave 注 into it. A hit
    # from KR1a0001 alone would prove only that the 底本 can find itself.
    for g, y in addresses:
        if n_of("retrieval_cross") >= CAPS["retrieval_cross"]:
            break
        text = gold[g][y]
        if len(text) < 6:
            continue
        q = shortest_unique(text, base_n)
        if not q:
            continue
        others = [w for w in WORKS if w != BASE and (g, y) in per_work[w]
                  and fold(q) in fold(per_work[w][(g, y)])]
        if not others:
            continue          # not attested elsewhere in data/raw/; not this test's target
        qs.append({
            "id": f"RX-{g:02d}-{y}", "category": "retrieval_cross", "kind": "cross_work",
            "query": q,
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y, "top_k": TOP_K,
                       "must_include_work_other_than": BASE,
                       "attested_in": others},
            "gold_witness": {"work": others[0], "text": q, "space": "folded_jing",
                             "why": f"the same fragment is attested at 卦{g}{y} in "
                                    f"{others[0]} in data/raw/, so a retrieval that only "
                                    f"reaches the 底本 is incomplete"},
        })

    # ---- retrieval tier 3: ranking under competition ----------------------------------
    # A SHORT fragment (3-4 chars) that identifies exactly one address in the 底本 but
    # occurs many times corpus-wide. This is the tier that can actually fail: it tests
    # whether BM25 surfaces the right address among thousands of units that share the
    # characters, rather than whether the phrase matcher works.
    for g, y in addresses:
        if n_of("retrieval_hard") >= CAPS["retrieval_hard"]:
            break
        text = gold[g][y]
        if len(text) < 6:
            continue
        q = shortest_unique(text, base_n, lo=3, hi=4)
        if not q:
            continue
        n = corpus_count(q)
        if n < 8:
            continue          # not contested enough to be a ranking test
        qs.append({
            "id": f"RH-{g:02d}-{y}", "category": "retrieval_hard", "kind": "competitive",
            "query": q,
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y, "top_k": TOP_K},
            "gold_witness": {"work": BASE, "text": q, "space": "folded_notes",
                             "why": f"unique in the 底本 but occurs {n} times corpus-wide; "
                                    f"the gold address must still rank in the top {TOP_K}"},
            "note": f"corpus occurrences={n}",
        })

    # ---- citation: every hit at a real address must resolve to file + <pb:> ----------
    for g, y in addresses[:CAPS["citation"] * 3]:
        if sum(1 for q in qs if q["category"] == "citation") >= CAPS["citation"]:
            break
        if sum(1 for w in WORKS if (g, y) in per_work[w]) < 2:
            continue
        qs.append({
            "id": f"C-{g:02d}-{y}", "category": "citation",
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y,
                       "min_works": 2, "all_citations_resolve": True},
            "gold_witness": {"work": BASE, "text": gold[g][y][:8],
                             "space": "folded_jing",
                             "why": "address is attested in >=2 works in data/raw/"},
        })

    # ---- groundedness, positive: claimed text really is at that address -------------
    for g, y in addresses:
        if sum(1 for q in qs if q["category"] == "grounded_pos") >= CAPS["grounded_pos"]:
            break
        text = gold[g][y]
        if len(text) < 10:
            continue
        probe = text[:10]
        if base_n.count(probe) != 1:
            continue
        qs.append({
            "id": f"GP-{g:02d}-{y}", "category": "grounded_pos", "query": probe,
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y,
                       "text_present_at_address": True},
            "gold_witness": {"work": BASE, "text": probe, "space": "folded_notes",
                             "why": "10-char head of the 底本 爻辭, unique in the 底本"},
        })

    # ---- groundedness, adversarial: fabrications must return NOTHING ----------------
    # The one non-derived case, and it is a regression test rather than a guess: this
    # exact string was EMITTED by the index before X-07 was fixed (KR1a0032 乾九三 was
    # indexed as 有能乾○九乾惕厲之象 where the source reads 有能乾乾惕厲之象). ○ is dropped by
    # the FTS tokeniser on both sides, so the CJK-only form is what a query can express.
    # Absence is checked over ALL 28 works and in BOTH folded spaces. Both parts matter:
    # a mutant that happens to occur in 三命通會 is not a fabrication, and a mutant absent
    # from the notes-kept view can still occur in the 經-only view (where dropping a 注
    # joins the text on either side of it), in which case a 經-layer unit could legitimately
    # contain it and "0 hits" would be the wrong expectation.
    def absent_everywhere(s: str) -> list[str]:
        f = fold(s)
        return [w for w in works_on_disk(RAW)
                if f in body_in(RAW, w, "folded_notes")
                or f in body_in(RAW, w, "folded_jing")]

    fabrications = [("有能乾九乾", "X-07: index once emitted this; source reads 有能乾乾")]
    for phrase, why in fabrications:
        where = absent_everywhere(phrase)
        qs.append({
            "id": "GN-x07", "category": "grounded_neg", "query": phrase,
            "expect": {"hits": 0},
            "gold_witness": {"work": "*", "text": phrase, "absent": True,
                             "space": "folded_notes+folded_jing",
                             "why": why, "occurs_in": where},
        })

    for g, y in addresses:
        if sum(1 for q in qs if q["category"] == "grounded_neg") >= CAPS["grounded_neg"]:
            break
        text = gold[g][y]
        if len(text) < 8:
            continue
        mut = transpose_mutant(text[:10])
        if not mut:
            continue
        if absent_everywhere(mut):
            continue          # not a fabrication at all; skip rather than mis-score it
        qs.append({
            "id": f"GN-{g:02d}-{y}", "category": "grounded_neg", "query": mut,
            "expect": {"hits": 0},
            "gold_witness": {"work": "*", "text": mut, "absent": True,
                             "space": "folded_notes+folded_jing",
                             "why": "adjacent transposition of a real 爻辭; multiset "
                                    "identical, so only an order-aware check sees it",
                             "occurs_in": []},
        })

    # ---- version awareness, part 1: genuine divergence must stay distinct ------------
    # Only EARLY divergence qualifies. Measured (probes/probe_eval_version.py): of the 377
    # addresses shared by KR1a0031/0032, 248 differ only in that one text is a PREFIX of
    # the other — i.e. they differ in how much commentary follows, not in what the 經
    # reads. Scoring those as "version awareness" would make the test pass automatically
    # and measure nothing. Requiring the first difference inside the first 30 characters
    # puts it in the 爻辭 itself, which is where 校勘 evidence lives: 枯楊生稊/生梯,
    # 跛能履/破能履, 日昃/日昊, 恆/怕, 已日/己日. 47 addresses qualify.
    div = []
    for (g, y), t31 in per_work["KR1a0031"].items():
        t32 = per_work["KR1a0032"].get((g, y))
        if not t32:
            continue
        a, b = fold(t31), fold(t32)
        if len(a) < 6 or len(b) < 6:
            continue
        i = 0
        while i < min(len(a), len(b)) and a[i] == b[i]:
            i += 1
        if i >= min(len(a), len(b)) or i >= 30:
            continue
        # fold() is 1:1 per character (asserted idempotent and non-chaining in
        # probe_eval_version.py), so an index found in the folded text is valid in the
        # unfolded text too. The witness is stored UNFOLDED because that is what has to be
        # string-matchable in data/raw/.
        lo = max(0, i - 5)
        div.append((g, y, t31[lo:i + 6], t32[lo:i + 6], i))
    rnd.shuffle(div)
    for g, y, wa, wb, at in div[:CAPS["version"] // 2]:
        qs.append({
            "id": f"VD-{g:02d}-{y}", "category": "version", "kind": "divergent",
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y,
                       "work_a": "KR1a0031", "work_b": "KR1a0032",
                       "a_contains": wa, "b_contains": wb},
            "gold_witness": {"work": "KR1a0031+KR1a0032", "space": "folded_jing",
                             "text": wa, "text_b": wb, "first_diff_at": at,
                             "why": "the two editions read differently INSIDE the 爻辭 "
                                    "(first difference at char %d); 校勘 evidence that "
                                    "must not be flattened" % at},
        })

    # ---- version awareness, part 2: folded variants must UNIFY -----------------------
    # The mirror obligation of part 1. 稊/梯 must stay two readings (NOT_VARIANTS), while
    # 黄/黃 must become one (FOLD) or a reader typing the familiar form finds nothing.
    pairs = [("𫝊", "傳"), ("説", "說"), ("𤣥", "玄"), ("黄", "黃"),
             ("濳", "潛"), ("於", "于"), ("無", "无"), ("羣", "群")]
    for var, canon in pairs:
        if sum(1 for q in qs if q.get("kind") == "unified") >= CAPS["version"] // 2:
            break
        if FOLD.get(var) != canon:
            continue
        # The context MUST be cut from an UNFOLDED body: fold() maps 黄 -> 黃, so in any
        # folded space the variant spelling does not exist and the witness could never be
        # verified. Two questions were INVALID from getting this wrong.
        found = None
        for w in WORKS:
            un = body_in(RAW, w, "unfolded_notes")
            at = un.find(var)
            if at < 2 or at + 3 > len(un):
                continue
            ctx = un[at - 2:at + 3]
            if len(ctx) < 5 or canon in ctx:
                continue      # canon already adjacent would make the query ambiguous
            found = (w, ctx)
            break
        if not found:
            continue
        w, ctx = found
        qs.append({
            "id": f"VU-{canon}", "category": "version", "kind": "unified",
            "query": ctx.replace(var, canon),
            "expect": {"min_hits": 1, "hit_contains_variant": var},
            "gold_witness": {"work": w, "text": ctx, "space": "unfolded_notes",
                             "variant": var, "canon": canon,
                             "why": f"{var} occurs in {w}; searching the canonical "
                                    f"{canon} must still reach it (fold applied both sides)"},
        })

    # ---- retrieval tier 4: concept / paraphrase (D-029 batch, scored by bge) ----------
    # The query is a 白话转述 that does NOT occur verbatim anywhere in the corpus — that is
    # the entire point of the tier. The gold is the ADDRESS; the witness is the 爻辭 at that
    # address in the 底本, verified in data/raw/ exactly like every other gold (D-019: never
    # the index). Scoring is by the bge encoder (probes/probe_embed_bge.py), not FTS5.
    for i, (query, g, y, why) in enumerate(PARAPHRASES):
        if g not in gold or y not in gold[g]:
            continue
        qs.append({
            "id": f"CP-{i:02d}-{g:02d}-{y}", "category": "retrieval_concept",
            "kind": "paraphrase",
            "query": query,
            "expect": {"scheme": "zhouyi", "addr1": g, "addr2": y, "top_k": TOP_K},
            "gold_witness": {"work": BASE, "text": gold[g][y], "space": "folded_notes",
                             "why": why},
            "note": f"概念转述题（D-029 批）：{why}",
        })

    bank = {
        "derived_by": "scripts/derive_eval_g1.py",
        "derived_from": "data/raw/ only — never the index (D-019)",
        "seed": SEED, "top_k": TOP_K,
        "counts": {k: sum(1 for q in qs if q["category"] == k) for k in CAPS},
        "questions": qs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)

    print(f"gold addresses available: {len(addresses)}")
    print(f"divergent 31/32 addresses: {len(div)}")
    for k, v in bank["counts"].items():
        print(f"  {k:14s} {v}")
    print(f"total {len(qs)} questions -> {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

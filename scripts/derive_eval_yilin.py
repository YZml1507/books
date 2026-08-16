"""Derive G1 questions for 焦氏易林 (yilin scheme) from data/raw/.

The principle is identical to derive_eval_g1.py: gold answers come from data/raw/, never the
index. This module extends the evaluation bank with a SECOND address scheme. Per TASK_LEDGER
P-05: "现在评测集只覆盖周易，第三种体系没有对应的检索/引用题目，等于新增的 5,032 个单元
没有验收。"

Coverage:
  - retrieval (verbatim fragments unique in the work)
  - citation (every address must resolve to file + <pb:>)
  - grounded_pos (claimed text really is at that address)
  - grounded_neg (fabrications return nothing)

NOT covered here:
  - retrieval_cross: 焦氏易林 has no second edition in the corpus
  - version: same reason

Appends to data/catalog/eval_g1.json rather than overwriting it.
"""
from __future__ import annotations

import json
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.evalset import body_in  # noqa: E402
from guji.variants import fold  # noqa: E402
from guji.yilin import WORK_ID, name_table, parse_cells  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
BANK = os.path.join(ROOT, "data", "catalog", "eval_g1.json")
SEED = 13
TOP_K = 10

# Per-category caps. 焦氏易林 is 4,096 cells; sampling fraction is deliberately lower than
# 周易's to keep the total bank manageable (193 zhouyi + ~30 yilin = ~220).
CAPS = {"retrieval": 12, "citation": 8, "grounded_pos": 6, "grounded_neg": 6}


def shortest_unique(phrase: str, hay: str, lo: int = 4, hi: int = 12) -> str | None:
    """Shortest window of `phrase` occurring exactly once in `hay`."""
    for size in range(lo, hi + 1):
        if size > len(phrase):
            break
        for i in range(len(phrase) - size + 1):
            w = phrase[i:i + size]
            if hay.count(w) == 1:
                return w
    return None


def transpose_mutant(phrase: str) -> str | None:
    """Swap one adjacent pair near the middle."""
    m = len(phrase) // 2
    for d in range(0, len(phrase) // 2):
        for i in (m + d, m - d):
            if 0 <= i < len(phrase) - 1 and phrase[i] != phrase[i + 1]:
                return phrase[:i] + phrase[i + 1] + phrase[i] + phrase[i + 2:]
    return None


def main() -> int:
    rnd = random.Random(SEED)

    # Load existing bank
    with open(BANK, encoding="utf-8") as f:
        bank = json.load(f)

    existing = bank.get("questions", [])
    if not existing:
        print(f"ERROR: {BANK} does not have a 'questions' key", file=sys.stderr)
        return 1

    # Derive gua_names from KR1a0001 the same way build_index does
    from guji.ingest import derive_gua_names  # noqa: E402
    base_raw = work_body(RAW, "KR1a0001")
    base_names = derive_gua_names(base_raw)
    names = name_table(base_names)

    raw = work_body(RAW, WORK_ID)
    raw_n = body_in(RAW, WORK_ID, "folded_notes")
    p = parse_cells(raw, names)
    cells = p.cells

    if len(cells) != 4096:
        print(f"ERROR: expected 4,096 cells, got {len(cells)}", file=sys.stderr)
        return 1

    # Build address -> text map for grounded_pos
    addr_text: dict[tuple[int, str], str] = {}
    for c in cells:
        addr_text[(c.ben, c.zhi)] = c.text

    qs: list[dict] = []
    addrs = [(c.ben, c.zhi) for c in cells]
    rnd.shuffle(addrs)

    def n_of(cat: str) -> int:
        return sum(1 for q in qs if q["category"] == cat)

    # ---- retrieval: a distinctive fragment must bring back its own address ----
    for ben, zhi in addrs:
        if n_of("retrieval") >= CAPS["retrieval"]:
            break
        text = addr_text[(ben, zhi)]
        if len(text) < 6:
            continue
        q = shortest_unique(text, raw_n)
        if not q:
            continue
        qs.append({
            "id": f"YL-R-{ben:02d}-{zhi}", "category": "retrieval", "kind": "verbatim",
            "query": q,
            "expect": {"scheme": "yilin", "addr1": ben, "addr2": zhi, "top_k": TOP_K},
            "gold_witness": {"work": WORK_ID, "text": q, "space": "folded_notes",
                             "why": "fragment occurs exactly once in 焦氏易林"},
            "note": f"林辭 {text[:20]}",
        })

    # ---- citation: every hit must resolve to file + <pb:> ----
    for ben, zhi in addrs[:CAPS["citation"] * 3]:
        if n_of("citation") >= CAPS["citation"]:
            break
        text = addr_text.get((ben, zhi), "")
        if len(text) < 6:
            continue
        qs.append({
            "id": f"YL-C-{ben:02d}-{zhi}", "category": "citation",
            "expect": {"scheme": "yilin", "addr1": ben, "addr2": zhi,
                       "min_works": 1, "all_citations_resolve": True},
            "gold_witness": {"work": WORK_ID, "text": text[:8], "space": "folded_jing",
                             "why": "address is attested in data/raw/"},
        })

    # ---- grounded_pos: claimed text really is at that address ----
    for ben, zhi in addrs:
        if n_of("grounded_pos") >= CAPS["grounded_pos"]:
            break
        text = addr_text.get((ben, zhi), "")
        if len(text) < 10:
            continue
        probe = text[:10]
        if raw_n.count(probe) != 1:
            continue
        qs.append({
            "id": f"YL-GP-{ben:02d}-{zhi}", "category": "grounded_pos", "query": probe,
            "expect": {"scheme": "yilin", "addr1": ben, "addr2": zhi,
                       "text_present_at_address": True},
            "gold_witness": {"work": WORK_ID, "text": probe, "space": "folded_notes",
                             "why": "10-char head of the 林辭, unique in the work"},
        })

    # ---- grounded_neg: fabrications must return nothing ----
    for ben, zhi in addrs:
        if n_of("grounded_neg") >= CAPS["grounded_neg"]:
            break
        text = addr_text.get((ben, zhi), "")
        if len(text) < 8:
            continue
        mut = transpose_mutant(text[:10])
        if not mut:
            continue
        # Check it's actually absent
        f = fold(mut)
        if f in raw_n:
            continue
        qs.append({
            "id": f"YL-GN-{ben:02d}-{zhi}", "category": "grounded_neg", "query": mut,
            "expect": {"hits": 0},
            "gold_witness": {"work": "*", "text": mut, "absent": True,
                             "space": "folded_notes",
                             "why": "adjacent transposition of a real 林辭",
                             "occurs_in": []},
        })

    # Append to existing bank. Idempotent: a re-run with the same SEED derives the same
    # ids, and appending them again would double-count every question (R18a). Skip ids
    # already present instead — the same discipline research_thread.py's demo follows.
    already = {q["id"] for q in existing}
    dupes = sum(1 for q in qs if q["id"] in already)
    qs = [q for q in qs if q["id"] not in already]
    existing.extend(qs)
    bank["questions"] = existing

    # Update counts
    for cat in ["retrieval", "citation", "grounded_pos", "grounded_neg"]:
        bank["counts"][cat] = bank["counts"].get(cat, 0) + n_of(cat)

    with open(BANK, "w", encoding="utf-8") as f:
        json.dump(bank, f, ensure_ascii=False, indent=1)

    print(f"Added {len(qs)} 焦氏易林 questions to {BANK}"
          + (f" ({dupes} already present, skipped)" if dupes else ""))
    for cat in ["retrieval", "citation", "grounded_pos", "grounded_neg"]:
        print(f"  {cat:16s} {n_of(cat)}")
    print(f"Total bank now {len(existing)} questions")
    return 0


if __name__ == "__main__":
    sys.exit(main())

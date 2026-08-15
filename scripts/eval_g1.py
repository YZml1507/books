"""Score the G1 evaluation bank against the index. This is what makes G1 measurable.

    python scripts/derive_eval_g1.py     # build/refresh the bank from data/raw/
    python scripts/eval_g1.py            # score the index against it

G1's criterion (BOOK_AI_ARCHITECTURE §1): 给定概念，返回的原文片段人工核验准确率 ≥ 95%.

Two properties make this an executable gate rather than an opinion:

 1. EVERY gold answer is re-verified against data/raw/ before it is used. The bank is
    derived from the raw corpus (D-019), and this script independently re-reads the raw
    files and confirms each witness string is present (or, for adversarial questions,
    absent) in the file it names. A question whose witness no longer holds is reported
    INVALID and excluded from scoring — it never silently passes. This is the guard against
    the failure mode that produced 有能乾○九乾: the index cannot be its own authority.

 2. Every assertion is made against RETURNED TEXT, never against a hit count (§3). FTS5
    char-segmentation turns a bare multi-token query into an implicit AND, so counts pass
    while the text is wrong.

PRE-REGISTERED pass criteria — fixed before the first run, and NOT to be relaxed to make
a number look better (docs/GOAL.md §1 red line 2):

    retrieval       >= 95%   gold address appears among the top-10 hits
    citation        == 100%  mechanical: page_anchor is a literal <pb:> in the named file
                             and the unit text is recoverable from that file
    grounded_pos    >= 95%   the claimed 原文 really is at the claimed address
    grounded_neg    == 100%  a fabricated passage MUST return zero hits. Any single false
                             positive fails the category outright, because "quietly
                             returning text that is not in the source" is this project's
                             most severe failure mode (GOAL §2) and one leak is one
                             fabricated citation.
    version         >= 95%   two editions' differing readings stay distinct at one address,
                             AND a folded 異體字 still reaches its variant spelling

    G1 verdict = PASS only if all five categories meet their target.
"""
from __future__ import annotations

import json
import os
import re
import sys

import numpy as np

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.evalset import body_in, in_space, works_on_disk  # noqa: E402
from guji.variants import fold  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
BANK = os.path.join(ROOT, "data", "catalog", "eval_g1.json")
OUT = os.path.join(ROOT, "data", "catalog", "eval_g1_result.json")

# retrieval_concept is scored by the bge encoder, not FTS5 (2a, user-authorized 2026-08-15).
MODEL_DIR = os.path.join(ROOT, "data", "external", "bge-small-zh-v1.5")
QUERY_PREFIX = "为这个句子生成表示以用于检索相关文章："
DOCVECS = os.path.join(ROOT, "data", "catalog", "bge_docvecs.npy")
DOCMETA = os.path.join(ROOT, "data", "catalog", "bge_docmeta.json")

# Separate targets per tier ON PURPOSE. Folding the three retrieval tiers into one
# category would let 40 easy verbatim questions carry a failing ranking tier — an average
# is exactly the wrong summary when the tiers differ in difficulty by construction.
TARGETS = {"retrieval": 0.95, "retrieval_cross": 0.90, "retrieval_hard": 0.80,
           "citation": 1.0, "grounded_pos": 0.95, "grounded_neg": 1.0, "version": 0.95,
           "retrieval_concept": 0.80}
CATS = ("retrieval", "retrieval_cross", "retrieval_hard", "citation",
        "grounded_pos", "grounded_neg", "version", "retrieval_concept")


def unit_text_at(c: Corpus, addr1: int, addr2: str, work: str | None = None,
                 scheme: str = "zhouyi") -> list[str]:
    sql = ("SELECT text FROM unit WHERE scheme=? AND addr1=? AND addr2=?"
           + (" AND work_id=?" if work else "") + " ORDER BY raw_start")
    args = [scheme, addr1, addr2] + ([work] if work else [])
    return [r["text"] for r in c.db.execute(sql, args)]


# ---------------------------------------------------------------------------------------
# witness verification: does the gold still hold in data/raw/?
# ---------------------------------------------------------------------------------------
def verify_witness(q: dict) -> tuple[bool, str]:
    """Re-read data/raw/ and confirm the gold still holds, IN THE SPACE IT WAS CUT FROM.

    The space is not a detail. A witness cut from the 經-only view is not generally a
    substring of the notes-kept view, and a witness containing a variant character cannot
    be found in any folded view at all — see guji.evalset. Eight questions were reported
    INVALID by an earlier version of this function that used one space for everything.
    """
    w = q["gold_witness"]
    space = w.get("space", "folded_notes")

    if w.get("absent"):
        # Absence must hold in BOTH folded spaces, over every work on disk.
        want = fold(w["text"])
        hits = [k for k in works_on_disk(RAW)
                if want in body_in(RAW, k, "folded_notes")
                or want in body_in(RAW, k, "folded_jing")]
        if hits:
            return False, f"witness claims absent but occurs in {hits}"
        return True, f"confirmed absent from all {len(works_on_disk(RAW))} works"

    if w["work"] == "KR1a0031+KR1a0032":
        a = in_space(w["text"], space)
        b = in_space(w["text_b"], space)
        a_ok = a in body_in(RAW, "KR1a0031", space)
        b_ok = b in body_in(RAW, "KR1a0032", space)
        if not (a_ok and b_ok):
            return False, f"31 has witness={a_ok}, 32 has witness={b_ok} (space={space})"
        if a == b:
            return False, "the two witnesses are identical in the comparison space"
        return True, f"both readings present in their own source and differ ({space})"

    want = in_space(w["text"], space)
    if want not in body_in(RAW, w["work"], space):
        return False, f"witness text not found in {w['work']} (space={space})"
    return True, f"present in {w['work']} ({space})"


# ---------------------------------------------------------------------------------------
# scorers — one per category. Each returns (passed, detail).
# ---------------------------------------------------------------------------------------
RANKS: dict[str, list[int]] = {}


def score_retrieval(c: Corpus, q: dict) -> tuple[bool, str]:
    """Gold address must appear among the top-K hits, and the hit must really contain the
    query text — a rank alone would be satisfiable by FTS5's implicit AND (§3)."""
    e = q["expect"]
    hits = c.search(q["query"], limit=e["top_k"])
    want = (e["addr1"], e["addr2"])
    got = [(h.gua, h.yao) for h in hits]
    at = [i for i, gy in enumerate(got) if gy == want]
    if not at:
        RANKS.setdefault(q["category"], []).append(0)      # 0 = not in top-K
        return False, (f"{len(hits)} hits, gold 卦{want[0]}{want[1]} absent; "
                       f"top: {got[:4]}")
    RANKS.setdefault(q["category"], []).append(at[0] + 1)
    wanted = fold(q["query"])
    matching = [hits[i] for i in at if wanted in fold(hits[i].text)]
    if not matching:
        return False, (f"gold address at rank {at[0] + 1} but its text does not contain "
                       f"the query — implicit-AND match, not a phrase match")
    if e.get("must_include_work_other_than"):
        others = [h for h in matching
                  if h.work_id != e["must_include_work_other_than"]]
        if not others:
            return False, (f"gold address found only in "
                           f"{e['must_include_work_other_than']}; attested in "
                           f"{e.get('attested_in')} but not returned from there")
        return True, (f"rank {at[0] + 1}/{len(hits)}, incl. "
                      f"{others[0].work_id} ({len(matching)} units carry the text)")
    return True, f"rank {at[0] + 1}/{len(hits)}"


def score_citation(c: Corpus, q: dict) -> tuple[bool, str]:
    e = q["expect"]
    scheme = e.get("scheme", "zhouyi")
    rows = c.db.execute(
        "SELECT work_id, file, page_anchor, text FROM unit "
        "WHERE scheme=? AND addr1=? AND addr2=?", (scheme, e["addr1"], e["addr2"])
    ).fetchall()
    if not rows:
        return False, "no units at this address"
    works = {r["work_id"] for r in rows}
    if len(works) < e["min_works"]:
        return False, f"only {len(works)} works: {sorted(works)}"
    for r in rows:
        if not r["page_anchor"] or not r["file"]:
            return False, f"{r['work_id']} unit has no anchor/file"
        p = os.path.join(RAW, r["work_id"], r["file"])
        if not os.path.exists(p):
            return False, f"cited file missing on disk: {r['work_id']}/{r['file']}"
        body = open(p, encoding="utf-8").read()
        if f"<pb:{r['page_anchor']}>" not in body:
            return False, (f"anchor {r['page_anchor']} is not a literal <pb:> tag in "
                           f"{r['file']}")
        # The quoted text must be recoverable from the file it names. Two things this must
        # get right, both learned the hard way:
        #  * BOTH sides go through the same normalisation. Comparing a punctuated
        #    unit.text against a DROP-stripped body scored this category 0/30 with no
        #    index defect behind it (probes/probe_citation_space.py).
        #  * subsequence, not substring: a 經 unit legitimately skips an interleaved 注,
        #    so raw_start..raw_end is an envelope rather than a contiguous quotation (G6).
        fb = in_space(re.sub(r"^#.*$", "", body, flags=re.M), "folded_notes")
        t = in_space(r["text"], "folded_notes")
        i = 0
        for ch in fb:
            if i < len(t) and ch == t[i]:
                i += 1
        if i != len(t):
            return False, f"{r['work_id']} text not recoverable from {r['file']}"
    return True, f"{len(rows)} units across {len(works)} works all resolve"


def score_grounded_pos(c: Corpus, q: dict) -> tuple[bool, str]:
    e = q["expect"]
    scheme = e.get("scheme", "zhouyi")
    want = fold(q["query"])
    texts = unit_text_at(c, e["addr1"], e["addr2"], scheme=scheme)
    if not texts:
        return False, "no units at this address"
    for t in texts:
        if want in fold(t):
            return True, "found in a single unit at the address"
    joined = fold("".join(texts))
    if want in joined:
        return True, "found only across concatenated units at the address (merge split)"
    return False, f"claimed 原文 absent from all {len(texts)} units at the address"


def score_grounded_neg(c: Corpus, q: dict) -> tuple[bool, str]:
    """A fabrication must return NOTHING. This is the category that cannot be relaxed."""
    hits = c.search(q["query"], limit=5)
    if not hits:
        return True, "0 hits, as required"
    # Confirm the leak against the returned text before calling it a failure — a hit whose
    # text does not actually contain the query would be a different bug (FTS implicit AND).
    want = fold(q["query"])
    leaked = [h for h in hits if want in fold(h.text)]
    return False, (f"{len(hits)} hits returned for text absent from the corpus; "
                   f"{len(leaked)} literally contain it. first: {hits[0].citation()} "
                   f"-> {hits[0].text[:40]}")


def score_version(c: Corpus, q: dict) -> tuple[bool, str]:
    e = q["expect"]
    scheme = e.get("scheme", "zhouyi")
    if q["kind"] == "divergent":
        ta = unit_text_at(c, e["addr1"], e["addr2"], e["work_a"], scheme=scheme)
        tb = unit_text_at(c, e["addr1"], e["addr2"], e["work_b"], scheme=scheme)
        if not ta or not tb:
            return False, f"units A={len(ta)} B={len(tb)} — address missing in one edition"
        a_all, b_all = fold("".join(ta)), fold("".join(tb))
        wa, wb = fold(e["a_contains"]), fold(e["b_contains"])
        if wa not in a_all:
            return False, f"{e['work_a']} reading {e['a_contains']} not at this address"
        if wb not in b_all:
            return False, f"{e['work_b']} reading {e['b_contains']} not at this address"
        if wa == wb:
            return False, "the two readings collapsed to the same string (flattened)"
        # The sharp part: each edition must NOT carry the other's reading, or the two are
        # not being kept apart at all.
        if wb in a_all or wa in b_all:
            return False, "each edition contains the other's reading; not distinguished"
        return True, f"both readings present and distinct ({e['a_contains']} / {e['b_contains']})"

    hits = c.search(q["query"], limit=20)
    if len(hits) < e["min_hits"]:
        return False, f"searching the canonical spelling returned {len(hits)} hits"
    var = e["hit_contains_variant"]
    with_var = [h for h in hits if var in h.text]
    if not with_var:
        return False, (f"{len(hits)} hits but none contains the variant {var}; the fold "
                       f"is not reaching the variant spelling")
    return True, f"{len(with_var)}/{len(hits)} hits carry the variant {var}"


_bge_model = None
_doc_cache: tuple | None = None


def _load_bge():
    """Lazy model load: eval_g1 is a gate run on every change, so do not pay the import
    cost unless a retrieval_concept question is actually in the bank."""
    global _bge_model
    if _bge_model is None:
        from sentence_transformers import SentenceTransformer
        _bge_model = SentenceTransformer(MODEL_DIR)
    return _bge_model


def _doc_vecs_and_addr(c: Corpus) -> tuple:
    """(N, D) float32 doc vectors + parallel [(addr1, addr2), ...] for the same unit set
    probes/probe_embed_bge.py embeds. Reuses the persisted cache when it is fresh (the id
    list matches the current corpus); otherwise re-encodes and overwrites it."""
    global _doc_cache
    if _doc_cache is not None:
        return _doc_cache
    ids_now = [r["id"] for r in c.db.execute(
        "SELECT unit.id FROM unit JOIN work ON work.id = unit.work_id "
        "WHERE unit.layer='經' AND unit.addr1 IS NOT NULL AND unit.addr2 IS NOT NULL "
        "ORDER BY unit.id")]
    addrs_now = [tuple(r) for r in c.db.execute(
        "SELECT unit.addr1, unit.addr2 FROM unit JOIN work ON work.id = unit.work_id "
        "WHERE unit.layer='經' AND unit.addr1 IS NOT NULL AND unit.addr2 IS NOT NULL "
        "ORDER BY unit.id")]
    if os.path.exists(DOCVECS) and os.path.exists(DOCMETA):
        meta = json.load(open(DOCMETA, encoding="utf-8"))
        if meta.get("ids") == ids_now:
            vecs = np.load(DOCVECS)
            assert vecs.shape[0] == len(ids_now), "cached vector count != unit count"
            _doc_cache = (vecs, [tuple(a) for a in meta["addrs"]])
            return _doc_cache
    model = _load_bge()
    texts = [r["text"] for r in c.db.execute(
        "SELECT unit.text FROM unit JOIN work ON work.id = unit.work_id "
        "WHERE unit.layer='經' AND unit.addr1 IS NOT NULL AND unit.addr2 IS NOT NULL "
        "ORDER BY unit.id")]
    vecs = np.asarray(model.encode(texts, batch_size=64, show_progress_bar=False,
                                   normalize_embeddings=True), dtype=np.float32)
    json.dump({"ids": ids_now, "addrs": [list(a) for a in addrs_now]},
              open(DOCMETA, "w", encoding="utf-8"))
    np.save(DOCVECS, vecs)
    _doc_cache = (vecs, addrs_now)
    return _doc_cache


def score_concept(c: Corpus, q: dict) -> tuple[bool, str]:
    """Concept/paraphrase retrieval: the query is a 白话转述 that does NOT occur verbatim
    in the corpus, so FTS5 cannot answer it. Encode the query with bge (query-side prefix,
    per the model card) and check the gold address appears in the top-K by cosine."""
    e = q["expect"]
    model = _load_bge()
    vecs, addrs = _doc_vecs_and_addr(c)
    qv = np.asarray(model.encode([QUERY_PREFIX + q["query"]],
                                 normalize_embeddings=True),
                    dtype=np.float32).ravel()
    sims = vecs @ qv
    order = np.argsort(-sims)
    want = (e["addr1"], e["addr2"])
    top = order[:e["top_k"]]
    for rank, idx in enumerate(top, 1):
        if addrs[idx] == want:
            RANKS.setdefault(q["category"], []).append(rank)
            return True, f"rank {rank}/{len(top)} (bge cosine)"
    RANKS.setdefault(q["category"], []).append(0)
    got = [addrs[i] for i in top[:4]]
    return False, (f"gold 卦{want[0]}{want[1]} absent from bge top-{e['top_k']}; "
                   f"top: {got}")


SCORERS = {"retrieval": score_retrieval, "retrieval_cross": score_retrieval,
           "retrieval_hard": score_retrieval, "citation": score_citation,
           "grounded_pos": score_grounded_pos, "grounded_neg": score_grounded_neg,
           "version": score_version, "retrieval_concept": score_concept}


def main() -> int:
    if not os.path.exists(BANK):
        print(f"no bank at {BANK} — run scripts/derive_eval_g1.py first")
        return 2
    bank = json.load(open(BANK, encoding="utf-8"))
    c = Corpus(os.path.join(ROOT, "data", "index", "corpus.db"))

    print("=" * 78)
    print(f"G1 evaluation — {len(bank['questions'])} questions, "
          f"bank derived from {bank['derived_from']}")
    print("=" * 78)

    results = []
    by_cat: dict[str, list[bool]] = {}
    invalid: list[tuple[str, str]] = []
    for q in bank["questions"]:
        ok_w, why_w = verify_witness(q)
        if not ok_w:
            invalid.append((q["id"], why_w))
            results.append({**{k: q[k] for k in ("id", "category")},
                            "status": "INVALID", "detail": why_w})
            continue
        passed, detail = SCORERS[q["category"]](c, q)
        by_cat.setdefault(q["category"], []).append(passed)
        results.append({"id": q["id"], "category": q["category"],
                        "status": "PASS" if passed else "FAIL", "detail": detail,
                        "witness": why_w})

    if invalid:
        print(f"\n### {len(invalid)} INVALID questions (gold no longer holds in "
              f"data/raw/; excluded from scoring, never passed silently)")
        for qid, why in invalid[:12]:
            print(f"  {qid:16s} {why}")

    verdicts = {}
    for cat in CATS:
        res = by_cat.get(cat, [])
        n, k = len(res), sum(res)
        rate = k / n if n else 0.0
        tgt = TARGETS[cat]
        verdicts[cat] = "PASS" if n and rate >= tgt else "FAIL"
        print(f"\n{'=' * 78}\n[{verdicts[cat]}] {cat}: {k}/{n} = {rate:.1%}  "
              f"(target {tgt:.0%})")
        for r in results:
            if r["category"] == cat and r["status"] == "FAIL":
                print(f"    FAIL {r['id']:16s} {r['detail']}")
        shown = [r for r in results if r["category"] == cat and r["status"] == "PASS"]
        for r in shown[:2]:
            print(f"    pass {r['id']:16s} {r['detail']}")

    # A tier where every gold address lands at rank 1 is not measuring ranking, whatever
    # its pass rate says. Print the distribution so the bank's own weakness is visible in
    # its output rather than inferred later — "the number is good" is not evidence the test
    # is good (GOAL §2).
    print(f"\n{'=' * 78}\nrank distribution (0 = gold not in top-K)")
    for cat, rs in RANKS.items():
        dist = {r: rs.count(r) for r in sorted(set(rs))}
        flat = len(set(rs)) == 1
        print(f"  {cat:16s} {dist}"
              f"{'   <- every hit at one rank: this tier does NOT discriminate' if flat else ''}")

    overall = "PASS" if all(v == "PASS" for v in verdicts.values()) else "FAIL"
    total = sum(len(v) for v in by_cat.values())
    scored = sum(sum(v) for v in by_cat.values())
    print(f"\n{'=' * 78}")
    print(f"G1 = {overall}    {scored}/{total} questions passed "
          f"({scored / max(total, 1):.1%} overall), {len(invalid)} invalid")
    for cat, v in verdicts.items():
        print(f"  {cat:14s} {v}")
    print("=" * 78)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"verdicts": verdicts, "overall": overall,
                   "targets": TARGETS, "invalid": invalid,
                   "results": results}, f, ensure_ascii=False, indent=1)
    print(f"-> {os.path.relpath(OUT, ROOT)}")
    c.close()
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

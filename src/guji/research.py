"""Deep research: retrieve → read → expand, with the hop chain shown (G4 made interactive).

This is the 检索即推理 layer the founding brief (chatgpt给的建议.txt §6/§7/§16) asks for:
NOT "question → vector search → LLM", but an agent-shaped loop that decides what to read
next from what it just read. It is deterministic and text-grounded — no LLM is involved,
so every step is reproducible and every result carries a verifiable citation.

Rounds, each recorded in `steps` so the chain that produced the evidence is itself part
of the answer (「链路可展示」 is G4's wording):

  1. search    — folded FTS phrase match over the whole corpus.
  2. witnesses — the zhouyi 卦/爻 addresses the round-1 hits landed on are re-read with
                 `at_address`, which gathers EVERY edition's text at that address; where
                 ≥2 works meet, `compare_address` adds the classified 差异摘要 (校勘-grade
                 differences, never folded away — D-013).
  3. link-hop  — a 焦氏易林 hit is followed through the source-printed cross-reference
                 table (`link`, G4: relations PRINTED IN THE ORIGINAL, not inferred), and
                 the cell it points at joins the evidence set.

Suspect discipline mirrors answer.py: flagged hits are separated from clean evidence; a
result that is ENTIRELY flagged is a refusal unless `allow_damaged` — returning OCR
corruption as research evidence is the failure X-11 exists to prevent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .compare import compare_address
from .search import Corpus, Hit


@dataclass
class Step:
    action: str      # search | witnesses | compare | link-hop
    query: str       # what was asked of the corpus
    found: int       # raw result count
    kept: int        # how many joined the evidence set
    note: str = ""


@dataclass
class Research:
    question: str
    steps: list[Step] = field(default_factory=list)
    evidence: list[Hit] = field(default_factory=list)
    flagged: list[Hit] = field(default_factory=list)   # suspect hits, disclosed not served
    comparisons: list[dict] = field(default_factory=list)
    refused: bool = False
    reason: str | None = None

    def step_dict(self) -> list[dict]:
        return [{"action": s.action, "query": s.query, "found": s.found,
                 "kept": s.kept, "note": s.note} for s in self.steps]


def _key(h: Hit):
    return (h.work_id, h.gua, h.yao, h.layer, h.page_anchor, h.text[:60])


def _subphrases(q: str, max_tries: int = 150) -> list[tuple[str, int]]:
    """Longest-first candidate phrases (with raw start offsets) when the full
    question is not a corpus phrase.

    A natural-language question (「亢龍有悔是什麼意思」) is not a contiguous string in a
    classical corpus; its quoted classical core (「亢龍有悔」) is. Deterministic
    extraction only — punctuation-split runs, then sliding windows longest-first —
    so what the loop searched remains visible and reproducible. Offsets let callers
    pick position-DISJOINT seeds (containment alone misses 「與莊子中」 vs 「子中如何」,
    which overlap without nesting).

    The cap must be generous: a 13-char vernacular question needs ~44 windows before
    its 4-char classical core is reached, and the core can sit anywhere in the run.
    Each try is one FTS MATCH over 61k units (~ms), so 150 tries is well under a
    second and far cheaper than a wrong refusal.
    """
    runs = [(m.group(0), m.start()) for m in re.finditer(r"[^，。？！,. !？;；、\s]+", q)
            if len(m.group(0)) >= 2]
    out: list[tuple[str, int]] = []
    for run, rs in sorted(runs, key=lambda t: -len(t[0])):
        n = len(run)
        for size in range(n, 1, -1):
            for i in range(0, n - size + 1):
                out.append((run[i:i + size], rs + i))
                if len(out) >= max_tries:
                    return out
    return out


def research(corpus: Corpus, question: str, max_addresses: int = 3,
             per_address: int = 50, allow_damaged: bool = False) -> Research:
    """Run the retrieve → read → expand loop for one question.

    `max_addresses` caps round 2: the loop must stop somewhere, and the addresses are
    ranked by round-1 hit score so the cap drops the least relevant witnesses first.
    """
    res = Research(question=question)
    seen: set = set()

    def keep(hits: list[Hit], step: Step) -> int:
        n = 0
        for h in hits:
            k = _key(h)
            if k in seen:
                continue
            seen.add(k)
            (res.flagged if h.suspect and not allow_damaged else res.evidence).append(h)
            n += 1
        step.kept = n
        res.steps.append(step)
        return n

    # --- round 1: phrase search over the whole corpus -------------------------------
    hits = corpus.search(question, limit=12)
    s1 = Step("search", question, len(hits), 0,
              "folded FTS phrase match（異體字折叠，整词相邻匹配）")
    if not hits:
        # A natural-language question is not a corpus phrase. Retry with up to three
        # POSITION-DISJOINT hitting sub-phrases as seeds: the first-hitting longest
        # window is often a connective fragment (「與莊子」), while the question's
        # conceptual core (「無爲」, 2 chars, tried last by length) is a separate
        # seed that must not be crowded out. Each retry is itself a step: what was
        # searched stays visible and repeatable.
        seeds: list[tuple[str, list[Hit]]] = []
        seed_spans: list[tuple[int, int]] = []
        for cand, cs in _subphrases(question):
            ce = cs + len(cand)
            if any(cs < se and s < ce for s, se in seed_spans):
                continue    # overlaps an existing seed's span in the question
            found = corpus.search(cand, limit=12)
            if found:
                seeds.append((cand, found))
                seed_spans.append((cs, ce))
                if len(seeds) >= 3:
                    break
        if seeds:
            merged: list[Hit] = []
            seen_r1: set = set()
            for _, found in seeds:
                for h in found:
                    k = _key(h)
                    if k not in seen_r1:
                        seen_r1.add(k)
                        merged.append(h)
            hits = merged[:18]
            s1 = Step("search-fallback", "；".join(s for s, _ in seeds),
                      sum(len(f) for _, f in seeds), 0,
                      f"整句「{question}」无命中，改用 {len(seeds)} 个互不重叠的"
                      f"命中子短语作种子（可见可复现）")
    keep(hits, s1)
    if not hits:
        res.refused = True
        res.reason = (f"检索「{question}」在语料中无命中，不推测。"
                      "研究循环没有第一轮证据就无法展开（G7）。")
        return res

    # --- round 2: re-read the addresses round 1 landed on ---------------------------
    ranked: dict[tuple[int, str | None], float] = {}
    for h in hits:
        if h.scheme == "zhouyi" and h.gua is not None:
            k = (h.gua, h.yao)
            ranked[k] = max(ranked.get(k, 0.0), h.score)
    for gua, yao in sorted(ranked, key=ranked.get, reverse=True)[:max_addresses]:
        label = f"卦{gua}" + (f"·{yao}" if yao else "")
        wit = corpus.at_address(gua, yao, limit=per_address)
        keep(wit, Step("witnesses", label, len(wit), 0,
                       "该地址全部见证（各版本/各层）"))
        works = {h.work_id for h in wit if h.scheme == "zhouyi"}
        if len(works) >= 2 and yao:
            cmp = compare_address(corpus, gua, yao)
            ev = cmp.evidential()
            if ev:
                res.comparisons.append({
                    "addr": cmp.addr, "reference": cmp.reference,
                    "agree": cmp.agree,
                    "findings": [{"kind": f.kind, "base_id": f.base_id,
                                  "base": f.base, "others": f.others,
                                  "note": f.note, "line": f.line()} for f in ev],
                    "citations": cmp.citations,
                })
                res.steps.append(Step("compare", label, len(ev), len(ev),
                                      "差异摘要：校勘级分歧（preserved-variant 不折叠）"))

    # --- round 3: follow source-printed cross-references from 焦氏易林 hits ----------
    for h in hits:
        if h.scheme != "yilin" or h.gua is None:
            continue
        rows = corpus.db.execute(
            "SELECT l.dst_unit, l.note FROM link l JOIN unit s ON s.id = l.src_unit "
            "WHERE s.work_id = ? AND s.addr1 = ? AND s.addr2 = ? AND s.layer = ?",
            (h.work_id, h.gua, h.yao, h.layer)).fetchall()
        if not rows:
            continue
        dst = corpus.units_by_id([r["dst_unit"] for r in rows])
        notes = "；".join(r["note"] for r in rows)
        keep(dst, Step("link-hop", f"{h.work_id} 卦{h.gua}·{h.yao}", len(rows), 0,
                       f"原文印出的互见（{notes}），非推断边（D-023）"))

    # --- G7 discipline: clean evidence or refusal -----------------------------------
    if not res.evidence:
        if res.flagged and not allow_damaged:
            flags = sorted({h.suspect for h in res.flagged})
            res.refused = True
            res.reason = (f"「{question}」的命中全部位于质量闸门标记区"
                          f"（{', '.join(flags)}），不作为研究证据。"
                          f"如需查看请用 allow_damaged=True。")
        # allow_damaged with hits: evidence was kept via keep() above, not here.
    return res


def concept_census(corpus: Corpus, concept: str, per_work: int = 3,
                   scan_limit: int = 200) -> dict:
    """One concept across the whole corpus: per-work census + shared-address map.

    The cross-book research shape the founding brief §17 asks for («研究'变'的概念»):
    which works carry the concept, in which layers, how often, with a verifiable
    citation for each top hit — and where two works meet the concept at the SAME
    zhouyi address, because that is where 版本/注家 divergence begins.
    """
    works = [dict(r) for r in corpus.db.execute(
        "SELECT id, title, attribution FROM work ORDER BY id")]
    census: list[dict] = []
    shared: dict[tuple[int, str | None], list[str]] = {}
    for w in works:
        hits = corpus.search(concept, limit=scan_limit, work_id=w["id"])
        if not hits:
            continue
        layers: dict[str, int] = {}
        for h in hits:
            layers[h.layer] = layers.get(h.layer, 0) + 1
            if h.scheme == "zhouyi" and h.gua is not None:
                shared.setdefault((h.gua, h.yao), []).append(w["id"])
        census.append({
            "work_id": w["id"], "title": w["title"], "attribution": w["attribution"],
            "n_hits": len(hits), "layers": layers,
            "top": [{"citation": h.citation(), "text": h.text[:200],
                     "disclosure": h.disclosure()} for h in hits[:per_work]],
        })
    census.sort(key=lambda c: -c["n_hits"])
    # Honest census: n_hits is capped by scan_limit per work; say so instead of
    # silently under-reporting a very frequent concept (audit-track R20a note 2).
    truncated = any(c["n_hits"] >= scan_limit for c in census)
    cross = [{"addr": f"卦{g}" + (f"·{y}" if y else ""), "works": sorted(set(ws))}
             for (g, y), ws in sorted(shared.items(),
                                      key=lambda kv: (kv[0][0], kv[0][1] or ""))
             if len(set(ws)) >= 2]
    return {"concept": concept, "works_with_hits": len(census),
            "scan_limit": scan_limit, "truncated": truncated,
            "census": census, "shared_addresses": cross[:30]}


def compare_works(corpus: Corpus, work_a: str, work_b: str, concept: str,
                  per_work: int = 3, scan_limit: int = 200) -> dict:
    """Two-work side-by-side comparison at one concept (愿景 §7 Comparative Study).

    The founding brief's third UX scenario verbatim — 「把《道德经》和《庄子》
    中关于'无为'的思想进行比较」: pick TWO works and ONE concept, and see each
    work's own evidence (citation + layer + text) side by side, its layer
    distribution, and any zhouyi address where BOTH works meet the concept —
    because a shared 卦/爻 address is where 版本/注家 divergence begins.

    Honest by construction: a work with zero hits is shown as 0, not dropped —
    the asymmetry IS the comparison. Only a fully empty result (both sides 0)
    is refused.
    """
    concept = (concept or "").strip()
    if not concept:
        return {"error": "concept 不能为空"}

    def _side(wid: str) -> dict | None:
        w = corpus.db.execute(
            "SELECT id, title, attribution FROM work WHERE id = ?", (wid,)).fetchone()
        if w is None:
            return None
        hits = corpus.search(concept, limit=scan_limit, work_id=wid)
        layers: dict[str, int] = {}
        for h in hits:
            layers[h.layer] = layers.get(h.layer, 0) + 1
        return {
            "work_id": w["id"], "title": w["title"], "attribution": w["attribution"],
            "n_hits": len(hits), "layers": layers,
            "truncated": len(hits) >= scan_limit,
            "top": [{"citation": h.citation(), "layer": h.layer,
                     "text": h.text[:200], "disclosure": h.disclosure()}
                    for h in hits[:per_work]],
            "_hits": hits,
        }

    sa = _side(work_a)
    sb = _side(work_b)
    if sa is None or sb is None:
        return {"error": f"work not found: {work_a if sa is None else work_b}"}
    if sa["n_hits"] == 0 and sb["n_hits"] == 0:
        return {"error": f"「{concept}」在两书均无命中"}
    # shared zhouyi addresses where BOTH works meet the concept
    za = {(h.gua, h.yao) for h in sa["_hits"]
          if h.scheme == "zhouyi" and h.gua is not None}
    zb = {(h.gua, h.yao) for h in sb["_hits"]
          if h.scheme == "zhouyi" and h.gua is not None}
    shared = [{"addr": f"卦{g}" + (f"·{y}" if y else "")}
              for (g, y) in sorted(za & zb, key=lambda kv: (kv[0], kv[1] or ""))]
    for s in (sa, sb):
        s.pop("_hits", None)
    return {"concept": concept, "scan_limit": scan_limit,
            "works": [sa, sb], "shared_addresses": shared}


if __name__ == "__main__":
    # Self-test (R18b). Run: PYTHONPATH=src python -m guji.research
    # (top-level relative imports mean this file is not a script).
    # The acceptance cases are the ones the gates already calibrate, so a regression
    # here is a regression the gates would eventually catch too.
    import os
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    c = Corpus(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "index", "corpus.db"))

    r1 = research(c, "見群龍无首")
    assert not r1.refused and r1.evidence, r1.reason
    assert any(s.action == "search" for s in r1.steps)
    assert any(s.action == "witnesses" for s in r1.steps), \
        "round 1 hits a zhouyi address, round 2 must re-read its witnesses"
    print(f"[1] 見群龍无首 -> {len(r1.evidence)} evidence, "
          f"steps: {[s.action for s in r1.steps]}")

    r2 = research(c, "枯楊生稊")
    assert not r2.refused and r2.comparisons, "卦28九二 must compare across works"
    kinds = {f["kind"] for cmp in r2.comparisons for f in cmp["findings"]}
    assert "preserved-variant" in kinds, "稊/梯 control must surface as preserved-variant"
    print(f"[2] 枯楊生稊 -> comparisons at {[cmp['addr'] for cmp in r2.comparisons]}, "
          f"kinds={sorted(kinds)}")

    # A question whose FULL text and EVERY sub-phrase miss the corpus must refuse.
    # (Modern words only — 青龍白虎-style strings DO hit via the sub-phrase fallback,
    # which is the fallback working as designed, not a refusal-path failure.)
    r3 = research(c, "電話飛機電腦")
    assert r3.refused, "no-hit question must refuse (G7)"
    print(f"[3] impossible -> refused: {r3.reason[:40]}…")

    row = c.db.execute(
        "SELECT u.text, u.work_id, u.addr1, u.addr2 FROM unit u "
        "JOIN link l ON l.src_unit = u.id WHERE u.layer = '林辭' LIMIT 1").fetchone()
    r4 = research(c, row["text"][:4])
    assert any(s.action == "link-hop" for s in r4.steps), \
        "a yilin hit with an outgoing link must trigger the hop round"
    print(f"[4] yilin hop -> steps: {[s.action for s in r4.steps]}")

    cc = concept_census(c, "潛龍勿用", per_work=2)
    assert cc["works_with_hits"] >= 2, "潛龍勿用 must appear in more than one work"
    assert cc["shared_addresses"], "multiple works carry it at a shared address"
    print(f"[5] concept 潛龍勿用 -> {cc['works_with_hits']} works, "
          f"shared at {[x['addr'] for x in cc['shared_addresses'][:3]]}")

    cw = compare_works(c, "KR5c0057", "KR5c0126", "無爲", per_work=2)
    assert "error" not in cw, cw
    wa, wb = cw["works"]
    assert wa["work_id"] == "KR5c0057" and wb["work_id"] == "KR5c0126"
    assert wa["n_hits"] > 0 and wb["n_hits"] > 0, \
        "無爲 must hit both 老子 and 莊子"
    assert all(h["citation"] for h in wa["top"] + wb["top"]), \
        "every compared hit carries a verifiable citation"
    print(f"[6] compare_works 無爲 老子({wa['n_hits']}) vs 莊子({wb['n_hits']}), "
          f"shared={[x['addr'] for x in cw['shared_addresses']]}")
    cw404 = compare_works(c, "KR5c0057", "KR5c0126", "電話飛機電腦")
    assert "error" in cw404
    print(f"[7] compare_works no-hit -> refused: {cw404['error']}")

    # A vernacular question whose 2-char conceptual core must survive as a seed
    # alongside the longer connective windows that hit first (R20b finding).
    r6 = research(c, "無爲在老子與莊子中如何表述")
    assert not r6.refused, r6.reason
    fb = next((s for s in r6.steps if s.action == "search-fallback"), None)
    assert fb and "無爲" in fb.query.split("；"), f"seeds were {fb and fb.query}"
    dao = [h for h in r6.evidence if h.work_id.startswith("KR5c")]
    assert dao, "Daoist works must be reachable from the 無爲 seed"
    print(f"[6] 無爲 multi-seed -> seeds「{fb.query}」, "
          f"{len(dao)} Daoist evidence of {len(r6.evidence)}")
    print("self-test PASS")
    c.close()

"""MCP server (founding brief §11): the corpus as tools for external agents.

    PYTHONPATH=src python -m guji.mcp_server          # stdio MCP server

Exposes exactly the operations the web/CLI layers already run on, with the same
discipline — nothing here invents a new capability, it re-publishes the existing
ones so a Claude-class client can search, read addresses, compare editions, run
the deep-research loop, and resume research threads:

  search    FTS phrase retrieval (folded 異體字), citations attached
  addr      address lookup, all six schemes, scheme declared explicitly (D-005)
  compare   cross-edition reading + classified 差异摘要 at one 卦/爻 (G5)
  concept   one concept across the whole corpus, per-work census (§17.3)
  research  the deterministic retrieve -> read -> expand loop (steps returned,
            refusal on no evidence — G7; never an LLM call)
  threads   G9 research threads: list / transcript

Citations are rendered server-side from Hit objects (page_anchor + address +
file); a tool result never carries a page reference the corpus cannot reproduce
(G2). Suspect/damaged hits are disclosed with their verdict, never silently
served (X-11).
"""
from __future__ import annotations

import json
import os

from mcp.server.mcpserver import MCPServer

from .bookstudy import book_summary  # noqa: E402
from .bookstudy import chapter as book_chapter  # noqa: E402
from .bookstudy import structure as book_structure  # noqa: E402
from .knowledge import KnowledgeBase
from .research import compare_works, concept_census, research
from .search import Corpus

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS_DB = os.path.join(ROOT, "data", "index", "corpus.db")
KNOWLEDGE_DB = os.path.join(ROOT, "data", "index", "knowledge.db")

mcp = MCPServer(
    name="guji-books",
    instructions=(
        "古籍研究语料（47 部，周易系/道家/圣经/哲学/文学/科学多体系）。"
        "所有结果附可核验引用（书名/层/地址/页锚点/源文件）；损坏区带标记披露；"
        "无证据时 research_tool 会拒绝并说明原因——不要绕过拒绝。"
    ),
)


def _hits_md(hits) -> str:
    if not hits:
        return "(no hits)"
    lines = []
    for h in hits:
        d = f"  ⚠ {h.disclosure()}" if h.disclosure() else ""
        lines.append(f"- {h.citation()}\n  {h.text[:200]}{d}")
    return "\n".join(lines)


@mcp.tool()
def search(q: str, layer: str | None = None, work: str | None = None,
           limit: int = 10) -> str:
    """Full-text phrase search over the 古籍 corpus (異體字 folded, adjacency kept).
    Every hit carries a verifiable citation: 书名/层/卦爻地址/页锚点/源文件."""
    c = Corpus(CORPUS_DB)
    try:
        return _hits_md(c.search(q, limit=min(max(limit, 1), 50),
                                 layer=layer, work_id=work))
    finally:
        c.close()


@mcp.tool()
def addr(scheme: str, gua: int | None = None, yao: str | None = None,
         addr_name: str | None = None, addr1: int | None = None,
         addr2: str | None = None, limit: int = 20) -> str:
    """Read every witness at one address. scheme: zhouyi(卦/爻) | bcv(圣经卷章節) |
    yilin(本卦/之卦) | booksec(BOOK·節) | play(幕/場) | euclid(BOOK·命题).
    zhouyi uses gua/yao; others use addr_name/addr1/addr2."""
    c = Corpus(CORPUS_DB)
    try:
        if scheme == "zhouyi":
            if gua is None:
                return "zhouyi needs gua (1-64)"
            hits = c.at_address(gua, yao, limit=min(max(limit, 1), 100))
        else:
            hits = c.at_scheme(scheme, addr_name=addr_name, addr1=addr1,
                               addr2=addr2, limit=min(max(limit, 1), 100))
        return _hits_md(hits)
    finally:
        c.close()


@mcp.tool()
def compare(gua: int, yao: str = "九三", layer: str | None = "經") -> str:
    """Parallel editions at one 卦/爻 plus a classified difference summary
    (校勘-grade; preserved variants are never folded away)."""
    from .compare import compare_address
    c = Corpus(CORPUS_DB)
    try:
        cmp = compare_address(c, gua, yao, layer=layer)
        out = [f"{cmp.addr} · reference {cmp.reference} · "
               + ("各版本一致" if cmp.agree else "存在校勘差异")]
        for w, cite in cmp.citations.items():
            out.append(f"- {cite}: {cmp.witnesses.get(w, '')[:120]}")
        for f in cmp.findings:
            out.append(f"  {f.line()}")
        return "\n".join(out) if out else "(no witnesses)"
    finally:
        c.close()


@mcp.tool()
def concept(q: str, per_work: int = 3) -> str:
    """Census of one concept across the whole corpus: which works carry it, in
    which layers, how often, top citations, and the addresses where several
    works meet (where 版本/注家 divergence begins)."""
    c = Corpus(CORPUS_DB)
    try:
        r = concept_census(c, q, per_work=min(max(per_work, 1), 10))
        head = [f"「{r['concept']}」in {r['works_with_hits']} works"
                + (" (TRUNCATED at scan_limit)" if r.get("truncated") else "")]
        for e in r["census"]:
            who = e["title"] or e["work_id"]
            head.append(f"- {who} [{e['work_id']}] {e['n_hits']} hits "
                        f"layers={json.dumps(e['layers'], ensure_ascii=False)}")
            for t in e["top"]:
                head.append(f"    {t['citation']}: {t['text'][:80]}")
        if r["shared_addresses"]:
            head.append("shared addresses: " + "; ".join(
                f"{x['addr']}({','.join(x['works'])})" for x in r["shared_addresses"][:10]))
        return "\n".join(head)
    finally:
        c.close()


@mcp.tool()
def research_tool(q: str, max_addresses: int = 3,
                  allow_damaged: bool = False) -> str:
    """Deterministic deep research: retrieve -> read all witnesses at the hit
    addresses -> compare editions -> follow source-printed cross-references.
    Returns the STEP CHAIN (what was searched and kept at every round), the
    evidence set with citations, and classified differences. Refuses when there
    is no clean evidence (G7) — the refusal text says why."""
    c = Corpus(CORPUS_DB)
    try:
        r = research(c, q, max_addresses=min(max(max_addresses, 1), 6),
                     allow_damaged=allow_damaged)
        out = [f"steps: " + " | ".join(
            f"{s.action}→「{s.query}」{s.kept}/{s.found}" for s in r.steps)]
        if r.refused:
            out.append(f"REFUSED: {r.reason}")
            return "\n".join(out)
        for cmp in r.comparisons:
            out.append(f"diff {cmp['addr']} (ref {cmp['reference']}):")
            out.extend(f"  {f['line']}" for f in cmp["findings"][:10])
        out.append("evidence:")
        out.append(_hits_md(r.evidence[:20]))
        return "\n".join(out)
    finally:
        c.close()


@mcp.tool()
def threads(tid: int | None = None) -> str:
    """G9 research threads: list resumable threads (topic + claims), or when
    tid is given, the full transcript of that thread."""
    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        if tid is None:
            rows = kb.resume()
            if not rows:
                return "(no threads)"
            return "\n".join(f"- #{t['id']} {t['topic']}" for t in rows)
        turns = kb.thread_transcript(tid)
        if not turns:
            return f"(thread {tid} not found or empty)"
        return "\n".join(f"{t['role']}: {t['text'][:400]}" for t in turns)
    finally:
        kb.close()


@mcp.tool()
def book_summary_tool(work_id: str) -> str:
    """Book Summary (R27b): one work's structured knowledge card — sections,
    units, total chars, 經/注/疏 layer distribution, damaged-unit disclosure,
    unaddressed count, and the largest/smallest sections (reading attention
    points). Pure read-only aggregation over the index."""
    c = Corpus(CORPUS_DB)
    try:
        r = book_summary(c, work_id)
        if "error" in r:
            return r["error"]
        out = [f"{r['title']} · {r['n_sections']} 节 · {r['n_units']} 单元 · "
               f"{r['total_chars']} 字 · scheme {r['scheme'] or '（无）'}"]
        if r["layers"]:
            out.append("层分布: " + "、".join(
                f"{lv}={v['units']}单元/{v['chars']}字"
                for lv, v in r["layers"].items()))
        out.append(f"未编址 {r['unaddressed_units']} 单元 · 损坏区 {r['suspect_units']} · "
                   f"非连续 {r['skipped_chars_units']}")
        if r["largest_section"]:
            out.append(f"最大节: {r['largest_section']['label']} "
                       f"({r['largest_section']['chars']} 字) · 最小节: "
                       f"{r['smallest_section']['label']} "
                       f"({r['smallest_section']['chars']} 字)")
        return "\n".join(out)
    finally:
        c.close()


@mcp.tool()
def bookstudy_structure(work_id: str, sample_chars: int = 60) -> str:
    """Book Study (R23b): one work's structural map — sections in source order,
    sizes, 經/注/疏 layers, and a first-line sample with a REAL citation per
    section. Every number is a COUNT over the index, recomputed on call."""
    c = Corpus(CORPUS_DB)
    try:
        r = book_structure(c, work_id, sample_chars=min(max(sample_chars, 20), 200))
        if "error" in r:
            return r["error"]
        out = [f"{r['title']} · {r['n_sections']} 节 · {r['n_units']} 单元 "
               f"· scheme {r['scheme'] or '（无）'}"]
        for s in r["sections"]:
            out.append(f"- {s['label']} [{s['scheme'] or 'file'}] "
                       f"{s['n_units']} 单元 {s['chars']} 字 "
                       f"layers={json.dumps(s['layers'], ensure_ascii=False)}")
            if s["sample"]:
                out.append(f"    {s['sample']} — {s['sample_citation']}")
        return "\n".join(out)
    finally:
        c.close()


@mcp.tool()
def bookstudy_chapter(work_id: str, scheme: str,
                      addr_name: str | None = None, addr1: int | None = None,
                      file: str | None = None, limit: int = 60) -> str:
    """Book Study (R23b): one section's full reading view — every unit in source
    order with server-rendered citations; damaged (?) and non-contiguous (!)
    units disclosed. NULL-scheme works (老子) take scheme='file' + file=."""
    c = Corpus(CORPUS_DB)
    try:
        r = book_chapter(c, work_id, scheme, addr_name=addr_name, addr1=addr1,
                         file=file, limit=min(max(limit, 1), 200))
        if "error" in r:
            return r["error"]
        out = [f"{r['section']} · {r['n_units']} 单元（原书顺序）"]
        out.extend(f"- [{u['layer'] or '?'}] {u['citation']}: {u['text'][:200]}"
                   for u in r["units"])
        return "\n".join(out)
    finally:
        c.close()


@mcp.tool()
def compare_works_tool(work_a: str, work_b: str, concept: str,
                       per_work: int = 3) -> str:
    """Comparative Study (R24b): one concept in TWO works side by side — each
    work's top evidence (citation + layer + text), layer distribution, and any
    zhouyi address where both works meet the concept (版本/注家分歧起点).
    A side with zero hits is shown as 0; both-empty refuses (G7)."""
    c = Corpus(CORPUS_DB)
    try:
        r = compare_works(c, work_a, work_b, concept,
                          per_work=min(max(per_work, 1), 10))
        if "error" in r:
            return r["error"]
        a, b = r["works"]
        out = [f"「{r['concept']}」{a['title']} {a['n_hits']} vs "
               f"{b['title']} {b['n_hits']} "
               f"(layers {json.dumps(a['layers'], ensure_ascii=False)} / "
               f"{json.dumps(b['layers'], ensure_ascii=False)})"]
        if r["shared_addresses"]:
            out.append("同址命中: " + "、".join(x["addr"] for x in r["shared_addresses"]))
        for tag, w in (("A", a), ("B", b)):
            out.append(f"{tag}. {w['title']}:")
            if not w["top"]:
                out.append("    (0 命中)")
            for h in w["top"]:
                out.append(f"    [{h['layer'] or '?'}] {h['citation']}: "
                           f"{h['text'][:200]}")
        return "\n".join(out)
    finally:
        c.close()


if __name__ == "__main__":
    mcp.run()

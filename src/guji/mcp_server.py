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
import sys

from mcp.server.mcpserver import MCPServer

from .bookstudy import book_summary  # noqa: E402
from .bookstudy import chapter as book_chapter  # noqa: E402
from .bookstudy import structure as book_structure  # noqa: E402
from .knowledge import KnowledgeBase
from .research import compare_works, concept_census, research
from .sources import add_local_work
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
    tid is given, the full transcript of that thread PLUS its derived claims
    with evidence (R42b — read-back side of the record_claim_tool write,
    mirroring web GET /api/threads/{tid})."""
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
        out = [f"{t['role']}: {t['text'][:400]}" for t in turns]
        claims = kb.db.execute(
            "SELECT id FROM derived WHERE thread_id=? ORDER BY id", (tid,))
        if claims:
            out.append("=== derived claims ===")
            for row in claims:
                d = kb.get(row["id"])
                if d is None:
                    continue
                out.append(f"- [{d.kind}] {d.claim} "
                           f"(method: {d.method}"
                           + (f", conf: {d.confidence}" if d.confidence else "")
                           + ")")
                for e in d.evidence:
                    out.append(f"    ev {e.role} {e.work_id} @{e.page_anchor or '?'} "
                               f"({e.file}): {e.quote[:100]}")
        return "\n".join(out)
    finally:
        kb.close()


@mcp.tool()
def record_claim_tool(kind: str, claim: str, method: str,
                      evidence: list[dict] | None = None,
                      confidence: str | None = None,
                      thread_id: int | None = None) -> str:
    """G9 record a derived claim into a research thread (R36b, 愿景 §8/§9).
    G8 discipline verbatim from knowledge.record: asserting kinds
    (summary/diff/link/answer) REQUIRE at least one evidence entry with a real
    work_id/file/quote — a claim without provenance is refused; kind='refusal'
    is exempt (G7: 「证据不足」 is itself a valid finding). Each evidence dict:
    {work_id, file, quote, page_anchor?, scheme?, addr1?, addr2?, role?}.
    thread_id: bind to an existing thread (see `threads` for the list) so the
    claim shows up in that thread's readback; omit to leave it standalone.
    Returns the derived_id / thread_id summary, or an error: text."""
    from .knowledge import Evidence  # noqa: E402

    kb = KnowledgeBase(KNOWLEDGE_DB)
    try:
        ev = []
        for e in (evidence or []):
            ev.append(Evidence(
                work_id=str(e.get("work_id") or ""), file=str(e.get("file") or ""),
                raw_start=int(e.get("raw_start") or -1),
                raw_end=int(e.get("raw_end") or -1),
                quote=str(e.get("quote") or ""),
                page_anchor=e.get("page_anchor"), scheme=e.get("scheme"),
                addr1=e.get("addr1"), addr2=e.get("addr2"),
                role=str(e.get("role") or "supports")))
        try:
            did = kb.record(kind, claim, method, ev, confidence=confidence,
                            thread_id=thread_id)
        except ValueError as exc:
            return f"error: {exc}"
        row = kb.db.execute(
            "SELECT thread_id FROM derived WHERE id = ?", (did,)).fetchone()
        return (f"recorded #{did} kind={kind} thread={row['thread_id'] if row else None} "
                f"evidence={len(ev)}. 跨会话可用 threads 工具恢复。")
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
def add_local_work_tool(work_id: str, genre: str, rationale: str,
                        txt_dir: str) -> str:
    """Add a LOCAL directory of utf-8 txt files as a new work (R31b, 愿景
    §10/§18: 不断加书). Only `{work_id}(_\\w+)?\\.txt` files are imported into
    data/raw/<work_id>/; title/edition read from #+TITLE / BASEEDITION headers
    when present; the manifest is upserted additively (other works kept).
    Zero network. IMPORTANT: run `python -m guji.sources` — actually
    `scripts/build_index.py` — afterwards for the work to enter the index."""
    try:
        e = add_local_work(work_id, genre, rationale, txt_dir)
    except RuntimeError as exc:
        return f"error: {exc}"
    return (f"added {e['id']} 《{e['title']}》 genre={e['genre']} "
            f"{e['n_files']} files {e['n_chars']:,} chars (local). "
            f"运行 scripts/build_index.py 后入库生效。")


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
    if "--selftest" in sys.argv:
        # Protocol-level self-test (R28b): drive a real stdio MCP subprocess over
        # newline-delimited JSON-RPC, exactly as an external client would.
        # Run: PYTHONPATH=src python -m guji.mcp_server --selftest
        import subprocess

        env = dict(os.environ)
        env["PYTHONPATH"] = os.path.join(ROOT, "src") + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.Popen(
            [sys.executable, "-u", "-m", "guji.mcp_server"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env, cwd=ROOT,
            text=True, encoding="utf-8", bufsize=1)

        def send(obj):
            proc.stdin.write(json.dumps(obj) + "\n")
            proc.stdin.flush()

        def recv():
            line = proc.stdout.readline()
            if not line:
                raise AssertionError("MCP subprocess closed stdout")
            return json.loads(line)

        send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
              "params": {"protocolVersion": "2024-11-05",
                         "capabilities": {},
                         "clientInfo": {"name": "guji-selftest", "version": "0"}}})
        resp = recv()
        assert resp["id"] == 1 and "result" in resp, resp
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        resp = recv()
        tools = [t["name"] for t in resp["result"]["tools"]]
        assert resp["id"] == 2, resp
        expected = {"search", "addr", "compare", "concept", "research_tool",
                    "threads", "bookstudy_structure", "bookstudy_chapter",
                    "compare_works_tool", "book_summary_tool",
                    "add_local_work_tool", "record_claim_tool"}
        assert set(tools) == expected, f"tools mismatch: {sorted(set(tools) ^ expected)}"
        print(f"[selftest] tools/list -> {len(tools)} tools OK")

        calls = [
            ("bookstudy_structure", {"work_id": "KR5c0057"}),
            ("bookstudy_chapter", {"work_id": "KR1a0001", "scheme": "zhouyi",
                                   "addr1": 40}),
            ("compare_works_tool", {"work_a": "KR5c0057", "work_b": "KR5c0126",
                                    "concept": "無爲"}),
            ("book_summary_tool", {"work_id": "KR1a0001"}),
            # error path only — a real import would write the live corpus
            ("add_local_work_tool", {"work_id": "T1x9999", "genre": "测试",
                                     "rationale": "协议自测错误路径",
                                     "txt_dir": "C:/definitely/not/here"}),
            # record_claim_tool: legal write with a REAL corpus quote, then the
            # no-evidence refusal path (G8) — the written row is cleaned below
            ("record_claim_tool", {"kind": "summary",
                                   "claim": "协议自测：無爲在老子中可核验的引文",
                                   "method": "mcp-selftest",
                                   "thread_id": 1,
                                   "evidence": [{"work_id": "KR5c0057",
                                                 "file": "KR5c0057_043.txt",
                                                 "quote": "第四十三章 天下之至柔",
                                                 "page_anchor": "KR5c0057_tls_043-1a"}]}),
            ("record_claim_tool", {"kind": "summary", "claim": "无证据断言",
                                   "method": "mcp-selftest", "evidence": []}),
            # R165b（D-211b）：research_tool 协议级断言——与 web /api/research
            # 同内核（web 侧已有 research.allow_damaged/empty/too_long 断言），
            # MCP 发布面此前零协议级覆盖：G7 拒绝路径（q 空→REFUSED）与正常
            # 检索路径（q=潛龍勿用→evidence）
            ("research_tool", {"q": " ", "max_addresses": 2}),
            ("research_tool", {"q": "潛龍勿用", "max_addresses": 2}),
        ]
        record_did = None
        for i, (name, args) in enumerate(calls, start=3):
            send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
            resp = recv()
            assert resp["id"] == i and "result" in resp, (name, resp)
            content = "".join(c.get("text", "") for c in resp["result"].get("content", []))
            assert content, (name, content)
            if name == "add_local_work_tool":
                assert content.startswith("error:"), (name, content)
            elif name == "record_claim_tool" and not args.get("evidence"):
                assert content.startswith("error:"), (name, content)
            elif name == "record_claim_tool":
                assert content.startswith("recorded #"), (name, content)
                record_did = int(content.split("#")[1].split()[0])
            elif name == "research_tool" and not (args.get("q") or "").strip():
                # G7 拒绝路径：空查询必须显式 REFUSED（同 web /api/research
                # 的 q 空→400 语义——同内核不同发布面）
                assert "REFUSED" in content and "evidence:" not in content, (name, content)
            elif name == "research_tool":
                # 正常检索路径：必须返回 evidence（同 web research check）
                assert "evidence:" in content, (name, content)
            else:
                assert "error" not in content.lower(), (name, content)
            print(f"[selftest] tools/call {name} -> {len(content)} chars OK")
        # R42b round trip: the claim written above (bound to thread 1) must
        # show up in threads(1)'s readback
        send({"jsonrpc": "2.0", "id": 99, "method": "tools/call",
              "params": {"name": "threads", "arguments": {"tid": 1}}})
        resp = recv()
        content = "".join(c.get("text", "") for c in resp["result"].get("content", []))
        assert "=== derived claims ===" in content, content
        assert "無爲在老子中可核验的引文" in content, \
            "threads(tid) readback must include the just-recorded claim"
        print("[selftest] threads(1) readback -> claims present OK")
        proc.stdin.close()
        proc.wait(timeout=15)
        assert proc.returncode == 0, f"subprocess exit {proc.returncode}"
        # R34b lesson: the legal record_claim_tool write touched the LIVE
        # knowledge.db — clean that row up so the store stays baseline-clean
        if record_did is not None:
            from .knowledge import KnowledgeBase  # noqa: E402
            from .variants import fold, segment_cjk  # noqa: E402

            kb = KnowledgeBase(KNOWLEDGE_DB)
            try:
                row = kb.db.execute(
                    "SELECT claim FROM derived WHERE id=?", (record_did,)).fetchone()
                if row is not None:
                    seg = segment_cjk(fold(row["claim"]))
                    kb.db.execute(
                        "INSERT INTO derived_fts(derived_fts,rowid,seg) "
                        "VALUES('delete',?,?)", (record_did, seg))
                    kb.db.execute("DELETE FROM evidence WHERE derived_id=?",
                                  (record_did,))
                    kb.db.execute("DELETE FROM derived WHERE id=?", (record_did,))
                    kb.db.commit()
                    print(f"[selftest] record_claim_tool test row #{record_did} cleaned")
            finally:
                kb.close()
        print("MCP protocol self-test PASS")
    else:
        mcp.run()

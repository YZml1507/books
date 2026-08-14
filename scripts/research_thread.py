"""G9: persist a line of enquiry across sessions, and prove it can be resumed.

    python scripts/research_thread.py demo      # create/extend the worked example
    python scripts/research_thread.py list      # what a new session would resume
    python scripts/research_thread.py show 1    # transcript + claims + evidence

G9 asks: 跨会话恢复 — 哪本书、哪版本、哪些原文、何结论、何证据. `build_meta` records builds,
not enquiries, which is why this was FAIL.

The demo thread is not decoration; it is the acceptance test, and it deliberately records a
finding from THIS session so that resumption has something real to recover: the 稊/梯 校勘
divergence at 卦28九二, with both readings, both citations, and a refusal recorded alongside
it for the question the corpus cannot answer.

Idempotent: re-running `demo` reuses the existing thread instead of duplicating it, so this
can sit in a gate list without inflating the store on every run.
"""
from __future__ import annotations

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.compare import compare_address  # noqa: E402
from guji.knowledge import Evidence, KnowledgeBase  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
KBP = os.path.join(ROOT, "data", "index", "knowledge.db")
CORPUS = os.path.join(ROOT, "data", "index", "corpus.db")
TOPIC = "大過九二 枯楊生稊/生梯：異文性质与版本归属"


def demo(kb: KnowledgeBase, c: Corpus) -> int:
    existing = [t for t in kb.resume() if t["topic"] == TOPIC]
    if existing:
        print(f"thread {existing[0]['id']} already exists — reusing it "
              f"({existing[0]['turns']} turns, {existing[0]['claims']} claims)")
        return existing[0]["id"]

    tid = kb.open_thread(TOPIC)
    kb.add_turn(tid, "user", "朱熹两个版本在 大過九二 上到底差在哪，是異文还是刻误？")
    kb.add_turn(tid, "assistant",
                "在 卦28九二 上比较六个见证：KR1a0032 印 生梯，其余五个印 生稊。"
                "稊/梯 在 variants.NOT_VARIANTS 里，即曾考虑折叠并被否决，"
                "所以这是校勘证据而非拼写差异。")

    cmp = compare_address(c, 28, "九二")
    ev: list[Evidence] = []
    for w, t in sorted(cmp.witnesses.items()):
        hs = [h for h in c.at_address(28, "九二", layer="經", limit=50)
              if h.work_id == w]
        if hs and ("稊" in t or "梯" in t):
            ev.append(Evidence.from_hit(hs[0]))
    finding = next((f for f in cmp.findings if f.kind == "preserved-variant"), None)

    kb.record("diff",
              "卦28九二：KR1a0032 作「枯楊生梯」，KR1a0001/0006/0007/0016/0031 作「枯楊生稊」。"
              "稊/梯 属已否决折叠的字对（通假），故为校勘異文，不可归一。",
              method="guji.compare.compare_address + variants.NOT_VARIANTS",
              evidence=ev, confidence="high — 六个见证逐字比对，判据来自折叠否决表",
              thread_id=tid)

    # A refusal recorded next to the finding, because the honest state of this question is
    # "the corpus does not settle it" and G7 requires that to be sayable rather than guessed.
    kb.record("refusal",
              "哪一个读法是朱熹原本？语料无法判定：KR1a0031/0032 均为四庫本，"
              "无更早刻本作第三见证，且本项目不接受未经 provenance 记录的新语料。",
              method="scripts/research_thread.py — 明确认输，不猜",
              confidence="unknown", thread_id=tid)

    kb.add_turn(tid, "assistant",
              f"已记录 1 条 diff 结论（{len(ev)} 条证据）与 1 条认输。"
              f"下一步：查是否存在第三个见证版本（须先过 §5 法务与 provenance）。")
    print(f"created thread {tid}: {TOPIC}")
    if finding:
        print(f"  finding: {finding.line()}")
    return tid


def show(kb: KnowledgeBase, tid: int) -> None:
    rows = kb.thread_transcript(tid)
    print(f"\n=== thread {tid} transcript ({len(rows)} turns) ===")
    for r in rows:
        print(f"  [{r['seq']}] {r['role']:9s} {r['text'][:110]}")
    ds = kb.db.execute("SELECT id FROM derived WHERE thread_id=? ORDER BY id",
                       (tid,)).fetchall()
    print(f"\n=== derived claims on this thread ({len(ds)}) ===")
    for row in ds:
        d = kb.get(row["id"])
        print(f"\n  #{d.id} kind={d.kind}  confidence={d.confidence}")
        print(f"    claim : {d.claim}")
        print(f"    method: {d.method}")
        if not d.evidence:
            print("    evidence: NONE — this is a refusal, which is a finding, not a gap")
        for e in d.evidence:
            print(f"    evidence: {e.citation()}")
            print(f"              {e.quote[:70]}")
    v = kb.verify(RAW)
    print(f"\n=== evidence re-verified against data/raw/: ok={v['ok']} stale={v['stale']} ===")
    if v["stale"]:
        for s in v["details"][:5]:
            print(f"    STALE {s}")


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    kb = KnowledgeBase(KBP)
    try:
        if cmd == "demo":
            c = Corpus(CORPUS)
            try:
                tid = demo(kb, c)
            finally:
                c.close()
            show(kb, tid)
        elif cmd == "show":
            show(kb, int(sys.argv[2]))
        else:
            rows = kb.resume()
            print(f"=== open research threads: {len(rows)} ===")
            for r in rows:
                print(f"  #{r['id']}  {r['topic']}")
                print(f"       opened {r['opened_at']}  updated {r['updated_at']}  "
                      f"turns={r['turns']}  claims={r['claims']}")
            print(f"\nstore: {kb.stats()}")
            if not rows:
                print("nothing to resume — run `research_thread.py demo` first")
        return 0
    finally:
        kb.close()


if __name__ == "__main__":
    raise SystemExit(main())

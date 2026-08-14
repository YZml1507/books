"""G7: answer from evidence, or say 证据不足 — never in between.

The criterion is 「无证据时明确输出"证据不足"，不编造。对抗性测试通过率 ≥ 95%」. Two halves,
and the second is the one that bites: a system that answers everything scores 100% on the
positive half and 0% here.

What this module is NOT: it does not generate prose, and that is deliberate. Every 答案 it
returns is a set of retrieved passages, each carrying the file and page anchor it came from.
The moment an answering layer paraphrases, its output stops being checkable against
data/raw/, and this project's worst measured failure was text that looked like the source but
was not (X-07's 有能乾○九乾). So `Answer.evidence` holds quotations, and `Answer.refused`
carries the reason when there are none.

Three refusal grounds, each measured rather than inferred:

  no-hit            retrieval returned nothing. The corpus does not contain the string.
  address-empty     an address was requested that carries no units in any work.
  damaged-only      every passage found sits at an address the quality gate flagged
                    (schema `suspect`). Returning OCR-damaged text as an answer would be
                    presenting corruption as evidence — KR1a0006 卦61 reads 翰青登于天
                    where the witness has 翰音登于天. Answerable, but not without saying so.

`damaged_only` is why this is not just `if not hits: refuse()`. A count-based refusal rule
would happily serve the damaged text, because there IS a hit.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Answer:
    query: str
    evidence: list = field(default_factory=list)      # list[search.Hit]
    refused: bool = False
    reason: str = ""
    caveats: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.refused:
            return f"证据不足：{self.reason}"
        out = []
        for h in self.evidence:
            line = f"{h.citation()}\n    {h.text[:160]}"
            d = h.disclosure()
            if d:
                line += f"\n    {d}"
            out.append(line)
        head = "\n".join(f"⚠ {c}" for c in self.caveats)
        return (head + "\n" if head else "") + "\n".join(out)

    def as_derived(self) -> tuple[str, str]:
        """(kind, claim) for guji.knowledge.record — refusals stay refusals in the store."""
        if self.refused:
            return "refusal", f"{self.query}：证据不足。{self.reason}"
        return "answer", f"{self.query}：找到 {len(self.evidence)} 条可核验原文"


def answer_text(corpus, query: str, limit: int = 5,
                allow_damaged: bool = False) -> Answer:
    """Answer a text query from retrieved passages, or refuse.

    `allow_damaged=False` means a result set consisting ENTIRELY of flagged passages is a
    refusal, not an answer. When some passages are clean, the damaged ones are dropped and
    the omission is reported as a caveat — silently including them would be the failure this
    guards against, and silently dropping them without saying so would be a different one.
    """
    hits = corpus.search(query, limit=limit)
    if not hits:
        return Answer(query, refused=True,
                      reason=f"检索「{query}」在 28 部语料中无命中，不推测。")
    clean = [h for h in hits if not h.suspect]
    if not clean and not allow_damaged:
        flags = sorted({h.suspect for h in hits if h.suspect})
        return Answer(query, refused=True,
                      reason=(f"仅在已被质量闸门标记的区域命中（{', '.join(flags)}），"
                              f"该处文本可能为 OCR 损坏，不作为证据。"
                              f"如需查看请用 allow_damaged=True。"))
    caveats = []
    if len(clean) < len(hits):
        caveats.append(f"已排除 {len(hits) - len(clean)} 条位于损坏区的命中")
    n_skip = sum(1 for h in clean if h.skipped_chars)
    if n_skip:
        caveats.append(f"{n_skip} 条为非连续引文（层过滤），详见各条披露")
    return Answer(query, evidence=clean, caveats=caveats)


def answer_address(corpus, addr1: int, addr2: str | None = None,
                   layer: str | None = None, allow_damaged: bool = False) -> Answer:
    """Answer 「what does each witness read at this address」, or refuse."""
    label = f"卦{addr1}" + (f"·{addr2}" if addr2 else "")
    hits = corpus.at_address(addr1, addr2, layer=layer, limit=50)
    if not hits:
        return Answer(label, refused=True,
                      reason=f"地址 {label} 在索引中无任何单元；未编址不等于原文不存在，"
                             f"但本系统不据此推测。")
    clean = [h for h in hits if not h.suspect]
    if not clean and not allow_damaged:
        flags = sorted({h.suspect for h in hits if h.suspect})
        return Answer(label, refused=True,
                      reason=f"{label} 上所有见证均位于标记区（{', '.join(flags)}）。")
    caveats = []
    if len(clean) < len(hits):
        caveats.append(f"已排除 {len(hits) - len(clean)} 条位于损坏区的命中")
    return Answer(label, evidence=clean, caveats=caveats)

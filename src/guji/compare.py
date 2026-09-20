"""差异摘要: what the witnesses at one canonical address actually disagree about.

G5's criterion is 「给定同一爻位，并列输出王弼/程頤/朱熹三家原文 + 差异摘要」. The parallel
text has worked since D-006; this module is the missing summary.

The design turns on one constraint, and it is why Work and Edition are modelled separately
at all: a 校勘 variant is EVIDENCE and must survive the summary intact. 枯楊生稊/生梯 and
跛能履/破能履 were explicitly REFUSED as fold candidates (variants.NOT_VARIANTS) because
稊/梯 and 跛/破 are different words, not different spellings. A summary reporting "the
editions agree" there would destroy the finding the system exists to surface.

So divergences are CLASSIFIED, never merged, and the class is read from the fold tables
rather than guessed:

    preserved-variant   the pair is in NOT_VARIANTS — folding was considered and REJECTED
                        with a recorded reason. The strongest class: someone already
                        established these are two words.
    orthographic        the readings fold to the same string (濳/潛, 黄/黃). Reported, not
                        hidden — a reader is entitled to know the witness prints a
                        different glyph — but marked as not a textual variant.
    divergent           survives folding, not a recorded pair. Genuinely different text.
                        NOT adjudicated: 卦1九三 reads 居卜之上 in KR1a0031 against 居下之上
                        in KR1a0032, almost certainly a misprint, but this module reports
                        and leaves the judgement to a reader.
    omission/addition   a short run one witness lacks or adds inside the shared text.
    commentary          a witness's own 注/疏 — summarised as VOLUME, never char-diffed.

That last class earns its own paragraph, because the first version of this module got it
wrong. Diffing 王弼's 注 against 程頤's 注 character by character produces one 350-character
"divergence" that means nothing: different commentators are supposed to write different
words. Only the 經 they quote is a shared text with a shared address, so only that is
aligned. Commentary is reported as "N 字注", which is the honest summary of it.

Two normalisation notes, both learned by breaking them (L-18):

  * texts are compared in the `unfolded_notes` space — punctuation dropped, 異體字 NOT
    folded. Punctuation must go or KR1a0001 (the only heavily punctuated edition: 9,784
    DROP chars over 100% of its units) fragments every reading, and 稊 vs 梯 came back as
    '稊，' vs '梯', which is not a character pair and could not be classified.
  * folding must NOT be applied before alignment, or every orthographic difference vanishes
    from the alignment and therefore from the report.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field

from .evalset import in_space
from .variants import FOLD, NOT_VARIANTS, fold

# Kanripo marks a commentator's own material with these literal characters. Using them is
# what keeps `commentary` from being a pure length heuristic — this project already
# measured that length ratios mislead (Q-02: 卦61 was misclassified 'span-defect' purely
# because one side was short).
COMMENTARY_MARKS = ("注", "疏", "音義", "傳", "○")

# Length fallback for an unmarked insertion, applied ONLY when no marker is present. It is
# a heuristic and is labelled as one in the output; findings of this class are summarised as
# volume and never presented as textual evidence.
COMMENTARY_MIN = 12

REFUSAL_REASON = {
    ("梯", "稊"): "枯楊生稊/生梯 是版本間真实異文（通假字），折叠会抹掉校勘证据",
    ("破", "跛"): "跛能履/破能履 同上；跛（跛足）与 破 是不同的字",
    ("冽", "洌"): "冽（寒）与 洌（清）不同词，语境全为 井洌寒泉，属通假",
    ("已", "己"): "已（已经）与 己（自己）不同词，木刻常混但不可归一",
    ("已", "巳"): "已/己/巳 三字各有其义，任意两两折叠都会毁掉字义",
    ("巳", "已"): "同上",
    ("己", "已"): "同上",
    ("極", "拯"): "極 2,821 次含 太極，折叠会为一个爻改写全语料",
    ("悔", "晦"): "悔 是周易核心词（亢龍有悔），KR1a0031 印 悔 为 晦 属源文误刻",
    ("昊", "昃"): "昊 在别处是正确字（昊天），折叠会污染正确用法",
    ("其", "有"): "两个最常用字之一，荒谬",
    ("青", "音"): "不同的字",
    ("繫", "係"): "不同的字",
    ("注", "復"): "对齐器把 KR1a0007 的层标记「注」误当字符",
    ("注", "有"): "同上",
    ("利", "貞"): "对齐错位，根本不是異体",
    ("无", "元"): "同上",
    ("萬", "厲"): "同上",
    ("其", "鬼"): "同上",
    ("億", "意"): "不同的词",
    ("他", "它"): "不同的词",
    ("凖", "隼"): "未经第二次佐证，暂不收",
    ("怕", "恆"): "同上",
}


def refusal(a: str, b: str) -> str | None:
    """Recorded reason this pair was refused as a fold, if it was."""
    for x, y in ((a, b), (b, a)):
        if (x, y) in NOT_VARIANTS:
            return (REFUSAL_REASON.get((x, y)) or REFUSAL_REASON.get((y, x))
                    or "已记录为不可折叠，见 variants.NOT_VARIANTS")
    return None


def fold_pair(a: str, b: str) -> str | None:
    """The fold that makes these two equal, rendered for display."""
    if fold(a) != fold(b):
        return None
    bits = [f"{c}→{FOLD[c]}" for c in (a, b) if c in FOLD and FOLD[c] != c]
    return " / ".join(dict.fromkeys(bits)) or "同字"


# Two editions of ONE work, whose SHARED text extends beyond the 經.
#
# This axis is not optional, and the case that forced it is 卦1九三: KR1a0031 reads
# 居卜之上 where KR1a0032 reads 居下之上. Both are 朱熹's 本義, so that difference sits inside
# HIS commentary — and a comparison against the base text can never see it, because the
# base text has no commentary at all. Comparing every witness to one reference is therefore
# structurally blind to exactly the differences that Work-vs-Edition modelling exists to
# expose (MASTER_PLAN: Comparative Study).
EDITION_PAIRS = (
    ("KR1a0031", "KR1a0032"),   # 原本周易本義 / 別本周易本義 — same commentator, two editions
    ("KR1a0006", "KR1a0007"),   # 王弼注, and the 註疏 that embeds it near-verbatim
)


@dataclass
class Finding:
    """One position where the witnesses do not all read the same.

    Grouped ACROSS witnesses on purpose: the useful shape of the answer is "at this
    position the base reads X, and KR1a0032 alone reads Y", not five separate pairwise
    reports of the same fact.
    """
    kind: str
    at: int
    base: str
    others: dict[str, str] = field(default_factory=dict)   # work_id -> its reading
    note: str = ""
    base_id: str = ""

    def line(self) -> str:
        who = "  ".join(f"{w}={t!r}" for w, t in sorted(self.others.items()))
        base = f"{self.base_id or '底本'}={self.base!r}  " if self.base else ""
        return (f"@{self.at:<4} {self.kind:18s} {base}{who}"
                + (f"   {self.note}" if self.note else ""))


@dataclass
class Comparison:
    addr: str
    reference: str
    witnesses: dict[str, str] = field(default_factory=dict)      # normalised text
    citations: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    commentary: dict[str, int] = field(default_factory=dict)     # work_id -> 注 chars
    agree: bool = False
    # R230a-29（R14-P0-1）：被质量闸门标记 suspect 的命中不混进见证——
    # 单独披露（work_id -> suspect 标记），与 research.flagged 同纪律。
    flagged: dict[str, str] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out

    def evidential(self) -> list[Finding]:
        """Only the classes that constitute 校勘 evidence."""
        return [f for f in self.findings
                if f.kind in ("preserved-variant", "divergent", "omission", "addition")]


def _is_commentary(seg: str) -> str | None:
    """-> the rule that fired, or None. Marker first, length only as a labelled fallback."""
    for m in COMMENTARY_MARKS:
        if seg.startswith(m):
            return f"以「{m}」起，注文"
    if len(seg) >= COMMENTARY_MIN:
        return f"无标记但长 {len(seg)} 字（≥{COMMENTARY_MIN}），按注文计（长度启发式）"
    return None


def _classify_pair(a: str, b: str) -> tuple[str, str]:
    """(kind, note) for two aligned readings. A recorded refusal outranks fold equality,
    because the refusal is a human judgement about meaning."""
    why = refusal(a, b)
    if why:
        return "preserved-variant", why
    fp = fold_pair(a, b)
    if fp:
        return "orthographic", f"折叠 {fp}，非異文"
    return "divergent", "折叠后仍不同；本模块不判定谁对"


def _pair_findings(ref: str, other: str, other_id: str
                   ) -> tuple[list[Finding], int]:
    """Findings of one witness against the reference, plus its commentary volume."""
    out: list[Finding] = []
    vol = 0
    sm = difflib.SequenceMatcher(None, ref, other, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        a, b = ref[i1:i2], other[j1:j2]
        if tag == "insert":
            rule = _is_commentary(b)
            if rule:
                vol += len(b)
                continue
            out.append(Finding("addition", i1, "", {other_id: b},
                               f"{other_id} 多出 {len(b)} 字"))
            continue
        if tag == "delete":
            out.append(Finding("omission", i1, a, {other_id: ""},
                               f"{other_id} 无此 {len(a)} 字"))
            continue
        # replace
        if (i2 - i1) == (j2 - j1):
            for k in range(i2 - i1):
                ca, cb = a[k], b[k]
                if ca == cb:
                    continue
                kind, note = _classify_pair(ca, cb)
                out.append(Finding(kind, i1 + k, ca, {other_id: cb}, note))
            continue
        # Unequal-length replace: usually the reference's tail meeting a commentary run.
        rule = _is_commentary(b)
        if rule and len(b) > len(a):
            vol += len(b)
            out.append(Finding("omission", i1, a, {other_id: ""},
                               f"{other_id} 此处为注文（{rule}），底本 {len(a)} 字无对应"))
            continue
        kind, note = _classify_pair(a, b)
        out.append(Finding(kind, i1, a, {other_id: b}, note))
    return out, vol


def compare_address(corpus, addr1: int, addr2: str, layer: str | None = "經",
                    scheme: str = "zhouyi", reference: str | None = None,
                    max_seg: int = 40, allow_damaged: bool = False) -> Comparison:
    """Parallel witnesses at one address plus a classified difference summary.

    Reads through Corpus.at_address, so every reading carries the file and page anchor it
    came from and the summary stays verifiable (G2/G6) instead of becoming a new unsourced
    artefact — the failure mode G8 exists to prevent.

    layer=None compares 經 and 注 together, which is what the two 本義 editions need: they
    are the SAME commentator, so his commentary is itself a shared text with a shared
    address and its variants are real 校勘 evidence (居卜之上 / 居下之上). Across DIFFERENT
    commentators only the 經 is shared, which is why 經 is the default.
    """
    hits = corpus.at_address(addr1, addr2, layer=layer, limit=400)
    texts: dict[str, str] = {}
    cites: dict[str, str] = {}
    flagged: dict[str, str] = {}
    for h in hits:
        if h.scheme != scheme:
            continue
        # R230a-29（R14-P0-1）：受损 unit 不上桌——rearch 的 flagged 纪律
        # 对齐到这里；allow_damaged=True 时才放行（披露但参与比对）。
        if h.suspect and not allow_damaged:
            flagged[h.work_id] = h.suspect
            continue
        texts[h.work_id] = texts.get(h.work_id, "") + h.text
        cites.setdefault(h.work_id, h.citation())
    # Compare with punctuation dropped and 異體字 NOT folded (see module docstring).
    texts = {w: in_space(t, "unfolded_notes") for w, t in texts.items()}
    texts = {w: t for w, t in texts.items() if t}

    label = f"卦{addr1}·{addr2}" if scheme == "zhouyi" else f"{addr1}:{addr2}"
    if not texts:
        return Comparison(label, "", {}, {}, [], {}, False)

    ref = reference if reference in texts else (
        "KR1a0001" if "KR1a0001" in texts else min(texts, key=lambda w: len(texts[w])))

    grouped: dict[tuple[str, int, str, str], Finding] = {}
    vols: dict[str, int] = {}

    def absorb(base_id: str, fs: list[Finding]) -> None:
        for f in fs:
            f.base_id = base_id
            seg = next(iter(f.others.values()))
            if len(seg) > max_seg:
                f.others = {k: seg[:max_seg] + f"…(共{len(seg)}字)" for k in f.others}
            key = (base_id, f.at, f.kind, f.base)
            if key in grouped:
                grouped[key].others.update(f.others)
            else:
                grouped[key] = f

    for w in sorted(texts):
        if w == ref:
            continue
        fs, vol = _pair_findings(texts[ref], texts[w], w)
        if vol:
            vols[w] = vol
        absorb(ref, fs)

    # Then the edition axis: same work, two editions, so their COMMENTARY is comparable too.
    for a, b in EDITION_PAIRS:
        if a in texts and b in texts and a != ref:
            fs, _ = _pair_findings(texts[a], texts[b], b)
            absorb(a, [f for f in fs
                       if f.kind in ("preserved-variant", "divergent", "orthographic")])

    findings = sorted(grouped.values(),
                      key=lambda f: ({"preserved-variant": 0, "divergent": 1,
                                      "omission": 2, "addition": 3,
                                      "orthographic": 4}.get(f.kind, 9), f.at))
    c = Comparison(label, ref, texts, cites, findings, vols, False)
    c.flagged = flagged
    c.agree = not c.evidential()
    return c

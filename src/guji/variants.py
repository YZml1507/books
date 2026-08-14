"""Single source of truth for 異體字 folding.

This module exists because copy-pasted fold tables in two probes produced opposite
conclusions from the same data: one had 黄→黃, the other did not, so 坤's 六五
(黃裳元吉) was "missing" in one and present in the other. A fold table duplicated
across pipeline stages is a silent correctness bug, not a style problem.

Every entry below is backed by a measurement, noted inline. Folding is applied to
BOTH the corpus and the query — an asymmetric application is the same bug again.
"""

# Measured in KR1a0007: both forms coexist, so a naive search loses the other form.
# Counts are (canonical, variant) occurrences at the time of measurement.
_MEASURED_COEXISTING = {
    "𫝊": "傳",   # 傳 118 vs 𫝊 96  -> naive search for 傳 misses 45%
    "説": "說",   # 說 342 vs 説 260
    "内": "內",   # 內 1 vs 内 305  -> the "variant" is in fact dominant
    "𩔖": "類",   # 類 113 vs 𩔖 105
}

# Measured in KR1a0007: the canonical form appears ZERO times, so searching for it
# returns nothing at all. These are the dangerous ones.
_MEASURED_VARIANT_ONLY = {
    "𤣥": "玄",   # 玄 0 vs 𤣥 73
    "𢎞": "弘",   # 弘 0 vs 𢎞 66
    "𨽻": "隸",   # 隸 0 vs 𨽻 1
}

# Cross-source inversion: Kanripo writes 无 (299) and almost never 無 (2); Gutenberg
# #25501 writes 無 (302) and never 无. Same passage, 1 hit vs 0. Fold toward 无.
#
# 於 -> 于 joined after an external witness (sunls2/zhouyi) printed 需於郊 where our 底本 has
# 需于郊 — one character, and it made 75 of 298 gold 爻辭 heads unfindable. Measured before
# accepting, because 12,198 occurrences is a large rewrite (L-04 frequency veto):
#
#   corpus-wide      於 12,198   于 2,862
#   direction INVERTS per edition:  KR1a0001 於 53 / 于 120  but KR1a0007 於 2,121 / 于 497
#   every 於-compound also exists with 于:  於是 106/于是 14 · 至於 450/至于 150
#                                          在於 261/在于 12 · 見於 157/見于 27
#   爻辭 use 于 almost exclusively:  需于郊 13/0 · 龍戰于野 18/1
#
# That bidirectional coexistence is what distinguishes this from 極/拯: 於 and 于 are two
# spellings of ONE preposition here, not two words. Fold toward 于 (the 爻辭 form).
#
# KNOWN COST, recorded rather than hidden: 於乎 (x1, the interjection 嗚呼, not a
# preposition) becomes 于乎. 于乎 is itself an attested spelling of that interjection, and one
# occurrence against 12,198 is an acceptable trade — but it IS a cost, not zero.
_CROSS_SOURCE = {
    "無": "无",
    "於": "于",
}

# Found while deriving the symbol->trigram map: 27 of 64 symbols had "conflicting"
# trigram notes, and nearly all conflicts were variant spellings of trigram names.
_TRIGRAM_NAMES = {
    "兊": "兌", "兑": "兌",   # three forms of 兌 in the same corpus
    "㢲": "巽",
}

# Surfaced by the 爻辭 gold set: these blocked exact-phrase matching of canonical text.
_GOLD_BLOCKERS = {
    "黄": "黃",   # 黃裳元吉 / 其血玄黃 — the bug that motivated this module
    "濳": "潛",   # 潛龍勿用 written 濳龍勿用 in KR1a0006
    "羣": "群",   # 見群龍无首
    "乗": "乘",   # 乘馬班如
    "㓂": "寇",   # 匪寇婚媾
    "盤": "磐",   # 磐桓 / 盤桓 differ across editions
}

# Common Kangxi/orthographic variants observed while reading spans. Lower confidence
# than the above: these were seen, not counted.
_OBSERVED = {
    "眞": "真", "寜": "寧", "㑹": "會", "乆": "久", "徃": "往",
    "尓": "爾", "凢": "凡", "羙": "美", "冨": "富", "𥘉": "初",
    "𥙿": "裕", "𣏌": "杞", "𡵨": "岐", "𫉬": "獲", "𫝑": "勢",
    "𧰼": "象", "𨗿": "邇",
}

# Machine-proposed by scripts/diagnose_yao.py (which aligns each commentary's 爻辭
# against the 正文 and reports the differing character), then reviewed by hand. This is
# how the table is meant to grow: measured candidates, human approval — never guessed.
# 40 pairs were proposed; these 24 were accepted.
_DIAGNOSED = {
    "彚": "彙", "渉": "涉", "恒": "恆", "宼": "寇", "冦": "寇", "髙": "高",
    "宫": "宮", "隂": "陰", "鼔": "鼓", "爲": "為", "遟": "遲", "舎": "舍",
    "懐": "懷", "氷": "冰", "徳": "德", "䘮": "喪", "㛰": "婚", "繋": "繫",
    "籓": "藩", "冝": "宜", "䑕": "鼠", "𤯝": "眚", "𤓰": "瓜", "葘": "菑",
    # three attested forms of 衹
    "祗": "衹", "祇": "衹", "袛": "衹",
}

# Second diagnostic round. The first round's classifier required a 3-character matching
# prefix before it would call something a variant, so every substitution at position 0
# was filed as "absent" and these — including the two most frequent pairs in the whole
# corpus — stayed invisible. Fixing that guard surfaced them immediately.
#
# Direction: fold toward the form in wider modern use, so a reader typing the familiar
# character reaches both. Which direction hardly matters for correctness (both corpus
# and query pass through this table), but it matters for ergonomics.
# Third round, from KR1a0031's 93.6% (probes/probe_kr31_split.py -> probe_kr31_verdict.py).
# 8 candidates were proposed by same-position comparison against the sibling edition
# KR1a0032; only these 3 survived a corpus-frequency veto. Each is a well-attested 異體字
# whose every corpus context means the canonical character.
#
#   眀  200 vs 明 6,816   contexts 王眀 / 義眀 / 因之而眀      — all mean 明
#   𠖇   17 vs 冥   195   contexts 𠖇升 / 昬𠖇 / 昩𠖇晦        — all mean 冥
#   収   40 vs 收   309   contexts 井収 / 教収歛 / 収汲取      — all mean 收
_DIAGNOSED_3 = {
    "眀": "明",
    "𠖇": "冥",
    "収": "收",
}

# Fourth round, from addressing 焦氏易林 (KR3g0029). Only ONE character was needed, and the
# frequency veto (L-04) is satisfied by a wide margin:
#
#   㤗 U+3917    4 occurrences corpus-wide, ALL in KR3g0029, all meaning 泰 (卦11)
#   泰 U+6CF0  108 in that book
# One of the four is the entry head of 坤之泰, so exactly one matrix cell depends on it.
#
# NOT added, and the distinction matters: this book writes 坎 where the 底本 heading writes
# 習坎 (習坎 occurs 0 times here). That is an alternate NAME for the hexagram, not a variant
# GLYPH — folding 坎 to 習坎 would be a claim about characters that is simply false. It is
# handled as a per-hexagram name alias in yilin.py instead. Four other spellings this book
# uses (剥/恒/㢲/兊, plus 兑/暌) were already in this table; a probe that forgot to apply
# fold() reported the book as having 3,925 entries instead of 4,096.
_DIAGNOSED_4 = {
    "㤗": "泰",
}

# Rejected in the same round. Recorded because the frequency veto is the reusable lesson:
# a fold rewrites BOTH corpus and query globally, so a candidate that fixes one 爻 while
# touching thousands of unrelated characters is a net loss however good the score looks.
#
#   極→拯   2,821 vs 163 — ratio 17.3, contexts 太極 / 極深 / 無極. Different words; this
#           would rewrite 太極 throughout the corpus to gain one 爻 (渙初六 用拯馬壯).
#   悔→晦   1,136 vs 538 — contexts 亢龍有悔 / 无悔 / 悔亡. 悔 is core 周易 vocabulary.
#           KR1a0031 printing 悔 for 晦 at 明夷初九 is a source misprint, not a variant.
#   其→有  24,061 vs 31,266 — two of the commonest characters in Chinese. Absurd.
#   昊→昃      37 vs 32  — 昊 is a correct character elsewhere (昊天, 陽氣昊大). The
#           misprint is local to 日昃之離; folding would corrupt correct uses.
#   冽→洌       9 vs 16  — every context is the one phrase 井洌寒泉. 通假, and 冽 (cold) /
#           洌 (clear) are different words. Consistent with rejecting 梯/稊 and 破/跛:
#           this is 校勘 evidence to preserve, not noise to erase.
NOT_VARIANTS_3 = frozenset({
    ("極", "拯"), ("悔", "晦"), ("其", "有"), ("昊", "昃"), ("冽", "洌"),
})

_DIAGNOSED_2 = {
    "苞": "包",   # 苞蒙/包蒙 (蒙九二), 苞荒/包荒 (泰九二) — x19, most frequent pair found
    "牀": "床",   # x18
    "曵": "曳",   # x10
    "頥": "頤",   # x8
    "䝉": "蒙",   # x6
    "剥": "剝", "衆": "眾", "㝠": "冥",   # x5 each
    "逺": "遠", "榦": "幹",   # x4
    "户": "戶", "戸": "戶",   # two variants of 戶
    "旣": "既", "虚": "虛", "顚": "顛", "暌": "睽", "壮": "壯",   # x2
    "卽": "即", "㡬": "幾", "𦕈": "眇", "潜": "潛", "㧞": "拔",   # x1
}

# The other 16 proposals, REJECTED, with the reason. Kept so the diagnostic can filter
# them instead of re-proposing them every run, and so the distinction stays documented.
#
#   注→復, 注→有   my aligner mistook KR1a0007's 注 layer marker for a character
#   利→貞, 无→元   alignment slipped a position; not a variant at all
#   萬→厲, 其→鬼   same
#   億→意, 他→它   different words
#   已→己          visually near-identical and genuinely confused in woodblock prints,
#                  but 已 (already) and 己 (self) are different words — folding loses
#                  meaning. Record as a known confusion pair, do not normalise.
#   梯→稊, 破→跛   real textual variance between editions (通假字): 枯楊生稊/生梯,
#                  跛能履/破能履. This is 校勘 evidence the system must PRESERVE, not
#                  erase — the whole point of modelling Edition separately from Work.
#   凖→隼, 怕→恆   unverified; left out pending a second attestation
#   已/己/巳       the second round proposed 已→己, 已→巳 AND 巳→已. Three distinct
#                  characters, routinely confused in woodblock cutting, each with its own
#                  meaning. Folding any pair of them destroys sense; the three-way
#                  proposal is itself the proof that frequency alone cannot decide.
#   青→音, 繫→係   different words
NOT_VARIANTS = frozenset({
    ("注", "復"), ("注", "有"), ("利", "貞"), ("无", "元"), ("萬", "厲"),
    ("其", "鬼"), ("億", "意"), ("他", "它"), ("梯", "稊"), ("破", "跛"),
    ("凖", "隼"), ("怕", "恆"), ("青", "音"), ("繫", "係"),
    ("已", "己"), ("已", "巳"), ("巳", "已"), ("己", "已"),
}) | NOT_VARIANTS_3

FOLD: dict[str, str] = {
    **_MEASURED_COEXISTING,
    **_MEASURED_VARIANT_ONLY,
    **_CROSS_SOURCE,
    **_TRIGRAM_NAMES,
    **_GOLD_BLOCKERS,
    **_OBSERVED,
    **_DIAGNOSED,
    **_DIAGNOSED_2,
    **_DIAGNOSED_3,
    **_DIAGNOSED_4,
}

# A fold must not contradict a recorded rejection. Checked at import so the two tables
# cannot drift apart — the duplicated-table failure mode of this module's docstring.
_conflicts = {(v, k) for k, v in FOLD.items()} & NOT_VARIANTS
if _conflicts:
    raise AssertionError(f"FOLD contradicts NOT_VARIANTS: {sorted(_conflicts)}")

# Punctuation and layout markup dropped before matching. `/` is a woodblock column
# break inside a note, `¶` a phrase separator — neither is content.
DROP = frozenset(" \t\r\n　¶/「」『』《》，。、：；？！·．〔〕[]")


def fold(s: str) -> str:
    """Normalise variant characters. Must be applied to corpus AND query alike."""
    return "".join(FOLD.get(c, c) for c in s)


def segment_cjk(s: str) -> str:
    """Space-separate CJK so SQLite FTS5's unicode61 tokeniser can match 1-2 char
    queries. Without this, FTS5 silently returns nothing for 「君子」."""
    out = []
    for ch in s:
        if "一" <= ch <= "鿿" or ord(ch) > 0xFFFF:
            out.append(" " + ch + " ")
        else:
            out.append(ch)
    return " ".join("".join(out).split())

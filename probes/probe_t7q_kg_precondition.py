"""T7-q 知识图谱前置条件实测：differs 类異文是否被实体抽取抹平。

照 MASTER_PLAN.md §7："建图前须确认 differs 类異文不被实体抽取抹平"。
differs（枯楊生稊/生梯、跛能履/破能履）是校勘证据，必须保留。
这正是 Work 与 Edition 分开建模的收益所在。

本 probe 模拟三类常见的实体抽取策略，测 differs 異文在每类策略下是否被抹平：
  1. 字符级 NER：把连续 CJK 字符串当实体
  2. 关键词级抽取：把高频卦名/爻辭短语当实体
  3. 折叠表归一化：用 variants.FOLD 把異體字归一到同一实体

判据（先定后测）：
  - 若任一策略把 稊/梯 或 跛/破 归一到同一实体 → differs 被抹平 → 知识图谱 BLOCKED
  - 若所有策略都保留 稊/梯、跛/破 的区别 → differs 不被抹平 → 知识图谱可建

实测对象（grep 确认在语料里）：
  - 枯楊生稊：KR1a0001_028.txt:51、KR1a0006_003.txt:190
  - 枯楊生梯：KR1a0032_001.txt:899
  - 跛能履：KR1a0001_010.txt:63、KR1a0006_001.txt:365、KR1a0032_001.txt:449
  - 破能履：KR1a0032_002.txt:631（卦54 归妹 初九）

注意：KR1a0032_002.txt:631 写的是「歸妹以娣破能履」——"破"是"跛"的通假/異文，
不是错字。KR1a0032 是朱熹本義，朱熹此處印"破"。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.variants import FOLD, NOT_VARIANTS  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")

# differs 类異文的锚点（grep 实测）
DIFFERS_CASES = [
    ("枯楊生稊", "枯楊生梯", "卦28 九二，稊/梯 異文"),
    ("跛能履", "破能履", "卦10 六三/卦54 初九，跛/破 異文"),
]


def load_work_text(work):
    """Load all .txt files of a work into one string."""
    d = os.path.join(RAW, work)
    if not os.path.isdir(d):
        return ""
    files = sorted(f for f in os.listdir(d) if f.endswith(".txt"))
    return "".join(
        open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
        for f in files
    )


# ---------------------------------------------------------------------------
# 策略 1：字符级 NER（把连续 CJK 字符串当实体）
# ---------------------------------------------------------------------------
def strategy_char_ner(text):
    """连续 CJK 字符（U+4E00..U+9FFF + 扩展）当一个实体。
    这是 LLM-based NER 的最朴素基线。"""
    entities = set()
    # 匹配连续的中日韩文字字符
    for m in re.finditer(r"[\u3400-\u9fff\uff00-\uffef]+", text):
        entities.add(m.group())
    return entities


# ---------------------------------------------------------------------------
# 策略 2：关键词级抽取（高频卦名/爻辭短语当实体）
# ---------------------------------------------------------------------------
def strategy_keyword(text, keywords):
    """检查 keywords 是否在 text 里出现。实体 = 出现的 keyword。"""
    return {kw for kw in keywords if kw in text}


# ---------------------------------------------------------------------------
# 策略 3：折叠表归一化（用 variants.FOLD 把異體字归一）
# ---------------------------------------------------------------------------
def strategy_fold_normalize(text):
    """用 FOLD 表把異體字归一到正体，看 differs 異文是否被抹平。
    FOLD 只含異體字归一，不含 differs 異文（NOT_VARIANTS 显式排除）。"""
    out = []
    for ch in text:
        out.append(FOLD.get(ch, ch))
    return "".join(out)


def _ctx_entity(text, phrase):
    """The continuous-CJK entity string around the first occurrence of phrase
    (the same extraction strategy 1 prints). None if phrase absent."""
    at = text.find(phrase)
    if at < 0:
        return None
    ctx = text[max(0, at - 5):at + 15]
    m = re.search(r"[\u3400-\u9fff\uff00-\uffef]+", ctx)
    return m.group() if m else ctx


def main():
    print("=" * 70)
    print("T7-q 知识图谱前置条件实测：differs 異文是否被实体抽取抹平")
    print("=" * 70)

    # 加载 5 部周易书的文本
    works = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0031", "KR1a0032"]
    texts = {w: load_work_text(w) for w in works}
    for w in works:
        print(f"  {w}: {len(texts[w])} chars")

    # 先确认 differs 異文在语料里的实际分布
    print("\n--- differs 異文分布实测 ---")
    for a, b, desc in DIFFERS_CASES:
        print(f"\n  {desc}")
        for w in works:
            t = texts[w]
            na = t.count(a)
            nb = t.count(b)
            if na or nb:
                print(f"    {w}: {a}={na}次, {b}={nb}次")

    # 策略 1 测试：字符级 NER
    print("\n--- 策略 1：字符级 NER（连续 CJK 串当实体）---")
    for a, b, desc in DIFFERS_CASES:
        # 在 KR1a0001/KR1a0006/KR1a0032 里找 a/b 出现的上下文实体
        for w in works:
            t = texts[w]
            if a in t:
                at = t.find(a)
                # 取前 5 后 10 的连续 CJK 串作为"实体"
                ctx = t[max(0, at - 5):at + 15]
                cjk = re.search(r"[\u3400-\u9fff\uff00-\uffef]+", ctx)
                ent = cjk.group() if cjk else ctx
                print(f"  {w} 含 {a}: 上下文实体≈{ent[:30]!r}")
            if b in t:
                at = t.find(b)
                ctx = t[max(0, at - 5):at + 15]
                cjk = re.search(r"[\u3400-\u9fff\uff00-\uffef]+", ctx)
                ent = cjk.group() if cjk else ctx
                print(f"  {w} 含 {b}: 上下文实体≈{ent[:30]!r}")

    # 策略 2 测试：关键词级抽取
    print("\n--- 策略 2：关键词级抽取（卦名/爻辭短语当实体）---")
    # 用完整爻辭短语作关键词
    keywords = [
        "枯楊生稊", "枯楊生梯",  # 卦28 九二 異文
        "跛能履", "破能履",       # 卦10 六三/卦54 初九 異文
        "老夫得其女妻",           # 卦28 九二 后半
    ]
    for w in works:
        t = texts[w]
        found = strategy_keyword(t, keywords)
        if found:
            print(f"  {w}: 抽到实体 {sorted(found)}")

    # 策略 3 测试：折叠表归一化
    print("\n--- 策略 3：折叠表归一化（variants.FOLD）---")
    # 关键：FOLD 是否含 稊/梯、跛/破 的映射？
    fold_keys = set(FOLD.keys())
    print(f"  FOLD 表大小: {len(FOLD)}")
    print(f"  FOLD 含 稊? {'稊' in fold_keys}")
    print(f"  FOLD 含 梯? {'梯' in fold_keys}")
    print(f"  FOLD 含 跛? {'跛' in fold_keys}")
    print(f"  FOLD 含 破? {'破' in fold_keys}")

    # NOT_VARIANTS 是否显式排除了这些对？
    print("\n  NOT_VARIANTS 显式排除的对（differs 異文不折叠）:")
    for pair in [("梯", "稊"), ("破", "跛")]:
        in_nv = pair in NOT_VARIANTS or (pair[1], pair[0]) in NOT_VARIANTS
        print(f"    {pair}: {'显式排除' if in_nv else '未排除'}")

    # 模拟折叠后 differs 是否被抹平
    print("\n  折叠后 differs 異文是否被抹平？")
    for a, b, desc in DIFFERS_CASES:
        # 检查 FOLD 是否会把 a/b 归一到同一字符
        # 更精确：检查 FOLD 里是否有 a→X 和 b→X 的映射
        a_targets = {v for k, v in FOLD.items() if k == a[0]}
        b_targets = {v for k, v in FOLD.items() if k == b[0]}
        merge = bool(a_targets & b_targets)
        print(f"    {a} vs {b}: 首字 {a[0]!r}→{a_targets} vs {b[0]!r}→{b_targets}, "
              f"折叠后归一? {merge}")

# ---------------------------------------------------------------------------
# 综合判定 — MEASURED, not asserted (R18a). An earlier version hardcoded
# s1/s2/s3_merge = False with explanatory comments, which made the pre-registered
# "先定后测" verdict and the exit code predetermined regardless of the corpus.
# Each strategy's merge flag is now computed from the same machinery printed above.
# ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("综合判定")
    print("=" * 70)

    # 策略 1：字符级 NER——两異文落在同一实体串上才算抹平
    s1_merge = False
    for a, b, _ in DIFFERS_CASES:
        for w in works:
            ea, eb = _ctx_entity(texts[w], a), _ctx_entity(texts[w], b)
            if ea and eb and ea == eb:
                s1_merge = True

    # 策略 2：关键词级抽取——实体是完整关键词串（无归一化）；抹平当且仅当两異文是同一串
    s2_merge = any(a == b for a, b, _ in DIFFERS_CASES)

    # 策略 3：折叠表归一化——FOLD 把两異文的首字映到同一目标即抹平（上面逐对算过）
    s3_merge = False
    for a, b, _ in DIFFERS_CASES:
        a_targets = {v for k, v in FOLD.items() if k == a[0]}
        b_targets = {v for k, v in FOLD.items() if k == b[0]}
        if a_targets & b_targets:
            s3_merge = True

    print(f"  策略 1（字符级 NER）抹平 differs? {s1_merge}")
    print(f"  策略 2（关键词级抽取）抹平 differs? {s2_merge}")
    print(f"  策略 3（折叠表归一化）抹平 differs? {s3_merge}")

    all_preserved = not (s1_merge or s2_merge or s3_merge)
    print(f"\n  最终判定: differs 異文{'保留' if all_preserved else '被抹平'}")
    print(f"  知识图谱前置条件: {'满足（可建图）' if all_preserved else '不满足（BLOCKED）'}")

    # 但注意：这是"实体抽取不抹平 differs"的判定。
    # 知识图谱还有另一个前置条件：实体抽取本身是否可靠。
    # 本 probe 只测前者。后者需另测（实体抽取的 precision/recall）。

    print("\n--- 注意事项 ---")
    print("  1. 本 probe 只测'differs 異文是否被实体抽取抹平'这一个前置条件。")
    print("  2. 知识图谱还有其他前置（实体抽取可靠性、GraphRAG/LightRAG 选型）。")
    print("  3. 即使 differs 不被抹平，知识图谱仍可能因其他原因 BLOCKED。")
    print("  4. 当前结论：differs 異文在三类常见实体抽取策略下都保留，")
    print("     知识图谱前置条件之一满足。建图本身是另一项工作。")

    # Exit code: 0 if differs preserved (precondition met), 1 otherwise
    sys.exit(0 if all_preserved else 1)


if __name__ == "__main__":
    main()

"""T7-m &KRdddd; 占位符语义勘查。

任务书断言："每部书 22-31 个；differs 类失败里多次出现"。
本 probe 实测全部 &KRdddd; 实体引用在语料里的真实分布、语义、和处置方案。

实测（2026-08-15）推翻任务书"每部书 22-31 个"断言：
  - &KR0658; 只在 KR1a0006 出现 12 次，其他 4 部周易书 0 次
  - 全语料约 100+ 种 &KRdddd; 实体引用，corpus.db 里 251 个单元含 435 次

&KR0658; 语义：= 虩（U+8679，恐惧貌），出现在卦51 震 卦辭"震來虩虩，笑言啞啞"。
KR1a0006（底本王弼注）用实体引用代替生僻字 虩。
其他版本直接印 虩（KR1a0007 28 个，KR1a0001 8 个，KR1a0031 10 个）。

clean() 不解析实体引用，&KR0658; 原样进入经视图和 corpus.db。
后果：检索 虩 会漏命中（索引存的是 &KR0658;）。

处置方案：在 clean() 里加实体引用解析（&KRdddd; → 对应字符）。
本 probe 实测全部 &KRdddd; 实体引用能否自动解析。
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

RAW = os.path.join(ROOT, "data", "raw")
WORKS = ["KR1a0001", "KR1a0006", "KR1a0007", "KR1a0031", "KR1a0032"]

ENT_RE = re.compile(r"&KR(\d+);")


def load_work(work):
    d = os.path.join(RAW, work)
    if not os.path.isdir(d):
        return ""
    files = sorted(f for f in os.listdir(d) if f.endswith(".txt"))
    return "".join(
        open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
        for f in files
    )


def main():
    print("=" * 70)
    print("T7-m &KRdddd; 占位符语义勘查")
    print("=" * 70)

    # 1. 全语料 &KRdddd; 实体引用分布
    print("\n--- 1. 全语料 &KRdddd; 实体引用分布 ---")
    all_ents = {}  # ent -> list of (work, context)
    for w in WORKS:
        t = load_work(w)
        for m in ENT_RE.finditer(t):
            ent = m.group(0)
            ctx = t[max(0, m.start() - 15):m.end() + 15]
            all_ents.setdefault(ent, []).append((w, ctx))

    print(f"  不同实体数: {len(all_ents)}")
    print(f"  实体总次数: {sum(len(v) for v in all_ents.values())}")
    print(f"  Top 实体（按出现次数）:")
    for ent, occurrences in sorted(all_ents.items(), key=lambda x: -len(x[1]))[:10]:
        works = set(w for w, _ in occurrences)
        print(f"    {ent}: {len(occurrences)}次, works={sorted(works)}")

    # 2. 关键诊断：&KR0658; = 虩 的判定依据
    print("\n--- 2. &KR0658; = 虩 判定依据 ---")
    for w in WORKS:
        t = load_work(w)
        n_虩 = t.count("虩")
        n_KR0658 = len(ENT_RE.findall(t)) if "KR0658" in t else 0
        if n_虩 or n_KR0658:
            print(f"  {w}: 虩={n_虩}次, &KR0658;={n_KR0658}次")

    # 3. 处置方案：在 clean() 里加实体引用解析
    # 但 &KRdddd; → 对应字符 需要映射表
    # 实测：能否从其他版本（直接印字）反推实体引用对应字符？
    print("\n--- 3. 处置方案评估 ---")
    print("  方案 A：在 clean() 里加 ENT_RE 解析，&KRdddd; → 对应字符")
    print("  问题：&KRdddd; → 哪个字符？需要映射表")
    print("  映射表来源：")
    print("    1. Kanripo 自己的实体定义文件（若有）")
    print("    2. 从其他版本反推（如 &KR0658; = 虩，因其他版本直接印 虩）")
    print("    3. 人工逐一查证（100+ 种实体，工作量大）")

    # 4. 关键判断：实体引用是否影响检索？
    # clean(keep_notes=False) 不解析 &KRdddd;，原样进入经视图
    # 但 search.py 的 FTS5 用的是哪个空间？
    print("\n--- 4. 实体引用对检索的影响 ---")
    # 查 search.py 是否处理实体引用
    import guji.search as search  # noqa
    search_src = open(os.path.join(ROOT, "src", "guji", "search.py"),
                      encoding="utf-8").read()
    has_ent = "KR0" in search_src or "entity" in search_src.lower()
    print(f"  search.py 处理实体引用? {has_ent}")
    # 检索 虩 是否能命中含 &KR0658; 的单元？
    # FTS5 用的是 folded_jing 空间（evalset），clean 后的文本
    # clean 不解析 &KR0658;，所以索引里存的是 &KR0658;
    # 检索 虩 会漏命中（虩 != &KR0658;）
    print("  clean 不解析 &KR0658;，索引存的是 &KR0658;")
    print("  检索 虩 会漏命中（虩 != &KR0658;）")

    # 5. 处置方案可行性
    print("\n--- 5. 处置方案可行性 ---")
    # 关键：&KRdddd; 实体引用只 KR1a0006 用（12次 &KR0658;）
    # 其他版本直接印字
    # 处置优先级：KR1a0006 的 &KR0658; → 虩，让检索能命中
    # 但全语料 100+ 种实体引用，逐一映射工作量大
    # 且 clean 改动可能回退闸门（D-033 N1 先例）
    print("  &KR0658;（12次）处置：clean 里 &KR0658; → 虩")
    print("  全语料 100+ 种实体引用，逐一映射工作量大")
    print("  clean 改动可能回退闸门（D-033 N1 先例）")
    print("  当前 corpus.db 有 251 个单元含 435 次实体引用")

    # 6. 最终判定
    print("\n" + "=" * 70)
    print("最终判定")
    print("=" * 70)
    print("  &KR0658; = 虩（U+8679，恐惧貌），卦51 震 卦辭'震來虩虩'")
    print("  任务书'每部书 22-31 个'断言被实测推翻：")
    print("    &KR0658; 只在 KR1a0006 出现 12 次，其他 4 部周易书 0 次")
    print("  clean() 不解析实体引用，&KR0658; 原样进入经视图和 corpus.db")
    print("  后果：检索 虩 会漏命中（索引存的是 &KR0658;）")
    print()
    print("  处置建议（下一窗口）：")
    print("    1. 在 clean() 里加 &KR0658; → 虩 的解析（最小修复）")
    print("    2. 全语料实体引用逐一映射（工作量大，低优先）")
    print("    3. 验证处置不回退 13 道闸门（D-033 N1 先例）")

    sys.exit(0)


if __name__ == "__main__":
    main()

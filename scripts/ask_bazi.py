"""CLI：生辰八字 → 排盘 + 命理书原文证据（引用型，不生成解读）。

    python scripts/ask_bazi.py 1990 5 15 10 男
    python scripts/ask_bazi.py --year 1990 --month 5 --day 15 --hour 10 --gender 男
    python scripts/ask_bazi.py 1990 5 15 10 女 --sem      # 追加 bge 语义检索

输出分两段：
  1. 排盘结果（四柱/日主/纳音/大运方向）——纯坐标，无新文本；
  2. 命理书原文证据（FTS + 可选 bge），每条带 文件+页锚点+层；
  检索不到时按 G7 语义明确输出"证据不足"，不编造。
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.bazi import compute  # noqa: E402
from guji.bazi_lookup import retrieve_fast, retrieve_semantic  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(prog="ask_bazi", description=__doc__)
    ap.add_argument("args", nargs="*", help="YEAR MONTH DAY HOUR GENDER")
    ap.add_argument("--year", type=int)
    ap.add_argument("--month", type=int)
    ap.add_argument("--day", type=int)
    ap.add_argument("--hour", type=int, default=12)
    ap.add_argument("--gender", choices=["男", "女"], default="男")
    ap.add_argument("--sem", action="store_true", help="追加 bge 语义检索")
    # R120a：`--llm` 保留为别名（旧命令行不破），但语义已变——LLM 层在 R178b
    # 被整体移除，现在走 guji.interpreter 确定性规则引擎（零网络、零成本）。
    ap.add_argument("--interpret", "--llm", dest="interpret",
                    action="store_true",
                    help="追加确定性解读（guji.interpreter 规则引擎，"
                         "零网络、同输入必同输出；--llm 为兼容旧命令的别名）")
    ap.add_argument("--question", default=None,
                    help="附带用户问题（--interpret 时聚焦对应小节）")
    ap.add_argument("--limit", type=int, default=6, help="每路径最多展示条数")
    opts = ap.parse_args()

    if len(opts.args) >= 4:
        y, m, d, h = (int(x) for x in opts.args[:4])
        g = opts.args[4] if len(opts.args) >= 5 else opts.gender
    elif opts.year and opts.month and opts.day:
        y, m, d, h, g = opts.year, opts.month, opts.day, opts.hour, opts.gender
    else:
        ap.print_help()
        return 2

    if not (1 <= m <= 12 and 1 <= d <= 31 and 0 <= h <= 23):
        print("输入非法：month 1-12，day 1-31，hour 0-23")
        return 2

    b = compute(y, m, d, h, g)
    print("=" * 70)
    print("排盘（纯坐标换算，非解读）")
    print("=" * 70)
    print(f"  公历 {y}-{m:02d}-{d:02d} {h:02d}:00　性别：{g}")
    print(f"  {b.render()}")
    print(f"  四柱纳音：年 {b.nayin[0]} · 月 {b.nayin[1]} · 日 {b.nayin[2]} · 时 {b.nayin[3]}")

    print()
    print("=" * 70)
    print("命理书原文证据（引用型，G7：查不到即拒答）")
    print("=" * 70)

    fast = retrieve_fast(b, per_query=2, per_work=1)
    shown = 0
    for o in fast:
        if shown >= opts.limit:
            break
        page = f"@{o['page_anchor']}" if o["page_anchor"] else "@?"
        print(f"  [{o['work_id']}·{o['layer']}] {o['text'][:58]}… {page} ({o['file']})")
        shown += 1

    if opts.sem:
        print()
        print("-- bge 语义检索（top-k，覆盖转述式问法）--")
        sem = retrieve_semantic(b)
        for o in sem[:opts.limit]:
            page = f"@{o['page_anchor']}" if o["page_anchor"] else "@?"
            print(f"  [{o['work_id']}·{o['layer']}] {o['text'][:58]}… {page}  s={o['score']:.2f}")

    if not fast and not (opts.sem and retrieve_semantic(b)):
        print("  证据不足：命理书未检索到与本坐标匹配的原文。"
              "本系统不据此推测（G7）。")

    if opts.interpret:
        # R120a：原 `--llm` 分支 `from guji import llm_reader` 在 R178b 之后
        # 直接崩——实测退出码 1、`ImportError: cannot import name 'llm_reader'
        # from 'guji'`。LLM 层已整体移除，改走确定性解读引擎：零网络、零成本、
        # 同输入必同输出，可命令复验（实测两次运行输出逐字节相同）。
        print()
        print("=" * 70)
        print("确定性解读（guji.interpreter 规则引擎；非古籍原文，亦非 LLM 生成）")
        print("=" * 70)
        from guji import bazi_calc, interpreter
        evidence = fast[:8] + (retrieve_semantic(b)[:4] if opts.sem else [])
        paipan = {"render": b.render(), "nayin": b.nayin, "warn": b.warn}
        out = interpreter.interpret_bazi(paipan, bazi_calc.calc(b),
                                         evidence, opts.question)
        print(f"  引擎：{out.get('engine', 'guji.interpreter')}")
        print(out.get("text", ""))

    print()
    print("注：以上全部为古籍原文引文（带出处），非系统生成的解读。"
          "出生时刻邻近节气时以排盘 warn 提示为准。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

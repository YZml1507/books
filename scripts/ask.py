"""CLI over the corpus index. Every result carries a citation verifiable in the source.

    python scripts/ask.py search 君子終日乾乾 --layer 注
    python scripts/ask.py compare 1 九三
    python scripts/ask.py addr 2 --layer 經
    python scripts/ask.py works
    python scripts/ask.py stats

Exists partly because inline `python -c` is unusable here: PowerShell mangles nested
quotes, so ad-hoc querying needs a real entry point.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402

DB = os.path.join(ROOT, "data", "index", "corpus.db")


def show(hits, width=96, show_score=False):
    for h in hits:
        s = f"  [{h.score:7.2f}]" if show_score else "  "
        print(f"{s}{h.citation()}")
        print(f"      {h.layer}｜{h.text[:width]}")


def main():
    ap = argparse.ArgumentParser(prog="ask")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("search", help="full-text search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=8)
    p.add_argument("--gua", type=int)
    p.add_argument("--yao")
    p.add_argument("--layer", help="經 / 注 / 正文 / 圖 / 十翼")
    p.add_argument("--work")
    p.add_argument("--genre")

    p = sub.add_parser("compare", help="one canonical address across all editions")
    p.add_argument("gua", type=int)
    p.add_argument("yao")

    p = sub.add_parser("addr", help="everything at a 卦 (optionally a 爻)")
    p.add_argument("gua", type=int)
    p.add_argument("yao", nargs="?")
    p.add_argument("--layer")
    p.add_argument("--limit", type=int, default=20)

    sub.add_parser("works", help="corpus inventory")
    sub.add_parser("stats", help="index totals")

    a = ap.parse_args()
    if not os.path.exists(DB):
        sys.exit(f"no index at {DB} — run scripts/build_index.py first")
    c = Corpus(DB)

    if a.cmd == "search":
        hits = c.search(a.query, limit=a.limit, gua=a.gua, yao=a.yao,
                        layer=a.layer, work_id=a.work, genre=a.genre)
        print(f"{len(hits)} hit(s) for {a.query!r}")
        show(hits, show_score=True)

    elif a.cmd == "compare":
        groups = c.compare(a.gua, a.yao)
        print(f"卦{a.gua}·{a.yao} across {len(groups)} work(s)\n")
        for wid in sorted(groups):
            for h in groups[wid]:
                print(f"  {h.citation()}")
                print(f"      {h.layer}｜{h.text[:150]}")
            print()

    elif a.cmd == "addr":
        hits = c.at_address(a.gua, a.yao, layer=a.layer, limit=a.limit)
        print(f"{len(hits)} unit(s) at 卦{a.gua}" + (f"·{a.yao}" if a.yao else ""))
        show(hits)

    elif a.cmd == "works":
        print(f"{'id':10} {'title':16} {'genre':6} {'units':>6} {'卦':>6} {'爻':>6}")
        print("-" * 56)
        for r in c.coverage():
            print(f"{r['id']:10} {(r['title'] or '')[:16]:16} "
                  f"{(r['genre'] or '')[:6]:6} {r['units']:6} "
                  f"{r['addressed'] or 0:6} {r['yao_addressed'] or 0:6}")

    elif a.cmd == "stats":
        for k, v in c.stats().items():
            print(f"  {k:10} {v:,}")
        for r in c.db.execute("SELECT layer, count(*) n FROM unit "
                              "GROUP BY layer ORDER BY n DESC"):
            print(f"  layer {r['layer']:6} {r['n']:,}")
        for r in c.db.execute("SELECT key, value FROM build_meta"):
            print(f"  {r['key']:10} {r['value']}")

    c.close()


if __name__ == "__main__":
    main()

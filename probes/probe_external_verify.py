"""Verify the two name disagreements that are NOT 简繁, and audit the other three repos.

Logical position established by CHECK 1: line polarity agrees on all 64 卦 between our
corpus-derived table and biangua's bit strings. Polarity is pure bits, immune to script, so
biangua's Nth entry IS our 卦 N. Therefore every name difference is orthographic or a
naming convention — it CANNOT be a mapping error. That narrows the review to two rows:

    卦29  ours 習坎   biangua 坎    -- not 简繁
    卦33  ours 遯     biangua 遁    -- 異體/通假, not 简繁

Both must be checked against our own source rather than assumed. If our corpus really
prints 習坎, then our `gua_name` is right for THIS edition and biangua is using the common
short name — a difference to record, not a bug to fix.
"""
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.zhouyi import work_body  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
EXT = os.path.join(ROOT, "data", "external")

print("=" * 78)
print("PART 1 — do our sources really print 習坎 and 遯?")
print("=" * 78)
base = work_body(RAW, "KR1a0001")
for n, ours, theirs in ((29, "習坎", "坎"), (33, "遯", "遁")):
    print(f"\n卦{n}: ours={ours}  biangua={theirs}")
    # the heading our derivation read
    for m in re.finditer(r"《([一-鿿]{1,4})第([一二三四五六七八九十]{1,4})》", base):
        cn = m.group(2)
        num = {"二十九": 29, "三十三": 33}.get(cn)
        if num == n:
            print(f"  heading in KR1a0001: 《{m.group(1)}第{m.group(2)}》  "
                  f"context {base[max(0,m.start()-16):m.start()+22]!r}")
    # how often does each form appear across the 易類 corpus?
    for w in ("KR1a0001", "KR1a0006", "KR1a0007", "KR1a0031"):
        if not os.path.isdir(os.path.join(RAW, w)):
            continue
        b = work_body(RAW, w)
        print(f"  {w}: {ours}={b.count(ours):5}  {theirs}={b.count(theirs):5}")

print("\n" + "=" * 78)
print("PART 2 — audit the other three repos: is there any usable 卦 data?")
print("=" * 78)


def peek(path, needles, width=150, limit=6):
    if not os.path.exists(path):
        print(f"  MISSING {path}")
        return
    t = open(path, encoding="utf-8", errors="replace").read()
    print(f"  {os.path.basename(path)}  {len(t):,} chars")
    for nd in needles:
        hits = [m.start() for m in re.finditer(re.escape(nd), t)]
        print(f"    {nd!r}: {len(hits)} occurrence(s)")
        for h in hits[:limit]:
            frag = t[h:h + width].replace("\n", "\\n")
            print(f"      {frag}")
        if len(hits) > limit:
            print(f"      … {len(hits)-limit} more")


print("\n--- lyyxqg-lyy/suanle-me : src/lib/divination.ts ---")
peek(os.path.join(EXT, "suanle-me", "suanle-me-main", "src", "lib", "divination.ts"),
     ["乾", "GUA", "hexagram", "卦"], width=110, limit=3)

print("\n--- starloom/starloom : does it contain 卦 data or only prompts? ---")
sl = os.path.join(EXT, "starloom", "starloom-main")
if os.path.isdir(sl):
    hits = []
    for dp, _, fs in os.walk(sl):
        for f in fs:
            if f.endswith((".vue", ".py", ".json", ".ts", ".js")) and "node_modules" not in dp:
                p = os.path.join(dp, f)
                try:
                    t = open(p, encoding="utf-8", errors="replace").read()
                except OSError:
                    continue
                n = t.count("乾") + t.count("坤") + t.count("卦")
                if n:
                    hits.append((n, os.path.relpath(p, sl), len(t)))
    hits.sort(reverse=True)
    print(f"  files mentioning 乾/坤/卦: {len(hits)}")
    for n, rel, sz in hits[:8]:
        print(f"    {n:5} hits  {sz:>8,} chars  {rel}")

print("\n--- dreamhunter2333/chatgpt-tarot-divination : what generates the reading? ---")
ct = os.path.join(EXT, "chatgpt-tarot-divination", "chatgpt-tarot-divination-main")
if os.path.isdir(ct):
    for dp, _, fs in os.walk(ct):
        if "node_modules" in dp:
            continue
        for f in fs:
            if f.endswith(".py") and ("divination" in dp or "divination" in f):
                p = os.path.join(dp, f)
                t = open(p, encoding="utf-8", errors="replace").read()
                print(f"\n  {os.path.relpath(p, ct)}  {len(t):,} chars")
                for kw in ("prompt", "openai", "gpt", "卦"):
                    c = t.lower().count(kw.lower())
                    if c:
                        print(f"    {kw!r} x{c}")

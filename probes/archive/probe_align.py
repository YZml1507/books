"""Can we recover 卦 attribution in the commentaries by anchoring on the canonical text?

Idea: KR1a0001 gives us 64 卦 names + their 爻辭 verbatim. The commentaries quote the
經文 before commenting. So: build a canonical index of distinctive 爻辭 strings from
KR1a0001, then scan the commentary sequentially and carry forward the last matched 卦.
"""
import glob
import os
import re
from collections import Counter

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")

VARIANTS = {
    "𫝊": "傳", "𫝑": "勢", "𧰼": "象", "𢎞": "弘", "𨽻": "隸", "𩔖": "類",
    "𤣥": "玄", "説": "說", "眞": "真", "内": "內", "𥘉": "初", "𥙿": "裕",
    "𣏌": "杞", "𡵨": "岐", "𫉬": "獲",
}
GUA_RE = re.compile(r"《([^》]{1,4})第([一二三四五六七八九十]+)》")


def fold(s):
    return "".join(VARIANTS.get(c, c) for c in s)


def clean(s):
    s = re.sub(r"<pb:[^>]+>", "", s)
    s = re.sub(r"&\w+;", "", s)
    return re.sub(r"[¶\s　/「」『』《》，。、：；？！()]", "", fold(s))


# ---- 1. canonical: 卦 -> its distinctive phrases, from KR1a0001 ----
canon = {}   # gua -> list of phrases
order = []
for path in sorted(glob.glob(os.path.join(BASE, "KR1a0001", "*.txt"))):
    raw = open(path, encoding="utf-8").read()
    body = re.sub(r"^#.*$", "", raw, flags=re.M)
    cur = None
    for line in re.sub(r"<pb:[^>]+>", "", body).split("¶"):
        g = GUA_RE.search(line)
        if g:
            cur = g.group(1)
            if cur not in canon:
                canon[cur] = []
                order.append(cur)
            continue
        if cur:
            c = clean(line)
            if len(c) >= 4:
                canon[cur].append(c)

print(f"canonical 卦 recovered from KR1a0001: {len(canon)}")
print(f"  first 12: {order[:12]}")
print(f"  phrases per 卦: min={min(len(v) for v in canon.values())} "
      f"median={sorted(len(v) for v in canon.values())[len(canon)//2]} max={max(len(v) for v in canon.values())}")

# ---- 2. pick phrases that are UNIQUE to one 卦 (discriminative anchors) ----
phrase_owner = {}
dupes = set()
for gua, phrases in canon.items():
    for p in phrases:
        if len(p) < 5:
            continue
        if p in phrase_owner and phrase_owner[p] != gua:
            dupes.add(p)
        else:
            phrase_owner[p] = gua
for p in dupes:
    phrase_owner.pop(p, None)
print(f"\ndiscriminative phrases (>=5 chars, unique to one 卦): {len(phrase_owner)}")
per_gua = Counter(phrase_owner.values())
missing = [g for g in order if per_gua[g] == 0]
print(f"  卦 with at least one unique anchor: {len(per_gua)}/{len(canon)}")
if missing:
    print(f"  卦 with NO unique anchor: {missing}")

# ---- 3. scan a commentary sequentially, carry forward last matched 卦 ----
def attribute(repo):
    total = attributed = 0
    hits_by_gua = Counter()
    files = sorted(glob.glob(os.path.join(BASE, repo, "*.txt")))
    for path in files:
        raw = open(path, encoding="utf-8").read()
        body = re.sub(r"^#.*$", "", raw, flags=re.M)
        cur = None
        for seg in re.split(r"(<pb:[^>]+>)", body):
            if re.match(r"<pb:", seg or ""):
                continue
            for line in (seg or "").split("¶"):
                c = clean(line)
                if not c:
                    continue
                total += 1
                # try to (re)anchor on any discriminative phrase present in this line
                for p, gua in phrase_owner.items():
                    if len(p) <= len(c) and p in c:
                        cur = gua
                        break
                if cur:
                    attributed += 1
                    hits_by_gua[cur] += 1
    return total, attributed, hits_by_gua


for repo, label in (("KR1a0006", "王弼注"), ("KR1a0007", "注疏")):
    total, attributed, by_gua = attribute(repo)
    print(f"\n=== {repo} ({label}) ===")
    print(f"  units: {total}, attributed to a 卦: {attributed} = {100*attributed/max(total,1):.1f}%")
    print(f"  distinct 卦 touched: {len(by_gua)}/64")
    print(f"  top: {by_gua.most_common(8)}")

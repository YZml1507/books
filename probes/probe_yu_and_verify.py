"""Two jobs: verify the user's zips are byte-identical to mine, and decide 於/于 on evidence.

Part 1 exists because the user believed I had failed to fetch the repos. I had fetched all
five; the channel died during the LAST step (this frequency check). Comparing sha256 settles
it either way rather than by assertion — and if they differ, mine are suspect, not theirs.

Part 2 is the outstanding question. Measured corpus-wide: 於 12,198 vs 于 2,862, and the
direction INVERTS between editions:

    KR1a0001 底本    於    53   于   120     <- 于 dominant
    KR1a0006 王弼     於   544   于   217
    KR1a0007 註疏     於 2,121   于   497
    KR1a0031 本義     於   421   于   197

That is the D-003 pattern exactly: same corpus, opposite conventions per edition. External
witness confirms it at the phrase level — sunls2 prints 需於郊 where our 底本 has 需于郊, the
single difference that made 75 of 298 gold 爻辭 heads "not found" (the 74.8% figure).

My pre-stated criterion for this case was "both large -> inspect contexts, do not decide on
frequency alone". So: sample contexts and check whether 於 ever does work 于 cannot. The veto
condition is a compound or fixed expression where folding would corrupt meaning (L-04).
"""
import collections
import glob
import hashlib
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

RAW = os.path.join(ROOT, "data", "raw")
DL = r"C:\Users\Lenovo\Downloads\data-pull"
YU2, YU1 = "\u65bc", "\u4e8e"          # 於 , 于

print("=" * 78)
print("PART 1 — are the user's downloads identical to what I fetched?")
print("=" * 78)
man = {r["repo"].split("/")[1]: r
       for r in json.load(open(os.path.join(ROOT, "data", "catalog",
                                           "external_manifest.json"), encoding="utf-8"))
       if r.get("fetched")}
print(f"  {'zip':34} {'user':14} {'mine':14} same")
if os.path.isdir(DL):
    for f in sorted(os.listdir(DL)):
        p = os.path.join(DL, f)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        key = f.replace("-master.zip", "").replace("-main.zip", "")
        mine = man.get(key, {}).get("zip_sha256", "")
        print(f"  {f:34} {h[:14]} {mine[:14]} {h == mine}")
else:
    print(f"  {DL} not found")

print("\n" + "=" * 78)
print("PART 2 — 於/于: is folding safe? Contexts decide, not counts.")
print("=" * 78)
body = "".join(
    re.sub(r"^#.*$", "", open(p, encoding="utf-8").read(), flags=re.M)
    for d in sorted(os.listdir(RAW)) if os.path.isdir(os.path.join(RAW, d))
    for p in glob.glob(os.path.join(RAW, d, "*.txt")))
clean = re.sub(r"<pb:[^>]+>|[¶\s　/()（）]", "", body)


def bigrams_after(ch):
    c = collections.Counter()
    for m in re.finditer(re.escape(ch), clean):
        nxt = clean[m.end():m.end() + 1]
        if nxt:
            c[nxt] += 1
    return c


def bigrams_before(ch):
    c = collections.Counter()
    for m in re.finditer(re.escape(ch), clean):
        if m.start():
            c[clean[m.start() - 1]] += 1
    return c


for name, ch in (("於", YU2), ("于", YU1)):
    print(f"\n  --- {name} (U+{ord(ch):04X}) total {clean.count(ch):,} ---")
    print(f"    most common FOLLOWING char: "
          f"{[(k, v) for k, v in bigrams_after(ch).most_common(10)]}")
    print(f"    most common PRECEDING char: "
          f"{[(k, v) for k, v in bigrams_before(ch).most_common(10)]}")

print("\n  --- fixed expressions that would be rewritten by folding 於 -> 于 ---")
# A compound where 於 is not the preposition would be the veto.
COMPOUNDS = ["於是", "於此", "於斯", "於乎", "於戲", "於菟", "至於", "對於", "關於",
             "終於", "由於", "在於", "見於", "本於"]
for w in COMPOUNDS:
    n2 = clean.count(w)
    n1 = clean.count(w.replace(YU2, YU1))
    if n2 or n1:
        print(f"    {w:6} {n2:6,}    {w.replace(YU2, YU1):6} {n1:6,}")

print("\n  --- the decisive case: 於乎/於戲 (interjection, NOT the preposition) ---")
for w in ["於乎", "於戲", "於菟"]:
    for m in list(re.finditer(re.escape(w), clean))[:3]:
        print(f"    {w}: …{clean[max(0,m.start()-14):m.start()+16]}…")

print("\n  --- do the SAME 爻辭 differ only by 於/于 across our own editions? ---")
PAIRS = [("需于郊", "需於郊"), ("需于沙", "需於沙"), ("需于泥", "需於泥"),
         ("龍戰于野", "龍戰於野"), ("或躍在淵", "或躍在淵")]
for a, b in PAIRS:
    print(f"    {a} x{clean.count(a):<5}   {b} x{clean.count(b):<5}")

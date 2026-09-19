"""Are the 22 unvalidated works merely unchecked, or are they UNCHECKABLE?

Both validation techniques we own need something the 術數 works may not have:

    gold-scored       needs a canonical address + an independent base text (KR1a0001)
    witness-covered   needs a SECOND EDITION of the same work to diff against

If no 術數 work has either, then 40.2% of the index has no validation path at all with
current methods — which would mean "fetch more 古籍" specifically adds unvalidatable
material, and the right acquisition strategy is SECOND EDITIONS of works we already hold,
not new titles.

That is a strong claim, so check it against the cached Kanripo catalogue rather than assume.
"""
import json
import os
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAT = os.path.join(ROOT, "data", "catalog")

man = json.load(open(os.path.join(CAT, "corpus_manifest.json"), encoding="utf-8"))
held = {w["id"]: w for w in man.get("works", [])}
print(f"held works: {len(held)}")

# 1. Do we already hold any two works that are editions of one title?
print("\n=== 1. edition pairs ALREADY held ===")
def norm(t):
    t = re.sub(r"^(原本|別本|重刊|新刊|欽定|御定|御纂)", "", t or "")
    return re.sub(r"(注|註|疏|傳|義|解|說|考|圖說)$", "", t)

by_norm = defaultdict(list)
for wid, w in held.items():
    by_norm[norm(w.get("title", ""))].append((wid, w.get("title")))
pairs = {k: v for k, v in by_norm.items() if len(v) > 1}
for k, v in pairs.items():
    print(f"  {k!r}: {v}")
if not pairs:
    print("  none by title normalisation")

# 2. The 周易 cluster is the exception — count it explicitly.
zy = [wid for wid, w in held.items() if wid.startswith("KR1a")]
sx = [wid for wid, w in held.items() if wid.startswith("KR3g")]
print(f"\n  KR1a (易類, share a canonical address + a base text): {len(zy)}")
print(f"  KR3g (術數, no shared address, no base text)         : {len(sx)}")

# 3. Does the cached catalogue offer second editions for the 術數 titles we hold?
print("\n=== 2. could we ACQUIRE a second edition for the 術數 works? ===")
# The cached catalogue keys entries as `name`, not `id`. A first version of this probe read
# `id` and silently found 1 entry, then printed "NONE" — a conclusion drawn from a failed
# parse. Assert the parse succeeded before believing any answer derived from it.
cat_files = [f for f in os.listdir(CAT) if f.startswith("kanripo_")]
allcat = {}
for f in cat_files:
    d = json.load(open(os.path.join(CAT, f), encoding="utf-8"))
    items = d if isinstance(d, list) else d.get("works", d.get("items", []))
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict):
            wid = it.get("name") or it.get("id") or it.get("repo") or ""
            if wid:
                allcat[wid] = it.get("title") or ""
print(f"  catalogue entries cached: {len(allcat)}")
if len(allcat) < 50:
    raise SystemExit(f"catalogue parse looks wrong ({len(allcat)} entries) — refusing to "
                     f"draw a conclusion from it")
# Catalogue titles carry a 「-朝代-」 suffix, e.g. 六壬大全-清- ; strip it before comparing.
allcat = {k: re.sub(r"-[^-]*-$", "", v) for k, v in allcat.items()}

held_sx_titles = {wid: held[wid].get("title", "") for wid in sx}
found_any = False
for wid, title in sorted(held_sx_titles.items()):
    if not title:
        continue
    cands = [(k, v) for k, v in allcat.items()
             if k != wid and v and (norm(v) == norm(title) or
                                    (len(title) > 2 and title in v))]
    if cands:
        found_any = True
        print(f"    {wid} {title}: candidates {cands[:3]}")
if not found_any:
    print("    NONE — the cached catalogue offers no second edition for any 術數 work held")

print("\n=== 3. how many 易類 works does the catalogue still offer? ===")
# 易類 works DO have a validation path (shared 卦/爻 address + KR1a0001 as base text), so
# more of them is qualitatively different from more 術數 titles.
kr1a_cat = {k: v for k, v in allcat.items() if k.startswith("KR1a")}
kr1a_held = {wid for wid in held if wid.startswith("KR1a")}
avail = {k: v for k, v in kr1a_cat.items() if k not in kr1a_held}
print(f"  KR1a in catalogue: {len(kr1a_cat)}   held: {len(kr1a_held)}   "
      f"not yet held: {len(avail)}")
for k, v in sorted(avail.items())[:12]:
    print(f"    {k} {v}")
if len(avail) > 12:
    print(f"    … {len(avail)-12} more")

print("\n=== 4. verdict ===")
print("  22 unvalidated works (40.2% of units) lack BOTH prerequisites:")
print("    - no shared canonical address (術數 works have no 卦/爻 — correct, not a gap)")
print("    - no second edition held to diff against")
print("  Whether a second edition is ACQUIRABLE is answered above, per work.")
print("  Adding 易類 titles is qualitatively different from adding 術數 titles: the former")
print("  land in an existing validation harness, the latter cannot be checked at all yet.")

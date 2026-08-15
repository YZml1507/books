"""How much of the 古籍 text is unrepresentable in Unicode, and how do we align editions?"""
import glob
import os
import re
from collections import Counter

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "raw")


def whole(repo):
    return "".join(open(p, encoding="utf-8").read() for p in sorted(glob.glob(os.path.join(BASE, repo, "*.txt"))))


print("=== 1. Kanripo &KRxxxx; entities = glyphs with no Unicode codepoint ===")
for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
    t = whole(repo)
    ents = re.findall(r"&(KR\d+);", t)
    other_ents = re.findall(r"&([A-Za-z][A-Za-z0-9]*);", t)
    non_kr = [e for e in other_ents if not e.startswith("KR")]
    chars = len(re.sub(r"<pb:[^>]+>|&\w+;|[¶\s　]", "", t))
    print(f"  {repo}: {len(ents)} &KR entities ({len(set(ents))} distinct) over {chars} real chars "
          f"= {100*len(ents)/max(chars,1):.2f}%  | non-KR entities: {Counter(non_kr).most_common(5)}")
    if ents:
        print(f"     most frequent: {Counter(ents).most_common(6)}")

print("\n=== 2. Rare-plane characters (beyond BMP / in Ext-B+) that fonts may not render ===")
for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
    t = whole(repo)
    astral = [c for c in t if ord(c) > 0xFFFF]
    ext_b = [c for c in t if 0x20000 <= ord(c) <= 0x2FFFF]
    print(f"  {repo}: {len(astral)} chars > U+FFFF ({len(set(astral))} distinct); Ext-B+: {len(ext_b)}")
    if astral:
        print(f"     sample: {[(c, hex(ord(c))) for c in list(dict.fromkeys(astral))[:8]]}")

print("\n=== 3. The alignment problem: do editions share a common addressable unit? ===")
for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
    t = whole(repo)
    props = dict(re.findall(r"^#\+PROPERTY: (\w+) (.+)$", t, re.M)[:12])
    anchors = re.findall(r"<pb:(KR\w+)_([A-Za-z]+)_(\d+)-(\d+)([ab])>", t)
    eds = Counter(a[1] for a in anchors)
    print(f"  {repo}: BASEEDITION={props.get('BASEEDITION')!r} witnesses={dict(eds)} "
          f"juan_range={min((int(a[2]) for a in anchors), default=None)}..{max((int(a[2]) for a in anchors), default=None)}")

print("\n=== 4. Can we find the SAME passage across the three editions? ===")
needle_variants = ["天行健", "君子以自強不息", "潛龍勿用", "見龍在田"]
for needle in needle_variants:
    print(f"  {needle!r}:")
    for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
        t = whole(repo)
        flat = re.sub(r"<pb:[^>]+>|[¶\s　/]|&\w+;", "", t)
        cnt = flat.count(needle)
        print(f"     {repo}: {cnt} occurrence(s)")

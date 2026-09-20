"""Do the parentheses in KR1a0006/0007 actually delimit 注/疏? Print real samples."""
import glob
import os
import re

# canonical corpus (R18a: was a single-dirname probes/data/raw path that
# matched no existing directory — the historical scratch fetcher output)
BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw")


def load(repo, idx=0):
    files = sorted(glob.glob(os.path.join(BASE, repo, "*.txt")))
    return files[idx], open(files[idx], encoding="utf-8").read()


print("########## KR1a0006 (王弼注) — raw window around first parentheses ##########")
f, t = load("KR1a0006")
print(f"file: {os.path.basename(f)}")
body = t.split(">¶", 1)[-1]
# strip the org header block for readability
i = body.find("(")
print(body[max(0, i - 400):i + 700])

print("\n\n########## KR1a0007 (注疏) — window around a ○ marker ##########")
f2, t2 = load("KR1a0007", idx=3)
print(f"file: {os.path.basename(f2)}")
j = t2.find("○")
if j == -1:
    for k in range(len(sorted(glob.glob(os.path.join(BASE, 'KR1a0007', '*.txt'))))):
        f2, t2 = load("KR1a0007", idx=k)
        j = t2.find("○")
        if j != -1:
            print(f"(found in {os.path.basename(f2)})")
            break
print(t2[max(0, j - 700):j + 700])

print("\n\n########## paren content length distribution (are they 注 or just punctuation?) ##########")
for repo in ("KR1a0006", "KR1a0007"):
    whole = "".join(open(p, encoding="utf-8").read() for p in sorted(glob.glob(os.path.join(BASE, repo, "*.txt"))))
    # remove page anchors first so they don't pollute
    clean = re.sub(r"<pb:[^>]+>", "", whole)
    spans = re.findall(r"\(([^()]{0,400})\)", clean)
    lens = sorted(len(s.replace("¶", "")) for s in spans)
    if not lens:
        print(f"  {repo}: no paren spans")
        continue
    import statistics
    print(f"  {repo}: {len(spans)} spans, median len {statistics.median(lens)}, "
          f"p90 {lens[int(len(lens)*0.9)]}, max {lens[-1]}")
    print(f"     shortest 3: {[s.replace(chr(182),'') for s in spans[:0]] or [s.replace('¶','') for s in sorted(spans, key=len)[:3]]}")
    longsp = sorted(spans, key=len)[-2:]
    for s in longsp:
        print(f"     LONG ({len(s)}): {s.replace('¶','')[:220]}")

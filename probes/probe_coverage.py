import probe_pipeline as P
db = P.db
print("=== 卦 attribution coverage per repo ===")
for repo in ("KR1a0001","KR1a0006","KR1a0007"):
    tot = db.execute("SELECT count(*) FROM unit WHERE repo=?", (repo,)).fetchone()[0]
    got = db.execute("SELECT count(*) FROM unit WHERE repo=? AND gua IS NOT NULL", (repo,)).fetchone()[0]
    print(f"  {repo}: {got}/{tot} = {100*got/tot:5.1f}% have 卦")
print()
print("=== 爻 attribution coverage per repo ===")
for repo in ("KR1a0001","KR1a0006","KR1a0007"):
    tot = db.execute("SELECT count(*) FROM unit WHERE repo=?", (repo,)).fetchone()[0]
    got = db.execute("SELECT count(*) FROM unit WHERE repo=? AND yao IS NOT NULL", (repo,)).fetchone()[0]
    print(f"  {repo}: {got}/{tot} = {100*got/tot:5.1f}% have 爻")
print()
print("=== why: do KR1a0006/0007 contain 卦名 headings at all? ===")
import re, glob, os
for repo in ("KR1a0006","KR1a0007"):
    t = "".join(open(p,encoding="utf-8").read() for p in sorted(glob.glob(os.path.join(P.BASE,repo,"*.txt"))))
    print(f"  {repo}: 《X第N》 pattern hits = {len(P.GUA_RE.findall(t))}")
    print(f"     JUAN props: {re.findall(r'^#\+PROPERTY: JUAN (.+)$', t, re.M)[:8]}")

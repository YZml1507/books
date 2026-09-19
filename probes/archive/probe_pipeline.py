"""End-to-end feasibility spike: Kanripo -> structured units -> char-segmented FTS5
-> cross-commentator query with exact citations. Throwaway, but must actually work."""
import glob
import os
import re
import sqlite3
import sys

BASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "raw"
)

# --- variant folding table (the measured problem; a real system needs a much bigger one) ---
VARIANTS = {
    "𫝊": "傳", "𫝑": "勢", "𧰼": "象", "𢎞": "弘", "𨽻": "隸", "𩔖": "類",
    "𤣥": "玄", "説": "說", "眞": "真", "内": "內", "𥘉": "初", "𥙿": "裕",
    "𣏌": "杞", "𡵨": "岐", "𫉬": "獲", "𢎞": "弘", "𨗿": "邇", "𠔉": "𠔉",
}

GUA_RE = re.compile(r"《([^》]{1,4})第([一二三四五六七八九十]+)》")
YAO_RE = re.compile(r"^(初九|初六|九二|九三|九四|九五|上九|上六|六二|六三|六四|六五|用九|用六)")


def fold(s: str) -> str:
    return "".join(VARIANTS.get(c, c) for c in s)


def segment(s: str) -> str:
    """Char-segment CJK so FTS5 unicode61 can match 1-2 char queries."""
    out = []
    for ch in s:
        if "一" <= ch <= "鿿" or ord(ch) > 0xFFFF:
            out.append(" " + ch + " ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


def parse_kanripo(repo):
    """Yield units: (repo, juan_file, page_anchor, gua, yao, kind, text)."""
    for path in sorted(glob.glob(os.path.join(BASE, repo, "*.txt"))):
        raw = open(path, encoding="utf-8").read()
        title = (re.search(r"^#\+TITLE: (.+)$", raw, re.M) or [None, "?"])[1].strip()
        edition = (re.search(r"^#\+PROPERTY: BASEEDITION (\S+)", raw, re.M) or [None, "?"])[1].strip()
        body = re.sub(r"^#.*$", "", raw, flags=re.M)

        cur_anchor, cur_gua = None, None
        # split on page anchors, keeping them
        parts = re.split(r"(<pb:[^>]+>)", body)
        for part in parts:
            m = re.match(r"<pb:([^>]+)>", part or "")
            if m:
                cur_anchor = m.group(1)
                continue
            if not part or not part.strip():
                continue
            for line in part.split("¶"):
                line = line.strip().strip("　")
                if not line:
                    continue
                g = GUA_RE.search(line)
                if g:
                    cur_gua = g.group(1)
                # separate 注 (parenthesised) from base text
                notes = re.findall(r"\(([^()]*)\)", line)
                base = re.sub(r"\([^()]*\)", "", line)
                y = YAO_RE.match(base.lstrip("《》「」 "))
                yao = y.group(1) if y else None
                if base.strip():
                    yield (repo, title, edition, os.path.basename(path), cur_anchor, cur_gua, yao, "經", base.strip())
                for nt in notes:
                    nt = nt.replace("/", "")
                    if nt.strip():
                        yield (repo, title, edition, os.path.basename(path), cur_anchor, cur_gua, yao, "注", nt.strip())


# --- build the index ---
db = sqlite3.connect(":memory:")
db.execute("""CREATE TABLE unit(
    id INTEGER PRIMARY KEY, repo TEXT, title TEXT, edition TEXT, file TEXT,
    anchor TEXT, gua TEXT, yao TEXT, kind TEXT, text TEXT)""")
db.execute("CREATE VIRTUAL TABLE unit_fts USING fts5(seg, content='')")

rows = []
for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
    rows.extend(parse_kanripo(repo))

for i, r in enumerate(rows, start=1):
    db.execute("INSERT INTO unit VALUES (?,?,?,?,?,?,?,?,?,?)", (i,) + r)
    db.execute("INSERT INTO unit_fts(rowid, seg) VALUES (?,?)", (i, segment(fold(r[8]))))
db.commit()

print(f"indexed {len(rows)} units")
for repo in ("KR1a0001", "KR1a0006", "KR1a0007"):
    c = db.execute("SELECT kind, count(*) FROM unit WHERE repo=? GROUP BY kind", (repo,)).fetchall()
    t = db.execute("SELECT title, edition FROM unit WHERE repo=? LIMIT 1", (repo,)).fetchone()
    print(f"  {repo} {t[0]:8} ed={t[1]:6} {dict(c)}")

# --- the query that the whole system exists to answer ---
def search(q, limit=6, kind=None, repo=None):
    seg = segment(fold(q))
    sql = ("SELECT u.repo, u.title, u.edition, u.anchor, u.gua, u.yao, u.kind, u.text, "
           "bm25(unit_fts) AS score FROM unit_fts JOIN unit u ON u.id = unit_fts.rowid "
           "WHERE unit_fts MATCH ?")
    args = [seg]
    if kind:
        sql += " AND u.kind = ?"; args.append(kind)
    if repo:
        sql += " AND u.repo = ?"; args.append(repo)
    sql += " ORDER BY score LIMIT ?"
    args.append(limit)
    return db.execute(sql, args).fetchall()


print("\n" + "=" * 78)
print('TEST 1 — 2-char CJK query that plain FTS5 fails on: 「君子」')
for r in search("君子", limit=4):
    print(f"  [{r[0]} {r[1]} {r[2]}] {r[3]} 卦={r[4]} 爻={r[5]} {r[6]}: {r[7][:52]}")

print("\n" + "=" * 78)
print('TEST 2 — variant folding: 「傳」 should also match 𫝊')
hits = search("傳", limit=4, repo="KR1a0007")
print(f"  hits: {len(hits)}")
for r in hits:
    shown = r[7][:56]
    print(f"  {r[3]}: {shown}")
    print(f"      contains 𫝊? {'𫝊' in r[7]}   contains 傳? {'傳' in r[7]}")

print("\n" + "=" * 78)
print("TEST 3 — the real use case: what do 王弼 and 孔穎達 say about 乾卦九三?")
q = "君子終日乾乾"
for r in search(q, limit=8):
    tag = {"KR1a0001": "正文", "KR1a0006": "王弼注", "KR1a0007": "注疏"}[r[0]]
    print(f"  [{tag:6}] anchor={r[3]} kind={r[6]}")
    print(f"           {r[7][:88]}")

print("\n" + "=" * 78)
print("TEST 4 — citation completeness: can every hit be cited precisely?")
tot = db.execute("SELECT count(*) FROM unit").fetchone()[0]
no_anchor = db.execute("SELECT count(*) FROM unit WHERE anchor IS NULL").fetchone()[0]
no_gua = db.execute("SELECT count(*) FROM unit WHERE gua IS NULL").fetchone()[0]
print(f"  units without page anchor : {no_anchor}/{tot} ({100*no_anchor/tot:.1f}%)")
print(f"  units without 卦 attribution: {no_gua}/{tot} ({100*no_gua/tot:.1f}%)")

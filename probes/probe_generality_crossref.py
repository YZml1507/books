"""Generality falsification, extension: cross-scheme links, address aliasing, 3-chain consistency.

MASTER_PLAN §11 follow-up to probes/probe_generality_roundtrip.py. That probe showed every
scheme's address round-trips through (scheme, addr1, addr2). This probe attacks the parts
the round-trip cannot see:

  1. CROSS-SCHEME LINKS — the link table's 558 entries, grouped by (src_scheme, dst_scheme).
     If references ever crossed scheme boundaries (Euclid → BCV, say), the plugin model must
     survive it. Measured: all 558 are yilin→yilin, so the answer is "no cross-scheme links
     exist in the Source store" — a negative result, recorded not assumed.

  2. ADDRESS ALIASING — the same (addr1, addr2) appearing under two schemes is the Psalms-99
     == 卦99 hazard (D-005). Two sub-checks:
       a. cross-scheme alias set: how many (addr1, addr2) combos appear in >= 2 schemes, and
          does filtering by scheme return ONLY that scheme's rows (the isolation the API
          depends on)?
       b. within-scheme locativity: is (scheme, addr_name, addr1, addr2) unique per work,
          or do different works/books silently share one address? (For bcv, Genesis 1:1 and
          Exodus 1:1 share (1, 1) but differ in addr_name — the alias must be resolved by
          the FULL key, not the bare pair.)

  3. THREE-CHAIN CONSISTENCY — for a sampled unit, three independent paths must land on the
     SAME unit:
       addressing: (scheme, addr_name, addr1, addr2) -> unit id   (the G2/G3 path)
       retrieval:  FTS phrase of a distinctive substring -> unit  (the G1 path)
       citation:   a link whose dst is this unit resolves, and its target 卦名 is printed in
                   the src unit's text (the G4 path, but ALL 558 links, not eval_g4's 400)

Read-only. Numbers come from script output (GOAL §2).
"""
import os
import random
import sqlite3
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "index", "corpus.db")
random.seed(20260815)

sys.path.insert(0, os.path.join(ROOT, "src"))
from guji.ingest import derive_gua_names  # noqa: E402
from guji.yilin import NAME_ALIASES  # noqa: E402
from guji.variants import fold, segment_cjk  # noqa: E402
from guji.zhouyi import work_body  # noqa: E402

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row

print("=" * 78)
print("generality xref / alias / three-chain probe")
print("=" * 78)

# ---------------------------------------------------------------- 1. cross-scheme links
rows = db.execute("""
    SELECT l.id, l.note, l.src_unit, l.dst_unit,
           s.scheme AS ss, d.scheme AS ds, s.work_id AS sw, d.work_id AS dw
    FROM link l JOIN unit s ON s.id = l.src_unit JOIN unit d ON d.id = l.dst_unit
""").fetchall()
pairs = Counter((r["ss"], r["ds"]) for r in rows)
print(f"\n[1] link table: {len(rows)} entries, src_scheme x dst_scheme:")
for (ss, ds), n in sorted(pairs.items()):
    print(f"      {ss} -> {ds}: {n}")
cross = [r for r in rows if r["ss"] != r["ds"]]
print(f"      cross-scheme links: {len(cross)} "
      f"({'NONE — no cross-scheme reference exists in the Source store' if not cross else ''})")

# ---------------------------------------------------------------- 2a. cross-scheme alias
alias = db.execute("""
    SELECT addr1, addr2, COUNT(DISTINCT scheme) n, GROUP_CONCAT(DISTINCT scheme) sc
    FROM unit WHERE addr1 IS NOT NULL
    GROUP BY addr1, addr2 HAVING n > 1
""").fetchall()
print(f"\n[2a] cross-scheme address aliases: (addr1, addr2) present in >= 2 schemes: "
      f"{len(alias)}")
for a in alias[:10]:
    print(f"      addr1={a['addr1']} addr2={a['addr2']!r} schemes={a['sc']}")

# isolation: the API path at_address() hard-codes scheme='zhouyi' (search.py). The real
# test is not a SQL tautology — it is that a 卦-number query returns ONLY zhouyi rows even
# when another scheme carries the same (addr1, addr2) (Psalms-99 == 卦99, D-005).
sys.path.insert(0, os.path.join(ROOT, "src"))
from guji.search import Corpus  # noqa: E402

c = Corpus(DB)
leak = 0
checked = 0
for a in alias:
    scs = a["sc"].split(",")
    if "zhouyi" not in scs:
        continue
    checked += 1
    hits = c.at_address(a["addr1"], a["addr2"], limit=200)
    if any(h.scheme != "zhouyi" for h in hits):
        leak += 1
print(f"      at_address(addr1={alias[0]['addr1'] if alias else '?'}...) — zhouyi-aliased "
      f"addresses checked: {checked}, scheme-leak: {leak} "
      f"(0 = the API never returns another scheme's text for a 卦 address)")

# ---------------------------------------------------------------- 2b. within-scheme locativity
# TRUE alias = same (scheme, work, addr_name, addr1, addr2, LAYER) -> 2+ units. Multi-layer
# units at one address (經+注+疏 at the same 卦爻, X-07) are the designed structure, not an
# alias — so layer must be part of the key.
full_dup = db.execute("""
    SELECT scheme, work_id, addr_name, addr1, addr2, COUNT(*) n
    FROM unit WHERE addr1 IS NOT NULL
    GROUP BY scheme, work_id, addr_name, addr1, addr2, layer HAVING n > 1
""").fetchall()
print(f"\n[2b] same-work same-FULL-address+layer units: {len(full_dup)} "
      f"(true aliases; bcv's 9 known Vulgate Psalms-113/Prov-12:12 conflicts expected)")
by_scheme = Counter(f["scheme"] for f in full_dup)
print(f"      by scheme: {dict(by_scheme)}")
for f in full_dup[:8]:
    print(f"      {f['scheme']} {f['work_id']} {f['addr_name']} {f['addr1']} {f['addr2']} "
          f"n={f['n']}")

# ---------------------------------------------------------------- 3. three-chain consistency
_canon = derive_gua_names(work_body(os.path.join(ROOT, "data", "raw"), "KR1a0001"))
_alts: dict[str, set[str]] = {}
for _num, _nm in _canon.items():
    _alts.setdefault(fold(_nm), set()).add(fold(_nm))
for _alias, _num in NAME_ALIASES.items():
    if _num in _canon:
        _alts.setdefault(fold(_canon[_num]), set()).add(fold(_alias))

print("\n[3] three-chain consistency")

# 3a. citation chain: ALL 558 links — dst resolves, target 卦名 printed in src cell text
unsup = []
for r in rows:
    src_rows = db.execute("SELECT text FROM unit WHERE work_id=? AND addr1=? AND addr2=?",
                          (r["sw"], db.execute("SELECT addr1 FROM unit WHERE id=?",
                                               (r["src_unit"],)).fetchone()["addr1"],
                           db.execute("SELECT addr2 FROM unit WHERE id=?",
                                      (r["src_unit"],)).fetchone()["addr2"])).fetchall()
    blob = fold("".join(x["text"] for x in src_rows))
    d2 = db.execute("SELECT addr2 FROM unit WHERE id=?",
                    (r["dst_unit"],)).fetchone()["addr2"]
    want = fold(str(d2))
    forms = _alts.get(want, {want})
    if not any(f in blob for f in forms):
        unsup.append((r["id"], r["note"], sorted(forms), blob[:40]))
print(f"      links with target 卦名 NOT printed in src cell text: {len(unsup)}/{len(rows)}")
for u in unsup[:5]:
    print(f"        link {u[0]} note={u[1]!r} target={u[2]!r} not in {u[3]!r}")

# 3b. addressing chain on link endpoints: dst unit's OWN full key round-trips to itself
bad_addr = []
for r in rows:
    d = db.execute("SELECT scheme, addr_name, addr1, addr2 FROM unit WHERE id=?",
                   (r["dst_unit"],)).fetchone()
    if d["addr1"] is None:
        continue  # unaddressed dst (should not happen for yilin); counted separately
    hits = db.execute("SELECT id FROM unit WHERE scheme=? AND addr_name=? AND addr1=? "
                      "AND addr2 IS ?", (d["scheme"], d["addr_name"], d["addr1"],
                                         d["addr2"])).fetchall()
    if not any(h["id"] == r["dst_unit"] for h in hits):
        bad_addr.append((r["id"], r["dst_unit"], d["scheme"], d["addr1"], d["addr2"]))
print(f"      link dst units whose own address does not round-trip: {len(bad_addr)}")
for b in bad_addr[:5]:
    print(f"        link {b[0]} dst={b[1]} {b[2]} {b[3]} {b[4]}")

# 3c. retrieval chain: FTS phrase of a distinctive contiguous CJK run finds the unit.
# Token must be a CONTIGUOUS slice of the raw text: (1) unit.text can carry raw entity
# refs (&KRdddd;) which the FTS feed does NOT all decode (only &KR0658; does, 2c) — a token
# spliced across an entity is not contiguous in the index; (2) chars outside "一".."鿿"
# (Ext-A 䞇 U+4787, etc.) are not spaced by segment_cjk, so they glue to neighbours — a
# token that dropped such a char also does not exist contiguously. Skipping such units
# tests the retrieval chain, not the decoder or the segmenter.
def seg(q: str) -> str:
    return f'"{segment_cjk(fold(q)).replace(chr(34), "")}"'

def cjk_token(s: str) -> str | None:
    """First 8-char in-range window that starts at a real FTS token boundary.

    segment_cjk spaces only chars in "一".."鿿" (and >0xFFFF); anything else (ASCII entity
    refs, Ext-A 䞇 U+4787, punctuation) is left UNSPACED and glues to its neighbours in the
    index. A token window whose preceding char is such a gluer is not standalone in the FTS
    stream, so it tests the segmenter, not the retrieval chain — skip it.
    """
    n = len(s)
    for i in range(n - 7):
        win = s[i:i + 8]
        if not all("一" <= ch <= "鿿" for ch in win):
            continue
        if i > 0 and not ("一" <= s[i - 1] <= "鿿" or ord(s[i - 1]) > 0xFFFF):
            continue
        return win
    return None

sample = random.sample([r for r in rows if r["ss"] == "yilin"], min(30, len(rows)))
retr_fail = []
for r in sample:
    s = db.execute("SELECT text FROM unit WHERE id=?", (r["src_unit"],)).fetchone()["text"]
    tok = cjk_token(s)
    if tok is None:
        continue  # unit text is not a clean CJK run; not a retrieval-chain claim
    hits = db.execute(
        "SELECT u.id FROM unit_fts JOIN unit u ON u.id = unit_fts.rowid "
        "WHERE unit_fts MATCH ?", (seg(tok),)).fetchall()
    if not any(h["id"] == r["src_unit"] for h in hits):
        retr_fail.append((r["src_unit"], tok, len(hits)))
print(f"      sampled {len(sample)} link sources: FTS does not return the unit itself: "
      f"{len(retr_fail)}")
for rf in retr_fail[:5]:
    print(f"        unit {rf[0]} tok={rf[1]!r} top-hits={rf[2]}")

print("\n" + "=" * 78)
print("done — see per-check counts above; anything non-zero is a candidate falsification")
print()
print("=" * 78)
print("addendum — play-scheme locativity (Shakespeare addressing correctness)")
print("=" * 78)
# The round-trip probe proves address -> unit id is stable, but NOT that the address
# locates the content it claims. Gutenberg pg100.txt prints a per-play "Contents" block
# (compact "ACT I\nScene I.\n<setting>" list) before the body. ACT_RE matches those
# Contents ACT headers first, so every act's region collapses onto the Contents offsets and
# the address stops naming the content it covers. Body ACT headers are distinguishable: the
# next non-blank line is uppercase "SCENE", the Contents ones are mixed-case "Scene".
import re  # noqa: E402

_ACT_LINE = re.compile(r"(?m)^\s*ACT\s+([IVXL]+)\.?\s*$")
_SCENE_LINE = re.compile(r"(?m)^\s*SCENE\s+([IVXL]+)\.?")

raw_path = os.path.join(ROOT, "data", "raw_ext", "generality", "shakespeare", "pg100.txt")
raw = open(raw_path, encoding="utf-8", errors="replace").read()
# Body-ACT detection must use the SAME criterion play.py now uses (D-036 fix): an ACT
# header counts as a real body act iff an uppercase "SCENE n." occurs somewhere between it
# and the NEXT ACT header — NOT merely within a 200-char window. The narrower window
# misfires on plays whose act opens with a Chorus ("Enter Gower.") before its first SCENE
# (Pericles measured), producing false positives. Aligning the probe with the parser keeps
# the check honest about the parser it is auditing.
all_acts = sorted(m.start() for m in _ACT_LINE.finditer(raw))
body_acts = []  # (offset, roman)
for m in _ACT_LINE.finditer(raw):
    nxt = min((a for a in all_acts if a > m.start()), default=len(raw))
    if _SCENE_LINE.search(raw[m.start():nxt]):
        body_acts.append((m.start(), m.group(1)))

import bisect  # noqa: E402
play_units = db.execute(
    "SELECT id, raw_start, addr2 FROM unit WHERE scheme='play' "
    "AND addr2 LIKE 'ACT %' ORDER BY id").fetchall()
mis = 0
examples = []
for u in play_units:
    mm = re.match(r"ACT ([IVXL]+) SCENE", u["addr2"])
    if not mm:
        continue
    claimed = mm.group(1)
    offs = [b[0] for b in body_acts]
    i = bisect.bisect_right(offs, u["raw_start"]) - 1
    actual = body_acts[i][1] if i >= 0 else None
    if actual != claimed:
        mis += 1
        if len(examples) < 4:
            examples.append((u["id"], u["addr2"], actual, u["raw_start"]))
print(f"play units checked: {len(play_units)}, whose nearest preceding body-ACT != claimed "
      f"ACT: {mis}")
for e in examples:
    print(f"      unit {e[0]} addr2={e[1]!r} actual-preceding-ACT={e[2]!r} raw_start={e[3]}")
print("      => the play scheme's addresses do NOT locate their content "
      f"({'FALSIFIED' if mis else 'not falsified'})")
db.close()

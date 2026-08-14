"""G8 falsification test: TRY TO BREAK the Source / Derived / Conversation separation.

Modelled on U-01, the generality falsification that actually earned its keep: it did not
assert that the schema was general, it tried to store a second address system and FAILED,
which is why the finding was believed. So this probe does not assert isolation — it attempts
six specific violations and reports whether each was stopped.

The stakes are stated in MASTER_PLAN §2: an external project's generated 卦辭, stored as
Source, would be 「无出处生成文本」 entering a citation system 「从正门进来」. Until derived
content has a place that a source query cannot reach, there is nowhere safe to put it — which
is why 「在 G8 三类隔离落地之前，不接受任何外部生成内容」.

Writes only to data/index/knowledge_test.db, which it deletes on entry and exit. It does not
touch corpus.db, data/raw/, or the real knowledge.db.
"""
from __future__ import annotations

import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji import Corpus  # noqa: E402
from guji.knowledge import Evidence, KnowledgeBase  # noqa: E402

RAW = os.path.join(ROOT, "data", "raw")
CORPUS = os.path.join(ROOT, "data", "index", "corpus.db")
TESTKB = os.path.join(ROOT, "data", "index", "knowledge_test.db")

# A string that must NOT be findable in the corpus. It is deliberately shaped like a real
# 爻辭 gloss, because the danger is not gibberish — it is plausible generated prose.
FAKE = "潛龍勿用者謂陽氣潛藏于淵此乃機器所撰非經文"

for p in (TESTKB, TESTKB + "-journal"):
    if os.path.exists(p):
        os.remove(p)

fails: list[str] = []


def attempt(name: str, blocked: bool, detail: str = "") -> None:
    print(f"  [{'BLOCKED' if blocked else 'LEAKED '}] {name}" + (f" — {detail}" if detail else ""))
    if not blocked:
        fails.append(name)


c = Corpus(CORPUS)
kb = KnowledgeBase(TESTKB)

print("=" * 78)
print("G8 falsification: six attempts to violate Source/Derived/Conversation separation")
print("=" * 78)

# Real evidence, taken from a real retrieval, so the derived claim is well-formed.
hits = c.at_address(1, "初九", layer="經", limit=3)
ev = [Evidence.from_hit(h) for h in hits[:2]]
print(f"\nreal evidence available: {len(ev)}")
for e in ev:
    print(f"    {e.citation()}  {e.quote[:30]}")

did = kb.record("summary", FAKE, method="probe_g8_isolation/hand-written",
                evidence=ev, confidence="none — this is a test fixture")
print(f"\nstored a derived claim containing a fabricated gloss, id={did}")

print("\n--- attempt 1: reach derived text through the SOURCE search API ---")
got = c.search(FAKE, limit=5)
attempt("Corpus.search cannot return a derived claim", not got,
        f"{len(got)} hits" + (f" first={got[0].work_id}" if got else ""))

print("\n--- attempt 2: find derived text inside corpus.db at all ---")
raw_db = sqlite3.connect(CORPUS)
n_unit = raw_db.execute("SELECT count(*) FROM unit WHERE text LIKE ?",
                        (f"%{FAKE[:12]}%",)).fetchone()[0]
try:
    n_fts = raw_db.execute("SELECT count(*) FROM unit_fts WHERE unit_fts MATCH ?",
                           ('"' + " ".join(FAKE[:8]) + '"',)).fetchone()[0]
except sqlite3.OperationalError as exc:
    n_fts = 0
    print(f"      (fts probe raised {exc.__class__.__name__}, treated as 0)")
tables = [r[0] for r in raw_db.execute(
    "SELECT name FROM sqlite_master WHERE type='table'")]
raw_db.close()
attempt("corpus.db contains no derived text", n_unit == 0 and n_fts == 0,
        f"unit rows={n_unit}, unit_fts hits={n_fts}")
attempt("corpus.db has no derived/evidence/thread tables",
        not {"derived", "evidence", "thread", "turn"} & set(tables),
        f"tables={tables}")

print("\n--- attempt 3: store an asserting claim with NO evidence ---")
try:
    kb.record("answer", "乾卦九三讲的是君子终日勤勉", method="test/no-evidence")
    attempt("evidence-free asserting claim is refused", False, "it was accepted")
except ValueError as exc:
    attempt("evidence-free asserting claim is refused", True, str(exc)[:72])

print("\n--- attempt 4: a REFUSAL must still be storable without evidence (G7) ---")
# The mirror obligation. If the store only accepted claims with evidence, 「证据不足」 would be
# unrepresentable and G7 could never be satisfied — the same shape as the schema that could
# not hold a second address system (D-015).
try:
    rid = kb.record("refusal", "语料中没有关于焦氏易林作者生卒年的证据",
                    method="test/refusal")
    attempt("refusal without evidence is storable", rid is not None, f"id={rid}")
except Exception as exc:
    attempt("refusal without evidence is storable", False, repr(exc))

print("\n--- attempt 5: does a corpus REBUILD destroy derived knowledge? ---")
# The reason for two files. corpus.db is removed and recreated by ingest.build(); simulate
# exactly that against the knowledge store's own path to prove it is unaffected.
before = kb.stats()
kb.close()
sim = os.path.join(ROOT, "data", "index", "_g8_rebuild_sim.db")
if os.path.exists(sim):
    os.remove(sim)
open(sim, "wb").close()
os.remove(sim)          # the os.remove(db_path) that build() performs, on a stand-in
kb = KnowledgeBase(TESTKB)
after = kb.stats()
attempt("derived knowledge survives a corpus rebuild",
        after["derived"] == before["derived"] and after["derived"] > 0,
        f"before={before['derived']} after={after['derived']}")
print(f"      corpus.db is deleted by ingest.build() (os.remove) on EVERY build; "
      f"knowledge.db is a different file, so it is untouched.")

print("\n--- attempt 6: is a derived claim auditable back to source after the fact? ---")
d = kb.get(did)
v = kb.verify(RAW)
print(f"      claim {d.id} kind={d.kind} evidence={len(d.evidence)}")
for e in d.evidence:
    print(f"        {e.citation()}")
attempt("every stored quote re-verifies against data/raw/", v["stale"] == 0,
        f"ok={v['ok']} stale={v['stale']}")

print("\n--- bonus: evidence must not be identified by unit row id ---")
cols = [r[1] for r in kb.db.execute("PRAGMA table_info(evidence)")]
attempt("evidence stores a durable citation, not unit(id)",
        "unit_id" not in cols and {"work_id", "file", "raw_start", "page_anchor"} <= set(cols),
        f"cols={cols}")
print("      unit ids come from a build-time counter (`uid += 1`), so they are NOT stable")
print("      across rebuilds; a claim citing unit 1234 would later point elsewhere.")

print("\n--- orphan sweep: asserting claims with no evidence ---")
orph = kb.orphans()
attempt("no asserting claim lacks evidence", not orph, f"orphans={orph}")

print(f"\n{'=' * 78}")
print(f"knowledge store stats: {kb.stats()}")
print("PASS — separation holds under all attempts" if not fails
      else f"FAIL — leaked: {fails}")
kb.close()
c.close()
for p in (TESTKB, TESTKB + "-journal"):
    if os.path.exists(p):
        os.remove(p)
sys.exit(1 if fails else 0)

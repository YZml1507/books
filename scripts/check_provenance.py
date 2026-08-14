"""Provenance audit: MASTER_PLAN §9 requires sha256 / source_url / fetched_at / licence for
every acquisition. The index holds 28 works but corpus_manifest.json lists 25, so at least
three works were ingested outside the recorded pipeline. Find them and quantify the gap.

This is our own stated rule being violated, which matters more than an external repo's
missing LICENSE: an unprovenanced work cannot be re-fetched, re-verified, or licence-checked.
"""
import json
import os
import sqlite3
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

man = json.load(open(os.path.join(ROOT, "data", "catalog", "corpus_manifest.json"),
                    encoding="utf-8"))
listed = {w["id"]: w for w in man["works"]}
db = sqlite3.connect(os.path.join(ROOT, "data", "index", "corpus.db"))
db.row_factory = sqlite3.Row
rows = db.execute("SELECT id, title, genre, source_url, zip_sha256, licence, "
                  "fetched_at, n_files, n_chars FROM work ORDER BY id").fetchall()

print(f"index works: {len(rows)}    manifest works: {len(listed)}")

print("\n=== works with NO manifest entry (unprovenanced) ===")
orphans = [r for r in rows if r["id"] not in listed]
for r in orphans:
    print(f"  {r['id']:10} {(r['title'] or ''):14} genre={r['genre']}")
    print(f"     source_url={r['source_url']}")
    print(f"     sha256={r['zip_sha256']}  licence={r['licence']}  "
          f"fetched_at={r['fetched_at']}")
if not orphans:
    print("  none")

print("\n=== provenance completeness across the whole index ===")
fields = ["source_url", "zip_sha256", "fetched_at", "licence", "n_files", "n_chars"]
for f in fields:
    missing = [r["id"] for r in rows if not r[f]]
    print(f"  {f:12} missing {len(missing):3}/{len(rows)}"
          + (f"   e.g. {missing[:4]}" if missing else ""))

print("\n=== are the orphans' files actually on disk? ===")
RAW = os.path.join(ROOT, "data", "raw")
for r in orphans:
    d = os.path.join(RAW, r["id"])
    n = len([f for f in os.listdir(d) if f.endswith(".txt")]) if os.path.isdir(d) else 0
    print(f"  {r['id']:10} dir_exists={os.path.isdir(d)}  txt_files={n}  "
          f"db_says_units>0")

print("\n=== verdict ===")
print(f"  {len(orphans)} works are in the index with no recorded sha256 / url / fetch time.")
print("  They cannot be re-fetched or licence-audited from the record alone.")
print("  Fix is cheap (re-run the fetch probe for those ids, or backfill by inspecting the")
print("  source dirs) and it is OUR OWN rule (MASTER_PLAN §9), so it should not wait.")
db.close()

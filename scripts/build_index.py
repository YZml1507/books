"""Build the corpus index and verify it against the properties that must hold.

Verification is part of the build on purpose: three of the four properties checked here
were real bugs earlier in this project (silent FTS5 CJK failure, asymmetric variant
folding, page anchors that could not be traced to a file).

ORDERING NOTE: the `suspect` column (X-11) is populated from data/catalog/quality_report.json,
which scripts/check_quality.py produces by reading data/raw/ (it does not need the index).
So on a fresh checkout run check_quality.py FIRST. If the report is absent the build still
succeeds with no flags, prints it below, and records it in build_meta — verify_index.py then
fails the provenance assertion rather than letting an unflagged index look complete.
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.ingest import build  # noqa: E402

DB = os.path.join(ROOT, "data", "index", "corpus.db")
RAW = os.path.join(ROOT, "data", "raw")
MANIFEST = os.path.join(ROOT, "data", "catalog", "corpus_manifest.json")
QUALITY = os.path.join(ROOT, "data", "catalog", "quality_report.json")
EXT_DIR = os.path.join(ROOT, "data", "raw_ext", "generality")

if not os.path.exists(QUALITY):
    print("  !! data/catalog/quality_report.json absent — building with NO suspect flags.")
    print("     Run scripts/check_quality.py first, then rebuild.")

t0 = time.time()
stats = build(DB, RAW, MANIFEST, quality_report=QUALITY, ext_dir=EXT_DIR if os.path.isdir(EXT_DIR) else None)
print(f"built in {time.time() - t0:.1f}s")
print(f"  works          {stats.works}")
print(f"  units          {stats.units:,}")
print(f"  with 卦        {stats.addressed:,} ({100*stats.addressed/max(stats.units,1):.1f}%)")
print(f"  with 卦+爻     {stats.yao_addressed:,} "
      f"({100*stats.yao_addressed/max(stats.units,1):.1f}%)")
print(f"  with anchor    {stats.anchored:,} "
      f"({100*stats.anchored/max(stats.units,1):.1f}%)")
print(f"  db size        {os.path.getsize(DB)/1024/1024:.1f} MB")

# Disclosure summary (X-10/X-11). Printed at build time because a citation-integrity figure
# that nobody looks at is not a gate: 54% of units quote non-contiguously, and that is a
# property of the corpus's layout, not a defect to be hidden.
import sqlite3  # noqa: E402

_db = sqlite3.connect(DB)
_n, _skip, _susp, _worst = _db.execute(
    "SELECT count(*), sum(skipped_chars > 0), count(suspect), max(skipped_chars) "
    "FROM unit").fetchone()
_meta = dict(_db.execute("SELECT key, value FROM build_meta").fetchall())
_db.close()
print(f"  non-contiguous {_skip:,} ({100 * _skip / max(_n, 1):.1f}%)  "
      f"largest skip {_worst:,} chars")
print(f"  suspect        {_susp} units  (source: {_meta.get('suspect_source')}"
      f"{', ' + _meta['suspect_mtime'] if 'suspect_mtime' in _meta else ''})")

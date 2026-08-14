"""Backfill sha256 / source_url / licence for the generality test set. DRY RUN by default.

    python scripts/backfill_generality_provenance.py          # report only
    python scripts/backfill_generality_provenance.py --write  # rewrite the manifest

MASTER_PLAN §9 / GOAL §5: 「每次获取必须记 sha256 / source_url / fetched_at / licence」.
data/catalog/generality_manifest.json records fetched_at, gutenberg_id, title, authors and
copyright — but NOT sha256, source_url or a licence field. So the ten tier-1/2/3 books are in
the same state the three core 周易 works were in before W-06 backfilled them.

This computes hashes from the bytes ALREADY ON DISK and derives the URL from the recorded
Gutenberg id. It fetches nothing — GOAL §1 rules out network acquisition without asking, and
nothing here needs it. That distinction is the point: provenance can be reconstructed from what
we already hold plus what we already recorded, and reconstructing it is not a new acquisition.

Prerequisite for P-08 (indexing Herodotus + Darwin): a work must not enter the index without
provenance, so this comes first regardless of how the ingest path is written.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(ROOT, "data", "catalog", "generality_manifest.json")
EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
WRITE = "--write" in sys.argv


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


entries = json.load(open(MANIFEST, encoding="utf-8"))
if not isinstance(entries, list):
    print(f"unexpected manifest shape: {type(entries)}")
    raise SystemExit(2)

print(f"{'slug':16} {'gid':>7}  {'files':>5}  copyright / derived licence")
print("-" * 78)
changed = 0
for e in entries:
    slug = e.get("slug") or "?"
    gid = e.get("gutenberg_id")
    d = os.path.join(EXT, slug)
    on_disk = sorted(os.listdir(d)) if os.path.isdir(d) else []

    # Licence: Gutenberg texts are public domain in the US; the manifest's own `copyright`
    # field is the recorded evidence for that, so it is carried across rather than replaced by
    # an assumption. Anything unexpected is left as unknown rather than guessed.
    cp = str(e.get("copyright", "")).strip()
    if gid and ("public domain" in cp.lower() or cp == "" or cp.lower() in ("false", "none")):
        licence = "public-domain (Project Gutenberg)"
    else:
        licence = f"unknown — manifest copyright field reads {cp!r}"

    hashes = {f: sha256_of(os.path.join(d, f)) for f in on_disk}
    url = f"https://www.gutenberg.org/ebooks/{gid}" if gid else None

    print(f"{slug:16} {str(gid):>7}  {len(on_disk):5}  {cp!r} -> {licence}")
    for f, h in hashes.items():
        print(f"                              {f:20} {h[:16]}…")

    if e.get("source_url") != url or "file_sha256" not in e or e.get("licence") != licence:
        changed += 1
    e["source_url"] = url
    e["file_sha256"] = hashes
    e["licence"] = licence
    e["provenance_note"] = ("hashes computed from local bytes; url derived from the recorded "
                            "gutenberg_id; nothing re-fetched")

print("-" * 78)
missing = [e.get("slug") for e in entries
           if not e.get("source_url") or not e.get("file_sha256")]
print(f"entries needing an update: {changed}/{len(entries)}   still incomplete: {missing}")

if WRITE:
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
    print(f"-> wrote {os.path.relpath(MANIFEST, ROOT)}")
else:
    print("DRY RUN — nothing written. Re-run with --write to apply.")

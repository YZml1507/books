"""Merge generality_manifest.json into corpus_manifest.json.

corpus_manifest has {"works": [{"id": "KR...", ...}, ...]}.
generality_manifest is [{"slug": "bible-kjv", ...}, ...].

We map slug → id for generality works by using slug as the id.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

corpus_path = os.path.join(ROOT, "data", "catalog", "corpus_manifest.json")
gen_path = os.path.join(ROOT, "data", "catalog", "generality_manifest.json")

corpus = json.load(open(corpus_path, encoding="utf-8"))
gen = json.load(open(gen_path, encoding="utf-8"))

existing_ids = {w["id"] for w in corpus["works"]}

for work in gen:
    work_id = work.get("slug")
    if not work_id:
        print(f"warning: work without slug: {work}")
        continue
    if work_id in existing_ids:
        print(f"skipping duplicate: {work_id}")
        continue

    # Add id field matching slug
    work["id"] = work_id
    corpus["works"].append(work)
    print(f"added {work_id}")

with open(corpus_path, "w", encoding="utf-8") as f:
    json.dump(corpus, f, ensure_ascii=False, indent=2)

print(f"done. corpus now has {len(corpus['works'])} works.")

#!/usr/bin/env python3
"""Verify booksec-addressed works in the index."""
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "index", "corpus.db")

db = sqlite3.connect(DB)
rows = db.execute("""
    SELECT unit.work_id, work.title, scheme, COUNT(*) as n
    FROM unit JOIN work ON unit.work_id = work.id
    WHERE scheme = 'booksec'
    GROUP BY unit.work_id
""").fetchall()

if not rows:
    print("No booksec-addressed works found.")
    sys.exit(1)

for work_id, title, scheme, n in rows:
    print(f"{work_id:15} {title:30} {scheme:10} {n:5} units")

# Show a sample
sample = db.execute("""
    SELECT work_id, addr1, addr2, substr(text, 1, 60)
    FROM unit
    WHERE scheme = 'booksec'
    LIMIT 5
""").fetchall()

print("\nSample units:")
for work_id, book, sec, text in sample:
    print(f"  {work_id} Book {book} §{sec}: {text.strip()[:60]}...")

db.close()

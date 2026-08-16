#!/usr/bin/env python3
"""Verify Herodotus booksec structure."""
import os
import sqlite3

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "data", "index", "corpus.db")

db = sqlite3.connect(DB)

# Count books
books = db.execute("""
    SELECT COUNT(DISTINCT addr1) FROM unit WHERE work_id='herodotus'
""").fetchone()[0]

# Count sections per book
per_book = db.execute("""
    SELECT addr1, COUNT(*) FROM unit
    WHERE work_id='herodotus'
    GROUP BY addr1
    ORDER BY addr1
""").fetchall()

total_secs = sum(n for _, n in per_book)
print(f"Herodotus: {books} books, {total_secs} sections")
for book, n in per_book:
    print(f"  Book {book}: {n} sections")

db.close()

"""Test euclid.py parser on Euclid Elements html."""
import sys
sys.path.insert(0, "src")
from guji.euclid import parse_propositions, find_books, _strip_tags
from pathlib import Path

html = (Path("data/raw_ext/generality") / "euclid-elements" / "pg21076.html").read_text(encoding="utf-8", errors="replace")
text = _strip_tags(html)
print(f"stripped text chars: {len(text)}")

books = find_books(text)
print(f"\nbooks found: {len(books)}")
for n, s, e in books:
    print(f"  BOOK {n}  start={s}  end={e}  region_len={e-s}")

props = parse_propositions(html)
print(f"\npropositions found: {len(props)}")
from collections import Counter
bc = Counter(p.book for p in props)
for b in sorted(bc):
    print(f"  BOOK {b}: {bc[b]} propositions")

print("\n=== first 5 propositions ===")
for p in props[:5]:
    print(f"  BOOK {p.book} PROP {p.number} ({p.roman})  text[:80]={p.text[:80]!r}")

print("\n=== last 5 propositions ===")
for p in props[-5:]:
    print(f"  BOOK {p.book} PROP {p.number} ({p.roman})  text[:80]={p.text[:80]!r}")

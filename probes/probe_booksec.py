"""Does the `booksec` parser place Herodotus's sections correctly, and does Darwin
degrade to a chapter-only address without inventing one?

PRE-REGISTERED acceptance criteria, fixed before the first run:

  H1  4 book spans, numbered I-IV
  H2  per-book section counts within 3 of canonical: I 216 · II 182 · III 160 · IV 205
  H3  ZERO sections located inside a 「NOTES TO BOOK n」 block — the notes are a second
      ascending chain (U-04's shape) and must not be addressed as text
  H4  control passages resolve to text containing the expected phrase. Assert on RETURNED
      TEXT, never on a count (§3) — a count passes while the text is another section's
  H5  Darwin yields exactly 14 chapters and NO finer address is invented

H4's controls are chosen the way probe_bcv's were: each is a passage whose content is
checkable independently of this parser.
"""
from __future__ import annotations

import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from guji.booksec import NOTES_RE, book_spans, parse_sections  # noqa: E402

EXT = os.path.join(ROOT, "data", "raw_ext", "generality")
CANON = {1: 216, 2: 182, 3: 160, 4: 205}
CONTROLS = [
    (1, 1, ("Persians", "history")),
    (1, 6, ("Croesus",)),
    (2, 1, ("Cyrus", "Cambyses")),
    (3, 1, ("Cambyses",)),
    (4, 1, ("Scythia", "Scythians", "Darius")),
]

fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        fails.append(name)


def load(slug: str, ext: str = ".txt") -> str:
    d = os.path.join(EXT, slug)
    if not os.path.isdir(d):
        return ""
    for f in sorted(os.listdir(d)):
        if f.endswith(ext):
            return open(os.path.join(d, f), encoding="utf-8", errors="replace").read()
    return ""


raw = load("herodotus")
print(f"herodotus: {len(raw):,} chars")

print("\n=== H1: book spans ===")
spans = book_spans(raw)
for s in spans:
    print(f"  {s.label:10s} number={s.number}  @{s.start:>7,}  text ends @{s.text_end:>7,}"
          f"  ({s.text_end - s.start:,} chars)")
check("4 books, numbered I-IV", [s.number for s in spans] == [1, 2, 3, 4],
      f"{[s.number for s in spans]}")

print("\n=== H2: per-book section counts vs canonical ===")
secs = parse_sections(raw)
per: dict[int, list[int]] = {}
for s in secs:
    per.setdefault(s.book, []).append(s.number)
worst = 0
for b in sorted(CANON):
    got = per.get(b, [])
    want = CANON[b]
    delta = abs(len(got) - want)
    worst = max(worst, delta)
    missing = [n for n in range(1, want + 1) if n not in set(got)]
    print(f"  book {b}: {len(got):4d} sections (canonical {want})  delta {delta:2d}  "
          f"max={max(got) if got else 0}  missing={missing[:6]}"
          f"{'…' if len(missing) > 6 else ''}")
check("every book within 3 of canonical", worst <= 3, f"worst delta {worst}")
print(f"  total sections: {len(secs)} (canonical {sum(CANON.values())})")

print("\n=== H3: no section may fall inside a NOTES block ===")
notes_at = [m.start() for m in NOTES_RE.finditer(raw)]
book_end = {s.number: s.text_end for s in spans}
inside = [s for s in secs if s.start >= book_end.get(s.book, 0)]
print(f"  NOTES markers at {notes_at}")
check("zero sections inside the notes apparatus", not inside,
      f"{len(inside)} leaked")
for s in inside[:4]:
    print(f"      leaked: book {s.book} sec {s.number} @{s.start} {s.text[:50]!r}")

print("\n=== H4: control passages must contain their expected phrase ===")
index = {(s.book, s.number): s for s in secs}
for b, n, needles in CONTROLS:
    s = index.get((b, n))
    if not s:
        check(f"book {b} section {n} located", False, "not found")
        continue
    hit = [w for w in needles if w.lower() in s.text.lower()]
    check(f"book {b} section {n} contains one of {needles}", bool(hit),
          f"found {hit}; text: {s.text[:88]!r}")

print("\n=== H5: Darwin degrades to chapter-only, inventing nothing ===")
dar = load("darwin-origin")
if not dar:
    print("  darwin-origin has no .txt on disk — skipping (not a failure of booksec)")
else:
    print(f"  darwin: {len(dar):,} chars")
    ch = re.findall(r"(?m)^CHAPTER\s+([IVXLC]+|\d{1,2})\.?\s*$", dar)
    body = [c for c in ch]
    print(f"  own-line CHAPTER headings: {len(ch)}   distinct: {len(set(body))}")
    for pat, label in ((r"(?m)^\s*§", "§ section marks"),
                       (r"\[Page\s+\d+\]", "[Page n]"),
                       (r"\(p\.\s*\d+\)", "(p. n)")):
        print(f"  {label}: {len(re.findall(pat, dar))}")
    check("Darwin has 14 distinct chapters", len(set(body)) == 14,
          f"{len(set(body))} distinct from {len(ch)} headings")
    check("no finer address invented for Darwin",
          not re.search(r"\[Page\s+\d+\]", dar), "no [Page n] in the .txt")

print("\n" + "=" * 78)
print("booksec controls PASS" if not fails else f"FAILURES: {fails}")
sys.exit(1 if fails else 0)

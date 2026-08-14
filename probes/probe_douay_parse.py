"""Probe Douay-Rheims parser feasibility — simple, deterministic.

Run:
    ./.venv/Scripts/python.exe probes/probe_douay_parse.py
"""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

DOUAY_TXT = os.path.join(ROOT, "data", "raw_ext", "generality", "bible-douay", "pg1581.txt")

DOUAY_CHAP_RE = re.compile(r"^(\S.+) Chapter (\d+)\s*$")
DOUAY_VERSE_RE = re.compile(r"^(\d{1,3}):(\d{1,3})\.\s*(\S.*)$")

DOUAY_TO_BCV = {
    "Genesis": "Genesis", "Exodus": "Exodus", "Leviticus": "Leviticus",
    "Numbers": "Numbers", "Deuteronomy": "Deuteronomy", "Judges": "Judges",
    "Ruth": "Ruth", "Job": "Job", "Psalms": "Psalms", "Proverbs": "Proverbs",
    "Ecclesiastes": "Ecclesiastes", "Daniel": "Daniel", "Joel": "Joel",
    "Amos": "Amos", "Esther": "Esther", "Matthew": "Matthew", "Mark": "Mark",
    "Luke": "Luke", "John": "John", "Acts": "Acts", "Romans": "Romans",
    "James": "James", "Hebrews": "Hebrews",
    "1 Corinthians": "1 Corinthians", "2 Corinthians": "2 Corinthians",
    "Galatians": "Galatians", "Ephesians": "Ephesians",
    "Philippians": "Philippians", "Colossians": "Colossians",
    "1 Thessalonians": "1 Thessalonians", "2 Thessalonians": "2 Thessalonians",
    "1 Timothy": "1 Timothy", "2 Timothy": "2 Timothy",
    "Titus": "Titus", "Philemon": "Philemon",
    "1 Peter": "1 Peter", "2 Peter": "2 Peter",
    "1 John": "1 John", "2 John": "2 John", "3 John": "3 John", "Jude": "Jude",
    "Josue": "Joshua", "Isaias": "Isaiah", "Jeremias": "Jeremiah",
    "Ezechiel": "Ezekiel", "Osee": "Hosea", "Jonas": "Jonah",
    "Micheas": "Micah", "Nahum": "Nahum", "Habacuc": "Habakkuk",
    "Sophonias": "Zephaniah", "Aggeus": "Haggai", "Zacharias": "Zechariah",
    "Malachias": "Malachi", "Abdias": "Obadiah",
    "Canticle of Canticles": "Song of Solomon", "Apocalypse": "Revelation",
    "1 Kings": "1 Samuel", "2 Kings": "2 Samuel", "3 Kings": "1 Kings",
    "4 Kings": "2 Kings", "1 Paralipomenon": "1 Chronicles",
    "2 Paralipomenon": "2 Chronicles", "1 Esdras": "Ezra",
    "2 Esdras": "Nehemiah", "Tobias": "Tobit", "Judith": "Judith",
    "Wisdom": "Wisdom", "Ecclesiasticus": "Sirach",
    "1 Machabees": "1 Maccabees", "2 Machabees": "2 Maccabees",
    "Lamentations": "Lamentations", "Baruch": "Baruch",
}


def parse_douay(text):
    """Parse Douay-Rheims into (bcv_book, chapter, verse, text) tuples.

    Each verse is the text from its C:V. marker up to the next C:V. marker
    or chapter heading, accumulated across continuation lines.
    """
    lines = text.splitlines()
    out = []
    cur_bcv = None
    cur_chap = None
    cur_c, cur_v, buf = None, None, []

    def flush():
        if cur_c is not None and buf:
            out.append((cur_bcv, cur_chap, cur_c, cur_v, " ".join(buf).strip()))

    for line in lines:
        cm = DOUAY_CHAP_RE.match(line)
        if cm:
            flush()
            cur_bcv = DOUAY_TO_BCV.get(cm.group(1))
            cur_chap = int(cm.group(2))
            cur_c, cur_v, buf = None, None, []
            continue
        vm = DOUAY_VERSE_RE.match(line)
        if vm:
            flush()
            cur_c, cur_v = int(vm.group(1)), int(vm.group(2))
            buf = [vm.group(3)]
            continue
        if cur_c is not None and line.strip():
            buf.append(line.strip())

    flush()
    return out


def main():
    raw = open(DOUAY_TXT, encoding="utf-8", errors="replace").read()
    verses = parse_douay(raw)

    print("=== Douay parser probe ===")
    print("total verses parsed:", len(verses))

    books_seen = {}
    none_count = 0
    for b, ch, c, v, t in verses:
        if b is None:
            none_count += 1
        books_seen[b] = books_seen.get(b, 0) + 1
    print("distinct bcv books captured:", len(books_seen))
    print("verses with None book mapping:", none_count)

    print("\n=== first 5 verses ===")
    for b, ch, c, v, t in verses[:5]:
        print(f"  {b} {ch}:{c}.{v}  {t[:80]}")

    print("\n=== control: Genesis 1:1 ===")
    for b, ch, c, v, t in verses:
        if b == "Genesis" and ch == 1 and c == 1 and v == 1:
            print(f"  {t}")

    print("\n=== control: John 1:1 ===")
    for b, ch, c, v, t in verses:
        if b == "John" and ch == 1 and c == 1 and v == 1:
            print(f"  {t}")

    print("\n=== control: Psalms 23 (first 3) ===")
    count = 0
    for b, ch, c, v, t in verses:
        if b == "Psalms" and ch == 23:
            print(f"  {c}:{v}  {t[:80]}")
            count += 1
            if count >= 3:
                break

    # Address collisions: same (book, chap, verse) with different text
    addr_map = {}
    collisions = 0
    for b, ch, c, v, t in verses:
        key = (b, ch, c, v)
        if key in addr_map and addr_map[key] != t:
            collisions += 1
        addr_map[key] = t
    print("\naddress collisions (should be 0):", collisions)

    # Chapter count per book
    print("\n=== chapter count per book ===")
    chap_per_book = {}
    for b, ch, c, v, t in verses:
        chap_per_book.setdefault(b, set()).add(ch)
    for b in sorted(chap_per_book, key=lambda x: list(books_seen.keys()).index(x) if x in books_seen else 999):
        print(f"  {str(b):24s}  {len(chap_per_book[b]):3d} chapters, {books_seen[b]:5d} verses")

    print("\n=== probe complete ===")


if __name__ == "__main__":
    main()

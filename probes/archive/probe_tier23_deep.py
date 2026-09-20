"""Deep recon of tier 2/3 five books: print actual structure.

Goal: for each book, find the REAL address markers that exist in the bytes,
not the UNVERIFIED claims in TASK_LEDGER §14b.
"""
import re
import zipfile
from pathlib import Path

ROOT = Path("data/raw_ext/generality")


def read_text(slug, ext="txt"):
    for p in ROOT.glob(f"{slug}/*.{ext}"):
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


def body(t):
    m = re.search(r"\*\*\* START.*?\*\*\*", t, re.S)
    start = m.end() if m else 0
    m2 = re.search(r"\*\*\* END", t)
    end = m2.start() if m2 else len(t)
    return t[start:end], start


def plato_deep():
    print("=" * 70)
    print("PLATO REPUBLIC — deep recon")
    t = read_text("plato-republic")
    b, b0 = body(t)
    # All BOOK headings
    bk = re.findall(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b, re.M)
    print(f"BOOK headings n={len(bk)}")
    for i, (num, rest) in enumerate(bk[:25]):
        print(f"  [{i}] BOOK {num}  rest={rest[:50]!r}")
    # Is there a TOC?
    toc = re.search(r"^\s*CONTENTS\s*$", b, re.M | re.I)
    print(f"'CONTENTS' own line: {bool(toc)}")
    # Dialogue speakers — Jowett uses UPPERCASE names at line start
    speakers = re.findall(r"^([A-Z]{3,20})\s*[.;]", b, re.M)
    from collections import Counter
    sc = Counter(speakers)
    print(f"UPPERCASE speakers n={len(speakers)} distinct={len(sc)}")
    for name, n in sc.most_common(8):
        print(f"  {name:<20} {n}")
    # Books in the body after TOC — how many distinct?
    nums = set(num for num, _ in bk)
    print(f"distinct BOOK numerals: {sorted(nums)}")


def shakespeare_deep():
    print("=" * 70)
    print("SHAKESPEARE — deep recon")
    t = read_text("shakespeare")
    b, b0 = body(t)
    # Find the TOC and count entries
    lines = b.splitlines()
    # TOC usually near top
    toc_start = -1
    for i, l in enumerate(lines[:200]):
        if l.strip().lower() in ("contents", "contents."):
            toc_start = i
            break
    print(f"TOC start line={toc_start}")
    if toc_start >= 0:
        toc = []
        for l in lines[toc_start+1:toc_start+200]:
            s = l.strip()
            if not s:
                continue
            if s.lower().startswith("the sonnets") or s == "THE SONNETS":
                break
            toc.append(s)
        print(f"TOC entries (before SONNETS): {len(toc)}")
        for e in toc[:10]:
            print(f"  {e!r}")
    # Count ACT I/II/.../V on their own line — that's the real structure
    for roman in ["I", "II", "III", "IV", "V"]:
        n = len(re.findall(rf"^\s*ACT\s+{roman}\s*$", b, re.M))
        print(f"  ACT {roman} (own line): {n}")
    # SCENE patterns
    sc_own = len(re.findall(r"^\s*SCENE\s+[IVXL]+\s*$", b, re.M))
    sc_rest = len(re.findall(r"^\s*SCENE\s+[IVXL]+\.?\s+\S", b, re.M))
    print(f"SCENE n (own line): {sc_own}; SCENE n. text: {sc_rest}")
    # Dramatis Personae markers
    dp = len(re.findall(r"^\s*DRAMATIS\s+PERSONAE", b, re.M | re.I))
    print(f"DRAMATIS PERSONAE: {dp}")
    # How many distinct play titles (own-line, all caps)?
    titles = re.findall(r"^\s{0,4}([A-Z][A-Z\s,'\-—]{6,60})\s*$", b, re.M)
    from collections import Counter
    tc = Counter(t.strip() for t in titles)
    print(f"distinct ALL-CAPS own-line titles: {len(tc)}")
    for name, n in tc.most_common(15):
        print(f"  {name[:50]:<52} {n}")


def euclid_deep():
    print("=" * 70)
    print("EUCLID — deep recon (html only, no txt)")
    h = read_text("euclid-elements", "html")
    print(f"html chars={len(h)}")
    # Strip tags but preserve small-caps spans content
    # Small-caps are wrapped in <span class="smcap">...</span>
    smcap = re.findall(r'<span class="smcap"[^>]*>(.*?)</span>', h, re.S)
    sample = repr(smcap[0][:60]) if smcap else "none"
    print(f"smcap spans: {len(smcap)}; sample: {sample}")
    # What structure markers exist?
    for label, pat in [
        ("BOOK I", r"BOOK\s+I\b"),
        ("BOOK heading", r"<h[1-6][^>]*>\s*BOOK\s+[IVX]+"),
        ("PROPOSITION heading", r"<h[1-6][^>]*>\s*PROPOSITION"),
        ("DEFINITION heading", r"<h[1-6][^>]*>\s*D[EÉ]FINITION"),
        ("POSTULATE", r"POSTULATE"),
        ("AXIOM", r"AXIOM"),
        ("PROBLEM", r"PROBLEM"),
        ("THEOREM", r"THEOREM"),
        ("PROP. (any)", r"PROP\."),
        ("Q.E.D.", r"Q\.\s?E\.\s?D\."),
        ("Corollary / Cor.", r"\bCor\."),
        ("class=smcap", r'class="smcap"'),
        ("class=figure", r'class="figure"'),
        ("<img", r"<img[^>]*>"),
        ("<svg", r"<svg"),
    ]:
        ms = re.findall(pat, h)
        print(f"  {label:<28} n={len(ms)}")
    # epub parts — each part is a Book?
    for p in ROOT.glob("euclid-elements/*.epub"):
        with zipfile.ZipFile(p) as z:
            names = sorted([n for n in z.namelist() if n.lower().endswith((".xhtml", ".html"))])
            print(f"epub html parts: {len(names)}")
            for n in names:
                part = z.read(n).decode("utf-8", errors="replace")
                np = len(re.findall(r"PROP\.", part))
                nb = len(re.findall(r"BOOK\s+[IVX]+", part))
                nd = len(re.findall(r"D[EÉ]FINITION", part))
                ncor = len(re.findall(r"\bCor\.", part))
                if np or nb or nd or ncor:
                    print(f"  {n[-50:]:<52} PROP={np} BOOK={nb} DEF={nd} Cor={ncor}")


def darwin_deep():
    print("=" * 70)
    print("DARWIN — deep recon")
    t = read_text("darwin-origin")
    b, b0 = body(t)
    # CHAPTER on own line — what do they look like?
    ch = re.findall(r"^\s*CHAPTER\s+([IVXL]+|\d+)\.?\s*(.*)$", b, re.M)
    print(f"CHAPTER lines n={len(ch)}")
    # Distinguish roman vs arabic
    rom = [c for c in ch if c[0].isalpha()]
    arab = [c for c in ch if c[0].isdigit()]
    print(f"  roman CHAPTER: {len(rom)}; arabic: {len(arab)}")
    for i, (num, rest) in enumerate(ch[:15]):
        print(f"  [{i}] CHAPTER {num}  rest={rest[:50]!r}")
    # TOC?
    toc = re.search(r"^\s*(?:CONTENTS|Table of Contents)\s*$", b, re.M | re.I)
    print(f"TOC: {bool(toc)}")
    # Look for the SUMMARY/ANALYSIS that lists chapters
    # How many distinct roman numerals?
    rom_nums = set(c[0] for c in rom)
    print(f"distinct roman CHAPTER numerals: {sorted(rom_nums)}")
    # html page anchors
    h = read_text("darwin-origin", "html")
    pages = re.findall(r'id="Page(\d+)"', h)
    print(f"html id=PageN: {len(pages)}, range={pages[0]}..{pages[-1] if pages else '?'}")


def iliad_deep():
    print("=" * 70)
    print("HOMER ILIAD (Butler trans.) — deep recon")
    t = read_text("homer-iliad-but")
    b, b0 = body(t)
    bk = re.findall(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b, re.M)
    print(f"BOOK headings n={len(bk)}")
    for i, (num, rest) in enumerate(bk[:10]):
        print(f"  [{i}] BOOK {num}  rest={rest[:60]!r}")
    # Does Butler have paragraph breaks but no line numbers?
    # Count blank-line separated paragraphs
    paras = re.split(r"\n\s*\n", b)
    print(f"paragraphs (blank-line separated): {len(paras)}")
    # Is there a translator's preface / TOC?
    print(f"first 400 chars of body: {b[:400]!r}")

    print()
    print("HOMER ILIAD (Pope trans.) — deep recon")
    t2 = read_text("homer-iliad-pope")
    b2, b02 = body(t2)
    bk2 = re.findall(r"^\s*BOOK\s+([IVX]+)\.?\s*(.*)$", b2, re.M)
    print(f"BOOK headings n={len(bk2)}")
    for i, (num, rest) in enumerate(bk2[:10]):
        print(f"  [{i}] BOOK {num}  rest={rest[:60]!r}")
    # Pope's translation is verse — count couplets / lines
    # Verse lines typically end with specific patterns
    lines = b2.splitlines()
    print(f"total lines: {len(lines)}")
    # Right-margin line numbers
    rm = re.findall(r"\s(\d{2,4})\s*$", b2, re.M)
    print(f"right-margin line numbers: {len(rm)}, sample: {rm[:10]}")


if __name__ == "__main__":
    plato_deep()
    shakespeare_deep()
    euclid_deep()
    darwin_deep()
    iliad_deep()

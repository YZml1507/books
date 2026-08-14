"""Self-verify tier 2/3 five books' real address structure.

DO NOT trust the UNVERIFIED claims in TASK_LEDGER §14b.
Probe the raw bytes directly and report what address markers exist.

Books: Plato (Republic), Shakespeare, Euclid, Darwin, Iliad (2 translations).
"""
import re
import zipfile
from pathlib import Path

ROOT = Path("data/raw_ext/generality")


def txt(slug: str) -> str:
    for p in ROOT.glob(f"{slug}/*.txt"):
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


def html(slug: str) -> str:
    for p in ROOT.glob(f"{slug}/*.html"):
        return p.read_text(encoding="utf-8", errors="replace")
    return ""


def body(t: str) -> tuple[str, int]:
    m = re.search(r"\*\*\* START.*?\*\*\*", t, re.S)
    start = m.end() if m else 0
    m2 = re.search(r"\*\*\* END", t)
    end = m2.start() if m2 else len(t)
    return t[start:end], start


def count(label, pat, text, flags=0):
    ms = re.findall(pat, text, flags)
    print(f"    {label:<40} n={len(ms)}")
    return ms


def plato():
    print("=== Plato Republic ===")
    t = txt("plato-republic")
    b, b0 = body(t)
    print(f"  txt body chars={len(b)}")
    count("BOOK I..X heading own-line", r"^\s*BOOK\s+[IVX]+\.?\s*$", b, re.M)
    count("BOOK n (any)", r"BOOK\s+[IVX]+", b)
    count("Stephanus NNNa-e", r"\b\d{2,3}\s?[a-e]\b", b)
    count("word 'Stephanus'", r"[Ss]tephanus", b)
    count("word 'pagination'", r"pagination", b)
    count("dialogue speaker SOCRATES:", r"^\s*SOCRATES\s*:?", b, re.M)
    count("dialogue speaker GLAUCON:", r"^\s*GLAUCON\s*:?", b, re.M)
    # html
    h = html("plato-republic")
    print(f"  html chars={len(h)}")
    count("HTML NNNa-e", r"\b\d{2,3}\s?[a-e]\b", h)
    count("HTML 'Stephanus'", r"[Ss]tephanus", h)
    count("HTML <span class=marg", r'class="[^"]*(?:margin|marg|pagenum|linenum)[^"]*"', h)
    count("HTML id=page/pg", r'id="(?:page|pg|Page)[^"]*"', h)


def shakespeare():
    print("\n=== Shakespeare Complete Works ===")
    t = txt("shakespeare")
    b, b0 = body(t)
    print(f"  txt body chars={len(b)}")
    count("ACT n (own line)", r"^\s*ACT\s+[IVXL]+\s*$", b, re.M)
    count("ACT n. rest", r"^\s*ACT\s+[IVXL]+\..*$", b, re.M)
    count("SCENE n. rest", r"^\s*SCENE\s+[IVXL]+\.?(.*)$", b, re.M)
    count("ACT n (any line start)", r"^\s*ACT\s+[IVXL]+", b, re.M)
    # count TOC entries
    lines = b.splitlines()
    toc0 = next((i for i, l in enumerate(lines) if l.strip() == "Contents"), -1)
    if toc0 >= 0:
        toc = [l.strip() for l in lines[toc0+1:toc0+60] if l.strip()]
        print(f"  TOC at line {toc0}, {len(toc)} entries")
    # plays with no act/scene (poems)
    for w in ["THE SONNETS", "VENUS AND ADONIS", "A LOVER'S COMPLAINT"]:
        ms = re.findall(rf"^\s*{re.escape(w)}\s*$", b, re.M)
        print(f"    {w:<30} own-line={len(ms)}")


def euclid():
    print("\n=== Euclid Elements ===")
    h = html("euclid-elements")
    print(f"  html chars={len(h)}")
    count("HTML PROP. n", r"PROP\.\s*[IVXLC0-9]+", h)
    count("HTML BOOK n", r"BOOK\s+[IVX]+", h)
    count("HTML Définition", r"D[EÉ]F(?:INITION)?[SNIT]*", h)
    count("HTML class=", r'class="[^"]*"', h)
    count("HTML id=", r'id="([^"]+)"', h)
    count("HTML Q.E.D.", r"Q\.\s?E\.\s?D\.", h)
    count("HTML Cor.", r"\bCor\.", h)
    # epub
    for p in ROOT.glob("euclid-elements/*.epub"):
        with zipfile.ZipFile(p) as z:
            names = z.namelist()
            html_parts = [n for n in names if n.lower().endswith((".xhtml", ".html"))]
            print(f"  epub parts={len(html_parts)}")
            total_prop = 0
            for n in html_parts[:20]:
                try:
                    part = z.read(n).decode("utf-8", errors="replace")
                    np = len(re.findall(r"PROP\.\s*[IVXLC0-9]+", part))
                    total_prop += np
                    if np:
                        print(f"    {n[-40:]:<42} PROP.n={np}")
                except Exception as e:
                    print(f"    {n}: {e}")
            print(f"  epub total PROP. (first 20 parts)={total_prop}")


def darwin():
    print("\n=== Darwin Origin of Species ===")
    t = txt("darwin-origin")
    b, b0 = body(t)
    print(f"  txt body chars={len(b)}")
    count("CHAPTER n (own line)", r"^\s*CHAPTER\s+([IVXL]+|\d+)\.?\s*(.*)$", b, re.M)
    count("§ section sign", r"§", b)
    count("[Page n]", r"\[Page[^\]]*\]", b)
    count("(p. n)", r"\(p\.\s*\d+\)", b)
    # html page anchors
    h = html("darwin-origin")
    print(f"  html chars={len(h)}")
    count("HTML id=PageN", r'id="Page(\d+)"', h)
    count("HTML <span class=pagenum", r'class="[^"]*pagenum[^"]*"', h)


def iliad():
    print("\n=== Homer Iliad (Butler trans.) ===")
    t = txt("homer-iliad-but")
    b, b0 = body(t)
    print(f"  txt body chars={len(b)}")
    count("BOOK n (own line)", r"^\s*BOOK\s+([IVXL]+)\.?\s*$", b, re.M)
    count("BOOK I..XXIV heading", r"^\s*BOOK\s+[IVX]+", b, re.M)
    count("right-margin line number (2-4 digit at EOL)", r"\s\d{2,4}\s*$", b, re.M)
    count("standalone line number", r"^\s*\d{1,4}\s*$", b, re.M)
    count("(NN) paren form", r"\(\d{1,4}\)", b)
    count("'line NN'", r"line\s+\d+", b)
    print("\n=== Homer Iliad (Pope trans.) ===")
    t2 = txt("homer-iliad-pope")
    b2, b02 = body(t2)
    print(f"  txt body chars={len(b2)}")
    count("BOOK n (own line)", r"^\s*BOOK\s+([IVXL]+)\.?\s*$", b2, re.M)
    count("BOOK I..XXIV heading", r"^\s*BOOK\s+[IVX]+", b2, re.M)
    count("CANTO n", r"CANTO\s+[IVX]+", b2)
    count("right-margin line number", r"\s\d{2,4}\s*$", b2, re.M)


if __name__ == "__main__":
    plato()
    shakespeare()
    euclid()
    darwin()
    iliad()

"""Survey several real PDFs: text layer present? encoding corrupted? page labels? TOC?"""
import glob
import os
import sys
import pymupdf

EXT_A = lambda ch: "㐀" <= ch <= "䶿"
PUA = lambda ch: "" <= ch <= ""
CJK = lambda ch: "一" <= ch <= "鿿"

paths = sys.argv[1:]
print(f"{'file':44} {'pg':>4} {'chars/pg':>9} {'cjk%':>6} {'bad%':>6} {'toc':>4} {'enc':>10}  verdict")
print("-" * 118)
for p in paths:
    try:
        doc = pymupdf.open(p)
    except Exception as e:
        print(f"{os.path.basename(p)[:44]:44} OPEN FAIL {type(e).__name__}")
        continue
    n = doc.page_count
    sample_pages = range(min(15, n))
    total = cjk = bad = 0
    chars = 0
    for i in sample_pages:
        t = doc[i].get_text()
        chars += len(t.strip())
        for ch in t:
            if ch.isspace():
                continue
            total += 1
            if CJK(ch):
                cjk += 1
            elif EXT_A(ch) or PUA(ch):
                bad += 1
    encs = {f[5] for f in doc[0].get_fonts()} if n else set()
    enc = ",".join(sorted(e for e in encs if e))[:10]
    cjkpct = 100 * cjk / total if total else 0
    badpct = 100 * bad / total if total else 0
    perpage = chars / len(list(sample_pages)) if n else 0
    toc = len(doc.get_toc())
    if perpage < 50:
        verdict = "SCANNED -> needs OCR"
    elif badpct > 0.5:
        verdict = f"CORRUPT CMAP ({bad} bad glyphs)"
    else:
        verdict = "clean text layer"
    print(f"{os.path.basename(p)[:44]:44} {n:4} {perpage:9.0f} {cjkpct:6.1f} {badpct:6.2f} {toc:4} {enc:>10}  {verdict}")
    doc.close()

"""Throwaway probe: can we actually keep page numbers + structure on a real Chinese PDF?"""
import sys
import pymupdf

path = sys.argv[1]
doc = pymupdf.open(path)
print(f"file      : {path}")
print(f"pages     : {doc.page_count}")
print(f"metadata  : {doc.metadata}")
print(f"toc       : {doc.get_toc()[:10]}")
print(f"is_pdf    : {doc.is_pdf}, needs_pass: {doc.needs_pass}")

# Does the PDF have a real text layer, or is it a scan?
total_chars = 0
for i in range(min(5, doc.page_count)):
    total_chars += len(doc[i].get_text().strip())
print(f"chars in first 5 pages: {total_chars}  -> {'TEXT LAYER' if total_chars > 200 else 'LIKELY SCANNED (needs OCR)'}")

# Page-anchored extraction with block structure + font size (heading detection signal)
print("\n--- page 1 blocks (dict mode), showing span sizes ---")
d = doc[0].get_text("dict")
for b in d["blocks"][:6]:
    if b["type"] != 0:
        print(f"  [image block] bbox={tuple(round(v,1) for v in b['bbox'])}")
        continue
    for line in b["lines"][:2]:
        for span in line["spans"][:2]:
            print(f"  size={span['size']:.1f} font={span['font'][:24]:24} bbox={tuple(round(v,1) for v in span['bbox'])}")
            print(f"      text={span['text'][:60]!r}")

# Prove we can map any text back to (page, bbox) => citation anchor
print("\n--- citation anchor test: search a term, get page+bbox ---")
probe_terms = ["税收", "绿色", "影响", "the", "of"]
for term in probe_terms:
    hits = []
    for pno in range(doc.page_count):
        rects = doc[pno].search_for(term)
        if rects:
            hits.append((pno + 1, len(rects), tuple(round(v, 1) for v in rects[0])))
        if len(hits) >= 3:
            break
    if hits:
        print(f"  {term!r}: " + "; ".join(f"p{p} x{n} bbox={bb}" for p, n, bb in hits))

# Labeled page numbers (a PDF's printed page label can differ from index)
print("\n--- page labels (printed page number vs index) ---")
try:
    labels = [doc[i].get_label() for i in range(min(8, doc.page_count))]
    print(f"  labels: {labels}")
except Exception as e:
    print(f"  get_label unsupported: {e}")
doc.close()

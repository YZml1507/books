import sys, pymupdf
doc = pymupdf.open(sys.argv[1])
print("=== page 3 raw extracted text (first 600 chars) ===")
print(repr(doc[2].get_text()[:600]))
print()
print("=== page 5 ===")
print(repr(doc[4].get_text()[:400]))
doc.close()

"""Quantify the CNKI font-encoding corruption and test whether OCR is the only way out."""
import sys
import unicodedata
import pymupdf

path = sys.argv[1]
doc = pymupdf.open(path)

# Sample text across the document, count codepoints that are not sane Chinese/ASCII
CJK = lambda ch: "一" <= ch <= "鿿"
PUA = lambda ch: "" <= ch <= ""
# CJK Ext A: 0x3400-0x4DBF -- rare in real modern text, common as mis-mapped output
EXT_A = lambda ch: "㐀" <= ch <= "䶿"

stats = {"total": 0, "cjk": 0, "pua": 0, "ext_a": 0, "ascii": 0, "other": 0}
bad_samples = []
for pno in range(min(20, doc.page_count)):
    txt = doc[pno].get_text()
    for ch in txt:
        if ch.isspace():
            continue
        stats["total"] += 1
        if CJK(ch):
            stats["cjk"] += 1
        elif PUA(ch):
            stats["pua"] += 1
            if len(bad_samples) < 15:
                bad_samples.append((pno + 1, ch, hex(ord(ch)), "PUA"))
        elif EXT_A(ch):
            stats["ext_a"] += 1
            if len(bad_samples) < 15:
                bad_samples.append((pno + 1, ch, hex(ord(ch)), "CJK-ExtA"))
        elif ord(ch) < 128:
            stats["ascii"] += 1
        else:
            stats["other"] += 1

print("=== codepoint census over first 20 pages ===")
for k, v in stats.items():
    pct = 100 * v / stats["total"] if stats["total"] else 0
    print(f"  {k:8} {v:7}  {pct:5.1f}%")
corrupt = stats["pua"] + stats["ext_a"]
print(f"\n  suspected mis-mapped glyphs: {corrupt} ({100*corrupt/stats['total']:.1f}% of non-space chars)")
print("\n  samples:", bad_samples[:15])

# Are the fonts embedded with a ToUnicode CMap?
print("\n=== fonts on page 1 ===")
for f in doc[0].get_fonts():
    xref, ext, ftype, basefont, name, enc = f[:6]
    print(f"  xref={xref} type={ftype:12} basefont={basefont:34} enc={enc!r} ext={ext}")

# Does rendering + OCR bypass the problem? Check we can at least rasterize.
print("\n=== rasterization check (OCR fallback viability) ===")
pix = doc[0].get_pixmap(dpi=150)
print(f"  page1 raster: {pix.width}x{pix.height}, {len(pix.samples)/1024/1024:.1f} MB at 150dpi")
print(f"  -> full 74-page scan at 150dpi ~= {74*len(pix.samples)/1024/1024:.0f} MB of raw pixels")

# Does PyMuPDF's own text-extraction flag help?
print("\n=== alternate extraction modes on the corrupted title ===")
page = doc[0]
for mode in ("text", "blocks", "words", "rawdict"):
    try:
        out = page.get_text(mode)
        if mode == "text":
            s = out[:0]
        sample = ""
        if mode == "text":
            sample = out.strip().replace("\n", " ")[:0]
        print(f"  mode={mode:8} ok (type={type(out).__name__})")
    except Exception as e:
        print(f"  mode={mode:8} FAIL {e}")

# the actual title line, raw
print("\n=== raw title line as extracted ===")
for b in page.get_text("dict")["blocks"]:
    if b["type"] != 0:
        continue
    for line in b["lines"]:
        t = "".join(s["text"] for s in line["spans"])
        if len(t.strip()) > 8 and any(CJK(c) or EXT_A(c) for c in t):
            print(f"  {t.strip()[:70]!r}")
            break
    else:
        continue
    break
doc.close()

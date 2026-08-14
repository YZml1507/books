"""Round 3: find a real Ancient-Greek original, and measure HTML-level structure.

Two open questions after round 2:
  (a) PG52692 reports 8 Greek chars in 979k — so the Didot Greek is NOT in the
      plain text. Either it is a Latin-only volume or the encoding ate it. If
      there is no Greek Iliad on PG, the cross-lingual pair has to come from
      elsewhere (or the multi-translation item becomes English-vs-English).
  (b) figures / tables / equations only exist in HTML+EPUB, never in .txt, so
      the science pick must be chosen on its HTML.
"""
import json
import os
import re
import sys
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw_ext", "_probe")


def out(*a):
    print(*a)
    sys.stdout.flush()


def get(url, timeout=120):
    with opener.open(url, timeout=timeout) as r:
        return r.read()


# ---- (a1) what is actually inside pg52692? ----
p = os.path.join(CACHE, "pg52692.txt")
raw = open(p, "rb").read()
out(f"[52692] bytes={len(raw):,}  U+FFFD after utf8={raw.decode('utf-8','replace').count(chr(0xFFFD))}")
head = raw[:1200].decode("utf-8", "replace")
out("--- head ---")
out(head)
# beta code / transliteration markers
txt = raw.decode("utf-8", "replace")
for pat, lab in [(r"\[Greek:", "[Greek: tag"), (r"[ἀ-῿]", "polytonic"),
                 (r"[Α-Ωα-ω]", "monotonic-range")]:
    out(f"  {lab:16} {len(re.findall(pat, txt))}")

# ---- (a2) any Ancient Greek (grc) texts on PG at all? ----
for lang in ("grc", "la"):
    try:
        d = json.loads(get(f"https://gutendex.com/books?languages={lang}&search=Homer").decode())
        out(f"\n=== languages={lang} search=Homer ({d['count']}) ===")
        for b in d["results"][:12]:
            out(f"  {b['id']:>6} {b['title'][:64]:64} {b.get('languages')}")
    except Exception as e:
        out(f"!! {lang}: {type(e).__name__}: {e}")

try:
    d = json.loads(get("https://gutendex.com/books?languages=grc").decode())
    out(f"\n=== all grc on PG ({d['count']}) ===")
    for b in d["results"][:25]:
        out(f"  {b['id']:>6} {b['title'][:64]:64} {b.get('languages')}")
except Exception as e:
    out(f"!! grc list: {type(e).__name__}: {e}")

# ---- (b) HTML structure of science candidates ----
SCI = [(30155, "Einstein Relativity"), (5001, "Einstein Relativity 5001"),
       (21076, "Euclid Casey"), (2009, "Darwin Origin 6th"),
       (66944, "Principle of Relativity Bose/Saha")]
out("")
for pid, lab in SCI:
    try:
        meta = json.loads(get(f"https://gutendex.com/books/{pid}").decode())
    except Exception as e:
        out(f"[{pid} {lab}] meta fail {type(e).__name__}")
        continue
    hurl = None
    for m, u in meta["formats"].items():
        if m.startswith("text/html") and not u.endswith(".zip"):
            hurl = u
            break
    if not hurl:
        out(f"[{pid} {lab}] no html")
        continue
    try:
        h = get(hurl, 240).decode("utf-8", "replace")
    except Exception as e:
        out(f"[{pid} {lab}] html dl fail {type(e).__name__}")
        continue
    with open(os.path.join(CACHE, f"pg{pid}.html"), "w", encoding="utf-8") as f:
        f.write(h)
    counts = {
        "table": len(re.findall(r"<table", h, re.I)),
        "tr": len(re.findall(r"<tr", h, re.I)),
        "img": len(re.findall(r"<img", h, re.I)),
        "figure": len(re.findall(r"<figure|class=\"fig", h, re.I)),
        "sub_sup": len(re.findall(r"<su[bp]", h, re.I)),
        "math": len(re.findall(r"<math|MathJax|\\\(", h, re.I)),
        "eq_img": len(re.findall(r"<img[^>]+(?:eq|formula)", h, re.I)),
        "footnote": len(re.findall(r"footnote|class=\"fn", h, re.I)),
    }
    out(f"[{pid} {lab:26}] kb={len(h)//1024:>5} " +
        " ".join(f"{k}={v}" for k, v in counts.items() if v))

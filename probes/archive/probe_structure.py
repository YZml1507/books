"""Download candidate plain texts and measure the structural features we need.

Rationale: a book is only a useful parse-layer test if its DIGITISATION carries
the feature. Jowett's Republic is worthless as a Stephanus-numbering test if the
Gutenberg transcription dropped the Stephanus numbers. So we count, not assume.
"""
import json
import os
import re
import urllib.parse
import urllib.request

PROXY = "http://127.0.0.1:7897"
opener = urllib.request.build_opener(
    urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
)
opener.addheaders = [("User-Agent", "book-research-fetch/0.1")]

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "data", "raw_ext", "_probe")
os.makedirs(CACHE, exist_ok=True)

CANDIDATES = [
    (1497, "Plato Republic Jowett"),
    (55201, "Plato Republic Jowett 2"),
    (150, "Plato Republic 150"),
    (8438, "Aristotle Nicomachean Ethics"),
    (3800, "Spinoza Ethics"),
    (17611, "Summa Theologica I"),
    (6130, "Iliad Pope"),
    (2199, "Iliad Butler"),
    (3059, "Iliad Lang/Leaf/Myers"),
    (22382, "Iliad Buckley"),
    (2701, "Moby Dick"),
    (25717, "Gibbon 25717"),
    (731, "Gibbon 731"),
    (2707, "Herodotus v1 Macaulay"),
    (30155, "Einstein Relativity"),
    (1228, "Darwin Origin 1st ed"),
    (2009, "Darwin Origin 6th ed"),
    (21076, "Euclid Casey"),
]

FEATURES = {
    # Stephanus pagination as printed in translations: 327a / [327 a] / 514 a
    "stephanus": r"\b\d{3}\s?[a-e]\b",
    # Bekker: 1094a12 / 1103b
    "bekker": r"\b1[0-4]\d{2}\s?[ab]\b",
    "footnote_block": r"\[Footnote",
    "footnote_ref": r"\[\d{1,4}\]",
    "prop_def_axiom": r"^\s*(PROP\.|DEFINITION|AXIOM|Proposition|Prop\.)",
    "summa_article": r"(Whether .{5,90}\?|Objection \d+|Reply Obj\. \d+|ARTICLE \d)",
    "book_heading": r"^\s*(BOOK|Book) [IVXLCDM\d]+",
    "chapter_heading": r"^\s*(CHAPTER|Chapter) [IVXLCDM\d]+",
    "equation_ish": r"[=+\-]\s?\d.*?\bc\^?2\b|\\frac|√|\bsqrt\b|x\^2|²",
    "table_rule": r"^[ \t]*[-+|]{6,}[ \t]*$",
    "greek_chars": r"[Ͱ-Ͽἀ-῿]",
    "verse_lineno": r"^\s{0,20}\S.*?\s{2,}\d{2,4}\s*$",
}


def fetch_txt(pid):
    path = os.path.join(CACHE, f"pg{pid}.txt")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        with open(path, "rb") as f:
            return f.read().decode("utf-8", "replace"), "cache"
    try:
        with opener.open(f"https://gutendex.com/books/{pid}", timeout=90) as r:
            meta = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        return None, f"meta fail {type(e).__name__}"
    url = None
    for m, u in meta["formats"].items():
        if m.startswith("text/plain") and not u.endswith(".zip"):
            url = u
            if "utf-8" in m:
                break
    if not url:
        return None, "no text/plain"
    try:
        with opener.open(url, timeout=180) as r:
            blob = r.read()
    except Exception as e:
        return None, f"dl fail {type(e).__name__}"
    with open(path, "wb") as f:
        f.write(blob)
    return blob.decode("utf-8", "replace"), "fetched"


print(f"{'id':>6} {'label':26} {'kb':>6} {'src':8} features")
print("-" * 110)
for pid, label in CANDIDATES:
    text, how = fetch_txt(pid)
    if text is None:
        print(f"{pid:>6} {label:26} {'--':>6} {how}")
        continue
    hits = []
    for name, pat in FEATURES.items():
        n = len(re.findall(pat, text, re.M))
        if n >= 3:
            hits.append(f"{name}={n}")
    print(f"{pid:>6} {label:26} {len(text)//1024:>6} {how:8} {' '.join(hits)}")

# --- is there an ancient-Greek Homer, and a Greek/Latin original of anything? ---
for q in ["Homerus", "Ilias", "Odyssea Homer Greek", "Plato Greek"]:
    try:
        with opener.open(
            "https://gutendex.com/books?search=" + urllib.parse.quote(q), timeout=90
        ) as r:
            d = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"!! {q}: {e}")
        continue
    print(f"\n=== {q} ({d['count']}) ===")
    for b in d["results"][:10]:
        print(f"  {b['id']:>6} {b['title'][:60]:60} {b.get('languages')} "
              f"{'; '.join(a['name'] for a in b['authors'])[:34]}")
